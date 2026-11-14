"""
exame 考试系统桥接层

中职学生登录小程序后，前端调用 /exame/* 接口。
本模块负责：
1. 验证小程序 token（已有依赖 verify_token_and_get_payload）
2. 从 token 中取 xs_xh（学号），调用 exame 后端的 zz-login 换取 exame JWT
3. 缓存 exame token（MySQL 表 + Redis 二级缓存），减少登录开销
4. 用 exame token 代理转发请求到 exame 后端 /api/v1/student/*

注意：本模块只代理"中职学生"相关接口（exam list / start / submit / records），
不涉及本地 users 表。管理员后台仍在 exame 系统独立运行。
"""
import os
import time
import json
import logging
import requests
from datetime import datetime, timedelta
from typing import Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel

from common.auth import verify_token_and_get_payload
from init.dependencies import get_db
from init.config import get_config
from init.redis_manager import redis_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/exame", tags=["exame考试桥接"])


# ============= 配置 =============

EXAME_BASE_URL = os.getenv("EXAME_BASE_URL", "http://localhost:8086").rstrip("/")
EXAME_TIMEOUT = int(os.getenv("EXAME_TIMEOUT", "30"))
EXAME_TOKEN_TTL = int(os.getenv("EXAME_TOKEN_TTL", str(2 * 3600)))  # 与 exame 一致（默认 24h，此处保守取 2h 强制刷新）
TOKEN_CACHE_KEY = "exame_token:{xs_xh}"  # Redis 二级缓存


# ============= Token 缓存 =============

class _ExameTokenCache:
    """两层缓存：Redis 短期 + MySQL 持久"""

    def __init__(self):
        self._memory_cache: dict[str, tuple[str, float]] = {}

    def _get_memory(self, xs_xh: str) -> Optional[str]:
        item = self._memory_cache.get(xs_xh)
        if not item:
            return None
        token, expire_at = item
        if time.time() >= expire_at:
            self._memory_cache.pop(xs_xh, None)
            return None
        return token

    def _set_memory(self, xs_xh: str, token: str, ttl: int):
        self._memory_cache[xs_xh] = (token, time.time() + ttl - 60)  # 提前 60s 失效

    def get_token(self, xs_xh: str) -> Optional[str]:
        # 1. 内存
        cached = self._get_memory(xs_xh)
        if cached:
            return cached

        # 2. Redis
        try:
            cached = redis_manager.get(TOKEN_CACHE_KEY.format(xs_xh=xs_xh))
            if cached:
                self._set_memory(xs_xh, cached, EXAME_TOKEN_TTL)
                return cached
        except Exception as e:
            logger.warning("exame token Redis 缓存读取失败: %s", e)

        return None

    def set_token(self, xs_xh: str, token: str, ttl: int = EXAME_TOKEN_TTL):
        self._set_memory(xs_xh, token, ttl)
        try:
            redis_manager.set(TOKEN_CACHE_KEY.format(xs_xh=xs_xh), token, ex=ttl)
        except Exception as e:
            logger.warning("exame token Redis 缓存写入失败: %s", e)

    def invalidate(self, xs_xh: str):
        self._memory_cache.pop(xs_xh, None)
        try:
            redis_manager.delete(TOKEN_CACHE_KEY.format(xs_xh=xs_xh))
        except Exception as e:
            logger.warning("exame token Redis 缓存失效失败: %s", e)


_exame_cache = _ExameTokenCache()


def _get_or_create_exame_token(xs_xh: str) -> str:
    """取 exame JWT；失效或不存在则调 zz-login 重新申请"""
    token = _exame_cache.get_token(xs_xh)
    if token:
        return token

    # 重新申请
    url = f"{EXAME_BASE_URL}/api/v1/student/auth/zz-login"
    try:
        resp = requests.post(url, json={"xh": xs_xh}, timeout=EXAME_TIMEOUT)
    except requests.RequestException as e:
        logger.error("调用 exame zz-login 失败: %s", e)
        raise HTTPException(status_code=503, detail=f"考试系统连接失败: {e}")

    if resp.status_code != 200:
        # 透传 exame 的错误信息（保持 {success, msg, data} 结构）
        try:
            payload = resp.json()
            msg = payload.get("msg") or payload.get("detail") or f"exame 返回 {resp.status_code}"
        except Exception:
            msg = f"exame 返回 {resp.status_code}"
        raise HTTPException(status_code=resp.status_code, detail=msg)

    data = resp.json().get("data") or {}
    token = data.get("access_token")
    if not token:
        raise HTTPException(status_code=500, detail="exame 未返回 access_token")

    _exame_cache.set_token(xs_xh, token)
    return token

# ============= 通用请求转发 =============

def _extract_xs_xh(payload: dict) -> str:
    xs_xh = payload.get("xs_xh") or payload.get("xh")
    if not xs_xh:
        raise HTTPException(status_code=403, detail="非中职学生身份，无法访问 exame")
    return str(xs_xh).strip()


