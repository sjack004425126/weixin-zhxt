"""
通用手机号快捷认证入口（zhpt-new 内全子系统共享）。

设计目标：
    - 任意子系统（vocational-new-payment / student-info / feedback-login /
      user-center）只要前端调过 /auth/verify_phone 一次，
      7 天内任意子系统都可通过 /auth/get_cached_verify 直接拿到业务身份。
    - 业务 token（access_token / verify_token）仍由各自的原业务接口签发，
      本控制器只负责"缓存层"。
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Optional

from init.dependencies import DatabaseDep
from common import phone_cache
from utils.wx_utils import WxUtils


router = APIRouter(prefix="/auth", tags=["通用手机号认证"])


# ==================== 请求模型 ====================


class VerifyPhoneRequest(BaseModel):
    """
    通用手机号认证请求。
    - login_code: 前端 wx.login() 返回的 code（用来换 openid，作为缓存 key）
    - phone_code: 前端 <button open-type="getPhoneNumber"> 返回的 code（用来解手机号）
    - subject:   业务身份标识
    - role:      'self' 或 'parent'
    """
    login_code: str = Field(..., description="wx.login() 返回的 code")
    phone_code: str = Field(..., description="getPhoneNumber 返回的 code")
    subject: str = Field(..., description="业务身份标识")
    role: str = Field(default="self", description="self 或 parent")


class GetCachedVerifyRequest(BaseModel):
    """
    查询手机号授权缓存。
    - login_code: 前端 wx.login() 返回的 code
    - subject:    期望使用的业务身份（命中后用于一致性校验）
    """
    login_code: str
    subject: str


class ClearCachedVerifyRequest(BaseModel):
    """清除手机号授权缓存（"重选身份"按钮调用）"""
    login_code: str


# ==================== 工具：解码手机号 ====================


def _decode_phone(phone_code: str):
    """调用 WxUtils 解密手机号，返回 (pure_phone, masked_phone)。失败抛 HTTPException。"""
    wx_result = WxUtils.get_phone_number(phone_code)
    if not wx_result or not wx_result.get("phone_info"):
        raise HTTPException(status_code=400, detail="微信手机号获取失败，请重试")

    phone_info = wx_result["phone_info"]
    wx_phone = phone_info.get("phoneNumber") or phone_info.get("purePhoneNumber") or ""
    if not wx_phone:
        raise HTTPException(status_code=400, detail="微信未返回手机号信息")

    pure = phone_cache.normalize_phone(wx_phone)
    masked = phone_cache.mask_phone(pure)
    return pure, masked


# ==================== 1) /auth/verify_phone  ====================


@router.post("/verify_phone")
async def verify_phone(
    payload: VerifyPhoneRequest,
    db: Session = DatabaseDep,
):
    """
    通用手机号快捷认证。
    - 用 login_code 换 openid
    - 用 phone_code 换手机号
    - 归一化手机号后写 7 天缓存
    - 由前端按 subject 调对应业务接口签发业务 token（access_token / verify_token）
    """
    login_code = (payload.login_code or "").strip()
    phone_code = (payload.phone_code or "").strip()
    subject = (payload.subject or "").strip()
    role = (payload.role or "self").strip().lower()

    if not login_code or not phone_code:
        return {"success": False, "msg": "缺少 login_code 或 phone_code", "data": None}
    if subject not in phone_cache.ALL_SUBJECTS:
        return {"success": False, "msg": f"subject 非法，应为 {sorted(phone_cache.ALL_SUBJECTS)}", "data": None}
    if role not in ("self", "parent"):
        return {"success": False, "msg": "role 只能为 self 或 parent", "data": None}

    # 1) 解手机号
    try:
        pure_phone, masked_phone = _decode_phone(phone_code)
    except HTTPException as e:
        return {"success": False, "msg": e.detail, "data": None}

    if not pure_phone:
        return {"success": False, "msg": "微信未返回有效手机号", "data": None}

    # 2) 换 openid
    openid = phone_cache.resolve_openid_by_login_code(login_code)
    if not openid:
        return {"success": False, "msg": "无法解析 openid，请检查 wx.login 状态", "data": None}

    # 3) 写缓存
    ok = phone_cache.write_phone_cache(
        openid=openid,
        pure_phone=pure_phone,
        role=role,
        subject=subject,
        extra={
            "masked_phone": masked_phone,
        },
    )

    if ok:
        print(f'[auth.verify_phone] 缓存写入成功 openid={openid[:8]}*** subject={subject} '
              f'role={role} pure_phone={pure_phone} ttl={phone_cache.PHONE_CACHE_TTL_SECONDS}s')
    else:
        print(f'[auth.verify_phone] 缓存写入失败（不影响业务） openid={openid[:8]}***')

    return {
        "success": True,
        "msg": "验证通过" if ok else "验证通过（缓存写入失败，下次需重新授权）",
        "data": {
            "openid": openid,
            "pure_phone": pure_phone,
            "masked_phone": masked_phone,
            "role": role,
            "subject": subject,
            "cache_written": ok,
            "expires_in": phone_cache.PHONE_CACHE_TTL_SECONDS,
        },
    }


# ==================== 2) /auth/get_cached_verify  ====================


@router.post("/get_cached_verify")
async def get_cached_verify(payload: GetCachedVerifyRequest):
    """
    查询缓存。
    返回：
      - 命中：{ success: True, data: { cached: True, pure_phone, masked_phone, role, expires_in } }
      - 未命中：{ success: True, data: { cached: False } }
    """
    login_code = (payload.login_code or "").strip()
    subject = (payload.subject or "").strip()

    if not login_code:
        return {"success": False, "msg": "缺少 login_code", "data": None}
    if subject not in phone_cache.ALL_SUBJECTS:
        return {"success": False, "msg": f"subject 非法，应为 {sorted(phone_cache.ALL_SUBJECTS)}", "data": None}

    openid = phone_cache.resolve_openid_by_login_code(login_code)
    if not openid:
        return {"success": False, "msg": "无法解析 openid", "data": None}

    cache = phone_cache.read_phone_cache(openid)
    if not cache:
        print(f'[auth.get_cached_verify] 未命中 openid={openid[:8]}*** subject={subject}')
        return {
            "success": True,
            "msg": "未命中缓存",
            "data": {"cached": False, "openid": openid},
        }

    print(f'[auth.get_cached_verify] 命中 openid={openid[:8]}*** subject={subject} '
          f'cache_subject={cache.get("subject")} role={cache.get("role")} '
          f'pure_phone={cache.get("pure_phone")} verified_at={cache.get("verified_at")}')

    # 计算剩余 TTL（前端可显示倒计时）
    expires_in = phone_cache.PHONE_CACHE_TTL_SECONDS  # 简化：取配置上限；前端不需要精确到秒

    return {
        "success": True,
        "msg": "命中缓存",
        "data": {
            "cached": True,
            "openid": openid,
            "pure_phone": cache.get("pure_phone"),
            "masked_phone": cache.get("masked_phone") or phone_cache.mask_phone(cache.get("pure_phone") or ""),
            "role": cache.get("role"),
            "subject": cache.get("subject"),
            "sfzh": cache.get("sfzh"),
            "xm": cache.get("xm"),
            "verified_at": cache.get("verified_at"),
            "expires_in": expires_in,
        },
    }


# ==================== 3) /auth/clear_cached_verify  ====================


@router.post("/clear_cached_verify")
async def clear_cached_verify(payload: ClearCachedVerifyRequest):
    """主动清除缓存（"重选身份"入口）。"""
    login_code = (payload.login_code or "").strip()
    if not login_code:
        return {"success": False, "msg": "缺少 login_code", "data": None}

    openid = phone_cache.resolve_openid_by_login_code(login_code)
    if not openid:
        return {"success": False, "msg": "无法解析 openid", "data": None}

    ok = phone_cache.clear_phone_cache(openid)
    return {
        "success": True,
        "msg": "清除成功" if ok else "清除失败（不影响业务）",
        "data": {"openid": openid, "cleared": ok},
    }


# ==================== 4) /auth/issue_verify_token_by_cache  ====================
# 缓存命中后，前端用缓存手机号直接换取业务 token。
# 不重复走 wx.getPhoneNumber（避免用户再次授权）。

class IssueByCacheRequest(BaseModel):
    login_code: str = Field(..., description="wx.login() 返回的 code")
    subject: str = Field(..., description="业务身份")
    role: str = Field(default="self", description="self / parent")


def _issue_vocational_verify_token(db: Session, pure_phone: str, role: str):
    """
    中职新生缴费场景：用 pure_phone 反查报名记录，签发 verify_token。
    返回 (verify_token, sfzh, xm, masked_phone) 或 (None, None, None, error_msg)。
    """
    from models.models import ZzXs, ZzSys
    sys_info = db.query(ZzSys).first()
    current_nd = sys_info.zz_xsjf_nd if sys_info else None

    phone_col = ZzXs.xsdh if role == "self" else ZzXs.jzdh

    candidates = (
        db.query(ZzXs)
        .filter(phone_col == pure_phone)
        .filter(ZzXs.nd == current_nd)
        .all()
    ) if current_nd else []
    if not candidates:
        candidates = (
            db.query(ZzXs)
            .filter(phone_col.like(f"%{pure_phone}%"))
            .all()
        )

    matched = []
    for c in candidates:
        stored = (getattr(c, "xsdh" if role == "self" else "jzdh") or "").strip().replace(" ", "")
        if stored.startswith("+86"):
            stored = stored[3:]
        if stored == pure_phone:
            matched.append(c)

    if not matched:
        return None, None, None, f"未查询到使用该{'本人手机号' if role == 'self' else '家长手机号'}的报名信息"
    if len(matched) > 1:
        return None, None, None, "该手机号对应多条报名记录，请联系学校核实"

    student_xs = matched[0]
    verify_token = _issue_verify_token_student(student_xs.sfzh, role)
    return verify_token, student_xs.sfzh, student_xs.xm, None


def _issue_verify_token_student(sfzh: str, role: str) -> str:
    """
    复用 vocational_tuition 中的 token 签发逻辑。
    这里直接调用 vocational_tuition 的私有函数。
    """
    from controllers.vocational_tuition import _issue_verify_token as _voc_issue
    return _voc_issue(sfzh, role)


@router.post("/issue_verify_token_by_cache")
async def issue_verify_token_by_cache(
    payload: IssueByCacheRequest,
    db: Session = DatabaseDep,
):
    """
    缓存命中后，直接用缓存手机号换业务 token。
    按 subject 路由到对应业务：
      - vocational_new_payment  → 签 verify_token (10 分钟)
      - 其它 subject 暂未启用，后续扩展
    """
    login_code = (payload.login_code or "").strip()
    subject = (payload.subject or "").strip()
    role = (payload.role or "self").strip().lower()

    if not login_code:
        return {"success": False, "msg": "缺少 login_code", "data": None}
    if subject not in phone_cache.ALL_SUBJECTS:
        return {"success": False, "msg": f"subject 非法", "data": None}
    if role not in ("self", "parent"):
        return {"success": False, "msg": "role 只能为 self 或 parent", "data": None}

    openid = phone_cache.resolve_openid_by_login_code(login_code)
    if not openid:
        return {"success": False, "msg": "无法解析 openid", "data": None}

    cache = phone_cache.read_phone_cache(openid)
    if not cache:
        return {"success": False, "msg": "缓存已过期或不存在", "data": None}

    pure_phone = cache.get("pure_phone") or ""
    print(f'[auth.issue_verify_token_by_cache] 进入 openid={openid[:8]}*** subject={subject} '
          f'role={role} pure_phone={pure_phone} cache_subject={cache.get("subject")}')

    if subject == phone_cache.SUBJECT_VOCATIONAL_PAYMENT:
        verify_token, sfzh, xm, err = _issue_vocational_verify_token(db, pure_phone, role)
        if err:
            print(f'[auth.issue_verify_token_by_cache] 反查报名失败: {err}')
            return {"success": False, "msg": err, "data": None}
        print(f'[auth.issue_verify_token_by_cache] 缓存换 token 成功 sfzh={sfzh} xm={xm}')
        return {
            "success": True,
            "msg": "OK",
            "data": {
                "verify_token": verify_token,
                "sfzh": sfzh,
                "student_name": xm,
                "masked_phone": cache.get("masked_phone") or phone_cache.mask_phone(pure_phone),
                "expires_in": 600,  # 10 分钟，与 verify_token TTL 对齐
            },
        }

    # 其它 subject 暂未接入"换 token"，返回缓存中的基础字段供前端自行处理
    return {
        "success": True,
        "msg": "OK",
        "data": {
            "pure_phone": pure_phone,
            "masked_phone": cache.get("masked_phone") or phone_cache.mask_phone(pure_phone),
            "role": role,
            "subject": subject,
            "sfzh": cache.get("sfzh"),
            "xm": cache.get("xm"),
        },
    }
