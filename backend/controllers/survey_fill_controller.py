"""
问卷填写端 API (survey fill / public)
- GET /survey-fill/surveys/{sid}        → 获取问卷详情(脱敏)
- POST /survey-fill/surveys/{sid}/draft → 新建/更新草稿
- GET  /survey-fill/drafts/{aid}         → 获取草稿
- POST /survey-fill/surveys/{sid}/submit → 提交答卷
- POST /survey-fill/check-user           → 验证用户是否有权填写

功能对齐 docs/survey/02-features/06-answer-submit.md MVP 范围
"""
from fastapi import APIRouter, Depends, Query, Request, Header
from pydantic import BaseModel, Field
from sqlalchemy import func, text
from sqlalchemy.orm import Session
from typing import Optional, Any
from datetime import datetime
import json
import logging
import random
import string
import jwt as pyjwt

from init.dependencies import DatabaseDep, RedisDep
from common.auth import SECRET_KEY, ALGORITHM
from models.survey import (
    OaSurveySurvey,
    OaSurveyQuestion,
    OaSurveyAnswer,
    OaSurveyAnswerDetail,
    OaSurveyBlacklist,
)
from services.survey_submit_limit import check_submit_limit
from utils.survey_guard import check_ip_rate_limit, verify_submit_signature

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/survey-fill", tags=["问卷填写"])


def _ok(data: Any = None, msg: str = "ok") -> dict:
    return {"success": True, "msg": msg, "data": data}


def _fail(msg: str, code: int = 400) -> dict:
    return {"success": False, "msg": msg, "data": None}


def _optional_token(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    """
    可选 token：前端传了 Authorization:Bearer xxx 才解析，不传则返回 None。
    不会抛 401。
    """
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1]
    try:
        payload = pyjwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        # 忽略过期的 refresh token
        if payload.get("type") == "refresh":
            return None
        return payload
    except (pyjwt.ExpiredSignatureError, pyjwt.InvalidTokenError, Exception):
        return None


def _json_dumps(v) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, str):
        return v
    try:
        return json.dumps(v, ensure_ascii=False)
    except Exception:
        return str(v)


def _json_loads(text_val, default=None):
    if not text_val:
        return default
    if isinstance(text_val, (dict, list)):
        return text_val
    try:
        return json.loads(text_val)
    except Exception:
        return default


def _get_user_identity(token_payload: Optional[dict], wx_openid_from_body: Optional[str] = None) -> dict:
    """
    优先用请求 body 的 wx_openid（小程序前端自动传），
    次用 JWT payload 的 wx_openid（登录用户）。
    """
    # body 的 openid 优先级最高
    wx_oid = wx_openid_from_body or ""
    if not wx_oid and token_payload:
        wx_oid = token_payload.get("wx_openid") or ""

    if not token_payload:
        return {"user_type": "ANONYMOUS", "user_id": None, "user_name": None, "user_no": None, "wx_openid": wx_oid}

    ut = token_payload.get("user_type", "ANONYMOUS")
    uid = token_payload.get("user_id") or token_payload.get("id")
    un = token_payload.get("user_name") or token_payload.get("name") or token_payload.get("xm") or token_payload.get("teacher_name")
    un_no = token_payload.get("user_no") or token_payload.get("xh") or token_payload.get("teacher_code")
    return {
        "user_type": ut.upper() if ut else "ANONYMOUS",
        "user_id": uid,
        "user_name": un,
        "user_no": un_no,
        "wx_openid": wx_oid,
    }


# ============================================================
# Request/Response Models
# ============================================================

class AnswerSubmitIn(BaseModel):
    aid: Optional[int] = Field(None, description="草稿ID，有则续答")
    answers: list[dict] = Field(default_factory=list, description="[{\"qid\": \"q1\", \"value\": \"a\"}]")
    duration_sec: int = 0
    device_id: Optional[str] = Field(None, max_length=64)
    wx_openid: Optional[str] = Field(None, max_length=64, description="微信openid，匿名用户必须传")
    wx_code: Optional[str] = Field(None, max_length=64, description="微信code，提交时直接传code后端换openid")
    extra: Optional[dict] = None
    # ---- 反爬签名(可选,但强烈建议传) ----
    sig_ts: Optional[int] = Field(None, description="客户端时间戳(秒),用于防重放")
    sig_nonce: Optional[str] = Field(None, max_length=64)
    sig: Optional[str] = Field(None, max_length=128, description="HMAC-SHA256 签名")


