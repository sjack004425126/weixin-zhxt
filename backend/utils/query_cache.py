#!/usr/bin/env python3
"""
数据库查询缓存工具
提供查询结果缓存、缓存失效等功能
"""

import json
import hashlib
import logging
from typing import Any, Optional, Callable, List
from functools import wraps
from sqlalchemy.orm import Session
from init.redis_manager import redis_manager

logger = logging.getLogger(__name__)

class QueryCache:
    """数据库查询缓存管理器"""
    
    def __init__(self, prefix: str = "query_cache:", default_expire: int = 300):
        self.prefix = prefix
        self.default_expire = default_expire
        self.redis = redis_manager
    
    def _generate_cache_key(self, query_str: str, params: dict = None) -> str:
        """生成缓存键"""
        # 将查询和参数组合生成唯一键
        cache_data = {
            'query': query_str,
            'params': params or {}
        }
        cache_str = json.dumps(cache_data, sort_keys=True, ensure_ascii=False)
        cache_hash = hashlib.md5(cache_str.encode('utf-8')).hexdigest()
        return f"{self.prefix}{cache_hash}"
    
    def get(self, query_str: str, params: dict = None) -> Optional[Any]:
        """获取缓存的查询结果"""
        try:
            cache_key = self._generate_cache_key(query_str, params)
            result = self.redis.get(cache_key)
            if result:
                logger.debug(f"Cache hit for query: {query_str[:100]}...")
                return result
            return None
        except Exception as e:
            logger.error(f"Failed to get query cache: {e}")
            return None
    
    def set(self, query_str: str, result: Any, params: dict = None, expire: int = None) -> bool:
        """设置查询结果缓存"""
        try:
            cache_key = self._generate_cache_key(query_str, params)
            expire_time = expire or self.default_expire
            success = self.redis.set(cache_key, result, ex=expire_time)
            if success:
                logger.debug(f"Cached query result: {query_str[:100]}...")
            return success
        except Exception as e:
            logger.error(f"Failed to set query cache: {e}")
            return False
    
    def delete(self, query_str: str, params: dict = None) -> bool:
        """删除特定查询的缓存"""
        try:
            cache_key = self._generate_cache_key(query_str, params)
            return self.redis.delete(cache_key)
        except Exception as e:
            logger.error(f"Failed to delete query cache: {e}")
            return False
    
    def delete_pattern(self, pattern: str) -> int:
        """删除匹配模式的缓存"""
        try:
            keys = self.redis.keys(f"{self.prefix}{pattern}")
            if keys:
                return self.redis.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"Failed to delete cache pattern: {e}")
            return 0
    
    def clear_all(self) -> int:
        """清除所有查询缓存"""
        return self.delete_pattern("*")

# 全局查询缓存实例
query_cache = QueryCache()

def cached_query(expire: int = 300, cache_key_prefix: str = ""):
    """
    查询缓存装饰器
    
    Args:
        expire: 缓存过期时间（秒）
        cache_key_prefix: 缓存键前缀
    
    Usage:
        @cached_query(expire=600, cache_key_prefix="student_")
        def get_student_info(db: Session, student_id: int):
            return db.query(Student).filter_by(id=student_id).first()
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            func_name = f"{cache_key_prefix}{func.__name__}"
            
            # 提取参数用于缓存键生成
            cache_params = {
                'args': str(args[1:]),  # 跳过第一个参数（通常是db session）
                'kwargs': kwargs
            }
            
            # 尝试从缓存获取
            cached_result = query_cache.get(func_name, cache_params)
            if cached_result is not None:
                return cached_result
            
            # 执行原函数
            result = func(*args, **kwargs)
            
            # 缓存结果
            if result is not None:
                query_cache.set(func_name, result, cache_params, expire)
            
            return result
        return wrapper
    return decorator

def cached_query_async(expire: int = 300, cache_key_prefix: str = ""):
    """
    异步查询缓存装饰器
    
    Usage:
        @cached_query_async(expire=600, cache_key_prefix="student_")
        async def get_student_info_async(db: Session, student_id: int):
            return db.query(Student).filter_by(id=student_id).first()
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 生成缓存键
            func_name = f"{cache_key_prefix}{func.__name__}"
            
            # 提取参数用于缓存键生成
            cache_params = {
                'args': str(args[1:]),  # 跳过第一个参数（通常是db session）
                'kwargs': kwargs
            }
            
            # 尝试从缓存获取
            cached_result = query_cache.get(func_name, cache_params)
            if cached_result is not None:
                return cached_result
            
            # 执行原函数
            result = await func(*args, **kwargs)
            
            # 缓存结果
            if result is not None:
                query_cache.set(func_name, result, cache_params, expire)
            
            return result
        return wrapper
    return decorator

def invalidate_cache(patterns: List[str]):
    """
    缓存失效装饰器
    
    Args:
        patterns: 要失效的缓存模式列表
    
    Usage:
        @invalidate_cache(["student_*", "class_*"])
        def update_student(db: Session, student_id: int, data: dict):
            # 更新逻辑
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 执行原函数
            result = func(*args, **kwargs)
            
            # 失效相关缓存
            for pattern in patterns:
                deleted_count = query_cache.delete_pattern(pattern)
                if deleted_count > 0:
                    logger.info(f"Invalidated {deleted_count} cache entries for pattern: {pattern}")
            
            return result
        return wrapper
    return decorator

def invalidate_cache_async(patterns: List[str]):
    """
    异步缓存失效装饰器
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 执行原函数
            result = await func(*args, **kwargs)
            
            # 失效相关缓存
            for pattern in patterns:
                deleted_count = query_cache.delete_pattern(pattern)
                if deleted_count > 0:
                    logger.info(f"Invalidated {deleted_count} cache entries for pattern: {pattern}")
            
            return result
        return wrapper
    return decorator

# 便捷函数
def cache_student_query(expire: int = 600):
    """学生查询缓存装饰器"""
    return cached_query(expire=expire, cache_key_prefix="student_")

def cache_teacher_query(expire: int = 600):
    """教师查询缓存装饰器"""
    return cached_query(expire=expire, cache_key_prefix="teacher_")

def cache_class_query(expire: int = 300):
    """班级查询缓存装饰器"""
    return cached_query(expire=expire, cache_key_prefix="class_")

def cache_system_query(expire: int = 1800):
    """系统配置查询缓存装饰器（缓存时间较长）"""
    return cached_query(expire=expire, cache_key_prefix="system_")
