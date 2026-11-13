from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Any, Dict, Optional
from models.models import Teacher
from init.dependencies import DatabaseDep
from common.auth import verify_token_and_get_payload, create_token, create_refresh_token
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/open_teacher", tags=["开放教育教师"])


class QuickLoginRequest(BaseModel):
    code: str
    # 7 天手机号缓存 + openid 绑定：可选字段
    login_code: Optional[str] = None
    subject: Optional[str] = None


class OpenidLoginRequest(BaseModel):
    """openid 一键登录请求（wx.login code）"""
    code: str


def _bind_openid_to_teacher(db: Session, teacher: Teacher, openid: str) -> bool:
    """把 openid 绑定到教师记录（供后续 openid 一键登录使用）。

    规则（与学生端 /bind_openid 保持一致）：
      - 已有 openid 且非空 → 不覆盖（返回 False）
      - openid 已被别的教师占用 → 踢掉旧绑定，再写入
      - 同时维护 t_wx_openid_hash（隐私合规）

    Returns: 是否成功写入绑定。
    """
    if not openid:
        return False
    try:
        from utils.hash_util import hash_openid

        current = teacher.t_wx_openid
        if current and str(current).strip():
            # 已绑定：不覆盖，避免抢占他人绑定
            return False

        kicked = (
            db.query(Teacher)
            .filter(Teacher.t_wx_openid == openid, Teacher.t_id != teacher.t_id)
            .update(
                {"t_wx_openid": None, "t_wx_openid_hash": None},
                synchronize_session=False,
            )
        )
        if kicked:
            logger.warning(f"[bind_openid] 踢掉旧绑定 openid={openid} count={kicked}")

        teacher.t_wx_openid = openid
        teacher.t_wx_openid_hash = hash_openid(openid)
        db.commit()
        return True
    except Exception as e:
        logger.warning(f"[bind_openid] 绑定 openid 失败: {e}")
        db.rollback()
        return False


@router.post('/quick_login')
async def quick_login(
    request: QuickLoginRequest,
    db: Session = DatabaseDep
):
    """开放教育教师快捷登录（通过微信手机号匹配oa_t表）"""
    try:
        from utils.wx_utils import WxUtils

        phone_result = WxUtils.get_phone_number(request.code)
        if not phone_result:
            return {
                'success': True,
                'data': {'authorized': False, 'msg': '获取手机号失败'}
            }

        phone_info = phone_result.get('phone_info', {})
        phone_number = phone_info.get('phoneNumber') or phone_info.get('purePhoneNumber')
        if not phone_number:
            return {
                'success': True,
                'data': {'authorized': False, 'msg': '获取手机号失败'}
            }

        # 查询oa_t表匹配教师手机号
        teacher = db.query(Teacher).filter(Teacher.t_dh == phone_number).first()
        if not teacher:
            return {
                'success': True,
                'data': {'authorized': False, 'msg': '该手机号未注册为教师'}
            }

        # 生成token
        payload = {
            't_id': teacher.t_id,
            't_yhm': teacher.t_yhm,
            't_xm': teacher.t_xm,
            't_sfzh': teacher.t_sfzh,
            'is_open_teacher': True
        }
        token = create_token({**payload})
        refresh_token = create_refresh_token(payload)

        # 首次手机号登录：把 openid 绑到该教师，供后续 openid 一键登录使用
        openid_bound = False
        cache_written = False
        try:
            from common import phone_cache as _phone_cache

            if request.login_code:
                openid = _phone_cache.resolve_openid_by_login_code(request.login_code)
                if openid:
                    openid_bound = _bind_openid_to_teacher(db, teacher, openid)
                    if request.subject:
                        pure_phone = _phone_cache.normalize_phone(phone_number)
                        masked_phone = _phone_cache.mask_phone(pure_phone)
                        cache_written = _phone_cache.write_phone_cache(
                            openid=openid,
                            pure_phone=pure_phone,
                            role='self',
                            subject=request.subject,
                            extra={
                                'masked_phone': masked_phone,
                                'sfzh': getattr(teacher, 't_sfzh', None) or '',
                                'xm': teacher.t_xm,
                                't_id': teacher.t_id,
                            },
                        )
        except Exception as _e:
            logger.warning(f"[bind_openid] open_teacher.quick_login 绑定/写缓存失败: {_e}")

        return {
            'success': True,
            'data': {
                'authorized': True,
                'token': token,
                'refresh_token': refresh_token,
                'openid_bound': openid_bound,
                'cache_written': cache_written,
                'userInfo': {
                    't_id': teacher.t_id,
                    't_yhm': teacher.t_yhm,
                    't_xm': teacher.t_xm,
                    't_dh': teacher.t_dh,
                    't_bm_id': teacher.t_bm_id
                }
            }
        }
    except Exception as e:
        logger.error(f"开放教育教师快捷登录失败: {str(e)}")
        return {
            'success': False,
            'msg': f'登录失败: {str(e)}',
            'data': None
        }


