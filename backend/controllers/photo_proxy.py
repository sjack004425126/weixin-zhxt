"""
私有桶代理 / 公共桶兜底代理（统一入口）。

参考 headphoto/backend/app/api/v1/photo_proxy.py 的设计：
- 所有私有桶对象对外访问统一走本路由
- 同步阻塞 IO 丢进专用线程池（隔离默认线程池）
- 每个 MinIO 操作有硬超时；超时即放弃本次请求
- 支持 HTTP Range / 206 边下边播

挂载在 main.py 根路径下，不带 /api/v1 前缀，因为前端 <img src=...> 是绝对路径。

路由
----
GET /photo/get_headphoto/{sfzh}            头像（私有桶根，{sfzh}.jpg）
GET /object/{path:path}                    通用私有桶 HMAC 签名代理
GET /feedback/image/{object_key:path}      反馈工单图片（与小程序签名一致）
GET /brochure/image/{path:path}            招生简章图片
GET /job/image/{filename:path}             就业推荐配图
GET /photo/zs_image/{filename}             3+4 报名图片（兼容老路径）
GET /static/{path:path}                    公共桶静态资源（开发/测试兜底，生产走 nginx）
GET /public/{path:path}                    公开桶业务公开资源（开发/测试兜底，生产走 nginx）
"""
import asyncio
import hashlib
import hmac as _hmac
import logging
import mimetypes
import re
import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response, StreamingResponse

from services.minio_service import (
    BUCKET_PRIVATE,
    BUCKET_PUBLIC,
    FEEDBACK_IMG_SECRET,
    FEEDBACK_URL_EXPIRE,
    STATIC_LINK_EXPIRE_SECONDS,
    user_type_to_headphoto_subdir,
    verify_feedback_sign,
    verify_object_sign,
    verify_photo_sign,
)
from utils.minio_client import gateway

logger = logging.getLogger(__name__)

router = APIRouter(tags=["私有桶代理"])

_CACHE_HEADERS = {"Cache-Control": "private, max-age=3600"}


# 私有桶代理专用线程池（隔离默认线程池，避免 MinIO 卡死拖垮其他 web 请求）
# 限制并发数：单 client 没法支撑大并发（N 个线程一起拉 → urllib3 连接池锁竞争 → hang）
_PROXY_THREAD_POOL = ThreadPoolExecutor(
    max_workers=16,
    thread_name_prefix="photo-proxy",
)


# 单个 MinIO 操作的最大允许耗时（防止 urllib3 在 503 后无限 retry hang 住线程）
_MINIO_OP_TIMEOUT_S = 8.0


def _open_minio():
    """获取 MinIO client；不可用时直接 503。"""
    if not gateway.available:
        raise HTTPException(503, "对象存储不可用")
    return gateway.client


