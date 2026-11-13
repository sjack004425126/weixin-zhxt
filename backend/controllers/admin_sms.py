from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
from models.models import jw_chongxiu,TzdCjZJsh,Student,BkGkbkb, JhZ, WxxsSfTkpayinfo, Class, bk_sxbkb, wxxs_xf_zd, wxxs_xf_zdgr, wxxs_xf_info, lw_sys, wxxs_xf_payinfo, GraduateRegistration, bk_sxbkb_z, tzd_cjfh, wxxs_payinfo, bk_bkb, Major
from init.dependencies import (
    get_redis, get_db,
    RedisDep, DatabaseDep, RedisManagerDep
)
import logging
logger = logging.getLogger(__name__)
from common.auth import verify_token_and_get_payload, verify_token_only
from datetime import datetime
from sqlalchemy import text
import random
import json
import traceback
from utils.wx_pay import WxPayUtil
from utils.system_config import SystemConfig
from utils.wx_pay_transfer import WxPayTransfer
import logging
from utils.wx_utils import WxUtils
import re
import uuid
import time
from models.common_models import UserInfo
from models.models import SMSLog,SMSTb
from utils.debug_logger import debug_print_query_results, debug_print
from utils.sms_status_codes import get_status_description
from utils.sms import SMSTool

# 创建路由器
router = APIRouter(prefix="/admin", tags=["管理员接口"])

# 请求模型
class SmsSyncDataItem(BaseModel):
    """MAS短信平台推送数据项"""
    userID: Optional[str] = None  # 用户ID
    spNo: Optional[str] = None  # 服务号码
    uPhone: str  # 手机号码
    cpSubID: str  # CP任务编号（关键字段）
    cpSubSn: Optional[str] = None  # 手机号码序列号
    rptCode: Optional[str] = None  # 状态报告码（状态报告）
    rptTime: Optional[str] = None  # 回执时间（状态报告）
    reContent: Optional[str] = None  # 回复内容（上行消息）
    reTime: Optional[str] = None  # 回复时间（上行消息）

class SmsPushRequest(BaseModel):
    """MAS短信平台推送请求模型"""
    nCount: int  # 推送总数
    syncType: int  # 推送类型 (0=状态报告, 1=上行消息)
    syncData: list[SmsSyncDataItem]  # 推送数据


# ==================== 短信发送接口 ====================

class SendSmsRequest(BaseModel):
    """发送短信请求模型"""
    mobile: str  # 手机号码
    content: str  # 短信内容（作为「通用通知」模板的正文变量）
    scenario: Optional[str] = None  # 业务场景，默认 notify（通用通知）


@router.post('/sms/send')
async def send_sms(request: Request):
    """
    发送短信接口

    Args:
        mobile: 手机号码
        content: 短信内容

    Returns:
        {
            "success": bool,
            "message": str,
            "data": {
                "cpSubID": str,  # 任务编号
                "response": str  # API响应
            }
        }
    """
    try:
        # 获取请求体
        body = await request.body()

        # 解析JSON数据
        try:
            request_data = json.loads(body) if isinstance(body, bytes) else body
        except Exception as e:
            logger.error(f"JSON解析失败: {str(e)}")
            return {
                "success": False,
                "message": "请求参数格式错误",
                "data": None
            }

        # 验证必要参数
        mobile = request_data.get('mobile')
        content = request_data.get('content')
        scenario = request_data.get('scenario') or 'notify'

        if not mobile or not content:
            return {
                "success": False,
                "message": "缺少必要参数: mobile 或 content",
                "data": None
            }

        # 发送短信（走统一模板工具，正文作为场景变量下发）
        sms_tool = SMSTool()
        result = sms_tool.send_by_scenario(
            scenario=scenario,
            mobile=mobile,
            values={'content': content},
        )

        return {
            "success": result["success"],
            "message": result["msg"],
            "data": result["data"]
        }
    except Exception as e:
        logger.error(f"发送短信异常: {str(e)}", exc_info=True)
        return {
            "success": False,
            "message": f"发送异常: {str(e)}",
            "data": None
        }


