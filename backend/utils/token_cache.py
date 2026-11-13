#!/usr/bin/env python3
"""
JWT Token 缓存系统
提供 Token 验证缓存、用户信息缓存等功能
"""

import json
import time
import hashlib
import logging
from typing import Dict, Any, Optional
from functools import wraps
import jwt
from init.redis_manager import redis_manager

logger = logging.getLogger(__name__)

class TokenCache:
    """JWT Token 缓存管理器"""
    
    def __init__(self, prefix: str = "token_cache:", default_expire: int = 1800):
        self.prefix = prefix
        self.default_expire = default_expire  # 30分钟默认缓存时间
        self.redis = redis_manager
        
        # Token 验证缓存前缀
        self.token_prefix = f"{prefix}token:"
        self.user_prefix = f"{prefix}user:"
        self.blacklist_prefix = f"{prefix}blacklist:"
    
    def _get_token_hash(self, token: str) -> str:
        """生成 Token 的哈希值作为缓存键"""
        return hashlib.sha256(token.encode()).hexdigest()[:16]
    
    def cache_token_payload(self, token: str, payload: Dict[str, Any], 
                           expire: int = None) -> bool:
        """
        缓存 Token 的解析结果
        
        Args:
            token: JWT token
            payload: 解析后的载荷
            expire: 缓存过期时间（秒）
        """
        try:
            token_hash = self._get_token_hash(token)
            cache_key = f"{self.token_prefix}{token_hash}"
            
            # 添加缓存时间戳
            cache_data = {
                'payload': payload,
                'cached_at': int(time.time()),
                'token_exp': payload.get('exp', 0)
            }
            
            expire_time = expire or self.default_expire
            # 不能超过 token 本身的过期时间
            if payload.get('exp'):
                max_expire = payload['exp'] - int(time.time())
                if max_expire > 0:
                    expire_time = min(expire_time, max_expire)
                else:
                    # Token 已过期，不缓存
                    return False
            
            success = self.redis.set(cache_key, cache_data, ex=expire_time)
            if success:
                logger.debug(f"Cached token payload for {expire_time}s")
            return success
            
        except Exception as e:
            logger.error(f"Failed to cache token payload: {e}")
            return False
    
    def get_cached_payload(self, token: str) -> Optional[Dict[str, Any]]:
        """
        获取缓存的 Token 载荷
        
        Returns:
            Token 载荷字典，如果未缓存或已过期则返回 None
        """
        try:
            token_hash = self._get_token_hash(token)
            cache_key = f"{self.token_prefix}{token_hash}"
            
            cached_data = self.redis.get(cache_key)
            if not cached_data:
                return None
            
            # 检查 token 是否在黑名单中
            if self.is_token_blacklisted(token):
                self.invalidate_token(token)
                return None
            
            # 检查 token 本身是否过期
            payload = cached_data['payload']
            if payload.get('exp') and payload['exp'] < int(time.time()):
                self.invalidate_token(token)
                return None
            
            logger.debug("Token payload cache hit")
            return payload
            
        except Exception as e:
            logger.error(f"Failed to get cached token payload: {e}")
            return None
    
    def cache_user_info(self, user_id: str, user_info: Dict[str, Any], 
                       expire: int = None) -> bool:
        """
        缓存用户信息
        
        Args:
            user_id: 用户ID
            user_info: 用户信息字典
            expire: 缓存过期时间（秒）
        """
        try:
            cache_key = f"{self.user_prefix}{user_id}"
            expire_time = expire or self.default_expire
            
            cache_data = {
                'user_info': user_info,
                'cached_at': int(time.time())
            }
            
            success = self.redis.set(cache_key, cache_data, ex=expire_time)
            if success:
                logger.debug(f"Cached user info for user {user_id}")
            return success
            
        except Exception as e:
            logger.error(f"Failed to cache user info: {e}")
            return False
    
    def get_cached_user_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取缓存的用户信息"""
        try:
            cache_key = f"{self.user_prefix}{user_id}"
            cached_data = self.redis.get(cache_key)
            
            if cached_data:
                logger.debug(f"User info cache hit for user {user_id}")
                return cached_data['user_info']
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get cached user info: {e}")
            return None
    
    def invalidate_token(self, token: str) -> bool:
        """使 Token 缓存失效"""
        try:
            token_hash = self._get_token_hash(token)
            cache_key = f"{self.token_prefix}{token_hash}"
            return self.redis.delete(cache_key) > 0
        except Exception as e:
            logger.error(f"Failed to invalidate token: {e}")
            return False
    
    def invalidate_user_cache(self, user_id: str) -> bool:
        """使用户信息缓存失效"""
        try:
            cache_key = f"{self.user_prefix}{user_id}"
            return self.redis.delete(cache_key) > 0
        except Exception as e:
            logger.error(f"Failed to invalidate user cache: {e}")
            return False
    
    def blacklist_token(self, token: str, expire: int = None) -> bool:
        """
        将 Token 加入黑名单
        
        Args:
            token: 要加入黑名单的 token
            expire: 黑名单过期时间（通常设置为 token 的剩余有效期）
        """
        try:
            token_hash = self._get_token_hash(token)
            blacklist_key = f"{self.blacklist_prefix}{token_hash}"
            
            # 如果没有指定过期时间，尝试从 token 中获取
            if expire is None:
                try:
                    # 不验证签名，只获取过期时间
                    payload = jwt.decode(token, options={"verify_signature": False})
                    if payload.get('exp'):
                        expire = payload['exp'] - int(time.time())
                        if expire <= 0:
                            expire = 60  # 已过期的 token 也要短暂加入黑名单
                except:
                    expire = 3600  # 默认1小时
            
            success = self.redis.set(blacklist_key, "blacklisted", ex=expire)
            if success:
                # 同时使缓存失效
                self.invalidate_token(token)
                logger.info(f"Token blacklisted for {expire}s")
            return success
            
        except Exception as e:
            logger.error(f"Failed to blacklist token: {e}")
            return False
    
    def is_token_blacklisted(self, token: str) -> bool:
        """检查 Token 是否在黑名单中"""
        try:
            token_hash = self._get_token_hash(token)
            blacklist_key = f"{self.blacklist_prefix}{token_hash}"
            return self.redis.exists(blacklist_key)
        except Exception as e:
            logger.error(f"Failed to check token blacklist: {e}")
            return False
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        try:
            token_keys = self.redis.keys(f"{self.token_prefix}*")
            user_keys = self.redis.keys(f"{self.user_prefix}*")
            blacklist_keys = self.redis.keys(f"{self.blacklist_prefix}*")
            
            return {
                'token_cache_count': len(token_keys),
                'user_cache_count': len(user_keys),
                'blacklist_count': len(blacklist_keys),
                'total_cache_keys': len(token_keys) + len(user_keys) + len(blacklist_keys)
            }
        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {}
    
    def clear_expired_cache(self) -> int:
        """清理过期的缓存（Redis 会自动处理，这里主要用于统计）"""
        # Redis 会自动清理过期的键，这个方法主要用于手动清理和统计
        try:
            # 获取所有相关的键
            all_keys = []
            all_keys.extend(self.redis.keys(f"{self.token_prefix}*"))
            all_keys.extend(self.redis.keys(f"{self.user_prefix}*"))
            all_keys.extend(self.redis.keys(f"{self.blacklist_prefix}*"))
            
            # 检查并删除过期的键（实际上 Redis 会自动处理）
            expired_count = 0
            for key in all_keys:
                ttl = self.redis.ttl(key)
                if ttl == -2:  # 键不存在（已过期被删除）
                    expired_count += 1
            
            logger.info(f"Found {expired_count} expired cache keys")
            return expired_count
            
        except Exception as e:
            logger.error(f"Failed to clear expired cache: {e}")
            return 0

# 全局 Token 缓存实例
token_cache = TokenCache()

def cached_token_verification(func):
    """
    Token 验证缓存装饰器
    
    Usage:
        @cached_token_verification
        def verify_token_and_get_payload(token: str):
            # 原有的 token 验证逻辑
            pass
    """
    @wraps(func)
    def wrapper(token: str, *args, **kwargs):
        # 尝试从缓存获取
        cached_payload = token_cache.get_cached_payload(token)
        if cached_payload:
            return cached_payload
        
        # 缓存未命中，执行原函数
        try:
            payload = func(token, *args, **kwargs)
            
            # 缓存结果
            if payload:
                token_cache.cache_token_payload(token, payload)
            
            return payload
            
        except Exception as e:
            # 如果验证失败，确保不缓存错误结果
            logger.debug(f"Token verification failed: {e}")
            raise
    
    return wrapper
