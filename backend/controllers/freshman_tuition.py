from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from models.models import Student, Class, wxxs_xf_zd, wxxs_xf_zdgr, wxxs_xf_info, lw_sys, wxxs_xf_payinfo, Major, MajorType
from init.dependencies import (
    get_redis, get_db,
    RedisDep, DatabaseDep, RedisManagerDep
)
from common.auth import verify_token_and_get_payload
from datetime import datetime
from sqlalchemy import text, or_
from typing import Optional
import random
from utils.wx_pay import WxPayUtil
from utils.wx_utils import WxUtils
import json
import logging


# ====================== 路由定义 ======================
router = APIRouter(prefix="/freshman_tuition", tags=["新生学费"])


# ====================== 请求模型 ======================
class PhoneVerifyRequest(BaseModel):
    code: Optional[str] = None
    role: Optional[str] = 'self'
    openid_code: Optional[str] = ''


def _get_verify_token_payload(token: str, redis_client):
    """从 Redis 中解析 verify_token"""
    key = f'kfxf:phone_verify:{token}'
    raw = redis_client.get(key)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


# ====================== 新生报名信息查询 ======================
@router.get('/new-student-checkPayment')
async def new_student_check_payment(
    queryCode: Optional[str] = None,
    verify_token: Optional[str] = None,
    role: Optional[str] = None,
    db: Session = DatabaseDep,
):
    """
    开放教育新生报名信息查询。
    - 模式 A (查询码): queryCode
    - 模式 B (手机号验证): verify_token（来自 verify_phone_for_payment）
    """
    sys_info = db.query(lw_sys).filter_by(id=1).first()

    # === 模式 A：查询码查询 ===
    if queryCode:
        code = queryCode.strip()
        if not code:
            return {'success': False, 'msg': '请输入查询码', 'data': None}

        payinfo = db.query(wxxs_xf_payinfo).filter_by(query_code=code).first()
        if not payinfo:
            return {'success': False, 'msg': '查询码无效', 'data': None}

        # 检查过期
        if payinfo.query_code_expire and payinfo.query_code_expire < datetime.now():
            return {'success': False, 'msg': '查询码已过期，请联系管理员', 'data': None}

        id_number = payinfo.o_sfzh
    else:
        # === 模式 B：手机号验证 ===
        if not verify_token:
            return {'success': False, 'msg': '请先完成微信身份验证', 'data': None}
        # 这里简化：verify_token 直接是身份证号（由 verify_phone_for_payment 签发）
        id_number = verify_token.strip()

    if not id_number:
        return {'success': False, 'msg': '身份验证失败', 'data': None}

    # 查订单
    payinfo = (
        db.query(wxxs_xf_payinfo)
        .filter_by(o_sfzh=id_number, o_pc=sys_info.sys_xsbm_pc)
        .filter(wxxs_xf_payinfo.o_close == 0)
        .filter(wxxs_xf_payinfo.o_delete == 0)
        .order_by(wxxs_xf_payinfo.o_addtime.desc())
        .first()
    )
    if not payinfo:
        return {'success': False, 'msg': '未找到您的报名记录', 'data': None}

    # 联查专业信息（含类型、层次、专业名）
    major = db.query(Major).filter_by(id=payinfo.o_zyid).first()
    major_name  = major.mc     if major else ''
    major_level = major.cc     if major else ''  # 专科/本科
    major_type  = ''
    if major and major.typeid:
        mtype = db.query(MajorType).filter_by(id=major.typeid).first()
        major_type = mtype.mc if mtype else ''   # 文史类/经管类等

    # 姓名取订单表
    student_name = payinfo.o_xm or ''

    # o_status == 1 已缴费
    paid_tip = (payinfo.o_status == 1)

    # 检查微信订单状态（防止延迟）
    if not paid_tip and payinfo.o_order_no:
        wx_pay = WxPayUtil()
        pay_result = wx_pay.query_order(payinfo.o_order_no)
        if pay_result.get('success'):
            payinfo.o_status = 1
            payinfo.o_paytime = pay_result.get('success_time', '')
            payinfo.o_trade_no = pay_result.get('transaction_id', '')
            db.commit()
            paid_tip = True

    # 费用（元转分 → 分转元字符串）
    xf  = payinfo.o_xf or 0
    sf  = payinfo.o_sf or 0
    zsf = 0
    total_fen = xf + sf + zsf

    jfxx = {
        'xf':     xf,
        'sf':     sf,
        'zsf':    zsf,
        'xfStr':  (xf  / 100).__format__('.2f'),
        'sfStr':  (sf  / 100).__format__('.2f'),
        'zsfStr': '0.00',
        'totalStr': (total_fen / 100).__format__('.2f'),
    }

    payorder_xx = None
    if payinfo.o_order_no:
        payorder_xx = {
            'o_id':            payinfo.o_id,
            'o_sfzh':          payinfo.o_sfzh,
            'o_paytype':       payinfo.o_paytype or '',
            'o_payment_time':  payinfo.o_paytime or '',
            'o_trade_no':      payinfo.o_trade_no or '',
            'o_money':         payinfo.o_money or 0,
            'o_status':        payinfo.o_status,
        }

    return {
        'success': True,
        'msg': '查询成功',
        'data': {
            'zyxx': {
                'xm':           student_name,
                'major_type':    major_type,   # 文史类/经管类等
                'major_level':   major_level,  # 专科/本科
                'major_name':    major_name,
            },
            'jfxx':  jfxx,
            'payorder_xx': payorder_xx,
            'student_name': student_name,
            'verified_name': student_name,
            'school_phone': '',
            'query_code': payinfo.query_code or '',
        }
    }