@router.post('/quick_login_openid')
async def quick_login_openid(
    request: OpenidLoginRequest,
    db: Session = DatabaseDep
):
    """开放教育教师 openid 一键登录。

    前提：用户此前至少通过一次手机号快捷登录，后端已把 openid 绑定到该教师。
    """
    try:
        from utils.wx_utils import WxUtils

        code = request.code
        if not code:
            return {
                'success': True,
                'data': {'authorized': False, 'msg': '缺少关键参数'}
            }

        wx_result = WxUtils.get_openid_and_session_key(code)
        if not wx_result or not wx_result.get('openid'):
            return {
                'success': True,
                'data': {'authorized': False, 'msg': '登录失败，您提供的code错误'}
            }
        openid = wx_result.get('openid')

        # 查询教师：同一 openid 可能有多条，取 t_id 最大（最新绑定）
        teacher = (
            db.query(Teacher)
            .filter(Teacher.t_wx_openid == openid)
            .order_by(Teacher.t_id.desc())
            .first()
        )
        if not teacher:
            return {
                'success': True,
                'data': {
                    'authorized': False,
                    'msg': '当前微信还未绑定教师信息，请先使用「手机号快捷登录」完成一次登录'
                }
            }

        payload = {
            't_id': teacher.t_id,
            't_yhm': teacher.t_yhm,
            't_xm': teacher.t_xm,
            't_sfzh': teacher.t_sfzh,
            'is_open_teacher': True
        }
        token = create_token({**payload})
        refresh_token = create_refresh_token(payload)

        return {
            'success': True,
            'data': {
                'authorized': True,
                'token': token,
                'refresh_token': refresh_token,
                'userInfo': {
                    't_id': teacher.t_id,
                    't_yhm': teacher.t_yhm,
                    't_xm': teacher.t_xm,
                    't_dh': teacher.t_dh,
                    't_bm_id': teacher.t_bm_id
                }
            }
        }
    except Exception as e:
        logger.error(f"开放教育教师 openid 登录失败: {str(e)}")
        return {
            'success': False,
            'msg': f'登录失败: {str(e)}',
            'data': None
        }


class BookPickupSiteRequest(BaseModel):
    address: Optional[str] = None


def _get_teacher_from_payload(payload: Dict[str, Any], db: Session) -> Teacher:
    t_id = payload.get("t_id")
    teacher = db.query(Teacher).filter(Teacher.t_id == t_id).first() if t_id else None
    if teacher is None:
        raise HTTPException(status_code=404, detail="未找到教师信息")
    return teacher


@router.get('/book_pickup_site')
def get_book_pickup_site(
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep,
):
    """班主任查询自己设置的新书自取地点"""
    teacher = _get_teacher_from_payload(current_user, db)
    addr = (getattr(teacher, "t_book_pickup_addr", None) or "").strip()
    return {
        "success": True,
        "msg": "ok",
        "data": {"address": addr},
    }


@router.post('/book_pickup_site')
def save_book_pickup_site(
    body: BookPickupSiteRequest,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep,
):
    """班主任设置自己的新书自取地点（最多200字，可清空）"""
    teacher = _get_teacher_from_payload(current_user, db)
    addr = (body.address or "").strip()
    if len(addr) > 200:
        raise HTTPException(status_code=400, detail="地址过长，最多200字")
    try:
        teacher.t_book_pickup_addr = addr or None
        db.commit()
        logger.info(f"教师 {teacher.t_id} 设置自取地点: {addr[:30]}")
        return {"success": True, "msg": "保存成功", "data": {"address": addr}}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("保存自取地点失败")
        raise HTTPException(status_code=500, detail=f"保存失败: {e}")