class DraftSaveIn(BaseModel):
    aid: Optional[int] = Field(None, description="草稿ID")
    answers: list[dict] = Field(default_factory=list, description="当前作答")
    duration_sec: int = 0
    device_id: Optional[str] = Field(None, max_length=64)
    wx_openid: Optional[str] = Field(None, max_length=64, description="微信openid，匿名用户必须传")


# ============================================================
# 1. 获取问卷详情 (GET /survey-fill/surveys/{sid})
# ============================================================

@router.get("/surveys/{sid}", summary="获取问卷详情（填写页用）")
async def get_survey_for_fill(
    sid: int,
    request: Request,
    db: Session = DatabaseDep,
    token_payload: Optional[dict] = Depends(_optional_token),
):
    obj: OaSurveySurvey | None = (
        db.query(OaSurveySurvey)
        .filter(OaSurveySurvey.sid == sid, OaSurveySurvey.archived_at.is_(None))
        .first()
    )
    if not obj:
        return _fail("问卷不存在或已归档", 404)

    # 仅发布状态可填写
    if obj.status != "PUBLISHED":
        return _fail(f"问卷当前状态({obj.status})不可填写", 403)

    # 时间校验
    now = datetime.now()
    if obj.start_at and now < obj.start_at:
        return _fail(f"问卷尚未开始，请于 {obj.start_at.strftime('%m-%d %H:%M')} 后再来", 403)
    if obj.end_at and now > obj.end_at:
        return _fail("问卷已结束", 403)

    # settings 解析
    settings = _json_loads(obj.settings) or {}
    anti_repeat = settings.get("anti_repeat", {})

    # ---------- allow_users 权限检查 ----------
    allow_list: list[dict] = _json_loads(obj.allow_users) or []
    identity = _get_user_identity(token_payload)
    if allow_list:
        user_type = identity["user_type"]
        user_no = identity["user_no"]
        uid = identity["user_id"]
        # 简单匹配：user_no 需在某条规则的 user_no 字段中
        allowed = False
        for rule in allow_list:
            rule_ut = rule.get("user_type", "")
            rule_ids = rule.get("ids", [])
            rule_nos = rule.get("user_nos", [])
            if rule_ut and rule_ut.upper() == user_type.upper():
                if uid and uid in rule_ids:
                    allowed = True
                    break
                if user_no and str(user_no) in [str(n) for n in rule_nos]:
                    allowed = True
                    break
        if not allowed:
            return _fail("您不在允许填写的人员范围内", 403)

    wx_oid = identity.get("wx_openid") or ""

    # ---------- 拉题目 ----------
    questions = (
        db.query(OaSurveyQuestion)
        .filter(OaSurveyQuestion.sid == sid)
        .order_by(OaSurveyQuestion.order_no.asc(), OaSurveyQuestion.id.asc())
        .all()
    )

    # ---------- 解析出题目的 options/logic ----------
    result_questions = []
    for q in questions:
        opts = _json_loads(q.options) or []
        logic = _json_loads(q.logic) or []
        # 脱敏：不给 creator 相关信息
        result_questions.append({
            "id": q.id,
            "qid": q.qid,
            "qtype": q.qtype,
            "title": q.title,
            "description": q.description,
            "required": q.required,
            "options": opts,
            "logic": logic,
            "order_no": q.order_no,
            # 评分相关字段
            "score_min": q.score_min or 1,
            "score_max": q.score_max or 5,
            "scale_left_label": q.scale_left_label,
            "scale_right_label": q.scale_right_label,
            # 滑动条字段(SLIDER 题专用)
            "slider_min": q.slider_min if q.slider_min is not None else 0,
            "slider_max": q.slider_max if q.slider_max is not None else 100,
            "slider_step": q.slider_step if q.slider_step is not None else 1,
            "slider_unit": q.slider_unit or '',
            # 测评相关（填空页也拉，只是前端可能不用）
            "score": float(q.score) if q.score else 0,
            "correct_answer": q.correct_answer,
        })

    # ---------- 用户是否已提交 ----------
    already_submitted = False
    if wx_oid:
        from utils.hash_util import hash_openid
        wx_oid_hash = hash_openid(wx_oid)
        cnt = db.query(func.count(OaSurveyAnswer.aid)).filter(
            OaSurveyAnswer.sid == sid,
            OaSurveyAnswer.wx_openid_hash == wx_oid_hash,
            OaSurveyAnswer.status == "SUBMITTED",
        ).scalar()
        already_submitted = cnt and cnt > 0

    # ---- 次数限制 ----
    device_id_qs = (request.query_params.get("device_id") or "").strip()
    limit_result = check_submit_limit(
        db, obj, wx_openid=wx_oid, device_id=device_id_qs or None,
    )

    return _ok({
        "sid": obj.sid,
        "survey_code": obj.survey_code,
        "title": obj.title,
        "subtitle": "",
        "description": obj.description or "",
        "survey_type": obj.survey_type,
        "is_anonymous": bool(obj.is_anonymous),
        "max_answers": obj.max_answers,
        # ---- 次数限制字段 ----
        "submit_limit": int(getattr(obj, "submit_limit", 1) or 1),
        "submit_limit_period": (getattr(obj, "submit_limit_period", "once") or "once"),
        "submit_used": limit_result.used,
        "submit_remaining": limit_result.remaining,
        "submit_can_submit": limit_result.allowed,
        "submit_message": limit_result.message,
        "start_at": obj.start_at.isoformat() if obj.start_at else None,
        "end_at": obj.end_at.isoformat() if obj.end_at else None,
        "settings": settings,
        "sub_config": _json_loads(obj.sub_config) or {},
        "questions": result_questions,
        "already_submitted": already_submitted,
        # 填写者身份信息(前端用 openid 识别)
        "identity": {
            "user_type": identity["user_type"],
            "user_name": identity["user_name"],
            "user_no": identity["user_no"],
            "wx_openid": identity["wx_openid"],
        },
    })


