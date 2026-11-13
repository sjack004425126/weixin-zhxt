"""
创蓝云智短信状态回执处理

官方文档: https://doc.chuanglan.com/docs/MZX3EWYPJJ45IHW1

推送说明:
- 方式: HTTP POST, JSON
- 推送地址: 优先使用发送时指定的 callbackUrl, 未传则用 API Key 上配置的回调地址
- 发送时 report=true 才推送

推送示例:
{
  "ID": "evt_20260323100000_001",
  "EventCode": "SMS_REPORT",
  "CreatedAt": "2026-03-23T10:00:00.000+08:00",
  "Data": {
    "receiver": "",
    "pswd": "",
    "mobile": "13900000000",
    "status": "DELIVRD",
    "statusDesc": "消息发送成功",
    "notifyTime": "241104172820",
    "reportTime": "2411041728",
    "msgid": "24073116453300902203000007708373",
    "length": "1",
    "uid": "321abc"
  }
}

处理逻辑:
- 用 Data.msgid 反查 sms_log.cpSubID, 更新 callback_status / callback_desc
- callback_status 存原始 JSON 报文(不解析、不改写, 最长截断 1000)
- callback_desc 存可读描述
- 回调记录写入 sms_tb 留档
- 响应创蓝要求: {"clcode": "000000", "msg": "接收成功"}
"""
import os
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def _mask_payload_for_log(payload):
    """回执落盘前脱敏：Data.pswd 只留长度，不留明文"""
    try:
        import copy
        data = copy.deepcopy(payload)
        def _mask_item(item):
            if isinstance(item, dict):
                if isinstance(item.get('Data'), dict) and 'pswd' in item['Data']:
                    p = item['Data'].get('pswd') or ''
                    item['Data']['pswd'] = f'***len={len(str(p))}' if p else ''
                if 'pswd' in item and ('msgid' in item or 'mobile' in item):
                    p = item.get('pswd') or ''
                    item['pswd'] = f'***len={len(str(p))}' if p else ''
            return item
        if isinstance(data, dict):
            return _mask_item(data)
        if isinstance(data, list):
            return [_mask_item(x) for x in data]
        return data
    except Exception:
        return payload


def get_chuanglan_status_desc(status: str = None, status_desc: str = None) -> str:
    """生成可读描述

    Args:
        status: 运营商返回状态, DELIVRD=成功, 其余为失败(详见 code.253.com)
        status_desc: 创蓝返回的中文解释

    Returns:
        状态描述文本
    """
    parts = []
    if status:
        s = str(status).strip().upper()
        if s == 'DELIVRD':
            parts.append('成功')
        else:
            parts.append(f'失败({status})')
    if status_desc:
        parts.append(str(status_desc).strip())
    return ' '.join(parts) if parts else '未知状态'


def normalize_mobile(mobile: str) -> str:
    """归一化手机号, 去掉 +86 / 86 / 0086 前缀, 与 sms_log.xs_dh 对齐"""
    if not mobile:
        return ''
    m = str(mobile).strip()
    if m.startswith('+'):
        m = m[1:]
    if m.startswith('00') and len(m) > 11:
        m = m[2:]
    if m.startswith('86') and len(m) == 13:
        m = m[2:]
    return m


def _extract_items(payload) -> list:
    """兼容多种推送形态, 统一成 [{...Data 平铺...}] 列表

    创蓝正常只推单个对象(含 Data)。兼容:
    - dict 含 Data
    - dict 本身就是 Data(直接含 msgid)
    - list[dict]
    """
    if isinstance(payload, dict):
        # 标准形态
        if isinstance(payload.get('Data'), dict):
            top = {k: v for k, v in payload.items() if k != 'Data'}
            merged = dict(payload['Data'])
            merged['_top'] = top
            return [merged]
        # Data 平铺形态
        if payload.get('msgid') or payload.get('mobile'):
            return [payload]
        return []
    if isinstance(payload, list):
        items = []
        for p in payload:
            items.extend(_extract_items(p))
        return items
    return []