# ====================== 微信手机号身份认证 ======================
@router.post('/verify_phone_for_payment')
async def verify_phone_for_payment(
    payload: PhoneVerifyRequest,
    db: Session = DatabaseDep,
    redis_client=RedisDep,
):
    """
    开放教育新生缴费 - 微信手机号快捷身份认证。
    验证通过后签发 verify_token（直接为身份证号），15分钟有效。
    """
    code = (payload.code or '').strip()
    if not code:
        return {'success': False, 'msg': '请完成微信手机号验证', 'data': None}

    # 解微信手机号
    wx_result = WxUtils.get_phone_number(code)
    if not wx_result or not wx_result.get('phone_info'):
        return {'success': False, 'msg': '微信手机号获取失败', 'data': None}

    phone_info = wx_result['phone_info']
    wx_phone = phone_info.get('phoneNumber') or phone_info.get('purePhoneNumber') or ''
    wx_norm = wx_phone.strip().replace(' ', '')
    if wx_norm.startswith('+86'):
        wx_norm = wx_norm[3:]

    sys_info = db.query(lw_sys).filter_by(id=1).first()
    pc_filter = sys_info.sys_xsbm_pc if sys_info else 0

    # 在订单表中按手机号反查（o_sj 字段）
    payinfo_list = (
        db.query(wxxs_xf_payinfo)
        .filter_by(o_sj=wx_norm)
        .filter(wxxs_xf_payinfo.o_pc == pc_filter)
        .filter(wxxs_xf_payinfo.o_close == 0)
        .filter(wxxs_xf_payinfo.o_delete == 0)
        .all()
    )
    # 兼容空格/换行存储
    if not payinfo_list:
        payinfo_list = (
            db.query(wxxs_xf_payinfo)
            .filter(wxxs_xf_payinfo.o_sj.like(f'%{wx_norm}%'))
            .filter(wxxs_xf_payinfo.o_pc == pc_filter)
            .filter(wxxs_xf_payinfo.o_close == 0)
            .filter(wxxs_xf_payinfo.o_delete == 0)
            .all()
        )

    matched = []
    for p in payinfo_list:
        stored = (p.o_sj or '').strip().replace(' ', '')
        if stored.startswith('+86'):
            stored = stored[3:]
        if stored == wx_norm:
            matched.append(p)

    if len(matched) == 0:
        return {'success': False, 'msg': '未找到您的报名记录，请确认报名手机号', 'data': None}
    if len(matched) > 1:
        return {'success': False, 'msg': '手机号匹配到多条记录，请使用查询码查询', 'data': None}

    payinfo = matched[0]
    id_number = payinfo.o_sfzh
    masked = wx_norm[:3] + '****' + wx_norm[-4:]

    # verify_token 直接用身份证号，存 Redis 15分钟
    token_key = f'kfxf:phone_verify:{id_number}'
    token_data = json.dumps({'id_number': id_number, 'phone': wx_norm}, ensure_ascii=False)
    redis_client.setex(token_key, 900, token_data)

    return {
        'success': True,
        'msg': '身份验证通过',
        'data': {
            'verify_token': id_number,
            'masked_phone': masked,
        }
    }


