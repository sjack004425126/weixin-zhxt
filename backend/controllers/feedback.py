"""校园问题反馈系统 - 控制器
覆盖:用户端提交/列表/详情/撤回/上传 + 管理端列表/详情/办结/驳回 + 短信回调办结通知
"""
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from fastapi.responses import Response, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_, and_, func
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import os
import json
import uuid
import logging

import jwt as pyjwt
import time

from init.dependencies import DatabaseDep
from common.auth import verify_token_and_get_payload, SECRET_KEY, ALGORITHM
from models.models import (
    FeedbackTicket, FeedbackTimeline, Teacher, Student, ZzXs, ZzBj,
    Staff, FeedbackDict, FeedbackAdmin, FeedbackLocation, FeedbackLocationType,
)
# 注：旧硬编码白名单仅作为启动时保底种子使用（见 services/feedback_init.py）
# 运行时一律改读 FeedbackAdmin 表，下方提供新的 is_feedback_admin / get_admin_info 实现
from utils.sms import SMSTool
from services.feedback_image_service import (
    delete_image as mio_delete,
    get_signed_url,
    media_type_of,
    ext_of as mio_ext_of,
    IMAGE_EXTS,
    VIDEO_EXTS,
    ALL_EXTS,
    CONTENT_TYPE_MAP,
)
import re

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/feedback", tags=["校园反馈"])

# ============== 反馈专属双 Token 配置 ==============

FEEDBACK_ACCESS_TOKEN_TTL  = 2 * 60 * 60          # 2 小时
FEEDBACK_REFRESH_TOKEN_TTL = 30 * 24 * 60 * 60    # 30 天
FEEDBACK_REFRESH_SECRET    = SECRET_KEY + "_fb_refresh"


def _create_feedback_access_token(payload: dict) -> str:
    data = {**payload, "type": "fb_access", "exp": int(time.time()) + FEEDBACK_ACCESS_TOKEN_TTL}
    return pyjwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)


def _create_feedback_refresh_token(payload: dict) -> str:
    data = {**payload, "type": "fb_refresh", "exp": int(time.time()) + FEEDBACK_REFRESH_TOKEN_TTL}
    return pyjwt.encode(data, FEEDBACK_REFRESH_SECRET, algorithm=ALGORITHM)


# ============== 工具函数 ==============

def _ok(data=None, msg="ok"):
    return {"success": True, "msg": msg, "data": data}


def _fail(msg: str, code: int = 400):
    return {"success": False, "msg": msg, "data": None}


def resolve_user(payload: dict, db: Session) -> Optional[dict]:
    """根据 token payload 识别 5 类用户身份并返回统一信息"""
    if not payload:
        return None
    # 0) 工作人员 - is_staff=True
    if payload.get("is_staff") or payload.get("staff_id") is not None:
        sid = payload.get("staff_id")
        s = db.query(Staff).filter(Staff.id == sid).first()
        if not s:
            return None
        return {
            "user_type": "staff",
            "user_id": str(s.id),
            "name": s.name or "",
            "phone": (s.phone or "").strip(),
            "dept": s.department or "",
        }
    # 1) 开放教师 - is_open_teacher=True
    if payload.get("is_open_teacher"):
        t_id = payload.get("t_id")
        t = db.query(Teacher).filter(Teacher.t_id == t_id).first()
        if not t:
            return None
        return {
            "user_type": "open_teacher",
            "user_id": str(t.t_id),
            "name": t.t_xm or "",
            "phone": (t.t_dh or "").strip(),
            "dept": str(t.t_bm_id or ""),
        }
    # 2) 中职教师 - 仅 t_id,无 is_open_teacher
    if payload.get("t_id") is not None and payload.get("xs_xh") is None:
        t_id = payload.get("t_id")
        t = db.query(Teacher).filter(Teacher.t_id == t_id).first()
        if not t:
            return None
        return {
            "user_type": "vocational_teacher",
            "user_id": str(t.t_id),
            "name": t.t_xm or "",
            "phone": (t.t_dh or "").strip(),
            "dept": str(t.t_bm_id or ""),
        }
    # 3) 中职学生 - xs_id 存在
    if payload.get("xs_id") is not None:
        s = db.query(ZzXs).filter(ZzXs.id == payload.get("xs_id")).first()
        if not s:
            return None
        bj = db.query(ZzBj).filter(ZzBj.id == s.bj_id).first() if s.bj_id else None
        return {
            "user_type": "vocational_student",
            "user_id": str(s.id),
            "name": s.xm or "",
            "phone": (s.xsdh or "").strip(),
            "dept": (bj.mc if bj else ""),
        }
    # 4) 开放学生 - xs_xh 存在,无 xs_id
    if payload.get("xs_xh"):
        s = db.query(Student).filter(Student.xs_xh == payload.get("xs_xh")).first()
        if not s:
            return None
        return {
            "user_type": "open_student",
            "user_id": str(s.xs_id),
            "name": s.xs_xm or "",
            "phone": (s.xs_dh or "").strip(),
            "dept": str(s.xs_bj_id or ""),
        }
    return None


def require_user(payload: dict = Depends(verify_token_and_get_payload), db: Session = DatabaseDep):
    user = resolve_user(payload, db)
    if not user:
        raise HTTPException(status_code=401, detail="无法识别用户身份,请重新登录")
    return user


# ---- 反馈管理员权限（运行时一律读 FeedbackAdmin 表） ----

_ROLE_ORDER = {"viewer": 1, "handler": 2, "manager": 3, "super": 4}
_ROLE_LABELS = {
    "super": "超级管理员",
    "manager": "管理员",
    "handler": "处理员",
    "viewer": "观察员",
}


def get_admin_info(db: Session, phone: str) -> Optional[FeedbackAdmin]:
    """按手机号定位激活的管理员记录；未找到返回 None"""
    if not phone:
        return None
    phone = str(phone).strip()
    return db.query(FeedbackAdmin).filter(
        FeedbackAdmin.phone_snapshot == phone,
        FeedbackAdmin.is_active == True,  # noqa: E712
    ).first()


def is_feedback_admin(db: Session, phone: str) -> bool:
    return get_admin_info(db, phone) is not None


def _role_at_least(role: str, min_role: str) -> bool:
    return _ROLE_ORDER.get(role or "", 0) >= _ROLE_ORDER.get(min_role, 0)


def require_admin(
    min_role: str = "handler",
):
    """生成依赖：要求当前 token 对应 FeedbackAdmin 表中至少 min_role 角色

    用法：
        user: dict = Depends(require_admin())                  # 默认 handler 及以上
        user: dict = Depends(require_admin("manager"))         # 仅 manager / super
    """
    def _dep(
        payload: dict = Depends(verify_token_and_get_payload),
        db: Session = DatabaseDep,
    ) -> dict:
        user = resolve_user(payload, db)
        if not user:
            raise HTTPException(status_code=401, detail="未登录")
        admin = get_admin_info(db, user.get("phone"))
        if not admin:
            raise HTTPException(status_code=403, detail="无管理权限")
        if not _role_at_least(admin.role, min_role):
            raise HTTPException(status_code=403, detail=f"需要 {min_role} 及以上角色")
        user["admin_role"] = admin.role
        user["admin_name"] = admin.name_snapshot or user["name"]
        user["admin_id"] = admin.id
        user["admin_scope"] = admin.scope_codes or ""
        user["admin_department"] = admin.department or ""
        # 严格以数据库字段为准，所有角色（含 super/manager）均受 can_view_suggestion 控制
        user["can_view_suggestion"] = bool(admin.can_view_suggestion)
        return user
    return _dep


# ============== 反馈专属登录（微信手机号一键授权） ==============

class PhoneLoginReq(BaseModel):
    code: str = Field(..., description="小程序 getPhoneNumber 返回的 code")
    # 7 天手机号缓存：可选字段
    login_code: Optional[str] = None
    subject: Optional[str] = None


class RefreshReq(BaseModel):
    refresh_token: str = Field(..., description="反馈模块专属 refresh token")