def handle_chuanglan_callback(payload, db) -> dict:
    """处理创蓝云智状态回执

    用 Data.msgid 反查 sms_log.cpSubID, 更新 callback_status / callback_desc。
    B 方案鉴权：每个 item 先验 Data.receiver / Data.pswd（只存哈希比对，
    不存不打明文）；失败则丢弃不落库，统计为 auth_failed。

    Args:
        payload: 创蓝回调 JSON(单个 dict 或 list)
        db: SQLAlchemy Session

    Returns:
        处理统计 dict
    """
    from models.models import SMSLog, SMSTb

    try:
        from utils.sms_callback_chuanglan_config import (
            is_chuanglan_auth_configured,
            verify_chuanglan_auth,
        )
    except Exception:
        def is_chuanglan_auth_configured():
            return False
        def verify_chuanglan_auth(receiver='', pswd=''):
            return True

    items = _extract_items(payload)
    auth_on = is_chuanglan_auth_configured()
    if not auth_on:
        logger.warning('创蓝回执鉴权未配置，过渡期放行（待创蓝配好 receiver/pswd 后将严格校验）')
    stats = {'total': len(items), 'updated': 0, 'not_found': 0, 'failed': 0, 'auth_failed': 0}

    for item in items:
        if not isinstance(item, dict):
            stats['failed'] += 1
            continue

        receiver = str(item.get('receiver') or '')
        pswd = str(item.get('pswd') or '')
        if auth_on:
            try:
                from utils.sms_callback_chuanglan_config import CHUANGLAN_CB_AUTH_STRICT
            except Exception:
                CHUANGLAN_CB_AUTH_STRICT = True
            if not receiver and not pswd and not CHUANGLAN_CB_AUTH_STRICT:
                logger.warning(
                    f'创蓝回调鉴权过渡期放行（创蓝尚未配置 receiver/pswd）: msgid={str(item.get("msgid") or "")[:20]}'
                )
            elif not verify_chuanglan_auth(receiver, pswd):
                stats['auth_failed'] += 1
                logger.warning(
                    f'创蓝回调鉴权失败，已丢弃: msgid={str(item.get("msgid") or "")[:20]} '
                    f'mobile={str(item.get("mobile") or "")[:15]} receiver={receiver[:16]}'
                )
                continue

        msgid = str(item.get('msgid') or '').strip()
        mobile = normalize_mobile(item.get('mobile'))
        status = str(item.get('status') or '').strip()
        status_desc_raw = str(item.get('statusDesc') or item.get('status_desc') or '').strip()
        notify_time = str(item.get('notifyTime') or '').strip()
        report_time = str(item.get('reportTime') or '').strip()
        uid = str(item.get('uid') or '').strip()
        top = item.get('_top') if isinstance(item.get('_top'), dict) else {}

        callback_desc = get_chuanglan_status_desc(status, status_desc_raw)
        if notify_time:
            callback_desc = f'{callback_desc} notifyTime:{notify_time}'
        if report_time:
            callback_desc = f'{callback_desc} reportTime:{report_time}'
        if uid:
            callback_desc = f'{callback_desc} uid:{uid}'

        # 入库前脱敏：callback_status 存掩码后的报文，不存 pswd 明文
        try:
            masked_item = dict(item)
            _p = masked_item.get('pswd') or ''
            if _p:
                masked_item['pswd'] = f'***len={len(str(_p))}'
        except Exception:
            masked_item = item
        raw_callback = json.dumps(masked_item, ensure_ascii=False, default=str)

        if not msgid:
            stats['failed'] += 1
            logger.warning('创蓝回调缺少 msgid, 忽略')
            continue

        try:
            # 回调记录留档(sms_tb.rptcode 仅 20 字符, 存 status)
            tb = SMSTb(cpSubID=msgid[:50], uPhone=mobile[:15], rptcode=status[:20])
            db.add(tb)

            record = db.query(SMSLog).filter_by(cpSubID=msgid).first()
            if record:
                record.callback_status = raw_callback[:1000]
                record.callback_desc = callback_desc[:600]
                stats['updated'] += 1
                logger.info(
                    f'创蓝回调已更新 sms_log: id={record.id}, msgid={msgid}, '
                    f'status={status}, desc={callback_desc}'
                )
            else:
                stats['not_found'] += 1
                logger.warning(f'创蓝回调未找到对应发送记录: msgid={msgid}, mobile={mobile}')

            db.commit()
        except Exception as e:
            db.rollback()
            stats['failed'] += 1
            logger.error(f'处理创蓝回调失败: msgid={msgid}, error={e}', exc_info=True)

    return stats


def dump_callback_log(payload, client_ip: str = '', extra: dict = None):
    """把回调原始报文写入 logs/sms_requests.log（pswd 脱敏后落盘）"""
    try:
        from utils.log_setup import safe_append_line, get_log_dir
        entry = {
            'timestamp': datetime.now().isoformat(),
            'type': 'chuanglan_sms_callback',
            'client_ip': client_ip,
            'payload': _mask_payload_for_log(payload),
        }
        if extra:
            entry.update(extra)
        safe_append_line(
            os.path.join(get_log_dir(), 'sms_requests.log'),
            json.dumps(entry, ensure_ascii=False, default=str) + '\n'
        )
    except Exception as e:
        logger.error(f'记录创蓝回调日志失败: {e}')
