"""
优化的数据库管理方案
"""

from sqlalchemy import create_engine, event, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, scoped_session
from sqlalchemy.pool import QueuePool
from init.config import get_config
import logging
from contextlib import contextmanager
from typing import Generator

# 创建基础模型类
Base = declarative_base()

class DatabaseManager:
    """优化的数据库管理器"""
    
    _instance = None
    _engine = None
    _session_factory = None
    _scoped_session = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
        return cls._instance
    
    def init_db(self, config_name='development'):
        """初始化数据库连接"""
        if self._engine is None:
            app_config = get_config(config_name)
            db_config = app_config.database

            # 基础引擎配置
            engine_options = {
                # 连接池配置
                'poolclass': QueuePool,
                'echo': False,             # 禁用SQL日志以提升性能
                'echo_pool': False,        # 连接池日志
                'future': True,            # 使用SQLAlchemy 2.0风格
            }

            # 优先使用数据库特定的引擎配置，否则使用优化的默认配置
            if hasattr(db_config, 'SQLALCHEMY_ENGINE_OPTIONS'):
                # 使用配置文件中的设置
                engine_options.update(db_config.SQLALCHEMY_ENGINE_OPTIONS)
                logging.info("Using database-specific engine options from config")
            else:
                # 使用优化的默认配置
                default_options = {
                    'pool_size': 15,          # 连接池大小（与config.py保持一致）
                    'max_overflow': 25,       # 最大溢出连接数（与config.py保持一致）
                    'pool_pre_ping': True,    # 连接前ping检查
                    'pool_recycle': 1800,     # 连接回收时间(30分钟，与config.py保持一致)
                    'pool_timeout': 20,       # 获取连接超时时间（与config.py保持一致）
                }
                engine_options.update(default_options)
                logging.info("Using optimized default engine options")

            self._engine = create_engine(
                db_config.SQLALCHEMY_DATABASE_URI,
                **engine_options
            )
            
            # 创建会话工厂
            self._session_factory = sessionmaker(
                bind=self._engine,
                autocommit=False,
                autoflush=False,
                expire_on_commit=False
            )
            
            # 创建线程安全的scoped_session
            self._scoped_session = scoped_session(self._session_factory)
            
            # 添加连接池事件监听
            self._setup_engine_events()

            # 设置智能 SQL 日志记录
            self._setup_sql_logging()

            logging.info("Database initialized successfully")
            
        return self._engine
    
    def _setup_engine_events(self):
        """设置引擎事件监听"""
        
        @event.listens_for(self._engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            """SQLite特殊配置（如果使用SQLite）"""
            if 'sqlite' in str(self._engine.url):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()
        
        @event.listens_for(self._engine, "checkout")
        def receive_checkout(dbapi_connection, connection_record, connection_proxy):
            """连接检出时的处理"""
            logging.debug("Connection checked out from pool")
        
        @event.listens_for(self._engine, "checkin")
        def receive_checkin(dbapi_connection, connection_record):
            """连接归还时的处理"""
            logging.debug("Connection checked in to pool")

    def _setup_sql_logging(self):
        """设置智能 SQL 日志记录"""
        try:
            from utils.sql_logger import setup_smart_sql_logging
            import os
            environment = os.getenv('FASTAPI_ENV', 'development')
            setup_smart_sql_logging(self._engine, environment)
            logging.info(f"✅ Smart SQL logging configured for {environment}")
        except ImportError:
            logging.warning("⚠️ SQL logger not available, SQL logging disabled for performance")
        except Exception as e:
            logging.error(f"❌ Failed to setup SQL logging: {e}")

    def enable_sql_debug(self):
        """临时启用 SQL 调试日志"""
        try:
            from utils.sql_logger import enable_debug_sql_logging
            enable_debug_sql_logging()
            logging.info("✅ SQL debug logging enabled")
        except ImportError:
            logging.warning("⚠️ SQL logger not available")

    def disable_sql_logging(self):
        """禁用 SQL 日志"""
        try:
            from utils.sql_logger import disable_sql_logging
            disable_sql_logging()
            logging.info("✅ SQL logging disabled")
        except ImportError:
            logging.warning("⚠️ SQL logger not available")

    def get_sql_stats(self):
        """获取 SQL 统计信息"""
        try:
            from utils.sql_logger import get_sql_stats
            return get_sql_stats()
        except ImportError:
            return {"error": "SQL logger not available"}
    
    def get_session(self) -> Session:
        """获取数据库会话（非scoped）"""
        if self._session_factory is None:
            raise RuntimeError("Database not initialized. Call init_db() first.")
        return self._session_factory()
    
    def get_scoped_session(self):
        """获取线程安全的scoped session"""
        if self._scoped_session is None:
            raise RuntimeError("Database not initialized. Call init_db() first.")
        return self._scoped_session
    
    @contextmanager
    def get_db_session(self) -> Generator[Session, None, None]:
        """上下文管理器方式获取会话，自动处理事务"""
        session = self.get_session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logging.error(f"Database transaction failed: {e}")
            raise
        finally:
            session.close()
    
    def create_all(self):
        """创建所有表"""
        if self._engine is None:
            raise RuntimeError("Database not initialized. Call init_db() first.")
        Base.metadata.create_all(self._engine)
    
    def drop_all(self):
        """删除所有表（谨慎使用）"""
        if self._engine is None:
            raise RuntimeError("Database not initialized. Call init_db() first.")
        Base.metadata.drop_all(self._engine)
    
    def get_engine_info(self):
        """获取引擎信息"""
        if self._engine is None:
            return None

        try:
            pool = self._engine.pool
            info = {
                'url': str(self._engine.url),
                'pool_class': pool.__class__.__name__,
                'pool_size': getattr(pool, 'size', lambda: 0)(),
                'checked_in': getattr(pool, 'checkedin', lambda: 0)(),
                'checked_out': getattr(pool, 'checkedout', lambda: 0)(),
                'overflow': getattr(pool, 'overflow', lambda: 0)()
            }

            # 添加可用的额外信息
            if hasattr(pool, 'invalidated'):
                info["invalidated_count"] = len(pool.invalidated)

            return info
        except Exception as e:
            return {
                'url': str(self._engine.url),
                'error': f'Failed to get pool info: {str(e)}'
            }

    def get_connection_info(self):
        """获取连接信息（兼容性方法）"""
        try:
            if self._engine is None:
                return {
                    "status": "not_initialized",
                    "connected": False
                }

            # 测试连接
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                connected = True
        except Exception as e:
            connected = False
            logging.error(f"Database connection test failed: {e}")

        # 获取连接池信息（安全方式）
        pool_info = None
        if self._engine:
            try:
                pool = self._engine.pool
                pool_info = {
                    "size": getattr(pool, 'size', lambda: 0)(),
                    "checked_in": getattr(pool, 'checkedin', lambda: 0)(),
                    "checked_out": getattr(pool, 'checkedout', lambda: 0)(),
                    "overflow": getattr(pool, 'overflow', lambda: 0)(),
                    "pool_class": pool.__class__.__name__
                }

                # 添加可用的额外信息
                if hasattr(pool, 'invalidated'):
                    pool_info["invalidated"] = len(pool.invalidated)
                if hasattr(pool, '_creator'):
                    pool_info["has_creator"] = True

            except Exception as e:
                pool_info = {"error": f"Failed to get pool info: {str(e)}"}

        return {
            "status": "initialized" if self._engine else "not_initialized",
            "connected": connected,
            "url": str(self._engine.url).split('@')[-1] if self._engine else None,  # 隐藏密码
            "pool_info": pool_info
        }
    
    def close_all_sessions(self):
        """关闭所有会话"""
        if self._scoped_session:
            self._scoped_session.remove()
    
    def dispose_engine(self):
        """销毁引擎和连接池"""
        if self._engine:
            self._engine.dispose()
            self._engine = None
            self._session_factory = None
            self._scoped_session = None

# 全局数据库管理器实例
db_manager = DatabaseManager()

# FastAPI依赖函数
async def get_db() -> Generator[Session, None, None]:
    """
    FastAPI依赖：获取数据库会话
    自动处理事务提交/回滚和会话关闭
    """
    session = db_manager.get_session()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logging.error(f"Database session error: {e}")
        raise
    finally:
        session.close()

# 同步上下文管理器
def get_db_context():
    """
    同步代码使用的数据库会话上下文管理器
    """
    return db_manager.get_db_session()

# 装饰器方式的事务管理
def transactional(func):
    """
    事务装饰器，自动处理事务
    """
    def wrapper(*args, **kwargs):
        with get_db_context() as session:
            # 将session注入到函数参数中
            if 'session' not in kwargs:
                kwargs['session'] = session
            return func(*args, **kwargs)
    return wrapper



# 兼容性别名
database = db_manager
