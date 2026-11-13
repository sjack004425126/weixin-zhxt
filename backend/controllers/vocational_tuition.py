from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from models.models import ZzBj, Class, WxPayinfo, ZzBmxs, ZzSys,ZzXs,ZzBjZdgr,ZzXsZd,ZzBjZd
from init.dependencies import (
    get_redis, get_db,
    RedisDep, DatabaseDep, RedisManagerDep
)
from common.auth import verify_token_and_get_payload, verify_token_only
from datetime import datetime
from sqlalchemy import null, text
import random
import secrets
import hashlib
from typing import Optional
from init.redis_manager import redis_manager
from utils import wx_pay
from utils.wx_pay import WxPayUtil
import json
from utils.system_config import SystemConfig
import logging
import time
from utils.wx_utils import WxUtils
import requests

# 创建路由器
router = APIRouter(prefix="/vocational_tuition", tags=["职业教育学费"])

# 创建学生信息路由器
info_router = APIRouter(prefix="/vocational_info", tags=["职业教育学生信息"])

# 请求模型
class PaymentRequest(BaseModel):
    idNumber: str
    openid_code: str

class UpdatePayStatusRequest(BaseModel):
    orderNo: str

class OldStudentPaymentRequest(BaseModel):
    openid_code: str


class PhoneVerifyRequest(BaseModel):
    """手机号验证请求体"""
    code: str          # 小程序 getPhoneNumber 返回的 code
    role: str          # 'self' = 本人手机号验证；'parent' = 家长手机号验证
    openid_code: str = ''  # 预留，目前未使用
    # 7 天手机号缓存：可选字段；前端 wx.login() 返回的 code
    login_code: str = ''






# 检查报名信息，支付信息。
@router.get('/new-student-checkPayment')
async def get_payment_info(
    queryCode: Optional[str] = None,
    idNumber: Optional[str] = None,
    verify_token: Optional[str] = None,
    db: Session = DatabaseDep,
):
    """
    新生缴费信息查询。
    - 模式 A (查询码): 仅 queryCode。不需手机号验证。
    - 模式 B (手机号验证): verify_token（来自 verify_phone_for_payment，无需再传身份证号）
    """
    sys_info = db.query(ZzSys).first()
    current_nd = sys_info.zz_xsjf_nd

    # === 模式 A：查询码 ===
    if queryCode:
        query_code = queryCode.strip()
        if not query_code:
            return {'success': False, 'msg': '缺少查询码', 'data': None}
        student_xs = (
            db.query(ZzXs)
            .filter_by(query_code=query_code, nd=current_nd)
            .first()
        )
        if not student_xs:
            return {
                'success': False,
                'msg': '查询码无效或已过期',
                'data': None,
            }
        # 检查是否已完成报名（is_complete=0 草稿不允许查看/缴费）
        if not student_xs.is_complete:
            return {
                'success': False,
                'msg': '您还没有完善报名信息，请到报名页面完善报名信息',
                'data': None,
            }
        idNumber = student_xs.sfzh
    else:
        # === 模式 B：手机号验证（verify_token 内部已绑定身份证号）===
        if not verify_token:
            return {
                'success': False,
                'msg': '请先通过微信手机号验证身份',
                'data': None,
            }
        token_payload = _get_verify_token_payload(verify_token)
        if not token_payload or not token_payload.get('id_number'):
            return {
                'success': False,
                'msg': '身份验证已过期，请重新验证',
                'data': None,
            }
        idNumber = token_payload['id_number']
        student_xs = db.query(ZzXs).filter_by(sfzh=idNumber, nd=current_nd).first()
        # 检查是否已完成报名（is_complete=0 草稿不允许查看/缴费）
        if student_xs and not student_xs.is_complete:
            return {
                'success': False,
                'msg': '您还没有完善报名信息，请到报名页面完善报名信息',
                'data': None,
            }

    if not student_xs:
        return {
            'success': False,
            'msg': '您还没有报名，请检查您的身份证号码是否正确。',
            'data': None
        }

    # 查询专业信息
    sql = text("""
        select *
        from zz_bmxs_cooperation_schoolmajor as a
        left join zz_bmxs_local_major b on a.local_major_id=b.id
        where a.id=:cooperation_schoolmajor_id
    """)

    result = db.execute(sql, {'cooperation_schoolmajor_id': student_xs.cooperation_schoolmajor_id}).first()
    zsf = result.zsf
    sf = result.sf
    xf = result.xf
    zyxx ={
        'xm':student_xs.xm,
        'major_name':result.major_name,
        'cooperation_school':result.cooperation_school,
        'cooperation_major':result.cooperation_major,
        'remark':result.remark
    }

    pre_payment_info = db.query(WxPayinfo).filter_by(o_sfzh=idNumber,o_nd=sys_info.zz_xsjf_nd,o_xq=sys_info.zz_xsjf_xq,o_tk_status=0,o_close=0).first()
    if pre_payment_info:
        if pre_payment_info.o_status == 0 and pre_payment_info.o_order_no != '':
            # 查询订单状态，看看是否已经支付
            wx_pay = WxPayUtil()
            pay_result = wx_pay.query_order(pre_payment_info.o_order_no)
            # 检查查询结果是否成功，并且订单状态为成功
            if pay_result.get('success'):
                # 因为各种原因延迟支付，但是支付成功，更新订单状态
                pre_payment_info.o_status = '1'
                pre_payment_info.o_paytime = pay_result['success_time']
                pre_payment_info.o_trade_no = pay_result['transaction_id']
                db.commit()


        payorder_xx={
            'o_id':pre_payment_info.o_id,
            'o_sfzh':pre_payment_info.o_sfzh,
            'o_paytype':pre_payment_info.o_paytype,
            'o_payment_time':pre_payment_info.o_paytime,
            'o_trade_no':pre_payment_info.o_trade_no,
            'o_money':pre_payment_info.o_money,
            'o_status':pre_payment_info.o_status
        }
    else:
        payorder_xx=None

    return {
        'success': True,
        'msg':'获取成功',
        'data':{
            'student_name': student_xs.xm or '',
            'zyxx':zyxx,
            'payorder_xx':payorder_xx,
            'jfxx':{
                'zsf':zsf,
                'xf':xf,
                'sf':sf
            }
        }
    }



