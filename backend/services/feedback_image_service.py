"""反馈媒体(图片/视频)存储服务(MinIO) —— zhpt-new 重构版

设计原则（参考 headphoto/backend/app/services/feedback_image_service.py 的反馈子模块 + 本项目 services/minio_service.py）：
1. 不再自己持有 MinIO 客户端；通过 utils/minio_client.gateway 拿单例
2. 不再 make_bucket；桶由运维预建
3. 不在 controller 内直接调 SDK；业务语义统一在 services/minio_service.py
4. 对象路径约定：
   - 新工单：private/hq/feedback/<uuid>.<ext>     (与 minio_service._ROUTES 对齐)
   - 历史数据：feedback/<yyyymm>/<name>.<ext>      (清库前数据，路由兜底)
5. 访问方式：/feedback/image/<key>?t=&s= → photo_proxy 走 HMAC md5[:8] 签名
6. 支持扩展名：图片 jpg/jpeg/png/webp；视频 mp4/mov
"""
import logging
from datetime import datetime
from typing import Tuple

from minio.error import S3Error

from services.minio_service import (
    BUCKET_PRIVATE,
    BUCKET_PUBLIC,
    delete_by_path as _delete_by_path,
    put_feedback_image as _put_feedback_image,
    put_feedback_poster as _put_feedback_poster,
    get_feedback_image_url as _get_signed_url,
    verify_feedback_sign as _verify_sign,
    is_private_path,
    infer_bucket_by_path,
)
from utils.minio_client import gateway

logger = logging.getLogger(__name__)


# 支持的媒体扩展名
IMAGE_EXTS = ("jpg", "jpeg", "png", "webp")
VIDEO_EXTS = ("mp4", "mov")
ALL_EXTS = IMAGE_EXTS + VIDEO_EXTS

# content-type 映射
CONTENT_TYPE_MAP = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "png": "image/png", "webp": "image/webp",
    "mp4": "video/mp4", "mov": "video/quicktime",
}


def ext_of(object_key: str) -> str:
    if not object_key or "." not in object_key:
        return ""
    return object_key.rsplit(".", 1)[-1].lower()


def media_type_of(object_key: str) -> str:
    """根据 object_key 扩展名判断 image / video"""
    e = ext_of(object_key)
    if e in VIDEO_EXTS:
        return "video"
    return "image"


# 兼容老接口：保留函数名
get_signed_url = _get_signed_url
verify_sign = _verify_sign


def upload_image(file_content: bytes, ext: str = "jpg", content_type: str = "image/jpeg") -> str:
    """上传反馈媒体(图片/视频)到 MinIO，返回 object_key。

    新工单路径：private/hq/feedback/<uuid>.<ext>（与 minio_service._ROUTES 对齐）

    注意：历史路径 feedback/<yyyymm>/<name>.<ext> 仍然作为兜底（详见 _ROUTES）。
    """
    ext = (ext or "jpg").lower().lstrip(".")
    if ext not in ALL_EXTS:
        raise ValueError("不支持的媒体格式")
    if not content_type:
        content_type = CONTENT_TYPE_MAP.get(ext, "application/octet-stream")
    # 委托给统一的 put_feedback_image
    return _put_feedback_image(file_content, f"x.{ext}", content_type)


def delete_image(object_key: str) -> bool:
    """按 key 删除反馈媒体（自动选桶）。"""
    if not object_key:
        return False
    return _delete_by_path(object_key)


def stream_image(object_key: str) -> Tuple[bytes, str]:
    """从 MinIO 取文件字节 + content-type。

    新代码建议直接走 /feedback/image/<key>?t=&s= 签名代理，
    本函数仅供老接口调用。
    """
    bucket = infer_bucket_by_path(object_key)
    client = gateway.client
    resp = client.get_object(bucket, object_key.lstrip("/"))
    try:
        data = resp.read()
    finally:
        resp.close()
        resp.release_conn()
    ext = ext_of(object_key) or "jpg"
    return data, CONTENT_TYPE_MAP.get(ext, "application/octet-stream")


def stat_object_size(object_key: str) -> int:
    """获取对象总字节数,用于 Range/Content-Length 头"""
    bucket = infer_bucket_by_path(object_key)
    return gateway.client.stat_object(bucket, object_key.lstrip("/")).size


def stream_range(object_key: str, offset: int, length: int) -> bytes:
    """读取对象指定字节范围(供 HTTP Range 边下边播使用)"""
    bucket = infer_bucket_by_path(object_key)
    resp = gateway.client.get_object(bucket, object_key.lstrip("/"), offset=offset, length=length)
    try:
        return resp.read()
    finally:
        resp.close()
        resp.release_conn()


def put_object_raw(object_key: str, content: bytes, content_type: str) -> None:
    """直接以指定 object_key 写入(供封面 sidecar 等已规划路径的场景使用)。

    视频封面的标准路径 = video_key + ".jpg"，由 put_feedback_poster 负责；
    这里保留 raw 入口用于特殊场景（不在 _FEEDBACK_DIR 下的写入）。
    """
    if is_private_path(object_key):
        gateway.upload_private(object_key.lstrip("/"), content, content_type)
    else:
        gateway.upload_public(object_key.lstrip("/"), content, content_type)
    logger.info(f"反馈 raw 上传: {object_key} ({content_type}, {len(content)}B)")


__all__ = [
    "IMAGE_EXTS",
    "VIDEO_EXTS",
    "ALL_EXTS",
    "CONTENT_TYPE_MAP",
    "ext_of",
    "media_type_of",
    "upload_image",
    "delete_image",
    "stream_image",
    "stat_object_size",
    "stream_range",
    "put_object_raw",
    "get_signed_url",
    "verify_sign",
]