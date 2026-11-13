import os
from typing import Dict, Any
from dataclasses import dataclass


@dataclass
class AppConfig:
    """应用基础配置"""
    HOST: str = 'localhost'
    PORT: int = 3050
    DEBUG: bool = False


@dataclass
class JWTConfig:
    """JWT认证配置"""
    SECRET_KEY: str = os.getenv('JWT_SECRET_KEY', 'salt.qdnkd.cn@qdndd')
    ALGORITHM: str = 'HS256'
    ACCESS_TOKEN_EXPIRES: int = 3600 * 2  # 2小时


@dataclass
class RedisConfig:
    """Redis缓存配置"""
    HOST: str = os.getenv('REDIS_HOST', '172.16.100.102')
    PORT: int = int(os.getenv('REDIS_PORT', '6379'))
    DB: int = int(os.getenv('REDIS_DB', '0'))
    PASSWORD: str = os.getenv('REDIS_PASSWORD', 'Skh@1234')
    PREFIX: str = 'zhpt:'  # 项目前缀，避免键名冲突
    EXPIRE: int = 7200  # 默认过期时间（2小时）


@dataclass
class DatabaseConfig:
    """数据库配置"""
    HOST: str = os.getenv('DB_HOST', '172.16.100.101')
    PORT: str = os.getenv('DB_PORT', '1433')
    USER: str = os.getenv('DB_USER', 'zhxt')
    PASSWORD: str = os.getenv('DB_PASSWORD', 'Skh@1234')
    DATABASE: str = os.getenv('DB_DATABASE', 'OA')
    CHARSET: str = os.getenv('DB_CHARSET', 'GBK')

    @property
    def DB_PARAMS(self) -> dict:
        """ODBC连接参数"""
        return {
            'DRIVER': '{ODBC Driver 17 for SQL Server}',  # 使用完整的驱动名称
            'SERVER': self.HOST,
            'DATABASE': self.DATABASE,
            'UID': self.USER,
            'PWD': self.PASSWORD,
            'TrustServerCertificate': 'yes'
        }

    @property
    def DB_CONN_STR(self) -> str:
        """构建连接字符串"""
        import urllib.parse
        return ';'.join(f"{key}={value}" for key, value in self.DB_PARAMS.items())

    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        """SQLAlchemy 数据库连接字符串"""
        import urllib.parse
        return f"mssql+pyodbc:///?odbc_connect={urllib.parse.quote_plus(self.DB_CONN_STR)}"

    @property
    def SQLALCHEMY_ENGINE_OPTIONS(self) -> dict:
        """SQLAlchemy配置 - 高并发优化"""
        return {
            'pool_pre_ping': True,  # 自动检测断开的连接
            'pool_recycle': 1800,   # 30分钟后回收连接（减少超时）
            'pool_timeout': 30,     # 获取连接超时时间（增加到30秒）
            'pool_size': 30,        # 连接池大小（从15增加到30）
            'max_overflow': 50,     # 最大溢出连接数（从25增加到50）
            'connect_args': {
                'timeout': 15,      # 连接超时时间
                'login_timeout': 10, # 登录超时
            }
        }


@dataclass
class WeChatConfig:
    """微信小程序配置"""
    # 从环境变量获取，如果没有则使用默认值（开发环境）
    APP_ID: str = os.getenv('WECHAT_APP_ID', 'wxe8f312724bfb12f0')
    APP_SECRET: str = os.getenv('WECHAT_APP_SECRET', '0175cc4b75d631412dcc94bcf88e9f70')

    # 微信支付配置
    MCH_ID: str = os.getenv('WX_MCH_ID', '1601457680')
    SERIAL_NO: str = os.getenv('WX_SERIAL_NO', '7DCE517ADBA4ECEBB13109C0576D3746ACE24178')
    APIv3_KEY: str = os.getenv('WX_APIv3_KEY', 'iiF4Lo7wSeDLlD1EQoc00Im4WnwYsggz')  # APIv3密钥，用于解密回调数据
    PLATFORM_SERIAL_NO: str = os.getenv('WX_PLATFORM_SERIAL_NO', '4446B03EC42569E2E4C21A43079CC2688EDFD6E2')  # 微信平台证书序列号

    # 回调URL模板，{table_name} 会替换为实际的表名
    NOTIFY_URL_TEMPLATE: str = os.getenv('WX_NOTIFY_URL_TEMPLATE', 'https://m.qdndd.com.cn/wxpay/callback/{table_name}')
    # 兼容旧版本
    NOTIFY_URL: str = os.getenv('WX_NOTIFY_URL', 'https://m.qdndd.com.cn/wxpay/callback/wx_payinfo')

    # 微信平台证书路径（用于验签）
    PLATFORM_CERT_PATH: str = os.getenv('WX_PLATFORM_CERT_PATH', 'wechatpay_4446B03EC42569E2E4C21A43079CC2688EDFD6E2.pem')

    # 微信API地址
    LOGIN_URL: str = 'https://api.weixin.qq.com/sns/jscode2session'
    PAY_URL: str = 'https://api.mch.weixin.qq.com/v3/pay/transactions/jsapi'

    # openid hash salt: SHA256(openid + salt)，用于问卷匿名存储
    OPENID_HASH_SALT: str = os.getenv('WX_OPENID_HASH_SALT', 'zhpt_openid_salt_2026')