def _match_phone(db: Session, phone: str) -> Optional[dict]:
    """按优先级在 5 张用户表里匹配手机号；返回 token payload + identity dict

    优先级：staff > teacher > open_student > vocational_student
    （教师不区分中职/开放，统一查 oa_t 表；这里登记为 open_teacher 类型，
     resolve_user 中两种类型都查 Teacher）
    """
    if not phone:
        return None
    phone = str(phone).strip()

    # 1) 工作人员
    s = db.query(Staff).filter(Staff.phone == phone, Staff.status == 'active').first()
    if s:
        return {
            "token_payload": {
                "staff_id": s.id, "is_staff": True,
                "name": s.name, "phone": phone,
            },
            "identity": {
                "user_type": "staff", "user_id": str(s.id),
                "name": s.name or "", "phone": phone,
                "department": s.department or "", "position": s.position or "",
            },
        }

    # 2) 教师（统一 oa_t）
    t = db.query(Teacher).filter(Teacher.t_dh == phone).first()
    if t:
        return {
            "token_payload": {
                "t_id": t.t_id, "t_yhm": t.t_yhm, "t_xm": t.t_xm,
                "is_open_teacher": True,  # 反馈模块统一作为 open_teacher 处理
            },
            "identity": {
                "user_type": "open_teacher", "user_id": str(t.t_id),
                "name": t.t_xm or "", "phone": phone,
                "department": str(t.t_bm_id or ""), "position": t.t_zc or "",
            },
        }

    # 3) 开放学生
    os_ = db.query(Student).filter(Student.xs_dh == phone).first()
    if os_:
        return {
            "token_payload": {
                "xs_xh": os_.xs_xh, "xs_xm": os_.xs_xm, "xs_id": os_.xs_id,
            },
            "identity": {
                "user_type": "open_student", "user_id": str(os_.xs_id),
                "name": os_.xs_xm or "", "phone": phone,
                "department": str(os_.xs_bj_id or ""), "position": "",
            },
        }

    # 4) 中职学生
    vs = db.query(ZzXs).filter(ZzXs.xsdh == phone).first()
    if vs:
        bj = db.query(ZzBj).filter(ZzBj.id == vs.bj_id).first() if vs.bj_id else None
        return {
            "token_payload": {
                "xs_id": vs.id, "xm": vs.xm, "xh": vs.xh,
            },
            "identity": {
                "user_type": "vocational_student", "user_id": str(vs.id),
                "name": vs.xm or "", "phone": phone,
                "department": (bj.mc if bj else ""), "position": "",
            },
        }

    return None


@router.post("/auth/phone-login")
async def phone_login(req: PhoneLoginReq, db: Session = DatabaseDep):
    """微信小程序手机号一键登录

    流程:
      1. 用 code 调微信开放接口换手机号
      2. 在 5 张用户表中按优先级匹配
      3. 匹配命中 -> 生成 JWT token + 附带管理员信息返回
      4. 未匹配 -> 返回 authorized=false，前端弹窗提示联系管理员
    """
    if not req.code:
        return _fail("缺少手机号 code")

    # 1) 换手机号
    from utils.wx_utils import WxUtils
    phone_result = WxUtils.get_phone_number(req.code)
    if not phone_result:
        return _fail("微信手机号授权失败，请重试")
    phone_info = phone_result.get("phone_info") or {}
    phone = (phone_info.get("purePhoneNumber") or phone_info.get("phoneNumber") or "").strip()
    if not phone:
        return _fail("未获取到手机号")

    # 2) 匹配身份
    matched = _match_phone(db, phone)
    if not matched:
        return _ok({
            "authorized": False,
            "msg": "该手机号未在系统中注册，请联系管理员",
            "phone": phone,
        }, msg="未授权")

    # 3) 生成双 token
    token_payload   = matched["token_payload"]
    access_token    = _create_feedback_access_token(token_payload)
    refresh_token   = _create_feedback_refresh_token(token_payload)

    # 4) 附带管理员信息
    admin = get_admin_info(db, phone)

    # 5) 写 7 天手机号缓存（可选：兼容旧前端，未传 login_code 时跳过）
    cache_written = False
    try:
        from common import phone_cache as _phone_cache
        if req.login_code and req.subject:
            openid = _phone_cache.resolve_openid_by_login_code(req.login_code)
            if openid:
                pure_phone = _phone_cache.normalize_phone(phone)
                masked_phone = _phone_cache.mask_phone(pure_phone)
                cache_written = _phone_cache.write_phone_cache(
                    openid=openid,
                    pure_phone=pure_phone,
                    role='self',
                    subject=req.subject,
                    extra={
                        'masked_phone': masked_phone,
                        'sfzh': '',
                        'xm': matched["identity"]["name"],
                    },
                )
    except Exception as _e:
        logger.warning(f"[phone_cache] feedback/auth/phone-login 写缓存失败: {_e}")

    return _ok({
        "authorized": True,
        "token": access_token,
        "refresh_token": refresh_token,
        "identity": matched["identity"],
        "is_admin": admin is not None,
        "admin_role": admin.role if admin else None,
        "admin_role_label": _ROLE_LABELS.get(admin.role, "") if admin else "",
        "admin_scope": admin.scope_codes if admin else "",
        "admin_department": admin.department if admin else "",
        "cache_written": cache_written,
    }, msg="登录成功")


@router.post("/auth/refresh")
def feedback_token_refresh(req: RefreshReq):
    """用 refresh_token 换新的 access_token（及轮换 refresh_token）"""
    try:
        payload = pyjwt.decode(req.refresh_token, FEEDBACK_REFRESH_SECRET, algorithms=[ALGORITHM])
        if payload.get("type") != "fb_refresh":
            raise pyjwt.exceptions.InvalidTokenError("wrong token type")
        clean = {k: v for k, v in payload.items() if k not in ("type", "exp", "iat")}
        new_access  = _create_feedback_access_token(clean)
        new_refresh = _create_feedback_refresh_token(clean)
        return _ok({"token": new_access, "refresh_token": new_refresh})
    except pyjwt.exceptions.ExpiredSignatureError:
        return _fail("refresh token 已过期，请重新登录")
    except pyjwt.exceptions.InvalidTokenError:
        return _fail("无效的 refresh token，请重新登录")
    except Exception:
        logger.exception("feedback token refresh error")
        return _fail("刷新失败，请重试")


@router.get("/auth/me")
async def auth_me(
    payload: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep,
):
    """前端按钮判定接口：同时返回身份 + 是否管理员 + 角色"""
    user = resolve_user(payload, db)
    if not user:
        return _fail("无法识别用户身份", 401)
    admin = get_admin_info(db, user.get("phone"))
    return _ok({
        "identity": user,
        "is_admin": admin is not None,
        "admin_role": admin.role if admin else None,
        "admin_role_label": _ROLE_LABELS.get(admin.role, "") if admin else "",
        "admin_scope": admin.scope_codes if admin else "",
        "admin_department": admin.department if admin else "",
    })


# ============== 字典（场景 / 物品类型） ==============

def _serialize_dict(d: FeedbackDict) -> dict:
    """序列化为字典；extra_data 是 JSON 字符串，尝试解析失败回退原值。"""
    import json as _json
    extra = None
    if d.extra_data:
        try:
            extra = _json.loads(d.extra_data)
        except Exception:
            extra = d.extra_data
    base = {
        "code": d.code,
        "label": d.label,
        "icon": d.icon or "",
        "is_custom": bool(d.is_custom),
        "feedback_type": d.feedback_type or "both",
        "sort_order": d.sort_order or 0,
        "extra_data": extra,
    }
    # 维修类型额外提取 group/icon 到顶层（前端可直接用）
    if d.category == "repair_type" and isinstance(extra, dict):
        base["group"] = extra.get("group")
        base["icon"] = extra.get("icon") or d.icon or ""
    return base


@router.get("/dict")
async def dict_list(
    # 2026-09-27：item 已合并到 repair_type
    feedback_type: str = Query("", description="repair / suggestion / 空=全部"),
    db: Session = DatabaseDep,
):
    q = db.query(FeedbackDict).filter(
        FeedbackDict.category == 'repair_type',
        FeedbackDict.is_active == True,  # noqa: E712
    )
    if feedback_type in ("repair", "suggestion"):
        q = q.filter(FeedbackDict.feedback_type.in_([feedback_type, "both"]))
    items = q.order_by(FeedbackDict.sort_order.asc(), FeedbackDict.id.asc()).all()
    return _ok({"items": [_serialize_dict(d) for d in items]})


