"""
openid hash 工具：用于问卷匿名合规存储。
算法：SHA256(openid + salt)

⚠️ 注意：
- salt 来自 init.config 的 wechat.OPENID_HASH_SALT，切勿硬编码或泄露
- salt 一旦变更，所有基于 hash 的查询将失效
- 空 openid 返回 None，便于上层判空
"""
import hashlib
from typing import Optional

# 从 config 统一获取 salt
from init.config import get_config


def get_hash_salt() -> str:
    salt = get_config().wechat.OPENID_HASH_SALT
    if not salt:
        raise ValueError("OPENID_HASH_SALT 未配置")
    return salt


def hash_openid(openid: Optional[str]) -> Optional[str]:
    """计算 openid 的 SHA256 hash。

    Args:
        openid: 微信原始 openid，空字符串/None 返回 None。

    Returns:
        64位 hex 字符串，或 None。
    """
    if not openid or not str(openid).strip():
        return None
    salt = get_hash_salt()
    return hashlib.sha256((str(openid).strip() + salt).encode("utf-8")).hexdigest()