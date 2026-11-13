from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session
from init.database_optimized import get_db
from models.models import ZsCategory, ZsDict, ZsAdultEnrollment, lw_sys
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
    """替换富文本中的图片URL为后端代理接口URL
    
    将 /headphoto/zs/xxx.jpg 或 https://m.qdndd.com.cn/headphoto/zs/xxx.jpg
    替换为 /photo/zs_image/xxx.jpg（由 photo_upload.py 的代理接口提供服务）
    """
    if not html:
        return html
    
    # 匹配相对路径: src="/headphoto/zs/xxx.jpg"
    def replace_relative(match):
        filename = match.group(1)
        return f'src="/photo/zs_image/{filename}"'
    
    html = re.sub(
        r'src=["\']/headphoto/zs/([^"\']+)["\']',
        replace_relative,
        html
    )
    
    # 匹配完整URL: src="https://m.qdndd.com.cn/headphoto/zs/xxx.jpg"
    def replace_full_url(match):
        filename = match.group(1)
        return f'src="/photo/zs_image/{filename}"'
    
    html = re.sub(
        r'src=["\']https?://[^"\']*?/headphoto/zs/([^"\']+)["\']',
        replace_full_url,
        html
    )
    
    return html


class AdultEnrollmentSubmit(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    phone: str = Field(..., min_length=11, max_length=11)
    major_code: str = Field(..., min_length=1)
    learning_center_code: str = Field(..., min_length=1)
    recruiter: Optional[str] = Field(None, max_length=50)
    wx_openid: Optional[str] = None
    wx_nickname: Optional[str] = None
    wx_headimgurl: Optional[str] = None


@router.get('/enrollment/prospectus')
def get_prospectus(code: str, db: Session = Depends(get_db)):
    try:
        category = db.query(ZsCategory).filter(
            ZsCategory.code == code,
            ZsCategory.is_active == 1
        ).first()
        
        if not category:
            raise HTTPException(status_code=404, detail='招生类别不存在')
        
        # 处理富文本中的图片URL：将私有桶路径替换为代理接口
        prospectus_html = category.prospectus or ''
        prospectus_html = _replace_prospectus_images(prospectus_html)
        
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f'获取招生简章失败: {str(e)}')
        raise HTTPException(status_code=500, detail=f'获取招生简章失败: {str(e)}')


@router.get('/enrollment/dict_list')
def get_dict_list(category_code: str, type: str, parent_code: Optional[str] = None, db: Session = Depends(get_db)):
    try:
        category = db.query(ZsCategory.id).filter(ZsCategory.code == category_code).first()
        if not category:
            raise HTTPException(status_code=404, detail='招生类别不存在')
        category_id = category[0]
        query = db.query(ZsDict).filter(ZsDict.category_id == category_id, ZsDict.type == type, ZsDict.is_active == 1)
        if parent_code:
            query = query.filter(ZsDict.parent_code == parent_code)
        dict_list = query.order_by(ZsDict.sort_order).all()
        return [{'id': item.id, 'code': item.code, 'label': item.label, 'parent_code': item.parent_code, 'sort_order': item.sort_order, 'remark': item.remark, 'extra_data': item.extra_data} for item in dict_list]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f'获取字典列表失败: {str(e)}')
        raise HTTPException(status_code=500, detail=f'获取字典列表失败: {str(e)}')


@router.post('/enrollment/adult_submit')
def adult_enrollment_submit(data: AdultEnrollmentSubmit, db: Session = Depends(get_db)):
    try:
        import re
        if not re.match(r'^1[3-9]\d{9}$', data.phone or ''):
            return {'success': False, 'msg': '手机号格式不正确'}
        if not data.name or not data.name.strip():
            return {'success': False, 'msg': '请输入姓名'}
        if not data.major_code:
            return {'success': False, 'msg': '请选择意向专业'}
        if not data.learning_center_code:
            return {'success': False, 'msg': '请选择学习中心'}
        existing = db.query(ZsAdultEnrollment).filter(ZsAdultEnrollment.phone == data.phone).first()
        if existing:
            return {'success': False, 'msg': '该手机号已经报名，请勿重复提交'}
        # 查询category_id
        category = db.query(ZsCategory).filter(ZsCategory.code == 'adult_exam').first()
        if not category:
            return {'success': False, 'msg': '招生类别adult_exam不存在'}
        # 时间窗口校验
        if not category.is_active:
            return {'success': False, 'msg': '该招生已停用'}
        now = datetime.now()
        if category.start_time and now < category.start_time:
            return {'success': False, 'msg': f'报名未开始，开始时间：{category.start_time.strftime("%Y-%m-%d %H:%M")}'}
        if category.end_time and now > category.end_time:
            return {'success': False, 'msg': f'报名已结束，结束时间：{category.end_time.strftime("%Y-%m-%d %H:%M")}'}
        cat_id = category.id

        # 批次：优先用招生类别自身的批次（zs_category.batch），否则回退到 lw_sys.sys_pc
        if category.batch is not None:
            batch_value = category.batch
        else:
            sys_config = db.query(lw_sys).first()
            batch_value = sys_config.sys_pc if sys_config else None
        
        # 字典字段转换为 category_id:type:code 格式
        major_code_val = f"{cat_id}:zyyx:{data.major_code}" if data.major_code else None
        learning_center_val = f"{cat_id}:xxzx:{data.learning_center_code}" if data.learning_center_code else None
        
        enrollment = ZsAdultEnrollment(name=data.name.strip(), phone=data.phone, major_code=major_code_val, learning_center_code=learning_center_val, batch=batch_value, recruiter=data.recruiter.strip() if data.recruiter else None, wx_openid=data.wx_openid, wx_nickname=data.wx_nickname, wx_headimgurl=data.wx_headimgurl, status=0, submit_time=datetime.now())
        
        # 生成查询码（在insert之前赋值，避免两次commit）
        from utils.query_code import generate_unique_query_code, get_query_code_expire_time
        query_code = generate_unique_query_code(db, 'zs_adult_enrollment')
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
                    'biz_name': '成人教育预报名',
                },
                xs_xm=data.name.strip(),
            )
        except Exception as sms_err:
            logger.error(f'报名成功但短信发送失败: {sms_err}')
        
        logger.info(f'成人教育报名成功: {data.name} - {data.phone}, query_code={query_code}')
        return {'success': True, 'msg': '报名成功', 'data': {'id': enrollment.id, 'query_code': query_code}}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f'成人教育报名失败: {str(e)}')
        return {'success': False, 'msg': '系统异常，报名失败'}