# ====================== 发起支付 ======================
@router.get('/get_pre_payment_info')
async def get_pre_payment_info(
    queryCode: Optional[str] = None,
    verify_token: Optional[str] = None,
    openid_code: Optional[str] = None,
    db: Session = DatabaseDep,
):
    """获取支付参数"""
    sys_info = db.query(lw_sys).filter_by(id=1).first()

    id_number = None
    if queryCode:
        payinfo = db.query(wxxs_xf_payinfo).filter_by(query_code=queryCode.strip()).first()
        if payinfo:
            id_number = payinfo.o_sfzh
    elif verify_token:
        id_number = verify_token.strip()

    if not id_number:
        return {'success': False, 'msg': '缺少认证信息', 'data': None}

    payinfo = (
        db.query(wxxs_xf_payinfo)
        .filter_by(o_sfzh=id_number, o_pc=sys_info.sys_xsbm_pc)
        .filter(wxxs_xf_payinfo.o_close == 0)
        .filter(wxxs_xf_payinfo.o_delete == 0)
        .first()
    )
    if not payinfo:
        return {'success': False, 'msg': '订单不存在', 'data': None}

    if payinfo.o_status == 1:
        return {'success': False, 'msg': '该订单已完成支付', 'data': None}

    if not openid_code:
        return {'success': False, 'msg': '缺少 openid_code', 'data': None}

    wx_openid_result = WxUtils.get_openid_and_session_key(openid_code)
    if not wx_openid_result:
        return {'success': False, 'msg': '获取 openid 失败', 'data': None}
    openid = wx_openid_result['openid']

    wx_pay = WxPayUtil()
    pay_result = wx_pay.create_pay_info(
        openid=openid,
        out_trade_no=payinfo.o_order_no,
        total_fee=payinfo.o_money,
        description=payinfo.o_body or '开放教育新生缴费',
        business_type='wxxs_xf_payinfo',
    )
    if pay_result.get('success'):
        return {
            'success': True,
            'msg': '获取成功',
            'data': {**pay_result['pay_params'], 'orderNo': payinfo.o_order_no}
        }
    return {'success': False, 'msg': pay_result.get('req_des', '支付参数生成失败'), 'data': None}


# ====================== 支付后状态更新 ======================
@router.get('/update_pre_payment_order_status')
async def update_pre_payment_order_status(
    o_order_no: Optional[str] = None,
    db: Session = DatabaseDep,
):
    """更新订单支付状态"""
    if not o_order_no:
        return {'success': False, 'msg': '缺少订单号', 'data': None}

    payinfo = db.query(wxxs_xf_payinfo).filter_by(o_order_no=o_order_no).first()
    if not payinfo:
        return {'success': False, 'msg': '订单不存在', 'data': None}

    wx_pay = WxPayUtil()
    pay_result = wx_pay.query_order(o_order_no)
    if pay_result.get('success'):
        payinfo.o_status = 1
        payinfo.o_paytime = pay_result.get('success_time', '')
        payinfo.o_trade_no = pay_result.get('transaction_id', '')
        db.commit()
        return {'success': True, 'msg': '支付成功', 'data': None}
    return {'success': False, 'msg': pay_result.get('trade_state_desc', '支付状态查询失败'), 'data': None}


