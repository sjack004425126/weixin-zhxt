from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from models.models import WxXwyyPayinfo, lw_sys, Student, DegreeEnglishRegistration
from init.dependencies import get_redis, get_db,RedisDep, DatabaseDep, RedisManagerDep
from common.auth import verify_token_and_get_payload
from datetime import datetime
from sqlalchemy import false, text
import random
from utils.wx_utils import WxUtils
from utils.wx_pay import WxPayUtil

# 创建路由器
router = APIRouter(prefix="/degree", tags=["学位英语"])

# 请求模型
class CreateOrderRequest(BaseModel):
    openid_code: str

class PrepayRequest(BaseModel):
    order_no: str
    openid_code: str

class UpdateOrderRequest(BaseModel):
    order_no: str

@router.get('/degree_english_info')
async def get_degree_english_info(current_user: dict = Depends(verify_token_and_get_payload), db: Session = DatabaseDep):
    """获取学位英语报名基本信息"""
    try:
        sys_info = db.query(lw_sys).filter_by(dq1_mc=current_user.get('dq1_mc')).first()
        if not sys_info:
            return {'success': False, 'message': '系统配置信息不存在', 'data': None}

        xs_xh = current_user.get('xs_xh')

        # 1. 查 kw_xwyybmmd，有记录才能缴费
        reg = db.query(DegreeEnglishRegistration).filter_by(xh=xs_xh).first()
        in_list = reg is not None  # 是否在报名名单内

        # 2. 查 wx_xwyy_payinfo，获取缴费状态（有记录即已报名）
        pay_order = db.query(WxXwyyPayinfo).filter_by(
            o_xh=xs_xh,
            o_delete=0,
            o_close=0,
            o_pc=sys_info.sys_pc
        ).first()

        has_order = pay_order is not None
        has_paid = False
        order_info = None

        if pay_order:
            # 如果订单未支付但有交易号，尝试查询微信支付状态
            if pay_order.o_status == 0 and pay_order.o_trade_no:
                try:
                    wx_pay = WxPayUtil()
                    pay_result = wx_pay.query_order(pay_order.o_order_no)
                    if pay_result.get('success'):
                        pay_order.o_status = 1
                        pay_order.o_paytime = pay_result['success_time']
                        pay_order.o_trade_no = pay_result['transaction_id']
                        db.commit()
                except Exception:
                    pass

            has_paid = pay_order.o_status == 1

            order_info = {
                'o_id': pay_order.o_id,
                'order_no': pay_order.o_order_no,
                'money': pay_order.o_money,
                'status': pay_order.o_status,
                'create_time': pay_order.o_addtime.strftime('%Y-%m-%d %H:%M:%S') if pay_order.o_addtime else None,
                'pay_time': pay_order.o_paytime,
            }

        # 3. 审批状态：缴费后从 kw_xwyybmmd.bkspzt 取
        bkspzt = None
        if has_paid and reg:
            bkspzt = reg.bkspzt or '已报考待审批'

        return {
            'success': True,
            'message': '获取成功',
            'data': {
                'start_time': sys_info.sys_xwyy_start.strftime('%Y-%m-%d %H:%M:%S') if sys_info.sys_xwyy_start else None,
                'end_time': sys_info.sys_xwyy_end.strftime('%Y-%m-%d %H:%M:%S') if sys_info.sys_xwyy_end else None,
                'in_list': in_list,      # 是否在报名名单
                'has_order': has_order,  # 是否已创建订单（已报名）
                'has_paid': has_paid,    # 是否已缴费
                'order': order_info,     # 订单信息
                'bkspzt': bkspzt,        # 报考审批状态（缴费后才有）
            }
        }
    except Exception as e:
        return {'success': False, 'message': f'获取信息失败：{str(e)}', 'data': None}