@router.get("/dict/bundle")
async def dict_bundle(
    feedback_type: str = Query("", description="repair / suggestion / 空=全部"),
    db: Session = DatabaseDep,
):
    """一次拿维修类型，前端首屏减少请求数。

    返回：
      repair_types: 维修类型列表（按工种分组，每个含 group 字段）

    2026-09-27：移除 scene/item 类目（FeedbackTicket 上 scene/scene_custom 已 DROP；item 已合并到 repair_type）。
    """
    q = db.query(FeedbackDict).filter(
        FeedbackDict.is_active == True,  # noqa: E712
        FeedbackDict.category == 'repair_type',
    )
    if feedback_type in ("repair", "suggestion"):
        q = q.filter(FeedbackDict.feedback_type.in_([feedback_type, "both"]))
    rows = q.order_by(FeedbackDict.sort_order.asc(), FeedbackDict.id.asc()).all()
    repair_types = [_serialize_dict(d) for d in rows]
    return _ok({"repair_types": repair_types})


# ============== 地点字典接口 ==============

def _serialize_location(d: FeedbackLocation) -> dict:
    return {
        "id": d.id,
        "parent_id": d.parent_id,
        "code": d.code,
        "name": d.name,
        "type_code": d.type_code,  # 2026-09-27：新增，任意地点类型
        "level": d.level,
        "full_path": d.full_path,
        "sort_order": d.sort_order or 0,
        "is_active": bool(d.is_active),
    }


@router.get("/location/types")
async def location_types(db: Session = DatabaseDep, user: dict = Depends(require_user)):
    """返回所有出现过的 type_code（小程序提交工单时使用）。

    2026-09-29：类型排序字段独立到 hp_feedback_location_type 表。
    - 优先用独立 type 表的 sort_order 排序
    - 对未登记的 type_code 自动补一行（sort_order=0）
    """
    rows = (
        db.query(FeedbackLocation.type_code)
          .filter(FeedbackLocation.type_code.isnot(None),
                  FeedbackLocation.type_code != '',
                  FeedbackLocation.is_active == True)  # noqa: E712
          .group_by(FeedbackLocation.type_code)
          .all()
    )
    type_codes = [r[0] for r in rows if r[0]]
    if not type_codes:
        return _ok({"types": [], "total": 0})

    # 一次性取这些 type_code 的 sort_order
    sort_rows = db.query(FeedbackLocationType).filter(
        FeedbackLocationType.type_code.in_(type_codes)
    ).all()
    sort_map = {t.type_code: (t.sort_order or 0) for t in sort_rows}

    # 补齐缺失项（老数据 / 漏登记）
    missing = [tc for tc in type_codes if tc not in sort_map]
    if missing:
        try:
            for tc in missing:
                db.add(FeedbackLocationType(type_code=tc, sort_order=0))
            db.commit()
            for tc in missing:
                sort_map[tc] = 0
        except Exception:
            db.rollback()
            for tc in missing:
                sort_map.setdefault(tc, 0)

    # count
    cnt_rows = (
        db.query(FeedbackLocation.type_code, FeedbackLocation.id)
          .filter(FeedbackLocation.type_code.in_(type_codes),
                  FeedbackLocation.is_active == True)  # noqa: E712
          .all()
    )
    count_map = {}
    for tc, _ in cnt_rows:
        count_map[tc] = count_map.get(tc, 0) + 1

    types = [
        {"type_code": tc, "count": count_map.get(tc, 0), "sort_order": sort_map.get(tc, 0)}
        for tc in type_codes
    ]
    types.sort(key=lambda x: (x["sort_order"], x["type_code"]))
    return _ok({"types": types, "total": len(types)})


@router.get("/location/bundle")
async def location_bundle(db: Session = DatabaseDep, user: dict = Depends(require_user)):
    """一次拿所有地点按 type_code 分组，小程序首屏使用。

    2026-09-29：返回 types.sort_order（来自 hp_feedback_location_type）。
    """
    rows = (
        db.query(FeedbackLocation)
          .filter(FeedbackLocation.is_active == True,  # noqa: E712
                  FeedbackLocation.type_code.isnot(None),
                  FeedbackLocation.type_code != '')
          .order_by(FeedbackLocation.type_code.asc(),
                    FeedbackLocation.sort_order.asc(),
                    FeedbackLocation.id.asc())
          .all()
    )
    values, types = {}, {}
    for r in rows:
        tc = r.type_code
        values.setdefault(tc, []).append(_serialize_location(r))
        if tc not in types:
            types[tc] = {"type_code": tc, "count": 0, "sort_order": r.sort_order or 0}
        types[tc]["count"] += 1
    # 2026-09-29：从独立 type 表取 sort_order 覆盖
    tcs = list(types.keys())
    if tcs:
        sort_rows = db.query(FeedbackLocationType).filter(
            FeedbackLocationType.type_code.in_(tcs)
        ).all()
        sort_map = {r.type_code: (r.sort_order or 0) for r in sort_rows}
    else:
        sort_map = {}
    for tc, meta in types.items():
        meta["sort_order"] = sort_map.get(tc, 0)
    types_list = sorted(types.values(), key=lambda x: (x["sort_order"], x["type_code"]))
    return _ok({"types": types_list, "values": values})


@router.get("/location/tree")
async def location_tree(db: Session = DatabaseDep, user: dict = Depends(require_user)):
    """2026-09-27 重构：返回扁平列表（按 type_code 排序），不再返回树形。

    兼容老前端：原 `list` 字段仍保留；新增 `types` 字段携带类型汇总。
    """
    rows = (
        db.query(FeedbackLocation)
          .filter(FeedbackLocation.is_active == True)  # noqa: E712
          .order_by(FeedbackLocation.type_code.asc(),
                    FeedbackLocation.sort_order.asc(),
                    FeedbackLocation.id.asc())
          .all()
    )
    return _ok({"list": [_serialize_location(r) for r in rows]})


@router.get("/location/path/{location_id}")
async def location_path(
    location_id: int,
    db: Session = DatabaseDep,
    user: dict = Depends(require_user),
):
    """返回从根到当前节点的完整路径数组 [楼栋, 楼层, 房间]。"""
    node = db.query(FeedbackLocation).filter(FeedbackLocation.id == location_id).first()
    if not node:
        return _fail("地点不存在", 404)
    chain = []
    cur = node
    while cur:
        chain.append(_serialize_location(cur))
        if cur.parent_id is None:
            break
        cur = db.query(FeedbackLocation).filter(FeedbackLocation.id == cur.parent_id).first()
        if cur is None:
            break
    chain.reverse()
    return _ok({"chain": chain, "full_path": node.full_path})


# ============== 工单业务 ==============

def gen_ticket_no() -> str:
    return "FB" + datetime.now().strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:4].upper()


def parse_json_field(s: Optional[str]) -> List[str]:
    if not s:
        return []
    try:
        v = json.loads(s)
        return v if isinstance(v, list) else []
    except Exception:
        return []


# 2026-09-27：scene/scene_custom 已废弃，SCENE_LABELS 不再使用
ITEM_LABELS = {
    "meal": "饭菜质量", "water_power": "水电", "desk": "桌椅板凳",
    "banbantong": "班班通", "training_eq": "实训设备", "facility": "校园设施",
    "service": "服务态度", "safety": "安全卫生", "custom": ""
}


def _derive_title(t: "FeedbackTicket") -> str:
    """根据 scene + repair_type_text 生成展示用标题(无 title 字段时使用)。

    2026-09-27 重构：item_type/item_custom 已废弃，改用 repair_type_text。
    """
    item = ""
    if t.repair_type_text:
        item = t.repair_type_text.strip()
    # scene/scene_custom 已废弃（2026-09-27）
    item_or_default = item or ("维修反馈" if t.category == "repair" else "意见建议")
    return item_or_default


def _active(query):
    """统一过滤已软删除的工单"""
    return query.filter(FeedbackTicket.is_deleted == 0)