# ====================== 录取通知书 PDF ======================
@router.get('/generate_admission_notice_pdf_data')
async def generate_admission_notice_pdf_data(
    o_id: Optional[int] = None,
    db: Session = DatabaseDep,
):
    """生成录取通知书 PDF 数据（暂返回占位）"""
    return {
        'success': True,
        'msg': '生成成功',
        'pdf_base64': '',
    }


# ====================== 家长通知（占位） ======================
@router.post('/notify_parent_after_payment')
async def notify_parent_after_payment(
    o_order_no: Optional[str] = None,
    db: Session = DatabaseDep,
):
    return {'success': True, 'msg': '通知已发送', 'data': None}


# 地区书费配置
AREA_BOOK_FEE_CONFIG = {
    '黔东南直属': 0,  # 使用后台专业数据
    '丹寨': 900,
    '麻江': 900,
    '黄平': 900,
    '施秉': 900,
    '镇远': 900,
    '岑巩': 900,
    '三穗': 900,
    '天柱': 900,
    '锦屏': 900,
    '黎平': 900,
    '从江': 900,
    '榕江': 900,
    '雷山': 900,
    '台江': 900,
    '剑河': 900
}

# 地区名称 → 编码映射（对应原系统 isxs 字段）
AREA_CODE_MAP = {
    '黔东南直属': 1,
    '三穗':       2,
    '天柱':       3,
    '麻江':       4,
    '台江':       5,
    '锦屏':       6,
    '剑河':       7,
    '从江':       8,
    '黎平':       9,
    '镇远':       10,
    '施秉':       11,
    '黄平':       12,
    '榕江':       13,
    '岑巩':       14,
    '雷山':       15,
    '丹寨':       16,
}

# 三穗地区特殊专业配置
SANSUI_SPECIAL_MAJORS = {
    26: 350,  # 专业26的书费
    73: 350   # 专业73的书费
}

def get_area_book_fee(area, major_id, default_book_fee):
    """根据地区和专业ID计算书费"""
    # 如果没有传入地区或地区为黔东南直属，使用后台专业数据
    if not area or area == '黔东南直属':
        return default_book_fee

    # 三穗地区特殊专业处理
    if area == '三穗' and major_id in SANSUI_SPECIAL_MAJORS:
        return SANSUI_SPECIAL_MAJORS[major_id]

    # 其他地区按配置表匹配
    return AREA_BOOK_FEE_CONFIG.get(area, default_book_fee)


# 请求模型
class PaymentRequest(BaseModel):
    name: str
    id_card: str
    phone: str
    major_id: int
    code: str
    area: str

class UpdatePayStatusRequest(BaseModel):
    orderNo: str

class UpdateMajorFeesRequest(BaseModel):
    major_id: int
    tuition: int
    books: int