@router.get('/create_degree_english_order')
async def create_degree_english_order(current_user: dict = Depends(verify_token_and_get_payload),db: Session = DatabaseDep):
    """创建学位英语报考订单"""
    try:
        # 检查是否在报名时间内
        sys_info = db.query(lw_sys).filter_by(dq1_mc=current_user.get('dq1_mc')).first()
        if not sys_info:
            return {
                'success': False,
                'msg': '系统配置信息不存在',
                'data': None
            }
        user_xs = db.query(Student).filter_by(xs_xh=current_user.get('xs_xh')).first()
        if not user_xs:
            return {
                'success': False,
                'msg': '学生信息不存在',
                'data': None
            }
        else:
            if user_xs.xs_xjzt != '1':
                return {
                    'success': False,
                    'msg': '您不是在籍生，不能报名',
                    'data': None
                }

        # 新增：校验是否在学位英语报名名单内
        print("序号",user_xs.xs_xh)
        reg = db.query(DegreeEnglishRegistration).filter_by(xh=user_xs.xs_xh).first()
        if not reg:
            return {
                'success': False,
                'msg': '您不在学位英语报名名单内，无法报名，请先到一平台报名，如已在一平台报名，请耐心等待数据同步。',
                'data': None
            }
        now = datetime.now()
        if sys_info.sys_xwyy_start and now < sys_info.sys_xwyy_start:
             return {
                 'success': False,
                 'msg': '报名未开始',
                 'data': None
             }
        if sys_info.sys_xwyy_end and now > sys_info.sys_xwyy_end:
             return {
                 'success': False,
                 'msg': '报名已结束',
                 'data': None
             }

        # 检查是否已有未支付或已支付的订单
        existing_order = db.query(WxXwyyPayinfo).filter_by(
            o_xh=current_user.get('xs_xh'),
            o_delete=0,
            o_close=0,
            o_pc=sys_info.sys_pc
        ).first()

        if existing_order:
            return {
                'success': False,
                'msg': '您已报名，无需重复报名',
                'data': None
            }
        
        # 生成订单号
        order_no = f"xwyy{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(1000, 9999)}"

        # 创建新订单
        order = WxXwyyPayinfo(
            o_xh=user_xs.xs_xh,
            o_sfzh=user_xs.xs_sfzh,
            o_body=f'黔东南开放大学-{sys_info.sys_pc}批次学位英语报名费-{user_xs.xs_xm}-JSAPIX',
            o_money=4500,  # 300元，以分为单位
            o_type=5,  # 订单类型，5为小程序
            o_status=0,  # 未支付
            o_delete=0,
            o_close=0,
            o_addtime=datetime.now(),
            o_order_no=order_no,
            o_shenhe=0,
            o_tk_status=0,
            o_paytype='weixin',
            o_pc=sys_info.sys_pc
        )

        db.add(order)
        db.commit()

        return {
            'success': True,
            'msg': '报名成功',
            'data': {
                'order_no': order.o_order_no
            }
        }
    except Exception as e:
        db.rollback()
        return {
            'success': False,
            'msg': f'报名失败：{str(e)}',
            'data': None
        }




# 生成学位英语报名费预支付参数------------------------------------------------------还未修改完成--记得修改
@router.post('/prepay_degree_english')
async def prepay_degree_english(prepay_request: PrepayRequest,current_user: dict = Depends(verify_token_and_get_payload),db: Session = DatabaseDep):
    """生成学位英语报名费预支付参数"""
    try:
        order_no = prepay_request.order_no
        openid_code = prepay_request.openid_code
        if not order_no:
            return {
                'success': False,
                'msg': '订单号不能为空',
                'data': None
            }

        # 查询订单
        order = db.query(WxXwyyPayinfo).filter_by(
            o_order_no=order_no,
            o_xh=current_user.get('xs_xh'),
            o_delete=0,
            o_pc=current_user.get('sys_pc')
        ).first()

        if not order:
            return {
                'success': False,
                'msg': '参数错误，您还未报名',
                'data': None
            }

        if order.o_status == 1:
            return {
                'success': False,
                'msg': '您已缴费完成,无需重复缴费',
                'data': None
            }

        wx_util = WxUtils()
        openidResult = wx_util.get_openid_and_session_key(openid_code)
        if not openidResult:
            return {
                'success': False,
                'msg': '获取openid失败',
                'data': None
            }
        openid = openidResult.get('openid')
        # 调用微信支付工具类生成预支付参数
        # 生成支付参数
        wx_pay = WxPayUtil()
        pay_result = wx_pay.create_pay_info(
            openid=openid,
            out_trade_no=order.o_order_no,
            total_fee=order.o_money,
            description=order.o_body,
            business_type='wx_xwyy_payinfo'
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
        return {
            'success': False,
            'msg': f'获取预支付参数失败：{str(e)}',
            'data': None
        }
    


@router.post('/update_degree_english_order')
async def update_degree_english_order(update_request: UpdateOrderRequest,current_user: dict = Depends(verify_token_and_get_payload),db: Session = DatabaseDep):
    """更新学位英语报考订单支付状态"""
    try:
        order_no = update_request.order_no
        if not order_no:
            return {
                'success': false,
                'msg': '参数错误，订单号不能为空',
                'data': None
            }

        # 查询订单
        order = db.query(WxXwyyPayinfo).filter_by(
            o_order_no=order_no,
            o_pc=current_user.get('sys_pc'),
            o_delete=0
        ).first()

        if not order:
            return {
                'success': False,
                'msg': '订单不存在',
                'data': None
            }
        
        # 查询订单状态，看看是否已经支付
        wx_pay = WxPayUtil()
        pay_result = wx_pay.query_order(order_no)
        # 检查查询结果是否成功，并且订单状态为成功
        if pay_result.get('success'):
            # 因为各种原因延迟支付，但是支付成功，更新订单状态
            order.o_status = 1
            order.o_paytime = pay_result['success_time']
            order.o_trade_no = pay_result['transaction_id']
            db.commit()
            return {
                'success': True,
                'msg': '缴费成功',
                'data': None
            }
        else:
            return {
                'success': False,
                'msg': '缴费失败',
                'data': None
            }
    except Exception as e:
        return {
            'success': False,
            'msg': f'更新订单状态失败: {str(e)}',
            'data': None
        }