"""
问卷提交防滥用工具
提供:
  - IP 滑窗限频
  - HMAC 签名校验(防裸 curl / 重放)
  - timestamp 防重放

签名协议(SURVEY_SUBMIT):
    前端: sig = HMAC_SHA256(SECRET, f"{sid}|{ts}|{nonce}|{sha256(answers_json)}")
    后端: 同算法校验
    timestamp 与服务端时间差 ≤ 300s 有效
    同一 nonce 5 分钟内只能使用一次
"""
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# ---------- 配置 ----------
# 同一 IP 60 秒内最多提交次数
SUBMIT_IP_LIMIT_PER_MIN = 3
# 同一 IP 1 小时(3600s)内最多提交次数
SUBMIT_IP_LIMIT_PER_HOUR = 30
# timestamp 允许漂移(秒)
SUBMIT_TS_TOLERANCE = 300
# nonce 有效期(秒)
SUBMIT_NONCE_TTL = 300

# 共享密钥(从后端 .env 读取 SURVEY_SIGN_SECRET)
SURVEY_SIGN_SECRET = os.environ.get("SURVEY_SIGN_SECRET", "zhpt-survey-sign-2026-change-me")


def _get_real_ip(request) -> str:
    """获取真实 IP(优先反向代理头)."""
    if not request:
        return "unknown"
    # 常见代理头,有则用,没有 fallback
    for header in ("X-Forwarded-For", "X-Real-IP", "CF-Connecting-IP"):
        v = request.headers.get(header)
        if v:
            # X-Forwarded-For 可能为 "client, proxy1, proxy2", 取第一个
            return v.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def check_ip_rate_limit(redis_client, request, sid: int) -> Tuple[bool, str]:
    """
    IP 滑窗限频。
    Return: (allowed, message)
    """
    if not redis_client:
        # 没有 redis 时放行,避免单点挂全站
        return True, "ok"

    ip = _get_real_ip(request)
    try:
        minute_key = f"survey:rl:ip:{ip}:min"
        hour_key = f"survey:rl:ip:{ip}:hour"

        pipe = redis_client.pipeline()
        pipe.incr(minute_key)
        pipe.expire(minute_key, 60)
        pipe.incr(hour_key)
        pipe.expire(hour_key, 3600)
        min_count, _, hour_count, _ = pipe.execute()

        if min_count > SUBMIT_IP_LIMIT_PER_MIN:
            return False, f"提交过于频繁,请 {60}s 后再试"
        if hour_count > SUBMIT_IP_LIMIT_PER_HOUR:
            return False, "提交次数超限,请稍后再试"
        return True, "ok"
    except Exception as e:
        logger.warning(f"[survey-guard] ip rate limit check failed: {e}")
        return True, "ok"


def _answers_canonical(answers) -> str:
    """将 answers 规范化为稳定 JSON 字符串(对 list/dict 排序)."""
    try:
        return json.dumps(answers or [], sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return ""


def build_sign_payload(sid: int, ts: int, nonce: str, answers) -> str:
    """生成签名明文(前后端共用)."""
    answers_hash = hashlib.sha256(_answers_canonical(answers).encode("utf-8")).hexdigest()
    return f"{sid}|{ts}|{nonce}|{answers_hash}"


def compute_signature(payload: str, secret: str = SURVEY_SIGN_SECRET) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_submit_signature(
    redis_client,
    sid: int,
    ts: Optional[int],
    nonce: Optional[str],
    sig: Optional[str],
    answers,
) -> Tuple[bool, str]:
    """
    校验签名 + 防重放(分级策略).

    三档:
      sig + ts + nonce 都有 -> 校验 HMAC(最严,挡裸 curl + 防重放)
      sig 没有, 仅 ts + nonce -> 仅做时间窗 + nonce 唯一性(中档,挡重放)
      都没有 -> 直接拒(低级门槛)
    """
    # 1. ts + nonce 是基础门槛, 至少要有
    if not ts or not nonce:
        return False, "缺少时间戳或 nonce"

    # 2. ts 必须是 int, 漂移检查
    try:
        ts = int(ts)
    except (TypeError, ValueError):
        return False, "时间戳格式错误"
    now = int(time.time())
    if abs(now - ts) > SUBMIT_TS_TOLERANCE:
        return False, "请求已过期, 请重新提交"

    # 3. HMAC 签名(可选但建议传)
    if sig:
        payload = build_sign_payload(sid, ts, nonce, answers)
        expected = compute_signature(payload)
        if not hmac.compare_digest(expected, sig):
            return False, "签名校验失败"

    # 4. nonce 防重放(5 分钟内只能使用一次)
    if redis_client:
        nonce_key = f"survey:nonce:{sid}:{nonce}"
        try:
            ok = redis_client.set(nonce_key, "1", nx=True, ex=SUBMIT_NONCE_TTL)
            if not ok:
                return False, "请勿重复提交"
        except Exception as e:
            logger.warning(f"[survey-guard] nonce check failed: {e}")
    return True, "ok"