# 获取所有专业信息(包含层次、类型、专业名称、学费信息)
# 三级联动顺序：类型 → 层次 → 专业
@router.get('/get_majors_all')
async def get_majors_all(db: Session = DatabaseDep):
    try:
        # 从oa_zy_type表查询未锁定的类型(isblock=0)
        major_types = db.query(MajorType).filter(
            MajorType.isblock == 0
        ).order_by(
            MajorType.orderid
        ).all()
        
        # 构建类型ID到名称的映射
        type_names = {mt.id: mt.mc for mt in major_types}
        valid_type_ids = set(type_names.keys())
        
        # 查询未锁定的专业,且类型ID在有效类型列表中
        majors = db.query(Major).filter(
            Major.isblock == 0,
            Major.typeid.in_(valid_type_ids)
        ).order_by(
            Major.typeid,  # 先按类型排序
            Major.cc,      # 再按层次排序
            Major.orderid  # 最后按显示顺序排序
        ).all()

        # 组织数据结构：类型 → 层次 → 专业
        result = {}
        for major in majors:
            type_id = major.typeid
            if not type_id or type_id not in valid_type_ids:
                continue
                
            level = major.cc  # 层次
            
            # 如果类型不存在，创建新类型
            if type_id not in result:
                result[type_id] = {
                    'id': type_id,
                    'name': type_names.get(type_id, f'类别{type_id}'),
                    'levels': {}  # 该类型下的层次
                }
            
            # 如果层次不存在，创建新层次
            if level not in result[type_id]['levels']:
                result[type_id]['levels'][level] = {
                    'name': level,
                    'majors': []  # 该层次下的专业列表
                }
            
            # 添加专业信息
            result[type_id]['levels'][level]['majors'].append({
                'id': major.id,
                'name': major.mc,
                'tuition': major.xf_1 if major.xf_1 else 0,  
                'books': major.sf_1 if major.sf_1 else 0
            })

        # 转换为前端需要的格式,按照oa_zy_type的orderid排序
        formatted_result = []
        for major_type in major_types:
            type_id = major_type.id
            
            # 如果该类型下有专业数据
            if type_id in result:
                type_data = result[type_id]
                levels_list = []
                
                # 将层次字典转换为列表
                for level_name in type_data['levels']:
                    level_data = type_data['levels'][level_name]
                    levels_list.append({
                        'name': level_data['name'],
                        'majors': level_data['majors']
                    })
                
                # 添加类型数据
                formatted_result.append({
                    'id': type_data['id'],
                    'name': type_data['name'],
                    'levels': levels_list
                })
            else:
                # 如果该类型下没有专业,也返回该类型,但levels为空数组
                formatted_result.append({
                    'id': major_type.id,
                    'name': major_type.mc,
                    'levels': []
                })

        return {
            'success': True,
            'msg': '获取成功',
            'data': formatted_result
        }

    except Exception as e:
        logging.error(f"获取专业信息异常: {str(e)}")
        return {
            'success': False,
            'msg': f'获取专业信息失败: {str(e)}',
            'data': None
        }


# 更新专业费用
@router.post('/update_major_fees')
async def update_major_fees(request: UpdateMajorFeesRequest, db: Session = DatabaseDep):
    try:
        major = db.query(Major).filter(Major.id == request.major_id).first()
        
        if not major:
            return {
                'success': False,
                'msg': '专业不存在',
                'data': None
            }
        
        major.xf_1 = request.tuition
        major.sf_1 = request.books
        db.commit()
        
        return {
            'success': True,
            'msg': '更新成功',
            'data': {
                'id': major.id,
                'name': major.mc,
                'tuition': major.xf_1,
                'books': major.sf_1
            }
        }
    except Exception as e:
        db.rollback()
        logging.error(f"更新专业费用异常: {str(e)}")
        return {
            'success': False,
            'msg': f'更新失败: {str(e)}',
            'data': None
        }


