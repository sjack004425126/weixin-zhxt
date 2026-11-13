"""毕业生就业情况与就业需求调查 控制器"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import or_, cast, Unicode, func
from init.database_optimized import get_db
from common.auth import verify_token_and_get_payload
from controllers.feedback import require_admin
from services.minio_service import sign_object_url
from models.models import (
    ZsCategory, ZsDict, ZsGraduateEmploymentSurvey,
    Student, Class, Teacher,
    ZzXs, ZzBj,
)
import json
import logging
import re

logger = logging.getLogger(__name__)
router = APIRouter()


def _mask_id_card(value):
    """身份证号脱敏：保留前 4 位与后 4 位，中间用 * 替代。
    长度小于 8 时整体用 * 替代，避免泄露。"""
    if not value:
        return ''
    s = str(value)
    n = len(s)
    if n <= 8:
        return '*' * n
    return s[:4] + '*' * (n - 8) + s[-4:]

CATEGORY_CODE = 'graduate_employment_survey'


def _get_category_id(db: Session) -> Optional[int]:
    cat = db.query(ZsCategory.id).filter(ZsCategory.code == CATEGORY_CODE).first()
    return cat[0] if cat else None


def _get_category(db: Session) -> Optional[ZsCategory]:
    return db.query(ZsCategory).filter(ZsCategory.code == CATEGORY_CODE).first()


def _check_window(category: Optional[ZsCategory]) -> Optional[str]:
    """校验采集时间窗口；返回错误消息（None 表示通过）。"""
    if not category:
        return '调查类别不存在或未配置'
    if not category.is_active:
        return '该调查已停用'
    now = datetime.now()
    if category.start_time and now < category.start_time:
        return f'调查未开始，开始时间：{category.start_time.strftime("%Y-%m-%d %H:%M")}'
    if category.end_time and now > category.end_time:
        return f'调查已结束，结束时间：{category.end_time.strftime("%Y-%m-%d %H:%M")}'
    return None


@router.get('/grad_emp_survey/info')
def get_info(db: Session = Depends(get_db)):
    """获取调查类别信息（批次/起止时间/状态），供前端时间窗判断。"""
    try:
        cat = _get_category(db)
        if not cat:
            raise HTTPException(status_code=404, detail='调查类别不存在')
        now = datetime.now()
        within = True
        msg = ''
        if not cat.is_active:
            within, msg = False, '该调查已停用'
        elif cat.start_time and now < cat.start_time:
            within, msg = False, f'调查未开始，开始时间：{cat.start_time.strftime("%Y-%m-%d %H:%M")}'
        elif cat.end_time and now > cat.end_time:
            within, msg = False, f'调查已结束，结束时间：{cat.end_time.strftime("%Y-%m-%d %H:%M")}'
        extra_info = {}
        if cat.extra_info:
            try:
                parsed = json.loads(cat.extra_info)
                if isinstance(parsed, dict):
                    extra_info = parsed
            except Exception:
                extra_info = {}
        return {
            'code': cat.code,
            'name': cat.name,
            'description': cat.description,
            'extra_info': extra_info,
            'batch': cat.batch,
            'start_time': cat.start_time.isoformat() if cat.start_time else None,
            'end_time': cat.end_time.isoformat() if cat.end_time else None,
            'is_active': bool(cat.is_active),
            'within_window': within,
            'window_message': msg,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f'获取调查类别信息失败: {e}')
        raise HTTPException(status_code=500, detail=f'获取调查信息失败: {e}')


@router.get('/grad_emp_survey/students')
def get_students(db: Session = Depends(get_db)):
    """一次性返回本调查类别下的全部学生字典（仅 dict_id / 学号 / 姓名），供前端本地缓存 + 本地过滤。
    数据量不大（3位数量级），加载开销可接受。
    """
    try:
        cat_id = _get_category_id(db)
        if not cat_id:
            return []

        items = db.query(ZsDict).filter(
            ZsDict.category_id == cat_id,
            ZsDict.type == 'student',
            ZsDict.is_active == 1
        ).order_by(ZsDict.sort_order, ZsDict.id).limit(5000).all()

        logger.info(f'[grad_emp_survey/students] cat_id={cat_id} total={len(items)}')

        return [{
            'dict_id': it.id,
            'xs_xh': it.code or '',
            'xs_xm': it.label or '',
        } for it in items]
    except Exception as e:
        logger.error(f'获取毕业生学生列表失败: {e}')
        raise HTTPException(status_code=500, detail=f'获取学生失败: {e}')


@router.get('/grad_emp_survey/students/detail')
def get_student_detail(student_no: str, db: Session = Depends(get_db)):
    """按单个学号获取学生详情（姓名/性别/班级/班主任/脱敏身份证）。
    用户在搜索列表中点选一条后调用，每次只查一个学号。
    返回统一封装：{success: bool, msg: str, data: {...}}
    """
    try:
        xh = (student_no or '').strip()
        if not xh:
            return {'success': False, 'msg': '学号不能为空'}

        # 越权校验：学号必须在本调查类别的学生字典内，避免任意枚举 oa_xs
        cat_id = _get_category_id(db)
        if not cat_id:
            return {'success': False, 'msg': '调查类别不存在'}
        dict_row = db.query(ZsDict.id).filter(
            ZsDict.category_id == cat_id,
            ZsDict.type == 'student',
            ZsDict.is_active == 1,
            ZsDict.code == xh
        ).first()
        if not dict_row:
            logger.info(f'[grad_emp_survey/students/detail] not in dict cat_id={cat_id} xh={xh}')
            return {'success': False, 'msg': f'学号 {xh} 不在本次调查范围内'}
        dict_id = dict_row[0]

        # 在调查范围内，再按学号在中职学生表 zz_xs 查学生主体信息（本调查面向中职毕业生）
        stu = db.query(ZzXs).filter(ZzXs.xh == xh).first()
        if not stu:
            logger.info(f'[grad_emp_survey/students/detail] not found in zz_xs xh={xh}')
            return {'success': False, 'msg': f'未在学生库中找到学号 {xh}'}

        # 班级 + 班主任：zz_bj.mc / zz_bj.bzr_id → oa_t.t_xm
        bj_mc = ''
        bzr = ''
        if stu.bj_id:
            cls = db.query(ZzBj).filter(ZzBj.id == stu.bj_id).first()
            if cls:
                bj_mc = cls.mc or ''
                if cls.bzr_id:
                    t = db.query(Teacher.t_xm).filter(Teacher.t_id == cls.bzr_id).first()
                    if t:
                        bzr = t[0] or ''

        return {
            'success': True,
            'msg': '',
            'data': {
                'dict_id': dict_id,
                'xs_xh': stu.xh or xh,
                'xs_xm': stu.xm or '',
                'xs_xb': stu.xb or '',
                'xs_sfzh': _mask_id_card(stu.sfzh),
                'bj_mc': bj_mc,
                'bzr': bzr,
            }
        }
    except Exception as e:
        logger.error(f'获取学生详情失败 xh={student_no}: {e}')
        return {'success': False, 'msg': f'获取学生详情失败: {e}'}


@router.get('/grad_emp_survey/students/debug')
def debug_students(db: Session = Depends(get_db)):
    """诊断接口：返回本调查类别下学生字典的总数及前 5 条 label，用于快速判断数据是否入库、中文是否被存为 '?'。"""
    cat_id = _get_category_id(db)
    if not cat_id:
        return {'category_id': None, 'total': 0, 'sample': [], 'msg': '未找到调查类别'}
    total = db.query(func.count(ZsDict.id)).filter(
        ZsDict.category_id == cat_id,
        ZsDict.type == 'student',
        ZsDict.is_active == 1
    ).scalar() or 0
    sample = db.query(ZsDict.id, ZsDict.code, ZsDict.label).filter(
        ZsDict.category_id == cat_id,
        ZsDict.type == 'student',
        ZsDict.is_active == 1
    ).order_by(ZsDict.sort_order, ZsDict.id).limit(5).all()
    return {
        'category_id': cat_id,
        'total': int(total),
        'sample': [{'id': r.id, 'code': r.code, 'label': r.label} for r in sample]
    }


@router.get('/grad_emp_survey/dict')
def get_dict(type: str, db: Session = Depends(get_db)):
    """获取调查表的字典列表（college 高校 / major 专业）"""
    try:
        cat_id = _get_category_id(db)
        if not cat_id:
            return []
        items = db.query(ZsDict).filter(
            ZsDict.category_id == cat_id,
            ZsDict.type == type,
            ZsDict.is_active == 1
        ).order_by(ZsDict.sort_order, ZsDict.id).all()
        return [{
            'id': it.id,
            'code': it.code,
            'label': it.label,
            'parent_code': it.parent_code,
            'remark': it.remark
        } for it in items]
    except Exception as e:
        logger.error(f'获取调查字典失败 type={type}: {e}')
        raise HTTPException(status_code=500, detail=f'获取字典失败: {e}')


class GradEmpSurveySubmit(BaseModel):
    # Q1
    student_no: Optional[str] = None
    student_name: str = Field(..., min_length=1, max_length=50)
    id_card: Optional[str] = None
    # Q2
    phone: str = Field(..., min_length=11, max_length=11)
    # Q3
    precise_service: Optional[str] = None
    # Q4
    destination: str = Field(...)
    # Q5
    military_office: Optional[str] = None
    # Q6
    education_level: Optional[str] = None
    # Q7
    college_code: Optional[str] = None
    college_name: Optional[str] = None
    # Q8
    major_code: Optional[str] = None
    major_name: Optional[str] = None
    # Q9
    admission_score: Optional[str] = None
    # Q10-18
    contract_type: Optional[str] = None
    employment_channel: Optional[str] = None
    company_name: Optional[str] = None
    work_province_city: Optional[str] = None
    work_address: Optional[str] = None
    company_nature: Optional[str] = None
    industry: Optional[str] = None
    position: Optional[str] = None
    position_name: Optional[str] = None
    monthly_salary: Optional[str] = None
    # Q19
    certificate_url: Optional[str] = None
    # Q20-22
    satisfaction: Optional[str] = None
    need_recommendation: Optional[str] = None
    feedback: Optional[str] = None


def _vs(v):
    """非空字符串校验辅助：去空白后判断"""
    return v is not None and str(v).strip() != ''


@router.post('/grad_emp_survey/submit')
def submit_survey(data: GradEmpSurveySubmit, db: Session = Depends(get_db)):
    """提交毕业生就业调查（按分支全部必填）"""
    try:
        import re
        if not re.match(r'^1[3-9]\d{9}$', data.phone or ''):
            return {'success': False, 'msg': '手机号格式不正确'}

        # 基础必填
        if not _vs(data.student_name):
            return {'success': False, 'msg': '请选择本人姓名'}
        if not _vs(data.precise_service):
            return {'success': False, 'msg': '请选择是否精准服务'}
        if not _vs(data.destination):
            return {'success': False, 'msg': '请选择毕业去向'}

        d = str(data.destination)
        # 分支必填
        if d == '1':
            for field, msg in [
                ('contract_type', '请选择合同/协议签订情况'),
                ('employment_channel', '请选择就业渠道'),
                ('company_name', '请输入工作单位名称'),
                ('work_province_city', '请选择单位所在省份/城市'),
                ('work_address', '请输入单位详细地址'),
                ('company_nature', '请选择单位性质'),
                ('industry', '请选择所处行业'),
                ('position_name', '请输入工作岗位'),
                ('monthly_salary', '请填写当前月薪'),
            ]:
                if not _vs(getattr(data, field, None)):
                    return {'success': False, 'msg': msg}
        elif d == '2':
            if not _vs(data.military_office):
                return {'success': False, 'msg': '请输入征兵办公室全称'}
        elif d == '3':
            for field, msg in [
                ('company_name', '请输入工作单位名称'),
                ('work_province_city', '请选择单位所在省份/城市'),
                ('work_address', '请输入单位详细地址'),
                ('company_nature', '请选择单位性质'),
                ('industry', '请选择所处行业'),
                ('position_name', '请输入工作岗位'),
                ('monthly_salary', '请填写当前月薪'),
            ]:
                if not _vs(getattr(data, field, None)):
                    return {'success': False, 'msg': msg}
        elif d == '4':
            for field, msg in [
                ('industry', '请选择所处行业'),
                ('position_name', '请输入工作岗位'),
                ('monthly_salary', '请填写当前月薪'),
            ]:
                if not _vs(getattr(data, field, None)):
                    return {'success': False, 'msg': msg}
        elif d in ('5', '6', '7', '8'):
            for field, msg in [
                ('education_level', '请选择升学层次'),
                ('college_code', '请选择录取高校'),
                ('major_code', '请选择录取专业'),
                ('admission_score', '请输入录取分数'),
            ]:
                if not _vs(getattr(data, field, None)):
                    return {'success': False, 'msg': msg}

        # 凭证 & 满意度：1-8 必填
        if d in ('1', '2', '3', '4', '5', '6', '7', '8'):
            if not _vs(data.certificate_url):
                return {'success': False, 'msg': '请上传就业凭证'}
            if not _vs(data.satisfaction):
                return {'success': False, 'msg': '请选择对当前就业现状是否满意'}
        # 推荐：除 10 外必填
        if d != '10':
            if not _vs(data.need_recommendation):
                return {'success': False, 'msg': '请选择是否需要学校就业推荐'}
        # 其他意见或建议：所有分支必填
        if not _vs(data.feedback):
            return {'success': False, 'msg': '请填写其他意见或建议，如无请填“无”'}

        # 类别 + 时间窗口校验
        category = _get_category(db)
        win_err = _check_window(category)
        if win_err:
            return {'success': False, 'msg': win_err}

        # 同一学生（按学号）只能提交一次（如有学号）
        if data.student_no:
            existing = db.query(ZsGraduateEmploymentSurvey).filter(
                ZsGraduateEmploymentSurvey.student_no == data.student_no
            ).first()
            if existing:
                return {'success': False, 'msg': '该学生已提交过调查，请勿重复提交'}

        # 身份证号以服务端权威数据（zz_xs.sfzh）为准，避免前端被篡改或回写脱敏值
        real_id_card = data.id_card
        if data.student_no:
            stu = db.query(ZzXs).filter(ZzXs.xh == data.student_no).first()
            if stu and stu.sfzh:
                real_id_card = stu.sfzh
        # 兜底：如果仍带 *，丢弃
        if real_id_card and '*' in str(real_id_card):
            real_id_card = None

        record = ZsGraduateEmploymentSurvey(
            batch=category.batch,
            student_no=data.student_no,
            student_name=data.student_name.strip(),
            id_card=real_id_card,
            phone=data.phone,
            precise_service=data.precise_service,
            destination=data.destination,
            military_office=data.military_office,
            education_level=data.education_level,
            college_code=data.college_code,
            college_name=data.college_name,
            major_code=data.major_code,
            major_name=data.major_name,
            admission_score=data.admission_score,
            contract_type=data.contract_type,
            employment_channel=data.employment_channel,
            company_name=data.company_name,
            work_province_city=data.work_province_city,
            work_address=data.work_address,
            company_nature=data.company_nature,
            industry=data.industry,
            position=data.position,
            position_name=data.position_name,
            monthly_salary=data.monthly_salary,
            certificate_url=data.certificate_url,
            satisfaction=data.satisfaction,
            need_recommendation=data.need_recommendation,
            feedback=data.feedback,
            submit_time=datetime.now()
        )
        
        # 生成查询码（在insert之前赋值，一次commit）
        from utils.query_code import generate_unique_query_code, get_query_code_expire_time
        query_code = generate_unique_query_code(db, 'zs_graduate_employment_survey')
        record.query_code = query_code
        record.query_code_expire = get_query_code_expire_time()
        
        db.add(record)
        db.commit()
        db.refresh(record)
        
        # 短信通知用户查询码
        try:
            from utils.sms import SMSTool
            sms_tool = SMSTool()
            sms_tool.send_by_scenario(
                scenario='query_code',
                mobile=data.phone,
                values={
                    'name': data.student_name.strip(),
                    'query_code': query_code,
                    'biz_name': '毕业生就业调查',
                },
                xs_xm=data.student_name.strip(),
            )
        except Exception as sms_err:
            logger.error(f'提交成功但短信发送失败: {sms_err}')

        logger.info(f'毕业生就业调查提交成功: {data.student_name}-{data.phone}, query_code={query_code}')
        return {'success': True, 'msg': '提交成功', 'data': {'id': record.id, 'query_code': query_code}}
    except Exception as e:
        db.rollback()
        logger.error(f'毕业生就业调查提交失败: {e}')
        return {'success': False, 'msg': f'系统异常，提交失败: {e}'}


# ============================================================
# 管理员后台：列表 + 详情（含就业凭证图片代理 URL）
# 鉴权：admin 小程序登录后的 token（feedback-admin 表里的角色）
# 图片：DB 里存的是历史带签名 URL（可能已过期），这里重新签名为当前可用的代理 URL
# ============================================================

_OBJECT_KEY_FROM_URL_RE = re.compile(r'/object/(private/[^?&\s]+)')
# DB 里存的纯净 object_key，前缀只允许 private/
_BARE_KEY_RE = re.compile(r'^(?:/)?(private/[\w./\-]+)$')


def _extract_object_key(certificate_url: Optional[str]) -> Optional[str]:
    """从以下两种形式提取 object_key：

    1. 旧历史 /object/{key}?t=&s= 形式（脏数据兼容）
    2. 新规范：纯净的 object_key，例 private/zs/<uuid>.png

    非法返回 None。
    """
    if not certificate_url:
        return None
    s = str(certificate_url).strip()
    m = _BARE_KEY_RE.match(s)
    if m:
        return m.group(1).lstrip('/')
    m = _OBJECT_KEY_FROM_URL_RE.search(s)
    if m:
        return m.group(1).lstrip('/')
    return None


def _signed_certificate_url(certificate_url: Optional[str]) -> Optional[str]:
    """将 DB 中的 object_key / 历史 URL 转换为当前可用的签名 URL。

    - 纯净 key（private/zs/...）：直接 sign_object_url(key)
    - 旧 /object/ 形式（脏数据）：剥出 key 后再签名
    - 其他情况（如旧的 feedback/ 路径）保持原样
    """
    key = _extract_object_key(certificate_url)
    if not key:
        return certificate_url or None
    try:
        return sign_object_url(key)
    except Exception as e:
        logger.warning(f'重新签名 certificate_url 失败: {e}; key={key}')
        return certificate_url or None


def _mask_phone(value: Optional[str]) -> str:
    s = (value or '').strip()
    if len(s) >= 7:
        return s[:3] + '****' + s[-4:]
    return s


_DESTINATION_LABELS = {
    '1': '签订合同或就业协议就业',
    '2': '应征义务兵',
    '3': '自主创业',
    '4': '灵活就业',
    '5': '普通高考升学',
    '6': '职教高考升学',
    '7': '出国、出境升学',
    '8': '贯通培养升学',
    '9': '待就业',
    '10': '不就业拟升学',
    '11': '其他暂不就业',
}


def _record_to_brief_dict(r: ZsGraduateEmploymentSurvey) -> dict:
    return {
        'id': r.id,
        'batch': r.batch,
        'student_no': r.student_no,
        'student_name': r.student_name,
        'phone': _mask_phone(r.phone),
        'destination': r.destination,
        'destination_label': _DESTINATION_LABELS.get(r.destination or '', r.destination or ''),
        'company_name': r.company_name,
        'college_name': r.college_name,
        'major_name': r.major_name,
        'has_certificate': bool(r.certificate_url),
        'submit_time': r.submit_time.isoformat() if r.submit_time else None,
    }


def _record_to_detail_dict(r: ZsGraduateEmploymentSurvey) -> dict:
    base = _record_to_brief_dict(r)
    base.update({
        'id_card': r.id_card,
        'precise_service': r.precise_service,
        'military_office': r.military_office,
        'education_level': r.education_level,
        'college_code': r.college_code,
        'major_code': r.major_code,
        'admission_score': r.admission_score,
        'contract_type': r.contract_type,
        'employment_channel': r.employment_channel,
        'work_province_city': r.work_province_city,
        'work_address': r.work_address,
        'company_nature': r.company_nature,
        'industry': r.industry,
        'position': r.position,
        'position_name': r.position_name,
        'monthly_salary': r.monthly_salary,
        'certificate_url': _signed_certificate_url(r.certificate_url),
        'satisfaction': r.satisfaction,
        'need_recommendation': r.need_recommendation,
        'feedback': r.feedback,
        'query_code': r.query_code,
    })
    return base


@router.get('/grad_emp_survey/admin/list')
def admin_list(
    keyword: Optional[str] = Query(None, description='学号 / 姓名 / 手机号 / 单位名 模糊'),
    destination: Optional[str] = Query(None),
    batch: Optional[str] = Query(None),
    has_certificate: Optional[int] = Query(None, description='1=有图, 0=无图'),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    user: dict = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    """admin 列表：分页 + 过滤；不在主表查询大字段以提速。"""
    try:
        q = db.query(ZsGraduateEmploymentSurvey)
        if batch:
            q = q.filter(ZsGraduateEmploymentSurvey.batch == batch)
        if destination:
            q = q.filter(ZsGraduateEmploymentSurvey.destination == destination)
        if has_certificate == 1:
            q = q.filter(ZsGraduateEmploymentSurvey.certificate_url.isnot(None),
                         ZsGraduateEmploymentSurvey.certificate_url != '')
        elif has_certificate == 0:
            q = q.filter(or_(ZsGraduateEmploymentSurvey.certificate_url.is_(None),
                             ZsGraduateEmploymentSurvey.certificate_url == ''))
        if keyword:
            kw = f'%{keyword.strip()}%'
            q = q.filter(or_(
                ZsGraduateEmploymentSurvey.student_no.like(kw),
                ZsGraduateEmploymentSurvey.student_name.like(kw),
                ZsGraduateEmploymentSurvey.phone.like(kw),
                ZsGraduateEmploymentSurvey.company_name.like(kw),
                ZsGraduateEmploymentSurvey.college_name.like(kw),
                ZsGraduateEmploymentSurvey.major_name.like(kw),
            ))
        total = q.count()
        rows = (q.order_by(ZsGraduateEmploymentSurvey.id.desc())
                 .offset((page - 1) * page_size)
                 .limit(page_size)
                 .all())
        # 批次字典：用于前端按批次过滤
        batches = [
            {'value': b, 'label': b}
            for (b,) in db.query(ZsGraduateEmploymentSurvey.batch)
                            .filter(ZsGraduateEmploymentSurvey.batch.isnot(None))
                            .distinct().order_by(ZsGraduateEmploymentSurvey.batch.desc()).all()
            if b
        ]
        return {
            'success': True,
            'data': {
                'list': [_record_to_brief_dict(r) for r in rows],
                'total': int(total),
                'page': page,
                'page_size': page_size,
                'batches': batches,
                'destinations': [
                    {'value': k, 'label': v} for k, v in _DESTINATION_LABELS.items()
                ],
            },
        }
    except Exception as e:
        logger.error(f'admin_list 失败: {e}')
        return {'success': False, 'msg': f'查询失败: {e}'}


@router.get('/grad_emp_survey/admin/detail/{record_id}')
def admin_detail(
    record_id: int,
    user: dict = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    """admin 详情：返回完整字段 + 当前可用签名的 certificate_url。"""
    try:
        r = db.query(ZsGraduateEmploymentSurvey).filter(
            ZsGraduateEmploymentSurvey.id == record_id
        ).first()
        if not r:
            return {'success': False, 'msg': '记录不存在'}
        return {'success': True, 'data': _record_to_detail_dict(r)}
    except Exception as e:
        logger.error(f'admin_detail 失败: {e}')
        return {'success': False, 'msg': f'查询失败: {e}'}


@router.get('/grad_emp_survey/admin/stats')
def admin_stats(
    user: dict = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    """admin 统计：总数 / 按去向分组 / 凭证上传率。"""
    try:
        total = db.query(func.count(ZsGraduateEmploymentSurvey.id)).scalar() or 0
        with_cert = (db.query(func.count(ZsGraduateEmploymentSurvey.id))
                       .filter(ZsGraduateEmploymentSurvey.certificate_url.isnot(None),
                               ZsGraduateEmploymentSurvey.certificate_url != '')
                       .scalar()) or 0
        by_dest = (db.query(ZsGraduateEmploymentSurvey.destination,
                            func.count(ZsGraduateEmploymentSurvey.id))
                     .group_by(ZsGraduateEmploymentSurvey.destination).all())
        return {
            'success': True,
            'data': {
                'total': int(total),
                'with_certificate': int(with_cert),
                'without_certificate': int(total) - int(with_cert),
                'by_destination': [
                    {
                        'value': d or '',
                        'label': _DESTINATION_LABELS.get(d or '', d or '未知'),
                        'count': int(c),
                    } for d, c in by_dest
                ],
            },
        }
    except Exception as e:
        logger.error(f'admin_stats 失败: {e}')
        return {'success': False, 'msg': f'查询失败: {e}'}

