"""
优化的Redis管理器
提供单例模式、连接池、错误处理和监控功能
"""

import redis
import logging
from typing import Optional, Dict, Any
from redis.connection import ConnectionPool
from init.config import get_redis_config, get_config
import json
import time

class RedisManager:
    """Redis管理器 - 单例模式"""

    _instance = None
    _redis_client = None
    _connection_pool = None
    _config = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_init_done'):
            self._init_done = True
            self.logger = logging.getLogger(__name__)
    
    @property
    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._initialized

    def init_redis(self, config_name='development'):
        """初始化Redis连接"""
        if self._redis_client is None:
            redis_config = get_redis_config(config_name)

            try:
                # 创建连接池
                pool_kwargs = {
                    "host": redis_config["host"],
                    "port": redis_config["port"],
                    "db": redis_config["db"],
                    "decode_responses": redis_config["decode_responses"],
                    "encoding": redis_config["encoding"],
                    "max_connections": redis_config["max_connections"],
                    "retry_on_timeout": redis_config["retry_on_timeout"],
                    "socket_timeout": redis_config["socket_timeout"],
                    "socket_connect_timeout": redis_config["socket_connect_timeout"],
                    "socket_keepalive": redis_config["socket_keepalive"],
                    "health_check_interval": redis_config["health_check_interval"],
                }

                # 如果有密码，添加密码配置
                if redis_config.get("password"):
                    pool_kwargs["password"] = redis_config["password"]

                self._connection_pool = ConnectionPool(**pool_kwargs)
                
                # 创建Redis客户端
                self._redis_client = redis.Redis(
                    connection_pool=self._connection_pool
                )
                
                # 测试连接
                self._redis_client.ping()
                self._initialized = True
                self.logger.info("Redis connection initialized successfully")

            except Exception as e:
                self.logger.error(f"Failed to initialize Redis: {e}")
                self._redis_client = None
                self._connection_pool = None
                self._initialized = False
                raise

        return self._redis_client
    
    def get_client(self) -> redis.Redis:
        """获取Redis客户端"""
        if self._redis_client is None:
            raise RuntimeError("Redis not initialized. Call init_redis() first.")
        return self._redis_client
    
    def is_connected(self) -> bool:
        """检查Redis连接状态"""
        try:
            if self._redis_client is None:
                return False
            self._redis_client.ping()
            return True
        except Exception as e:
            logging.warning(f"Redis connection check failed: {e}")
            return False

    def close(self):
        """关闭Redis连接"""
        try:
            if self._redis_client:
                self._redis_client.close()
                self.logger.info("Redis client closed")
            if self._connection_pool:
                self._connection_pool.disconnect()
                self.logger.info("Redis connection pool closed")
        except Exception as e:
            self.logger.error(f"Error closing Redis connections: {e}")
        finally:
            self._redis_client = None
            self._connection_pool = None
            self._initialized = False

    # ==================== 优雅的Redis操作方法 ====================

    def set(self, key: str, value: Any, ex: int = None, **kwargs) -> bool:
        """设置键值对 - 自动处理连接"""
        if not self.is_connected():
            self.logger.warning(f"Redis not connected, skipping set operation for key: {key}")
            return False

        try:
            if isinstance(value, (dict, list)):
                import json
                value = json.dumps(value, ensure_ascii=False)

            result = self._redis_client.set(key, value, ex=ex, **kwargs)
            return bool(result)
        except Exception as e:
            self.logger.error(f"Redis set operation failed for key {key}: {e}")
            return False

    def get(self, key: str, default=None) -> Any:
        """获取键值 - 自动处理连接"""
        if not self.is_connected():
            self.logger.warning(f"Redis not connected, returning default for key: {key}")
            return default

        try:
            result = self._redis_client.get(key)
            if result is None:
                return default

            # 尝试解析JSON
            try:
                import json
                return json.loads(result)
            except (json.JSONDecodeError, TypeError):
                return result
        except Exception as e:
            self.logger.error(f"Redis get operation failed for key {key}: {e}")
            return default

    def delete(self, *keys) -> int:
        """删除键 - 自动处理连接"""
        if not self.is_connected():
            self.logger.warning(f"Redis not connected, skipping delete operation for keys: {keys}")
            return 0

        try:
            return self._redis_client.delete(*keys)
        except Exception as e:
            self.logger.error(f"Redis delete operation failed for keys {keys}: {e}")
            return 0

    def exists(self, key: str) -> bool:
        """检查键是否存在 - 自动处理连接"""
        if not self.is_connected():
            return False

        try:
            return bool(self._redis_client.exists(key))
        except Exception as e:
            self.logger.error(f"Redis exists operation failed for key {key}: {e}")
            return False

    def expire(self, key: str, seconds: int) -> bool:
        """设置过期时间 - 自动处理连接"""
        if not self.is_connected():
            self.logger.warning(f"Redis not connected, skipping expire operation for key: {key}")
            return False

        try:
            return bool(self._redis_client.expire(key, seconds))
        except Exception as e:
            self.logger.error(f"Redis expire operation failed for key {key}: {e}")
            return False

    def keys(self, pattern: str = "*") -> list:
        """获取匹配的键列表 - 自动处理连接"""
        if not self.is_connected():
            return []

        try:
            return self._redis_client.keys(pattern)
        except Exception as e:
            self.logger.error(f"Redis keys operation failed for pattern {pattern}: {e}")
            return []

    def incr(self, key: str, amount: int = 1) -> int:
        """递增计数器 - 自动处理连接"""
        if not self.is_connected():
            self.logger.warning(f"Redis not connected, skipping incr operation for key: {key}")
            return 0

        try:
            return self._redis_client.incr(key, amount)
        except Exception as e:
            self.logger.error(f"Redis incr operation failed for key {key}: {e}")
            return 0

    def hset(self, name: str, key: str, value: Any) -> bool:
        """设置哈希字段 - 自动处理连接"""
        if not self.is_connected():
            self.logger.warning(f"Redis not connected, skipping hset operation for {name}:{key}")
            return False

        try:
            if isinstance(value, (dict, list)):
                import json
                value = json.dumps(value, ensure_ascii=False)

            result = self._redis_client.hset(name, key, value)
            return bool(result)
        except Exception as e:
            self.logger.error(f"Redis hset operation failed for {name}:{key}: {e}")
            return False

    def hget(self, name: str, key: str, default=None) -> Any:
        """获取哈希字段 - 自动处理连接"""
        if not self.is_connected():
            return default

        try:
            result = self._redis_client.hget(name, key)
            if result is None:
                return default

            # 尝试解析JSON
            try:
                import json
                return json.loads(result)
            except (json.JSONDecodeError, TypeError):
                return result
        except Exception as e:
            self.logger.error(f"Redis hget operation failed for {name}:{key}: {e}")
            return default
    
    def get_connection_info(self) -> Dict[str, Any]:
        """获取连接池信息"""
        if self._connection_pool is None:
            return {
                "status": "not_initialized",
                "is_connected": False
            }

        try:
            # 安全地获取连接池信息
            pool_info = {
                "status": "initialized",
                "is_connected": self.is_connected(),
                "host": self._config.redis.HOST if self._config else "unknown",
                "port": self._config.redis.PORT if self._config else "unknown",
                "db": self._config.redis.DB if self._config else "unknown",
                "pool_class": self._connection_pool.__class__.__name__
            }

            # 安全地获取连接池统计信息
            if hasattr(self._connection_pool, 'max_connections'):
                pool_info["max_connections"] = self._connection_pool.max_connections

            if hasattr(self._connection_pool, 'created_connections'):
                pool_info["created_connections"] = self._connection_pool.created_connections
            elif hasattr(self._connection_pool, '_created_connections'):
                pool_info["created_connections"] = self._connection_pool._created_connections

            if hasattr(self._connection_pool, '_available_connections'):
                pool_info["available_connections"] = len(self._connection_pool._available_connections)

            if hasattr(self._connection_pool, '_in_use_connections'):
                pool_info["in_use_connections"] = len(self._connection_pool._in_use_connections)

            # 尝试获取其他有用信息
            if hasattr(self._connection_pool, 'connection_kwargs'):
                pool_info["connection_configured"] = True

            return pool_info

        except Exception as e:
            logging.error(f"Failed to get Redis connection info: {e}")
            return {
                "status": "error",
                "error": str(e),
                "is_connected": False
            }
    
    def close_connections(self):
        """关闭所有连接"""
        try:
            if self._connection_pool:
                self._connection_pool.disconnect()
                logging.info("Redis connections closed")
        except Exception as e:
            logging.error(f"Error closing Redis connections: {e}")
        finally:
            self._redis_client = None
            self._connection_pool = None
    
    # ==================== 高级功能 ====================
    
    def set_with_retry(self, key: str, value: Any, ex: Optional[int] = None, retries: int = 3) -> bool:
        """带重试的设置操作"""
        for attempt in range(retries):
            try:
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=False)
                
                result = self._redis_client.set(key, value, ex=ex)
                return bool(result)
            except Exception as e:
                logging.warning(f"Redis set attempt {attempt + 1} failed: {e}")
                if attempt == retries - 1:
                    raise
                time.sleep(0.1 * (attempt + 1))  # 递增延迟
        return False
    
    def get_with_retry(self, key: str, retries: int = 3) -> Optional[Any]:
        """带重试的获取操作"""
        for attempt in range(retries):
            try:
                value = self._redis_client.get(key)
                if value is None:
                    return None
                
                # 尝试解析JSON
                try:
                    return json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    return value
            except Exception as e:
                logging.warning(f"Redis get attempt {attempt + 1} failed: {e}")
                if attempt == retries - 1:
                    raise
                time.sleep(0.1 * (attempt + 1))
        return None
    
    def delete_with_retry(self, key: str, retries: int = 3) -> bool:
        """带重试的删除操作"""
        for attempt in range(retries):
            try:
                result = self._redis_client.delete(key)
                return bool(result)
            except Exception as e:
                logging.warning(f"Redis delete attempt {attempt + 1} failed: {e}")
                if attempt == retries - 1:
                    raise
                time.sleep(0.1 * (attempt + 1))
        return False
    
    def exists_with_retry(self, key: str, retries: int = 3) -> bool:
        """带重试的存在检查"""
        for attempt in range(retries):
            try:
                result = self._redis_client.exists(key)
                return bool(result)
            except Exception as e:
                logging.warning(f"Redis exists attempt {attempt + 1} failed: {e}")
                if attempt == retries - 1:
                    raise
                time.sleep(0.1 * (attempt + 1))
        return False
    
    # ==================== 业务相关的便捷方法 ====================
    
    def _get_prefix(self) -> str:
        """获取Redis键前缀"""
        try:
            config = get_config()
            return config.redis.PREFIX
        except:
            return "zhpt:"  # 默认前缀

    def set_user_token(self, token: str, user_data: dict, expire_seconds: int = 7200) -> bool:
        """设置用户token"""
        key = f"{self._get_prefix()}user:{token}"
        return self.set_with_retry(key, user_data, ex=expire_seconds)

    def get_user_token(self, token: str) -> Optional[dict]:
        """获取用户token数据"""
        key = f"{self._get_prefix()}user:{token}"
        return self.get_with_retry(key)

    def delete_user_token(self, token: str) -> bool:
        """删除用户token"""
        key = f"{self._get_prefix()}user:{token}"
        return self.delete_with_retry(key)

    def set_verify_code(self, phone: str, code: str, expire_seconds: int = 300) -> bool:
        """设置验证码"""
        key = f"{self._get_prefix()}verify_code:{phone}"
        return self.set_with_retry(key, code, ex=expire_seconds)

    def get_verify_code(self, phone: str) -> Optional[str]:
        """获取验证码"""
        key = f"{self._get_prefix()}verify_code:{phone}"
        return self.get_with_retry(key)

    def delete_verify_code(self, phone: str) -> bool:
        """删除验证码"""
        key = f"{self._get_prefix()}verify_code:{phone}"
        return self.delete_with_retry(key)