# 中职新生报名缴费-获取支付参数。检查报名信息，支付信息。获取预支付参数，用于生成微信支付参数，并返回给前端。
@router.get('/get_pre_payment_info')
async def get_pre_payment_info(
    queryCode: Optional[str] = None,
    idNumber: Optional[str] = None,
    openid_code: Optional[str] = None,
    verify_token: Optional[str] = None,
    db: Session = DatabaseDep,
):
    """
    中职新生获取支付参数。
    - queryCode 模式：queryCode + openid_code（无需手机验证）
    - 手机号验证模式：verify_token + openid_code（verify_token 内已绑定身份证号，前端无需再传）
    """
    try:
        sys_info = db.query(ZzSys).first()
        current_nd = sys_info.zz_xsjf_nd

        # === 模式 A：查询码 ===
        if queryCode:
            query_code = queryCode.strip()
            if not query_code or not openid_code:
                return {'success': False, 'msg': '缺少查询码或微信code', 'data': None}
            student_xs = (
                db.query(ZzXs)
                .filter_by(query_code=query_code, nd=current_nd)
                .first()
            )
            if not student_xs:
                return {
                    'success': False,
                    'msg': '查询码无效或已过期',
                    'data': None,
                }
            if not student_xs.is_complete:
                return {
                    'success': False,
                    'msg': '您还没有完善报名信息，请到报名页面完善报名信息',
                    'data': None,
                }
            idNumber = student_xs.sfzh
        else:
            # === 模式 B：手机号验证（verify_token 内部已绑定身份证号）===
            if not openid_code:
                return {
                    'success': False,
                    'msg': '缺少微信code',
                    'data': None,
                }
            if not verify_token:
                return {
                    'success': False,
                    'msg': '请先通过微信手机号验证身份',
                    'data': None,
                }
            token_payload = _get_verify_token_payload(verify_token)
            if not token_payload or not token_payload.get('id_number'):
                return {
                    'success': False,
                    'msg': '身份验证已过期，请重新验证',
                    'data': None,
                }
            idNumber = token_payload['id_number']
            student_xs = (
                db.query(ZzXs)
                .filter_by(sfzh=idNumber, nd=current_nd)
                .first()
            )
            if student_xs and not student_xs.is_complete:
                return {
                    'success': False,
                    'msg': '您还没有完善报名信息，请到报名页面完善报名信息',
                    'data': None,
                }

        if not student_xs:
            return {
                'success': False,
                'msg':'您还没有报名，请检查您的身份证号码是否正确。',
                'data':None
            }

        # 1、先查询未退费，已支付的订单，还要核对是否有订单号，有则说明支付成功，没有则说明支付失败。
        pre_payment_info = db.query(WxPayinfo).filter_by(o_nd=sys_info.zz_xsjf_nd,o_xq=sys_info.zz_xsjf_xq,o_sfzh=idNumber,o_tk_status=0,o_status=1,o_close=0).first()
        if pre_payment_info and pre_payment_info.o_trade_no:
            return {
                'success': False,
                'msg':'您已支付过报名费，无需重复支付',
                'data':None
            }

        wx_pay = WxPayUtil()
        # 2、查询未退费，未支付的订单，如果没有，说明报名的时候没有生成缴费订单，让管理员手工处理，重新生成订单。
        pre_payment_info = db .query(WxPayinfo).filter_by(o_nd=sys_info.zz_xsjf_nd,o_xq=sys_info.zz_xsjf_xq,o_sfzh=idNumber,o_tk_status=0,o_status=0,o_close=0).first()
        if not pre_payment_info:
            try:

                sql = text("""
                    select *
                    from zz_bmxs_cooperation_schoolmajor as a
                    left join zz_bmxs_local_major b on a.local_major_id=b.id
                    where a.id=:cooperation_schoolmajor_id
                """)

                result = db.execute(sql, {'cooperation_schoolmajor_id': student_xs.cooperation_schoolmajor_id}).first()
                zsf = result.zsf
                sf = result.sf
                new_order_no = f"ZZ-XSJF{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(1000, 9999)}"
                # 创建订单
                order = WxPayinfo(
                    o_xm = student_xs.xm,
                    o_xh = '',
                    o_sfzh = idNumber,
                    o_sj = student_xs.xsdh,
                    o_body = "黔东南中等职业技术学校-新生报名费-"+student_xs.xm+"-JSAPIX",
                    o_money = zsf+sf,
                    o_zsf = zsf,
                    o_sf = sf,
                    o_paytype = 'weixin',
                    o_type ='5',
                    o_status = '0',
                    o_tk_status ='0',
                    o_close = '0',
                    o_xx_status = '0',
                    o_order_no = new_order_no,
                    o_trade_no ='',
                    o_addtime = datetime.now(),
                    o_paytime ='',
                    o_nd = sys_info.zz_xsjf_nd,
                    o_xq = sys_info.zz_xsjf_xq,
                    o_delete = '0'
                )
                # 保存订单
                db.add(order)
                db.commit()
                pre_payment_info = order
            except Exception as e:
                db.rollback()
                return {
                    'success': False,
                    'msg': f"订单生成失败: {str(e)}",
                    'data': None
                }


        
        # 4、现在是有本地单号，A、有可能生成微信端单号了，但是因为用户造成的取消或网络原因，未写微信端单号。B、或者还未生成微信端支付订单，现在要去生成生成支付参数，创建微信端订单并返回给前端。单号大概2天内有效，如果2天未支付，则需要管理员来处理。一般是重新生成本地订单号。
        wx_util = WxUtils()
        openidResult = wx_util.get_openid_and_session_key(openid_code)
        if not openidResult:
            return {
                'success': False,
                'msg': '获取openid失败',
                'data': None
            }
        openid = openidResult.get('openid')
        pay_result = wx_pay.create_pay_info(
            openid = openid,
            out_trade_no = pre_payment_info.o_order_no,
            total_fee = pre_payment_info.o_money,
            description=pre_payment_info.o_body
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


# 更新预支付订单状态，用于查询订单状态，如果支付成功，则更新订单状态。
@router.get('/update_pre_payment_order_status')
async def update_pre_payment_order_status(o_order_no:str,db: Session = DatabaseDep):
    if not o_order_no:
        return {
            'success': False,
            'msg': '参数错误',
            'data': None
        }
    
    # 查询订单
    pre_payment_info = db.query(WxPayinfo).filter_by(o_order_no=o_order_no).first()
    if not pre_payment_info:
        return {
            'success': False,
            'msg': '订单不存在',
            'data': None
        }

    # 查询订单状态，看看是否已经支付
    wx_pay = WxPayUtil()
    pay_result = wx_pay.query_order(o_order_no)
    # 检查查询结果是否成功，并且订单状态为成功
    if  pay_result.get('success'):
        # 因为各种原因延迟支付，但是支付成功，更新订单状态
        pre_payment_info.o_status = '1'
        pre_payment_info.o_trade_no = pay_result['transaction_id']
        pre_payment_info.o_paytime = pay_result['success_time']
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


# ==================== 老生缴费相关接口 ====================

# 获取老生缴费订单列表信息
@router.get('/old_student_tuition_info')
async def get_old_student_tuition_info(current_user: dict = Depends(verify_token_and_get_payload), db: Session = DatabaseDep):
    """获取老生缴费信息"""
    try:
        # 查询学生基本信息
        student = db.query(ZzXs).filter(ZzXs.id == current_user.get('xs_id')).first()
        if not student:
            return {
                'success': False,
                'message': '学生信息不存在',
                'data': None
            }

        # 查询系统配置信息
        sys_info = db.query(ZzSys).first()
        if not sys_info:
            return {
                'success': False,
                'message': '系统配置信息不存在',
                'data': None
            }

        # 获取当前学期是否需要缴费及原因
        pay_info = count_old_student_pay_with_reason(current_user.get('xs_id'), db)

        # 计算当前学期的term_number
        current_term_number = get_term_info(student.nd, sys_info.zz_dq_nd, sys_info.zz_dq_xq)

        semester_payments = []
        payment_record = db.query(WxPayinfo).filter_by(
            o_xh = student.xh,
            o_close = 0,
            o_delete = 0,
            o_tk_status = 0
        ).all()
        print(payment_record)

        for payment in payment_record:
            # 将 SQLAlchemy 对象转换为字典
            payment_dict = {
                'o_id': payment.o_id,
                'o_xm': payment.o_xm,
                'o_xh': payment.o_xh,
                'o_sfzh': payment.o_sfzh,
                'o_money': payment.o_money,
                'o_zsf': payment.o_zsf,
                'o_sf': payment.o_sf,
                'o_status': payment.o_status,
                'o_order_no': payment.o_order_no,
                'o_trade_no': payment.o_trade_no,
                'o_paytime': payment.o_paytime,
                'o_addtime': payment.o_addtime,
                'o_nd': payment.o_nd,
                'o_xq': payment.o_xq,
                'term_number': get_term_info(student.nd, payment.o_nd, payment.o_xq)
            }
            semester_payments.append(payment_dict)

        # 将当前学期的缴费信息插入到semester_payments中
        # 查找是否已存在当前学期的记录
        current_term_exists = False
        for sp in semester_payments:
            if sp.get('term_number') == current_term_number:
                # 已有记录，更新缴费信息
                sp['needPay'] = pay_info.get('needPay', False)
                sp['no_pay_reasons'] = pay_info.get('no_pay_reasons', [])
                sp['zsf'] = pay_info.get('zsf', 0)
                sp['sf'] = pay_info.get('sf', 0)
                current_term_exists = True
                break

        # 如果当前学期没有记录，添加新条目
        if not current_term_exists:
            current_term_payment = {
                'term_number': current_term_number,
                'needPay': pay_info.get('needPay', False),
                'no_pay_reasons': pay_info.get('no_pay_reasons', []),
                'zsf': pay_info.get('zsf', 0),
                'sf': pay_info.get('sf', 0)
            }
            semester_payments.append(current_term_payment)

        #测试数据
        # return{
        #     "success": True,
        #     "message": "获取成功",
        #     "data": {
        #         "semester_payments": [
        #             {
        #                 "o_id": 10660,
        #                 "o_xm": "欧阳锦凤",
        #                 "o_xh": "532250962",
        #                 "o_sfzh": "522624200908260149",
        #                 "o_money": 38000,
        #                 "o_zsf": 38000,
        #                 "o_sf": 0,
        #                 "o_status": 1,
        #                 "o_order_no": "202510140904541516",
        #                 "o_trade_no": "4200002850202510143830977815",
        #                 "o_paytime": "20251014090650",
        #                 "o_addtime": "2025-10-14T09:04:54",
        #                 "o_nd": 25,
        #                 "o_xq": "09",
        #                 "term_number": 1
        #             },
        #             {
        #                 "term_number": 2,
        #                 "needPay": True,
        #                 "no_pay_reasons": ["外出实习","建档立卡"],
        #                 "zsf": 38000,
        #                 "sf": 2600,
        #                 "o_id": 10660,
        #                 "o_xm": "欧阳锦凤",
        #                 "o_xh": "532250962",
        #                 "o_sfzh": "522624200908260149",
        #                 "o_money": 40600,
        #                 "o_zsf": 40600,
        #                 "o_sf": 0,
        #                 "o_status": 1,
        #                 "o_order_no": "202510140904541516",
        #                 "o_trade_no": "4200002850202510143830977815",
        #                 "o_paytime": "20251014090650",
        #                 "o_addtime": "2025-10-14T09:04:54",
        #                 "o_nd": 26,
        #                 "o_xq": "03",
        #                 "term_number": 2
        #             }
        #         ]
        #     }
        # }

        return {
            'success': True,
            'message': '获取成功',
            'data': {
                "semester_payments":semester_payments,
                "needPay": pay_info.get('needPay', False),
                "no_pay_reasons": pay_info.get('no_pay_reasons', [])
            }
        }

    except Exception as e:
        return {
            'success': False,
            'message': f'获取缴费确认信息失败: {str(e)}',
            'data': None
        }


# 获取老生预支付订单确认页面信息
@router.get('/get_old_student_pre_payment')
async def create_old_student_pre_payment(current_user: dict = Depends(verify_token_and_get_payload), db: Session = DatabaseDep):
    """获取老生预支付订单确认页面信息"""
    try:
        # 查询系统配置信息
        sys_info = db.query(ZzSys).first()
        if not sys_info:
            return {
                'success': False,
                'message': '系统配置信息不存在',
                'data': None
            }

        # 判断是否在缴费时间
        now = datetime.now()
        if not (sys_info.zz_lsjfksrq <= now <= sys_info.zz_lsjfjzrq):
            if now < sys_info.zz_lsjfksrq:
                return {
                    'success': False,
                    'message': '缴费未开始',
                    'data': None
                }
            else:
                return {
                    'success': False,
                    'message': '缴费已结束',
                    'data': None
                }

        count_result = count_old_student_pay_with_reason(current_user.get('xs_id'), db)

        # 如果账单检查失败（如无账单/账单未开启等），也透传到外层
        if not count_result.get('success', True):
            return {
                'success': False,
                'message': count_result.get('message', '无法获取缴费信息'),
                'data': count_result
            }

        return {
            'success': True,
            'message': "获取成功",
            'data': count_result
        }

    except Exception as e:
        return {
            'success': False,
            'message': f'查询缴费信息失败: {str(e)}',
            'data': None
        }



# 创建老生预支付订单确认页面信息
@router.get('/create_old_student_pre_payment')
async def create_old_student_pre_payment(openid_code: str,current_user: dict = Depends(verify_token_and_get_payload), db: Session = DatabaseDep):
    """创建老生预支付订单"""
    try:
        # 查询系统配置信息
        sys_info = db.query(ZzSys).first()
        student = db.query(ZzXs).filter_by(id=current_user.get('xs_id')).first()

        # 1. 先检查是否需要支付
        count_result = count_old_student_pay_with_reason(current_user.get('xs_id'), db)
        if not count_result['needPay']:
            return {
                'success': True,
                'message': '无需缴费',
                'data': None
            }

        # 2. 查询是否存在未支付的订单（状态为0）
        # 否则每次都会认为不存在未支付订单，导致重复生成订单记录。
        to_payment = db.query(WxPayinfo).filter_by(
            o_xh=current_user.get('xs_xh'),
            o_nd=sys_info.zz_dq_nd,
            o_xq=sys_info.zz_dq_xq,
            o_status=0,
            o_close=0,
            o_delete=0,
            o_tk_status=0
        ).first()

        wx_pay = WxPayUtil()

        # 获取openid（后面需要用到）
        wx_util = WxUtils()
        openidResult = wx_util.get_openid_and_session_key(openid_code)
        if not openidResult:
            return {
                'success': False,
                'message': '获取openid失败',
                'data': None
            }
        openid = openidResult.get('openid')

        # 3. 如果没有未支付订单，创建新订单
        if not to_payment:
            new_order_no = f"ZZ-LSJF{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(1000, 9999)}"
            order = WxPayinfo(
                o_xm=student.xm,
                o_xh=student.xh,
                o_sfzh=student.sfzh,
                o_sj=student.xsdh,
                o_body=f'黔东南中等职业技术学校-老生缴纳{sys_info.zz_dq_nd}年{sys_info.zz_dq_xq}学期学费-{student.xm}-JSAPIX',
                o_money=count_result['zsf']+count_result['sf'],
                o_zsf=count_result['zsf'],
                o_sf=count_result['sf'],
                o_paytype='weixin',
                o_type=5,
                o_status=0,
                o_tk_status=0,
                o_close=0,
                o_delete=0,
                o_xx_status=0,
                o_order_no=new_order_no,
                o_addtime=datetime.now(),
                o_nd=sys_info.zz_dq_nd,
                o_xq=sys_info.zz_dq_xq
            )
            db.add(order)
            db.commit()
            to_payment = order

        # 4. 检查订单是否已经支付成功
        wx_pay_result = wx_pay.query_order(to_payment.o_order_no)
        if wx_pay_result.get('success'):
            to_payment.o_status = 1
            to_payment.o_trade_no = wx_pay_result['transaction_id']
            to_payment.o_paytime = wx_pay_result['success_time']
            db.commit()
            return {
                'success': True,
                'message': '订单已经支付成功',
                'data': None
            }

        # 5. 未支付，检查是否需要重新下单
        # 检查 prepay_id 是否存在且在2小时内有效
        need_recreate = False
        if to_payment.prepay_id:
            # prepay_id 有效期2小时（7200秒）
            if to_payment.o_addtime:
                seconds_passed = (datetime.now() - to_payment.o_addtime).total_seconds()
                if seconds_passed > 7000:
                    need_recreate = True

        if need_recreate:
            # 5.1 关闭原订单
            wx_pay.close_order(to_payment.o_order_no)
            # 5.2 将原订单标记为关闭
            to_payment.o_close = 1
            db.commit()

            # 5.3 创建新订单
            new_order_no = f"ZZ-LSJF{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(1000, 9999)}"
            new_order = WxPayinfo(
                o_xm=student.xm,
                o_xh=student.xh,
                o_sfzh=student.sfzh,
                o_sj=student.xsdh,
                o_body=f'黔东南中等职业技术学校-老生缴纳{sys_info.zz_dq_nd}年{sys_info.zz_dq_xq}学期学费-{student.xm}-JSAPIX',
                o_money=count_result['zsf']+count_result['sf'],
                o_zsf=count_result['zsf'],
                o_sf=count_result['sf'],
                o_paytype='weixin',
                o_type=5,
                o_status=0,
                o_tk_status=0,
                o_close=0,
                o_delete=0,
                o_xx_status=0,
                o_order_no=new_order_no,
                o_addtime=datetime.now(),
                o_nd=sys_info.zz_dq_nd,
                o_xq=sys_info.zz_dq_xq
            )
            db.add(new_order)
            db.commit()
            to_payment = new_order

        # 6. 返回支付参数
        # 6.1 如果已有 prepay_id，直接使用
        if to_payment.prepay_id:
            pay_params_result = wx_pay.get_pay_params_by_prepay_id(to_payment.prepay_id)
            if pay_params_result.get('success'):
                return {
                    'success': True,
                    'msg': '创建支付订单成功',
                    'data': pay_params_result['pay_params']
                }
            # 如果获取失败，继续走创建流程

        # 6.2 没有 prepay_id ，创建新支付信息
        pay_result = wx_pay.create_pay_info(
            openid=openid,
            out_trade_no=to_payment.o_order_no,
            total_fee=to_payment.o_money,
            description=to_payment.o_body,
            business_type='wx_payinfo'
        )

        if pay_result.get('success'):
            # 保存 prepay_id 到订单记录
            to_payment.prepay_id = pay_result.get('prepay_id')
            db.commit()

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
        return {
            'success': False,
            'message': f'查询系统配置信息失败: {str(e)}',
            'data': None
        }



# 通过账单计算是否需要缴费（带原因）
def count_old_student_pay_with_reason(xs_id, db: Session = DatabaseDep):
    sys_info = db.query(ZzSys).first()
    student = db.query(ZzXs).filter_by(id=xs_id).first()
    zsf = sf = 0
    no_pay_reasons = []

    zz_zd_bj = db.query(ZzBjZd).filter_by(bjid=student.bj_id, nd=sys_info.zz_dq_nd, xq=sys_info.zz_dq_xq).first()
    zz_zd_gr = db.query(ZzBjZdgr).filter_by(xsxh=student.xh, nd=sys_info.zz_dq_nd, xq=sys_info.zz_dq_xq).first()

    if not zz_zd_gr:
        if not zz_zd_bj:
            return {
                'success': False,
                'message': '账单错误',
                'needPay': False,
                'zsf': 0,
                'sf': 0,
                'no_pay_reasons': ['未找到本学期账单，请联系学校管理员']
            }
        else:
            if zz_zd_bj.isopen == 0:
                return {
                    'success': False,
                    'message': '班级账单未开启',
                    'needPay': False,
                    'zsf': 0,
                    'sf': 0,
                    'no_pay_reasons': ['本学期缴费通道尚未开启，请耐心等待']
                }
            if zz_zd_bj.wcsx == 1:
                return {
                    'success': False,
                    'message': '外出实习学生无需缴费',
                    'needPay': False,
                    'zsf': 0,
                    'sf': 0,
                    'no_pay_reasons': ['您已标记为外出实习，本学期无需缴费']
                }
            zsf = zz_zd_bj.zsf
            sf = zz_zd_bj.sf
            if zz_zd_bj.isjdlk == 0 and student.sfjdlk == 1:
                zsf = 0
                sf = 0
                no_pay_reasons.append('建档立卡学生免缴学费')

            zz_zd = db.query(ZzXsZd).filter_by(xsid=student.id, nd=sys_info.zz_dq_nd, xq=sys_info.zz_dq_xq).first()
            if zz_zd:
                zsf = 0
                no_pay_reasons.append('走读学生免缴住宿费')
    else:
        zsf = zz_zd_gr.zsf
        sf = zz_zd_gr.sf


    needPay = (zsf + sf) > 0
    if not needPay and not no_pay_reasons:
        no_pay_reasons.append('当前学期无应缴费用')

    return {
        'needPay': needPay,
        'zsf': zsf,
        'sf': sf,
        'no_pay_reasons': no_pay_reasons if not needPay else []
    }

# 更新老生订单状态
@router.get('/update_old_student_order_status')
async def update_old_student_order_status(current_user: dict = Depends(verify_token_and_get_payload), db: Session = DatabaseDep):
    """更新老生订单状态"""
    try:

        # 查询系统配置信息
        sys_info = db.query(ZzSys).first()
        if not sys_info:
            return {
                'success': False,
                'message': '系统配置信息不存在',
                'data': None
            }

        # 查询未支付的订单
        to_update_payment = db.query(WxPayinfo).filter(
            WxPayinfo.o_xh == current_user.get('xs_xh'),
            WxPayinfo.o_nd == sys_info.zz_dq_nd,
            WxPayinfo.o_xq == sys_info.zz_dq_xq,
            WxPayinfo.o_close == 0,
            WxPayinfo.o_tk_status == 0,
            WxPayinfo.o_delete == 0
        ).first()

        if not to_update_payment:
            return {
                'success': False,
                'message': '未找到待支付订单',
                'data': None
            }
        if to_update_payment.o_status == 1:
            return {
                'success': True,
                'message': '订单已经支付成功',
                'data': None
            }
        # 查询微信支付订单状态
        wx_pay = WxPayUtil()
        pay_result = wx_pay.query_order(to_update_payment.o_order_no)

        if pay_result.get('success'):
            # 支付成功，更新订单状态
            to_update_payment.o_status = '1'
            to_update_payment.o_trade_no = pay_result['transaction_id']
            to_update_payment.o_paytime = pay_result['success_time']
            db.commit()
            return {
                'success': True,
                'message': '订单状态更新成功',
                'data': None
            }
        else:
            return {
                'success': False,
                'message': f"订单未支付: {pay_result.get('trade_state_desc', '未知状态')}",
                'data': None
            }

    except Exception as e:
        return {
            'success': False,
            'message': f'更新订单状态失败: {str(e)}',
            'data': None
        }




# 获取学期描述
def get_term_info(s_nd, sys_nd, sys_xq):
    """
    根据学生入学年度和系统当前年度、学期计算学期描述
    学生默认9月入学，'03'表示3月学期，'09'表示9月学期
    学期数最小为1，最大不限制（支持已毕业、留级等情况）
    """
    # 参数验证
    if s_nd is None or sys_nd is None or sys_xq is None:
        return 1  # 参数缺失时返回第1学期

    try:
        s_nd = int(s_nd)
        sys_nd = int(sys_nd)
    except (ValueError, TypeError):
        return 1  # 转换失败时返回第1学期

    if not isinstance(sys_xq, str):
        return 1  # 学期参数类型错误时返回第1学期

    # 验证学期代码
    valid_terms = ['03', '09']
    if sys_xq not in valid_terms:
        return 1  # 学期代码无效时返回第1学期

    # 计算年度差
    year_diff = sys_nd - s_nd

    # 如果年度差为负数（系统年度小于入学年度），返回第1学期
    if year_diff < 0:
        return 1

    # 学生9月入学，如果是入学当年的3月学期，学生还没入学，返回第1学期
    if year_diff == 0 and sys_xq == '03':
        return 1

    # 计算学期数
    # 每年有2个学期：3月学期和9月学期
    # 学生9月入学算第1学期，次年3月算第2学期，次年9月算第3学期...
    if year_diff == 0:  # 入学当年
        if sys_xq == '09':
            term_info = 1
        else:  # sys_xq == '03'
            term_info = 1  # 入学当年3月还未入学，返回1
    else:
        # 计算学期数：年度差 * 2 + (3月为偶数学期，9月为奇数学期)
        if sys_xq == '03':
            term_info = year_diff * 2
        else:  # sys_xq == '09'
            term_info = year_diff * 2 + 1

    # 只限制最小值为1，最大值不限制
    term_info = max(1, term_info)

    return term_info


# ============================================================
# 中职新生缴费 - 手机号验证
# ============================================================

VERIFY_TOKEN_TTL_SECONDS = 10 * 60  # 10 分钟
VERIFY_TOKEN_PREFIX = 'vocational_tuition:verify_token:'


def _issue_verify_token(id_number: str, role: str) -> str:
    """
    生成 verify_token，写 redis，返回 token 字符串。
    配套提供 _verify_token_matches 进行核验。
    """
    raw = secrets.token_urlsafe(24)
    payload = {
        'id_number': id_number,
        'role': role,
        'issued_at': datetime.utcnow().isoformat(),
    }
    redis_manager.set(
        VERIFY_TOKEN_PREFIX + raw,
        payload,
        ex=VERIFY_TOKEN_TTL_SECONDS,
    )
    return raw


def _verify_token_matches(token: str, id_number: str) -> bool:
    """
    校验 token 是否存在、未过期，且对应的 id_number 一致。
    返回 True/False。
    """
    if not token or not id_number:
        return False
    payload = _get_verify_token_payload(token)
    if not payload:
        return False
    return payload.get('id_number') == id_number


def _get_verify_token_payload(token: str):
    """
    读取 token 在 redis 中的 payload，若不存在/已过期/格式异常则返回 None。
    """
    if not token:
        return None
    key = VERIFY_TOKEN_PREFIX + token
    try:
        payload = redis_manager.get(key)
    except Exception:
        return None
    if not payload or not isinstance(payload, dict):
        return None
    return payload


def _mask_phone(phone: str) -> str:
    """13800001234 -> 138****1234"""
    if not phone or len(phone) < 7:
        return phone or ''
    return phone[:3] + '****' + phone[-4:]


@router.post('/verify_phone_for_payment')
async def verify_phone_for_payment(
    payload: PhoneVerifyRequest,
    db: Session = DatabaseDep,
    redis_client=RedisDep,
):
    """
    中职新生缴费 - 微信手机号快捷身份认证

    1. 根据 role 解出微信绑定的手机号
    2. 在 ZzXs 中按 xsdh（本人）或 jzdh（家长）反查报名记录
    3. 找到唯一一条报名记录则签发 verify_token (15 分钟，与 zzbm 编辑模式 token 同源)，返给前端
    """
    code = (payload.code or '').strip()
    role = (payload.role or 'self').strip().lower()

    if not code:
        return {
            'success': False,
            'msg': '请完成微信手机号验证',
            'data': None,
        }
    if role not in ('self', 'parent'):
        return {
            'success': False,
            'msg': 'role 参数错误，只能是 self 或 parent',
            'data': None,
        }

    # 解微信手机号
    wx_result = WxUtils.get_phone_number(code)
    if not wx_result or not wx_result.get('phone_info'):
        return {
            'success': False,
            'msg': '微信手机号获取失败，请重试',
            'data': None,
        }
    phone_info = wx_result['phone_info']
    wx_phone = phone_info.get('phoneNumber') or phone_info.get('purePhoneNumber') or ''
    if not wx_phone:
        return {
            'success': False,
            'msg': '微信未返回手机号信息',
            'data': None,
        }

    # 归一化手机号
    wx_norm = wx_phone.strip().replace(' ', '')
    if wx_norm.startswith('+86'):
        wx_norm = wx_norm[3:]

    sys_info = db.query(ZzSys).first()
    current_nd = sys_info.zz_xsjf_nd

    # 根据 role 在 ZzXs 中按手机号反查
    phone_col = ZzXs.xsdh if role == 'self' else ZzXs.jzdh
    label = '本人手机号' if role == 'self' else '家长手机号'

    candidates = (
        db.query(ZzXs)
        .filter(phone_col == wx_norm)
        .filter(ZzXs.nd == current_nd)
        .all()
    )
    if not candidates:
        # 兼容手机号列中带空格/换行的存储
        candidates = (
            db.query(ZzXs)
            .filter(phone_col.like(f'%{wx_norm}%'))
            .filter(ZzXs.nd == current_nd)
            .all()
        )
    # 进一步精确匹配（去空格后比较）
    matched = []
    for c in candidates:
        stored = (getattr(c, 'xsdh' if role == 'self' else 'jzdh') or '').strip().replace(' ', '')
        if stored.startswith('+86'):
            stored = stored[3:]
        if stored == wx_norm:
            matched.append(c)

    if not matched:
        return {
            'success': False,
            'msg': f'未查询到使用该{label}的报名信息',
            'data': None,
        }
    if len(matched) > 1:
        return {
            'success': False,
            'msg': f'该{label}对应多条报名记录，请联系学校核实',
            'data': None,
        }

    student_xs = matched[0]
    # 签发 token，token 内绑定身份证号（仅用于后端接口定位学生，不再要求前端传入）
    verify_token = _issue_verify_token(student_xs.sfzh, role)
    print(f'[verify_phone_for_payment] 业务 token 签发完成 sfzh={student_xs.sfzh} role={role}')

    # 同时写一份到 zzbm 编辑模式使用的 redis key，
    # 让 wxbm 弹窗（手机号快捷认证）拿到的 token 可以直接调 get_enrollment_detail_by_sfzh
    try:
        redis_client.setex(
            f"zzbm:enroll_verify:passport:{student_xs.sfzh}",
            900,
            verify_token,
        )
    except Exception as cross_err:
        print(f'[verify_phone_for_payment] 同步 token 到 zzbm redis 失败: {cross_err}')

    # 7 天手机号缓存写入（前端可选择传 login_code，缓存命中后下次可走 /auth/get_cached_verify）
    cache_written = False
    try:
        from common import phone_cache as _phone_cache
        if payload.login_code:
            print(f'[verify_phone_for_payment] 收到 login_code，开始换 openid 并写 7 天缓存')
            openid = _phone_cache.resolve_openid_by_login_code(payload.login_code)
            if openid:
                cache_written = _phone_cache.write_phone_cache(
                    openid=openid,
                    pure_phone=wx_norm,
                    role=role,
                    subject=_phone_cache.SUBJECT_VOCATIONAL_PAYMENT,
                    extra={
                        'masked_phone': _mask_phone(wx_phone),
                        'sfzh': student_xs.sfzh,
                        'xm': student_xs.xm,
                    },
                )
                print(f'[verify_phone_for_payment] phone_cache 写入结果={cache_written} '
                      f'openid={openid[:8]}*** subject={_phone_cache.SUBJECT_VOCATIONAL_PAYMENT} '
                      f'pure_phone={wx_norm} role={role}')
            else:
                print(f'[verify_phone_for_payment] login_code 换 openid 失败，跳过缓存写入')
        else:
            print(f'[verify_phone_for_payment] 未传 login_code，跳过 7 天缓存写入（兼容老前端）')
    except Exception as _e:
        print(f'[verify_phone_for_payment] 写 phone_cache 失败: {_e}')

    return {
        'success': True,
        'msg': '验证通过',
        'data': {
            'verify_token': verify_token,
            'masked_phone': _mask_phone(wx_phone),
            'expires_in': VERIFY_TOKEN_TTL_SECONDS,
            'student_name': student_xs.xm,
            'sfzh': student_xs.sfzh,
            'cache_written': cache_written,
        },
    }
