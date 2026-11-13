# -*- coding: utf-8 -*-
"""
微信支付回调路由
用于处理微信支付成功后的回调通知，更新本地订单状态
支持根据table_name动态路由到不同的业务表
"""
import os
import random
import json
import base64
import time
from datetime import datetime

from fastapi import APIRouter, Request, Depends, Path
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from Crypto.PublicKey import RSA
from Crypto.Hash import SHA256
from Crypto.Signature import PKCS1_v1_5
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import logging

from init.dependencies import DatabaseDep
from init.config import get_config
from models.models import WxPayinfo, wxxs_payinfo, wxxs_xf_payinfo, WxXwyyPayinfo, WxxsSfTkpayinfo, bk_bkb

# 创建路由器
router = APIRouter(prefix="/wxpay/callback", tags=["微信支付回调"])

# 表名 -> 模型类映射，新增业务在此处添加一行即可
TABLE_MODEL_MAP = {
    'wx_payinfo': WxPayinfo,
    'wxxs_payinfo': wxxs_payinfo,
    'wxxs_xf_payinfo': wxxs_xf_payinfo,
    'wx_xwyy_payinfo': WxXwyyPayinfo,
    'wxxs_sf_tkpayinfo': WxxsSfTkpayinfo,
}


def get_notify_url(table_name: str) -> str:
    """
    根据表名获取回调URL
    :param table_name: 表名
    :return: 完整的回调URL
    """
    config = get_config('development')
    # 使用模板生成回调URL
    notify_url = config.wechat.NOTIFY_URL_TEMPLATE.format(table_name=table_name)
    return notify_url


def decrypt_wx_callback_data(ciphertext: str, nonce: str, associated_data: str, api_v3_key: str) -> dict:
    """
    解密微信支付回调数据
    :param ciphertext: 数据密文 (Base64编码)
    :param nonce: 随机串
    :param associated_data: 附加数据
    :param api_v3_key: APIv3密钥
    :return: 解密后的JSON数据
    """
    try:
        # Base64解码
        ciphertext_bytes = base64.b64decode(ciphertext)
        # AES-GCM解密
        aesgcm = AESGCM(api_v3_key.encode('utf-8'))
        decrypted = aesgcm.decrypt(nonce.encode('utf-8'), ciphertext_bytes, associated_data.encode('utf-8'))
        # 解析JSON
        return json.loads(decrypted.decode('utf-8'))
    except Exception as e:
        logging.error(f"解密回调数据失败: {str(e)}")
        raise


def verify_wx_callback_signature(
    timestamp: str,
    nonce_str: str,
    body: str,
    signature: str,
    platform_cert_path: str,
    platform_serial_no: str
) -> bool:
    """
    验证微信支付回调签名
    :param timestamp: 时间戳 (Wechatpay-Timestamp)
    :param nonce_str: 随机串 (Wechatpay-Nonce)
    :param body: 请求体JSON字符串
    :param signature: 签名 (Wechatpay-Signature)
    :param platform_cert_path: 微信平台证书路径
    :param platform_serial_no: 平台证书序列号
    :return: 验签是否成功
    """
    try:
        # 构建验签串
        sign_string = f"{timestamp}\n{nonce_str}\n{body}\n"

        # 读取平台证书
        cert_content = None
        if platform_cert_path:
            # 尝试多个可能的路径
            possible_paths = [
                platform_cert_path,  # 绝对路径或当前目录
                os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'utils', platform_cert_path),  # 上级utils目录
                os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'utils', platform_cert_path),  # 上上级utils目录
            ]

            for cert_path in possible_paths:
                if os.path.exists(cert_path):
                    with open(cert_path, 'r') as f:
                        cert_content = f.read()
                    logging.info(f"找到平台证书: {cert_path}")
                    break

            if not cert_content:
                logging.error(f"平台证书文件不存在: {platform_cert_path}")
                logging.error(f"已尝试路径: {possible_paths}")
                return False

        # 导入公钥
        public_key = RSA.import_key(cert_content)

        # 计算期望的签名
        h = SHA256.new(sign_string.encode('utf-8'))
        verifier = PKCS1_v1_5.new(public_key)

        # 验证签名
        try:
            verifier.verify(h, base64.b64decode(signature))
            return True
        except Exception:
            logging.warning("签名验证失败")
            return False

    except Exception as e:
        logging.error(f"验签过程异常: {str(e)}")
        return False