# ============================================================
# 1b. 通过 survey_code 获取问卷详情 (GET /survey-fill/surveys/by-code/{code})
# ============================================================
@router.get("/surveys/by-code/{code}", summary="通过分享码获取问卷详情")
async def get_survey_by_code(
    code: str,
    request: Request,
    db: Session = DatabaseDep,
    token_payload: Optional[dict] = Depends(_optional_token),
):
    """与 get_survey_for_fill 功能完全相同，但用 survey_code 查找"""
    obj: OaSurveySurvey | None = (
        db.query(OaSurveySurvey)
        .filter(
            OaSurveySurvey.survey_code == code,
            OaSurveySurvey.archived_at.is_(None),
        )
        .first()
    )
    if not obj:
        return _fail("问卷不存在或已归档", 404)

    # 仅发布状态可填写
    if obj.status != "PUBLISHED":
        return _fail(f"问卷当前状态({obj.status})不可填写", 403)

    # 时间校验
    now = datetime.now()
    if obj.start_at and now < obj.start_at:
        return _fail(f"问卷尚未开始，请于 {obj.start_at.strftime('%m-%d %H:%M')} 后再来", 403)
    if obj.end_at and now > obj.end_at:
        return _fail("问卷已结束", 403)

    # settings 解析
    settings = _json_loads(obj.settings) or {}
    allow_list: list[dict] = _json_loads(obj.allow_users) or []
    identity = _get_user_identity(token_payload)

    if allow_list:
        user_type = identity["user_type"]
        user_no = identity["user_no"]
        uid = identity["user_id"]
        allowed = False
        for rule in allow_list:
            rule_ut = rule.get("user_type", "")
            rule_ids = rule.get("ids", [])
            rule_nos = rule.get("user_nos", [])
            if rule_ut and rule_ut.upper() == user_type.upper():
                if uid and uid in rule_ids:
                    allowed = True
                    break
                if user_no and str(user_no) in [str(n) for n in rule_nos]:
                    allowed = True
                    break
        if not allowed:
            return _fail("您不在允许填写的人员范围内", 403)

    questions = (
        db.query(OaSurveyQuestion)
        .filter(OaSurveyQuestion.sid == obj.sid)
        .order_by(OaSurveyQuestion.order_no.asc(), OaSurveyQuestion.id.asc())
        .all()
    )

    result_questions = []
    for q in questions:
        opts = _json_loads(q.options) or []
        logic = _json_loads(q.logic) or []
        result_questions.append({
            "id": q.id,
            "qid": q.qid,
            "qtype": q.qtype,
            "title": q.title,
            "description": q.description,
            "required": q.required,
            "options": opts,
            "logic": logic,
            "order_no": q.order_no,
            "score_min": q.score_min or 1,
            "score_max": q.score_max or 5,
            "scale_left_label": q.scale_left_label,
            "scale_right_label": q.scale_right_label,
            "slider_min": q.slider_min if q.slider_min is not None else 0,
            "slider_max": q.slider_max if q.slider_max is not None else 100,
            "slider_step": q.slider_step if q.slider_step is not None else 1,
            "slider_unit": q.slider_unit or '',
            "score": float(q.score) if q.score else 0,
            "correct_answer": q.correct_answer,
        })

    wx_oid = identity.get("wx_openid") or ""
    already_submitted = False
    if wx_oid:
        from utils.hash_util import hash_openid
        wx_oid_hash = hash_openid(wx_oid)
        existing = db.query(OaSurveyAnswer).filter(
            OaSurveyAnswer.sid == obj.sid,
            OaSurveyAnswer.wx_openid_hash == wx_oid_hash,
            OaSurveyAnswer.status.in_(["SUBMITTED", "APPROVED"]),
        ).first()
        already_submitted = existing is not None

    # ---- 次数限制 + 本周期已用次数(用于前端展示) ----
    # 前端在请求里带上 device_id(GET 参数或 body 都行,这里统一走 query string)
    device_id_qs = (request.query_params.get("device_id") or "").strip()
    limit_result = check_submit_limit(
        db, obj, wx_openid=wx_oid, device_id=device_id_qs or None,
    )

    return _ok({
        "sid": obj.sid,
        "survey_code": obj.survey_code,
        "title": obj.title,
        "subtitle": "",
        "description": obj.description or "",
        "survey_type": obj.survey_type,
        "is_anonymous": obj.is_anonymous,
        "max_answers": obj.max_answers,
        # ---- 次数限制字段(给前端展示) ----
        "submit_limit": int(getattr(obj, "submit_limit", 1) or 1),
        "submit_limit_period": (getattr(obj, "submit_limit_period", "once") or "once"),
        "submit_used": limit_result.used,
        "submit_remaining": limit_result.remaining,
        "submit_can_submit": limit_result.allowed,
        "submit_message": limit_result.message,
        "start_at": obj.start_at.isoformat() if obj.start_at else None,
        "end_at": obj.end_at.isoformat() if obj.end_at else None,
        "already_submitted": already_submitted,
        "questions": result_questions,
        "settings": settings,
        "identity": {
            "user_type": identity["user_type"],
            "user_id": identity["user_id"],
            "user_name": identity["user_name"],
            "user_no": identity["user_no"],
            "wx_openid": identity["wx_openid"],
        },
    })


