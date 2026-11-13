"""报名记录查询与修改控制器

用户报名成功后获得8位查询码，凭查询码可以：
1. 查看自己的报名记录
2. 修改报名信息并重新提交（update而非insert）
3. 管理员可以失效/重新生成查询码
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session
from init.database_optimized import get_db
from models.models import (
    ZsAdultEnrollment, ZsVocational34Enrollment,
    ZsGraduateEmploymentSurvey, ZzBmxs, WxPayinfo,
    wxxs_xf_payinfo, Major
)
from utils.query_code import (
    generate_unique_query_code, get_query_code_expire_time,
    is_query_code_valid, FORM_TYPE_CONFIG
)
from utils.sms import SMSTool
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/enrollment_query", tags=["报名查询"])

# 模型映射
MODEL_MAP = {
    'adult_exam': ZsAdultEnrollment,
    'vocational_34': ZsVocational34Enrollment,
    'graduate_employment_survey': ZsGraduateEmploymentSurvey,
    'vocational_zzbm': ZzBmxs,
}


class QueryCodeVerifyRequest(BaseModel):
    """验证查询码请求"""
    query_code: str = Field(..., min_length=8, max_length=12)


class AdminRefreshCodeRequest(BaseModel):
    """管理员刷新查询码请求"""
    form_type: str = Field(...)
    record_id: int = Field(...)


class AdminInvalidateCodeRequest(BaseModel):
    """管理员失效查询码请求"""
    form_type: str = Field(...)
    record_id: int = Field(...)


# ==================== 用户接口 ====================


@router.post('/verify')
def verify_query_code(data: QueryCodeVerifyRequest, db: Session = Depends(get_db)):
    """验证查询码，返回报名记录信息
    
    查询码全局唯一，无需指定form_type，自动识别来源表
    """
    try:
        code = data.query_code.strip().upper()
        
        if not code:
            return {'success': False, 'msg': '请输入查询码'}
        
        # 遍历所有报名表查找该查询码
        for form_type, model_cls in MODEL_MAP.items():
            record = db.query(model_cls).filter(
                model_cls.query_code == code
            ).first()
            
            if record:
                # 检查有效期
                if not is_query_code_valid(record.query_code_expire):
                    return {
                        'success': False,
                        'msg': '查询码已过期，请联系管理员重新生成'
                    }
                
                # 序列化记录
                record_data = _serialize_record(record, form_type)
                config = FORM_TYPE_CONFIG[form_type]
                
                # 对中职报名额外查询缴费状态
                payment_info = None
                if form_type == 'vocational_zzbm' and hasattr(record, 'sfzh') and record.sfzh:
                    payment_info = _get_payment_status(db, record.sfzh)
                
                return {
                    'success': True,
                    'msg': '验证成功',
                    'data': {
                        'form_type': form_type,
                        'form_display_name': config['display_name'],
                        'record_id': record.id,
                        'record': record_data,
                        'payment_info': payment_info
                    }
                }
        
        return {'success': False, 'msg': '查询码无效，请检查后重试', 'data': None}

    except Exception as e:
        logger.error(f'验证查询码失败: {e}')
        return {'success': False, 'msg': '系统异常，请稍后重试'}


@router.post('/verify_payment')
def verify_payment_query_code(data: QueryCodeVerifyRequest, db: Session = Depends(get_db)):
    """验证新生缴费查询码，返回订单信息和专业信息
    
    用于 pages/new-student-payment 页面
    """
    try:
        code = data.query_code.strip().upper()
        if not code:
            return {'success': False, 'msg': '请输入查询码', 'data': None}
        
        # 在 wxxs_xf_payinfo 表查找
        order = db.query(wxxs_xf_payinfo).filter(
            wxxs_xf_payinfo.query_code == code
        ).first()
        
        if not order:
            return {'success': False, 'msg': '查询码无效，请检查后重试', 'data': None}
        
        # 检查有效期
        if not is_query_code_valid(order.query_code_expire):
            return {'success': False, 'msg': '查询码已过期，请联系管理员', 'data': None}
        
        # 查询专业信息
        major_info = None
        if order.o_zyid:
            major = db.query(Major).filter(Major.id == order.o_zyid).first()
            if major:
                major_info = {
                    'id': major.id,
                    'name': major.mc,
                    'level': major.cc,
                }
        
        # 判断缴费状态
        has_paid = order.o_status == 1
        status_text = '已缴费' if has_paid else ('订单已关闭' if order.o_close == 1 else '未缴费')
        
        return {
            'success': True,
            'msg': '查询成功',
            'data': {
                'order': {
                    'order_no': order.o_order_no,
                    'name': order.o_xm,
                    'id_card': order.o_sfzh,
                    'phone': order.o_sj,
                    'amount': order.o_money,
                    'tuition': order.o_xf,
                    'book_fee': order.o_sf,
                    'status': order.o_status,
                    'has_paid': has_paid,
                    'status_text': status_text,
                    'pay_time': order.o_paytime,
                    'create_time': order.o_addtime.isoformat() if order.o_addtime else None,
                },
                'major': major_info
            }
        }
    except Exception as e:
        logger.error(f'验证缴费查询码失败: {e}')
        return {'success': False, 'msg': '系统异常，请稍后重试', 'data': None}


@router.post('/update/adult_exam')
def update_adult_exam(data: dict, db: Session = Depends(get_db)):
    """修改成人高等教育报名信息"""
    return _update_record('adult_exam', data, db)


@router.post('/update/vocational_34')
def update_vocational_34(data: dict, db: Session = Depends(get_db)):
    """修改3+4报名信息"""
    return _update_record('vocational_34', data, db)


@router.post('/update/graduate_employment_survey')
def update_graduate_survey(data: dict, db: Session = Depends(get_db)):
    """修改毕业生就业调查信息"""
    return _update_record('graduate_employment_survey', data, db)


@router.post('/update/vocational_zzbm')
def update_vocational_zzbm(data: dict, db: Session = Depends(get_db)):
    """修改中职报名信息
    
    注意：如果用户修改了专业(bdzy)，需要处理名额变动：
    - 原专业 bmrs - 1
    - 新专业 bmrs + 1（需检查新专业是否还有名额）
    使用行级锁保证原子性。
    """
    try:
        from sqlalchemy import text
        
        query_code = (data.get('query_code') or '').strip().upper()
        record_id = data.get('record_id')
        
        if not query_code or not record_id:
            return {'success': False, 'msg': '缺少必要参数', 'data': None}
        
        record = db.query(ZzBmxs).filter(
            ZzBmxs.id == record_id,
            ZzBmxs.query_code == query_code
        ).first()
        
        if not record:
            return {'success': False, 'msg': '记录不存在或查询码不匹配', 'data': None}
        
        if not is_query_code_valid(record.query_code_expire):
            return {'success': False, 'msg': '查询码已过期，请联系管理员', 'data': None}
        
        update_data = data.get('form_data', {})
        if not update_data:
            return {'success': False, 'msg': '没有需要更新的数据', 'data': None}
        
        # 检查是否修改了专业
        new_bdzy = update_data.get('bdzy')
        old_bdzy = record.bdzy
        
        if new_bdzy and int(new_bdzy) != int(old_bdzy):
            # 专业变更 — 需要处理名额
            new_bdzy = int(new_bdzy)
            old_bdzy = int(old_bdzy)
            
            # 锁定新专业行，检查名额
            new_major = db.execute(
                text("""
                    SELECT id, zsme, bmrs FROM zz_bmxs_cooperation_schoolmajor WITH (UPDLOCK, ROWLOCK)
                    WHERE id = :id
                """),
                {"id": new_bdzy}
            ).first()
            
            if not new_major:
                return {'success': False, 'msg': '新专业不存在', 'data': None}
            
            # 实时查询新专业实际报名人数
            new_bmrs = db.execute(
                text("SELECT COUNT(*) FROM zz_bmxs WHERE bdzy = :bdzy AND pc = :pc"),
                {"bdzy": new_bdzy, "pc": record.pc}
            ).scalar() or 0
            
            if new_major.zsme and new_bmrs >= new_major.zsme:
                return {'success': False, 'msg': '该专业名额已满，请选择其他专业', 'data': None}
            
            # 新专业 +1
            db.execute(
                text("UPDATE zz_bmxs_cooperation_schoolmajor SET bmrs = bmrs + 1 WHERE id = :id"),
                {"id": new_bdzy}
            )
            # 原专业 -1（不低于0）
            db.execute(
                text("UPDATE zz_bmxs_cooperation_schoolmajor SET bmrs = CASE WHEN bmrs > 0 THEN bmrs - 1 ELSE 0 END WHERE id = :id"),
                {"id": old_bdzy}
            )
        
        # 更新记录字段（排除系统字段）
        protected_fields = {
            'id', 'query_code', 'query_code_expire', 'pc', 'tjsj'
        }
        
        updated_count = 0
        for key, value in update_data.items():
            if key in protected_fields:
                continue
            if hasattr(record, key):
                setattr(record, key, value)
                updated_count += 1
        
        if updated_count == 0:
            return {'success': False, 'msg': '没有可更新的字段', 'data': None}

        db.commit()
        
        logger.info(f'中职报名信息修改成功: record_id={record_id}, updated_fields={updated_count}, bdzy_changed={new_bdzy != old_bdzy if new_bdzy else False}')
        
        return {
            'success': True,
            'msg': '修改成功',
            'data': {
                'record_id': record.id,
                'updated_fields': updated_count
            }
        }
    except Exception as e:
        db.rollback()
        logger.error(f'中职报名修改失败: {e}')
        return {'success': False, 'msg': f'系统异常: {e}', 'data': None}


# ==================== 管理员接口 ====================


@router.post('/admin/refresh_code')
def admin_refresh_code(data: AdminRefreshCodeRequest, db: Session = Depends(get_db)):
    """管理员重新生成查询码（旧码失效）"""
    try:
        form_type = data.form_type
        record_id = data.record_id
        
        if form_type not in MODEL_MAP:
            return {'success': False, 'msg': '无效的表单类型'}
        
        model_cls = MODEL_MAP[form_type]
        record = db.query(model_cls).filter(model_cls.id == record_id).first()
        
        if not record:
            return {'success': False, 'msg': '记录不存在'}
        
        config = FORM_TYPE_CONFIG[form_type]
        table_name = config['table']
        
        # 生成新查询码
        new_code = generate_unique_query_code(db, table_name)
        new_expire = get_query_code_expire_time()
        
        record.query_code = new_code
        record.query_code_expire = new_expire
        db.commit()
        
        # 发送短信通知用户
        phone_field = config['phone_field']
        phone = getattr(record, phone_field, None)
        name_field = config['name_field']
        name = getattr(record, name_field, '用户')
        
        if phone:
            sms_tool = SMSTool()
            sms_tool.send_by_scenario(
                scenario='query_code',
                mobile=phone,
                values={
                    'name': name,
                    'query_code': new_code,
                    'biz_name': config['display_name'],
                },
                xs_xm=name,
            )
        
        logger.info(f'管理员刷新查询码: form_type={form_type}, record_id={record_id}, new_code={new_code}')
        
        return {
            'success': True,
            'msg': '查询码已更新并短信通知用户',
            'data': {
                'query_code': new_code,
                'expire_time': new_expire.isoformat()
            }
        }
    except Exception as e:
        db.rollback()
        logger.error(f'刷新查询码失败: {e}')
        return {'success': False, 'msg': f'操作失败: {e}'}


@router.post('/admin/invalidate_code')
def admin_invalidate_code(data: AdminInvalidateCodeRequest, db: Session = Depends(get_db)):
    """管理员失效查询码"""
    try:
        form_type = data.form_type
        record_id = data.record_id
        
        if form_type not in MODEL_MAP:
            return {'success': False, 'msg': '无效的表单类型'}
        
        model_cls = MODEL_MAP[form_type]
        record = db.query(model_cls).filter(model_cls.id == record_id).first()
        
        if not record:
            return {'success': False, 'msg': '记录不存在'}
        
        # 将过期时间设为过去，使查询码失效
        record.query_code_expire = datetime(2000, 1, 1)
        db.commit()
        
        logger.info(f'管理员失效查询码: form_type={form_type}, record_id={record_id}')
        
        return {'success': True, 'msg': '查询码已失效'}
    except Exception as e:
        db.rollback()
        logger.error(f'失效查询码失败: {e}')
        return {'success': False, 'msg': f'操作失败: {e}'}


# ==================== 内部方法 ====================


def _update_record(form_type: str, data: dict, db: Session):
    """通用更新记录方法"""
    try:
        query_code = (data.get('query_code') or '').strip().upper()
        record_id = data.get('record_id')
        
        if not query_code or not record_id:
            return {'success': False, 'msg': '缺少必要参数', 'data': None}
        
        model_cls = MODEL_MAP[form_type]
        record = db.query(model_cls).filter(
            model_cls.id == record_id,
            model_cls.query_code == query_code
        ).first()
        
        if not record:
            return {'success': False, 'msg': '记录不存在或查询码不匹配'}
        
        # 检查有效期
        if not is_query_code_valid(record.query_code_expire):
            return {'success': False, 'msg': '查询码已过期，请联系管理员'}
        
        # 根据表单类型更新字段
        update_data = data.get('form_data', {})
        if not update_data:
            return {'success': False, 'msg': '没有需要更新的数据'}
        
        # 对 adult_exam 的字典字段做格式转换（前端传纯code，入库需要 category_id:type:code 格式）
        if form_type == 'adult_exam':
            from models.models import ZsCategory
            category = db.query(ZsCategory).filter(ZsCategory.code == 'adult_exam').first()
            if category:
                cat_id = category.id
                mc = update_data.get('major_code', '')
                if mc and ':' not in str(mc):
                    update_data['major_code'] = f"{cat_id}:zyyx:{mc}"
                lc = update_data.get('learning_center_code', '')
                if lc and ':' not in str(lc):
                    update_data['learning_center_code'] = f"{cat_id}:xxzx:{lc}"
        
        # 获取模型允许更新的字段（排除系统字段）
        protected_fields = {
            'id', 'query_code', 'query_code_expire', 'create_time',
            'submit_time', 'status', 'batch', 'serial_number',
            'audit_time', 'auditor_id', 'audit_remark',
            'wx_openid', 'wx_nickname', 'wx_headimgurl'
        }
        
        updated_count = 0
        for key, value in update_data.items():
            if key in protected_fields:
                continue
            if hasattr(record, key):
                setattr(record, key, value)
                updated_count += 1
        
        if updated_count == 0:
            return {'success': False, 'msg': '没有可更新的字段'}
        
        # 更新时间
        if hasattr(record, 'update_time'):
            record.update_time = datetime.now()
        
        db.commit()
        
        config = FORM_TYPE_CONFIG[form_type]
        logger.info(f'用户修改报名信息: form_type={form_type}, record_id={record_id}, updated_fields={updated_count}')
        
        return {
            'success': True,
            'msg': '修改成功',
            'data': {
                'record_id': record.id,
                'updated_fields': updated_count
            }
        }
    except Exception as e:
        db.rollback()
        logger.error(f'更新报名记录失败: {e}')
        return {'success': False, 'msg': f'系统异常: {e}'}


def _serialize_record(record, form_type: str) -> dict:
    """将ORM记录序列化为字典"""
    if form_type == 'adult_exam':
        return {
            'id': record.id,
            'name': record.name,
            'phone': record.phone,
            'major_code': record.major_code,
            'learning_center_code': record.learning_center_code,
            'recruiter': record.recruiter,
            'status': record.status,
            'submit_time': record.submit_time.isoformat() if record.submit_time else None,
        }
    elif form_type == 'vocational_34':
        return {
            'id': record.id,
            'serial_number': record.serial_number,
            'name': record.name,
            'admission_ticket_no': record.admission_ticket_no,
            'gender': record.gender,
            'nation': record.nation,
            'id_card': record.id_card,
            'junior_school_name': record.junior_school_name,
            'junior_school_county': record.junior_school_county,
            'is_qdn_graduate': record.is_qdn_graduate,
            'household_type': record.household_type,
            'household_province': record.household_province,
            'household_city': record.household_city,
            'household_district': record.household_district,
            'household_address': record.household_address,
            'residence_province': record.residence_province,
            'residence_city': record.residence_city,
            'residence_district': record.residence_district,
            'residence_address': record.residence_address,
            'phone': record.phone,
            'interview_car_plate': record.interview_car_plate,
            'guardian_name': record.guardian_name,
            'guardian_phone': record.guardian_phone,
            'guardian_relation': record.guardian_relation,
            'id_card_front_url': record.id_card_front_url,
            'id_card_back_url': record.id_card_back_url,
            'photo_url': record.photo_url,
            'consent_letter_url': record.consent_letter_url,
            'signature_base64': record.signature_base64,
            'is_confirmed': record.is_confirmed,
            'status': record.status,
            'submit_time': record.submit_time.isoformat() if record.submit_time else None,
        }
    elif form_type == 'graduate_employment_survey':
        return {
            'id': record.id,
            'student_no': record.student_no,
            'student_name': record.student_name,
            'id_card': record.id_card,
            'phone': record.phone,
            'precise_service': record.precise_service,
            'destination': record.destination,
            'military_office': record.military_office,
            'education_level': record.education_level,
            'college_code': record.college_code,
            'college_name': record.college_name,
            'major_code': record.major_code,
            'major_name': record.major_name,
            'admission_score': record.admission_score,
            'contract_type': record.contract_type,
            'employment_channel': record.employment_channel,
            'company_name': record.company_name,
            'work_province_city': record.work_province_city,
            'work_address': record.work_address,
            'company_nature': record.company_nature,
            'industry': record.industry,
            'position': record.position,
            'position_name': record.position_name,
            'monthly_salary': record.monthly_salary,
            'certificate_url': record.certificate_url,
            'satisfaction': record.satisfaction,
            'need_recommendation': record.need_recommendation,
            'feedback': record.feedback,
            'submit_time': record.submit_time.isoformat() if record.submit_time else None,
        }
    elif form_type == 'vocational_zzbm':
        return {
            'id': record.id,
            'xm': record.xm,
            'xb': record.xb,
            'mz': record.mz,
            'zzmm': record.zzmm,
            'sfzh': record.sfzh,
            'xsdh': record.xsdh,
            'jtxxdz': record.jtxxdz,
            'jzdlx': record.jzdlx,
            'hkxz': record.hkxz,
            'jzxm': record.jzxm,
            'jzgx': record.jzgx,
            'jzdh': record.jzdh,
            'bdzy': record.bdzy,
            'byxxssx1': record.byxxssx1,
            'byxxssx2': record.byxxssx2,
            'byxxssx3': record.byxxssx3,
            'byxxmc': record.byxxmc,
            'zsdx': record.zsdx,
            'sfjdlk': record.sfjdlk,
            'sflset': record.sflset,
            'sftwjrzn': record.sftwjrzn,
            'xsly': record.xsly,
            'qd': record.qd,
            'qdjs': record.qdjs,
            'sfqdxf': record.sfqdxf,
            'remark': getattr(record, 'remark', '') or '',
            'is_complete': getattr(record, 'is_complete', 0),
            'tjsj': record.tjsj.isoformat() if record.tjsj else None,
        }
    
    return {}


def _get_payment_status(db: Session, sfzh: str) -> dict:
    """查询中职学生缴费状态
    
    按身份证号查询 wx_payinfo 表，按 o_id 逆序取最新一条记录。
    - 无记录：未缴费
    - 有记录且 o_status=1：已缴费
    - 有记录但 o_status!=1：缴费未成功
    """
    try:
        latest_pay = db.query(WxPayinfo).filter(
            WxPayinfo.o_sfzh == sfzh
        ).order_by(WxPayinfo.o_id.desc()).first()
        
        if not latest_pay:
            return {
                'has_paid': False,
                'status_text': '未缴费',
                'order_no': None,
                'amount': None,
                'pay_time': None
            }
        
        if latest_pay.o_status == 1:
            return {
                'has_paid': True,
                'status_text': '已缴费',
                'order_no': latest_pay.o_order_no,
                'amount': latest_pay.o_money,
                'pay_time': latest_pay.o_paytime
            }
        else:
            return {
                'has_paid': False,
                'status_text': '缴费未成功',
                'order_no': latest_pay.o_order_no,
                'amount': latest_pay.o_money,
                'pay_time': None
            }
    except Exception as e:
        logger.error(f'查询缴费状态失败: {e}')
        return {
            'has_paid': False,
            'status_text': '查询异常',
            'order_no': None,
            'amount': None,
            'pay_time': None
        }
