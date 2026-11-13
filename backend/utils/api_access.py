from functools import wraps
from flask import jsonify

class ApiAccess:
    """API访问控制工具类"""
    
    @staticmethod
    def api_not_ready(message="该接口正在开发中，暂时无法访问"):
        """
        装饰器：标记API为不可访问状态
        
        Args:
            message (str): 自定义提示消息
            
        Returns:
            function: 装饰器函数
        """
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                return jsonify({
                    'code': 503,
                    'msg': message,
                    'data': None
                }), 503
            return wrapper
        return decorator
    
    @staticmethod
    def api_maintenance(start_time=None, end_time=None):
        """
        装饰器：标记API为维护状态
        
        Args:
            start_time (str): 维护开始时间，格式：YYYY-MM-DD HH:MM:SS
            end_time (str): 维护结束时间，格式：YYYY-MM-DD HH:MM:SS
            
        Returns:
            function: 装饰器函数
        """
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                message = "系统维护中"
                if start_time and end_time:
                    message = f"系统维护中，维护时间：{start_time} 至 {end_time}"
                elif start_time:
                    message = f"系统维护中，维护开始时间：{start_time}"
                elif end_time:
                    message = f"系统维护中，预计恢复时间：{end_time}"
                    
                return jsonify({
                    'code': 503,
                    'msg': message,
                    'data': None
                }), 503
            return wrapper
        return decorator 