# ============================================================
# 1c. 获取/生成分享码 (GET /survey-fill/surveys/{sid}/share)
# ============================================================
@router.get("/surveys/{sid}/share", summary="获取或生成问卷分享码")
async def get_or_generate_share_code(
    sid: int,
    db: Session = DatabaseDep,
):
    """已有 code 直接返回，没有则生成一个新的"""
    obj = db.query(OaSurveySurvey).filter(
        OaSurveySurvey.sid == sid,
        OaSurveySurvey.archived_at.is_(None),
    ).first()
    if not obj:
        return _fail("问卷不存在", 404)

    if not obj.survey_code:
        # 生成 8 位随机码（避免与已有码冲突）
        for _ in range(10):
            code = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
            exists = db.query(OaSurveySurvey).filter(
                OaSurveySurvey.survey_code == code,
                OaSurveySurvey.sid != sid,
            ).first()
            if not exists:
                obj.survey_code = code
                db.commit()
                db.refresh(obj)
                break

    return _ok({
        "sid": obj.sid,
        "survey_code": obj.survey_code,
        "share_url": f"/survey-fill?code={obj.survey_code}",
    })



# ============================================================
# 2. 新建草稿 (POST /survey-fill/surveys/{sid}/draft)
# ============================================================

@router.post("/surveys/{sid}/draft", summary="创建或更新草稿")
async def save_draft(
    sid: int,
    payload: DraftSaveIn,
    request: Request,
    db: Session = DatabaseDep,
    token_payload: Optional[dict] = Depends(_optional_token),
):
    obj = db.query(OaSurveySurvey).filter(
        OaSurveySurvey.sid == sid,
        OaSurveySurvey.archived_at.is_(None),
    ).first()
    if not obj:
        return _fail("问卷不存在", 404)
    if obj.status != "PUBLISHED":
        return _fail("问卷未发布", 403)

    identity = _get_user_identity(token_payload, payload.wx_openid)
    wx_oid = identity.get("wx_openid") or ""
    device_id = payload.device_id or ""
    from utils.hash_util import hash_openid
    wx_oid_hash = hash_openid(wx_oid)

    # 查找已有草稿
    draft = db.query(OaSurveyAnswer).filter(
        OaSurveyAnswer.sid == sid,
        OaSurveyAnswer.status == "DRAFT",
        OaSurveyAnswer.wx_openid_hash == (wx_oid_hash if wx_oid_hash else None),
    ).order_by(OaSurveyAnswer.aid.desc()).first()

    if draft:
        # 更新草稿
        draft.payload = _json_dumps({"answers": payload.answers})
        draft.duration_sec = payload.duration_sec or 0
        draft.device_id = device_id or draft.device_id
        draft.ip = request.client.host if request.client else None
        aid = draft.aid
    else:
        # 新建草稿
        draft = OaSurveyAnswer(
            sid=sid,
            user_id=identity.get("user_id"),
            user_type=identity["user_type"],
            user_name=identity.get("user_name"),
            user_no=identity.get("user_no"),
            wx_openid=wx_oid,
            wx_openid_hash=wx_oid_hash,
            device_id=device_id,
            ip=request.client.host if request.client else None,
            ua=(request.headers.get("user-agent") or "")[:255],
            status="DRAFT",
            duration_sec=payload.duration_sec or 0,
            payload=_json_dumps({"answers": payload.answers}),
        )
        db.add(draft)
        db.flush()
        aid = draft.aid

    db.commit()
    return _ok({"aid": aid, "status": "DRAFT"})