# 全局Redis管理器实例
redis_manager = RedisManager()


# ==================== 缓存装饰器 ====================

def cache_result(key_prefix: str, expire_seconds: int = 300):
    """
    缓存装饰器 - 自动缓存函数结果

    使用示例:
    @cache_result("student_info", expire_seconds=600)
    async def get_student_info(student_id: str):
        # 函数逻辑
        return student_data
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # 生成缓存键
            import hashlib
            import json

            # 将参数转换为字符串用于生成键
            args_str = json.dumps([str(arg) for arg in args], sort_keys=True)
            kwargs_str = json.dumps(kwargs, sort_keys=True, default=str)
            params_hash = hashlib.md5(f"{args_str}{kwargs_str}".encode()).hexdigest()[:8]

            cache_key = f"{key_prefix}:{params_hash}"

            # 尝试从缓存获取
            cached_result = redis_manager.get(cache_key)
            if cached_result is not None:
                return cached_result

            # 执行函数并缓存结果
            result = await func(*args, **kwargs)
            redis_manager.set(cache_key, result, ex=expire_seconds)

            return result
        return wrapper
    return decorator


def cache_invalidate(key_patterns: list):
    """
    缓存失效装饰器 - 自动清除相关缓存

    使用示例:
    @cache_invalidate(["student_info:*", "class_info:*"])
    async def update_student(student_id: str, data: dict):
        # 更新逻辑
        pass
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # 执行函数
            result = await func(*args, **kwargs)

            # 清除相关缓存
            for pattern in key_patterns:
                keys_to_delete = redis_manager.keys(pattern)
                if keys_to_delete:
                    redis_manager.delete(*keys_to_delete)

            return result
        return wrapper
    return decorator