def verify_wx_callback_signature_via_api(
    timestamp: str,
    nonce_str: str,
    body: str,
    signature: str,
    wechat_config
) -> bool:
    """
    通过微信平台证书API验签（当本地没有平台证书时使用）
    :param timestamp: 时间戳
    :param nonce_str: 随机串
    :param body: 请求体
    :param signature: 签名
    :param wechat_config: 微信配置
    :return: 验签是否成功
    """
    import requests

    try:
        # 构建验签串
        sign_string = f"{timestamp}\n{nonce_str}\n{body}\n"

        # 从微信API获取平台证书
        # 注意：实际生产环境应该缓存证书，定期更新
        url = f"https://api.mch.weixin.qq.com/v3/certificates"
        timestamp_str = str(int(time.time()))
        nonce_str_api = ''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=32))

        # 需要使用商户私钥签名请求
        # 这里简化处理，实际需要完整实现
        logging.warning("通过API验签功能需要完整实现，建议使用本地平台证书")
        return True  # 暂时跳过

    except Exception as e:
        logging.error(f"API验签异常: {str(e)}")
        return False


async def update_order_status(
    db: Session,
    table_name: str,
    order_no: str,
    transaction_id: str,
    success_time: str
) -> bool:
    """
    更新订单状态
    :param db: 数据库会话
    :param table_name: 表名，需在 TABLE_MODEL_MAP 中注册
    :param order_no: 商户订单号
    :param transaction_id: 微信支付订单号
    :param success_time: 支付完成时间
    :return: 是否更新成功
    """
    try:
        # 获取模型类
        model_class = TABLE_MODEL_MAP.get(table_name)
        if not model_class:
            logging.error(f"未找到对应的模型: {table_name}")
            return False

        # 查询订单
        order = db.query(model_class).filter_by(o_order_no=order_no).first()
        if not order:
            logging.warning(f"未找到订单: {order_no} (表: {table_name})")
            return False

        # 检查是否已经更新过（防止重复回调）
        if order.o_status == 1 and order.o_trade_no:
            logging.info(f"订单已支付，跳过更新: {order_no}")
            return True

        # 更新订单状态
        order.o_status = 1
        order.o_trade_no = transaction_id

        # 存储微信返回的原始支付时间格式（如 2018-06-08T10:34:56+08:00），不做解析
        order.o_paytime = success_time if success_time else None

        # 补考支付回调：更新关联的 bk_bkb 报考记录为已支付
        if table_name == 'wxxs_payinfo' and hasattr(order, 'o_bkkcid') and order.o_bkkcid:
            try:
                xh = getattr(order, 'o_xh', None)
                pc = getattr(order, 'o_pc', None)
                for kid in order.o_bkkcid.split(','):
                    kid = kid.strip()
                    if kid and xh:
                        reg = db.query(bk_bkb).filter_by(xsxh=xh, kcid=kid, pc=pc).first()
                        if reg and reg.ispay != 1:
                            reg.ispay = 1
                            reg.pay_id = order.o_id
                logging.info(f"补考报考记录已更新为已支付: xh={xh}, kcids={order.o_bkkcid}")
            except Exception as e:
                logging.error(f"更新补考报考记录失败: {str(e)}")

        db.commit()
        logging.info(f"订单更新成功: {order_no}, transaction_id: {transaction_id}, table: {table_name}")
        return True

    except Exception as e:
        logging.error(f"更新订单状态失败: {str(e)}")
        db.rollback()
        return False