# ============================================================
# 鉴权辅助：管理员 token 解析（Optional，用于图片代理）
# ============================================================
async def _try_admin(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    """尝试解析 admin token；失败返回 None。

    这里只关心「能否解析出有 admin 权限的用户」，不强制依赖某个固定字段名。
    zhpt-new 的 admin token 通常含 admin_id / is_admin；普通 user token 也含
    user_id；这里只要 token 能解出 + 包含至少一个识别字段就算合法。
    """
    if not authorization:
        return None
    try:
        # 使用 common.auth.verify_token_for_dependencies（异常即失败）
        from common.auth import verify_token_for_dependencies
        token = authorization.replace("Bearer ", "", 1)
        payload = verify_token_for_dependencies(token)
        if payload.get("admin_id") or payload.get("is_admin") or payload.get("user_id"):
            return payload
    except Exception:
        return None
    return None


# ============================================================
# 通用私有桶流式响应（支持 HTTP Range / 206）
# ============================================================
async def _stream_private_object(
    object_key: str,
    default_media: str = "application/octet-stream",
    request: Optional[Request] = None,
):
    """从私有桶流式返回对象，支持 HTTP Range / 206。

    所有同步阻塞 IO 都丢进专用线程池（隔离默认线程池，避免 MinIO 卡死时
    拖垮所有其他 web 请求）。每个 MinIO 操作有硬超时；超时即放弃本次请求，
    由 gateway 单例 client 自管理健康状态。
    """
    client = _open_minio()
    loop = asyncio.get_running_loop()

    # 先 stat 拿总长（带超时）
    try:
        st = await asyncio.wait_for(
            loop.run_in_executor(_PROXY_THREAD_POOL, client.stat_object, BUCKET_PRIVATE, object_key),
            timeout=_MINIO_OP_TIMEOUT_S,
        )
        total = int(st.size or 0)
    except asyncio.TimeoutError:
        logger.error("stat_object timeout (%ss) key=%s", _MINIO_OP_TIMEOUT_S, object_key)
        raise HTTPException(504, "对象存储响应超时")
    except Exception as e:
        logger.error(
            "object miss (stat): bucket=%s key=%s err_type=%s err=%s",
            BUCKET_PRIVATE, object_key, type(e).__name__, e,
        )
        raise HTTPException(404, f"Not Found: {object_key}")

    media_type = mimetypes.guess_type(object_key)[0] or default_media
    base_headers = {
        **_CACHE_HEADERS,
        "Accept-Ranges": "bytes",
    }

    range_header = ""
    if request is not None:
        range_header = request.headers.get("range") or request.headers.get("Range") or ""

    if range_header:
        m = re.match(r"bytes=(\d+)-(\d*)", range_header.strip())
        if not m:
            raise HTTPException(416, "Invalid Range")
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else max(total - 1, 0)
        if total == 0 or start >= total:
            return Response(
                status_code=416,
                headers={**base_headers, "Content-Range": f"bytes */{total}"},
            )
        end = min(end, total - 1)
        length = end - start + 1
        try:
            response = await asyncio.wait_for(
                loop.run_in_executor(
                    _PROXY_THREAD_POOL,
                    client.get_object,
                    BUCKET_PRIVATE, object_key,
                    start, length,
                ),
                timeout=_MINIO_OP_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.error("get_object(range) timeout (%ss) key=%s start=%s", _MINIO_OP_TIMEOUT_S, object_key, start)
            raise HTTPException(504, "对象存储响应超时")
        except Exception as e:
            logger.error("get_object range failed: %s", e)
            raise HTTPException(404, f"Not Found: {object_key}")

        headers = {
            **base_headers,
            "Content-Range": f"bytes {start}-{end}/{total}",
            "Content-Length": str(length),
        }
        # Range 分支用一次性 Response 而非 StreamingResponse：
        # Starlette 的 StreamingResponse 对所有 chunk 标 more_body=True，
        # ASGI 协议层会自动选 chunked Transfer-Encoding，忽略手工 Content-Length。
        # 而 HTTP 206 必须明确 Content-Length（chunked 与 Content-Length 互斥）。
        # 代价是 range 字节一次性读进内存——对 KB-MB 级图片/头像/工单图可接受；
        # 大文件 Range 应当走 nginx，本路由仅兜底 nginx 故障场景。
        try:
            body = await asyncio.wait_for(
                loop.run_in_executor(_PROXY_THREAD_POOL, response.read, length),
                timeout=_MINIO_OP_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.error("range read timeout key=%s start=%s length=%s", object_key, start, length)
            raise HTTPException(504, "对象存储响应超时")
        finally:
            try:
                response.close()
                response.release_conn()
            except Exception:
                pass
        return Response(
            content=body if isinstance(body, bytes) else bytes(body),
            status_code=206,
            media_type=media_type,
            headers=headers,
        )

    # 完整体
    try:
        response = await asyncio.wait_for(
            loop.run_in_executor(_PROXY_THREAD_POOL, client.get_object, BUCKET_PRIVATE, object_key),
            timeout=_MINIO_OP_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        logger.error("get_object timeout (%ss) key=%s", _MINIO_OP_TIMEOUT_S, object_key)
        raise HTTPException(504, "对象存储响应超时")
    except Exception as e:
        logger.error("get_object failed: %s", e)
        raise HTTPException(404, f"Not Found: {object_key}")

    async def _iter_full():
        try:
            while True:
                # 必须用 read(amt)，不能用 stream()（生成器陷阱）。
                chunk = await asyncio.wait_for(
                    loop.run_in_executor(_PROXY_THREAD_POOL, response.read, 32 * 1024),
                    timeout=_MINIO_OP_TIMEOUT_S,
                )
                if not chunk:
                    break
                yield bytes(chunk)
        except asyncio.TimeoutError:
            logger.warning("iter_full stream timeout key=%s", object_key)
        except Exception as e:
            logger.warning("iter_full stream error: %s", e)
        finally:
            try:
                response.close()
                response.release_conn()
            except Exception:
                pass

    # 不要手动设 Content-Length：StreamingResponse 是流式（chunked transfer），
    # starlette 会忽略手动 Content-Length 并改用 Transfer-Encoding: chunked。
    # 设了反而会让 uvicorn 检测 "Content-Length > 实际发送字节" 时报
    # "Response content shorter than Content-Length"。
    headers = {**base_headers}
    return StreamingResponse(_iter_full(), media_type=media_type, headers=headers)


# ============================================================
# 公共桶流式响应（无 Range 处理——nginx 应该已经处理）
# ============================================================
def _stream_public_object(object_key: str, default_media: str = "application/octet-stream",
                          cache_max_age: int = 86400):
    """从公开桶流式返回对象。

    失败统一抛 404，避免泄漏后端细节。
    """
    if not gateway.available:
        raise HTTPException(503, "对象存储不可用")
    client = gateway.client

    try:
        response = client.get_object(BUCKET_PUBLIC, object_key)
    except Exception as e:
        logger.warning("public proxy miss: bucket=%s key=%s err=%s", BUCKET_PUBLIC, object_key, e)
        raise HTTPException(404, "Not Found")

    media_type = mimetypes.guess_type(object_key)[0] or default_media

    def _iter():
        try:
            for chunk in response.stream(32 * 1024):
                yield chunk
        finally:
            try:
                response.close()
                response.release_conn()
            except Exception:
                pass

    return StreamingResponse(
        _iter(),
        media_type=media_type,
        headers={"Cache-Control": f"public, max-age={cache_max_age}"},
    )


# ============================================================
# 头像代理（私有桶 headphoto/<type>/<sfzh>.jpg）
# ============================================================
@router.get("/photo/get_headphoto/{sfzh}")
async def get_headphoto(
    sfzh: str,
    request: Request,
    t: int = Query(0),
    s: str = Query(""),
    type: str = Query("open", description="用户类型：open-开放大学 vocational-中职 teacher-教师"),
    admin: Optional[dict] = Depends(_try_admin),
):
    """读取学生头像（私有桶，key = headphoto/<type>/<sfzh>.jpg）。

    鉴权：HMAC 签名（t + s） 或 管理员 Token

    说明：``type`` 控制头像在 MinIO 上的子目录（默认 ``open``，与历史兼容路径
    ``<sfzh>.jpg`` 不一致——前端需要按 ``user_type`` 显式传 ``type`` 才会命中
    新子目录；缺省值保持 ``open`` 是为兼容未传参的老请求，会 fallback 到
    ``headphoto/open/<sfzh>.jpg`` 或历史桶根 ``<sfzh>.jpg``。
    """
    from services.minio_service import _headphoto_key, HEADPHOTO_DIR_OPEN

    subdir = user_type_to_headphoto_subdir(type)
    primary_key = _headphoto_key(sfzh, subdir)
    legacy_key = _headphoto_key(sfzh, "")

    if t and s and verify_photo_sign(sfzh, t, s):
        pass
    elif admin is not None:
        pass
    else:
        raise HTTPException(403, "签名无效或已过期")

    # 先尝试新子目录，找不到时按 history fallback 到桶根 <sfzh>.jpg
    try:
        client = _open_minio()
        loop = asyncio.get_running_loop()
        await asyncio.wait_for(
            loop.run_in_executor(_PROXY_THREAD_POOL, client.stat_object, BUCKET_PRIVATE, primary_key),
            timeout=_MINIO_OP_TIMEOUT_S,
        )
        object_key = primary_key
    except Exception:
        try:
            await asyncio.wait_for(
                loop.run_in_executor(_PROXY_THREAD_POOL, client.stat_object, BUCKET_PRIVATE, legacy_key),
                timeout=_MINIO_OP_TIMEOUT_S,
            )
            object_key = legacy_key
        except Exception:
            raise HTTPException(404, f"Not Found: {primary_key}")

    return await _stream_private_object(object_key, default_media="image/jpeg", request=request)


# ============================================================
# 通用私有桶代理
# ============================================================
@router.get("/object/{path:path}")
async def get_private_object(
    path: str,
    request: Request,
    t: int = Query(0),
    s: str = Query(""),
    admin: Optional[dict] = Depends(_try_admin),
):
    """读取私有桶任意对象（HMAC 签名 或 管理员 Token）。

    仅允许已知受管路径前缀（由 services.minio_service.is_known_object_path 派生）。
    """
    object_key = path.lstrip("/")
    if not object_key:
        raise HTTPException(400, "Invalid object path")
    from services.minio_service import is_known_object_path
    if not is_known_object_path(object_key):
        raise HTTPException(403, "未知路径前缀，禁止访问")

    if t and s and verify_object_sign(object_key, t, s):
        pass
    elif admin is not None:
        pass
    else:
        raise HTTPException(403, "签名无效或已过期")
    return await _stream_private_object(object_key, request=request)


# ============================================================
# 反馈工单图片代理（与小程序签名一致：md5 前 8 位）
# ============================================================
@router.get("/feedback/image/{object_key:path}")
async def get_feedback_image(
    object_key: str,
    request: Request,
    t: int = Query(0),
    s: str = Query(""),
    token: str = Query("", alias="token"),
    admin: Optional[dict] = Depends(_try_admin),
):
    """读取工单图片（私有桶，路径前缀 private/hq/feedback/ 或 feedback/）。

    鉴权优先级：
    1. 管理员 Authorization Header Token
    2. URL 中的 token 参数（el-image src 直接加载时使用）
    3. HMAC 签名（t + s 参数，与小程序一致，md5 前 8 位）
    """
    object_key = object_key.lstrip("/")
    if not object_key:
        raise HTTPException(400, "Invalid object key")
    # 允许的私有桶 key 前缀：
    # - private/hq/feedback/ : 当前规范路径（新工单，与 minio_service._ROUTES 对齐）
    # - feedback/            : 旧路径（清库前的历史数据，兜底）
    if not (
        object_key.startswith("private/hq/feedback/")
        or object_key.startswith("feedback/")
    ):
        raise HTTPException(403, "路径不合法")

    if admin is not None:
        pass
    elif token:
        try:
            from common.auth import verify_token_for_dependencies
            payload = verify_token_for_dependencies(token)
            if not (payload.get("user_id") or payload.get("admin_id") or payload.get("staff_id")
                    or payload.get("t_id") or payload.get("xs_id") or payload.get("xs_xh")):
                raise HTTPException(403, "Token 无效")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(403, "Token 无效或已过期")
    elif t and s and verify_feedback_sign(object_key, t, s):
        pass
    else:
        raise HTTPException(403, "签名无效或已过期，请重新打开页面")
    return await _stream_private_object(object_key, request=request)


# ============================================================
# 招生简章图片代理（公开桶 public/zs/brochure/<school_type>/<n>.<ext>）
# ============================================================
@router.get("/brochure/image/{path:path}")
async def get_brochure_image(
    path: str,
    request: Request,
):
    """读取招生简章图片（公开桶，nginx 接管；这里仅兜底 nginx 故障）。

    公开桶对象没有签名校验；如需防盗链，由 nginx secure_link 完成。
    """
    object_key = path.lstrip("/")
    if not object_key:
        raise HTTPException(400, "Invalid path")
    if not object_key.startswith("public/zs/brochure/"):
        raise HTTPException(403, "路径不合法")
    return _stream_public_object(object_key, default_media="image/jpeg", cache_max_age=3600)


# ============================================================
# 就业推荐配图代理（私有桶 private/jytj/...）
# ============================================================
@router.get("/job/image/{filename:path}")
async def get_job_image(
    filename: str,
    request: Request,
    t: int = Query(0),
    s: str = Query(""),
    admin: Optional[dict] = Depends(_try_admin),
):
    """读取就业推荐文章配图（私有桶，路径前缀 private/jytj/）。

    鉴权：HMAC 签名（t + s） 或 管理员 Token
    """
    object_key = filename.lstrip("/")
    if not object_key:
        raise HTTPException(400, "Invalid filename")
    if not object_key.startswith("private/jytj/"):
        raise HTTPException(403, "路径不合法")

    if t and s and verify_object_sign(object_key, t, s):
        pass
    elif admin is not None:
        pass
    else:
        raise HTTPException(403, "签名无效或已过期")
    return await _stream_private_object(object_key, request=request)


# ============================================================
# 3+4 报名图片代理（私有桶 private/zs/...）
# ============================================================
@router.get("/photo/zs_image/{filename:path}")
async def get_zs_image(
    filename: str,
    request: Request,
    t: int = Query(0),
    s: str = Query(""),
    admin: Optional[dict] = Depends(_try_admin),
):
    """读取 3+4 报名图片（私有桶，路径前缀 private/zs/）。

    鉴权：HMAC 签名（t + s） 或 管理员 Token
    """
    object_key = filename.lstrip("/")
    if not object_key:
        raise HTTPException(400, "Invalid filename")
    if not object_key.startswith("private/zs/"):
        raise HTTPException(403, "路径不合法")

    if t and s and verify_object_sign(object_key, t, s):
        pass
    elif admin is not None:
        pass
    else:
        raise HTTPException(403, "签名无效或已过期")
    return await _stream_private_object(object_key, request=request)


# ============================================================
# 公共桶静态资源兜底代理（开发/测试用；生产由 nginx 接管）
# ============================================================
@router.get("/static/{path:path}")
async def static_proxy(path: str):
    """GET /static/<path> → 公开桶 static/<path>

    生产环境此路由应由 nginx 直接代理到 MinIO 并加 secure_link 防盗链；
    仅当 nginx 命中 404/403 时回落到本路由。
    """
    if ".." in path:
        raise HTTPException(404, "Not Found")
    object_key = f"static/{path.lstrip('/')}"
    return _stream_public_object(object_key, cache_max_age=86400)


@router.get("/public/{path:path}")
async def public_proxy(path: str):
    """GET /public/<path> → 公开桶 public/<path>"""
    if ".." in path:
        raise HTTPException(404, "Not Found")
    object_key = f"public/{path.lstrip('/')}"
    return _stream_public_object(object_key, cache_max_age=86400)


# ============================================================
# 反馈工单附件上传（小程序 / 后台均可复用）
# ============================================================

_FB_IMG_EXTS = {"jpg", "jpeg", "png", "webp"}
_FB_VIDEO_EXTS = {"mp4", "mov"}
_FB_IMG_MAX = 8 * 1024 * 1024     # 8MB
_FB_VIDEO_MAX = 30 * 1024 * 1024  # 30MB
_FB_POSTER_MAX = 2 * 1024 * 1024  # 2MB
_FB_CT = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "png": "image/png", "webp": "image/webp",
    "mp4": "video/mp4", "mov": "video/quicktime",
}


def _ext_of_name(name: str) -> str:
    if not name or "." not in name:
        return ""
    return name.rsplit(".", 1)[-1].lower()


def _require_authed(authorization: Optional[str] = Header(None)) -> dict:
    """上传接口统一鉴权：需要有效 JWT（小程序 user_id 或后台 admin_id 等）。"""
    if not authorization:
        raise HTTPException(401, "未登录")
    try:
        from common.auth import verify_token_for_dependencies
        payload = verify_token_for_dependencies(authorization.replace("Bearer ", "", 1))
    except Exception:
        raise HTTPException(401, "Token 无效或已过期")
    if not (payload.get("user_id") or payload.get("admin_id") or payload.get("staff_id")
            or payload.get("t_id") or payload.get("xs_id") or payload.get("xs_xh")):
        raise HTTPException(401, "Token 无效")
    return payload


@router.post("/feedback/upload")
async def feedback_upload(
    file: UploadFile = File(...),
    _user: dict = Depends(_require_authed),
):
    """通用图片/视频上传。返回 {key, url, type}。"""
    from services.minio_service import put_feedback_image, get_feedback_image_url
    ext = _ext_of_name(file.filename or "")
    if ext in _FB_IMG_EXTS:
        media_type = "image"
        size_limit = _FB_IMG_MAX
    elif ext in _FB_VIDEO_EXTS:
        media_type = "video"
        size_limit = _FB_VIDEO_MAX
    else:
        raise HTTPException(400, "仅支持 jpg/jpeg/png/webp/mp4/mov")

    raw = await file.read()
    size = len(raw)
    if size <= 0:
        raise HTTPException(400, "空文件")
    if size > size_limit:
        mb = size_limit // (1024 * 1024)
        raise HTTPException(400, f"{'图片' if media_type == 'image' else '视频'}不能超过 {mb}MB")

    try:
        key = put_feedback_image(raw, file.filename or f"x.{ext}", _FB_CT.get(ext, "application/octet-stream"))
    except Exception as e:
        logger.exception("feedback upload failed")
        raise HTTPException(500, f"上传失败: {e}")

    return {
        "success": True,
        "data": {"key": key, "url": get_feedback_image_url(key.lstrip("/")), "type": media_type},
    }


@router.post("/feedback/upload_poster")
async def feedback_upload_poster(
    file: UploadFile = File(...),
    video_key: str = Form(...),
    _user: dict = Depends(_require_authed),
):
    """上传视频封面（sidecar）。存储路径 = video_key + ".jpg"。

    允许的 video_key 前缀：
    - private/hq/feedback/  : 当前规范路径（新工单）
    - feedback/             : 旧路径（清库前的历史数据，前端兜底用）
    """
    from services.minio_service import put_feedback_poster, get_feedback_image_url
    if not video_key or not (
        video_key.startswith("private/hq/feedback/")
        or video_key.startswith("feedback/")
    ):
        raise HTTPException(400, "video_key 不合法")
    if _ext_of_name(video_key) not in _FB_VIDEO_EXTS:
        raise HTTPException(400, "video_key 不是视频")

    raw = await file.read()
    size = len(raw)
    if size <= 0:
        raise HTTPException(400, "空文件")
    if size > _FB_POSTER_MAX:
        raise HTTPException(400, "封面不能超过 2MB")

    poster_key = put_feedback_poster(video_key, raw, content_type="image/jpeg")
    if not poster_key:
        raise HTTPException(400, "封面上传失败")

    return {
        "success": True,
        "data": {"key": poster_key, "url": get_feedback_image_url(poster_key)},
    }


__all__ = ["router"]