# ============================================================
# 3. 获取草稿 (GET /survey-fill/drafts/{aid})
# ============================================================

@router.get("/drafts/{aid}", summary="获取草稿")
async def get_draft(
    aid: int,
    db: Session = DatabaseDep,
    token_payload: Optional[dict] = Depends(_optional_token),
):
    draft = db.get(OaSurveyAnswer, aid)
    if not draft or draft.status != "DRAFT":
        return _fail("草稿不存在或已提交", 404)

    # 校验归属（wx_openid_hash 一致或匿名）
    identity = _get_user_identity(token_payload)
    wx_oid = identity.get("wx_openid") or ""
    from utils.hash_util import hash_openid
    wx_oid_hash = hash_openid(wx_oid)
    if draft.wx_openid_hash and wx_oid_hash and draft.wx_openid_hash != wx_oid_hash:
        return _fail("无权访问该草稿", 403)

    payload_data = _json_loads(draft.payload) or {}
    return _ok({
        "aid": draft.aid,
        "sid": draft.sid,
        "answers": payload_data.get("answers", []),
        "duration_sec": draft.duration_sec,
        "updated_at": draft.updated_at.isoformat() if draft.updated_at else None,
    })


# ============================================================
# 4. 提交答卷 (POST /survey-fill/surveys/{sid}/submit)
# ============================================================

