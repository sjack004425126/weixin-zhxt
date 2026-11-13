"""
学生 openid 补采端点。

设计要点:
  - 字段为空才写;已有不动(避免覆盖合法绑定)
  - 若该 openid 已被另一学生占用,踢掉旧绑定(清空对方 openid/hash)
  - 同时维护 openid_hash(隐私合规)
  - 前端静默调用,失败不影响登录
"""
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from common.auth import verify_token_and_get_payload
from init.dependencies import DatabaseDep
from models.models import Student, ZzXs
from utils.hash_util import hash_openid
from utils.wx_utils import WxUtils

logger = logging.getLogger(__name__)

bind_openid_router = APIRouter(prefix="/bind_openid", tags=["学生openid补采"])
# 别名(保持 main.py include_router 风格)
router = bind_openid_router


class BindOpenidRequest(BaseModel):
    code: str


def _ok(data: dict = None, msg: str = "ok"):
    return {"success": True, "msg": msg, "data": data or {}}


def _fail(msg: str):
    return {"success": False, "msg": msg, "data": {}}


def _do_bind(db: Session, model, pk_value, openid: str, h: str, pk_col: str):
    """核心绑定逻辑。

    Args:
        db: 数据库会话
        model: SQLAlchemy 模型类(Student 或 ZzXs)
        pk_value: 当前学生主键值
        openid: 微信 openid
        h: openid 的 SHA256 hash
        pk_col: 主键字段名('xs_id' / 'id')

    Returns:
        (bound, already, kicked)
    """
    record = db.query(model).filter(getattr(model, pk_col) == pk_value).first()
    if record is None:
        return None

    current = record.xs_wx_openid
    if current and str(current).strip():
        return (False, True, 0)

    kicked = (
        db.query(model)
        .filter(model.xs_wx_openid == openid, getattr(model, pk_col) != pk_value)
        .update(
            {"xs_wx_openid": None, "xs_wx_openid_hash": None},
            synchronize_session=False,
        )
    )
    if kicked:
        logger.warning(
            "[bind_openid] 踢掉旧绑定 model=%s openid=%s count=%s",
            model.__tablename__,
            openid,
            kicked,
        )

    record.xs_wx_openid = openid
    record.xs_wx_openid_hash = h
    db.commit()
    return (True, False, kicked)


# ----------------------------------------------------------------------------
# 端点 1:中职学生(/bind_openid/zz)
# ----------------------------------------------------------------------------
@bind_openid_router.post("/zz", summary="中职学生补采 openid")
async def bind_openid_zz(
    body: BindOpenidRequest,
    db: Session = DatabaseDep,
    payload: dict = Depends(verify_token_and_get_payload),
):
    xs_id = payload.get("xs_id")
    if not xs_id:
        return _fail("token 无效,缺少 xs_id")

    wx = WxUtils.get_openid_and_session_key(body.code)
    if not wx or not wx.get("openid"):
        return _fail("微信登录失败,请稍后重试")

    h = hash_openid(wx["openid"])
    result = _do_bind(db, ZzXs, xs_id, wx["openid"], h, pk_col="id")
    if result is None:
        return _fail("中职学生不存在")
    bound, already, kicked = result
    return _ok({"bound": bound, "already": already, "conflict_kicked": kicked})


# ----------------------------------------------------------------------------
# 端点 2:开放学生(/bind_openid/zs)
# ----------------------------------------------------------------------------
@bind_openid_router.post("/zs", summary="开放学生补采 openid")
async def bind_openid_zs(
    body: BindOpenidRequest,
    db: Session = DatabaseDep,
    payload: dict = Depends(verify_token_and_get_payload),
):
    xs_id = payload.get("xs_id")
    if not xs_id:
        return _fail("token 无效,缺少 xs_id")

    wx = WxUtils.get_openid_and_session_key(body.code)
    if not wx or not wx.get("openid"):
        return _fail("微信登录失败,请稍后重试")

    h = hash_openid(wx["openid"])
    result = _do_bind(db, Student, xs_id, wx["openid"], h, pk_col="xs_id")
    if result is None:
        return _fail("开放学生不存在")
    bound, already, kicked = result
    return _ok({"bound": bound, "already": already, "conflict_kicked": kicked})
