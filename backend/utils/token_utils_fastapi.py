"""
FastAPI兼容的Token工具类
"""

from functools import wraps
from fastapi import Request, HTTPException, Depends
import jwt
import time
from models.models import Student, ZzXs
from models.common_models import UserInfo
from sqlalchemy.orm import Session

class TokenUtils:
    # Token配置
    TOKEN_EXPIRE_SECONDS = 3600 * 60  # token有效时间 2小时
    TOKEN_SECRET_SALT = 'salt.qdnkd.cn@qdndd'
    TOKEN_ALGORITHM = 'HS256'

    # 生成token
    @staticmethod
    def generate_token(payload: dict) -> str:
        """
        生成token
        
        Args:
            payload: 用户信息，例如：{'user_id': '123', 'username': 'test'}
            
        Returns:
            str: 生成的token
        """
        # 添加过期时间到payload
        payload['exp'] = int(time.time()) + TokenUtils.TOKEN_EXPIRE_SECONDS
        print("payload:", payload)
        # 生成token
        token = jwt.encode(payload, TokenUtils.TOKEN_SECRET_SALT, algorithm=TokenUtils.TOKEN_ALGORITHM)
        return token

    # 验证token
    @staticmethod
    def verify_token(token: str) -> tuple:
        """
        验证token
        
        Args:
            token: 要验证的token
            
        Returns:
            tuple: (is_valid: bool, payload: dict)
        """
        try:
            # 解码token
            payload = jwt.decode(token, TokenUtils.TOKEN_SECRET_SALT, algorithms=[TokenUtils.TOKEN_ALGORITHM])
            
            # 检查是否过期
            if payload.get('exp', 0) < int(time.time()):
                return False, None
                
            return True, payload
        except jwt.ExpiredSignatureError:
            return False, None
        except jwt.InvalidTokenError:
            return False, None
        except Exception as e:
            print(f"Token验证异常: {e}")
            return False, None

    @staticmethod
    def basic_token_required(func):
        """
        基础token验证装饰器 - FastAPI版本
        只验证token的有效性
        """
        async def wrapper(*args, request: Request, **kwargs):
            token = request.headers.get('token')
            if not token:
                raise HTTPException(status_code=401, detail={'code': 401, 'msg': '缺少token', 'data': None})

            is_valid, _ = TokenUtils.verify_token(token)
            if not is_valid:
                raise HTTPException(status_code=401, detail={'code': 401, 'msg': 'token无效或已过期', 'data': None})
            
            return await func(*args, request=request, **kwargs)
        return wrapper

    @staticmethod
    def user_token_required(func):
        """
        用户token验证装饰器 - FastAPI版本
        验证token并获取用户信息
        """
        async def wrapper(*args, request: Request, db: Session, **kwargs):
            token = request.headers.get('token')
            if not token:
                raise HTTPException(status_code=401, detail={'code': 401, 'msg': '缺少token', 'data': None})
            
            try:
                is_valid, user_info = TokenUtils.verify_token(token)
                if not is_valid:
                    raise HTTPException(status_code=401, detail={'code': 401, 'msg': 'token无效或已过期', 'data': None})
                
                return await func(*args, user_info=user_info, request=request, db=db, **kwargs)
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail={'code': 500, 'msg': f'验证token时发生错误: {str(e)}', 'data': None})
        return wrapper

    @staticmethod
    def zz_user_token_required(func):
        """
        中职用户token验证装饰器 - FastAPI版本
        验证token并获取用户信息
        """
        async def wrapper(*args, request: Request, db: Session, **kwargs):
            token = request.headers.get('token')
            if not token:
                raise HTTPException(status_code=401, detail={'code': 401, 'msg': '缺少token', 'data': None})
            
            try:
                is_valid, _ = TokenUtils.verify_token(token)
                if not is_valid:
                    raise HTTPException(status_code=401, detail={'code': 401, 'msg': 'token无效或已过期', 'data': None})
                
                redis_key = f"zhpt:user:{token}"
                redis_client = request.app.redis
                token_payload = redis_client.hgetall(redis_key)
                if not token_payload:
                    raise HTTPException(status_code=401, detail={'code': 401, 'msg': 'redis中不存在该token，请重新登录', 'data': None})
                
                user_xs = db.query(ZzXs).filter(ZzXs.xh == token_payload['xs_xh']).first()
                if not user_xs:
                    raise HTTPException(status_code=401, detail={'code': 401, 'msg': 'redis中用户学号错误，请重新登录', 'data': None})
                
                return await func(*args, user_info=user_xs, request=request, db=db, **kwargs)
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail={'code': 500, 'msg': f'验证token时发生错误: {str(e)}', 'data': None})
        return wrapper

    @staticmethod
    def create_user_token(user_info: dict, redis_client=None) -> str:
        """
        创建用户token并存储到Redis
        
        Args:
            user_info: 用户信息字典
            redis_client: Redis客户端
            
        Returns:
            str: 生成的token
        """
        # 生成token
        token = TokenUtils.generate_token(user_info)
        
        # 如果提供了Redis客户端，存储token信息
        if redis_client:
            redis_key = f"zhpt:user:{token}"
            # 设置token过期时间（与JWT过期时间一致）
            redis_client.hset(redis_key, mapping=user_info)
            redis_client.expire(redis_key, TokenUtils.TOKEN_EXPIRE_SECONDS)
        
        return token

    @staticmethod
    def delete_user_token(token: str, redis_client=None) -> bool:
        """
        删除用户token
        
        Args:
            token: 要删除的token
            redis_client: Redis客户端
            
        Returns:
            bool: 删除是否成功
        """
        if not redis_client:
            return False
            
        try:
            redis_key = f"zhpt:user:{token}"
            result = redis_client.delete(redis_key)
            return result > 0
        except Exception as e:
            print(f"删除token失败: {e}")
            return False
