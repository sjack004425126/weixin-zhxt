"""
问卷提交次数控制服务(后端 zhpt-new)

同一份问卷,基于「wx_openid_hash 优先, device_id 兜底」的指纹识别同人,
按问卷配置的 submit_limit / submit_limit_period 校验。
优先级：
1. wx_openid_hash - 最准,同微信号跨设备不变
2. device_id      - 兜底,仅在 wx_openid 拿不到时使用(避免 code 换 openid 失败时无法防刷)
（openid 隐私合规改造：业务字段 wx_openid 仍保留用于支付，但指纹查询走 wx_openid_hash）

支持周期:
- once:    终身限 N 次
- day:     自然日内限 N 次
- week:    自然周内限 N 次(周一到周日)
- month:   自然月内限 N 次
- forever: 每天最多 1 次(永远可填,适合打卡)

特殊值:
- submit_limit = 0  → 不限制(仅受 max_answers 约束)
- submit_limit > 0  → 按周期限制
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from models.models import Student
from models.survey import OaSurveyAnswer
from utils.hash_util import hash_openid


VALID_PERIODS = ('once', 'day', 'week', 'month', 'forever')


@dataclass
class LimitCheckResult:
    """单次提交的次数校验结果"""
    allowed: bool
    used: int                  # 当前已提交次数(本次计入前)
    limit: int                 # 周期内允许的最大次数(0=不限)
    period: str                # 当前周期
    remaining: int             # 本周期内剩余次数(0=不限时永远 +∞ 用 -1 表示)
    message: str               # 文案(给前端展示)


def _period_window(period: str, now: datetime) -> tuple[datetime, datetime]:
    """返回 (start, end) 周期边界"""
    period = (period or 'once').lower()
    if period == 'once':
        return (datetime(1970, 1, 1), datetime(9999, 12, 31))
    if period == 'day':
        start = datetime(now.year, now.month, now.day)
        end = start + timedelta(days=1)
        return (start, end)
    if period == 'week':
        week_start = datetime(now.year, now.month, now.day) - timedelta(days=now.weekday())
        week_end = week_start + timedelta(days=7)
        return (week_start, week_end)
    if period == 'month':
        month_start = datetime(now.year, now.month, 1)
        if now.month == 12:
            month_end = datetime(now.year + 1, 1, 1)
        else:
            month_end = datetime(now.year, now.month + 1, 1)
        return (month_start, month_end)
    if period == 'forever':
        start = datetime(now.year, now.month, now.day)
        end = start + timedelta(days=1)
        return (start, end)
    return (datetime(1970, 1, 1), datetime(9999, 12, 31))


def _fingerprint_clause(wx_openid: Optional[str], device_id: Optional[str]):
    """
    构造指纹查询条件。

    优先级：
      1. wx_openid_hash（最准：同微信号跨设备不变，唯一稳定）
      2. device_id（兜底：仅在 openid 缺失时使用）
    """
    clauses = []
    wx_hash = hash_openid(wx_openid)
    if wx_hash:
        clauses.append(OaSurveyAnswer.wx_openid_hash == wx_hash)
    elif device_id:
        # 只有当 openid 拿不到时,才退回到 device_id 兜底
        clauses.append(OaSurveyAnswer.device_id == device_id)
    if not clauses:
        return None
    return or_(*clauses)


def count_used_in_period(
    db: Session,
    sid: int,
    wx_openid: Optional[str],
    device_id: Optional[str],
    period: str,
    now: Optional[datetime] = None,
) -> int:
    """查询当前周期内,此人已经提交了多少次"""
    if not wx_openid and not device_id:
        return 0

    now = now or datetime.now()
    start, _end = _period_window(period, now)
    fp = _fingerprint_clause(wx_openid, device_id)
    if fp is None:
        return 0

    stmt = select(func.count(OaSurveyAnswer.aid)).where(
        and_(
            OaSurveyAnswer.sid == sid,
            OaSurveyAnswer.status == 'SUBMITTED',
            fp,
            OaSurveyAnswer.submit_time >= start,
        )
    )
    return int(db.execute(stmt).scalar() or 0)


def check_submit_limit(
    db: Session,
    survey,
    wx_openid: Optional[str],
    device_id: Optional[str],
    now: Optional[datetime] = None,
) -> LimitCheckResult:
    """
    校验当前提交是否超限。
    返回 LimitCheckResult,前端根据 allowed 决定能否提交。
    """
    limit = int(getattr(survey, 'submit_limit', 1) or 0)
    period = (getattr(survey, 'submit_limit_period', 'once') or 'once').lower()
    if period not in VALID_PERIODS:
        period = 'once'

    if limit == 0:
        return LimitCheckResult(
            allowed=True,
            used=0,
            limit=0,
            period=period,
            remaining=-1,
            message='无限制',
        )

    now = now or datetime.now()
    used = count_used_in_period(db, survey.sid, wx_openid, device_id, period, now)
    remaining = max(limit - used, 0)

    if used >= limit:
        period_cn = {
            'once': '终身', 'day': '今天', 'week': '本周',
            'month': '本月', 'forever': '今天',
        }.get(period, '当前周期')
        return LimitCheckResult(
            allowed=False,
            used=used,
            limit=limit,
            period=period,
            remaining=0,
            message=f'您在{period_cn}已提交 {used} 次,该问卷最多允许 {limit} 次,无法再次提交',
        )

    return LimitCheckResult(
        allowed=True,
        used=used,
        limit=limit,
        period=period,
        remaining=remaining,
        message=f'本周期还可提交 {remaining} 次',
    )