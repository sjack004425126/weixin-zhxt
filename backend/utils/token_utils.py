from functools import wraps
from flask import request, jsonify, current_app
import jwt
import time
from models.models import Student,ZzXs
from models.common_models import UserInfo

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
        token = jwt.encode(
            payload, 
            TokenUtils.TOKEN_SECRET_SALT, 
            algorithm=TokenUtils.TOKEN_ALGORITHM
        )
        return token

    # 验证token
    @staticmethod
    def verify_token(token: str) -> tuple[bool, dict]:
        try:
            # 解码并验证token
            payload = jwt.decode(
                token, 
                TokenUtils.TOKEN_SECRET_SALT, 
                algorithms=[TokenUtils.TOKEN_ALGORITHM]
            )
            user_info = UserInfo.from_dict(payload)
            return True, user_info
        except jwt.ExpiredSignatureError:
            # token已过期
            return False, {'error': 'Token has expired'}
        except jwt.PyJWTError:
            # token无效
            return False, {'error': 'Invalid token'}

    @staticmethod
    def token_required(f):
        """
        基础token验证装饰器
        只验证token的有效性
        """
        @wraps(f)
        def decorated(*args, **kwargs):
            token = request.headers.get('token')
            if not token:
                return jsonify({'code': 401, 'msg': '缺少token', 'data': None}), 401

            is_valid, _ = TokenUtils.verify_token(token)
            if not is_valid:
                return jsonify({'code': 401, 'msg': 'token无效或已过期', 'data': None}), 401
            return f(*args, **kwargs)
        return decorated

    @staticmethod
    def user_token_required(f):
        """
        用户token验证装饰器
        验证token并获取用户信息
        """
        @wraps(f)
        def decorated(*args, **kwargs):
            token = request.headers.get('token')
            if not token:
                return jsonify({'code': 401, 'msg': '缺少token', 'data': None})
            try:
                is_valid, user_info = TokenUtils.verify_token(token)
                if not is_valid:
                    return jsonify({'code': 401, 'msg': 'token无效或已过期', 'data': None})
                return f(user_info=user_info, *args, **kwargs)
            except Exception as e:
                return jsonify({'code': 401, 'msg': f'token验证失败: {str(e)}', 'data': None})
        return decorated
    
    @staticmethod
    def zz_user_token_required(f):
        """
        中职用户token验证装饰器
        验证token并获取用户信息
        """
        @wraps(f)
        def decorated(*args, **kwargs):
            token = request.headers.get('token')
            if not token:
                return jsonify({'code': 401, 'msg': '缺少token', 'data': None})
            try:
                is_valid, _ = TokenUtils.verify_token(token)
                if not is_valid:
                    return jsonify({'code': 401, 'msg': 'token无效或已过期', 'data': None})
                
                redis_key = f"zhpt:user:{token}"
                token_payload = current_app.redis.hgetall(redis_key)
                if not token_payload:
                    return jsonify({'code': 401, 'msg': 'redis中不存在该token，请重新登录', 'data': None})
                user_xs = ZzXs.query.filter(ZzXs.xh == token_payload['xs_xh']).first()
                if not user_xs:
                    return jsonify({'code': 401, 'msg': 'redis中用户学号错误，请重新登录', 'data': None})
                return f(user_xs=user_xs, *args, **kwargs)
            except Exception as e:
                return jsonify({'code': 401, 'msg': f'token验证失败: {str(e)}', 'data': None})
        return decorated