def _proxy_request(
    method: str,
    path: str,
    payload: dict,
    *,
    params: Optional[dict] = None,
    json_body: Any = None,
) -> dict:
    """代理转发到 exame 后端"""
    xs_xh = _extract_xs_xh(payload)
    token = _get_or_create_exame_token(xs_xh)
    url = f"{EXAME_BASE_URL}{path}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        if method.upper() == "GET":
            resp = requests.get(url, headers=headers, params=params, timeout=EXAME_TIMEOUT)
        elif method.upper() == "POST":
            resp = requests.post(url, headers=headers, params=params, json=json_body, timeout=EXAME_TIMEOUT)
        elif method.upper() == "DELETE":
            resp = requests.delete(url, headers=headers, params=params, timeout=EXAME_TIMEOUT)
        else:
            raise HTTPException(status_code=500, detail=f"不支持的方法: {method}")
    except requests.RequestException as e:
        logger.error("exame 代理失败: %s %s, err=%s", method, url, e)
        raise HTTPException(status_code=503, detail=f"考试系统连接失败: {e}")

    # 处理 401：缓存可能过期，强制刷新一次
    if resp.status_code == 401:
        logger.info("exame token 失效，重试一次: %s", xs_xh)
        _exame_cache.invalidate(xs_xh)
        token = _get_or_create_exame_token(xs_xh)
        headers["Authorization"] = f"Bearer {token}"
        if method.upper() == "GET":
            resp = requests.get(url, headers=headers, params=params, timeout=EXAME_TIMEOUT)
        elif method.upper() == "POST":
            resp = requests.post(url, headers=headers, params=params, json=json_body, timeout=EXAME_TIMEOUT)
        elif method.upper() == "DELETE":
            resp = requests.delete(url, headers=headers, params=params, timeout=EXAME_TIMEOUT)

    # 直接透传 exame 的 JSON（{success, msg, data}）给前端
    try:
        return resp.json()
    except Exception:
        return {
            "success": resp.status_code < 400,
            "msg": f"exame 返回非 JSON 响应（{resp.status_code}）",
            "data": None,
            "_status_code": resp.status_code,
        }


# ============= 路由 =============

@router.get("/exams")
def list_exams(
    type: Optional[int] = Query(None, description="1在线考试 2模拟考试"),
    category_id: Optional[int] = Query(None),
    keyword: Optional[str] = Query(None),
    can_take: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    payload: dict = Depends(verify_token_and_get_payload),
):
    """获取可参加考试列表（代理 exame /api/v1/student/exams）"""
    return _proxy_request(
        "GET",
        "/api/v1/student/exams",
        payload,
        params={
            "type": type,
            "category_id": category_id,
            "keyword": keyword,
            "can_take": can_take,
            "page": page,
            "page_size": page_size,
        },
    )


class _StartExamBody(BaseModel):
    exam_id: int


@router.post("/exams/start")
def start_exam(
    body: _StartExamBody,
    payload: dict = Depends(verify_token_and_get_payload),
):
    """开始考试，返回题目 + record_id"""
    return _proxy_request(
        "POST",
        "/api/v1/student/exams/start",
        payload,
        json_body=body.model_dump(),
    )


class _SubmitExamBody(BaseModel):
    record_id: int
    answers: list


@router.post("/exams/submit")
def submit_exam(
    body: _SubmitExamBody,
    payload: dict = Depends(verify_token_and_get_payload),
):
    """提交试卷"""
    return _proxy_request(
        "POST",
        "/api/v1/student/exams/submit",
        payload,
        json_body=body.model_dump(),
    )

@router.get("/exams/records")
def list_records(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    payload: dict = Depends(verify_token_and_get_payload),
):
    """成绩列表（代理 exame）"""
    return _proxy_request(
        "GET",
        "/api/v1/student/exams/records",
        payload,
        params={"page": page, "page_size": page_size},
    )


@router.get("/exams/records/{record_id}")
def get_record_detail(
    record_id: int,
    payload: dict = Depends(verify_token_and_get_payload),
):
    """成绩详情"""
    return _proxy_request(
        "GET",
        f"/api/v1/student/exams/record/{record_id}",
        payload,
    )


@router.get("/exams/records/{record_id}/paper")
def get_record_paper(
    record_id: int,
    payload: dict = Depends(verify_token_and_get_payload),
):
    """成绩答卷（带正确答案）"""
    return _proxy_request(
        "GET",
        f"/api/v1/student/exams/record/{record_id}/paper",
        payload,
    )


@router.get("/exams/{exam_id}")
def get_exam_detail(
    exam_id: int,
    payload: dict = Depends(verify_token_and_get_payload),
):
    """获取考试详情（基于列表 + 单条）

    注意：必须放在所有 /exams/静态子路由（start/submit/records）
    之后定义，否则 "records" 会被误匹配为 exam_id。
    """
    # exame 后端没有专门的 detail 接口；用列表里取一条
    data = _proxy_request(
        "GET",
        "/api/v1/student/exams",
        payload,
        params={"page": 1, "page_size": 100},
    )
    items = (data.get("data") or {}).get("list") or []
    for item in items:
        if int(item.get("id", -1)) == int(exam_id):
            return {"success": True, "msg": "ok", "data": item}
    return {"success": False, "msg": "考试不存在或您无权查看", "data": None}


# ============= 调试接口（可选上线时关闭） =============

@router.get("/_health")
def health(payload: dict = Depends(verify_token_and_get_payload)):
    """健康检查：返回 exame zz-me 测试连通性"""
    xs_xh = _extract_xs_xh(payload)
    token = _get_or_create_exame_token(xs_xh)
    try:
        resp = requests.get(
            f"{EXAME_BASE_URL}/api/v1/student/auth/zz-me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        return {
            "success": resp.status_code < 400,
            "msg": "ok" if resp.status_code < 400 else f"exame {resp.status_code}",
            "data": {
                "exame_url": EXAME_BASE_URL,
                "exame_resp": resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text[:500],
            },
        }
    except Exception as e:
        return {"success": False, "msg": str(e), "data": None}