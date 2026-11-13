"""Agent Token代理接口

小程序通过此接口获取 Agent 系统的 Token，APP_SECRET 仅存于后端。
业务请求（callback / messages）由小程序直连 Agent 服务器，不经过此代理。
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import httpx
import logging
import time

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent_proxy", tags=["Agent代理"])

# Agent 系统配置（SECRET 仅存后端，不暴露给前端）
AGENT_API_BASE = "https://weixin.qdndd.com.cn/api/v1"
APP_KEY = "wxapp_student_service_2026"
APP_SECRET = "A8F3D9E2C7B4F1A6E5D9C3B8A7F2E1D4"


# App Token 缓存（进程内）
_app_token_cache = {
    "token": None,
    "expire_time": 0
}


async def _get_app_token() -> str:
    """获取/刷新 App Token（带缓存）"""
    now = time.time()
    if _app_token_cache["token"] and now < _app_token_cache["expire_time"]:
        return _app_token_cache["token"]

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{AGENT_API_BASE}/agent/auth/app-token",
            json={"app_key": APP_KEY, "app_secret": APP_SECRET}
        )
        resp.raise_for_status()
        data = resp.json()

    if not data.get("success"):
        raise HTTPException(status_code=502, detail="获取App Token失败")

    _app_token_cache["token"] = data["app_token"]
    _app_token_cache["expire_time"] = now + data.get("expires_in", 86400) - 300  # 提前5分钟
    return _app_token_cache["token"]


class UserTokenRequest(BaseModel):
    user_id: str


class RefreshTokenRequest(BaseModel):
    user_id: str
    refresh_token: str


@router.post('/get_user_token')
async def get_user_token(req: UserTokenRequest):
    """为指定用户获取 Agent User Token
    
    前端调用此接口，后端用 APP_SECRET 换 App Token，再用 App Token 换 User Token。
    前端无需知道 APP_SECRET。
    """
    try:
        app_token = await _get_app_token()

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{AGENT_API_BASE}/agent/auth/user-token",
                json={"user_id": req.user_id},
                headers={"X-App-Token": app_token}
            )
            resp.raise_for_status()
            data = resp.json()

        if not data.get("success"):
            return {"success": False, "msg": data.get("message", "获取Token失败")}

        return {
            "success": True,
            "data": {
                "access_token": data["access_token"],
                "refresh_token": data["refresh_token"],
                "expires_in": data.get("expires_in", 900)
            }
        }
    except httpx.HTTPError as e:
        logger.error(f"获取User Token失败: {e}")
        return {"success": False, "msg": "Agent服务暂不可用"}
    except Exception as e:
        logger.error(f"获取User Token异常: {e}")
        return {"success": False, "msg": "系统异常"}


@router.post('/refresh_user_token')
async def refresh_user_token(req: RefreshTokenRequest):
    """刷新 Agent User Token
    
    前端 access_token 过期后调用此接口刷新。
    """
    try:
        app_token = await _get_app_token()

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{AGENT_API_BASE}/agent/auth/refresh-token",
                json={
                    "user_id": req.user_id,
                    "refresh_token": req.refresh_token
                },
                headers={"X-App-Token": app_token}
            )
            resp.raise_for_status()
            data = resp.json()

        if not data.get("success"):
            return {"success": False, "msg": data.get("message", "刷新Token失败")}

        return {
            "success": True,
            "data": {
                "access_token": data["access_token"],
                "expires_in": data.get("expires_in", 900)
            }
        }
    except httpx.HTTPError as e:
        logger.error(f"刷新User Token失败: {e}")
        return {"success": False, "msg": "Agent服务暂不可用"}
    except Exception as e:
        logger.error(f"刷新User Token异常: {e}")
        return {"success": False, "msg": "系统异常"}