def _keys_to_images(keys: List[str]) -> List[dict]:
    """把 object_key 列表转为前端可直接使用的 [{key, url, type}]

    type 为 'image' | 'video'，按扩展名识别。
    """
    out = []
    for k in keys:
        if not k:
            continue
        # 兼容历史值:如果已是完整路径(含 /feedback/image/) 或 http 直接透传
        if k.startswith("http") or k.startswith("/feedback/image/"):
            # 历史完整路径,尝试从中提取 object_key 来判断类型
            mt = "video" if any(k.lower().split("?", 1)[0].endswith("." + e) for e in VIDEO_EXTS) else "image"
            out.append({"key": k, "url": k, "type": mt})
        else:
            mt = media_type_of(k)
            item = {"key": k, "url": get_signed_url(k), "type": mt}
            # 视频附带按 sidecar 约定的封面 URL ({video_key}.jpg)
            # 前端 image 标签若 404 会展示为空,会回落到深色占位 + 播放图标,不影响体验
            if mt == "video":
                item["poster"] = get_signed_url(k + ".jpg")
            out.append(item)
    return out


def serialize_ticket(t: FeedbackTicket, with_handle: bool = True, anonymize: bool = False) -> dict:
    """返回工单摘要（前端用）。

    2026-09-28 方案 C：地点双列同时输出，前端可以按需展示。
    - location_text：合并展示串（仅展示）
    - location_dict_text：列表段（"|"分隔的字典原值）
    - location_user_text：备注段（用户手写）
    """
    d = {
        "id": t.id,
        "ticket_no": t.ticket_no,
        "category": t.category,
        "title": _derive_title(t),
        "content": t.content,
        # 2026-09-28 方案 C：地点三字段（展示/列表段/备注段）
        "location_text": t.location_text,
        "location_dict_text": t.location_dict_text,
        "location_user_text": t.location_user_text,
        # 维修类型：前端只读 repair_type_text
        "repair_type_text": t.repair_type_text,
        "images": _keys_to_images(parse_json_field(t.images)),
        "urgency": t.urgency,
        "is_anonymous": bool(t.is_anonymous),
        "status": t.status,
        "created_at": t.created_at.strftime("%Y-%m-%d %H:%M") if t.created_at else "",
    }
    if anonymize and t.is_anonymous:
        d["reporter_name"] = "匿名用户"
        d["reporter_phone"] = ""
        d["reporter_dept"] = ""
        d["reporter_user_type"] = t.reporter_user_type
    else:
        d["reporter_name"] = t.reporter_name
        d["reporter_phone"] = t.reporter_phone
        d["reporter_dept"] = t.reporter_dept
        d["reporter_user_type"] = t.reporter_user_type
    if with_handle:
        d["handle_remark"] = t.handle_remark
        d["handle_images"] = _keys_to_images(parse_json_field(t.handle_images))
        d["handle_at"] = t.handle_at.strftime("%Y-%m-%d %H:%M") if t.handle_at else ""
        d["handler_name"] = t.handler_name
        d["reject_reason"] = t.reject_reason
    return d


def add_timeline(db: Session, ticket_id: int, action: str, name: str, phone: str = "", remark: str = ""):
    tl = FeedbackTimeline(
        ticket_id=ticket_id, action=action,
        operator_name=name, operator_phone=phone, remark=remark
    )
    db.add(tl)


# ============== 提交/查询/撤回 ==============

class SubmitReq(BaseModel):
    """反馈提交请求体。

    2026-09-28 方案 C：地点拆双列，按段分别提交。
    - location_dict_text：仅 chip 拼接的字典原值，"|"分隔
    - location_user_text：仅用户手写备注，自由文本
    - location_text     ：可选，如果前端不发合并展示串，后端自动生成（"<dict> · <user>"）

    兼容策略：
    - 老的 location_id / location_full_path / location_parts / location_text_fuzzy
      如果前端还在传，后端会接收但忽略（不再写入 DB）。
    """
    category: str = Field(..., description="repair / suggestion")

    # ---- 兼容旧字段（不再写入 DB，忽略即可） ----
    item_custom: Optional[str] = None
    repair_type_label: Optional[str] = None
    location_id: Optional[int] = None
    location_full_path: Optional[str] = None
    location_text_fuzzy: Optional[str] = None
    location_parts: Optional[list] = None

    # ---- 实际生效字段 ----
    content: str
    # 地点双列
    location_text: Optional[str] = None  # 合并展示串（仅展示，可由前端发或后端拼）
    location_dict_text: Optional[str] = None  # 列表段（"|"分隔的字典原值）
    location_user_text: Optional[str] = None  # 备注段（用户自由文本）
    repair_type_code: Optional[str] = None  # 兼容：查字典 label 后写入 repair_type_text
    repair_type_text: Optional[str] = None  # 维修类型自由文本（写入 repair_type_text 列）
    images: List[str] = []
    urgency: str = "normal"
    is_anonymous: bool = False


