from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_, func, and_
from models.models import Teacher, ZzXsQxj, ZzXs, ZzBj, ZzStCourse, ZzStCourseSelection
from init.dependencies import DatabaseDep
from common.auth import verify_token_and_get_payload, create_token, create_refresh_token
from datetime import datetime
from services.minio_service import check_photo_exists
import logging
import hashlib
import time

logger = logging.getLogger(__name__)


def _has_role(t_js_id, role_id: int) -> bool:
    """t_js_id 是逗号分隔的角色 id 字符串，判断是否包含指定角色。"""
    if t_js_id is None or t_js_id == '':
        return False
    try:
        return role_id in [int(x.strip()) for x in str(t_js_id).split(',') if x.strip()]
    except (ValueError, AttributeError):
        return False

router = APIRouter(prefix="/vocational_teacher", tags=["中职教师"])

# 直接导入photo_upload中的函数，保持签名一致
from controllers.photo_upload import get_signed_photo_url


def _resolve_leave_photo_url(db: Session, xh: str):
    """根据学号查询学生的照片 URL（中职类型）。找不到学生或没有照片时返回 None。

    之所以单独抽出：/leave/list、/leave/xsk_list、/leave/detail 三个接口都要给学生照片，
    各自重复一遍 ZzXs + get_signed_photo_url 逻辑容易写错。
    """
    if not xh:
        return None
    student = db.query(ZzXs).filter(ZzXs.xh == xh).first()
    if not student or student.headphoto != 1 or not student.sfzh:
        return None
    return get_signed_photo_url(student.sfzh, user_type="vocational")