@router.get('/enrollment/adult_check')
def check_adult_enrollment(phone: str, db: Session = Depends(get_db)):
    try:
        enrollment = db.query(ZsAdultEnrollment).filter(ZsAdultEnrollment.phone == phone).first()
        if enrollment:
            return {'has_enrolled': True, 'enrollment': {'id': enrollment.id, 'name': enrollment.name, 'phone': enrollment.phone, 'status': enrollment.status, 'submit_time': enrollment.submit_time.isoformat() if enrollment.submit_time else None}}
        else:
            return {'has_enrolled': False}
    except Exception as e:
        logger.error(f'检查报名状态失败: {str(e)}')
        raise HTTPException(status_code=500, detail=f'检查报名状态失败: {str(e)}')


# 招生老师列表（与vocational-zzbm渠道介绍人同一数据源）
# 置顶名单（始终显示在最前面）
RECRUITER_PINNED = ['石开华']

RECRUITER_LIST = [
    '王小华','高杰','张龙','杨欢','潘明月','杨仁伟','李聪聪','钟卫东','余勇','文肇','鄢汉萍',
    '文松萍','龙艳香','杨铠伊','王雪梅','杨旭','周文伟','尹慧','袁婷','朱彦蓉','陈方静怡',
    '植凤萍','杨颜萍','龙淇','刘荣枝','王在珣','蔡代娇','白银坪','童怡昕','龙明杰','刘嘉丽',
    '韦兴燕','杨帆','王琳','夏晓刚','龙开星','霍永生','杨顺波','王正仿','罗文雯',
    '杨敏','周桂珍','龙安发','喻双','王秀君','吴兴递','吴仙燕','张仕强','刘敏','潘燕林',
    '杨鹏','欧阳可珍','彭旺','潘淼','王东','姚荣珊','杨升敏','杨泽','潘永成','周昌松',
    '高亮','莫福梅','李瑶瑶','袁杨成','吴培英','吴化仙','肖祖芳','杨秀斌','王仁倩','杨瑞瑶',
    '吴敏茜','陈慧','林泽鸿','郑洁洁','陆大富','王一珏','杨天嫄','陈文龙','蒋昌容','王明灯',
    '邓力','吴光文','彭泽伟','张忠标','孙正飞','池穆朗','李媛媛','杨宗振','李永睿',
    '李国榕','粟多铭','王明勇','王晋伟','王昕','黄功琴','杨家平','封璇','段忠贵','潘柳松',
    '吴如金','包琳恩','韦国睿','杨百忠','杨亚群','姜魁','田锦友','杨熠','周明菲','杨军'
]


@router.get('/enrollment/recruiter_list')
def get_recruiter_list():
    """获取招生老师列表（置顶名单始终在最前面）"""
    import pypinyin

    def build_item(name):
        try:
            pinyin_list = pypinyin.lazy_pinyin(name, style=pypinyin.Style.FIRST_LETTER)
            first_letter = pinyin_list[0].upper() if pinyin_list else name[0].upper()
            full_pinyin = ''.join(pypinyin.lazy_pinyin(name)).upper()
        except Exception:
            first_letter = name[0].upper()
            full_pinyin = name
        return {
            'name': name,
            'avatar': name[0],
            'firstLetter': first_letter,
            'pinyin': full_pinyin
        }

    pinned_items = [build_item(n) for n in RECRUITER_PINNED]
    normal_names = [n for n in RECRUITER_LIST if n not in RECRUITER_PINNED]
    normal_items = sorted([build_item(n) for n in normal_names], key=lambda x: x['firstLetter'])
    return pinned_items + normal_items
