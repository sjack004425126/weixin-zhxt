"""
招生页背景音乐 URL 接口（zhpt-new 重构版）

业务路径
--------
音乐文件存放在私有桶 ``guizhou-zhpt-prod-private`` 下：

    audio/Kiss The Rain.mp3    ← 当前招生页背景音乐

访问方式
--------
浏览器 → ``/audio/url?key=audio/Kiss The Rain.mp3`` → FastAPI 生成 Sig V4 预签名 URL
       → 浏览器 → ``/object/<bucket>/<key>?X-Amz-...`` → nginx → MinIO 验签 → 文件

为何要前端拿签名 URL 而不直接用 /object 转发
------------------------------------------------
微信小程序 InnerAudioContext 要求 src 是普通 HTTPS URL，不能使用带 ``X-Amz-Signature``
查询串的相对路径。后端需要返回带 host 的完整 URL，让 InnerAudioContext 可直接拉取。
"""
from fastapi import APIRouter, HTTPException, Query
from urllib.parse import quote

from services.minio_service import (
    BUCKET_PRIVATE,
    BUCKET_PUBLIC,
    split_bucket_key,
    sign_object_url,
    PRESIGN_EXPIRES_SECONDS,
    stat_object,
)
from utils.minio_client import gateway
import logging

router = APIRouter(prefix="/audio", tags=["背景音乐"])
logger = logging.getLogger(__name__)


# ============================================================
# 业务常量：当前招生页背景音乐（私有桶）
# ============================================================
ENROLL_BGM_PATH = f"{BUCKET_PRIVATE}/audio/Kiss The Rain.mp3"
ENROLL_BGM_KEY = "audio/Kiss The Rain.mp3"


@router.get("/url")
async def get_audio_url(
    key: str = Query(
        default="audio/Kiss The Rain.mp3",
        description="对象 key 或 DB 路径（<bucket>/<key>）",
    ),
    host: str = Query(
        default="",
        description="前端访问域名（可选）；缺省时由前端拿到相对路径自己拼 host",
    ),
):
    """返回招生页背景音乐的 Sig V4 预签名 URL。

    默认 ``key=audio/Kiss The Rain.mp3``，命中私有桶 ``guizhou-zhpt-prod-private``。
    如果音乐文件不存在，返回 404，前端可以降级处理（静默不播放）。
    """
    # 1) 解析 key
    if "/" in (key or ""):
        try:
            bucket, real_key = split_bucket_key(key)
        except Exception:
            bucket, real_key = BUCKET_PRIVATE, key
    else:
        bucket, real_key = BUCKET_PRIVATE, key

    # 2) 校验对象是否存在（404 → 前端降级）
    try:
        if not stat_object(f"{bucket}/{real_key}"):
            raise HTTPException(status_code=404, detail=f"音频对象不存在: {bucket}/{real_key}")
    except HTTPException:
        raise
    except Exception as e:
        # stat 异常不阻塞签名（容错）：MinIO 偶尔 503 时仍希望前端能拿到 URL 试一次
        logger.warning("stat_object 异常，但仍尝试签发: %s", e)

    # 3) 生成 Sig V4 预签名 URL
    try:
        signed = sign_object_url(real_key, bucket=bucket)
    except Exception as e:
        logger.error("生成音频预签名 URL 失败: %s", e)
        raise HTTPException(status_code=500, detail=f"生成签名 URL 失败: {e}")

    # 4) 拼 host（如果有）
    final_url = f"{host.rstrip('/')}{signed}" if host else signed

    return {
        "success": True,
        "msg": "ok",
        "data": {
            "url": final_url,
            "bucket": bucket,
            "key": real_key,
            "expires_in": PRESIGN_EXPIRES_SECONDS,
            "content_type": "audio/mpeg",
        },
    }


@router.get("/info")
async def get_audio_info():
    """返回当前默认背景音乐的基本信息（用于前端展示/调试）。"""
    bucket, key = BUCKET_PRIVATE, ENROLL_BGM_KEY
    info = {"bucket": bucket, "key": key, "exists": False, "size": None, "content_type": None}
    try:
        obj = gateway.stat_object_full(bucket, key)
        if obj:
            info["exists"] = True
            info["size"] = obj.size
            info["content_type"] = obj.content_type if hasattr(obj, "content_type") else None
    except Exception as e:
        logger.warning("stat audio 失败: %s", e)
    return {"success": True, "msg": "ok", "data": info}


# ============================================================
# 公共桶图标（无需签名，长期有效）
#   type=music → images/music.png
#   type=home  → images/home.png
#
# 兜底策略：
#   1) 优先取公共桶里的 PNG（设计同学随时可更新）
#   2) 公共桶里没有时，返回内联的 SVG data URL（白底黑房）
# ============================================================
_PUBLIC_ICONS = {
    "music": {
        "key": "images/music.png",
        "fallback_svg": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48">'
            '<path fill="#1890ff" d="M35 4l-22 7v22.55A8 8 0 1 0 17 41l1-.46A6 6 0 1 1 14 36l3-1V18l18-6Z"/>'
            '</svg>'
        ),
    },
    "home": {
        "key": "images/home.png",
        "fallback_svg": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48">'
            '<path fill="#ffffff" d="M24 5L2 24h6v18h12V28h8v14h12V24h6z"/>'
            '</svg>'
        ),
    },
}

def _svg_to_data_url(svg: str) -> str:
    import urllib.parse
    encoded = urllib.parse.quote(svg, safe='')
    return f"data:image/svg+xml;utf8,{encoded}"

@router.get("/icon")
async def get_music_icon_url(
    type: str = Query(default="music", description="图标类型：music | home"),
    host: str = Query(default="", description="前端访问域名；缺省时由前端自己拼 host"),
):
    """返回公共桶音乐/返回首页图标的直接 URL（无需签名，长期有效）。"""
    entry = _PUBLIC_ICONS.get((type or "").lower())
    if not entry:
        raise HTTPException(status_code=400, detail=f"未知图标类型: {type}")
    key = entry["key"]
    bucket = BUCKET_PUBLIC
    info = {"bucket": bucket, "key": key, "exists": False, "url": "", "type": type,
            "usedFallback": False}
    try:
        if stat_object(f"{bucket}/{key}"):
            info["exists"] = True
            rel = f"/object/{bucket}/{key}"
            info["url"] = f"{host.rstrip('/')}{rel}" if host else rel
        else:
            # 公共桶里没有这个 png，使用 SVG fallback
            info["usedFallback"] = True
            info["url"] = _svg_to_data_url(entry["fallback_svg"])
    except Exception as e:
        logger.warning("stat public icon 失败: %s", e)
        # 出错也给一个 fallback SVG，前端图标永远可用
        info["usedFallback"] = True
        info["url"] = _svg_to_data_url(entry["fallback_svg"])
    return {"success": True, "msg": "ok", "data": info}