# 创建新生缴费订单
@router.post('/freshman_prePay')
async def create_payment(payment_request: PaymentRequest,db: Session = DatabaseDep):
    try:
        print('payment_request',payment_request)
        # 验证必要参数
        if not payment_request.name:
            return {
                'success': False,
                'msg': '缺少参数: name',
                'data': None
            }
        if not payment_request.id_card:
            return {
                'success': False,
                'msg': '缺少参数: id_card',
                'data': None
            }
        if not payment_request.phone:
            return {
                'success': False,
                'msg': '缺少参数: phone',
                'data': None
            }
        if not payment_request.major_id:
            return {
                'success': False,
                'msg': '缺少参数: major_id',
                'data': None
            }
        if not payment_request.code:
            return {
                'success': False,
                'msg': '缺少参数: code',
                'data': None
            }
        if not payment_request.area:
            return {
                'success': False,
                'msg': '缺少参数: area',
                'data': None
            }
            
        # 查询该身份证号的所有缴费记录,按时间倒序排列

        sys_info = db.query(lw_sys).filter_by(id=1).first()
        # 判断是否超过缴费截止时间
        if sys_info.sys_xs_jf and datetime.now() > sys_info.sys_xs_jf:
            return {
                'success': False,
                'msg': '已超过缴费截止时间',
                'data': None
            }


        # 先检查是否存在历史订单，没有则先创建订单
        history_order = db.query(wxxs_xf_payinfo).filter(
            wxxs_xf_payinfo.o_sfzh == payment_request.id_card,
            wxxs_xf_payinfo.o_pc == sys_info.sys_xsbm_pc,
            wxxs_xf_payinfo.o_close == 0,
            wxxs_xf_payinfo.o_tk_status == 0,
            wxxs_xf_payinfo.o_delete == 0,
            or_(
                wxxs_xf_payinfo.o_xh == None,
                wxxs_xf_payinfo.o_xh == ''
            )
        ).first()


        wx_pay = WxPayUtil()
        if not history_order:
            # 生成订单号（年月日时分秒+随机数）
            order_no = f"KD-XSJF{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(1000, 9999)}"
            # 查询专业信息
            major = db.query(Major).filter_by(id=payment_request.major_id,isblock=0).first()
            if not major:
                return {
                    'success': False,
                    'msg': '专业信息不存在',
                    'data': None
                }

            


            # 重新计算书费，需要根据分校来
            sf = get_area_book_fee(payment_request.area, payment_request.major_id, major.sf_1)


            try:
                # 创建订单
                to_pay_order = wxxs_xf_payinfo(
                    o_xm=payment_request.name,
                    o_sfzh=payment_request.id_card,
                    o_zyid=payment_request.major_id,
                    o_sj=payment_request.phone,
                    o_body=f'黔东南开放大学-新生报名费-{payment_request.name}-JSAPIX',
                    o_money=major.xf_1 * 100 + sf * 100,  # 总金额(分) - 使用重新计算的书费
                    o_xf=major.xf_1 * 100,  # 学费(分)
                    o_sf=sf * 100,    # 书费(分) - 使用重新计算的书费
                    o_jm=0,  # 减免金额
                    o_paytype='weixin',  # 固定使用微信支付
                    o_type=5,  # 5表示微信小程序支付
                    o_status=0,  # 0表示未支付
                    o_tk_status=0,  # 0表示未退款
                    o_close=0,  # 0表示未关闭
                    o_xx_status=0,  # 0表示未下发
                    o_xxtk_status=0,  # 0表示未退款
                    o_order_no=order_no,  # 订单号限制30字符
                    o_addtime=datetime.now(),
                    o_pc=sys_info.sys_xsbm_pc,  # 批次
                    o_isxs=AREA_CODE_MAP.get(payment_request.area, 0),  # 地区编码
                    o_delete=0,  # 0表示未删除
                    o_ip=''
                )
                # 保存订单
                db.add(to_pay_order)
                db.commit()
                
                # 生成查询码并短信通知
                try:
                    from utils.query_code import generate_unique_query_code, get_query_code_expire_time
                    query_code = generate_unique_query_code(db, 'wxxs_xf_payinfo')
                    to_pay_order.query_code = query_code
                    to_pay_order.query_code_expire = get_query_code_expire_time()
                    db.commit()
                    
                    from utils.sms import SMSTool
                    sms_tool = SMSTool()
                    sms_tool.send_by_scenario(
                        scenario='query_code',
                        mobile=payment_request.phone,
                        values={
                            'name': payment_request.name,
                            'query_code': query_code,
                            'biz_name': '新生缴费订单',
                        },
                        xs_xm=payment_request.name,
                    )
                except Exception as qc_err:
                    logging.warning(f'订单创建成功但查询码生成/短信发送失败: {qc_err}')
            except Exception as e:
                db.rollback()
                logging.error(f"创建订单异常: {str(e)}")
                return {
                    'success': False,
                    'msg': f'创建订单失败: {str(e)}',
                    'data': None    
                }
        else:
            to_pay_order = history_order
        



        # 如果订单已经支付，则直接返回
        if to_pay_order.o_status == 1 and to_pay_order.o_trade_no:
            return {
                'success': False,
                'msg': '您已经缴纳过该专业的费用，无需重复缴纳',
                'data': None
            }
        
        if to_pay_order.o_status == 0 and to_pay_order.o_trade_no:
            # 查询订单状态，看看是否已经支付
            pay_result = wx_pay.query_order(to_pay_order.o_order_no)
            # 检查查询结果是否成功，并且订单状态为成功
            if  pay_result.get('success'):
                # 因为各种原因延迟支付，但是支付成功，更新订单状态
                to_pay_order.o_status = '1'
                to_pay_order.o_trade_no = pay_result['transaction_id']
                to_pay_order.o_paytime = pay_result['success_time']
                db.commit()
                return {
                    'success': True,
                    'msg':'您已经缴纳过该专业的费用，无需重复缴纳',
                    'data':None
                }

        if history_order and history_order.o_zyid != payment_request.major_id:
            return {
                'success': False,
                'msg': '您更换了专业报名，费用可能发生变化，请联系招生办老师修改订单。',
                'data': None
            }

        # 向微信服务器获取openid
        wx_openid_result = WxUtils.get_openid_and_session_key(payment_request.code)
        if not wx_openid_result:
            return {
                'success': False,
                'msg': '获取openid失败',
                'data': None
            }
        openid = wx_openid_result['openid']
        # 生成支付参数,说明：out_trade_no和total_fee和历史订单的o_money一致，则说明该订单已经支付过了。
        pay_result = wx_pay.create_pay_info(
            openid = openid,
            out_trade_no = to_pay_order.o_order_no,
            total_fee = to_pay_order.o_money,      #to_pay_order.o_money
            description = to_pay_order.o_body,
            business_type='wxxs_xf_payinfo'
        )
        
        # 需要同时判断请求状态和业务状态来确定返回的参数
        if pay_result.get('success'):
            return {
                'success': True,
                'msg': '创建支付订单成功',
                'data': pay_result['pay_params']
            }
        else:
            if pay_result.get('req_code'):
                return {
                    'success': False,
                    'msg': pay_result['req_des']+':'+pay_result['error_code']+':'+pay_result['error_desc'],
                    'data': None
                }
            else:
                return {
                    'success': False,
                    'msg': pay_result['req_des']+':'+pay_result['error_code']+':'+pay_result['error_desc'],
                    'data': None
                }
    except Exception as e:
        logging.error(f"创建支付订单异常: {e}")
        return {
            'success': False,
            'msg': f'创建支付订单失败: {str(e)}',
            'data': None
        }


