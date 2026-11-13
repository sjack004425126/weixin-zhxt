from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session
from init.database_optimized import get_db
from models.models import ZsCategory, ZsDict, ZsVocational34Enrollment, lw_sys
from services.minio_service import (
    put_zs_image,
    sign_object_url as _sign_zs_image,
    delete_object as _delete_zs_object,
)
import json
import logging
import re


def _parse_extra_info(raw):
    """解析 zs_category.extra_info JSON 字符串为 dict，失败返回 {}"""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

logger = logging.getLogger(__name__)
router = APIRouter()


def _replace_prospectus_images(html: str) -> str:
    """替换富文本中的图片URL为后端代理接口URL。

    图片存储在私有桶 private/zs/<uuid>.<ext>。
    访问路径：/photo/zs_image/<filename>?t=&s=（HMAC 签名）
    """
    if not html:
        return html

    def _sign_src(m: re.Match) -> str:
        # m.group(1) 是 private/zs/ 之后的路径
        path = m.group(1)
        return f'src="{_sign_zs_image(path)}"'

    # 匹配 /private/zs/xxx 或 /headphoto/zs/xxx（历史路径）
    html = re.sub(
        r'src=["\'](?:/headphoto)?/private/zs/([^"\']+)["\']',
        _sign_src,
        html,
    )
    # 也匹配完整 URL 形式（http(s)://...）
    html = re.sub(
        r'src=["\']https?://[^"\']*?/(?:headphoto/)?private/zs/([^"\']+)["\']',
        _sign_src,
        html,
    )
    # 兼容老的 /headphoto/zs/ 前缀（清库前的历史数据）
    html = re.sub(
        r'src=["\']/headphoto/zs/([^"\']+)["\']',
        lambda m: f'src="{_sign_zs_image(m.group(1))}"',
        html,
    )
    html = re.sub(
        r'src=["\']https?://[^"\']*?/headphoto/zs/([^"\']+)["\']',
        lambda m: f'src="{_sign_zs_image(m.group(1))}"',
        html,
    )
    return html


