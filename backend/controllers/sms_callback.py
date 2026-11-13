"""短信状态回执回调控制器

对外回调地址（nginx 反代目标，保持不变）：
    POST /sms/callback

变更历史：
- 2026-11-01前：腾讯云「短信下发状态通知」回调（POST JSON 数组，sid 对 cpSubID）
- 2026-11-10起：切到创蓝云智「短信状态回执」（POST JSON 对象，Data.msgid 对 cpSubID）
  同一地址现双兼容：创蓝优先识别，腾讯数组走过渡兜底分支。
  待网关完全切创蓝、线上无腾讯回执后，再把腾讯分支注释掉（保留下方注释块备切回）。

参考文档：
- 创蓝：https://doc.chuanglan.com/docs/MZX3EWYPJJ45IHW1
- 腾讯：https://cloud.tencent.com/document/api/382/59178
"""
import json
import os
import logging
import ipaddress

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from init.dependencies import DatabaseDep
from utils.sms_callback_chuanglan import (
    handle_chuanglan_callback,
    dump_callback_log as dump_chuanglan_callback_log,
    _extract_items as _extract_chuanglan_items,
)
from utils.sms_callback_tencent import (
    handle_tencent_callback,
    dump_callback_log as dump_tencent_callback_log,
    is_tencent_callback_ip,
    SMS_CALLBACK_IP_CHECK_ENABLED,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sms", tags=["腾讯云短信回调"])


# 受信代理（nginx）：只有来自这些 IP 的请求才允许采信 X-Forwarded-For
# 配置环境变量 SMS_TRUSTED_PROXY_IPS，逗号分隔
# 默认值即当前 OpenResty 所在服务器 IP；后端部署到其它机器时务必改成实际值，
# 否则会退化为「不采信任何代理头」，导致回调来源 IP 变成 nginx 自身 IP，
# 从而被腾讯云白名单拦截。
_TRUSTED_PROXY_IPS = {
    ip.strip()
    for ip in os.getenv('SMS_TRUSTED_PROXY_IPS', '172.16.100.102').split(',')
    if ip.strip()
}


def _is_trusted_proxy(ip: str) -> bool:
    """判断该 IP 是否是受信代理（nginx）

    只认显式配置的代理 IP（环境变量 SMS_TRUSTED_PROXY_IPS）。
    不能用「内网地址段」来判断 —— 否则任何内网地址都能被当作代理，
    从而让伪造的 X-Forwarded-For 生效。

    Args:
        ip: 待判断的 IP

    Returns:
        True 表示是受信代理
    """
    if not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return str(addr) in _TRUSTED_PROXY_IPS


def _is_private(ip: str) -> bool:
    """判断 IP 是否为内网/回环地址"""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return addr.is_private or addr.is_loopback or addr.is_link_local


def _extract_client_ip(request: Request) -> str:
    """
    取真实来源 IP

    安全要点：
    - X-Forwarded-For 是**追加式**的（nginx 用 $proxy_add_x_forwarded_for），
      真实客户端 IP 永远在**最右侧**。
    - 因此必须**从右往左**遍历，跳过受信代理，遇到的第一个非受信 IP
      才是真实客户端。直接取第一个会被外部伪造的 XFF 欺骗。
    - 只有直连来源是受信代理时才采信 XFF，否则一律用直连来源。

    Args:
        request: 请求对象

    Returns:
        真实来源 IP
    """
    peer = request.client.host if request.client else ''
    if not _is_trusted_proxy(peer):
        # 直连（非受信代理），忽略任何 XFF，防止伪造
        return peer

    # 收集候选：X-Real-IP 优先，其后是 XFF 链（按逗号拆分，保持原顺序）
    candidates = []
    real_ip = request.headers.get('x-real-ip') or ''
    if real_ip.strip():
        candidates.append(real_ip.strip())
    xff = request.headers.get('x-forwarded-for') or ''
    candidates.extend([p.strip() for p in xff.split(',') if p.strip()])

    # 从右往左找第一个「非受信代理」的 IP
    for part in reversed(candidates):
        if not _is_trusted_proxy(part):
            return part

    # 全是受信代理（理论上不会），退回 peer
    return peer


@router.post('/callback')
async def sms_callback(request: Request, db: Session = DatabaseDep):
    """
    短信状态回执回调（双兼容，现用：创蓝云智优先）

    - 创蓝：单个 JSON 对象，Data.msgid -> sms_log.cpSubID，
      成功响应 {"clcode": "000000", "msg": "接收成功"}
    - 腾讯（过渡兜底）：JSON 数组，sid -> sms_log.cpSubID，
      成功响应 {"result": 0, "errmsg": "OK"}
      过渡期保留，待网关完全切创蓝、线上无腾讯回执后再注释掉本分支。

    为同时满足双方重试判定，统一返回双方字段：
      {"result": 0, "errmsg": "OK", "clcode": "000000", "msg": "接收成功"}
    """
    try:
        body = await request.body()
        if isinstance(body, bytes):
            try:
                body_str = body.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    body_str = body.decode('gbk')
                except Exception:
                    body_str = body.decode('utf-8', errors='replace')
        else:
            body_str = str(body)
    except Exception as e:
        logger.error(f'读取短信回调请求体失败: {e}')
        return JSONResponse(
            status_code=200,
            content={'result': 0, 'errmsg': 'OK', 'clcode': '000000', 'msg': '接收成功'},
        )

    client_ip = _extract_client_ip(request)
    logger.info(
        f'收到短信回执, 来源IP={client_ip}, '
        f'peer={request.client.host if request.client else ""}, '
        f'XFF={request.headers.get("x-forwarded-for") or "-"}, '
        f'X-Real-IP={request.headers.get("x-real-ip") or "-"}'
    )

    # 解析 JSON（创蓝为单个对象，腾讯为数组，都兼容）
    try:
        payload = json.loads(body_str) if body_str.strip() else {}
    except Exception as e:
        logger.error(f'短信回调JSON解析失败: {e}, body={body_str[:500]}')
        dump_chuanglan_callback_log({'raw': body_str[:2000]}, client_ip, extra={'error': 'json_invalid'})
        return JSONResponse(
            status_code=200,
            content={'result': 0, 'errmsg': 'OK', 'clcode': '000000', 'msg': '接收成功'},
        )

    # 判定回调类型：含 Data/msgid/EventCode=SMS_REPORT 视为创蓝，
    # 含 sid/report_status 的数组视为腾讯
    def _is_chuanglan(p) -> bool:
        try:
            if isinstance(p, dict):
                if isinstance(p.get('Data'), dict):
                    return True
                if p.get('EventCode') == 'SMS_REPORT' or p.get('msgid'):
                    return True
                return False
            if isinstance(p, list):
                return bool(_extract_chuanglan_items(p))
            return False
        except Exception:
            return False

    is_chuanglan = _is_chuanglan(payload)

    # 留档原始报文（按类型打不同 tag，便于排查）
    if is_chuanglan:
        dump_chuanglan_callback_log(payload, client_ip)
    else:
        # 腾讯过渡兜底：留档走腾讯原逻辑
        # 2026-11-11 起停用 IP 白名单校验（创蓝无回调名单，腾讯分支也不再拦）：
        # 校验代码保留在下方注释，需要时放开即可。
        # if SMS_CALLBACK_IP_CHECK_ENABLED and not is_tencent_callback_ip(client_ip):
        #     logger.warning(f'非腾讯云回调IP来源，已忽略腾讯分支: {client_ip}')
        #     dump_tencent_callback_log({'raw': body_str[:2000]}, client_ip, extra={'ignored': 'ip_not_allowed'})
        #     return JSONResponse(
        #         status_code=200,
        #         content={'result': 0, 'errmsg': 'OK', 'clcode': '000000', 'msg': '接收成功'},
        #     )
        dump_tencent_callback_log(payload, client_ip)

    # 更新 sms_log（msgid/sid -> cpSubID）
    try:
        if is_chuanglan:
            stats = handle_chuanglan_callback(payload, db)
            logger.info(f'创蓝回调处理完成: {stats}')
        else:
            stats = handle_tencent_callback(payload, db)
            logger.info(f'腾讯回调处理完成(过渡兜底): {stats}')
    except Exception as e:
        logger.error(f'处理短信回调异常: {e}', exc_info=True)

    # 双兼容成功响应：腾讯认 result，创蓝认 clcode
    return JSONResponse(
        status_code=200,
        content={'result': 0, 'errmsg': 'OK', 'clcode': '000000', 'msg': '接收成功'},
    )


# ==================== 腾讯云回调（已停用，仅保留备切回） ====================
# 说明：2026-11-10 起短信改走创蓝云智，腾讯云回调停用但不删除，
#       同一回调地址 /sms/callback 现由上面的创蓝函数接管。
#       如需切回腾讯云：注释掉上面的 chuanglan_sms_callback，
#       放开下面的 tencent_sms_callback，并恢复文件头部的腾讯云 import。
#
# @router.post('/callback')
# async def tencent_sms_callback(request: Request, db: Session = DatabaseDep):
#     """
#     腾讯云短信下发状态通知回调（已停用）
#
#     请求体为 JSON 数组，每个元素描述一条短信的送达结果。
#     返回腾讯云要求的格式：{"result": 0, "errmsg": "OK"}
#     """
#     try:
#         body = await request.body()
#         body_str = body.decode('utf-8') if isinstance(body, bytes) else str(body)
#     except Exception as e:
#         logger.error(f'读取腾讯云回调请求体失败: {e}')
#         return JSONResponse(status_code=200, content={'result': 0, 'errmsg': 'OK'})
#
#     client_ip = _extract_client_ip(request)
#     logger.info(
#         f'收到腾讯云短信回调, 来源IP={client_ip}, '
#         f'peer={request.client.host if request.client else ""}, '
#         f'XFF={request.headers.get("x-forwarded-for") or "-"}, '
#         f'X-Real-IP={request.headers.get("x-real-ip") or "-"}'
#     )
#
#     # 1) 来源 IP 校验：非腾讯云网段直接忽略（但仍返回成功，避免腾讯重试）
#     if SMS_CALLBACK_IP_CHECK_ENABLED and not is_tencent_callback_ip(client_ip):
#         logger.warning(f'非腾讯云回调IP来源，已忽略: {client_ip}')
#         dump_callback_log({'raw': body_str[:2000]}, client_ip, extra={'ignored': 'ip_not_allowed'})
#         return JSONResponse(status_code=200, content={'result': 0, 'errmsg': 'OK'})
#
#     # 2) 解析 JSON（腾讯云为数组，兼容单对象）
#     try:
#         payload = json.loads(body_str) if body_str.strip() else []
#     except Exception as e:
#         logger.error(f'腾讯云回调JSON解析失败: {e}, body={body_str[:500]}')
#         dump_callback_log({'raw': body_str[:2000]}, client_ip, extra={'error': 'json_invalid'})
#         return JSONResponse(status_code=200, content={'result': 0, 'errmsg': 'OK'})
#
#     # 3) 留档原始报文
#     dump_callback_log(payload, client_ip)
#
#     # 4) 更新 sms_log
#     try:
#         stats = handle_tencent_callback(payload, db)
#         logger.info(f'腾讯云回调处理完成: {stats}')
#     except Exception as e:
#         logger.error(f'处理腾讯云回调异常: {e}', exc_info=True)
#
#     # 腾讯云要求 result=0 表示接收成功，否则会重试 2 次
#     return JSONResponse(status_code=200, content={'result': 0, 'errmsg': 'OK'})


@router.get('/callback')
async def sms_callback_check():
    """回调探活（GET），便于确认 nginx 反代是否连通"""
    return {'status': 'ok', 'message': '创蓝云智短信回执服务正常'}