@router.post("/surveys/{sid}/submit", summary="提交答卷")
async def submit_answer(
    sid: int,
    payload: AnswerSubmitIn,
    request: Request,
    db: Session = DatabaseDep,
    redis_client = RedisDep,
    token_payload: Optional[dict] = Depends(_optional_token),
):
    obj: OaSurveySurvey | None = db.query(OaSurveySurvey).filter(
        OaSurveySurvey.sid == sid,
        OaSurveySurvey.archived_at.is_(None),
    ).first()
    if not obj:
        return _fail("问卷不存在", 404)
    if obj.status != "PUBLISHED":
        return _fail("问卷未发布", 403)

    now = datetime.now()
    if obj.start_at and now < obj.start_at:
        return _fail("问卷尚未开始", 403)
    if obj.end_at and now > obj.end_at:
        return _fail("问卷已结束", 403)

    settings = _json_loads(obj.settings) or {}
    anti_repeat = settings.get("anti_repeat", {})
    anti_cheat = settings.get("anti_cheat", {})
    submission_cfg = settings.get("submission", {})

    # ---------- 防滥用:IP 滑窗限频 ----------
    ip_allowed, ip_msg = check_ip_rate_limit(redis_client, request, sid)
    if not ip_allowed:
        return _fail(ip_msg, 429)

    # ---------- 防滥用:签名校验(防重放 + 防裸 curl) ----------
    sig_ok, sig_msg = verify_submit_signature(
        redis_client,
        sid,
        payload.sig_ts,
        payload.sig_nonce,
        payload.sig,
        payload.answers,
    )
    if not sig_ok:
        return _fail(sig_msg, 401)

    # ---------- 微信 code 转 openid ----------
    wx_oid = ""
    if payload.wx_code:
        try:
            from utils.wx_utils import WxUtils
            result = WxUtils.get_openid_and_session_key(payload.wx_code)
            if result and result.get("openid"):
                wx_oid = result["openid"]
        except Exception as e:
            logger.warning(f"[survey-fill] code2openid in submit failed: {e}")

    # identity 正常调用，wx_openid 优先用 code 换来的
    identity = _get_user_identity(token_payload, payload.wx_openid)
    if wx_oid:
        identity["wx_openid"] = wx_oid

    wx_oid = identity.get("wx_openid") or ""
    device_id = payload.device_id or ""
    client_ip = request.client.host if request.client else ""
    from utils.hash_util import hash_openid
    wx_oid_hash = hash_openid(wx_oid)

    # ---------- 提交次数限制(wx_openid_hash + device_id 联合指纹) ----------
    limit_result = check_submit_limit(
        db, obj, wx_openid=wx_oid, device_id=device_id or None,
    )
    if not limit_result.allowed:
        return _fail(limit_result.message, 4001)

    # ---------- 防重复 ----------
    if anti_repeat.get("wx_account_limit") and wx_oid_hash:
        cnt = db.query(func.count(OaSurveyAnswer.aid)).filter(
            OaSurveyAnswer.sid == sid,
            OaSurveyAnswer.wx_openid_hash == wx_oid_hash,
            OaSurveyAnswer.status == "SUBMITTED",
        ).scalar()
        if cnt and cnt > 0:
            return _fail("您已经提交过该问卷", 400)

    if anti_repeat.get("ip_limit"):
        limit = anti_repeat.get("ip_limit", 1)
        # 每日限制
        from datetime import timedelta
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        cnt = db.query(func.count(OaSurveyAnswer.aid)).filter(
            OaSurveyAnswer.sid == sid,
            OaSurveyAnswer.ip == client_ip,
            OaSurveyAnswer.status == "SUBMITTED",
            OaSurveyAnswer.submit_time >= today_start,
        ).scalar()
        if cnt and cnt >= limit:
            return _fail(f"同一IP每日提交上限为{limit}次", 400)

    if anti_repeat.get("device_limit") and device_id:
        cnt = db.query(func.count(OaSurveyAnswer.aid)).filter(
            OaSurveyAnswer.sid == sid,
            OaSurveyAnswer.device_id == device_id,
            OaSurveyAnswer.status == "SUBMITTED",
        ).scalar()
        if cnt and cnt > 0:
            return _fail("该设备已提交过", 400)

    # 黑名单检查（优先按 hash 列查，兼容老数据按 blacklist_value）
    if wx_oid_hash:
        bl = db.query(OaSurveyBlacklist).filter(
            OaSurveyBlacklist.scope == "wx_openid",
            (OaSurveyBlacklist.blacklist_value_hash == wx_oid_hash)
            | (OaSurveyBlacklist.blacklist_value == wx_oid)
        ).first()
        if bl:
            return _fail("您的账号存在异常，无法提交", 403)
    bl_ip = db.query(OaSurveyBlacklist).filter(
        OaSurveyBlacklist.scope == "ip",
        OaSurveyBlacklist.blacklist_value == client_ip,
    ).first()
    if bl_ip:
        return _fail("当前网络环境存在异常，无法提交", 403)

    # ---------- 答卷数上限 ----------
    if obj.max_answers and obj.max_answers > 0:
        cnt = db.query(func.count(OaSurveyAnswer.aid)).filter(
            OaSurveyAnswer.sid == sid,
            OaSurveyAnswer.status == "SUBMITTED",
        ).scalar()
        if cnt and cnt >= obj.max_answers:
            return _fail("答卷已达上限", 400)

    # ---------- 必填校验 ----------
    questions = {
        q.qid: q for q in
        db.query(OaSurveyQuestion).filter(OaSurveyQuestion.sid == sid).all()
    }
    errors = []
    answers_map = {a["qid"]: a["value"] for a in payload.answers if "qid" in a}
    for qid, q in questions.items():
        if q.required:
            v = answers_map.get(qid)
            if v is None or v == "" or v == []:
                errors.append({"qid": qid, "message": f"「{q.title or qid}」为必填项"})

    if errors:
        return {"success": False, "msg": "请检查必填项", "data": {"errors": errors}}

    # ---------- 写入答卷 ----------
    # 如果有 aid（草稿续答）→ 删除旧 SUBMITTED 记录后再插；否则直接新增
    existing = None
    if payload.aid:
        existing = db.get(OaSurveyAnswer, payload.aid)
        if existing and existing.status == "SUBMITTED":
            existing = None  # 忽略已提交的 aid

    if existing and existing.status == "DRAFT":
        # 删除旧草稿，重新创建
        db.delete(existing)
        db.flush()

    answer = OaSurveyAnswer(
        sid=sid,
        user_id=identity.get("user_id"),
        user_type=identity["user_type"],
        user_name=identity.get("user_name") if not obj.is_anonymous else None,
        user_no=identity.get("user_no") if not obj.is_anonymous else None,

        wx_openid_hash=wx_oid_hash,  # 微信openid的SHA256哈希，用于后期对接查询用户信息
        device_id=device_id,
        ip=client_ip,
        ua=(request.headers.get("user-agent") or "")[:255],
        status="SUBMITTED",
        duration_sec=payload.duration_sec or 0,
        submit_time=now,
        payload=_json_dumps({"answers": payload.answers}),
        extra=_json_dumps(payload.extra),
    )
    db.add(answer)
    db.flush()
    aid = answer.aid

    # ---------- 写入答卷明细 ----------
    for item in (payload.answers or []):
        try:
            detail_value = item.get("value")
            if isinstance(detail_value, (dict, list)):
                detail_value = _json_dumps(detail_value)
            detail = OaSurveyAnswerDetail(
                aid=aid,
                qid=str(item.get("qid", ""))[:32],
                qtype=str(item.get("qtype", ""))[:32],
                detail_value=str(detail_value)[:8000] if detail_value is not None else None,
                value_text=str(item.get("value_text", ""))[:8000] or None,
            )
            db.add(detail)
        except Exception as e:
            logger.warning(f"[survey-fill] answer detail failed: {e}")

    db.commit()

    # ---------- 提交后跳转 ----------
    redirect_cfg = settings.get("redirect", {})
    redirect = {
        "kind": redirect_cfg.get("kind", "NONE"),
        "url": redirect_cfg.get("url"),
        "inner_path": redirect_cfg.get("inner_path"),
        "delay_sec": redirect_cfg.get("delay_sec", 0),
    }

    return _ok({
        "aid": aid,
        "sid": sid,
        "status": "SUBMITTED",
        "submit_time": now.isoformat(),
        # ---- 提交后剩余次数(给前端展示用) ----
        "submit_limit": limit_result.limit,
        "submit_limit_period": limit_result.period,
        "submit_used": limit_result.used + 1,   # 本次计入
        "submit_remaining": max(limit_result.limit - (limit_result.used + 1), 0),
        "submit_can_submit": (limit_result.used + 1) < (limit_result.limit or 1),
        "redirect": redirect,
    })


