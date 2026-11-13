#!/usr/bin/env python3
"""
API 响应缓存中间件
提供基于路径和参数的响应缓存功能
"""

import json
import hashlib
import logging
from typing import Dict, Any, Optional, List, Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from init.redis_manager import redis_manager

logger = logging.getLogger(__name__)

class ResponseCacheMiddleware(BaseHTTPMiddleware):
    """API 响应缓存中间件"""
    
    def __init__(
        self, 
        app,
        cache_prefix: str = "api_cache:",
        default_expire: int = 300,
        cacheable_methods: List[str] = None,
        cacheable_paths: List[str] = None,
        exclude_paths: List[str] = None,
        cache_private_responses: bool = False
    ):
        super().__init__(app)
        self.cache_prefix = cache_prefix
        self.default_expire = default_expire
        self.cacheable_methods = cacheable_methods or ['GET']
        self.cacheable_paths = cacheable_paths or []
        self.exclude_paths = exclude_paths or ['/health', '/docs', '/openapi.json']
        self.cache_private_responses = cache_private_responses
        self.redis = redis_manager
        
        # 统计信息
        self.cache_hits = 0
        self.cache_misses = 0
        self.cache_errors = 0
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """处理请求和响应缓存"""
        
        # 检查是否应该缓存此请求
        if not self._should_cache_request(request):
            return await call_next(request)
        
        # 生成缓存键
        cache_key = self._generate_cache_key(request)
        
        # 尝试从缓存获取响应
        cached_response = await self._get_cached_response(cache_key)
        if cached_response:
            self.cache_hits += 1
            return cached_response
        
        # 缓存未命中，执行请求
        self.cache_misses += 1
        response = await call_next(request)
        
        # 缓存响应（如果符合条件）
        if self._should_cache_response(request, response):
            await self._cache_response(cache_key, response)
        
        return response
    
    def _should_cache_request(self, request: Request) -> bool:
        """判断是否应该缓存此请求"""
        
        # 检查HTTP方法
        if request.method not in self.cacheable_methods:
            return False
        
        # 检查路径是否在排除列表中
        path = request.url.path
        for exclude_path in self.exclude_paths:
            if path.startswith(exclude_path):
                return False
        
        # 如果指定了可缓存路径，检查是否匹配
        if self.cacheable_paths:
            path_matched = False
            for cacheable_path in self.cacheable_paths:
                if path.startswith(cacheable_path):
                    path_matched = True
                    break
            if not path_matched:
                return False
        
        # 检查是否包含认证信息（如果不缓存私有响应）
        if not self.cache_private_responses:
            auth_header = request.headers.get('authorization')
            if auth_header:
                return False
        
        return True
    
    def _should_cache_response(self, request: Request, response: Response) -> bool:
        """判断是否应该缓存此响应"""
        
        # 只缓存成功的响应
        if response.status_code != 200:
            return False
        
        # 检查响应头中的缓存控制
        cache_control = response.headers.get('cache-control', '')
        if 'no-cache' in cache_control or 'no-store' in cache_control:
            return False
        
        # 检查内容类型
        content_type = response.headers.get('content-type', '')
        if not content_type.startswith('application/json'):
            return False
        
        return True
    
    def _generate_cache_key(self, request: Request) -> str:
        """生成缓存键"""
        
        # 基本信息
        method = request.method
        path = request.url.path
        query_params = str(request.query_params)
        
        # 如果缓存私有响应，包含用户信息
        user_info = ""
        if self.cache_private_responses:
            auth_header = request.headers.get('authorization', '')
            if auth_header:
                # 使用认证头的哈希值作为用户标识
                user_info = hashlib.md5(auth_header.encode()).hexdigest()[:8]
        
        # 组合缓存键
        cache_data = f"{method}:{path}:{query_params}:{user_info}"
        cache_hash = hashlib.sha256(cache_data.encode()).hexdigest()[:16]
        
        return f"{self.cache_prefix}{cache_hash}"
    
    async def _get_cached_response(self, cache_key: str) -> Optional[Response]:
        """从缓存获取响应"""
        try:
            cached_data = self.redis.get(cache_key)
            if not cached_data:
                return None
            
            # 重构响应
            response_data = cached_data
            content = response_data.get('content', {})
            headers = response_data.get('headers', {})
            status_code = response_data.get('status_code', 200)
            
            # 添加缓存标识头
            headers['X-Cache'] = 'HIT'
            headers['X-Cache-Key'] = cache_key[-8:]  # 只显示最后8位
            
            response = JSONResponse(
                content=content,
                status_code=status_code,
                headers=headers
            )
            
            logger.debug(f"Cache hit for key: {cache_key}")
            return response
            
        except Exception as e:
            logger.error(f"Failed to get cached response: {e}")
            self.cache_errors += 1
            return None
    
    async def _cache_response(self, cache_key: str, response: Response) -> bool:
        """缓存响应"""
        try:
            # 读取响应内容
            if hasattr(response, 'body'):
                body = response.body
            else:
                # 对于StreamingResponse等，需要特殊处理
                return False
            
            # 解析JSON内容
            try:
                content = json.loads(body.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return False
            
            # 准备缓存数据
            cache_data = {
                'content': content,
                'headers': dict(response.headers),
                'status_code': response.status_code,
                'cached_at': self.redis.get_current_timestamp() if hasattr(self.redis, 'get_current_timestamp') else None
            }
            
            # 确定过期时间
            expire_time = self.default_expire
            
            # 检查响应中的缓存控制头
            cache_control = response.headers.get('cache-control', '')
            if 'max-age=' in cache_control:
                try:
                    max_age = int(cache_control.split('max-age=')[1].split(',')[0])
                    expire_time = min(expire_time, max_age)
                except (ValueError, IndexError):
                    pass
            
            # 缓存响应
            success = self.redis.set(cache_key, cache_data, ex=expire_time)
            
            if success:
                logger.debug(f"Cached response for key: {cache_key}, expire: {expire_time}s")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to cache response: {e}")
            self.cache_errors += 1
            return False
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        total_requests = self.cache_hits + self.cache_misses
        hit_rate = self.cache_hits / max(total_requests, 1)
        
        return {
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'cache_errors': self.cache_errors,
            'total_requests': total_requests,
            'hit_rate': round(hit_rate * 100, 2),
            'error_rate': round(self.cache_errors / max(total_requests, 1) * 100, 2)
        }
    
    def clear_cache(self, pattern: str = "*") -> int:
        """清除缓存"""
        try:
            cache_pattern = f"{self.cache_prefix}{pattern}"
            keys = self.redis.keys(cache_pattern)
            if keys:
                deleted_count = self.redis.delete(*keys)
                logger.info(f"Cleared {deleted_count} cache entries")
                return deleted_count
            return 0
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
            return 0

# 预定义的缓存配置
def create_api_cache_middleware(
    app,
    environment: str = 'development'
) -> ResponseCacheMiddleware:
    """
    创建适合不同环境的API缓存中间件
    
    Args:
        app: FastAPI应用实例
        environment: 环境名称
    
    Returns:
        配置好的缓存中间件
    """
    
    if environment == 'production':
        # 生产环境：更积极的缓存策略
        return ResponseCacheMiddleware(
            app,
            cache_prefix="prod_api_cache:",
            default_expire=600,  # 10分钟
            cacheable_methods=['GET'],
            cacheable_paths=['/api/'],
            exclude_paths=['/health', '/docs', '/openapi.json', '/admin/', '/dev/'],
            cache_private_responses=False
        )
    
    elif environment == 'development':
        # 开发环境：保守的缓存策略
        return ResponseCacheMiddleware(
            app,
            cache_prefix="dev_api_cache:",
            default_expire=60,  # 1分钟
            cacheable_methods=['GET'],
            cacheable_paths=['/api/public/', '/api/system/'],
            exclude_paths=['/health', '/docs', '/openapi.json', '/dev/', '/test/'],
            cache_private_responses=False
        )
    
    else:
        # 测试环境：最小缓存
        return ResponseCacheMiddleware(
            app,
            cache_prefix="test_api_cache:",
            default_expire=30,  # 30秒
            cacheable_methods=['GET'],
            cacheable_paths=[],
            exclude_paths=['/health', '/docs', '/openapi.json'],
            cache_private_responses=False
        )