@router.post('/vocational34/upload_image')
async def upload_image(file: UploadFile = File(...)):
    """上传图片到 MinIO 私有桶 private/zs/ 目录。

    桶名通过环境变量 MINIO_BUCKET_PRIVATE 配置；
    桶由运维预建，应用账号无 make_bucket 权限。
    """
    try:
        content = await file.read()
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail='图片大小不能超过10MB')

        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'jpg'
        if ext not in ('jpg', 'jpeg', 'png', 'gif', 'webp'):
            ext = 'jpg'

        # put_zs_image 返回 object_key（含前导斜杠），例如 /private/zs/<uuid>.jpg
        object_key = put_zs_image(content, ext=ext, content_type=file.content_type or 'image/jpeg')
        # 从 object_key 提取 filename（去掉前导斜杠）
        filename = object_key.lstrip("/").split("/", 1)[-1]
        # 返回带签名的代理 URL
        proxy_url = _sign_zs_image(object_key.lstrip("/"))
        logger.info(f'图片上传成功: {object_key}')
        return {
            'success': True,
            'msg': '上传成功',
            'data': {
                'url': proxy_url,
                'key': object_key,
                'filename': filename,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f'图片上传失败: {str(e)}')
        raise HTTPException(status_code=500, detail=f'图片上传失败: {str(e)}')


@router.post('/vocational34/delete_image')
async def delete_image(payload: dict):
    """删除单个 MinIO 对象（用于前端提交失败时回滚孤儿凭证）。

    入参：{"key": "zs/<uuid>.jpg" 或 "<bucket>/zs/<uuid>.jpg"}
    返回：{"success": true, "data": {"deleted": true/false}}

    安全：只允许删除 zs/ 前缀的对象，防止越权删除其他业务桶里的对象。
    """
    raw_key = (payload or {}).get('key', '')
    if not raw_key:
        raise HTTPException(status_code=400, detail='key 不能为空')
    s = str(raw_key).strip().lstrip('/')
    # 防御：必须以 zs/ 开头
    if not s.startswith('zs/'):
        raise HTTPException(status_code=400, detail='key 不合法：仅允许删除 zs/ 前缀对象')
    # 防御：路径里不能再有 ..，不能以 / 结尾
    tail = s[len('zs/'):]
    if not tail or '..' in tail or tail.endswith('/'):
        raise HTTPException(status_code=400, detail='key 不合法')
    ok = _delete_zs_object(s)
    return {'success': True, 'data': {'deleted': ok}}


class Vocational34EnrollmentSubmit(BaseModel):

    # 考生基本信息（全部必填）
    name: str = Field(..., min_length=1, max_length=50)
    admission_ticket_no: str = Field(..., min_length=1, max_length=50)
    gender: str = Field(..., min_length=1)
    nation: str = Field(..., min_length=1)
    id_card: str = Field(..., min_length=18, max_length=18)
    junior_school_name: str = Field(..., min_length=1, max_length=200)
    junior_school_county: str = Field(..., min_length=1, max_length=100)
    is_qdn_graduate: int = Field(...)
    
    # 籍贯信息（全部必填）
    household_type: str = Field(..., min_length=1)
    household_province: str = Field(..., min_length=1)
    household_city: str = Field(..., min_length=1)
    household_district: str = Field(..., min_length=1)
    household_address: str = Field(..., min_length=1, max_length=200)
    residence_province: str = Field(..., min_length=1)
    residence_city: str = Field(..., min_length=1)
    residence_district: str = Field(..., min_length=1)
    residence_address: str = Field(..., min_length=1, max_length=200)
    
    # 手机号
    phone: str = Field(..., min_length=11, max_length=11)

    # 面试当天是否驾车及车牌信息（不驾车填“无”）
    interview_car_plate: str = Field(..., min_length=1, max_length=50)
    
    # 监护人信息（全部必填）
    guardian_name: str = Field(..., min_length=1, max_length=50)
    guardian_phone: str = Field(..., min_length=11, max_length=11)
    guardian_relation: str = Field(..., min_length=1)
    
    # 图片URL（全部必填）
    id_card_front_url: str = Field(..., min_length=1)
    id_card_back_url: str = Field(..., min_length=1)
    photo_url: str = Field(..., min_length=1)
    consent_letter_url: str = Field(..., min_length=1)
    
    # 知情确认（必须勾选）
    is_confirmed: int = Field(...)
    
    # 签名（base64编码，必填）
    signature_base64: str = Field(..., min_length=1)
    
    # 微信信息
    wx_openid: Optional[str] = None
    wx_nickname: Optional[str] = None
    wx_headimgurl: Optional[str] = None


@router.get('/vocational34/prospectus')
def get_prospectus(db: Session = Depends(get_db)):
    """获取3+4招生简章"""
    try:
        category = db.query(ZsCategory).filter(
            ZsCategory.code == 'vocational_34',
            ZsCategory.is_active == 1
        ).first()
        
        if not category:
            raise HTTPException(status_code=404, detail='招生类别不存在')
        
        # 处理富文本中的图片URL
        prospectus_html = _replace_prospectus_images(category.prospectus or '')
        
        return {
            'code': category.code,
            'name': category.name,
            'description': category.description,
            'prospectus': prospectus_html,
            'extra_info': _parse_extra_info(category.extra_info),
            'start_time': category.start_time.isoformat() if category.start_time else None,
            'end_time': category.end_time.isoformat() if category.end_time else None,
            'batch': category.batch
        }
    except Exception as e:
        logger.error(f'获取招生简章失败: {str(e)}')
        raise HTTPException(status_code=500, detail=f'获取招生简章失败: {str(e)}')


@router.get('/vocational34/dict_list')
def get_dict_list(type: str, parent_code: Optional[str] = None, db: Session = Depends(get_db)):
    """获取字典列表"""
    try:
        category = db.query(ZsCategory.id).filter(ZsCategory.code == 'vocational_34').first()
        if not category:
            raise HTTPException(status_code=404, detail='招生类别不存在')
        
        category_id = category[0]
        query = db.query(ZsDict).filter(
            ZsDict.category_id == category_id,
            ZsDict.type == type,
            ZsDict.is_active == 1
        )
        
        if parent_code:
            query = query.filter(ZsDict.parent_code == parent_code)
        
        dict_list = query.order_by(ZsDict.sort_order).all()
        
        return [{
            'id': item.id,
            'code': item.code,
            'label': item.label,
            'parent_code': item.parent_code,
            'sort_order': item.sort_order,
            'remark': item.remark,
            'extra_data': item.extra_data
        } for item in dict_list]
    except Exception as e:
        logger.error(f'获取字典列表失败: {str(e)}')
        raise HTTPException(status_code=500, detail=f'获取字典列表失败: {str(e)}')


@router.post('/vocational34/submit')
def vocational34_enrollment_submit(data: Vocational34EnrollmentSubmit, db: Session = Depends(get_db)):
    """提交3+4报名信息"""
    try:
        # 验证手机号格式
        phone_re = re.compile(r'^1[3-9]\d{9}$')
        if not phone_re.match(data.phone or ''):
            raise HTTPException(status_code=400, detail='手机号格式不正确')
        if not phone_re.match(data.guardian_phone or ''):
            raise HTTPException(status_code=400, detail='监护人手机号格式不正确')
        
        # 验证身份证号格式
        id_card_re = re.compile(r'^(\d{15}|\d{17}[\dXx])$')
        if not id_card_re.match(data.id_card or ''):
            raise HTTPException(status_code=400, detail='身份证号格式不正确')

        # 知情确认必须勾选
        if data.is_confirmed != 1:
            raise HTTPException(status_code=400, detail='请勾选知情确认')

        # 是否黔东南州应届毕业生取值校验
        if data.is_qdn_graduate not in (0, 1):
            raise HTTPException(status_code=400, detail='请选择是否黔东南州应届毕业生')

        # 必填字符串字段去空白后非空校验
        required_str_fields = {
            'name': '请输入学生姓名',
            'admission_ticket_no': '请输入准考证号',
            'gender': '请选择性别',
            'nation': '请选择民族',
            'junior_school_name': '请输入原初中毕业学校全称',
            'junior_school_county': '请输入原初中毕业学校所在县份',
            'household_type': '请选择户口性质',
            'household_province': '请选择户籍省份',
            'household_city': '请选择户籍城市',
            'household_district': '请选择户籍区县',
            'household_address': '请输入户籍详细地址',
            'residence_province': '请选择实际居住省份',
            'residence_city': '请选择实际居住城市',
            'residence_district': '请选择实际居住区县',
            'residence_address': '请输入实际居住详细地址',
            'interview_car_plate': '请填写面试当天是否驾车及车牌信息（不驾车请填“无”）',
            'guardian_name': '请输入监护人姓名',
            'guardian_relation': '请选择监护人身份',
            'id_card_front_url': '请上传身份证正面照',
            'id_card_back_url': '请上传身份证反面照',
            'photo_url': '请上传标准证件照',
            'consent_letter_url': '请上传监护人知情同意书',
            'signature_base64': '请完成考生签名',
        }
        for f, msg in required_str_fields.items():
            v = getattr(data, f, None)
            if not v or (isinstance(v, str) and not v.strip()):
                raise HTTPException(status_code=400, detail=msg)
        
        # 检查是否已经报名
        existing = db.query(ZsVocational34Enrollment).filter(
            ZsVocational34Enrollment.id_card == data.id_card
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail='该身份证号已经报名，请勿重复提交')
        
        # 查询category_id
        category = db.query(ZsCategory).filter(ZsCategory.code == 'vocational_34').first()
        if not category:
            raise HTTPException(status_code=500, detail='招生类别vocational_34不存在')
        # 时间窗口校验
        if not category.is_active:
            raise HTTPException(status_code=400, detail='该招生已停用')
        now = datetime.now()
        if category.start_time and now < category.start_time:
            raise HTTPException(status_code=400, detail=f'报名未开始，开始时间：{category.start_time.strftime("%Y-%m-%d %H:%M")}')
        if category.end_time and now > category.end_time:
            raise HTTPException(status_code=400, detail=f'报名已结束，结束时间：{category.end_time.strftime("%Y-%m-%d %H:%M")}')
        cat_id = category.id

        # 批次：优先用招生类别自身的批次（zs_category.batch），否则回退到 lw_sys.sys_pc
        if category.batch is not None:
            batch_value = category.batch
        else:
            sys_config = db.query(lw_sys).first()
            batch_value = sys_config.sys_pc if sys_config else None
        
        # 字典字段转换为 category_id:type:code 格式
        nation_val = f"{cat_id}:nation:{data.nation}" if data.nation else None
        is_qdn_val = data.is_qdn_graduate if data.is_qdn_graduate is not None else None
        household_type_val = f"{cat_id}:household_type:{data.household_type}" if data.household_type else None
        guardian_relation_val = f"{cat_id}:guardian_relation:{data.guardian_relation}" if data.guardian_relation else None
        
        # 生成序号
        count = db.query(ZsVocational34Enrollment).count()
        serial_number = f'V34{str(count + 1).zfill(6)}'
        
        # 创建报名记录
        enrollment = ZsVocational34Enrollment(
            serial_number=serial_number,
            name=data.name.strip(),
            admission_ticket_no=data.admission_ticket_no,
            gender=data.gender,
            nation=nation_val,
            id_card=data.id_card,
            junior_school_name=data.junior_school_name,
            junior_school_county=data.junior_school_county,
            is_qdn_graduate=is_qdn_val,
            household_type=household_type_val,
            household_province=data.household_province,
            household_city=data.household_city,
            household_district=data.household_district,
            household_address=data.household_address,
            residence_province=data.residence_province,
            residence_city=data.residence_city,
            residence_district=data.residence_district,
            residence_address=data.residence_address,
            phone=data.phone,
            interview_car_plate=data.interview_car_plate.strip(),
            guardian_name=data.guardian_name,
            guardian_phone=data.guardian_phone,
            guardian_relation=guardian_relation_val,
            id_card_front_url=data.id_card_front_url,
            id_card_back_url=data.id_card_back_url,
            photo_url=data.photo_url,
            consent_letter_url=data.consent_letter_url,
            is_confirmed=data.is_confirmed,
            signature_base64=data.signature_base64,
            wx_openid=data.wx_openid,
            wx_nickname=data.wx_nickname,
            wx_headimgurl=data.wx_headimgurl,
            batch=batch_value,
            status=0,
            submit_time=datetime.now()
        )
        
        # 生成查询码（在insert之前赋值，一次commit）
        from utils.query_code import generate_unique_query_code, get_query_code_expire_time
        query_code = generate_unique_query_code(db, 'zs_vocational34_enrollment')
        enrollment.query_code = query_code
        enrollment.query_code_expire = get_query_code_expire_time()
        
        db.add(enrollment)
        db.commit()
        db.refresh(enrollment)
        
        # 短信通知用户查询码
        try:
            from utils.sms import SMSTool
            sms_tool = SMSTool()
            sms_tool.send_by_scenario(
                scenario='query_code',
                mobile=data.phone,
                values={
                    'name': data.name.strip(),
                    'query_code': query_code,
                    'biz_name': type_name,
                },
                xs_xm=data.name.strip(),
            )
        except Exception as sms_err:
            logger.error(f'报名成功但短信发送失败: {sms_err}')
        
        logger.info(f'3+4报名成功: {data.name} - {data.id_card}, query_code={query_code}')
        
        return {
            'success': True,
            'msg': '报名成功',
            'data': {
                'id': enrollment.id,
                'serial_number': serial_number,
                'query_code': query_code
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f'3+4报名失败: {str(e)}')
        raise HTTPException(status_code=500, detail=f'报名失败: {str(e)}')


@router.get('/vocational34/check')
def check_vocational34_enrollment(id_card: str, db: Session = Depends(get_db)):
    """检查报名状态"""
    try:
        enrollment = db.query(ZsVocational34Enrollment).filter(
            ZsVocational34Enrollment.id_card == id_card
        ).first()
        
        if enrollment:
            return {
                'has_enrolled': True,
                'enrollment': {
                    'id': enrollment.id,
                    'serial_number': enrollment.serial_number,
                    'name': enrollment.name,
                    'id_card': enrollment.id_card,
                    'status': enrollment.status,
                    'submit_time': enrollment.submit_time.isoformat() if enrollment.submit_time else None
                }
            }
        else:
            return {'has_enrolled': False}
    except Exception as e:
        logger.error(f'检查报名状态失败: {str(e)}')
        raise HTTPException(status_code=500, detail=f'检查报名状态失败: {str(e)}')