# ============================================================
# 5. 验证用户权限 (POST /survey-fill/check-user)
# ============================================================

@router.post("/check-user", summary="验证用户是否有权填写指定问卷")
async def check_user_fill_permission(
    sid: int = Query(..., description="问卷ID"),
    user_type: str = Query(..., description="用户类型"),
    user_no: str = Query(..., description="学号/工号"),
    user_id: Optional[int] = Query(None, description="用户ID"),
    db: Session = DatabaseDep,
    token_payload: Optional[dict] = Depends(_optional_token),
):
    """
    前端在填写前调用此接口验证用户身份。
    逻辑与 get_survey_for_fill 中的 allow_users 检查一致。
    """
    obj = db.get(OaSurveySurvey, sid)
    if not obj or obj.archived_at:
        return _fail("问卷不存在", 404)

    allow_list: list[dict] = _json_loads(obj.allow_users) or []
    if not allow_list:
        return _ok({"allowed": True, "reason": "无人员限制"})

    allowed = False
    for rule in allow_list:
        rule_ut = rule.get("user_type", "")
        rule_ids = rule.get("ids", [])
        rule_nos = rule.get("user_nos", [])
        if rule_ut and rule_ut.upper() == user_type.upper():
            if user_id and user_id in rule_ids:
                allowed = True
                break
            if user_no and str(user_no) in [str(n) for n in rule_nos]:
                allowed = True
                break

    if not allowed:
        return _ok({"allowed": False, "reason": "您不在允许填写的人员范围内"})

    return _ok({"allowed": True, "reason": "验证通过"})


# ============================================================
# 6. 通过微信 code 换 openid (POST /survey-fill/wx/code2openid)
# ============================================================

@router.post("/wx/code2openid", summary="微信 code 换 openid")
async def code_to_openid(
    body: dict,
    db: Session = DatabaseDep,
):
    """
    小程序前端通过 wx.login() 获取 code，
    传给后端换取 openid。
    用于匿名用户也能记录 openid。
    """
    code = body.get("code")
    if not code:
        return _fail("缺少 code 参数", 400)

    try:
        from utils.wx_utils import WxUtils
        result = WxUtils.get_openid_and_session_key(code)
        if not result:
            return _fail("换取 openid 失败，请重试", 500)
        return _ok({"openid": result.get("openid"), "session_key": result.get("session_key")})
    except Exception as e:
        logger.warning(f"[survey-fill] code2openid error: {e}")
        return _fail("换取 openid 失败", 500)


