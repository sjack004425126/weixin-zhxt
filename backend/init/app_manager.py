"""
应用管理器 - 统一管理数据库和Redis初始化
"""

import logging
import asyncio
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager

from init.redis_manager import redis_manager
from init.database_optimized import db_manager
from init.config import get_config


class AppManager:
    """统一应用管理器 - 管理数据库和Redis"""

    _instance = None
    _initialized = False
    _config_name = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AppManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_init_done'):
            self._init_done = True
            self.logger = logging.getLogger(__name__)

    async def initialize(self, config_name: str = 'development') -> bool:
        """初始化所有服务"""
        if self._initialized:
            self.logger.info("App manager already initialized")
            return True

        self._config_name = config_name
        config = get_config(config_name)

        self.logger.info(f"Initializing application services with config: {config_name}")

        # 初始化数据库连接（由main.py中的lifespan完成）
        self.logger.info("✅ Database manager initialized")

        # 初始化Redis（可选）
        try:
            redis_client = redis_manager.init_redis(config_name)
            if redis_client:
                self.logger.info("✅ Redis initialized successfully")
            else:
                self.logger.warning("⚠️  Redis initialization failed, continuing without Redis")
        except Exception as e:
            self.logger.error(f"❌ Redis initialization error: {e}")
            self.logger.warning("⚠️  Application will continue without Redis")

        self._initialized = True
        self.logger.info("🎉 Application services initialized successfully")

        return True
    
    async def shutdown(self):
        """关闭应用服务（数据库和Redis）"""
        if not self._initialized:
            return

        logging.info("Shutting down application services...")

        # 关闭Redis连接
        try:
            redis_manager.close()
            logging.info("✅ Redis connections closed")
        except Exception as e:
            logging.error(f"❌ Error closing Redis: {e}")

        self._initialized = False
        logging.info("🔚 Application shutdown completed")
    
    async def get_health_status(self) -> Dict[str, Any]:
        """获取应用健康状态"""
        if not self._initialized:
            return {
                "status": "unhealthy",
                "reason": "not_initialized",
                "services": {}
            }

        services = {}
        overall_healthy = True

        # 检查数据库状态
        try:
            db_info = db_manager.get_connection_info()
            services["database"] = db_info
            if db_info.get("status") != "connected":
                overall_healthy = False
        except Exception as e:
            services["database"] = {"status": "error", "error": str(e)}
            overall_healthy = False

        # 检查Redis状态
        try:
            redis_info = redis_manager.get_connection_info()
            services["redis"] = redis_info
            # Redis不是必需的，所以不影响整体健康状态
        except Exception as e:
            services["redis"] = {"status": "error", "error": str(e)}

        return {
            "status": "healthy" if overall_healthy else "unhealthy",
            "config": self._config_name,
            "services": services
        }
    
    async def get_detailed_status(self) -> Dict[str, Any]:
        """获取详细状态信息"""
        basic_status = await self.get_health_status()

        # 添加Redis连接信息
        try:
            redis_info = redis_manager.get_connection_info()
            basic_status["redis_info"] = redis_info
        except Exception as e:
            basic_status["redis_info"] = {"error": str(e)}

        return basic_status
    
    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._initialized
    
    def get_config_name(self) -> Optional[str]:
        """获取当前配置名称"""
        return self._config_name
    
    def get_db_manager(self):
        """获取数据库管理器"""
        return db_manager

    def get_redis_manager(self):
        """获取Redis管理器"""
        return redis_manager


# 创建全局实例
app_manager = AppManager()


# FastAPI生命周期管理
@asynccontextmanager
async def lifespan(app, config_name: str = 'development'):
    """FastAPI应用生命周期管理"""
    # 启动时初始化
    success = await app_manager.initialize(config_name)
    if not success:
        logging.error("Failed to initialize application")
        # 可以选择是否继续启动
        # raise RuntimeError("Application initialization failed")
    
    # 将管理器实例添加到app状态中
    app.state.app_manager = app_manager
    app.state.db_manager = db_manager
    app.state.redis_manager = redis_manager
    
    yield
    
    # 关闭时清理
    await app_manager.shutdown()


# 依赖注入函数
def get_app_manager() -> AppManager:
    """获取应用管理器 - 用于依赖注入"""
    return app_manager


def get_db_manager():
    """获取数据库管理器 - 用于依赖注入"""
    return db_manager


def get_redis_manager():
    """获取Redis管理器 - 用于依赖注入"""
    return redis_manager


def get_redis_client():
    """获取Redis客户端 - 用于依赖注入（兼容性）"""
    return redis_manager.get_client()


def get_redis() -> 'RedisManager':
    """获取Redis管理器 - 推荐的依赖注入方式"""
    return redis_manager


# 装饰器
def require_services(*services):
    """装饰器：确保指定服务可用"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            if not app_manager.is_initialized():
                raise RuntimeError("Application services not initialized")

            # 检查特定服务
            if 'database' in services:
                db_info = db_manager.get_connection_info()
                if not db_info.get("connected", False):
                    raise RuntimeError("Database service not available")

            if 'redis' in services and not redis_manager.is_connected():
                raise RuntimeError("Redis service not available")

            return await func(*args, **kwargs)
        return wrapper
    return decorator