class Config:
    """基础配置类 - 整合所有配置模块"""

    def __init__(self):
        self.app = AppConfig()
        self.jwt = JWTConfig()
        self.redis = RedisConfig()
        self.database = DatabaseConfig()
        self.wechat = WeChatConfig()

class DevelopmentConfig(Config):
    """开发环境配置"""

    def __init__(self):
        super().__init__()
        # 覆盖开发环境特定配置
        self.app.DEBUG = True
        self.app.HOST = '0.0.0.0'  # 监听所有接口
        self.app.PORT = 3050  # 开发环境端口


class ProductionConfig(Config):
    """生产环境配置"""

    def __init__(self):
        super().__init__()
        # 覆盖生产环境特定配置
        self.app.DEBUG = False
        self.app.HOST = '0.0.0.0'  # 监听所有接口
        self.app.PORT = 3050  # 生产环境端口

        # 生产环境配置检查和警告
        # 检查是否使用了默认的数据库配置
        if (self.database.HOST == '172.16.100.101' and
            self.database.USER == 'zhxt' and
            self.database.DATABASE == 'OA'):
            print("⚠️  警告: 正在使用默认数据库配置，生产环境建议设置环境变量:")
            print("   export DB_HOST=your_database_host")
            print("   export DB_USER=your_database_user")
            print("   export DB_PASSWORD=your_database_password")
            print("   export DB_DATABASE=your_database_name")

        # 检查是否使用了默认的JWT密钥
        if self.jwt.SECRET_KEY == 'salt.qdnkd.cn@qdndd':
            print("⚠️  警告: 正在使用默认JWT密钥，生产环境建议设置:")
            print("   export JWT_SECRET_KEY=your_secure_jwt_secret_key")

        # 检查是否使用了默认的微信配置
        if (self.wechat.APP_ID == 'wxe8f312724bfb12f0' and
            self.wechat.APP_SECRET == '0175cc4b75d631412dcc94bcf88e9f70'):
            print("⚠️  警告: 正在使用默认微信配置，生产环境建议设置:")
            print("   export WECHAT_APP_ID=your_wechat_app_id")
            print("   export WECHAT_APP_SECRET=your_wechat_app_secret")


# 配置工厂
CONFIG_MAPPING = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}

# 配置字典（用于database_optimized.py）
# 延迟初始化，避免在模块加载时检查环境变量
config = {}


def get_config(config_name: str = None) -> Config:
    """
    获取配置对象

    Args:
        config_name: 配置环境名称 ('development', 'production')
                    如果为None，则从环境变量FASTAPI_ENV获取，默认为'development'

    Returns:
        Config: 配置对象实例
    """
    if config_name is None:
        config_name = os.getenv('FASTAPI_ENV', 'development')

    config_class = CONFIG_MAPPING.get(config_name, CONFIG_MAPPING['default'])
    return config_class()


def get_redis_config(config_name: str = None) -> Dict[str, Any]:
    """
    获取Redis连接配置

    Args:
        config_name: 配置环境名称

    Returns:
        Dict[str, Any]: Redis连接配置字典
    """
    cfg = get_config(config_name)

    redis_config = {
        "host": cfg.redis.HOST,
        "port": cfg.redis.PORT,
        "db": cfg.redis.DB,
        "decode_responses": True,
        "encoding": "utf-8",
        "max_connections": 50,
        "retry_on_timeout": True,
        "socket_timeout": 5,
        "socket_connect_timeout": 5,
        "socket_keepalive": True,
        "health_check_interval": 30,
    }

    # 只有当密码不为空时才添加密码配置
    if cfg.redis.PASSWORD:
        redis_config["password"] = cfg.redis.PASSWORD

    return redis_config


# ==================== 便捷访问函数 ====================

def get_app_config(config_name: str = None) -> AppConfig:
    """获取应用配置"""
    return get_config(config_name).app


def get_jwt_config(config_name: str = None) -> JWTConfig:
    """获取JWT配置"""
    return get_config(config_name).jwt


def get_database_config(config_name: str = None) -> DatabaseConfig:
    """获取数据库配置"""
    return get_config(config_name).database


def get_wechat_config(config_name: str = None) -> WeChatConfig:
    """获取微信配置"""
    return get_config(config_name).wechat


