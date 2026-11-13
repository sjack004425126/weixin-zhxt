from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from models.models import Student, Class, bk_sxbkb, wxxs_xf_zd, wxxs_xf_zdgr, wxxs_xf_info, lw_sys, wxxs_xf_payinfo, GraduateRegistration, bk_sxbkb_z, tzd_cjfh, wxxs_payinfo, bk_bkb, WxXwyyPayinfo
from init.dependencies import (
    get_redis, get_db,
    RedisDep, DatabaseDep, RedisManagerDep
)
from common.auth import verify_token_and_get_payload, verify_token_only
from sqlalchemy import text
from datetime import datetime, timedelta
from utils.wx_pay import WxPayUtil
import logging

# 创建路由器
router = APIRouter(prefix="/system_admin", tags=["系统管理"])

@router.get('/order/repair')
async def repair_abnormal_orders(
    order_no: str,
    db: Session = DatabaseDep
):
    """查询并修复支付异常订单
    
    Query Parameters:
        start_time: 开始时间 (可选，格式：YYYY-MM-DD HH:mm:ss)
        end_time: 结束时间 (可选，格式：YYYY-MM-DD HH:mm:ss)
        order_no: 订单号 (可选)
        student_id: 学号 (可选)
        
    Returns:
        json: 异常订单列表及修复结果
    """

    wx_pay = WxPayUtil()
    query_result = wx_pay.query_order(out_trade_no=order_no)

    # 检查查询结果
    if not query_result or 'trade_state' not in query_result:
        raise HTTPException(status_code=500, detail={
            'code': 1,
            'msg': '查询订单失败',
            'data': None
        })

    # 检查支付状态
    if query_result['trade_state'] != 'SUCCESS':
        raise HTTPException(status_code=400, detail={
            'code': 1,
            'msg': f'订单未支付成功,当前状态: {query_result["trade_state_desc"]}',
            'data': None
        })

    # 从返回数据中提取需要的参数
    transaction_id = query_result['transaction_id']  # 微信支付订单号
    success_time = datetime.strptime(
        query_result['success_time'].replace('T', ' ').split('+')[0],
        '%Y-%m-%d %H:%M:%S'
    )  # 支付成功时间
    
    try:
        # 更新本地订单信息
        order = db.query(wxxs_payinfo).filter_by(o_order_no=order_no).first()
        if order:
            order.o_status = 1  # 更新为已支付
            order.o_trade_no = transaction_id
            order.o_paytime = success_time
            db.commit()

            # 更新报考记录信息
            # 查询并更新所有相关记录
            db.query(bk_bkb).filter_by(pay_id=order.o_id).update({
                'isbk': 1,
                'ispay': 1
            })
            db.commit()

            return {
                'code': 0,
                'msg': '订单支付成功并已更新',
                'data': {
                    'order_no': order_no,
                    'transaction_id': transaction_id,
                    'pay_time': success_time.strftime('%Y-%m-%d %H:%M:%S')
                }
            }
        else:
            raise HTTPException(status_code=404, detail={
                'code': 1,
                'msg': '本地订单不存在',
                'data': None
            })

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail={
            'code': 1,
            'msg': f'更新订单状态失败: {str(e)}',
            'data': None
        })

@router.get('/order/wxPayInfo')
async def get_wx_pay_info(
    order_no: str,
    type: str,
    db: Session = DatabaseDep
):
    """查询微信订单缴费信息
    
    Query Parameters:
        order_no: 订单号
        
    Returns:
        json: 订单缴费信息
    """
    try:
        if not order_no or not type:
            raise HTTPException(status_code=400, detail={
                'code': 1,
                'msg': '订单号和类型不能为空',
                'data': None
            })

        if type == 'bk':
            order_info = db.query(wxxs_payinfo).filter_by(o_order_no=order_no).first()
            if not order_info:
                raise HTTPException(status_code=404, detail={
                    'code': 1,
                    'msg': '未找到该订单信息',
                    'data': None
                })
            # 查询微信支付订单状态
            wx_pay = WxPayUtil()
            wx_order_status = wx_pay.query_order(out_trade_no=order_no)
            
            # 合并订单信息和微信支付状态
            response_data = {
                'localOrderMoney': str(order_info.o_money)+"元",
                'wxPayMoney': str(wx_order_status['amount']['total']/100)+"元",
                'wxPayStatus': wx_order_status['trade_state_desc']
            }
            return {
                'code': 0,
                'msg': 'success',
                'data': response_data
            }
        elif type == 'xf':
            order_info = db.query(wxxs_xf_payinfo).filter_by(o_order_no=order_no).first()
            if not order_info:
                raise HTTPException(status_code=404, detail={
                    'code': 1,
                    'msg': '未找到该订单信息',
                    'data': None
                })
            # 查询微信支付订单状态
            wx_pay = WxPayUtil()
            wx_order_status = wx_pay.query_order(out_trade_no=order_no)

            # 合并订单信息和微信支付状态
            response_data = {
                'localOrderMoney': str(order_info.o_money/100)+"元",
                'wxPayMoney': str(wx_order_status['amount']['total']/100)+"元",
                'wxPayStatus': wx_order_status['trade_state_desc']
            }
            return {
                'code': 0,
                'msg': 'success',
                'data': response_data
            }
        else:
            raise HTTPException(status_code=400, detail={
                'code': 1,
                'msg': '类型错误',
                'data': None
            })
    except Exception as e:
        logging.error(f"查询微信订单缴费信息失败: {str(e)}")
        raise HTTPException(status_code=500, detail={
            'code': 1,
            'msg': f'查询失败: {str(e)}',
            'data': None
        })
    