# ==================== 短信推送接口 ====================

# @router.post('/sms/push')
# async def sms_push(
#     request: Request,
#     db: Session = DatabaseDep
# ):
#     """
#     MAS短信平台推送接口
#     用于接收短信发送状态报告和上行消息

#     推送类型说明：
#     - syncType=0: 状态报告（发送结果）
#     - syncType=1: 上行消息（用户回复）

#     请求格式:
#     {
#         "nCount": 2,
#         "syncType": 0,
#         "syncData": [
#             {
#                 "userID": "1",
#                 "spNo": "10657001",
#                 "uPhone": "13800000001",
#                 "cpSubID": "14100817343197985",
#                 "cpSubSn": "1",
#                 "rptCode": "0",
#                 "rptTime": "2014/10/8 17:34:31"
#             }
#         ]
#     }
#     """
#     try:
#         # 获取请求体
#         body = await request.body()
#         logger.info(f"收到短信推送请求: {body}")

#         # 解析JSON数据
#         try:
#             push_data = json.loads(body) if isinstance(body, bytes) else body
#         except Exception as e:
#             logger.error(f"JSON解析失败: {str(e)}")
#             return {'code': 400, 'msg': 'JSON格式错误'}

#         # 参数验证
#         n_count = push_data.get('nCount')
#         sync_type = push_data.get('syncType')
#         sync_data = push_data.get('syncData', [])

#         if n_count is None or sync_type is None:
#             logger.warning(f"推送参数不完整: nCount={n_count}, syncType={sync_type}")
#             return {'code': 400, 'msg': '缺少必要参数'}

#         if not sync_data:
#             logger.warning("推送数据为空")
#             return {'code': 400, 'msg': '推送数据为空'}

#         logger.info(f"处理推送: 类型={sync_type}, 数量={n_count}")

#         # 处理推送数据
#         success_count = 0
#         error_details = []

#         for item in sync_data:
#             try:
#                 cp_sub_id = item.get('cpSubID')
#                 u_phone = item.get('uPhone')
#                 sp_no = item.get('spNo')

#                 if not cp_sub_id or not u_phone:
#                     error_details.append(f"缺少关键参数: cpSubID={cp_sub_id}, uPhone={u_phone}")
#                     continue

#                 # 根据推送类型处理
#                 if sync_type == 0:
#                     # 状态报告
#                     rpt_code = item.get('rptCode')
#                     rpt_time = item.get('rptTime')

#                     # 获取状态描述
#                     status_desc = get_status_description(rpt_code)

#                     # 查询或创建记录
#                     sms_record = db.query(TeacherSms).filter_by(cpSubID=cp_sub_id).first()

#                     if sms_record:
#                         # 更新现有记录
#                         sms_record.send_status = int(rpt_code) if rpt_code == '0' else rpt_code
#                         sms_record.status_desc = status_desc
#                         logger.info(f"更新短信记录: cpSubID={cp_sub_id}, 状态={rpt_code}")
#                     else:
#                         # 创建新记录
#                         sms_record = TeacherSms(
#                             cpSubID=cp_sub_id,
#                             xs_dh=u_phone,
#                             spNo=sp_no,
#                             fssj=datetime.now(),
#                             send_status=int(rpt_code) if rpt_code == '0' else rpt_code,
#                             status_desc=status_desc
#                         )
#                         db.add(sms_record)
#                         logger.info(f"创建短信记录: cpSubID={cp_sub_id}, 状态={rpt_code}")

#                     success_count += 1

#                 elif sync_type == 1:
#                     # 上行消息（用户回复）
#                     re_content = item.get('reContent')
#                     re_time = item.get('reTime')

#                     # 查询或创建记录
#                     sms_record = db.query(TeacherSms).filter_by(cpSubID=cp_sub_id).first()