@router.post("/submit")
async def submit(
    request: Request,
    db: Session = DatabaseDep,
    user: dict = Depends(require_user)
):
    """提交反馈。

    支持两种 Content-Type：

    1. application/json（兼容旧接口）
       {
         "category": "repair",
         ...
         "images": ["private/hq/feedback/xxx.jpg"]   // 已经是上传好的 key
       }

    2. multipart/form-data（新接口，推荐）
       formData["data"] = JSON 字符串，内容同上
       formData["files"] = 一个或多个图片 / 视频文件 (key 名 file_0 / file_1 ...)
       或者 formData["file_<index>"] = 与 images 数组下标一一对应的文件

    后端代上传语义：
      - 先把所有 files 上传到 MinIO private/hq/feedback/
      - 任一失败：回滚已上传的，返回错误
      - 全部成功：合并到 images 列表，写 DB（同一逻辑路径）
    """
    from fastapi import UploadFile, File, Form

    # ---------- 解析表单 ----------

    content_type = (request.headers.get("content-type") or "").lower()

    # ---------- 解析表单 ----------
    if "multipart/form-data" in content_type:
        form = await request.form()
        data_raw = form.get("data")
        if not data_raw:
            return _fail("multipart 提交缺少 data 字段")
        try:
            payload = json.loads(data_raw)
        except Exception:
            return _fail("data 字段不是合法 JSON")

        # 收集文件：支持 files / file_0 / file_1 ... / 单个 file
        # 优先匹配：files (多个) 或 file_<index> (与 images 下标对应)
        uploaded_files: List[Tuple[int, UploadFile]] = []
        # 多个 key 都是 "files"
        if "files" in form:
            f = form.getlist("files")
            for idx, ff in enumerate(f):
                if isinstance(ff, UploadFile):
                    uploaded_files.append((idx, ff))
        # 或者 file_0, file_1, ...
        for key in form.keys():
            if key.startswith("file_") and key[5:].isdigit():
                idx = int(key[5:])
                v = form[key]
                if isinstance(v, UploadFile) and not any(i == idx for i, _ in uploaded_files):
                    uploaded_files.append((idx, v))
        uploaded_files.sort(key=lambda t: t[0])
    else:
        payload = await request.json()
        uploaded_files = []

    # ---------- 校验 ----------
    try:
        req = SubmitReq(**payload)
    except Exception as e:
        return _fail(f"参数错误: {e}")

    logger.info("[submit] phone=%s category=%s", user.get("phone"), req.category)

    # 2026-09-28 方案 C：地点双列。dict_text / user_text 在下面维修类分支会被规范化。
    dict_text = ""
    user_text = ""

    # ---------- 校验 ----------
    if req.category not in ("repair", "suggestion"):
        return _fail("分类参数错误")
    if not req.content or len(req.content.strip()) < 2:
        return _fail("请填写至少2字的描述")

    # 维修类必填项（2026-09-28 方案 C）：校验双列。
    #   - 列表段 或 备注段 至少有一项非空（用户要么选了 chip，要么手写了备注）。
    if req.category == "repair":
        has_rt_text = bool((req.repair_type_text or "").strip())
        if not has_rt_text:
            return _fail("请选择维修类型")
        dict_text = (req.location_dict_text or "").strip()
        user_text = (req.location_user_text or "").strip()
        # 兜底：如果前端旧版没拆双列，只发了 location_text，尝试拆出来
        # 拆分规则：
        #   - 以最后出现的 " · " 切，前面是列表段（再按 | 切），后面是备注段
        #   - 单段且包含 "|" → 全当列表段
        #   - 单段且不包含 "|" → 全当备注段
        if not dict_text and not user_text:
            merged = (req.location_text or "").strip()
            if merged:
                if " · " in merged:
                    pre, post = merged.rsplit(" · ", 1)
                    dict_text = pre.strip()
                    user_text = post.strip()
                elif "|" in merged:
                    dict_text = merged
                else:
                    user_text = merged
        if not dict_text and not user_text:
            logger.warning(
                "[submit] 维修类缺少地点: location_dict_text=%r, location_user_text=%r, location_text=%r",
                req.location_dict_text, req.location_user_text, req.location_text,
            )
            return _fail("维修类必须选择或填写地点")
    is_anon = bool(req.is_anonymous and req.category == "suggestion")

    # ---------- 规范化已上传的 key ----------
    #
    # 兼容多种历史/当前格式（核心：跟 photo_proxy.feedback_upload 当前实际返回一致）：
    #   1. 带桶名全路径   : "guizhou-zhpt-prod-private/hq/feedback/<uuid>.jpg"  ← photo_proxy 当前实际返回
    #   2. 业务前缀路径   : "private/hq/feedback/<uuid>.jpg"                     ← 注释里的旧规范
    #   3. 旧业务前缀     : "feedback/<uuid>.jpg"                                ← 清库前的旧记录
    #   4. 旧 HMAC URL    : "/feedback/image/<uuid>.jpg?..."                    ← 兜底兼容
    #
    # 出栈侧（_keys_to_images → get_signed_url）能处理带/不带桶名任意格式，
    # 所以这里只做合法性校验，不强行改写。
    _BUCKET_PRIVATE_NAME = "guizhou-zhpt-prod-private"
    _FEEDBACK_DIR = "hq/feedback"
    def _normalize_key(s: str) -> Optional[str]:
        """规范化 key 入库格式。

        入库约定（与 photo_proxy.feedback_upload 实际写入的 MinIO object_name 一致）：
          hq/feedback/<uuid>.<ext>     （不带桶名、不带 private/ 前缀）

        兼容前端可能送进来的若干种格式：
          1. 带桶名全路径（photo_proxy 当前实际返回）:
             "guizhou-zhpt-prod-private/hq/feedback/<uuid>.jpg"
          2. 注释里的旧规范:
             "private/hq/feedback/<uuid>.jpg"
          3. 清库前的旧业务前缀:
             "feedback/<uuid>.jpg"
          4. 旧 HMAC URL 兜底:
             "/feedback/image/<uuid>.jpg?..."

        最终一律剥成纯 key "hq/feedback/<uuid>.<ext>" 入库，
        出栈由 _keys_to_images → sign_object_url 自动拼回 <bucket>/<key> 生成签名 URL。
        """
        if not s:
            return None
        s = s.strip().lstrip("/")
        if not s:
            return None
        if s.startswith("/feedback/image/"):
            s = s[len("/feedback/image/"):].split("?", 1)[0]
        if "?" in s:
            s = s.split("?", 1)[0]
        # 1) 带桶名全路径 → 剥桶名 + 剥 private/ 前缀（统一成 hq/feedback/...）
        if s.startswith(f"{_BUCKET_PRIVATE_NAME}/"):
            s = s[len(f"{_BUCKET_PRIVATE_NAME}/"):]
            if s.startswith("private/"):
                s = s[len("private/"):]
            if s.startswith(_FEEDBACK_DIR + "/"):
                tail = s[len(_FEEDBACK_DIR) + 1:]
                return s if tail and "/" not in tail and "." in tail else None
            return None
        # 2) 业务前缀路径 → 剥 private/
        if s.startswith("private/hq/feedback/"):
            s = "hq/feedback/" + s[len("private/hq/feedback/"):]
            tail = s[len("hq/feedback/"):]
            return s if tail and "/" not in tail and "." in tail else None
        # 3) 旧业务前缀 → 直接通过
        if s.startswith("feedback/"):
            s = "hq/feedback/" + s[len("feedback/"):]
            tail = s[len("hq/feedback/"):]
            return s if tail and "/" not in tail and "." in tail else None
        return None

    existing_keys: List[str] = [k for k in (_normalize_key(x) for x in (req.images or [])) if k]
    existing_keys = existing_keys[:6]
    remain_slots = 6 - len(existing_keys)

    # ---------- 后端代上传 ----------
    from services.minio_service import put_feedback_image, put_feedback_poster, BUCKET_PRIVATE as _BP
    uploaded_keys: List[str] = []
    try:
        # 视频封面用 (file_i, poster_i) 配对：约定 formData["file_<idx>_poster"]
        for idx, upload in uploaded_files[:remain_slots]:
            raw = await upload.read()
            if not raw:
                continue
            fname = upload.filename or "x.bin"
            ext = (fname.rsplit(".", 1)[-1] or "jpg").lower()[:8]
            content_type_map = {
                "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "png": "image/png", "webp": "image/webp",
                "mp4": "video/mp4", "mov": "video/quicktime",
            }
            ct = upload.content_type or content_type_map.get(ext, "application/octet-stream")
            key = put_feedback_image(raw, fname, ct)
            # ★ 入库时统一成纯 key hq/feedback/<uuid>.<ext>
            if key.startswith(f"{_BP}/"):
                key = key[len(_BP) + 1:]
            uploaded_keys.append(key)

            # 视频封面：file_<idx>_poster（pass full DB path；put_feedback_poster 内部自行 split）
            poster_form_key = f"file_{idx}_poster"
            if "multipart/form-data" in content_type and poster_form_key in form:
                poster = form[poster_form_key]
                if isinstance(poster, UploadFile):
                    praw = await poster.read()
                    if praw:
                        try:
                            put_feedback_poster(f"{_BP}/{key}", praw, "image/jpeg")
                        except Exception:
                            pass  # 封面失败不阻塞
    except Exception as e:
        # ★ 任一上传失败：回滚已上传的，返回错误
        from services.minio_service import delete_by_path
        for k in uploaded_keys:
            try:
                delete_by_path(k)
            except Exception:
                pass
        logger.exception("submit upload failed")
        return _fail(f"媒体上传失败: {e}")

    clean_images = (existing_keys + uploaded_keys)[:6]

    # ---------- 节流 ----------
    from datetime import timedelta
    five_min_ago = datetime.now() - timedelta(minutes=5)
    recent = _active(db.query(FeedbackTicket)).filter(
        FeedbackTicket.reporter_phone == user["phone"],
        FeedbackTicket.created_at >= five_min_ago
    ).count()
    if recent >= 3:
        # 同样回滚刚刚上传的
        from services.minio_service import delete_by_path
        for k in uploaded_keys:
            try:
                delete_by_path(k)
            except Exception:
                pass
        return _fail("提交过于频繁,请稍后再试")

    # ---------- 写 DB ----------
    # 2026-09-28 方案 C：双列写库 + 后端生成合并展示串。
    # 列表段与备注段由本次校验流程已规范化过（dict_text / user_text），不再依赖前端 location_text。
    final_dict = dict_text[:500] or None
    final_user = user_text[:500] or None
    if dict_text and user_text:
        final_display = f"{dict_text} · {user_text}"[:500]
    elif dict_text:
        final_display = dict_text[:500]
    elif user_text:
        # 仅备注段：保留空格给前端展示
        final_display = f" · {user_text}"[:500]
    else:
        final_display = None
    t = FeedbackTicket(
        ticket_no=gen_ticket_no(),
        category=req.category,
        content=req.content.strip(),
        location_text=final_display,
        location_dict_text=final_dict,
        location_user_text=final_user,
        repair_type_text=(req.repair_type_text or "").strip()[:64] or None,
        images=json.dumps(clean_images, ensure_ascii=False),
        urgency=req.urgency if req.urgency in ("normal", "urgent") else "normal",
        is_anonymous=1 if is_anon else 0,
        reporter_user_type=user["user_type"],
        reporter_id=user["user_id"],
        reporter_name=user["name"],
        reporter_phone=user["phone"],
        reporter_dept=user["dept"],
        status="pending",
    )
    db.add(t)
    db.flush()
    add_timeline(db, t.id, "submit", user["name"], user["phone"], "提交反馈")
    db.commit()
    db.refresh(t)
    return _ok({"id": t.id, "ticket_no": t.ticket_no, "image_count": len(clean_images)})


