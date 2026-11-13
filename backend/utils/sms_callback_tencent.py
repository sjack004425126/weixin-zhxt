"""
腾讯云短信平台（新版）配置与回调处理

与旧版 MAS 平台（http://101.37.116.233:8063/subSmsApi.aspx）不同：
- 发送：走管理员封装的网关 http://172.16.100.103:3088/api/v1/sms_manage/sms_interface/send
- 回调：腾讯云「短信下发状态通知」，POST JSON 数组

腾讯云回调报文（参考 https://cloud.tencent.com/document/api/382/59178）：
[
    {
        "user_receive_time": "2015-10-17 08:03:04",
        "nationcode": "86",
        "mobile": "13xxxxxxxxx",
        "report_status": "SUCCESS",       # SUCCESS / FAIL
        "errmsg": "DELIVRD",
        "description": "用户短信送达成功",
        "sid": "xxxxxxx",                # 与发送接口返回的 SerialNo 对应
        "ext": "..."                     # 对应发送时的 SessionContext
    }
]

回执状态错误码参考 https://cloud.tencent.com/document/api/382/59177
"""
import os
import json
import logging
import ipaddress
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


# ==================== 网关地址 ====================

# 管理员封装的短信发送网关（内网，已迁移到 102）
# 腾讯云对外接口（与创蓝 sms_clyz_interface 并存，仅通道不同）
# 2026-11-11 起默认指向 102（老 103 已下线），可被环境变量 SMS_GATEWAY_URL 覆盖
SMS_GATEWAY_URL = os.getenv('SMS_GATEWAY_URL', 'http://172.16.100.102:3088/api/v1/sms_manage/sms_interface/send')

# 腾讯云短信默认模板/签名（不传时由网关取后台配置）
SMS_DEFAULT_TEMPLATE_ID = os.getenv('SMS_DEFAULT_TEMPLATE_ID', '2726397')
SMS_DEFAULT_SIGN_NAME = os.getenv('SMS_DEFAULT_SIGN_NAME', '黔东南开放大学')

# 调用方标识（source）：小程序 / 教师端 / 后台
SMS_SOURCE = os.getenv('SMS_SOURCE', '小程序')

# 验证码模板：模板变量 [code, 有效时间(分钟)]
SMS_VERIFY_EXPIRE_MINUTES = int(os.getenv('SMS_VERIFY_EXPIRE_MINUTES', '5'))

# 模板 ID 统一由 utils/sms_templates.py 的注册表管理，
# 这里只做兼容导出，避免两处配置漂移。
# （验证码模板：SMS_VERIFY_TEMPLATE_ID 兼容 → SMS_TPL_VERIFY）
SMS_VERIFY_TEMPLATE_ID = os.getenv(
    'SMS_VERIFY_TEMPLATE_ID', os.getenv('SMS_TPL_VERIFY', '2726397'))

# 通知类模板（无变量）
SMS_NOTIFY_TEMPLATE_ID = os.getenv('SMS_NOTIFY_TEMPLATE_ID', '')
SMS_NOTIFY_TEMPLATE_IDS = {
    # key: 业务场景, value: 腾讯云模板 ID
    'query_code': os.getenv('SMS_TPL_QUERY_CODE', ''),
    'feedback_done': os.getenv('SMS_TPL_FEEDBACK_DONE', ''),
    'student_leave': os.getenv('SMS_TPL_STUDENT_LEAVE', ''),
    'student_stay': os.getenv('SMS_TPL_STUDENT_STAY', ''),
    'teacher_notify': os.getenv('SMS_TPL_TEACHER_NOTIFY', ''),
    'custom': os.getenv('SMS_TPL_CUSTOM', ''),
}

# 是否启用回调来源 IP 校验
# 说明：生产环境保持 true（严格拦截）；开发环境可设为 false 以便本地模拟回调
SMS_CALLBACK_IP_CHECK_ENABLED = os.getenv(
    'SMS_CALLBACK_IP_CHECK_ENABLED',
    'false' if os.getenv('FASTAPI_ENV', 'development') == 'development' else 'true'
).lower() in ('1', 'true', 'yes')