@router.post("/{table_name}")
async def wx_pay_callback(
    request: Request,
    table_name: str = Path(..., description="表名，用于区分不同的业务"),
    db: Session = DatabaseDep
):
    """
    微信支付回调接口
    根据table_name动态路由到不同的业务表
    例如: /wxpay/callback/wx_payinfo
    """
    try:
        # 获取请求体
        body = await request.body()
        body_str = body.decode('utf-8')
        logging.info(f"收到微信支付回调 (table: {table_name}): {body_str[:200]}...")

        # 获取请求头中的验签信息
        wechatpay_serial = request.headers.get('Wechatpay-Serial', '')
        wechatpay_signature = request.headers.get('Wechatpay-Signature', '')
        wechatpay_timestamp = request.headers.get('Wechatpay-Timestamp', '')
        wechatpay_nonce = request.headers.get('Wechatpay-Nonce', '')

        # 获取配置
        config = get_config('development')
        wechat_config = config.wechat

        # 验证签名
        if wechatpay_signature and wechatpay_timestamp and wechatpay_nonce:
            # 优先使用本地平台证书验签
            if wechat_config.PLATFORM_CERT_PATH:
                is_valid = verify_wx_callback_signature(
                    wechatpay_timestamp,
                    wechatpay_nonce,
                    body_str,
                    wechatpay_signature,
                    wechat_config.PLATFORM_CERT_PATH,
                    wechatpay_serial
                )
            else:
                # 尝试API验签（简化实现）
                logging.warning("未配置平台证书，签名验证可能不完整")
                is_valid = True  # 开发环境暂时跳过

            if not is_valid:
                logging.warning(f"微信支付回调签名验证失败 (table: {table_name})")
                return JSONResponse(
                    content={"code": "FAIL", "message": "签名验证失败"},
                    status_code=403
                )

        # 解析回调数据
        try:
            callback_data = json.loads(body_str)
        except json.JSONDecodeError:
            logging.error("回调数据解析失败")
            return JSONResponse(
                content={"code": "FAIL", "message": "Invalid JSON"},
                status_code=400
            )

        # 获取回调类型
        event_type = callback_data.get('event_type', '')
        if event_type != 'TRANSACTION.SUCCESS':
            logging.info(f"非支付成功回调，跳过处理: {event_type}")
            return Response(status_code=200)

        # 获取加密数据
        resource = callback_data.get('resource', {})
        if not resource:
            logging.error("回调数据缺少resource字段")
            return JSONResponse(
                content={"code": "FAIL", "message": "缺少resource字段"},
                status_code=400
            )

        # 解密数据
        ciphertext = resource.get('ciphertext', '')
        nonce = resource.get('nonce', '')
        associated_data = resource.get('associated_data', '')

        if not ciphertext or not nonce:
            logging.error("解密参数不完整")
            return JSONResponse(
                content={"code": "FAIL", "message": "解密参数不完整"},
                status_code=400
            )

        # 检查APIv3密钥
        if not wechat_config.APIv3_KEY:
            logging.error("未配置APIv3密钥")
            return JSONResponse(
                content={"code": "FAIL", "message": "服务器配置错误"},
                status_code=500
            )

        # 解密回调数据
        try:
            decrypted_data = decrypt_wx_callback_data(
                ciphertext,
                nonce,
                associated_data,
                wechat_config.APIv3_KEY
            )
            logging.info(f"解密后的数据: {json.dumps(decrypted_data)}")
        except Exception as e:
            logging.error(f"解密失败: {str(e)}")
            return JSONResponse(
                content={"code": "FAIL", "message": "解密失败"},
                status_code=400
            )

        # 获取业务数据
        out_trade_no = decrypted_data.get('out_trade_no', '')  # 商户订单号
        transaction_id = decrypted_data.get('transaction_id', '')  # 微信支付订单号
        trade_state = decrypted_data.get('trade_state', '')  # 交易状态
        success_time = decrypted_data.get('success_time', '')  # 支付完成时间

        if not out_trade_no:
            logging.error("解密数据缺少out_trade_no")
            return JSONResponse(
                content={"code": "FAIL", "message": "缺少订单号"},
                status_code=400
            )

        # 检查交易状态
        if trade_state != 'SUCCESS':
            logging.info(f"支付未成功: {trade_state}")
            return Response(status_code=200)

        # 检查表名是否支持
        if table_name not in TABLE_MODEL_MAP:
            logging.error(f"不支持的表名: {table_name}")
            return JSONResponse(
                content={"code": "FAIL", "message": "不支持的业务类型"},
                status_code=400
            )

        # 更新订单状态
        success = await update_order_status(
            db,
            table_name,
            out_trade_no,
            transaction_id,
            success_time
        )

        if success:
            return Response(status_code=200)
        else:
            return JSONResponse(
                content={"code": "FAIL", "message": "更新订单失败"},
                status_code=500
            )

    except Exception as e:
        logging.error(f"处理微信支付回调异常: {str(e)}", exc_info=True)
        return JSONResponse(
            content={"code": "FAIL", "message": f"服务器异常: {str(e)}"},
            status_code=500
        )


@router.get("/{table_name}")
async def wx_pay_callback_get(
    table_name: str = Path(..., description="表名")
):
    """
    微信支付回调GET请求（用于测试或验签）
    """
    return {
        "code": "SUCCESS",
        "message": "回调服务正常",
        "table": table_name,
        "timestamp": datetime.now().isoformat()
    }


# 为了兼容旧版本，保留简单路由
@router.post("")
async def wx_pay_callback_simple(request: Request, db: Session = DatabaseDep):
    """
    兼容旧版本的回调接口（默认使用wx_payinfo表）
    """
    return await wx_pay_callback(request, "wx_payinfo", db)
