"""
通用手机号快捷认证缓存服务。

为 zhpt-new 内所有子系统（student-info / vocational-new-payment /
feedback-login / user-center）提供统一的"7 天免二次手机号授权"能力。

Redis key 设计：
    zhpt:phone_auth:{appid}:{openid}
    value: {
        'pure_phone': '13800001234',
        'role':       'self' | 'parent',
        'subject':    'vocational_new_payment' | 'student_info' | 'feedback' | 'user_center',
        'sfzh':       '...',
        'xm':         '...',
        'xs_id':      ...,           # 可选
        'bj_id':      ...,           # 可选
        'verified_at': '2026-08-15T08:00:00',
        'appid':      'wxe8f312724bfb12f0',
    }
    TTL: 7 天
"""

import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from utils.wx_utils import WxUtils


PHONE_CACHE_PREFIX = "zhpt:phone_auth:"
PHONE_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 天

# 已知的业务身份（subject）。前端传入时按字符串匹配。
SUBJECT_VOCATIONAL_PAYMENT = "vocational_new_payment"
SUBJECT_STUDENT_INFO = "student_info"
SUBJECT_FEEDBACK = "feedback"
SUBJECT_USER_CENTER = "user_center"
ALL_SUBJECTS = {
    SUBJECT_VOCATIONAL_PAYMENT,
    SUBJECT_STUDENT_INFO,
    SUBJECT_FEEDBACK,
    SUBJECT_USER_CENTER,
}

logger = logging.getLogger(__name__)


def _redis():
    """惰性导入 redis_manager，避免循环依赖。"""
    from init.redis_manager import redis_manager
    return redis_manager


def _build_key(appid: str, openid: str) -> str:
    return f"{PHONE_CACHE_PREFIX}{appid}:{openid}"


def get_appid() -> str:
    """当前 appid（与 wx_utils 中的配置保持一致）。"""
    return WxUtils.WX_CONFIG.get("appid", "")


def normalize_phone(phone: str) -> str:
    """
    把微信返回的手机号归一化为纯 11 位（去 +86 / 空格 / 横线）。
    """
    if not phone:
        return ""
    p = phone.strip().replace(" ", "").replace("-", "")
    if p.startswith("+86"):
        p = p[3:]
    return p


def mask_phone(phone: str) -> str:
    """13800001234 -> 138****1234"""
    if not phone or len(phone) < 7:
        return phone or ""
    return phone[:3] + "****" + phone[-4:]


def write_phone_cache(
    openid: str,
    pure_phone: str,
    role: str,
    subject: str,
    extra: Optional[Dict[str, Any]] = None,
    ttl_seconds: int = PHONE_CACHE_TTL_SECONDS,
) -> bool:
    """
    把手机号授权结果写入 Redis。失败返回 False，不抛异常。

    参数：
        openid:      wx.login → jscode2session 拿到的 openid
        pure_phone:  归一化后的纯 11 位手机号
        role:        'self' 或 'parent'
        subject:     当前业务身份（vocational_new_payment / student_info / feedback / user_center）
        extra:       其它附属字段（sfzh / xm / xs_id / bj_id）
        ttl_seconds: 默认 7 天
    """
    try:
        appid = get_appid()
        payload: Dict[str, Any] = {
            "pure_phone": pure_phone,
            "role": role,
            "subject": subject,
            "verified_at": datetime.utcnow().isoformat(),
            "appid": appid,
        }
        if extra:
            payload.update(extra)
        key = _build_key(appid, openid)
        ok = _redis().set(key, payload, ex=ttl_seconds)
        print(f'[phone_cache] write {"OK" if ok else "FAIL"} key={key} subject={subject} '
              f'role={role} pure_phone={pure_phone} ttl={ttl_seconds}s')
        logger.info(
            "[phone_cache] write ok=%s key=%s subject=%s role=%s ttl=%ss",
            ok, key, subject, role, ttl_seconds,
        )
        return bool(ok)
    except Exception as e:
        print(f'[phone_cache] write EXCEPTION: {e}')
        logger.warning("[phone_cache] write failed: %s", e)
        return False


def read_phone_cache(openid: str) -> Optional[Dict[str, Any]]:
    """
    读取手机号授权缓存。
    返回 dict（包含 subject / pure_phone / role / extra 字段），未命中或失败返回 None。
    """
    try:
        appid = get_appid()
        key = _build_key(appid, openid)
        data = _redis().get(key)
        if not data or not isinstance(data, dict):
            print(f'[phone_cache] read MISS key={key}')
            return None
        print(f'[phone_cache] read HIT  key={key} subject={data.get("subject")} '
              f'role={data.get("role")} pure_phone={data.get("pure_phone")}')
        return data
    except Exception as e:
        logger.warning("[phone_cache] read failed: %s", e)
        return None


def clear_phone_cache(openid: str) -> bool:
    """
    主动清除手机号授权缓存（用于"重选身份"）。
    """
    try:
        appid = get_appid()
        key = _build_key(appid, openid)
        n = _redis().delete(key)
        logger.info("[phone_cache] clear ok=%s key=%s", n, key)
        return True
    except Exception as e:
        logger.warning("[phone_cache] clear failed: %s", e)
        return False


def resolve_openid_by_login_code(login_code: str) -> Optional[str]:
    """
    把 wx.login 返回的 code 通过 jscode2session 解析为 openid。
    失败返回 None。
    """
    if not login_code:
        return None
    try:
        info = WxUtils.get_openid_and_session_key(login_code)
        if not info:
            return None
        return info.get("openid")
    except Exception as e:
        logger.warning("[phone_cache] resolve_openid failed: %s", e)
        return None
