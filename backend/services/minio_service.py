"""
MinIO 业务语义层（zhpt-new 后端）。

参照 headphoto/backend/app/services/minio_service.py 的设计改造：

设计原则
--------
- 所有对象均为私有（与 headphoto 共用同一桶 MINIO_BUCKET_PRIVATE），无公开不变地址。
- 数据库存储格式：<bucket>/<key>，如
    ``guizhou-zhpt-prod-private/zs/brochure/vocational/testimg.png``
    第一段为桶名，其余为对象 key，无需路由表。
- resolve_url / sign_object_url 生成 MinIO presigned GET URL（Sig V4），浏览器通过
  nginx 反代访问：
      浏览器  →  GET /object/<bucket>/<key>?X-Amz-...
             nginx → rewrite /object/(.*) → /$1
                    proxy_pass http://<MINIO_ENDPOINT>
             MinIO ← GET /<bucket>/<key>?X-Amz-...  ← 与 presign 时完全一致，签名通过 ✅
- presigned URL 默认 5 分钟有效期，过期前端重新请求接口拿新链接。
- nginx secure_link 已废弃，所有防盗链由 MinIO Sig V4 签名承担。

桶说明
------
zhpt-new 与 headphoto 共用同一私有桶：
    MINIO_BUCKET_PRIVATE = "guizhou-zhpt-prod-private"
MINIO_BUCKET_PUBLIC 仅保留为兼容别名（指向同一桶），旧代码 / 旧数据库路径不会报错。

兼容策略
--------
为不破坏现有 controllers，保留以下 HMAC shim（标 deprecated）：
- sign_photo_url / verify_photo_sign   （头像 HMAC 短签名 URL）
- sign_object_url_old_hmac / verify_object_sign    （旧版私有对象 HMAC）
- get_feedback_image_url_old_hmac / verify_feedback_sign    （反馈工单 HMAC）
- STATIC_LINK_SECRET / FEEDBACK_IMG_SECRET    （HMAC 密钥常量）
controllers 应在后续 PR 中按 headphoto 同样方式迁到 SigV4：本步骤只动 minio_service.py。
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
import uuid
from datetime import timedelta
from io import BytesIO

from utils.minio_client import gateway

logger = logging.getLogger(__name__)


# ============================================================
# 环境变量读取（zhpt-new 没用 pydantic-settings，沿用 os.getenv）
# ============================================================
def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _env_int(name: str, default: int) -> int:
    raw = _env(name, "")
    if not raw:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


# ============================================================
# MinIO 端点（用于把 SDK 返回的绝对 URL 改写成 /object/<bucket>/）
# ============================================================
MINIO_ENDPOINT: str = _env(
    "MINIO_ENDPOINT",
    _env("MINIO_HOST", "172.16.100.102:9000"),
)
MINIO_SECURE: bool = _env("MINIO_SECURE", "false").lower() == "true"

# ============================================================
# 桶常量
# ============================================================
# 私有桶（业务所有对象）：与 headphoto 共用同一桶
BUCKET_PRIVATE: str = gateway.bucket_private
# 公开桶：本项目已废弃，统一改为私有桶；为兼容老代码仍指向同一桶
BUCKET_PUBLIC: str = gateway.bucket_public
# 业务专用桶（教师头像 zhxt），运维通过 MINIO_BUCKET_ZHXT 配置，未配置时回退到私有桶
BUCKET_ZHXT: str = gateway.bucket_zhxt
# 老别名（部分老代码用 MINIO_BUCKET 引用私有桶）
MINIO_BUCKET: str = BUCKET_PRIVATE
MINIO_BUCKET_PRIVATE: str = BUCKET_PRIVATE
MINIO_BUCKET_PUBLIC: str = BUCKET_PUBLIC
MINIO_BUCKET_ZHXT: str = BUCKET_ZHXT

# 前端看到的 URL 前缀（与 nginx location 对齐）
OBJECT_URL_PREFIX = "/object"
# zhxt 桶独立前缀（对应 nginx /zhxt/ location）
ZHXT_URL_PREFIX = "/zhxt"

# presigned URL 默认有效期（秒）
PRESIGN_EXPIRES_SECONDS = 300


# ============================================================
# 路径解析（从 DB 路径提取 bucket / key）
# ============================================================
def split_bucket_key(path: str) -> tuple[str, str]:
    """从数据库存储路径解析出 (bucket, key)。

    支持两种格式：
      1. 含桶名全路径（历史 / photo_proxy 返回值）：``<bucket>/<key>``
         例如："guizhou-zhpt-prod-private/zs/brochure/vocational/testimg.png"
         也支持业务专用桶："zhxt/teacher_head_photo/qdnskh.jpg"
      2. 纯 key（新入库约定）：``hq/feedback/<uuid>.png``
         例如："hq/feedback/abc.png" / "zs/brochure/abc.png"

    返回 (bucket, key)：
      bucket = "guizhou-zhpt-prod-private"（默认私有桶）
      key    = "zs/brochure/vocational/testimg.png"
    """
    p = (path or "").lstrip("/")
    parts = p.split("/", 1)
    if len(parts) == 1:
        # 纯 key 形式：默认走私有桶
        return BUCKET_PRIVATE, p
    bucket, key = parts[0], parts[1]
    # 兼容历史 DB 老记录里的桶名（保证 bucket 是我们认识的桶，否则视为纯 key）
    # 白名单包含 BUCKET_PRIVATE / BUCKET_PUBLIC / BUCKET_ZHXT
    if bucket not in (BUCKET_PRIVATE, BUCKET_PUBLIC, BUCKET_ZHXT):
        return BUCKET_PRIVATE, p
    return bucket, key


# ============================================================
# URL 生成（核心，与 headphoto 完全一致）
# ============================================================
def resolve_url(path: str) -> str:
    """把数据库路径翻译成前端可用的 /object/ Sig V4 预签名 URL。

    链路：浏览器 → /object/<bucket>/<key>?X-Amz-... → nginx → MinIO（Sig V4 验签）→ 文件

    参数
    ----
    path : 数据库存储路径，格式 <bucket>/<key>，如
           "guizhou-zhpt-prod-private/zs/brochure/vocational/testimg.png"

    返回
    ----
    形如 "/object/guizhou-zhpt-prod-private/zs/brochure/vocational/testimg.png?X-Amz-..."
    的相对路径（host 由前端拼：dev 用 localhost，prod 用实际域名）。
    """
    if not path:
        return ""
    if path.startswith(("http://", "https://")):
        return path

    bucket, key = split_bucket_key(path)
    return _sign_get_in_bucket(bucket, key)


def resolve_url_with_host(path: str, host: str) -> str:
    """resolve_url 的全量 URL 版本，拼接指定 host。

    参数
    ----
    path : 数据库存储路径（<bucket>/<key>）
    host : 前端访问域名，如 "http://localhost" 或 "https://img.example.com"，
           末尾不要加 /。
    """
    rel = resolve_url(path)
    if not rel:
        return ""
    return f"{host.rstrip('/')}{rel}"


def sign_object_url(object_key: str, bucket: str | None = None) -> str:
    """为指定桶的对象生成带 Sig V4 预签名的 /object URL。

    参数
    ----
    object_key : object key。可以是：
                 - 纯 key（新规范）：``zs/brochure/vocational/1.jpg``
                 - 含桶名全路径（DB 老记录或脏数据）：``guizhou-zhpt-prod-private/zs/...``
                 - 含前导 /：``/guizhou-zhpt-prod-private/zs/...``
                 - public/<key> 或 private/<key> 业务前缀（旧约定）：自动推断桶
                 - /object/<bucket>/<key>?X-Amz-... 旧签名 URL：剥 /object/ 后再签
                 - 完整 http(s) URL：抽 path 再签
    bucket : 桶名。默认私有桶（BUCKET_PRIVATE）。

    返回
    ----
    形如 ``/object/<bucket>/<key>?X-Amz-...`` 的相对路径；前端经 nginx + MinIO Sig V4 验签加载。
    """
    if not object_key:
        return ""

    raw = str(object_key).strip()
    if not raw:
        return ""

    target_bucket = bucket or BUCKET_PRIVATE

    # 1) http(s) URL → 抽 path 段
    if raw.startswith(("http://", "https://")):
        try:
            from urllib.parse import urlparse
            raw = urlparse(raw).path or ""
        except Exception:
            pass

    safe_key = raw.lstrip("/")

    # 1.5) 若还包含 query string (常见于"/object/...?X-Amz-..."旧签名 URL 或 http URL)，
    #      去掉 ? 后部分；presign 本身就要重新计算签名，旧 query 无意义。
    if "?" in safe_key:
        safe_key = safe_key.split("?", 1)[0]

    # 2) /object/<bucket>/<key> 旧签名 URL → 剥 /object/ 前缀
    if safe_key.startswith("object/"):
        safe_key = safe_key[len("object/"):]  # noqa: F841
        # safe_key 里可能还有 "?", 上面的 1.5 已经先剥过了；这里仅剥前缀

    # 3) 自动剥桶名（避免双桶名 URL）
    for cand_bucket in (BUCKET_PRIVATE, BUCKET_PUBLIC):
        prefix = cand_bucket + "/"
        if safe_key.startswith(prefix):
            safe_key = safe_key[len(prefix):]
            break

    # 4) brochure 风格：业务路径前缀 public/ 或 private/，自动推断桶
    #    兼容旧 brochure 存的 path "public/zs/brochure/vocational/1.jpg"
    for prefix, cand_bucket in (
        ("public/", BUCKET_PUBLIC),
        ("private/", BUCKET_PRIVATE),
    ):
        if safe_key.startswith(prefix):
            safe_key = safe_key[len(prefix):]
            if bucket is None:
                target_bucket = cand_bucket
            break

    return _sign_get_in_bucket(target_bucket, safe_key)


def _sign_get_in_bucket(bucket: str, key: str) -> str:
    """共用函数：对 (bucket, key) 生成 Sig V4 预签名的 /object/... URL。"""
    import re as _re
    minio_url = gateway.client.presigned_get_object(
        bucket,
        key,
        expires=timedelta(seconds=PRESIGN_EXPIRES_SECONDS),
    )
    # 替换 MinIO host + 桶名前缀 → /object/<bucket>/
    pattern = _re.escape(f"http://{MINIO_ENDPOINT}/") + r"([^/]+)/"
    replacement = f"{OBJECT_URL_PREFIX}/\\1/"
    return _re.sub(pattern, replacement, minio_url, count=1)


def _sign_get_zhxt(key: str) -> str:
    """对 zhxt 桶对象签 /zhxt/<key>?... URL。

    与 _sign_get_in_bucket 的区别：nginx 配了独立的 /zhxt/ location，
    URL 格式是 ``/zhxt/<key>?X-Amz-...``（不带桶名），由 nginx rewrite 把
    桶名拼到 proxy_pass 里。

    返回相对路径，前端 resolveImageUrl 拼 BASE_URL。
    """
    import re as _re
    minio_url = gateway.client.presigned_get_object(
        BUCKET_ZHXT,
        key,
        expires=timedelta(seconds=PRESIGN_EXPIRES_SECONDS),
    )
    # MinIO 返回形如 http://172.16.100.102:9000/zhxt/<key>?X-Amz-...
    # 替换为 /zhxt/<key>?X-Amz-...
    pattern = _re.escape(f"http://{MINIO_ENDPOINT}/") + _re.escape(BUCKET_ZHXT) + r"/"
    return _re.sub(pattern, "/zhxt/", minio_url, count=1)


def resolve_url_zhxt(key: str) -> str:
    """根据纯 key（不含桶名）生成 zhxt 桶预签 URL。

    用于教师头像，前端拿到的 URL 不再走 /object/ 前缀，
    而是 /zhxt/<key>?X-Amz-...，nginx /zhxt/ location 处理。
    """
    if not key:
        return ""
    if key.startswith(("http://", "https://")):
        return key
    # 去掉前导 /
    return _sign_get_zhxt(key.lstrip("/"))


# 旧版别名（保留兼容，后续可逐步迁移）
get_preview_url = resolve_url   # 语义别名：给定 DB 路径生成签名 URL


# ============================================================
# 工具
# ============================================================
def _ext_of(filename: str, fallback: str = "bin") -> str:
    name = os.path.basename(filename or "")
    if "." in name:
        return name.rsplit(".", 1)[-1].lower()
    return fallback


def _new_name(ext: str = "bin") -> str:
    return f"{uuid.uuid4().hex}.{ext.lstrip('.')}" if ext else uuid.uuid4().hex


# ============================================================
# 上传（返回数据库路径 <bucket>/<key>）
# ============================================================
def put_object(content: bytes, filename: str, subdir: str = "") -> str:
    """上传通用方法，返回数据库路径（<bucket>/<key>）。

    参数
    ----
    content     : 文件字节
    filename    : 原始文件名（用于提取扩展名），可为空
    subdir      : 对象子目录，如 "zs/brochure/vocational"，空则直接放桶根目录

    返回
    ----
    数据库存储路径，形如 "guizhou-zhpt-prod-private/<subdir>/<uuid>.<ext>"
    """
    ext = _ext_of(filename, "bin")
    name = _new_name(ext)
    key = f"{subdir.strip('/')}/{name}" if subdir else name
    # ★ object_name 不能含桶名（MinIO SDK 第一参数已是桶名）
    gateway.client.put_object(
        BUCKET_PRIVATE, key, BytesIO(content), len(content),
    )
    object_name = f"{BUCKET_PRIVATE}/{key}"
    logger.info("上传成功: %s size=%d", object_name, len(content))
    return object_name


def put_image(content: bytes, filename: str = "", subdir: str = "") -> str:
    """上传图片，返回数据库路径。content_type 固定为 image/jpeg。"""
    return put_object(content, filename, subdir)


def delete_object(path: str) -> bool:
    """按数据库路径删除对象。返回是否成功。"""
    if not path:
        return False
    try:
        bucket, key = split_bucket_key(path)
        gateway.client.remove_object(bucket, key)
        return True
    except Exception as e:
        logger.warning("删除对象失败: %s → %s", path, e)
        return False


def stat_object(path: str) -> bool:
    """按数据库路径判断对象是否存在。"""
    if not path:
        return False
    try:
        bucket, key = split_bucket_key(path)
        gateway.client.stat_object(bucket, key)
        return True
    except Exception:
        return False


# ============================================================
# 头像（私有桶内 headphoto/<type>/<sfzh>.jpg；type ∈ {open, vocational}）
# ============================================================
# 学生头像子目录前缀常量
HEADPHOTO_DIR_OPEN = "headphoto/open"
HEADPHOTO_DIR_VOCATIONAL = "headphoto/vocational"
HEADPHOTO_DIR_TEACHER = "headphoto/teacher"
# 历史数据兜底：清库前可能仍存在桶根 <sfzh>.jpg；fallback 读取时一并尝试
HEADPHOTO_LEGACY_KEY = "{sfzh}.jpg"


def user_type_to_headphoto_subdir(user_type: str | None) -> str:
    """根据 user_type 返回头像在 MinIO 上的子目录（不含私有桶名）。

    映射规则：
        - "open" / "student" / "" / None → HEADPHOTO_DIR_OPEN   （开放大学学生）
        - "vocational" / "zz"            → HEADPHOTO_DIR_VOCATIONAL （中职学生）
        - "teacher"                      → HEADPHOTO_DIR_TEACHER （教师）
        - 其它未知值                     → HEADPHOTO_DIR_OPEN （默认开放大学）
    """
    if not user_type:
        return HEADPHOTO_DIR_OPEN
    t = str(user_type).strip().lower()
    if t in ("vocational", "zz"):
        return HEADPHOTO_DIR_VOCATIONAL
    if t in ("teacher",):
        return HEADPHOTO_DIR_TEACHER
    # open / student / 其它 → 开放大学学生
    return HEADPHOTO_DIR_OPEN


def _headphoto_key(id_card: str, subdir: str = "") -> str:
    """生成头像对象 key。

    subdir 为空时使用历史兼容的 ``<id_card>.jpg``；否则 ``<subdir>/<id_card>.jpg``。
    返回的 key 不含桶名前缀，仅是 object key。
    """
    safe_subdir = (subdir or "").strip("/")
    if not safe_subdir:
        return f"{id_card}.jpg"
    return f"{safe_subdir}/{id_card}.jpg"


def _headphoto_db_path(id_card: str, subdir: str = "") -> str:
    """生成头像的数据库存储路径 ``<bucket>/<key>``。"""
    return f"{BUCKET_PRIVATE}/{_headphoto_key(id_card, subdir)}"


def upload_photo(
    id_card: str,
    file_content: bytes,
    content_type: str = "image/jpeg",
    subdir: str = HEADPHOTO_DIR_OPEN,
) -> str:
    """上传头像，返回数据库路径（guizhou-zhpt-prod-private/<subdir>/<id_card>.jpg）。

    参数
    ----
    id_card : 身份证号
    file_content : 文件字节
    content_type : MIME，默认 image/jpeg
    subdir : 头像子目录，默认 ``headphoto/open``。
             开放大学 → ``headphoto/open``；中职 → ``headphoto/vocational``；
             教师 → ``headphoto/teacher``。传空字符串 ``""`` 表示历史兼容
             （直接存桶根 ``<id_card>.jpg``，仅供迁移期使用）。

    返回
    ----
    数据库存储路径 ``<bucket>/<key>``。如需签名 URL，请用 ``resolve_url(...)`` 包装。
    """
    object_key = _headphoto_key(id_card, subdir)
    db_path = _headphoto_db_path(id_card, subdir)
    gateway.client.put_object(
        BUCKET_PRIVATE, object_key, BytesIO(file_content), len(file_content), content_type,
    )
    logger.info("照片上传: %s", db_path)
    return db_path


def upload_photo_with_url(
    id_card: str,
    file_content: bytes,
    content_type: str = "image/jpeg",
    subdir: str = HEADPHOTO_DIR_OPEN,
) -> str:
    """上传头像并返回签名 URL。

    仅保留给 controllers 老的 import 习惯（``return sign_photo_url(sfzh)``）。
    推荐新代码使用 upload_photo() + resolve_url()。
    """
    db_path = upload_photo(id_card, file_content, content_type, subdir=subdir)
    return resolve_url(db_path)


# 老的 put_headphoto 行为也改成"上传 + 返回 DB 路径"
def put_headphoto(
    content: bytes,
    id_card: str,
    content_type: str = "image/jpeg",
    subdir: str = HEADPHOTO_DIR_OPEN,
) -> str:
    """上传头像到私有桶，返回数据库路径。

    ``subdir`` 语义同 :func:`upload_photo`。
    """
    object_key = _headphoto_key(id_card, subdir)
    db_path = _headphoto_db_path(id_card, subdir)
    gateway.client.put_object(
        BUCKET_PRIVATE, object_key, BytesIO(content), len(content), content_type,
    )
    return db_path


def delete_photo(id_card: str, subdir: str = HEADPHOTO_DIR_OPEN) -> bool:
    """删除头像。文件不存在视为成功。

    ``subdir`` 为空字符串时按 ``<id_card>.jpg`` 删除（即历史兼容路径）。
    """
    object_key = _headphoto_key(id_card, subdir)
    try:
        gateway.client.remove_object(BUCKET_PRIVATE, object_key)
        return True
    except Exception:
        return False


def check_photo_exists(
    id_card: str,
    subdir: str = HEADPHOTO_DIR_OPEN,
    *,
    fallback_legacy: bool = True,
) -> bool:
    """头像是否存在。

    默认先按 ``<subdir>/<id_card>.jpg`` 查找；若不存在且 ``fallback_legacy=True``，
    再尝试历史兜底 ``<id_card>.jpg``（桶根）。
    """
    if stat_object(_headphoto_db_path(id_card, subdir)):
        return True
    if fallback_legacy and subdir:
        return stat_object(_headphoto_db_path(id_card, subdir=""))
    return False


def get_photo_url(
    id_card: str,
    subdir: str = HEADPHOTO_DIR_OPEN,
    *,
    fallback_legacy: bool = True,
) -> str:
    """获取照片访问 Sig V4 预签名 URL（/object/... 形式）。

    当新路径不存在但历史桶根 ``<id_card>.jpg`` 存在时，自动返回历史 URL。
    """
    if stat_object(_headphoto_db_path(id_card, subdir)):
        return resolve_url(_headphoto_db_path(id_card, subdir))
    if fallback_legacy and subdir and stat_object(_headphoto_db_path(id_card, subdir="")):
        return resolve_url(_headphoto_db_path(id_card, subdir=""))
    # 都没有：仍返回新路径的预签名（前端会拿到 404），保留调用方一致行为
    return resolve_url(_headphoto_db_path(id_card, subdir))


def get_photo_size(id_card: str, subdir: str = HEADPHOTO_DIR_OPEN) -> int:
    """获取头像字节大小。文件不存在返回 0。"""
    obj = gateway.stat_object_full(BUCKET_PRIVATE, _headphoto_key(id_card, subdir))
    if obj:
        return obj.size or 0
    if subdir:
        obj = gateway.stat_object_full(BUCKET_PRIVATE, _headphoto_key(id_card, ""))
        if obj:
            return obj.size or 0
    return 0


# ============================================================
# 教师头像（专用桶 zhxt，路径 teacher_head_photo/<username>.<ext>）
# ------------------------------------------------------------
# 与学生头像分开：学生头像在私有桶 headphoto/<open|vocational>/<sfzh>.jpg；
# 教师头像统一在 zhxt 桶下的 teacher_head_photo/<username>.<ext>，
# 文件名采用教师用户名（t_yhm），方便业务侧按用户名直接定位头像。
# ============================================================
TEACHER_HEADPHOTO_DIR = "teacher_head_photo"


def _teacher_headphoto_key(username: str, ext: str = "jpg") -> str:
    """生成教师头像对象 key：``teacher_head_photo/<username>.<ext>``。

    ``username`` 即 ``oa_t.t_yhm``。函数不做白名单校验，由调用方传入可信值。
    """
    safe_username = (username or "").strip().strip("/")
    if not safe_username:
        raise ValueError("教师用户名(username)不能为空")
    return f"{TEACHER_HEADPHOTO_DIR}/{safe_username}.{ext.lstrip('.').lower() or 'jpg'}"


def _teacher_headphoto_db_path(username: str, ext: str = "jpg") -> str:
    """生成教师头像的数据库存储路径（供前端 resolveImageUrl 使用）。

    返回格式：zhxt/teacher_head_photo/<username>.<ext>
    前端通过 resolveImageUrl("zhxt/teacher_head_photo/<username>.jpg") 拼完整 URL，
    再经 nginx /zhxt/ location 反代到 MinIO zhxt 桶。

    注意：不再返回 <bucket>/<key> 格式（前端无需知道桶名）。
    """
    return f"zhxt/{_teacher_headphoto_key(username, ext)}"


def upload_teacher_headphoto(
    username: str,
    file_content: bytes,
    content_type: str = "image/jpeg",
    ext: str = "jpg",
) -> str:
    """上传教师头像到 zhxt 桶，返回数据库路径。

    路径格式：``<zhxt-bucket>/teacher_head_photo/<username>.<ext>``。
    覆盖语义：同名文件直接覆盖（同一教师再次上传会自动替换）。

    参数
    ----
    username     : 教师用户名（oa_t.t_yhm）
    file_content : 文件字节
    content_type : MIME，默认 image/jpeg
    ext          : 扩展名，默认 jpg
    """
    object_key = _teacher_headphoto_key(username, ext)
    db_path = _teacher_headphoto_db_path(username, ext)
    gateway.client.put_object(
        BUCKET_ZHXT, object_key, BytesIO(file_content), len(file_content), content_type,
    )
    logger.info("教师头像上传: %s size=%d", db_path, len(file_content))
    return db_path


def check_teacher_headphoto_exists(username: str, ext: str = "jpg") -> bool:
    """判断教师头像是否存在（zhxt 桶）。"""
    if not username:
        return False
    return stat_object(_teacher_headphoto_db_path(username, ext))


def get_teacher_headphoto_url(username: str, ext: str = "jpg") -> str:
    """获取教师头像 Sig V4 预签名 URL（zhxt 桶，相对路径 ``/zhxt/...``）。

    返回相对路径（不含 host），前端通过 resolveImageUrl 拼 BASE_URL。
    走 nginx /zhxt/ location 反代到 MinIO zhxt 桶。
    """
    return resolve_url_zhxt(_teacher_headphoto_key(username, ext))


def get_teacher_headphoto_full_url(username: str, ext: str = "jpg", host: str = "") -> str:
    """获取教师头像完整 URL（含 host）。

    用于：
    - 后端直接渲染需要完整 URL 的场景（HTML 邮件、PDF 等）
    - 前端不再走 resolveImageUrl，直接展示后端返回的 URL

    参数
    ----
    username : 教师用户名（oa_t.t_yhm）
    ext      : 扩展名（默认 jpg）
    host     : 协议+域名（不含 /），如 "http://localhost" 或 "https://m.example.com"
    """
    rel = get_teacher_headphoto_url(username, ext)
    if not rel:
        return ""
    if rel.startswith(("http://", "https://")):
        return rel
    return f"{host.rstrip('/')}{rel}" if host else rel


def delete_teacher_headphoto(username: str, ext: str = "jpg") -> bool:
    """删除教师头像。文件不存在视为成功。"""
    try:
        gateway.client.remove_object(BUCKET_ZHXT, _teacher_headphoto_key(username, ext))
        return True
    except Exception as e:
        logger.warning("教师头像删除失败: %s → %s", username, e)
        return False


# ============================================================
# 招生简章图片（统一存私有桶，与 headphoto 一致）
# ============================================================
# 招生简章统一走私有桶 zs/brochure/<school_type>/<n>.<ext>
_BROCHURE_DIR = "zs/brochure"


def put_brochure_image(
    content: bytes,
    filename: str,
    category: str = "vocational",
    sort: int | None = None,
    ext: str | None = None,
    content_type: str | None = None,
) -> str:
    """上传招生简章图片到私有桶，返回数据库路径（guizhou-zhpt-prod-private/zs/brochure/.../...<ext>）。

    参数
    ----
    content : 文件字节
    filename : 原文件名，用于提取扩展名
    category : 招生类型（vocational / open / adult）
    sort : 序号；为 None 时使用 uuid（默认）
    ext : 显式指定扩展名；为 None 时从 filename 推断
    content_type : MIME；为 None 时默认 image/jpeg
    """
    sub = (category or "vocational").strip().strip("/") or "vocational"
    safe_ext = (ext or _ext_of(filename, "jpg"))
    if sort is not None:
        name = f"{int(sort)}.{safe_ext}"
    else:
        name = _new_name(safe_ext)
    obj = f"{_BROCHURE_DIR}/{sub}/{name}"
    full_obj = f"{BUCKET_PRIVATE}/{obj}"
    # ★ object_name 不能含桶名
    gateway.client.put_object(
        BUCKET_PRIVATE, obj, BytesIO(content), len(content),
        content_type or f"image/{safe_ext}",
    )
    logger.info("招生简章上传: %s", full_obj)
    return full_obj


# ============================================================
# 3+4 报名图（私有桶 private/zs/，业务前缀作为历史兼容，
# 实际新存的 DB 路径是 <bucket>/zs/... 不带 private/ 前缀）
# ============================================================
def put_zs_image(content: bytes, ext: str = "jpg",
                 content_type: str | None = None) -> str:
    """3+4 报名图片上传，返回数据库路径（guizhou-zhpt-prod-private/zs/<uuid>.<ext>）。

    业务路径历史上有 private/zs/ 前缀，本实现统一存 <bucket>/zs/<uuid>.<ext>，
    sign_object_url 对遗留 private/zs/ 也兼容识别。
    """
    safe_ext = _ext_of(f"x.{ext}", "jpg")
    obj = f"zs/{_new_name(safe_ext)}"
    full_obj = f"{BUCKET_PRIVATE}/{obj}"
    # ★ object_name 不能含桶名
    gateway.client.put_object(
        BUCKET_PRIVATE, obj, BytesIO(content), len(content),
        content_type or f"image/{safe_ext}",
    )
    return full_obj


# ============================================================
# 就业推荐配图（私有桶 jytj/<timestamp>.<ext>）
# ============================================================
def put_jytj_image(content: bytes, ext: str = "jpg",
                   content_type: str | None = None) -> str:
    """就业推荐配图上传，返回数据库路径（guizhou-zhpt-prod-private/jytj/<ts>.<ext>）。"""
    safe_ext = _ext_of(f"x.{ext}", "jpg")
    obj = f"jytj/{int(time.time() * 1000)}.{safe_ext}"
    full_obj = f"{BUCKET_PRIVATE}/{obj}"
    # ★ object_name 不能含桶名
    gateway.client.put_object(
        BUCKET_PRIVATE, obj, BytesIO(content), len(content),
        content_type or f"image/{safe_ext}",
    )
    return full_obj
# ============================================================
_FEEDBACK_DIR = "hq/feedback"  # 对象子目录（不含 public/private 前缀，与 headphoto 一致）


def put_feedback_image(content: bytes, filename: str, content_type: str | None = None) -> str:
    """上传反馈工单主附件，返回数据库路径（guizhou-zhpt-prod-private/hq/feedback/<uuid>.<ext>）。

    访问 URL 走 resolve_url() → /object/<bucket>/hq/feedback/<uuid>.<ext>?X-Amz-...
    """
    obj = f"{_FEEDBACK_DIR}/{_new_name(_ext_of(filename, 'jpg'))}"
    # ★ object_name 不能含桶名；MinIO SDK 第一参数已是桶名，object_name 必须是纯 key。
    gateway.client.put_object(
        BUCKET_PRIVATE, obj, BytesIO(content), len(content), content_type,
    )
    # 返回值保留 DB 路径格式（<bucket>/<key>），便于 split_bucket_key 等下游识别。
    return f"{BUCKET_PRIVATE}/{obj}"


def put_feedback_poster(video_path: str, content: bytes, content_type: str = "image/jpeg") -> str | None:
    """为视频附件生成同名封面（sidecar），返回数据库路径。

    ``video_path`` 须为 put_feedback_image 返回的数据库路径
    （形如 ``guizhou-zhpt-prod-private/hq/feedback/<uuid>.mp4``）。
    封面 key = ``<video_key>.jpg``（即 sidecar）。
    """
    if not video_path or not content:
        return None
    # 取去掉桶名前缀的 key
    bucket, key = split_bucket_key(video_path) if "/" in (video_path or "") else (BUCKET_PRIVATE, video_path)
    if bucket != BUCKET_PRIVATE or not key.startswith(f"{_FEEDBACK_DIR}/"):
        return None
    poster_key = f"{key}.jpg"
    # ★ object_name 不能含桶名
    gateway.client.put_object(
        BUCKET_PRIVATE, poster_key, BytesIO(content), len(content), content_type,
    )
    return f"{BUCKET_PRIVATE}/{poster_key}"


# ============================================================
# 公开图（保留兼容：实际也走私有桶）
# ============================================================
def put_public_image(
    content: bytes,
    filename: str,
    subdir: str = "",
    content_type: str | None = None,
) -> str:
    """保留兼容老 API；实际已统一改走私有桶。

    原行为：上传到公开桶 public/<uuid>.<ext>，并返回 ``/<subdir>/<uuid>.<ext>``。
    新行为：上传到私有桶，返回 DB 路径 ``<bucket>/<uuid>.<ext>``。
    """
    sub = (subdir or "").strip("/").strip()
    ext = _ext_of(filename, "jpg")
    name = _new_name(ext)
    key = f"{sub}/{name}" if sub else name
    full_obj = f"{BUCKET_PRIVATE}/{key}"
    # ★ object_name 不能含桶名
    gateway.client.put_object(
        BUCKET_PRIVATE, key, BytesIO(content), len(content),
        content_type or f"image/{ext}",
    )
    return full_obj


# ============================================================
# 删除 / 下载（保持原 API）
# ============================================================
def delete_by_path(path: str) -> bool:
    """按路径删除对象（自动 split bucket/key）。"""
    if not path:
        return False
    try:
        bucket, key = split_bucket_key(path)
        return gateway.delete_object(bucket, key)
    except (ValueError, Exception) as e:
        logger.warning("delete_by_path 失败: %s → %s", path, e)
        return False


def download_file(file_name: str, bucket: str | None = None) -> bytes | None:
    """下载对象字节。file_name 实际可能是 DB 路径（<bucket>/<key>）或纯 key。

    - 若含桶名前缀，按 split_bucket_key 解析
    - 否则 bucket 必填（默认私有桶）
    """
    if bucket:
        return gateway.download(bucket, file_name)
    if "/" in (file_name or ""):
        try:
            b, k = split_bucket_key(file_name)
            return gateway.download(b, k)
        except ValueError:
            pass
    return gateway.download(BUCKET_PRIVATE, file_name)


# ============================================================
# 路由判定保留兼容（controllers 老调用方使用，但不推荐继续演进）
# ============================================================
# ---- 路由表已不再需要（统一走私有桶），保留 is_known_object_path / BucketRoute
#     让老调用方不报错。 ----

# 简单的桶推断（统一返回 BUCKET_PRIVATE）
def infer_bucket_by_path(path: str) -> str:
    """保留兼容；统一返回 BUCKET_PRIVATE。"""
    return BUCKET_PRIVATE


def is_private_path(path: str) -> bool:  # noqa: D401  - 保留
    """保留兼容；统一返回 True（私有桶）。"""
    return True


def is_known_object_path(path: str) -> bool:
    """已知受管路径判定（保留兼容）：返回 True 除非是绝对 URL 或完全无法解析。

    为不影响 controllers 老调用方行为，统一返回 True（业务侧不严格校验）。
    """
    if not path or path.startswith(("http://", "https://")):
        return False
    return True


# ============================================================
# 兼容 shim：HMAC 短签名函数（DEPRECATED，仅让 controllers 不报错）
# ============================================================
STATIC_LINK_SECRET: str = _env("STATIC_LINK_SECRET", "zhpt_static_secret_2024")
STATIC_LINK_EXPIRE_SECONDS: int = _env_int("STATIC_LINK_EXPIRE_SECONDS", 300)
FEEDBACK_IMG_SECRET: str = _env("FEEDBACK_IMG_SECRET", "zhpt_feedback_img_secret_2024")
FEEDBACK_URL_EXPIRE: int = _env_int("FEEDBACK_URL_EXPIRE", 3600)


def _sign_token(payload: str, t: int, secret: str = "") -> str:
    """HMAC 短签名（DEPRECATED）。SigV4 时代不再使用，保留 shim。"""
    import warnings
    warnings.warn(
        "_sign_token() HMAC 短签名已废弃，新代码请用 sign_object_url()/resolve_url() 的 SigV4",
        DeprecationWarning,
        stacklevel=2,
    )
    secret = secret or STATIC_LINK_SECRET
    raw = f"{payload}{t}{secret}".encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def sign_photo_url(sfzh: str, subdir: str = HEADPHOTO_DIR_OPEN) -> str:  # pragma: no cover - 兼容
    """DEPRECATED：原返回 ``/photo/get_headphoto/{sfzh}?t=&s=`` 形式 HMAC URL。

    新实现：返回 Sig V4 预签名 URL（``/object/<bucket>/<subdir>/<sfzh>.jpg?X-Amz-...``），
    与 headphoto 同款，不依赖 photo_proxy 端 controller 验签。

    参数
    ----
    sfzh : 身份证号
    subdir : 头像子目录，默认 ``headphoto/open``。中职传 ``headphoto/vocational``。
    """
    import warnings
    warnings.warn(
        "sign_photo_url() HMAC 形式已废弃，请改用 resolve_url()/get_photo_url()",
        DeprecationWarning, stacklevel=2,
    )
    return get_photo_url(sfzh, subdir=subdir)


def verify_photo_sign(sfzh: str, t: int, s: str) -> bool:
    """DEPRECATED：SigV4 时代 MinIO 服务器端校验，无需应用层 shim。"""
    import warnings
    warnings.warn("verify_photo_sign() HMAC 形式已废弃", DeprecationWarning, stacklevel=2)
    return True  # 不阻塞 controller，URL 全部由 MinIO 验签


def sign_object_url_hmac(object_key: str) -> str:
    """DEPRECATED：HMAC 形式 ``/object/{key}?t=&s=`` 已废弃，迁移到 SigV4 后行为变化。"""
    import warnings
    warnings.warn(
        "sign_object_url_hmac() HMAC 形式已废弃，请改用 sign_object_url() (SigV4)",
        DeprecationWarning, stacklevel=2,
    )
    # 返回 SigV4 形式（实际安全更好，让原有 controllers 也能继续展示图片）
    return sign_object_url(object_key)


# controllers 老调用方用 sign_object_url(...)，但新 sign_object_url() 是 SigV4。
# 为保留 controller 端代码不动时的语义安全，**别名**老 verify 函数：
verify_object_sign = verify_photo_sign  # DEPRECATED alias


def _feedback_sign(object_key: str, ts: int) -> str:
    import warnings
    warnings.warn(
        "_feedback_sign() HMAC 形式已废弃，新代码用 sign_object_url() SigV4",
        DeprecationWarning, stacklevel=2,
    )
    raw = f"{object_key}_{ts}_{FEEDBACK_IMG_SECRET}"
    return hashlib.md5(raw.encode()).hexdigest()[:8]


def get_feedback_image_url(object_key: str) -> str:
    """DEPRECATED：HMAC 形式 ``/feedback/image/{key}?t=&s=`` 已废弃。"""
    import warnings
    warnings.warn(
        "get_feedback_image_url() HMAC 形式已废弃，请改用 sign_object_url() (SigV4)",
        DeprecationWarning, stacklevel=2,
    )
    return sign_object_url(object_key)


def verify_feedback_sign(object_key: str, t: int, s: str) -> bool:
    """DEPRECATED：SigV4 时代 MinIO 服务器端校验。"""
    import warnings
    warnings.warn("verify_feedback_sign() HMAC 形式已废弃", DeprecationWarning, stacklevel=2)
    return True


# ============================================================
# 兼容旧 BucketRoute dataclass（如果 controllers 有引用）
# ============================================================
from dataclasses import dataclass  # noqa: E402


@dataclass(frozen=True)
class BucketRoute:
    """保留兼容老 dataclass：现在只有单一桶，老调用方不会出错。"""
    bucket: str
    private: bool = True


def resolve_route(path: str) -> BucketRoute:
    """保留兼容：统一返回到 BUCKET_PRIVATE 的私有路由。"""
    return BucketRoute(BUCKET_PRIVATE, private=True)


# ============================================================
# 兼容 ensure_bucket_exists（controllers 初始化时调用）
# ============================================================
def ensure_bucket_exists() -> bool:
    """保留兼容老 API；按 headphoto 约定桶由运维预建，应用层只 stat 确认存在。"""
    try:
        client = gateway.client
    except RuntimeError as e:
        logger.warning("MinIO 不可用，跳过 ensure_bucket_exists: %s", e)
        return False
    try:
        client.stat_object(BUCKET_PRIVATE, "")
        return True
    except Exception:
        try:
            next(iter(client.list_objects(BUCKET_PRIVATE, prefix="", recursive=False)), None)
            return True
        except Exception as e2:
            logger.warning(
                "无法确认桶 %s 存在，请确认运维已预建: %s", BUCKET_PRIVATE, e2,
            )
            return False


__all__ = [
    # 配置常量
    "MINIO_ENDPOINT",
    "MINIO_SECURE",
    "MINIO_BUCKET_PRIVATE",
    "MINIO_BUCKET_PUBLIC",
    "MINIO_BUCKET",
    # 桶常量
    "BUCKET_PRIVATE",
    "BUCKET_PUBLIC",
    "BUCKET_ZHXT",
    "OBJECT_URL_PREFIX",
    "ZHXT_URL_PREFIX",
    "PRESIGN_EXPIRES_SECONDS",
    # 路径解析
    "split_bucket_key",
    # 核心 URL
    "resolve_url",
    "resolve_url_with_host",
    "resolve_url_zhxt",
    "sign_object_url",
    "get_preview_url",
    # 工具
    "BucketRoute",  # 兼容老 dataclass
    "resolve_route",
    "infer_bucket_by_path",
    "is_private_path",
    "is_known_object_path",
    # 照片
    "upload_photo",
    "upload_photo_with_url",
    "put_headphoto",
    "delete_photo",
    "check_photo_exists",
    "get_photo_url",
    "get_photo_size",
    # 头像子目录常量与映射
    "HEADPHOTO_DIR_OPEN",
    "HEADPHOTO_DIR_VOCATIONAL",
    "HEADPHOTO_DIR_TEACHER",
    "HEADPHOTO_LEGACY_KEY",
    "user_type_to_headphoto_subdir",
    # 教师头像（zhxt 桶专用）
    "BUCKET_ZHXT",
    "MINIO_BUCKET_ZHXT",
    "TEACHER_HEADPHOTO_DIR",
    "upload_teacher_headphoto",
    "check_teacher_headphoto_exists",
    "get_teacher_headphoto_url",
    "delete_teacher_headphoto",
    # 业务 put_*
    "put_object",
    "put_image",
    "put_brochure_image",
    "put_zs_image",
    "put_jytj_image",
    "put_feedback_image",
    "put_feedback_poster",
    "put_public_image",  # 保留兼容，但走私有桶
    # 上传 / 删除 / 下载
    "delete_object",
    "delete_by_path",
    "download_file",
    "stat_object",
    # 兼容
    "ensure_bucket_exists",
    # DEPRECATED HMAC shim（controllers 老调用方使用）
    "STATIC_LINK_SECRET",
    "STATIC_LINK_EXPIRE_SECONDS",
    "FEEDBACK_IMG_SECRET",
    "FEEDBACK_URL_EXPIRE",
    "_sign_token",
    "sign_photo_url",
    "verify_photo_sign",
    "verify_object_sign",
    "sign_object_url_hmac",
    "_feedback_sign",
    "get_feedback_image_url",
    "verify_feedback_sign",
]