#                     if sms_record:
#                         # 更新记录，添加回复内容
#                         sms_record.nr = re_content  # 存储回复内容
#                         sms_record.fssj = datetime.now()
#                         logger.info(f"更新上行消息: cpSubID={cp_sub_id}, 内容={re_content}")
#                     else:
#                         # 创建新记录
#                         sms_record = TeacherSms(
#                             cpSubID=cp_sub_id,
#                             xs_dh=u_phone,
#                             spNo=sp_no,
#                             nr=re_content,
#                             fssj=datetime.now(),
#                             send_status=1,  # 标记为已接收
#                             status_desc='上行消息'
#                         )
#                         db.add(sms_record)
#                         logger.info(f"创建上行消息记录: cpSubID={cp_sub_id}")

#                     success_count += 1

#             except Exception as e:
#                 error_details.append(f"处理项目失败: {str(e)}")
#                 logger.error(f"处理推送项目失败: {str(e)}", exc_info=True)

#         # 提交事务
#         db.commit()

#         logger.info(f"推送处理完成: 成功={success_count}, 失败={len(error_details)}")

#         # 返回成功响应（必须返回0表示接收成功）
#         return {'code': 0, 'msg': '接收成功'}

#     except Exception as e:
#         db.rollback()
#         logger.error(f"短信推送处理失败: {str(e)}", exc_info=True)
#         return {'code': 500, 'msg': f'处理失败: {str(e)}'}





@router.post('/sms/push')
async def sms_push(request: Request, db: Session = DatabaseDep):
    """
    MAS短信平台推送接口
    用于接收短信发送状态报告和上行消息

    接收 form-data 格式: msg={"nCount":1,"syncType":0,"syncData":[...]}
    """
    sms_tool = SMSTool()

    try:
        # 获取请求体
        body = await request.body()
        body_str = body.decode('utf-8') if isinstance(body, bytes) else str(body)

        # 记录原始请求到日志文件
        request_log = {
            "timestamp": datetime.now().isoformat(),
            "type": "push_request_body",
            "raw_body": body_str,
            "client_ip": request.client.host if request.client else 'Unknown'
        }
        sms_tool.log_sms_push_callback(request_log)
        # 解析 form-data 格式
        form_data = await request.form()
        msg_param = form_data.get('msg')
        if not msg_param:
            return {'code': 0, 'msg': '接收成功'}

        # 解析 JSON 数据
        push_data = json.loads(msg_param)

        # 获取推送数据
        sync_data = push_data.get('syncData', [])

        # 循环遍历所有数据，保存到 SMSTb 并更新 SMSLog 状态
        for item in sync_data:
            try:
                u_phone = item.get('uPhone')
                cp_sub_id = item.get('cpSubID')
                rpt_code = item.get('rptCode')

                # 保存到 SMSTb 表
                sms_record = SMSTb(
                    cpSubID=cp_sub_id,
                    uPhone=u_phone,
                    rptcode=rpt_code
                )
                db.add(sms_record)
                db.commit()

                # 查询 SMSLog 记录
                smslog = db.query(SMSLog).filter_by(xs_dh=u_phone, cpSubID=cp_sub_id).first()
                if smslog:
                    # 更新状态
                    smslog.send_status = rpt_code
                    status_desc = get_status_description(rpt_code)
                    smslog.status_desc = status_desc
                    db.commit()
                else:
                    # 记录未找到记录到日志文件
                    result_log = {
                        "timestamp": datetime.now().isoformat(),
                        "type": "smslog_update",
                        "uPhone": u_phone,
                        "cpSubID": cp_sub_id,
                        "status": "not_found"
                    }
                    sms_tool.log_sms_push_callback(result_log)

            except Exception as e:
                # 记录处理错误到日志文件
                error_log = {
                    "timestamp": datetime.now().isoformat(),
                    "type": "smslog_error",
                    "error": str(e),
                    "item": item
                }
                sms_tool.log_sms_push_callback(error_log)
        return {'code': 0, 'msg': '接收成功'}
    except Exception as e:
        # 记录异常到日志文件
        error_log = {
            "timestamp": datetime.now().isoformat(),
            "type": "push_exception",
            "error": str(e),
            "error_type": type(e).__name__
        }
        sms_tool.log_sms_push_callback(error_log)
        return {'code': 0, 'msg': '接收成功'}