# 更新订单支付状态
@router.post('/update_pay_status')
async def update_pay_status(  update_request: UpdatePayStatusRequest,  db: Session = DatabaseDep):
    try:
        order_no = update_request.orderNo

        if not order_no:
            return {
                'success': False,
                'msg': '缺少订单号',
                'data': None
            }
        
        # 查询订单
        to_update_payment = db.query(wxxs_xf_payinfo).filter_by(o_order_no=order_no).first()
        if not to_update_payment:
            return {
                'success': False,
                'msg': '订单不存在',
                'data': None
            }
        # 查询订单状态，看看是否已经支付
        wx_pay = WxPayUtil()
        pay_result = wx_pay.query_order(order_no)
        # 检查查询结果是否成功，并且订单状态为成功
        if  pay_result.get('success'):
            # 因为各种原因延迟支付，但是支付成功，更新订单状态
            to_update_payment.o_status = '1'
            to_update_payment.o_trade_no = pay_result['transaction_id']
            to_update_payment.o_paytime = pay_result['success_time']
            db.commit()
            return {
                'success': True,
                'msg':'缴费成功',
                'data':None
            }
        else:
            return {
                'success': False,
                'msg': pay_result['req_des']+':'+pay_result['trade_state']+':'+pay_result['trade_state_desc'],
                'data': None
            }
    except Exception as e:
        return {
            'success': False,
            'msg': f'更新订单状态失败: {str(e)}',
            'data': None
        }