# ==================== 便捷函数 ====================

def cache_student_info(student_id: str, data: dict, expire_seconds: int = 600) -> bool:
    """缓存学生信息"""
    return redis_manager.set(f"student:info:{student_id}", data, ex=expire_seconds)


def get_cached_student_info(student_id: str) -> dict:
    """获取缓存的学生信息"""
    return redis_manager.get(f"student:info:{student_id}", {})


def cache_class_info(class_id: int, data: dict, expire_seconds: int = 1800) -> bool:
    """缓存班级信息"""
    return redis_manager.set(f"class:info:{class_id}", data, ex=expire_seconds)


def get_cached_class_info(class_id: int) -> dict:
    """获取缓存的班级信息"""
    return redis_manager.get(f"class:info:{class_id}", {})


def invalidate_student_cache(student_id: str) -> int:
    """清除学生相关缓存"""
    patterns = [
        f"student:info:{student_id}",
        f"student:*:{student_id}",
        f"*:student:{student_id}:*"
    ]

    keys_to_delete = []
    for pattern in patterns:
        keys_to_delete.extend(redis_manager.keys(pattern))

    return redis_manager.delete(*keys_to_delete) if keys_to_delete else 0


def invalidate_class_cache(class_id: int) -> int:
    """清除班级相关缓存"""
    patterns = [
        f"class:info:{class_id}",
        f"class:*:{class_id}",
        f"*:class:{class_id}:*"
    ]

    keys_to_delete = []
    for pattern in patterns:
        keys_to_delete.extend(redis_manager.keys(pattern))

    return redis_manager.delete(*keys_to_delete) if keys_to_delete else 0


# 兼容性函数
def get_redis_client() -> redis.Redis:
    """获取Redis客户端（兼容性函数）"""
    return redis_manager.get_client()


def init_redis(config_name='default') -> redis.Redis:
    """初始化Redis（兼容性函数）"""
    return redis_manager.init_redis(config_name)