@router.get("/my")
async def my_list(
    status: str = "",
    page: int = 1,
    page_size: int = 20,
    db: Session = DatabaseDep,
    user: dict = Depends(require_user)
):
    page = max(page, 1)
    page_size = min(max(page_size, 1), 50)
    q = _active(db.query(FeedbackTicket)).filter(
        FeedbackTicket.reporter_user_type == user["user_type"],
        FeedbackTicket.reporter_id == user["user_id"],
    )
    if status:
        q = q.filter(FeedbackTicket.status == status)
    total = q.count()
    items = q.order_by(desc(FeedbackTicket.id)).offset((page - 1) * page_size).limit(page_size).all()
    return _ok({
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [serialize_ticket(t, with_handle=True, anonymize=False) for t in items]
    })


@router.get("/detail/{ticket_id}")
async def detail(
    ticket_id: int,
    db: Session = DatabaseDep,
    user: dict = Depends(require_user)
):
    t = _active(db.query(FeedbackTicket)).filter(FeedbackTicket.id == ticket_id).first()
    if not t:
        return _fail("工单不存在", 404)
    is_owner = (t.reporter_user_type == user["user_type"] and t.reporter_id == user["user_id"])
    is_admin = is_feedback_admin(db, user.get("phone"))
    if not is_owner and not is_admin:
        return _fail("无权查看", 403)
    timeline = db.query(FeedbackTimeline).filter(FeedbackTimeline.ticket_id == ticket_id) \
        .order_by(FeedbackTimeline.id.asc()).all()
    return _ok({
        # 匿名工单:对所有非本人查看者(包括管理员)脱敏 name/phone,仅 DB 留底
        "ticket": serialize_ticket(t, with_handle=True, anonymize=(not is_owner)),
        "timeline": [{
            "action": tl.action,
            "operator_name": tl.operator_name,
            "remark": tl.remark or "",
            "created_at": tl.created_at.strftime("%Y-%m-%d %H:%M") if tl.created_at else ""
        } for tl in timeline]
    })


@router.post("/cancel/{ticket_id}")
async def cancel(
    ticket_id: int,
    db: Session = DatabaseDep,
    user: dict = Depends(require_user)
):
    t = _active(db.query(FeedbackTicket)).filter(FeedbackTicket.id == ticket_id).first()
    if not t:
        return _fail("工单不存在", 404)
    if not (t.reporter_user_type == user["user_type"] and t.reporter_id == user["user_id"]):
        return _fail("无权操作", 403)
    if t.status != "pending":
        return _fail("当前状态不可撤回")
    t.status = "cancelled"
    add_timeline(db, t.id, "cancel", user["name"], user["phone"], "用户撤回")
    db.commit()
    return _ok()


# ============== 图片上传 / 访问 / 删除(MinIO) ==============

# 注：以下三条路由已迁移到 controllers/photo_proxy.py：
#   - POST /feedback/upload            → photo_proxy.feedback_upload
#   - GET  /feedback/image/{path}      → photo_proxy.get_feedback_image
#   - POST /feedback/upload_poster     → photo_proxy.feedback_upload_poster
# 这里不再重复定义，避免与 photo_proxy 路由冲突。
#
# 仅保留 /feedback/delete_image（带 DB 绑定校验）和 admin 系列路由在本控制器内。


class DeleteImageReq(BaseModel):
    key: str


@router.post("/delete_image")
async def delete_image(
    req: DeleteImageReq,
    db: Session = DatabaseDep,
    user: dict = Depends(require_user)
):
    """删除尚未提交的反馈图片（只允许删除未绑定到任何工单的对象）。

    允许的 key 前缀：
    - private/hq/feedback/   ：当前规范路径
    - feedback/              ：旧路径（清库前历史数据）
    """
    key = (req.key or "").strip()
    if not (key.startswith("private/hq/feedback/") or key.startswith("feedback/")):
        return _fail("非法路径")

    # 安全校验：若该对象已被持久化到某个工单，禁止删除（避免用户端删除别人正在用的图）
    like = f'%"{key}"%'
    bound = _active(db.query(FeedbackTicket)).filter(
        or_(FeedbackTicket.images.like(like), FeedbackTicket.handle_images.like(like))
    ).first()
    if bound:
        return _fail("图片已绑定工单,不能删除")

    ok = mio_delete(key)
    if not ok:
        return _fail("删除失败")
    # 视频附带的封面 sidecar 一并删除（失败不阻塞）
    if media_type_of(key) == "video":
        try:
            mio_delete(key + ".jpg")
        except Exception:
            pass
    return _ok()


# ============== 管理端 ==============

@router.get("/admin/whitelist_check")
async def admin_check(payload: dict = Depends(verify_token_and_get_payload), db: Session = DatabaseDep):
    user = resolve_user(payload, db)
    if not user:
        return _ok({"is_admin": False})
    admin = get_admin_info(db, user.get("phone"))
    # 严格以数据库字段为准，所有角色均受 can_view_suggestion 控制
    can_view_suggestion = bool(admin and admin.can_view_suggestion)
    return _ok({
        "is_admin": admin is not None,
        "admin_role": admin.role if admin else None,
        "admin_role_label": _ROLE_LABELS.get(admin.role, "") if admin else "",
        "admin_scope": admin.scope_codes if admin else "",
        "admin_department": admin.department if admin else "",
        "can_view_suggestion": can_view_suggestion,
        "phone": user.get("phone"),
        "name": user.get("name"),
        "user_type": user.get("user_type"),
    })


@router.get("/admin/stats")
async def admin_stats(db: Session = DatabaseDep, user: dict = Depends(require_admin())):
    base = _active(db.query(FeedbackTicket))
    # 无 suggestion 权限时只统计 repair 类工单
    if not user.get("can_view_suggestion"):
        base = base.filter(FeedbackTicket.category != "suggestion")
    return _ok({
        "pending": base.filter(FeedbackTicket.status == "pending").count(),
        "processing": base.filter(FeedbackTicket.status == "processing").count(),
        "done": base.filter(FeedbackTicket.status == "done").count(),
        "rejected": base.filter(FeedbackTicket.status == "rejected").count(),
        "total": base.count(),
    })


@router.get("/admin/trend")
async def admin_trend(
    period: str = Query("day", description="day|month"),
    n: int = Query(14, description="返回区间数,日:1-30,月:1-12"),
    db: Session = DatabaseDep,
    user: dict = Depends(require_admin())
):
    """趋势统计:按日/按月聚合最近 N 个区间。
    返回 buckets: [{label, total, repair, suggestion, done}]
    """
    from datetime import date, timedelta
    if period not in ("day", "month"):
        return _fail("period 参数错误")
    n = max(1, min(n, 30 if period == "day" else 12))

    today = date.today()

    # 生成区间起止
    buckets = []  # [(label, start_dt, end_dt)]
    if period == "day":
        for i in range(n - 1, -1, -1):
            d = today - timedelta(days=i)
            start = datetime.combine(d, datetime.min.time())
            end = start + timedelta(days=1)
            buckets.append((d.strftime("%m-%d"), start, end))
    else:
        # 最近 N 个月(含本月)
        y, m = today.year, today.month
        seq = []
        for _ in range(n):
            seq.append((y, m))
            m -= 1
            if m == 0:
                m = 12; y -= 1
        seq.reverse()
        for (yy, mm) in seq:
            start = datetime(yy, mm, 1)
            ny, nm = (yy + 1, 1) if mm == 12 else (yy, mm + 1)
            end = datetime(ny, nm, 1)
            buckets.append((f"{yy}-{mm:02d}", start, end))

    # 批量聚合(单次扫描),避免 N 次 query
    overall_start = buckets[0][1]
    overall_end = buckets[-1][2]
    rows = db.query(
        FeedbackTicket.created_at,
        FeedbackTicket.category,
        FeedbackTicket.status,
    ).filter(
        FeedbackTicket.is_deleted == 0,
        FeedbackTicket.created_at >= overall_start,
        FeedbackTicket.created_at < overall_end,
    ).all()

    # 初始化结果
    result = [
        {"label": lbl, "total": 0, "repair": 0, "suggestion": 0, "done": 0}
        for (lbl, _s, _e) in buckets
    ]
    # 按二分/线性归位(N 通常 <= 30,直接线性)
    edges = [b[1] for b in buckets] + [buckets[-1][2]]
    for created_at, cat, st in rows:
        if not created_at:
            continue
        # 找区间下标
        idx = -1
        for i in range(len(buckets)):
            if edges[i] <= created_at < edges[i + 1]:
                idx = i
                break
        if idx < 0:
            continue
        result[idx]["total"] += 1
        if cat == "repair":
            result[idx]["repair"] += 1
        elif cat == "suggestion":
            result[idx]["suggestion"] += 1
        if st == "done":
            result[idx]["done"] += 1

    # 顶部汇总
    summary = {
        "total": sum(b["total"] for b in result),
        "repair": sum(b["repair"] for b in result),
        "suggestion": sum(b["suggestion"] for b in result),
        "done": sum(b["done"] for b in result),
    }
    return _ok({"period": period, "n": n, "buckets": result, "summary": summary})