# ==================== 回调 IP 白名单 ====================

def _load_ip_cidrs():
    """加载腾讯云回调 IP 网段列表"""
    try:
        from utils.tencent_sms_ip import TENCENT_SMS_CALLBACK_IP_CIDRS
        return [ipaddress.ip_network(c, strict=False) for c in TENCENT_SMS_CALLBACK_IP_CIDRS]
    except Exception as e:
        logger.warning(f"加载腾讯云回调 IP 白名单失败: {e}")
        return []


_TENCENT_IP_NETS = _load_ip_cidrs()


def is_tencent_callback_ip(ip: str) -> bool:
    """判断来源 IP 是否属于腾讯云短信回调网段

    Args:
        ip: 来源 IP（不含端口）

    Returns:
        True 表示在白名单网段内
    """
    if not _TENCENT_IP_NETS:
        # 白名单未加载成功时放行，避免误杀回调（由配置项控制是否严格）
        return True
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in _TENCENT_IP_NETS)


# ==================== 回执状态码 ====================

# 腾讯云回执状态错误码（部分，参考文档 382/59177）
TENCENT_REPORT_ERROR_CODES = {
    'DELIVRD': '成功送达',
    'EXPIRED': '短信长时间未送达',
    'DELETED': '短信长时间未送达，运营商删除',
    'UNKNOWN': '未知状态',
    'SENTFAIL': '发送失败',
    'ISBLACK': '手机号在黑名单中',
    'NUMBER_ILLEGAL': '手机号不合法',
    'TEMPLATEID_ILLEGAL': '模板 ID 不合法',
    'CONTENT_ILLEGAL': '模板内容不匹配',
    'SIGNATURE_ILLEGAL': '签名不合法',
    'LIMIT_EXCEED': '发送量超限',
    'BALANCE_NOT_ENOUGH': '余额不足',
    'MOBILE_NUMBER_ILLEGAL': '手机号非法',
    'USERID_INVALID': '用户账号无效',
    'OPERATOR_ERROR': '运营商异常',
    'MOBILE_ACCOUNT_ERROR': '用户账户异常',
}


def get_tencent_status_desc(report_status: str, errmsg: str = None, description: str = None) -> str:
    """根据腾讯云回调字段生成可读描述

    Args:
        report_status: SUCCESS / FAIL
        errmsg: 回执状态码
        description: 平台自带描述

    Returns:
        状态描述文本
    """
    parts = []
    if report_status:
        parts.append('成功' if str(report_status).upper() == 'SUCCESS' else f'失败({report_status})')
    if errmsg:
        parts.append(TENCENT_REPORT_ERROR_CODES.get(errmsg, errmsg))
    elif description:
        parts.append(description)
    return ' '.join(parts) if parts else '未知状态'


# ==================== 回调处理 ====================

def normalize_mobile(mobile: str, nationcode: str = '86') -> str:
    """归一化手机号，去掉 +86 / 86 / 0086 前缀，与 sms_log.xs_dh 对齐"""
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


