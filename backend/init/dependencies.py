from fastapi import Request, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Generator, Dict, Any
import logging
import redis

# 导入数据库管理器
from init.database_optimized import db_manager

# 导入认证相关
from common.auth import verify_token_for_dependencies

# HTTP Bearer 认证
security = HTTPBearer()


"""
FastAPI 通用依赖管理模块
统一管理所有控制器需要的依赖函数
"""


# ==================== 数据库依赖 ====================

async def get_db() -> Generator[Session, None, None]:
    """
    获取数据库会话依赖
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

def get_db_sync() -> Session:
    """
    获取同步数据库会话（用于非FastAPI场景）
    注意：需要手动管理会话生命周期
    """
    return db_manager.get_session()

# ==================== Redis依赖 ====================

def get_redis(request: Request = None) -> redis.Redis:
    """
    获取Redis连接
    优先使用Redis管理器，fallback到request.app.redis
    """
    try:
        from init.redis_manager import redis_manager
        if redis_manager.is_initialized:
            return redis_manager.get_client()
        else:
            # 尝试初始化Redis
            try:
                redis_client = redis_manager.init_redis()
                return redis_client
            except Exception as e:
                logging.warning(f"Redis初始化失败: {str(e)}")
                return None
    except Exception as e:
        logging.warning(f"Redis管理器异常: {str(e)}")
        # Fallback到原有方式（如果Redis管理器未初始化）
        if request and hasattr(request.app, 'redis'):
            return request.app.redis
        return None  # 返回None而不是抛出异常

def get_redis_sync() -> redis.Redis:
    """
    获取同步Redis连接（用于非FastAPI场景）
    使用优化的Redis管理器
    """
    from init.redis_manager import redis_manager
    return redis_manager.get_client()

def get_redis_manager():
    """获取Redis管理器实例"""
    from init.redis_manager import redis_manager
    return redis_manager

# ==================== 认证依赖（被部分模块直接引用） ====================

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """
    获取当前用户信息
    验证JWT token并返回用户信息
    """
    token = credentials.credentials
    try:
        payload = verify_token_for_dependencies(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Token validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 验证失败",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def get_admin_user(current_user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """获取管理员用户"""
    if not current_user.get("is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user

# ==================== 工具函数 ====================

def get_user_student_no(current_user: dict) -> str:
    """
    从用户信息中提取学号
    统一处理不同字段名的情况
    """
    student_no = current_user.get('username') or current_user.get('xs_xh') or current_user.get('student_no')
    if not student_no:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无法获取学生学号"
        )
    return student_no

def get_user_teacher_id(current_user: dict) -> int:
    """
    从用户信息中提取教师ID
    """
    teacher_id = current_user.get('user_id') or current_user.get('t_id') or current_user.get('teacher_id')
    if not teacher_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无法获取教师ID"
        )
    return int(teacher_id)


# ==================== 导出常用依赖 ====================

# 为了方便导入，提供一些别名
DatabaseDep = Depends(get_db)
RedisDep = Depends(get_redis)
RedisManagerDep = Depends(get_redis_manager)
AdminUserDep = Depends(get_admin_user)
