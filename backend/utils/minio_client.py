"""
MinIO 网关层（统一入口，参考 headphoto/backend/app/core/minio_client.py 的设计）

职责：
1. 唯一 Minio SDK 客户端；endpoint / AK / SK / 桶名全部从 .env 读取
2. MinIO 不可用时优雅降级：初始化只记录日志，业务调用时才抛 RuntimeError
3. 上层统一通过 services/minio_service.py 的语义方法调用，本模块只暴露：
   - upload / upload_public / upload_private / delete_object / download / stat
   - presign_get / get_object
4. 不在应用启动期 make_bucket；桶由运维预建

设计要点：
- 单例网关（双重检查锁）
- 所有 IO 方法同步，调用方决定是否 to_thread
- 精确捕获 S3Error，避免被 urllib3 "Max retries exceeded" 笼统吞掉
- 兼容旧 API：get_minio_client() / get_zhpt_minio_client() / reset_minio_client()

环境变量（统一从 init.config 的 WeChatConfig 风格读取；这里直接用 os.getenv 跟项目其它
模块保持一致——zhpt-new 没有 pydantic-settings 风格的 BaseSettings）：

  MINIO_ENDPOINT       端点（不含 scheme，例如 172.16.100.102:9000）
  MINIO_SECURE         "true" / "false"
  MINIO_ACCESS_KEY
  MINIO_SECRET_KEY
  MINIO_BUCKET_PRIVATE 私有桶（头像/反馈/3+4报名图/招生简章 etc）
  MINIO_BUCKET_PUBLIC  公开桶（首页背景/默认头像/答题图标 etc）
  STATIC_LINK_SECRET   nginx secure_link 共享密钥 + 业务图 HMAC 签名密钥
  STATIC_LINK_EXPIRE_SECONDS  业务图签名 URL 有效期（默认 300）

关于连接池：
- `Minio` 底层使用 urllib3.PoolManager，单例下默认连接复用即可，不需要
  业务层再构建「连接池」。
- 仅当 QPS 高、对象偏大，或需要调整 connect/read 超时/重试参数时，
  构造 `Minio(...)` 时通过 `http_client=` 注入自定义 `urllib3.PoolManager`
  / `Retry` 即可。可参考：
      urllib3.PoolManager(num_pools=20, maxsize=50,
                           timeout=urllib3.Timeout(connect=2.0, read=10.0),
                           retries=urllib3.Retry(total=3, backoff_factor=0.2,
                                                 status_forcelist=[502, 503, 504]))
- 一个 client 可操作任意桶（含私有/公开两桶），不需要为每个桶各起一个 client
"""
from __future__ import annotations

import logging
import os
import threading
from io import BytesIO
from pathlib import Path
from typing import Optional

from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)


# ==============================================================
# .env 自动加载
# --------------------------------------------------------------
# zhpt-new/backend 没有 pydantic-settings，main.py / init/config.py
# 也没有显式 load_dotenv。如果直接 `python main.py` 启动，进程
# 环境变量里就不会有 MINIO_*，网关会被错误地"降级"。
#
# 这里在模块导入阶段静默加载 backend/.env（只兜底未设置的项，
# 不覆盖 os.environ 中已经显式注入的值——便于运维在 systemd /
# IIS / supervisor 里覆盖 .env）。
# ==============================================================
def _load_dotenv_quiet() -> None:
    try:
        from dotenv import load_dotenv  # python-dotenv
    except ImportError:
        return  # 没装就跳过；运维已经通过环境变量注入
    # backend/.env = utils/minio_client.py → 向上两级
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)


_load_dotenv_quiet()


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