# ============================================================
# 7. 问卷列表 (GET /survey-fill/list)
#   - 用户小程序首页"问卷调查"入口
#   - 仅返回 PUBLISHED + 在时间窗内 + (未限定人群 或 当前用户匹配) 的问卷
# ============================================================
@router.get("/list", summary="小程序端问卷列表")
async def list_surveys(
    keyword: Optional[str] = Query(None, description="关键词搜索(标题/描述)"),
    survey_type: Optional[str] = Query(None, description="类型筛选:SURVEY/REGISTRATION/VOTE/EXAM"),
    only_available: bool = Query(True, description="仅展示可填写的(过滤未开始/已结束)"),
    request: Request = None,
    db: Session = DatabaseDep,
    token_payload: Optional[dict] = Depends(_optional_token),
):
    """
    返回可填写的问卷列表。
    每条记录包含 sid / title / description / survey_type / start_at / end_at /
    survey_code / estimated_minutes / answered(当前用户是否已提交过)。
    """
    identity = _get_user_identity(token_payload)
    user_type = identity["user_type"]
    user_id = identity["user_id"]
    user_no = identity["user_no"]

    now = datetime.now()

    q = db.query(OaSurveySurvey).filter(
        OaSurveySurvey.status == "PUBLISHED",
        OaSurveySurvey.archived_at.is_(None),
    )
    if survey_type:
        q = q.filter(OaSurveySurvey.survey_type == survey_type)
    if keyword:
        like = f"%{keyword.strip()}%"
        q = q.filter(
            (OaSurveySurvey.title.like(like)) |
            (OaSurveySurvey.description.like(like))
        )
    if only_available:
        q = q.filter(
            (OaSurveySurvey.start_at.is_(None)) | (OaSurveySurvey.start_at <= now),
            (OaSurveySurvey.end_at.is_(None)) | (OaSurveySurvey.end_at >= now),
        )
    items = q.order_by(OaSurveySurvey.created_at.desc()).limit(200).all()

    result = []
    for obj in items:
        # allow_users 过滤(未登录用户仅展示未限定的)
        allow_list = _json_loads(obj.allow_users) or []
        if allow_list:
            if not user_type or user_type == "ANONYMOUS":
                continue
            allowed = False
            for rule in allow_list:
                rule_ut = rule.get("user_type", "")
                rule_ids = rule.get("ids", [])
                rule_nos = rule.get("user_nos", [])
                if rule_ut and rule_ut.upper() == user_type.upper():
                    if user_id and user_id in rule_ids:
                        allowed = True
                        break
                    if user_no and str(user_no) in [str(n) for n in rule_nos]:
                        allowed = True
                        break
            if not allowed:
                continue

        # 当前用户是否已答过(仅查 SUBMITTED 状态的去重)
        answered = False
        last_answer_aid = None
        last_submit_time = None
        if user_id:
            ans = db.query(OaSurveyAnswer).filter(
                OaSurveyAnswer.sid == obj.sid,
                OaSurveyAnswer.user_id == user_id,
                OaSurveyAnswer.status == "SUBMITTED",
            ).order_by(OaSurveyAnswer.submit_time.desc()).first()
            if ans:
                answered = True
                last_answer_aid = ans.aid
                last_submit_time = ans.submit_time

        # 时间窗状态文案
        if obj.start_at and now < obj.start_at:
            status_text = f"{obj.start_at.strftime('%m-%d %H:%M')} 开始"
            available = False
        elif obj.end_at and now > obj.end_at:
            status_text = "已结束"
            available = False
        else:
            status_text = "进行中"
            available = True

        result.append({
            "sid": obj.sid,
            "survey_code": obj.survey_code,
            "title": obj.title,
            "subtitle": obj.description or "",
            "survey_type": obj.survey_type,
            "is_anonymous": obj.is_anonymous,
            "max_answers": obj.max_answers,
            "submit_limit": obj.submit_limit,
            "submit_limit_period": obj.submit_limit_period,
            "start_at": obj.start_at.isoformat() if obj.start_at else None,
            "end_at": obj.end_at.isoformat() if obj.end_at else None,
            "status_text": status_text,
            "available": available,
            "answered": answered,
            "last_answer_aid": last_answer_aid,
            "last_submit_time": last_submit_time.isoformat() if last_submit_time else None,
        })

    return _ok({
        "total": len(result),
        "list": result,
    })