def _format_leave_duration(qjkssj, qjjssj) -> dict:
    """计算请假时长，返回 {days, hours, text}。

    text 形如 "2天3小时" / "5小时30分" / "45分钟"，便于前端直接展示。
    """
    if not qjkssj or not qjjssj:
        return {'days': 0, 'hours': 0, 'minutes': 0, 'text': ''}
    try:
        delta = qjjssj - qjkssj
    except Exception:
        return {'days': 0, 'hours': 0, 'minutes': 0, 'text': ''}
    total_minutes = max(0, int(delta.total_seconds() // 60))
    days, rem_min = divmod(total_minutes, 60 * 24)
    hours, minutes = divmod(rem_min, 60)
    parts = []
    if days > 0:
        parts.append(f'{days}天')
    if hours > 0:
        parts.append(f'{hours}小时')
    if not parts:
        # 不满 1 小时，显示分钟
        if minutes > 0:
            parts.append(f'{minutes}分钟')
        else:
            parts.append('0分钟')
    return {
        'days': days,
        'hours': hours,
        'minutes': minutes,
        'text': ''.join(parts),
    }


class TeacherLoginRequest(BaseModel):
    username: str
    password: str


class QuickLoginRequest(BaseModel):
    code: str
    # 7 天手机号缓存：可选字段
    login_code: Optional[str] = None
    subject: Optional[str] = None


class OpenidLoginRequest(BaseModel):
    """openid 一键登录请求（wx.login code）"""
    code: str


def _bind_openid_to_teacher(db: Session, teacher: Teacher, openid: str) -> bool:
    """把 openid 绑定到教师记录（供后续 openid 一键登录使用）。

    规则（与学生端 /bind_openid 保持一致）：
      - 已有 openid 且非空 → 不覆盖（返回 False）
      - openid 已被别的教师占用 → 踢掉旧绑定，再写入
      - 同时维护 t_wx_openid_hash（隐私合规）

    Returns: 是否成功写入绑定。
    """
    if not openid:
        return False
    try:
        from utils.hash_util import hash_openid

        current = teacher.t_wx_openid
        if current and str(current).strip():
            # 已绑定：不覆盖，避免抢占他人绑定
            return False

        kicked = (
            db.query(Teacher)
            .filter(Teacher.t_wx_openid == openid, Teacher.t_id != teacher.t_id)
            .update(
                {"t_wx_openid": None, "t_wx_openid_hash": None},
                synchronize_session=False,
            )
        )
        if kicked:
            logger.warning(f"[bind_openid] 踢掉旧绑定 openid={openid} count={kicked}")

        teacher.t_wx_openid = openid
        teacher.t_wx_openid_hash = hash_openid(openid)
        db.commit()
        return True
    except Exception as e:
        logger.warning(f"[bind_openid] 绑定 openid 失败: {e}")
        db.rollback()
        return False



class LeaveApproveRequest(BaseModel):
    leave_id: int
    status: int  # 1-通过 2-拒绝


class PhotoStatusRequest(BaseModel):
    student_id: int
    headphoto: int  # 0-无照片 1-有照片


@router.post('/login')
async def teacher_login(
    request: TeacherLoginRequest,
    db: Session = DatabaseDep
):
    """中职教师登录"""
    try:
        teacher = db.query(Teacher).filter(
            Teacher.t_yhm == request.username
        ).first()
        
        if not teacher:
            return {
                'success': False,
                'msg': '用户名或密码错误',
                'data': None
            }
        
        # 验证密码（MD5加密）
        password_md5 = hashlib.md5(request.password.encode()).hexdigest()
        if teacher.t_mm != password_md5:
            return {
                'success': False,
                'msg': '用户名或密码错误',
                'data': None
            }
        
        # 查询教师所管理的班级
        class_info = db.query(ZzBj).filter(
            ZzBj.bzr_id == teacher.t_id
        ).first()
        
        # 判断是否有学生科角色（t_js_id包含8），以及心理咨询管理权限（t_js_id包含26）
        is_xsk = _has_role(teacher.t_js_id, 8)
        is_counsel = _has_role(teacher.t_js_id, 26)
        
        # 生成token
        payload = {
            't_id': teacher.t_id,
            't_yhm': teacher.t_yhm,
            't_xm': teacher.t_xm,
            't_sfzh': teacher.t_sfzh,
            'is_vocational_teacher': True,
            'bj_id': class_info.id if class_info else None,
            'is_xsk': is_xsk,
            'is_counsel': is_counsel
        }
        token = create_token({**payload})
        refresh_token = create_refresh_token(payload)
        
        return {
            'success': True,
            'msg': '登录成功',
            'data': {
                't_id': teacher.t_id,
                't_yhm': teacher.t_yhm,
                't_xm': teacher.t_xm,
                'token': token,
                'refresh_token': refresh_token,
                'is_vocational_teacher': True,
                'bj_id': class_info.id if class_info else None,
                'class_name': class_info.mc if class_info else None,
                'is_xsk': is_xsk,
                'is_counsel': is_counsel
            }
        }
    except Exception as e:
        logger.error(f"教师登录失败: {str(e)}")
        return {
            'success': False,
            'msg': f'登录失败: {str(e)}',
            'data': None
        }


@router.post('/quick_login')
async def quick_login(
    request: QuickLoginRequest,
    db: Session = DatabaseDep
):
    """中职教师快捷登录（通过手机号验证）"""
    try:
        from utils.wx_utils import WxUtils
        
        # 获取手机号
        phone_result = WxUtils.get_phone_number(request.code)
        
        if not phone_result:
            return {
                'success': True,
                'msg': '获取手机号失败',
                'data': {'authorized': False, 'msg': '获取手机号失败'}
            }
        
        phone_info = phone_result.get('phone_info', {})
        phone_number = phone_info.get('phoneNumber') or phone_info.get('purePhoneNumber')
        
        if not phone_number:
            return {
                'success': True,
                'msg': '获取手机号失败',
                'data': {'authorized': False, 'msg': '获取手机号失败'}
            }
        
        # 查询教师表，验证手机号是否存在
        teacher = db.query(Teacher).filter(Teacher.t_dh == phone_number).first()
        
        if not teacher:
            return {
                'success': True,
                'msg': '您没有访问权限',
                'data': {'authorized': False, 'msg': '该手机号未注册为教师'}
            }
        
        # 查询教师所管理的所有班级
        class_list = db.query(ZzBj).filter(ZzBj.bzr_id == teacher.t_id).all()
        bj_ids = [c.id for c in class_list]
        class_names = [c.mc for c in class_list]
        
        # 判断是否有学生科角色（t_js_id包含8），以及心理咨询管理权限（t_js_id包含26）
        is_xsk = _has_role(teacher.t_js_id, 8)
        is_counsel = _has_role(teacher.t_js_id, 26)
        
        # 生成token
        payload = {
            't_id': teacher.t_id,
            't_yhm': teacher.t_yhm,
            't_xm': teacher.t_xm,
            't_sfzh': teacher.t_sfzh,
            'is_vocational_teacher': True,
            'bj_ids': bj_ids,
            'is_xsk': is_xsk,
            'is_counsel': is_counsel
        }
        token = create_token({**payload})
        refresh_token = create_refresh_token(payload)

        # 归一化手机号 + 写 7 天缓存
        from common import phone_cache as _phone_cache
        pure_phone = _phone_cache.normalize_phone(phone_number)
        masked_phone = _phone_cache.mask_phone(pure_phone)
        cache_written = False
        openid_bound = False
        try:
            if request.login_code:
                openid = _phone_cache.resolve_openid_by_login_code(request.login_code)
                if openid:
                    # 首次手机号登录：把 openid 绑到该教师，供后续 openid 一键登录使用
                    openid_bound = _bind_openid_to_teacher(db, teacher, openid)
                    if request.subject:
                        cache_written = _phone_cache.write_phone_cache(
                            openid=openid,
                            pure_phone=pure_phone,
                            role='self',
                            subject=request.subject,
                            extra={
                                'masked_phone': masked_phone,
                                'sfzh': getattr(teacher, 't_sfzh', None) or '',
                                'xm': teacher.t_xm,
                                't_id': teacher.t_id,
                            },
                        )
        except Exception as _e:
            logger.warning(f"[phone_cache] vocational_teacher.quick_login 写缓存失败: {_e}")

        return {
            'success': True,
            'msg': '登录成功',
            'data': {
                'authorized': True,
                'token': token,
                'refresh_token': refresh_token,
                'masked_phone': masked_phone,
                'cache_written': cache_written,
                'openid_bound': openid_bound,
                'userInfo': {
                    't_id': teacher.t_id,
                    't_yhm': teacher.t_yhm,
                    't_xm': teacher.t_xm,
                    'bj_ids': bj_ids,
                    'class_names': class_names,
                    'class_name': '、'.join(class_names) if class_names else '未分配班级',
                    'is_xsk': is_xsk,
                    'is_counsel': is_counsel
                }
            }
        }
    except Exception as e:
        logger.error(f"快捷登录失败: {str(e)}")
        return {
            'success': False,
            'msg': f'登录失败: {str(e)}',
            'data': None
        }


@router.post('/quick_login_openid')
async def quick_login_openid(
    request: OpenidLoginRequest,
    db: Session = DatabaseDep
):
    """中职教师 openid 一键登录。

    前提：用户此前至少通过一次手机号快捷登录，后端已把 openid 绑定到该教师。
    """
    try:
        from utils.wx_utils import WxUtils

        code = request.code
        if not code:
            return {
                'success': True,
                'msg': '缺少关键参数',
                'data': {'authorized': False, 'msg': '缺少关键参数'}
            }

        wx_result = WxUtils.get_openid_and_session_key(code)
        if not wx_result or not wx_result.get('openid'):
            return {
                'success': True,
                'msg': '登录失败，您提供的code错误',
                'data': {'authorized': False, 'msg': '登录失败，您提供的code错误'}
            }
        openid = wx_result.get('openid')

        # 查询教师：同一 openid 可能有多条，取 t_id 最大（最新绑定）
        teacher = (
            db.query(Teacher)
            .filter(Teacher.t_wx_openid == openid)
            .order_by(Teacher.t_id.desc())
            .first()
        )
        if not teacher:
            return {
                'success': True,
                'msg': '当前微信还未绑定教师信息，请先使用「手机号快捷登录」完成一次登录',
                'data': {
                    'authorized': False,
                    'msg': '当前微信还未绑定教师信息，请先使用「手机号快捷登录」完成一次登录'
                }
            }

        # 查询教师所管理的所有班级
        class_list = db.query(ZzBj).filter(ZzBj.bzr_id == teacher.t_id).all()
        bj_ids = [c.id for c in class_list]
        class_names = [c.mc for c in class_list]

        # 判断是否有学生科角色（t_js_id包含8），以及心理咨询管理权限（t_js_id包含26）
        is_xsk = _has_role(teacher.t_js_id, 8)
        is_counsel = _has_role(teacher.t_js_id, 26)

        payload = {
            't_id': teacher.t_id,
            't_yhm': teacher.t_yhm,
            't_xm': teacher.t_xm,
            't_sfzh': teacher.t_sfzh,
            'is_vocational_teacher': True,
            'bj_ids': bj_ids,
            'is_xsk': is_xsk,
            'is_counsel': is_counsel
        }
        token = create_token({**payload})
        refresh_token = create_refresh_token(payload)

        return {
            'success': True,
            'msg': '登录成功',
            'data': {
                'authorized': True,
                'token': token,
                'refresh_token': refresh_token,
                'userInfo': {
                    't_id': teacher.t_id,
                    't_yhm': teacher.t_yhm,
                    't_xm': teacher.t_xm,
                    'bj_ids': bj_ids,
                    'class_names': class_names,
                    'class_name': '、'.join(class_names) if class_names else '未分配班级',
                    'is_xsk': is_xsk,
                    'is_counsel': is_counsel
                }
            }
        }
    except Exception as e:
        logger.error(f"openid 登录失败: {str(e)}")
        return {
            'success': False,
            'msg': f'登录失败: {str(e)}',
            'data': None
        }


@router.get('/classes')
async def get_classes(
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """获取教师担任班主任的班级列表"""
    try:
        t_id = current_user.get('t_id')
        
        # 只查询该教师担任班主任的班级
        class_list = db.query(ZzBj).filter(
            ZzBj.bzr_id == t_id,
            or_(ZzBj.isblock == 0, ZzBj.isblock == None)
        ).order_by(ZzBj.nd.desc(), ZzBj.mc).all()
        
        classes = []
        for c in class_list:
            classes.append({
                'id': c.id,
                'name': c.mc
            })
        
        return {
            'success': True,
            'msg': '获取班级列表成功',
            'data': classes
        }
    except Exception as e:
        logger.error(f"获取班级列表失败: {str(e)}")
        return {
            'success': False,
            'msg': f'获取班级列表失败: {str(e)}',
            'data': None
        }


@router.get('/stats')
async def get_stats(
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """获取教师统计数据"""
    try:
        t_id = current_user.get('t_id')
        bj_ids = current_user.get('bj_ids', [])
        # 顺带返回最新权限标记：老缓存里可能没有 is_counsel，这里实时查库兜底
        is_counsel = bool(current_user.get('is_counsel', False))
        if t_id and not is_counsel:
            try:
                _t = db.query(Teacher).filter(Teacher.t_id == t_id).first()
                is_counsel = _has_role(getattr(_t, 't_js_id', None), 26)
            except Exception:
                pass
        
        # 待审批请假数量（班主任审批）
        pending_leave_count = 0
        if bj_ids:
            pending_leave_count = db.query(ZzXsQxj).filter(
                ZzXsQxj.bj_id.in_(bj_ids),
                ZzXsQxj.bzr_zt == 0
            ).count()
        
        # 无照片学生数量
        pending_photo_count = 0
        if bj_ids:
            pending_photo_count = db.query(ZzXs).filter(
                ZzXs.bj_id.in_(bj_ids),
                or_(ZzXs.headphoto == 0, ZzXs.headphoto == None)
            ).count()
        
        return {
            'success': True,
            'msg': '获取统计数据成功',
            'data': {
                'pending_leave_count': pending_leave_count,
                'pending_photo_count': pending_photo_count,
                'is_counsel': is_counsel
            }
        }
    except Exception as e:
        logger.error(f"获取统计数据失败: {str(e)}")
        return {
            'success': False,
            'msg': f'获取统计数据失败: {str(e)}',
            'data': None
        }


@router.get('/leave/list')
async def get_leave_list(
    status: str = 'pending',
    page: int = 1,
    page_size: int = 10,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """获取请假列表（只显示班主任班级，分页）"""
    try:
        t_id = current_user.get('t_id')
        bj_ids = current_user.get('bj_ids', [])
        
        if not bj_ids:
            return {
                'success': True,
                'msg': '您还未担任班主任',
                'data': { 'list': [], 'total': 0, 'page': page, 'page_size': page_size }
            }
        
        query = db.query(ZzXsQxj).filter(ZzXsQxj.bj_id.in_(bj_ids))
        
        if status == 'pending':
            query = query.filter(ZzXsQxj.bzr_zt == 0)
        elif status == 'approved':
            query = query.filter(ZzXsQxj.bzr_zt == 1)
        elif status == 'rejected':
            query = query.filter(ZzXsQxj.bzr_zt == 2)
        
        total = query.count()
        leaves = query.order_by(ZzXsQxj.qjsqsj.desc()).offset((page - 1) * page_size).limit(page_size).all()

        leave_list = []
        for leave in leaves:
            # 班级名称（直接用 leave.bj_id 查表，避免一次额外往返）
            class_name = ''
            if leave.bj_id:
                bj = db.query(ZzBj).filter(ZzBj.id == leave.bj_id).first()
                if bj:
                    class_name = bj.mc
            duration = _format_leave_duration(leave.qjkssj, leave.qjjssj)

            leave_list.append({
                'id': leave.id,
                'xm': leave.xm,
                'xh': leave.xh,
                'qjlb': leave.qjlb,
                'qjsy': leave.qjsy,
                'qjsqsj': leave.qjsqsj.strftime('%Y-%m-%d %H:%M') if leave.qjsqsj else None,
                'qjkssj': leave.qjkssj.strftime('%Y-%m-%d %H:%M') if leave.qjkssj else None,
                'qjjssj': leave.qjjssj.strftime('%Y-%m-%d %H:%M') if leave.qjjssj else None,
                'xslxxl': leave.xslxxl,
                'xslxjtgj': leave.xslxjtgj,
                'bzr_zt': leave.bzr_zt,
                'xsk_zt': leave.xsk_zt,
                'xj_zt': leave.xj_zt,
                # 增强字段（前端新版卡片要用到）
                'class_name': class_name,
                'photo_url': _resolve_leave_photo_url(db, leave.xh),
                'duration_text': duration['text'],
                'duration_days': duration['days'],
                'duration_hours': duration['hours'],
            })
        
        return {
            'success': True,
            'msg': '获取请假列表成功',
            'data': { 'list': leave_list, 'total': total, 'page': page, 'page_size': page_size }
        }
    except Exception as e:
        logger.error(f"获取请假列表失败: {str(e)}")
        return {
            'success': False,
            'msg': f'获取请假列表失败: {str(e)}',
            'data': None
        }


@router.get('/leave/detail')
async def get_leave_detail(
    id: int,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """获取请假详情"""
    try:
        t_id = current_user.get('t_id')
        bj_ids = current_user.get('bj_ids', [])
        is_xsk = current_user.get('is_xsk', False)
        
        # 学生科角色可以查看所有班主任已审批的记录，班主任只能查看自己班级的
        if is_xsk:
            leave = db.query(ZzXsQxj).filter(ZzXsQxj.id == id).first()
        else:
            leave = db.query(ZzXsQxj).filter(
                ZzXsQxj.id == id,
                ZzXsQxj.bj_id.in_(bj_ids) if bj_ids else False
            ).first()
        
        if not leave:
            return {
                'success': False,
                'msg': '请假记录不存在或无权限查看',
                'data': None
            }
        
        # 查询班级名称
        class_name = ''
        if leave.bj_id:
            bj = db.query(ZzBj).filter(ZzBj.id == leave.bj_id).first()
            if bj:
                class_name = bj.mc

        duration = _format_leave_duration(leave.qjkssj, leave.qjjssj)

        return {
            'success': True,
            'msg': '获取请假详情成功',
            'data': {
                'id': leave.id,
                'xm': leave.xm,
                'xh': leave.xh,
                'qjlb': leave.qjlb,
                'qjsy': leave.qjsy,
                'qjsqsj': leave.qjsqsj.strftime('%Y-%m-%d %H:%M') if leave.qjsqsj else None,
                'qjkssj': leave.qjkssj.strftime('%Y-%m-%d %H:%M') if leave.qjkssj else None,
                'qjjssj': leave.qjjssj.strftime('%Y-%m-%d %H:%M') if leave.qjjssj else None,
                'xslxxl': leave.xslxxl,
                'xslxjtgj': leave.xslxjtgj,
                'bzr_zt': leave.bzr_zt,
                'xsk_zt': leave.xsk_zt,
                'xj_zt': leave.xj_zt,
                'sp_bzr_tid': leave.sp_bzr_tid,
                'sp_bzr_xm': leave.sp_bzr_xm,
                'sp_xsk_tid': leave.sp_xsk_tid,
                'sp_xsk_xm': leave.sp_xsk_xm,
                'class_name': class_name,
                # 增强字段
                'photo_url': _resolve_leave_photo_url(db, leave.xh),
                'duration_text': duration['text'],
                'duration_days': duration['days'],
                'duration_hours': duration['hours'],
            }
        }
    except Exception as e:
        logger.error(f"获取请假详情失败: {str(e)}")
        return {
            'success': False,
            'msg': f'获取请假详情失败: {str(e)}',
            'data': None
        }


@router.post('/leave/approve')
async def approve_leave(
    request: LeaveApproveRequest,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """审批请假（班主任）"""
    try:
        t_id = current_user.get('t_id')
        t_xm = current_user.get('t_xm')
        bj_ids = current_user.get('bj_ids', [])
        
        # 只能审批自己班级的请假记录
        leave = db.query(ZzXsQxj).filter(
            ZzXsQxj.id == request.leave_id,
            ZzXsQxj.bj_id.in_(bj_ids) if bj_ids else False
        ).first()
        
        if not leave:
            return {
                'success': False,
                'msg': '请假记录不存在或无权限审批',
                'data': None
            }
        
        if leave.bzr_zt != 0:
            return {
                'success': False,
                'msg': '该请假已审批过',
                'data': None
            }
        
        leave.bzr_zt = request.status
        leave.sp_bzr_tid = t_id
        leave.sp_bzr_xm = t_xm
        leave.sp_bzr_sj = datetime.now()
        
        # 拒绝时设置xj_zt=1，否则学生无法继续下次请假
        if request.status == 2:
            leave.xj_zt = 1
        
        # 班主任审批通过且请假时长 <= 24 小时，自动填写学生科审批信息
        if request.status == 1 and leave.qjkssj and leave.qjjssj:
            duration_hours = (leave.qjjssj - leave.qjkssj).total_seconds() / 3600
            if duration_hours <= 24:
                leave.sp_xsk_tid = t_id
                leave.sp_xsk_xm = f"{t_xm}(自动审批)"
                leave.xsk_zt = 1
                leave.sp_xsk_sj = datetime.now()

        # 主流程：数据库审批状态提交（与海康下发、短信发送解耦，无论后续如何都应生效）
        db.commit()

        # 辅助流程：向海康平台下发门禁权限 + 发送短信（仅作为附加信息，不影响审批结果）
        aux_msgs = []
        if request.status == 1 and leave.qjkssj and leave.qjjssj:
            duration_hours = (leave.qjjssj - leave.qjkssj).total_seconds() / 3600
            if duration_hours <= 24:
                # 1、向海康平台下发门禁权限（失败不影响审批成功状态）
                try:
                    from services.hikvision_sync_service import get_hikvision_sync_service
                    sync_service = get_hikvision_sync_service()
                    if not sync_service:
                        logger.warning(f"门禁服务未初始化，无法为学生 {leave.xm}({leave.xh}) 下发门禁权限")
                        aux_msgs.append('门禁权限下发失败: 门禁服务未初始化')
                    else:
                        access_result = await sync_service.grant_access_permission(leave.xh)
                        if not isinstance(access_result, dict):
                            logger.warning(f"为学生 {leave.xm}({leave.xh}) 下发门禁权限返回异常: {access_result}")
                            aux_msgs.append('门禁权限下发失败: 门禁服务返回异常')
                        elif not access_result.get("success"):
                            err_msg = access_result.get('message') or access_result.get('msg') or '未知错误'
                            logger.warning(f"为学生 {leave.xm}({leave.xh}) 下发门禁权限失败: {err_msg}")
                            leave.hik_task_id = f"失败: {err_msg}"
                            aux_msgs.append(f'门禁权限下发失败: {err_msg}')
                        else:
                            leave.hik_task_id = access_result.get('hik_task_id') or ''
                            logger.info(f"为学生 {leave.xm}({leave.xh}) 下发门禁权限成功, task_id={leave.hik_task_id}")
                            aux_msgs.append('门禁权限下发成功')
                except Exception as hik_error:
                    logger.error(f"下发门禁权限异常: {str(hik_error)}")
                    aux_msgs.append(f'门禁权限下发异常: {str(hik_error)}')

                # 2、向学生发送短信提醒（失败不影响审批成功状态）
                try:
                    student = db.query(ZzXs).filter(ZzXs.xh == leave.xh).first()
                    if student and student.xsdh:
                        from utils.sms_tencent import SMSTencentTool
                        sms_tool = SMSTencentTool()
                        sms_result = sms_tool.send_by_scenario(
                            scenario='student_leave',
                            mobile=student.xsdh,
                            values={
                                'name': leave.xm,
                                'apply_type': leave.qjlb,
                                'status': '已通过',
                            },
                            xs_id=leave.xh, xs_xm=leave.xm,
                        )
                        if sms_result.get('success'):
                            logger.info(f"请假审批通过短信发送成功: 学生={leave.xm}, 手机号={student.xsdh}")
                            aux_msgs.append('已短信通知学生')
                        else:
                            logger.warning(f"请假审批通过短信发送失败: {sms_result.get('msg')}")
                            aux_msgs.append(f'短信发送失败: {sms_result.get("msg")}')
                    else:
                        logger.warning(f"学生手机号不存在，无法发送短信: 学号={leave.xh}")
                        aux_msgs.append('学生无手机号，未发送短信')
                except Exception as sms_error:
                    logger.error(f"发送审批通过短信异常: {str(sms_error)}")
                    aux_msgs.append(f'短信发送异常: {str(sms_error)}')

        msg_suffix = ('，' + '，'.join(aux_msgs)) if aux_msgs else ''
        return {
            'success': True,
            'msg': f'审批成功{msg_suffix}',
            'data': None
        }
    except Exception as e:
        db.rollback()
        logger.error(f"审批请假失败: {str(e)}")
        return {
            'success': False,
            'msg': f'审批失败: {str(e)}',
            'data': None
        }


class TeacherCancelLeaveRequest(BaseModel):
    leave_id: int


@router.post('/leave/teacher_cancel')
async def teacher_cancel_leave(
    request: TeacherCancelLeaveRequest,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """班主任代销假（不检查门禁记录）"""
    try:
        t_id = current_user.get('t_id')
        bj_ids = current_user.get('bj_ids', [])

        leave = db.query(ZzXsQxj).filter(
            ZzXsQxj.id == request.leave_id,
            ZzXsQxj.bj_id.in_(bj_ids) if bj_ids else False
        ).first()

        if not leave:
            return {
                'success': False,
                'msg': '请假记录不存在或无权限操作',
                'data': None
            }

        if leave.xj_zt == 1:
            return {
                'success': False,
                'msg': '该请假记录已销假',
                'data': None
            }

        if leave.bzr_zt != 1 or leave.xsk_zt != 1:
            return {
                'success': False,
                'msg': '请假尚未全部审批通过，无法销假',
                'data': None
            }

        leave.xj_zt = 1
        leave.xjsj = datetime.now()
        db.commit()

        return {
            'success': True,
            'msg': '代销假成功',
            'data': None
        }
    except Exception as e:
        db.rollback()
        logger.error(f"班主任代销假失败: {str(e)}")
        return {
            'success': False,
            'msg': f'代销假失败: {str(e)}',
            'data': None
        }


@router.get('/leave/xsk_list')
async def get_xsk_leave_list(
    status: str = 'pending',
    page: int = 1,
    page_size: int = 10,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """获取学生科待审批请假列表（班主任已审批通过，学生科未审批，分页）"""
    try:
        is_xsk = current_user.get('is_xsk', False)
        if not is_xsk:
            return {
                'success': False,
                'msg': '您没有学生科审批权限',
                'data': { 'list': [], 'total': 0, 'page': page, 'page_size': page_size }
            }

        query = db.query(ZzXsQxj).filter(ZzXsQxj.bzr_zt == 1)

        if status == 'pending':
            query = query.filter(ZzXsQxj.xsk_zt == 0)
        elif status == 'approved':
            query = query.filter(ZzXsQxj.xsk_zt == 1)
        elif status == 'rejected':
            query = query.filter(ZzXsQxj.xsk_zt == 2)

        total = query.count()
        leaves = query.order_by(ZzXsQxj.qjsqsj.desc()).offset((page - 1) * page_size).limit(page_size).all()

        leave_list = []
        for leave in leaves:
            class_name = ''
            if leave.bj_id:
                bj = db.query(ZzBj).filter(ZzBj.id == leave.bj_id).first()
                if bj:
                    class_name = bj.mc
            duration = _format_leave_duration(leave.qjkssj, leave.qjjssj)

            leave_list.append({
                'id': leave.id,
                'xm': leave.xm,
                'xh': leave.xh,
                'qjlb': leave.qjlb,
                'qjsy': leave.qjsy,
                'qjsqsj': leave.qjsqsj.strftime('%Y-%m-%d %H:%M') if leave.qjsqsj else None,
                'qjkssj': leave.qjkssj.strftime('%Y-%m-%d %H:%M') if leave.qjkssj else None,
                'qjjssj': leave.qjjssj.strftime('%Y-%m-%d %H:%M') if leave.qjjssj else None,
                'xslxxl': leave.xslxxl,
                'xslxjtgj': leave.xslxjtgj,
                'bzr_zt': leave.bzr_zt,
                'xsk_zt': leave.xsk_zt,
                'xj_zt': leave.xj_zt,
                'sp_bzr_xm': leave.sp_bzr_xm,
                'class_name': class_name,
                # 增强字段
                'photo_url': _resolve_leave_photo_url(db, leave.xh),
                'duration_text': duration['text'],
                'duration_days': duration['days'],
                'duration_hours': duration['hours'],
            })

        return {
            'success': True,
            'msg': '获取学生科请假列表成功',
            'data': { 'list': leave_list, 'total': total, 'page': page, 'page_size': page_size }
        }
    except Exception as e:
        logger.error(f"获取学生科请假列表失败: {str(e)}")
        return {
            'success': False,
            'msg': f'获取学生科请假列表失败: {str(e)}',
            'data': None
        }


@router.post('/leave/xsk_approve')
async def xsk_approve_leave(
    request: LeaveApproveRequest,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """学生科审批请假"""
    try:
        is_xsk = current_user.get('is_xsk', False)
        if not is_xsk:
            return {
                'success': False,
                'msg': '您没有学生科审批权限',
                'data': None
            }

        t_id = current_user.get('t_id')
        t_xm = current_user.get('t_xm')

        leave = db.query(ZzXsQxj).filter(ZzXsQxj.id == request.leave_id).first()

        if not leave:
            return {
                'success': False,
                'msg': '请假记录不存在',
                'data': None
            }

        if leave.bzr_zt != 1:
            return {
                'success': False,
                'msg': '班主任尚未审批通过，无法进行学生科审批',
                'data': None
            }

        if leave.xsk_zt != 0:
            return {
                'success': False,
                'msg': '学生科已审批过',
                'data': None
            }

        leave.sp_xsk_tid = t_id
        leave.sp_xsk_xm = t_xm
        leave.xsk_zt = request.status
        leave.sp_xsk_sj = datetime.now()

        # 拒绝时设置 xj_zt=1，否则学生无法继续下次请假
        if request.status == 2:
            leave.xj_zt = 1

        # 主流程：数据库审批状态提交（与海康下发、短信发送解耦，无论后续如何都应生效）
        db.commit()

        # 辅助流程：向海康平台下发门禁权限 + 发送短信（仅作为附加信息，不影响审批结果）
        aux_msgs = []
        if request.status == 1:
            # 1、向海康平台下发门禁权限（失败不影响审批成功状态）
            try:
                from services.hikvision_sync_service import get_hikvision_sync_service
                sync_service = get_hikvision_sync_service()
                if not sync_service:
                    logger.warning(f"门禁服务未初始化，无法为学生 {leave.xm}({leave.xh}) 下发门禁权限")
                    aux_msgs.append('门禁权限下发失败: 门禁服务未初始化')
                else:
                    access_result = await sync_service.grant_access_permission(leave.xh)
                    if not isinstance(access_result, dict):
                        logger.warning(f"为学生 {leave.xm}({leave.xh}) 下发门禁权限返回异常: {access_result}")
                        aux_msgs.append('门禁权限下发失败: 门禁服务返回异常')
                    elif not access_result.get("success"):
                        err_msg = access_result.get('message') or access_result.get('msg') or '未知错误'
                        logger.warning(f"为学生 {leave.xm}({leave.xh}) 下发门禁权限失败: {err_msg}")
                        leave.hik_task_id = f"失败: {err_msg}"
                        aux_msgs.append(f'门禁权限下发失败: {err_msg}')
                    else:
                        leave.hik_task_id = access_result.get('hik_task_id') or ''
                        logger.info(f"为学生 {leave.xm}({leave.xh}) 下发门禁权限成功, task_id={leave.hik_task_id}")
                        aux_msgs.append('门禁权限下发成功')
            except Exception as hik_error:
                logger.error(f"下发门禁权限异常: {str(hik_error)}")
                aux_msgs.append(f'门禁权限下发异常: {str(hik_error)}')

            # 2、向学生发送短信提醒（失败不影响审批成功状态）
            try:
                student = db.query(ZzXs).filter(ZzXs.xh == leave.xh).first()
                if student and student.xsdh:
                    from utils.sms_tencent import SMSTencentTool
                    sms_tool = SMSTencentTool()
                    sms_result = sms_tool.send_by_scenario(
                        scenario='student_leave',
                        mobile=student.xsdh,
                        values={
                            'name': leave.xm,
                            'apply_type': leave.qjlb,
                            'status': '已通过',
                        },
                        xs_id=leave.xh, xs_xm=leave.xm,
                    )
                    if sms_result.get('success'):
                        logger.info(f"学生科审批通过短信发送成功: 学生={leave.xm}, 手机号={student.xsdh}")
                        aux_msgs.append('已短信通知学生')
                    else:
                        logger.warning(f"学生科审批通过短信发送失败: {sms_result.get('msg')}")
                        aux_msgs.append(f'短信发送失败: {sms_result.get("msg")}')
                else:
                    logger.warning(f"学生手机号不存在，无法发送短信: 学号={leave.xh}")
                    aux_msgs.append('学生无手机号，未发送短信')
            except Exception as sms_error:
                logger.error(f"发送审批通过短信异常: {str(sms_error)}")
                aux_msgs.append(f'短信发送异常: {str(sms_error)}')

        msg_suffix = ('，' + '，'.join(aux_msgs)) if aux_msgs else ''
        return {
            'success': True,
            'msg': f'学生科审批成功{msg_suffix}',
            'data': {'msg':f'学生科审批成功{msg_suffix}'}
        }
    except Exception as e:
        db.rollback()
        logger.error(f"学生科审批请假失败: {str(e)}")
        return {
            'success': False,
            'msg': f'学生科审批失败: {str(e)}',
            'data': None
        }


@router.get('/photo/list')
async def get_photo_list(
    filter: str = 'all',
    bj_id: int = None,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """获取学生照片列表（只显示班主任班级）"""
    try:
        t_id = current_user.get('t_id')
        bj_ids = current_user.get('bj_ids', [])
        
        if not bj_id:
            return {
                'success': True,
                'msg': '请选择班级',
                'data': {
                    'students': [],
                    'xjzt_map': {}
                }
            }
        
        # 验证是否是自己的班级
        if bj_id not in bj_ids:
            return {
                'success': False,
                'msg': '无权限查看该班级',
                'data': {
                    'students': [],
                    'xjzt_map': {}
                }
            }
        
        # 按指定班级筛选
        query = db.query(ZzXs).filter(ZzXs.bj_id == bj_id)
        
        if filter == 'has':
            query = query.filter(ZzXs.headphoto == 1)
        elif filter == 'none':
            query = query.filter(or_(ZzXs.headphoto == 0, ZzXs.headphoto == None))
        
        # 按学籍状态排序：数字小的在前（1-在籍在前）
        # SQL Server 使用 CASE 语句处理 NULL 值
        from sqlalchemy import case
        students = query.order_by(
            case(
                (ZzXs.xjzt == None, 999),  # NULL 值排最后
                else_=ZzXs.xjzt
            ).asc(),  # 改为升序
            ZzXs.xm  # 同状态按姓名排序
        ).all()
        
        # 查询班级信息
        class_info = db.query(ZzBj).filter(ZzBj.id == bj_id).first()
        class_name = class_info.mc if class_info else ''
        
        # 查询所有学籍状态字典，构建map
        from models.models import ZzXsXjzt
        xjzt_map = {}
        xjzt_list = db.query(ZzXsXjzt).all()
        for xjzt in xjzt_list:
            xjzt_map[xjzt.id] = xjzt.mc

        student_list = []
        for student in students:
            has_photo = student.headphoto == 1
            photo_url = None
            if has_photo and student.sfzh:
                photo_url = get_signed_photo_url(student.sfzh, user_type="vocational")

            student_list.append({
                'id': student.id,
                'xs_xm': student.xm,
                'xs_xh': student.xh,
                'sfzh': student.sfzh,
                'headphoto': student.headphoto or 0,
                'class_name': class_name,
                'photo_url': photo_url,
                'xjzt': student.xjzt  # 只返回状态ID
            })
        
        return {
            'success': True,
            'msg': '获取学生列表成功',
            'data': {
                'students': student_list,
                'xjzt_map': xjzt_map  # 返回状态字典
            }
        }
    except Exception as e:
        logger.error(f"获取学生列表失败: {str(e)}")
        return {
            'success': False,
            'msg': f'获取学生列表失败: {str(e)}',
            'data': {
                'students': [],
                'xjzt_map': {}
            }
        }


@router.get('/xjzt/list')
async def get_xjzt_list(
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """获取学籍状态列表"""
    try:
        from models.models import ZzXsXjzt
        
        # 查询所有状态（zt字段用于控制是否启用，0或NULL表示启用）
        xjzt_list = db.query(ZzXsXjzt).filter(
            or_(ZzXsXjzt.zt == 0, ZzXsXjzt.zt == None)
        ).order_by(ZzXsXjzt.id).all()
        
        result = []
        for xjzt in xjzt_list:
            result.append({
                'id': xjzt.id,
                'name': xjzt.mc
            })
        
        return {
            'success': True,
            'msg': '获取学籍状态列表成功',
            'data': result
        }
    except Exception as e:
        logger.error(f"获取学籍状态列表失败: {str(e)}")
        return {
            'success': False,
            'msg': f'获取学籍状态列表失败: {str(e)}',
            'data': None
        }


@router.post('/photo/update_status')
async def update_photo_status(
    request: PhotoStatusRequest,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """更新学生照片状态"""
    try:
        student = db.query(ZzXs).filter(ZzXs.id == request.student_id).first()
        
        if not student:
            return {
                'success': False,
                'msg': '学生不存在',
                'data': None
            }
        
        student.headphoto = request.headphoto
        db.commit()
        
        return {
            'success': True,
            'msg': '更新成功',
            'data': None
        }
    except Exception as e:
        db.rollback()
        logger.error(f"更新照片状态失败: {str(e)}")
        return {
            'success': False,
            'msg': f'更新失败: {str(e)}',
            'data': None
        }



# ========== 社团课选课统计 ==========

@router.get('/club_course_stats')
async def get_club_course_stats(
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """获取社团课选课统计（按课程和按班级）"""
    try:
        # 按课程统计选课人数
        courses = db.query(ZzStCourse).filter(ZzStCourse.status == 1).order_by(ZzStCourse.category, ZzStCourse.course_name).all()

        course_stats = []
        for c in courses:
            course_stats.append({
                'id': c.id,
                'course_name': c.course_name,
                'course_code': c.course_code,
                'category': c.category,
                'classroom': c.classroom,
                'max_students': c.max_students,
                'current_students': c.current_students or 0,
            })

        # 按班级统计选课人数
        # 查询所有有效选课记录，关联学生和班级
        class_rows = db.query(
            ZzBj.id,
            ZzBj.mc,
            func.count(ZzStCourseSelection.id).label('selected_count')
        ).join(
            ZzXs, ZzXs.bj_id == ZzBj.id
        ).join(
            ZzStCourseSelection,
            ZzStCourseSelection.student_id == ZzXs.id
        ).filter(
            or_(ZzBj.isblock == 0, ZzBj.isblock == None)
        ).group_by(ZzBj.id, ZzBj.mc).order_by(ZzBj.mc).all()

        # 查询各班级总人数
        class_total_rows = db.query(
            ZzBj.id,
            ZzBj.mc,
            func.count(ZzXs.id).label('total_students')
        ).join(
            ZzXs, ZzXs.bj_id == ZzBj.id
        ).filter(
            or_(ZzBj.isblock == 0, ZzBj.isblock == None),
            ZzXs.xjzt == 1
        ).group_by(ZzBj.id, ZzBj.mc).order_by(ZzBj.mc).all()

        total_map = {r.id: {'mc': r.mc, 'total': r.total_students} for r in class_total_rows}
        selected_map = {r.id: r.selected_count for r in class_rows}

        class_stats = []
        for bj_id, info in total_map.items():
            selected = selected_map.get(bj_id, 0)
            class_stats.append({
                'id': bj_id,
                'class_name': info['mc'],
                'total_students': info['total'],
                'selected_count': selected,
                'unselected_count': info['total'] - selected,
            })

        # 总计
        total_courses = len(course_stats)
        total_selected = sum(c['current_students'] for c in course_stats)

        return {
            'success': True,
            'msg': '获取成功',
            'data': {
                'course_stats': course_stats,
                'class_stats': class_stats,
                'total_courses': total_courses,
                'total_selected': total_selected,
            }
        }
    except Exception as e:
        logger.error(f"获取社团课选课统计失败: {str(e)}")
        return {'success': False, 'msg': f'获取失败: {str(e)}', 'data': None}


@router.get('/club_course_detail')
async def get_club_course_detail(
    course_id: int = None,
    bj_id: int = None,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """获取某课程的选课学生列表 或 某班级的选课详情"""
    try:
        if course_id:
            # 查询选了该课程的学生
            rows = db.query(
                ZzXs.xm, ZzXs.xh, ZzBj.mc.label('class_name'),
                ZzStCourseSelection.select_time
            ).join(
                ZzStCourseSelection,
                ZzStCourseSelection.student_id == ZzXs.id
            ).outerjoin(
                ZzBj, ZzBj.id == ZzXs.bj_id
            ).filter(
                ZzStCourseSelection.course_id == course_id
            ).order_by(ZzBj.mc, ZzXs.xm).all()

            students = [{
                'xm': r.xm,
                'xh': r.xh,
                'class_name': r.class_name or '',
                'select_time': r.select_time.strftime('%m-%d %H:%M') if r.select_time else '',
            } for r in rows]

            return {'success': True, 'data': {'students': students, 'total': len(students)}}

        elif bj_id:
            # 查询该班级学生的选课情况
            students = db.query(ZzXs).filter(ZzXs.bj_id == bj_id, ZzXs.xjzt == 1).order_by(ZzXs.xm).all()
            id_list = [s.id for s in students]

            # 查询选课记录
            sel_map = {}
            if id_list:
                sels = db.query(
                    ZzStCourseSelection.student_id,
                    ZzStCourse.course_name
                ).join(
                    ZzStCourse, ZzStCourse.id == ZzStCourseSelection.course_id
                ).filter(
                    ZzStCourseSelection.student_id.in_(id_list)
                ).all()
                for s in sels:
                    sel_map[s.student_id] = s.course_name

            result = [{
                'xm': s.xm,
                'xh': s.xh,
                'course_name': sel_map.get(s.id, ''),
                'selected': s.id in sel_map,
            } for s in students]

            return {'success': True, 'data': {'students': result, 'total': len(result)}}

        return {'success': False, 'msg': '请指定course_id或bj_id'}
    except Exception as e:
        logger.error(f"获取选课详情失败: {str(e)}")
        return {'success': False, 'msg': f'获取失败: {str(e)}', 'data': None}


# ========== 留宿管理（班主任） ==========

from models.models import ZzSsLs, ZzSsCw, ZzSsSs, ZzSsLc, ZzSsLd


class StayApproveRequest(BaseModel):
    stay_id: int
    status: int  # 1-批准 2-拒绝
    remark: Optional[str] = ''


@router.get('/stay/class_list')
@router.get('/stay/class_list')
async def get_stay_class_list(
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """获取所有有效期内有留宿申请的学生（不按班级过滤）"""
    try:
        bj_ids = current_user.get('bj_ids', [])
        now = datetime.now()

        # 先批量将已过期的记录标记为过期
        db.query(ZzSsLs).filter(
            ZzSsLs.bj_id.in_(bj_ids),
            ZzSsLs.status.in_([0, 1]),
            ZzSsLs.end_date < now
        ).update({ZzSsLs.status: 3, ZzSsLs.gxsj: now}, synchronize_session='fetch')
        db.commit()

        # 查询所有班级内有状态0/1/2留宿申请的学生（去重）
        from controllers.photo_upload import get_signed_photo_url

        # 直接查留宿申请表，关联学生
        stays = db.query(ZzSsLs).filter(
            ZzSsLs.bj_id.in_(bj_ids),
            ZzSsLs.status.in_([0, 1, 2])
        ).order_by(ZzSsLs.cjsj.desc()).all()

        # 按学生ID去重，每个学生只取最新一条
        seen = {}
        for stay in stays:
            if stay.xs_id not in seen:
                seen[stay.xs_id] = stay

        student_list = []
        for xs_id, latest_stay in seen.items():
            s = db.query(ZzXs).filter(ZzXs.id == xs_id).first()
            if not s:
                continue

            # 班级信息
            bj = db.query(ZzBj).filter(ZzBj.id == s.bj_id).first()
            bj_mc = bj.mc if bj else '未分配班级'

            # 宿舍信息：通过床位表反向查询，格式：栋-楼层-宿舍号-床位号
            dorm_info = None
            bed = db.query(ZzSsCw).filter(
                ZzSsCw.zsr_id == s.id,
                ZzSsCw.zsr_type == 'student',
                ZzSsCw.zt == 1
            ).first()
            if bed:
                room = db.query(ZzSsSs).filter(ZzSsSs.id == bed.ss_id).first()
                floor = db.query(ZzSsLc).filter(ZzSsLc.id == room.lc_id).first() if room else None
                building = db.query(ZzSsLd).filter(ZzSsLd.id == floor.ld_id).first() if floor else None
                ld = building.mc if building else ''
                lc = f"{floor.lc}" if floor else ''
                ssh = room.ssh if room else ''
                cwh = bed.cwh
                dorm_info = f"{ld}-{lc}楼-{ssh}-{cwh}"

            has_photo = s.headphoto == 1
            photo_url = get_signed_photo_url(s.sfzh, user_type="vocational") if has_photo and s.sfzh else None

            student_list.append({
                'id': s.id, 'xm': s.xm, 'xh': s.xh,
                'sfzh': s.sfzh,
                'xsdh': s.xsdh or '',
                'bj_id': s.bj_id,
                'bj_mc': bj_mc,
                'photo_url': photo_url,
                'dorm_info': dorm_info,
                'stay': {
                    'id': latest_stay.id,
                    'ls_type': latest_stay.ls_type,
                    'ls_reason': latest_stay.ls_reason,
                    'start_date': latest_stay.start_date.strftime('%Y-%m-%d') if latest_stay.start_date else '',
                    'end_date': latest_stay.end_date.strftime('%Y-%m-%d') if latest_stay.end_date else '',
                    'status': latest_stay.status,
                    'approve_by': latest_stay.approve_by,
                    'approve_remark': latest_stay.approve_remark,
                    'approve_time': latest_stay.approve_time.strftime('%Y-%m-%d %H:%M') if latest_stay.approve_time else '',
                    'cjsj': latest_stay.cjsj.strftime('%Y-%m-%d %H:%M') if latest_stay.cjsj else ''
                }
            })

        # 按班级ID、姓名排序
        student_list.sort(key=lambda x: (x['bj_id'] or 0, x['xm']))

        return {'success': True, 'msg': '获取成功', 'data': {'students': student_list}}
    except Exception as e:
        logger.error(f"获取留宿学生列表失败: {str(e)}")
        return {'success': False, 'msg': f'获取失败: {str(e)}', 'data': {'students': []}}


@router.post('/stay/approve')
async def approve_stay(
    request: StayApproveRequest,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """审批留宿申请"""
    try:
        t_xm = current_user.get('t_xm', '')
        record = db.query(ZzSsLs).filter(ZzSsLs.id == request.stay_id).first()
        if not record:
            return {'success': False, 'msg': '记录不存在', 'data': None}
        if record.status != 0:
            return {'success': False, 'msg': '该申请已处理', 'data': None}

        record.status = request.status
        record.approve_by = t_xm
        record.approve_time = datetime.now()
        record.approve_remark = request.remark or ''
        db.commit()

        # 给学生发短信通知
        try:
            student = db.query(ZzXs).filter(ZzXs.id == record.xs_id).first()
            if student and student.xsdh:
                from utils.sms import SMSTool
                sms = SMSTool()
                status_text = '已批准' if request.status == 1 else '已拒绝'
                sms.send_by_scenario(
                    scenario='student_stay',
                    mobile=student.xsdh,
                    values={
                        'name': record.xs_xm,
                        'apply_type': '留宿',
                        'status': status_text,
                    },
                    xs_id=student.xh, xs_xm=student.xm,
                )
        except Exception as sms_err:
            logger.warning(f"留宿审批短信通知失败: {str(sms_err)}")

        return {'success': True, 'msg': f'审批成功（{("批准" if request.status == 1 else "拒绝")}）', 'data': None}
    except Exception as e:
        db.rollback()
        logger.error(f"审批留宿失败: {str(e)}")
        return {'success': False, 'msg': f'审批失败: {str(e)}', 'data': None}