# ==============================================================
# 单例 Gateway
# ==============================================================
class MinioGateway:
    """MinIO 统一网关：单例 + 优雅降级。"""

    _instance: Optional["MinioGateway"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init_client()
        return cls._instance

    def _init_client(self) -> None:
        self._client: Optional[Minio] = None
        self._available: bool = False

        endpoint = _env("MINIO_ENDPOINT", _env("MINIO_HOST", "172.16.100.102:9000"))
        ak = _env("MINIO_ACCESS_KEY")
        sk = _env("MINIO_SECRET_KEY")
        secure = _env("MINIO_SECURE", "false").lower() == "true"

        # 桶名（私有/公开），兼容老别名 MINIO_BUCKET
        bucket_private = _env("MINIO_BUCKET_PRIVATE") or _env("MINIO_BUCKET", "headphoto")
        bucket_public = _env("MINIO_BUCKET_PUBLIC", bucket_private)
        # 业务专用桶（如教师头像专用桶 zhxt），由运维在 .env 中显式配置；
        # 未配置时降级到私有桶，避免影响现有逻辑。
        bucket_zhxt = _env("MINIO_BUCKET_ZHXT", bucket_private)
        self._bucket_private = bucket_private
        self._bucket_public = bucket_public
        self._bucket_zhxt = bucket_zhxt
        self._endpoint = endpoint
        self._secure = secure

        if not (ak and sk):
            logger.warning("⚠️ MinIO 凭证缺失，MinIO 功能进入降级模式")
            return

        try:
            self._client = Minio(
                endpoint,
                access_key=ak,
                secret_key=sk,
                secure=secure,
            )
            self._available = True
            logger.info(
                "✅ MinIO 客户端初始化完成 endpoint=%s secure=%s private=%s public=%s zhxt=%s",
                endpoint, secure, bucket_private, bucket_public, bucket_zhxt,
            )
        except Exception as e:  # noqa: BLE001
            logger.error("❌ MinIO 客户端初始化失败，进入降级模式: %s", e)
            self._client = None
            self._available = False

    # ------------------------------------------------------------------
    # 基础属性
    # ------------------------------------------------------------------
    @property
    def available(self) -> bool:
        return self._available and self._client is not None

    @property
    def client(self) -> Minio:
        if not self.available:
            raise RuntimeError("MinIO 不可用：请检查 MINIO_ENDPOINT / 凭证配置")
        return self._client  # type: ignore[return-value]

    @property
    def bucket_private(self) -> str:
        return self._bucket_private

    @property
    def bucket_public(self) -> str:
        return self._bucket_public

    @property
    def bucket_zhxt(self) -> str:
        """教师头像专用桶（zhxt），运维通过 MINIO_BUCKET_ZHXT 配置，未配置时回退到私有桶。"""
        return self._bucket_zhxt

    @property
    def endpoint(self) -> str:
        return self._endpoint

    @property
    def secure(self) -> bool:
        return self._secure

    def reset(self) -> None:
        """测试 / 凭证轮换后强制重建 client。"""
        with self._lock:
            self._client = None
            self._available = False
            self._init_client()

    # ------------------------------------------------------------------
    # 上传 / 删除 / 下载 / stat / 签名
    # ------------------------------------------------------------------
    def upload(
        self,
        bucket: str,
        object_name: str,
        content: bytes,
        content_type: Optional[str] = None,
    ) -> str:
        """上传到指定桶，返回 object_name（不含 bucket 前缀）。"""
        if not self.available:
            raise RuntimeError("MinIO 不可用，无法上传文件")
        object_name = object_name.lstrip("/")
        try:
            self.client.put_object(
                bucket,
                object_name,
                BytesIO(content),
                length=len(content),
                content_type=content_type or "application/octet-stream",
            )
            logger.info("📤 上传成功 bucket=%s object=%s size=%d", bucket, object_name, len(content))
            return object_name
        except S3Error as e:
            logger.error("❌ 上传失败 bucket=%s object=%s: %s", bucket, object_name, e)
            raise

    def upload_public(self, object_name: str, content: bytes, content_type: Optional[str] = None) -> str:
        return self.upload(self._bucket_public, object_name, content, content_type)

    def upload_private(self, object_name: str, content: bytes, content_type: Optional[str] = None) -> str:
        return self.upload(self._bucket_private, object_name, content, content_type)

    def delete_object(self, bucket: str, object_name: str) -> bool:
        """删除对象；失败返回 False（不抛异常，调用方按需处理）。"""
        if not self.available:
            return False
        object_name = object_name.lstrip("/")
        try:
            self.client.remove_object(bucket, object_name)
            logger.info("🗑️ 删除成功 bucket=%s object=%s", bucket, object_name)
            return True
        except S3Error as e:
            logger.warning("⚠️ 删除失败 bucket=%s object=%s: %s", bucket, object_name, e)
            return False

    def download(self, bucket: str, object_name: str) -> Optional[bytes]:
        """下载对象字节；失败返回 None。"""
        if not self.available:
            return None
        object_name = object_name.lstrip("/")
        try:
            resp = self.client.get_object(bucket, object_name)
            try:
                return resp.read()
            finally:
                try:
                    resp.close()
                    resp.release_conn()
                except Exception:
                    pass
        except S3Error as e:
            logger.warning("⚠️ 下载失败 bucket=%s object=%s: %s", bucket, object_name, e)
            return None

    def stat(self, bucket: str, object_name: str):
        """stat_object 包装，失败抛 S3Error（由调用方决定如何处理）。"""
        if not self.available:
            raise RuntimeError("MinIO 不可用")
        return self.client.stat_object(bucket, object_name.lstrip("/"))

    def stat_silent(self, bucket: str, object_name: str) -> bool:
        """stat_object 但不抛异常；用于"对象是否存在"判断。"""
        if not self.available:
            return False
        try:
            self.client.stat_object(bucket, object_name.lstrip("/"))
            return True
        except S3Error:
            return False

    def stat_object_full(self, bucket: str, object_name: str):
        """返回完整 stat 对象（含 size / content_type 等）；失败返回 None。"""
        if not self.available:
            return None
        try:
            return self.client.stat_object(bucket, object_name.lstrip("/"))
        except S3Error as e:
            logger.warning("⚠️ stat 失败 bucket=%s object=%s: %s", bucket, object_name, e)
            return None

    def presign_get(self, bucket: str, object_name: str, expires_seconds: int = 300) -> str:
        """生成私有对象的预签名 GET URL（直连 MinIO）。"""
        if not self.available:
            raise RuntimeError("MinIO 不可用，无法生成预签名 URL")
        from datetime import timedelta
        return self.client.presigned_get_object(
            bucket,
            object_name.lstrip("/"),
            expires=timedelta(seconds=expires_seconds),
        )

    def get_object(self, bucket: str, object_name: str, offset: int = 0, length: Optional[int] = None):
        """透传 SDK 的 get_object（返回 response 流式对象）。失败抛 S3Error。"""
        if not self.available:
            raise RuntimeError("MinIO 不可用")
        if length is not None:
            return self.client.get_object(bucket, object_name.lstrip("/"), offset=offset, length=length)
        return self.client.get_object(bucket, object_name.lstrip("/"))

    def list_objects(self, bucket: str, prefix: str = "", recursive: bool = True):
        """透传 SDK 的 list_objects；不可用时抛 RuntimeError。"""
        if not self.available:
            raise RuntimeError("MinIO 不可用")
        return self.client.list_objects(bucket, prefix=prefix, recursive=recursive)


# ==============================================================
# 全局单例
# ==============================================================
gateway = MinioGateway()


# ==============================================================
# 兼容旧 API：保持函数签名一致，老代码无须修改
# ==============================================================
def get_minio_client() -> Minio:
    """兼容旧代码：返回 Minio 客户端；不可用时抛 RuntimeError。"""
    return gateway.client


def get_minio_gateway() -> MinioGateway:
    """返回 gateway 单例（推荐新代码使用）。"""
    return gateway


def reset_minio_client() -> None:
    """兼容旧代码：强制重建 client（测试 / 凭证轮换）。"""
    gateway.reset()


# 兼容别名（部分老代码用旧名）
def get_zhpt_minio_client() -> Minio:
    """已废弃别名，等同于 get_minio_client()。"""
    return get_minio_client()


def reset_zhpt_minio_client() -> None:
    """已废弃别名，等同于 reset_minio_client()。"""
    reset_minio_client()


__all__ = [
    "MinioGateway",
    "gateway",
    "get_minio_client",
    "get_minio_gateway",
    "reset_minio_client",
    "get_zhpt_minio_client",
    "reset_zhpt_minio_client",
]