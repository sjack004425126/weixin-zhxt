"""
创蓝云智短信平台（新版）配置与回调处理

与腾讯云版（utils/sms_callback_tencent.py）结构完全一致，仅网关地址不同：
- 发送：走管理员封装的网关 http://172.16.100.102:3088/api/v1/sms_manage/sms_interface/send
  （管理员已在网关侧自行切换到创蓝，本项目无需关心通道，只需调用模板）
- 回调：创蓝云智「短信状态回执」，POST JSON 对象
  官方文档: https://doc.chuanglan.com/docs/MZX3EWYPJJ45IHW1

创蓝回调报文：
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

说明：腾讯版 utils/sms_callback_tencent.py 保留不动，以后可能切回。
"""
import os
import json
import logging
import ipaddress
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def _load_dotenv_quiet() -> None:
    """静默加载 backend/.env（与 utils/minio_client.py 同逻辑）。

    sms_callback_chuanglan_config 在 import 时就读 env，若 import 早于
    minio_client 则 CHUANGLAN_CB_* 读不到。这里自己 load 一次，保证独立可用。
    """
    try:
        from dotenv import load_dotenv  # python-dotenv
    except ImportError:
        return
    try:
        from pathlib import Path
        env_path = Path(__file__).resolve().parent.parent / ".env"
        if env_path.is_file():
            load_dotenv(env_path, override=False)
    except Exception:
        pass


_load_dotenv_quiet()


# ==================== 网关地址 ====================

# 管理员封装的短信发送网关（内网，已迁移到 102，由管理员在网关侧切换创蓝通道）
# 创蓝云智对外接口（支持 product_type / report / callback_url）
SMS_GATEWAY_URL = os.getenv('SMS_GATEWAY_URL', 'http://172.16.100.102:3088/api/v1/sms_manage/sms_clyz_interface/send')

# 创蓝短信默认模板/签名（不传时由网关取后台配置）
# 验证码模板 1022934870：变量 [param1=姓名?, param2=验证码, param3=有效时间(分钟)]
# 按 2026-11-11 联调结论固定为该编码（联调示例 param1=张三, param2=526323, param3=5）
SMS_DEFAULT_TEMPLATE_ID = os.getenv('SMS_DEFAULT_TEMPLATE_ID', '1022934870')
SMS_DEFAULT_SIGN_NAME = os.getenv('SMS_DEFAULT_SIGN_NAME', '黔东南开放大学')

# 调用方标识（source）：小程序 / 教师端 / 后台
# 2026-11-11 统一为小程序
SMS_SOURCE = os.getenv('SMS_SOURCE', '小程序')

# 创蓝产品类型：verify=验证码短信（单发），notify=通知，market=营销等
# 2026-11-11 联调结论：验证码模板必须传 verify，传 notify 会报 templateId 不存在
SMS_DEFAULT_PRODUCT_TYPE = os.getenv('SMS_DEFAULT_PRODUCT_TYPE', 'verify')

# 是否需要状态回执：True 才推送回调到 callback_url / API Key 默认回调地址
SMS_REPORT = os.getenv('SMS_REPORT', 'true').lower() in ('1', 'true', 'yes')

# 状态回执推送地址：留空则不传 callback_url，由网关/创蓝 API Key 统一配置的默认回调地址接管
SMS_CALLBACK_URL = os.getenv('SMS_CALLBACK_URL', '')

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
    # key: 业务场景, value: 创蓝模板 ID
    'query_code': os.getenv('SMS_TPL_QUERY_CODE', ''),
    'feedback_done': os.getenv('SMS_TPL_FEEDBACK_DONE', ''),
    'student_leave': os.getenv('SMS_TPL_STUDENT_LEAVE', ''),
    'student_stay': os.getenv('SMS_TPL_STUDENT_STAY', ''),
    'teacher_notify': os.getenv('SMS_TPL_TEACHER_NOTIFY', ''),
    'custom': os.getenv('SMS_TPL_CUSTOM', ''),
}

# 是否启用回调来源 IP 校验
# 2026-11-11 起停用：创蓝云智官方未提供回调来源 IP 名单，无法做白名单校验。
# 代码保留（下方 _load_ip_cidrs / _TENCENT_IP_NETS / is_tencent_callback_ip 不删除），
# 仅强制关闭开关、不再调用验证；以后若创蓝/腾讯提供名单再打开即可。
SMS_CALLBACK_IP_CHECK_ENABLED = False


# ==================== 创蓝回执推送鉴权（receiver / pswd） ====================
# 文档：https://doc.chuanglan.com/docs/MZX3EWYPJJ45IHW1
# Data.receiver（≤16字符）/ Data.pswd（≤32字符）为账号级配置，需创蓝技术支持配好；
# 未配置时创蓝推空字符串。本项目 B 方案：本地只存哈希，不存 pswd 明文。
CHUANGLAN_CB_RECEIVER = os.getenv('CHUANGLAN_CB_RECEIVER', '')
CHUANGLAN_CB_PSWD_SALT = os.getenv('CHUANGLAN_CB_PSWD_SALT', '')
CHUANGLAN_CB_PSWD_HASH = os.getenv('CHUANGLAN_CB_PSWD_HASH', '').lower()
# 严格模式：False=过渡期（创蓝未配好前，空鉴权放行+告警；一旦带值则严格校验）；
# 创蓝确认配好后改为 True（空鉴权也判失败）。
CHUANGLAN_CB_AUTH_STRICT = os.getenv('CHUANGLAN_CB_AUTH_STRICT', 'false').lower() in ('1', 'true', 'yes')

def is_chuanglan_auth_configured() -> bool:
    """是否已配置回执鉴权（三者齐全才算配好）"""
    return bool(CHUANGLAN_CB_RECEIVER and CHUANGLAN_CB_PSWD_SALT and CHUANGLAN_CB_PSWD_HASH)

def verify_chuanglan_auth(receiver: str = '', pswd: str = '') -> bool:
    """校验创蓝回执 Data.receiver / Data.pswd（B 方案：只存哈希）

    - 未配置（expect 为空）：过渡期放行，由调用方打 warn
    - 已配置但创蓝还没配（收空串）：非严格模式放行+告警；严格模式判失败
    - 已配置且收到值：receiver 明文常量时间比对 + pswd 按 SHA256(salt+pswd) 比对哈希
    """
    import hmac as _hmac
    import hashlib as _hashlib
    if not is_chuanglan_auth_configured():
        return True
    got_receiver = str(receiver or '')
    got_pswd = str(pswd or '')
    if not got_receiver and not got_pswd and not CHUANGLAN_CB_AUTH_STRICT:
        return True
    try:
        ok_receiver = _hmac.compare_digest(got_receiver, CHUANGLAN_CB_RECEIVER)
    except Exception:
        ok_receiver = False
    try:
        got_hash = _hashlib.sha256((CHUANGLAN_CB_PSWD_SALT + got_pswd).encode('utf-8')).hexdigest()
        ok_pswd = _hmac.compare_digest(got_hash.lower(), CHUANGLAN_CB_PSWD_HASH)
    except Exception:
        ok_pswd = False
    return bool(ok_receiver and ok_pswd)


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
