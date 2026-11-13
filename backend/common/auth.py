from datetime import datetime, timedelta, timezone
from typing import Annotated
import jwt
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jwt.exceptions import InvalidTokenError
from passlib.context import CryptContext
from pydantic import BaseModel
from functools import wraps
import time
import logging
from sqlalchemy.orm import Session
from utils.token_cache import token_cache, cached_token_verification

logger = logging.getLogger(__name__)


# 密码加密上下文，暂时不用，因为目前杨仁伟的加密方式和现在不一样，建议后期替换一下
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# jwt的配置
# 隨機秘鑰
SECRET_KEY = "09d25e094faa6ca2556c818166b7e9563b93f7099f6f0f4caa6cf63b88e8d3e7"
# 加密算法
ALGORITHM = "HS256"
# access_token 过期时间（秒）：2小时
ACCESS_TOKEN_EXPIRE_SECONDS = 2 * 60 * 60
# refresh_token 过期时间（秒）：30天
REFRESH_TOKEN_EXPIRE_SECONDS = 30 * 24 * 60 * 60
# refresh_token 专用密钥后缀
REFRESH_SECRET = SECRET_KEY + "_refresh"


# 创建一个认证的依赖，這個組件可以直接注入取得token
auth_token = OAuth2PasswordBearer(tokenUrl='/token')


# ============================================================
# Token 签发
# ============================================================
def create_token(userinfo: dict):
    """创建 access_token"""
    expire = int(time.time()) + ACCESS_TOKEN_EXPIRE_SECONDS
    userinfo['exp'] = expire
    return jwt.encode(userinfo, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(userinfo: dict):
    """创建 refresh_token，有效期 30 天"""
    data = {k: v for k, v in userinfo.items() if k != 'exp'}
    data['exp'] = int(time.time()) + REFRESH_TOKEN_EXPIRE_SECONDS
    data['type'] = 'refresh'
    return jwt.encode(data, REFRESH_SECRET, algorithm=ALGORITHM)


def verify_refresh_token(token: str) -> dict:
    """验证 refresh_token，返回 payload（去除 type/exp）"""
    payload = jwt.decode(token, REFRESH_SECRET, algorithms=[ALGORITHM])
    if payload.get('type') != 'refresh':
        raise jwt.InvalidTokenError("不是有效的 refresh token")
    clean = {k: v for k, v in payload.items() if k not in ('type', 'exp', 'iat')}
    return clean


# ============================================================
# 密码工具
# ============================================================
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """获取密码哈希"""
    return pwd_context.hash(password)


# ============================================================
# 内部：JWT 解码（含黑名单检查 + 缓存）
# ============================================================
def _ensure_not_blacklisted(token: str) -> None:
    """统一的黑名单校验入口，黑名单命中即抛 401。"""
    try:
        if token_cache.is_token_blacklisted(token):
            raise HTTPException(status_code=401, detail="Token已被注销")
    except HTTPException:
        raise
    except Exception as e:
        # 黑名单检查本身失败不应阻塞业务,降级放行
        logger.warning("黑名单检查失败,降级放行: %s", e)


@cached_token_verification
def _verify_token_payload(token: str):
    """底层 JWT 解码,被缓存装饰器包装(自动命中 Redis 缓存)。

    - 业务侧不应直接调用,应走 verify_token_only / verify_token_and_get_payload / verify_token_for_dependencies
    - 上层调用前应先做黑名单校验
    """
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


# ============================================================
# 公开 API:三种 Token 验证依赖
# ============================================================
def verify_token_only(token: str = Depends(auth_token)) -> None:
    """只校验 token 有效性,不返回 payload。

    适用场景:接口只关心"用户是否登录",不需要拿到用户信息。

    行为:
        - 通过黑名单校验(命中即抛 401)
        - 校验签名 + 过期时间
    """
    _ensure_not_blacklisted(token)
    try:
        jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token已过期")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="无效的Token")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Token验证失败: {str(e)}")


def verify_token_and_get_payload(token: str = Depends(auth_token)) -> dict:
    """校验 token 并返回 payload(带 Redis 缓存 + 黑名单)。

    适用场景:绝大多数需要"当前用户是谁"的接口。

    性能优化:
        - 同一个 token 在 Redis 缓存期内(默认 30 分钟),不重复做 JWT 解码
        - 缓存命中时同时也会检查黑名单(在 get_cached_payload 内部)
        - 解析失败时主动失效缓存,避免脏数据
    """
    _ensure_not_blacklisted(token)
    try:
        return _verify_token_payload(token)
    except jwt.ExpiredSignatureError:
        token_cache.invalidate_token(token)
        raise HTTPException(status_code=401, detail="Token已过期")
    except jwt.InvalidTokenError:
        token_cache.invalidate_token(token)
        raise HTTPException(status_code=401, detail="无效的Token")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Token验证失败: {str(e)}")


def verify_token_for_dependencies(token: str) -> dict:
    """不依赖 FastAPI Depends 的版本,直接接收 token 字符串。

    适用场景:init/dependencies.py / photo_proxy.py 等需要手动提取
    Authorization 头并验证的场景。
    """
    _ensure_not_blacklisted(token)
    try:
        return _verify_token_payload(token)
    except jwt.ExpiredSignatureError:
        token_cache.invalidate_token(token)
        raise HTTPException(status_code=401, detail="Token已过期")
    except jwt.InvalidTokenError:
        token_cache.invalidate_token(token)
        raise HTTPException(status_code=401, detail="无效的Token")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Token验证失败: {str(e)}")