def handle_tencent_callback(payload, db) -> dict:
    """处理腾讯云短信下发状态通知回调

    用 sid（SerialNo）反查 sms_log.cpSubID，更新 callback_status / callback_desc。

    Args:
        payload: 腾讯云回调 JSON（单条 dict 或 list）
        db: SQLAlchemy Session

    Returns:
        处理统计 dict
    """
    from models.models import SMSLog, SMSTb

    if isinstance(payload, dict):
        items = [payload]
    elif isinstance(payload, list):
        items = payload
    else:
        items = []

    stats = {'total': len(items), 'updated': 0, 'not_found': 0, 'failed': 0}

    for item in items:
        if not isinstance(item, dict):
            stats['failed'] += 1
            continue

        sid = (item.get('sid') or '').strip()
        mobile = normalize_mobile(item.get('mobile'), item.get('nationcode', '86'))
        report_status = (item.get('report_status') or '').strip()
        errmsg = (item.get('errmsg') or '').strip()
        description = (item.get('description') or '').strip()
        user_receive_time = (item.get('user_receive_time') or '').strip()
        ext = (item.get('ext') or '').strip()

        callback_status = report_status or errmsg or 'UNKNOWN'
        callback_desc = get_tencent_status_desc(report_status, errmsg, description)
        if user_receive_time:
            callback_desc = f'{callback_desc} 接收时间:{user_receive_time}'
        if ext:
            callback_desc = f'{callback_desc} ext:{ext}'

        # callback_status 存腾讯云回调的**原始 JSON 报文**（不解析、不改写）。
        # callback_desc 仍按原逻辑存解析后的可读描述。
        raw_callback = json.dumps(item, ensure_ascii=False, default=str)

        if not sid:
            stats['failed'] += 1
            logger.warning('腾讯云回调缺少 sid，忽略')
            continue

        try:
            # 回调记录留档
            tb = SMSTb(cpSubID=sid, uPhone=mobile[:15], rptcode=callback_status[:20])
            db.add(tb)

            # 用 sid 反查发送记录（cpSubID 存的就是腾讯云 SerialNo）
            record = db.query(SMSLog).filter_by(cpSubID=sid).first()
            if record:
                record.callback_status = raw_callback[:1000]
                record.callback_desc = callback_desc
                stats['updated'] += 1
                logger.info(
                    f'腾讯云回调已更新 sms_log: id={record.id}, sid={sid}, '
                    f'status={callback_status}, desc={callback_desc}'
                )
            else:
                # sid 未对上时的兜底匹配。
                # 安全约束：只接受「发送时间在回调到达时间附近」的记录，
                # 否则一条旧短信的迟到回调会误写到新短信上（曾经踩过的坑）。
                phone_variants = {mobile, f'+86{mobile}', mobile.lstrip('+')}
                now = datetime.now()
                fallback = (
                    db.query(SMSLog)
                    .filter(
                        SMSLog.xs_dh.in_(phone_variants),
                        SMSLog.callback_status.is_(None),
                        SMSLog.cpSubID.like('99:%'),
                    )
                    .order_by(SMSLog.id.desc())
                    .first()
                )
                # 时间合理性校验：发送时间不能晚于回调 1 分钟，也不能早于回调 24 小时
                if fallback is not None:
                    sent_at = fallback.fssj
                    if sent_at is None or not (
                        now - timedelta(hours=24) <= sent_at <= now + timedelta(minutes=1)
                    ):
                        logger.warning(
                            f'腾讯云回调 sid 未匹配，手机号兜底记录时间不合理，已跳过: '
                            f'id={fallback.id}, sent_at={sent_at}, sid={sid}'
                        )
                        fallback = None

                if fallback:
                    fallback.callback_status = raw_callback[:1000]
                    fallback.callback_desc = callback_desc
                    stats['updated'] += 1
                    logger.warning(f'腾讯云回调 sid 未匹配，按手机号兜底匹配: id={fallback.id}, sid={sid}')
                else:
                    stats['not_found'] += 1
                    logger.warning(f'腾讯云回调未找到对应发送记录: sid={sid}, mobile={mobile}')

            db.commit()
        except Exception as e:
            db.rollback()
            stats['failed'] += 1
            logger.error(f'处理腾讯云回调失败: sid={sid}, error={e}', exc_info=True)

    return stats


def dump_callback_log(payload, client_ip: str = '', extra: dict = None):
    """把回调原始报文写入 logs/sms_requests.log"""
    try:
        from utils.log_setup import safe_append_line, get_log_dir
        entry = {
            'timestamp': datetime.now().isoformat(),
            'type': 'tencent_sms_callback',
            'client_ip': client_ip,
            'payload': payload,
        }
        if extra:
            entry.update(extra)
        safe_append_line(
            os.path.join(get_log_dir(), 'sms_requests.log'),
            json.dumps(entry, ensure_ascii=False, default=str) + '\n'
        )
    except Exception as e:
        logger.error(f'记录腾讯云回调日志失败: {e}')