@router.get("/admin/list")
async def admin_list(
    status: str = "",
    category: str = "",
    keyword: str = "",
    urgency: str = "",
    my_participation: int = 0,
    # 2026-09-28 v2：弹窗筛选 - 多选字典精确匹配 + 反馈人/时间/有图
    repair_type_codes: str = "",     # 逗号分隔，如 "water,electric"
    location_dict_kws: str = "",     # 逗号分隔，精确 token 匹配（location_dict_text 用 | 包夹），兼容老前端
    location_dict_kws_by_type: str = "",  # 2026-09-29：按 type_code 分组，组内 OR / 组间 AND；格式 '楼栋:A栋,综合楼|楼层:1楼,3楼'
    reporter_user_types: str = "",   # 逗号分隔，open_student/vocational_student/open_teacher/vocational_teacher/staff
    has_image: int = 0,              # 1=只看有图
    date_from: str = "",             # YYYY-MM-DD
    date_to: str = "",               # YYYY-MM-DD（含）
    preview: int = 0,                # 1=仅返回命中数 total，不取明细（用于弹窗底部"命中 X 条"预览）
    page: int = 1,
    page_size: int = 20,
    db: Session = DatabaseDep,
    user: dict = Depends(require_admin())
):
    """管理员列表接口（2026-09-28 v2：弹窗精确筛选）。

    - status / category / urgency / my_participation：单选或布尔
    - repair_type_codes / location_dict_kws / reporter_user_types：多选（逗号分隔）
      · repair_type_codes 精确匹配 FeedbackDict.code → repair_type_text
      · location_dict_kws_by_type（2026-09-29）：'楼栋:A栋|楼层:1楼,3楼' 组内 OR / 组间 AND
      · location_dict_kws：兼容老前端，扁平字符串（全 OR）
    - has_image / date_from / date_to：内容筛选
    - preview=1 时只返回 total，不查明细
    - keyword 兜底模糊（内容/工单号/反馈人）
    """
    page = max(page, 1)
    page_size = min(max(page_size, 1), 50)
    q = _active(db.query(FeedbackTicket))

    # 无 suggestion 权限：强制排除 suggestion 类，前端传 category=suggestion 也无效
    if not user.get("can_view_suggestion"):
        q = q.filter(FeedbackTicket.category != "suggestion")
        if category == "suggestion":
            category = ""  # 忽略前端传来的 suggestion 筛选

    if status:
        q = q.filter(FeedbackTicket.status == status)
    if category:
        q = q.filter(FeedbackTicket.category == category)
    if urgency:
        q = q.filter(FeedbackTicket.urgency == urgency)

    # 反馈人类型多选
    if reporter_user_types:
        types_list = [t.strip() for t in reporter_user_types.split(",") if t.strip()]
        if types_list:
            q = q.filter(FeedbackTicket.reporter_user_type.in_(types_list))

    # 维修类型精确匹配（按字典 code）
    if repair_type_codes:
        codes_list = [c.strip() for c in repair_type_codes.split(",") if c.strip()]
        if codes_list:
            # 把 code 反查成 label（来自 FeedbackDict），用 label 在 repair_type_text 里精确匹配
            labels = [
                d.label for d in db.query(FeedbackDict).filter(
                    FeedbackDict.category == "repair_type",
                    FeedbackDict.code.in_(codes_list),
                    FeedbackDict.is_active == True,
                ).all()
            ]
            labels = [l for l in labels if l]
            if labels:
                q = q.filter(FeedbackTicket.repair_type_text.in_(labels))
            else:
                q = q.filter(FeedbackTicket.id == -1)

    # 地点字典精确 token 匹配
    # 2026-09-29：支持按 type_code 分组的 AND/OR 语义
    #   - location_dict_kws_by_type：'楼栋:宿舍A栋,综合楼|楼层:1楼,3楼'
    #     含义：组内 OR（楼栋 = A栋 OR 综合楼），组间 AND（楼栋∈{...} AND 楼层∈{1楼,3楼}）
    #   - location_dict_kws：兼容旧前端（无分组，全 OR）。新前端不再传。
    if location_dict_kws_by_type:
        groups = []
        for grp in location_dict_kws_by_type.split("|"):
            grp = grp.strip()
            if not grp or ":" not in grp:
                continue
            _type_code, _names_part = grp.split(":", 1)
            _names = [n.strip() for n in _names_part.split(",") if n.strip()]
            if not _names:
                continue
            group_conds = []
            for kw in _names:
                kw_esc = kw.replace("[", "[[]").replace("%", "[%]").replace("_", "[_]")
                cond_first = FeedbackTicket.location_dict_text.like(f"{kw_esc}|%")
                cond_mid   = FeedbackTicket.location_dict_text.like(f"%|{kw_esc}|%")
                cond_last  = FeedbackTicket.location_dict_text.like("%|" + kw_esc)
                cond_alone = (FeedbackTicket.location_dict_text == kw_esc)
                group_conds.append(or_(cond_first, cond_mid, cond_last, cond_alone))
            groups.append(or_(*group_conds))
        if groups:
            q = q.filter(and_(*groups))  # 组间 AND
    elif location_dict_kws:
        # 兼容旧前端：扁平字符串列表，组间 OR（语义模糊，但保留旧行为避免破坏老版本）
        kws_list = [k.strip() for k in location_dict_kws.split(",") if k.strip()]
        if kws_list:
            loc_conds = []
            for kw in kws_list:
                kw_esc = kw.replace("[", "[[]").replace("%", "[%]").replace("_", "[_]")
                cond_first = FeedbackTicket.location_dict_text.like(f"{kw_esc}|%")
                cond_mid   = FeedbackTicket.location_dict_text.like(f"%|{kw_esc}|%")
                cond_last  = FeedbackTicket.location_dict_text.like("%|" + kw_esc)
                cond_alone = (FeedbackTicket.location_dict_text == kw_esc)
                loc_conds.append(or_(cond_first, cond_mid, cond_last, cond_alone))
            q = q.filter(or_(*loc_conds))

    # 有图筛选
    if has_image:
        # images 是 Text 字段，非空字符串即有图
        q = q.filter(FeedbackTicket.images.isnot(None))
        q = q.filter(func.trim(FeedbackTicket.images) != "")

    # 时间范围（created_at）
    if date_from:
        try:
            dt_from = datetime.strptime(date_from, "%Y-%m-%d")
            q = q.filter(FeedbackTicket.created_at >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.strptime(date_to, "%Y-%m-%d")
            # 含当日：+1 天 0 点
            dt_to = dt_to.replace(hour=23, minute=59, second=59)
            q = q.filter(FeedbackTicket.created_at <= dt_to)
        except ValueError:
            pass

    # "我参与的"筛选：reporter_phone 是我 或 handler_phone 是我 或 timeline 中有我的操作记录
    if my_participation:
        my_phone = user.get("phone", "")
        if my_phone:
            # 从 timeline 表中找出我参与过的工单 ID
            my_timeline_ticket_ids = [
                tid for (tid,) in db.query(FeedbackTimeline.ticket_id).filter(
                    FeedbackTimeline.operator_phone == my_phone
                ).distinct().all()
            ]
            participation_conds = [
                FeedbackTicket.reporter_phone == my_phone,
                FeedbackTicket.handler_phone == my_phone,
            ]
            if my_timeline_ticket_ids:
                participation_conds.append(FeedbackTicket.id.in_(my_timeline_ticket_ids))
            q = q.filter(or_(*participation_conds))
        else:
            # phone 字段为空则返回空列表（不可能匹配到任何记录）
            q = q.filter(FeedbackTicket.id == -1)

    if keyword:
        kw = keyword.strip()
        like = f"%{kw}%"
        # 2026-09-28 方案 C：地点拆两列 → 对两列都做 LIKE，并去掉列表段的 | 分隔符后
        # 再做一次 LIKE，让"用户自然拼"（无分隔符）也能命中。
        #   例：用户搜 "10楼宿舍楼A" → dict_text="10楼|宿舍楼A" → 去 | 后 LIKE 命中
        kw_no_sep = kw.replace("|", "")
        like_no_sep_dict = f"%{kw_no_sep}%"
        # SQL Server 中 REPLACE 是函数，直接用即可
        conds = [
            FeedbackTicket.content.like(like),
            FeedbackTicket.location_text.like(like),
            FeedbackTicket.location_user_text.like(like),
            FeedbackTicket.repair_type_text.like(like),
            FeedbackTicket.ticket_no.like(like),
            FeedbackTicket.reporter_name.like(like),
            # 列表段精确命中（保留 | 分隔的字典原值）
            FeedbackTicket.location_dict_text.like(like),
        ]
        # 列表段去除 | 后命中（用户自然拼写法）
        if "|" in kw or kw != kw_no_sep:
            # SQL Server: 用 REPLACE 表达式做 LIKE；这里用 or_ 合并
            conds.append(
                func.replace(FeedbackTicket.location_dict_text, '|', '').like(like_no_sep_dict)
            )
        q = q.filter(or_(*conds))
    total = q.count()
    # preview=1：仅返回命中数，不查明细
    if preview:
        return _ok({"total": total, "page": page, "page_size": page_size, "items": []})
    items = q.order_by(desc(FeedbackTicket.id)).offset((page - 1) * page_size).limit(page_size).all()
    return _ok({
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [serialize_ticket(t, with_handle=True, anonymize=True) for t in items]
    })


class HandleReq(BaseModel):
    ticket_id: int
    status: str  # processing / done
    remark: str
    images: List[str] = []
    send_sms: bool = True


@router.post("/admin/handle")
async def admin_handle(
    req: HandleReq,
    db: Session = DatabaseDep,
    user: dict = Depends(require_admin())
):
    if req.status not in ("processing", "done"):
        return _fail("状态参数错误")
    t = _active(db.query(FeedbackTicket)).filter(FeedbackTicket.id == req.ticket_id).first()
    if not t:
        return _fail("工单不存在", 404)
    if t.status in ("done", "rejected", "cancelled") and req.status != "done":
        return _fail(f"当前状态({t.status})不可继续处理")
    t.status = req.status
    t.handle_remark = req.remark.strip()
    _BUCKET_PRIVATE_NAME = "guizhou-zhpt-prod-private"
    _FEEDBACK_DIR = "hq/feedback"
    def _norm(s: str) -> Optional[str]:
        """与 submit._normalize_key 同语义：把入参规范成 hq/feedback/<uuid>.<ext> 入库。"""
        if not s: return None
        s = s.strip().lstrip("/")
        if not s: return None
        if s.startswith("/feedback/image/"):
            s = s[len("/feedback/image/"):].split("?", 1)[0]
        if "?" in s:
            s = s.split("?", 1)[0]
        # 1) 带桶名全路径 → 剥桶名 + 剥 private/
        if s.startswith(f"{_BUCKET_PRIVATE_NAME}/"):
            s = s[len(f"{_BUCKET_PRIVATE_NAME}/"):]
            if s.startswith("private/"):
                s = s[len("private/"):]
            if s.startswith(_FEEDBACK_DIR + "/"):
                tail = s[len(_FEEDBACK_DIR) + 1:]
                return s if tail and "/" not in tail and "." in tail else None
            return None
        # 2) 业务前缀路径 → 剥 private/
        if s.startswith("private/hq/feedback/"):
            s = "hq/feedback/" + s[len("private/hq/feedback/"):]
            tail = s[len("hq/feedback/"):]
            return s if tail and "/" not in tail and "." in tail else None
        # 3) 旧业务前缀
        if s.startswith("feedback/"):
            s = "hq/feedback/" + s[len("feedback/"):]
            tail = s[len("hq/feedback/"):]
            return s if tail and "/" not in tail and "." in tail else None
        return None
    clean_h = [k for k in (_norm(x) for x in (req.images or [])) if k][:6]
    t.handle_images = json.dumps(clean_h, ensure_ascii=False)
    t.handler_name = user.get("admin_name") or user["name"]
    t.handler_phone = user["phone"]
    if req.status == "done":
        t.handle_at = datetime.now()
    add_timeline(
        db, t.id,
        "process" if req.status == "processing" else "done",
        t.handler_name, t.handler_phone, req.remark
    )

    sms_result = None
    if req.status == "done" and req.send_sms and t.reporter_phone and not t.is_anonymous:
        try:
            short = (req.remark or "").strip().replace("\n", " ")
            if len(short) > 60:
                short = short[:60] + "…"
            sms = SMSTool()
            r = sms.send_by_scenario(
                scenario='feedback_done',
                mobile=t.reporter_phone,
                values={
                    'title': _derive_title(t),
                    'result': short,
                },
                xs_id=t.reporter_id,
                xs_xm=t.reporter_name,
                lx=6, t_id=0, t_xm=t.handler_name or "管理员",
            )
            sms_result = r
            if r and r.get("success") and r.get("data"):
                t.sms_cpSubID = r["data"].get("cpSubID")
        except Exception as e:
            logger.error(f"办结短信发送失败: {e}", exc_info=True)
            sms_result = {"success": False, "msg": str(e)}

    db.commit()
    return _ok({"sms": sms_result})


class RejectReq(BaseModel):
    ticket_id: int
    reason: str


@router.post("/admin/reject")
async def admin_reject(
    req: RejectReq,
    db: Session = DatabaseDep,
    user: dict = Depends(require_admin("manager"))
):
    if not req.reason or len(req.reason.strip()) < 2:
        return _fail("请填写驳回原因")
    t = _active(db.query(FeedbackTicket)).filter(FeedbackTicket.id == req.ticket_id).first()
    if not t:
        return _fail("工单不存在", 404)
    if t.status in ("done", "rejected", "cancelled"):
        return _fail("当前状态不可驳回")
    t.status = "rejected"
    t.reject_reason = req.reason.strip()
    t.handler_name = user.get("admin_name") or user["name"]
    t.handler_phone = user["phone"]
    t.handle_at = datetime.now()
    add_timeline(db, t.id, "reject", t.handler_name, t.handler_phone, req.reason.strip())
    db.commit()
    return _ok()


class DeleteTicketReq(BaseModel):
    ticket_id: int
    reason: Optional[str] = ""


@router.post("/admin/delete")
async def admin_delete(
    req: DeleteTicketReq,
    db: Session = DatabaseDep,
    user: dict = Depends(require_admin("manager"))
):
    """管理员软删除工单(数据保留,前后端不再展示)。仅 manager / super 可删除"""
    t = _active(db.query(FeedbackTicket)).filter(FeedbackTicket.id == req.ticket_id).first()
    if not t:
        return _fail("工单不存在或已删除", 404)
    operator = user.get("admin_name") or user.get("name") or ""
    t.is_deleted = 1
    t.deleted_at = datetime.now()
    t.deleted_by = operator[:50]
    add_timeline(
        db, t.id, "delete",
        operator, user.get("phone", ""),
        (req.reason or "").strip()[:200] or "管理员删除"
    )
    db.commit()
    logger.info(f"反馈软删除: id={t.id} ticket_no={t.ticket_no} by={operator}")
    return _ok()
