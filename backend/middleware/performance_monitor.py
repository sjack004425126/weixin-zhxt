"""
性能监控中间件
监控API响应时间和性能指标
"""

import time
import logging
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable
import json

class PerformanceMonitorMiddleware(BaseHTTPMiddleware):
    """性能监控中间件（优化版）"""

    def __init__(self, app, slow_threshold: float = 2.0, enable_detailed_logging: bool = False):
        super().__init__(app)
        self.slow_threshold = slow_threshold  # 慢查询阈值（秒）
        self.enable_detailed_logging = enable_detailed_logging  # 是否启用详细日志
        self.logger = logging.getLogger("performance")

        # 性能统计
        self.request_count = 0
        self.slow_request_count = 0
        self.error_count = 0

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 记录开始时间
        start_time = time.time()

        # 更新请求计数
        self.request_count += 1

        # 获取基本请求信息（减少字符串操作）
        method = request.method
        path = request.url.path  # 只获取路径，不包含查询参数
        client_ip = request.client.host if request.client else "unknown"

        # 处理请求
        try:
            response = await call_next(request)

            # 计算响应时间
            process_time = time.time() - start_time

            # 添加响应头
            response.headers["X-Process-Time"] = str(round(process_time * 1000, 2))

            # 只记录重要的性能日志（减少I/O开销）
            self._log_performance_optimized(
                method=method,
                path=path,
                status_code=response.status_code,
                process_time=process_time,
                client_ip=client_ip
            )

            return response
            
        except Exception as e:
            # 记录错误和响应时间
            process_time = time.time() - start_time
            self.logger.error(
                f"Request failed: {method} {url} - "
                f"Error: {str(e)} - "
                f"Time: {process_time:.3f}s - "
                f"Client: {client_ip}"
            )
            raise
    
    def _log_performance(self, method: str, url: str, status_code: int, 
                        process_time: float, client_ip: str, user_agent: str):
        """记录性能日志"""
        
        # 基本信息
        log_data = {
            "method": method,
            "url": url,
            "status_code": status_code,
            "response_time_ms": round(process_time * 1000, 2),
            "client_ip": client_ip
        }
        
        # 判断性能级别
        if process_time > self.slow_threshold:
            # 慢查询
            self.logger.warning(
                f"SLOW REQUEST: {method} {url} - "
                f"Status: {status_code} - "
                f"Time: {process_time:.3f}s - "
                f"Client: {client_ip} - "
                f"UA: {user_agent[:100]}"
            )
        elif process_time > 1.0:
            # 较慢请求
            self.logger.info(
                f"SLOW: {method} {url} - "
                f"Status: {status_code} - "
                f"Time: {process_time:.3f}s - "
                f"Client: {client_ip}"
            )
        elif status_code >= 400:
            # 错误请求
            self.error_count += 1
            self.logger.warning(
                f"ERROR: {method} {url} - "
                f"Status: {status_code} - "
                f"Time: {process_time:.3f}s - "
                f"Client: {client_ip}"
            )
        elif self.enable_detailed_logging:
            # 正常请求（仅在启用详细日志时记录）
            self.logger.debug(
                f"OK: {method} {url} - "
                f"Status: {status_code} - "
                f"Time: {process_time:.3f}s - "
                f"Client: {client_ip}"
            )

    def get_performance_stats(self) -> dict:
        """获取性能统计信息"""
        return {
            'total_requests': self.request_count,
            'slow_requests': self.slow_request_count,
            'error_requests': self.error_count,
            'slow_request_rate': self.slow_request_count / max(self.request_count, 1),
            'error_rate': self.error_count / max(self.request_count, 1)
        }


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件"""
    
    def __init__(self, app):
        super().__init__(app)
        self.logger = logging.getLogger("requests")
        
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 记录请求开始
        start_time = time.time()
        
        # 获取请求信息
        method = request.method
        url = str(request.url)
        client_ip = request.client.host if request.client else "unknown"
        
        # 记录请求体（仅POST/PUT/PATCH且非文件上传）
        request_body = None
        if method in ["POST", "PUT", "PATCH"]:
            content_type = request.headers.get("content-type", "")
            if "application/json" in content_type:
                try:
                    body = await request.body()
                    if body:
                        request_body = body.decode("utf-8")[:500]  # 限制长度
                except:
                    request_body = "Failed to read body"
        
        self.logger.info(
            f"REQUEST START: {method} {url} - Client: {client_ip}"
            + (f" - Body: {request_body}" if request_body else "")
        )
        
        # 处理请求
        try:
            response = await call_next(request)
            
            # 计算响应时间
            process_time = time.time() - start_time
            
            self.logger.info(
                f"REQUEST END: {method} {url} - "
                f"Status: {response.status_code} - "
                f"Time: {process_time:.3f}s - "
                f"Client: {client_ip}"
            )
            
            return response
            
        except Exception as e:
            process_time = time.time() - start_time
            self.logger.error(
                f"REQUEST FAILED: {method} {url} - "
                f"Error: {str(e)} - "
                f"Time: {process_time:.3f}s - "
                f"Client: {client_ip}"
            )
            raise


def setup_performance_logging():
    """设置性能日志配置"""
    
    # 性能日志配置
    perf_logger = logging.getLogger("performance")
    perf_logger.setLevel(logging.INFO)
    
    # 请求日志配置
    req_logger = logging.getLogger("requests")
    req_logger.setLevel(logging.INFO)
    
    # 创建文件处理器
    if not perf_logger.handlers:
        from utils.log_setup import ensure_log_dir, safe_file_handler

        # 确保日志目录存在（不可写时返回 None，退化为只输出到 stdout）
        log_dir = ensure_log_dir()
        if not log_dir:
            return

        # 性能日志文件
        perf_handler = safe_file_handler(
            f'{log_dir}/performance.log',
            max_bytes=10*1024*1024,  # 10MB
            backup_count=5
        )
        if perf_handler:
            perf_handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))
            perf_logger.addHandler(perf_handler)
        
        # 请求日志文件
        req_handler = safe_file_handler(
            f'{log_dir}/requests.log',
            max_bytes=10*1024*1024,  # 10MB
            backup_count=5
        )
        if req_handler:
            req_handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))
            req_logger.addHandler(req_handler)
