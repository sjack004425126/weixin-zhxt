"""
实时访问统计中间件
使用 Redis 存储访问统计数据，支持实时查询
"""
import time
import logging
from datetime import datetime, timedelta
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Redis 键前缀
STATS_PREFIX = "zhpt:stats:"
# 统计数据过期时间（秒）
STATS_EXPIRE = 86400  # 24小时


class StatsMiddleware(BaseHTTPMiddleware):
    """
    实时访问统计中间件
    统计内容：
    - 总请求数
    - 各路径请求数
    - 各状态码数量
    - 响应时间统计
    - 当前活跃请求数
    """
    
    # 不统计的路径前缀
    EXCLUDE_PATHS = ['/stats/', '/health', '/docs', '/redoc', '/openapi.json']
    
    async def dispatch(self, request: Request, call_next) -> Response:
        from init.redis_manager import redis_manager
        
        start_time = time.time()
        path = request.url.path
        method = request.method
        
        # 跳过统计接口自身和其他不需要统计的路径
        should_skip = any(path.startswith(prefix) for prefix in self.EXCLUDE_PATHS)
        
        if should_skip:
            return await call_next(request)
        
        # 获取当前时间键（按分钟统计）
        now = datetime.now()
        minute_key = now.strftime("%Y%m%d%H%M")
        hour_key = now.strftime("%Y%m%d%H")
        day_key = now.strftime("%Y%m%d")
        
        # 增加活跃请求计数
        active_key = f"{STATS_PREFIX}active_requests"
        try:
            redis_manager.incr(active_key)
        except Exception as e:
            logger.debug(f"Redis incr failed: {e}")
        
        try:
            # 执行请求
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            status_code = 500
            raise
        finally:
            # 减少活跃请求计数
            try:
                redis_manager.decr(active_key)
            except Exception:
                pass
            
            # 计算响应时间
            duration_ms = int((time.time() - start_time) * 1000)
            
            # 记录统计数据
            try:
                self._record_stats(
                    redis_manager, path, method, status_code, 
                    duration_ms, minute_key, hour_key, day_key
                )
            except Exception as e:
                logger.debug(f"Record stats failed: {e}")
        
        return response
    
    def _record_stats(self, redis_manager, path, method, status_code, 
                      duration_ms, minute_key, hour_key, day_key):
        """记录统计数据到 Redis"""
        client = redis_manager.get_client()
        pipe = client.pipeline()
        
        # 1. 总请求数（按天）
        total_key = f"{STATS_PREFIX}total:{day_key}"
        pipe.incr(total_key)
        pipe.expire(total_key, STATS_EXPIRE)
        
        # 2. 按分钟统计请求数（用于实时图表）
        minute_total_key = f"{STATS_PREFIX}minute:{minute_key}"
        pipe.incr(minute_total_key)
        pipe.expire(minute_total_key, 3600)  # 保留1小时
        
        # 3. 路径统计（按小时）
        # 简化路径，去除动态参数
        simple_path = self._simplify_path(path)
        path_key = f"{STATS_PREFIX}path:{hour_key}:{simple_path}"
        pipe.incr(path_key)
        pipe.expire(path_key, STATS_EXPIRE)
        
        # 4. 状态码统计（按小时）
        status_key = f"{STATS_PREFIX}status:{hour_key}:{status_code}"
        pipe.incr(status_key)
        pipe.expire(status_key, STATS_EXPIRE)
        
        # 5. 响应时间统计（使用 sorted set 存储最近的响应时间）
        rt_key = f"{STATS_PREFIX}response_time:{hour_key}"
        pipe.zadd(rt_key, {f"{path}:{time.time()}": duration_ms})
        pipe.expire(rt_key, STATS_EXPIRE)
        # 只保留最近1000条
        pipe.zremrangebyrank(rt_key, 0, -1001)
        
        # 7. 小时级历史数据（用于查看历史高峰）
        hour_total_key = f"{STATS_PREFIX}hour_total:{hour_key}"
        pipe.incr(hour_total_key)
        pipe.expire(hour_total_key, 86400 * 7)  # 保留7天
        
        # 6. 慢请求记录（超过1秒的请求）
        if duration_ms > 1000:
            slow_key = f"{STATS_PREFIX}slow:{hour_key}"
            slow_data = f"{method} {path} {duration_ms}ms {datetime.now().isoformat()}"
            pipe.lpush(slow_key, slow_data)
            pipe.ltrim(slow_key, 0, 99)  # 只保留最近100条
            pipe.expire(slow_key, STATS_EXPIRE)
        
        pipe.execute()
    
    def _simplify_path(self, path: str) -> str:
        """简化路径，将动态参数替换为占位符"""
        parts = path.split('/')
        simplified = []
        for part in parts:
            # 如果是纯数字或UUID格式，替换为占位符
            if part.isdigit() or (len(part) == 8 and part.isalnum()):
                simplified.append('{id}')
            else:
                simplified.append(part)
        return '/'.join(simplified)


def get_realtime_stats() -> dict:
    """
    获取实时统计数据
    """
    from init.redis_manager import redis_manager
    
    now = datetime.now()
    hour_key = now.strftime("%Y%m%d%H")
    day_key = now.strftime("%Y%m%d")
    
    try:
        # 活跃请求数
        active_requests = int(redis_manager.get(f"{STATS_PREFIX}active_requests") or 0)
        
        # 今日总请求数
        total_today = int(redis_manager.get(f"{STATS_PREFIX}total:{day_key}") or 0)
        
        # 最近60分钟的请求数（用于图表）
        minute_data = []
        base_time = now.replace(second=0, microsecond=0)
        for i in range(60):
            minute_time = base_time - timedelta(minutes=i)
            minute_key = minute_time.strftime("%Y%m%d%H%M")
            count = int(redis_manager.get(f"{STATS_PREFIX}minute:{minute_key}") or 0)
            minute_data.append({
                "time": minute_time.strftime("%H:%M"),
                "count": count
            })
        minute_data.reverse()
        
        # 当前小时各路径统计
        path_stats = {}
        pattern = f"{STATS_PREFIX}path:{hour_key}:*"
        client = redis_manager.get_client()
        keys = client.keys(pattern)
        for key in keys[:20]:  # 只取前20个
            path = key.decode().split(':')[-1] if isinstance(key, bytes) else key.split(':')[-1]
            count = int(redis_manager.get(key) or 0)
            path_stats[path] = count
        
        # 排序取 Top 10
        path_stats = dict(sorted(path_stats.items(), key=lambda x: x[1], reverse=True)[:10])
        
        # 状态码统计
        status_stats = {}
        for code in [200, 201, 400, 401, 403, 404, 500, 502, 503]:
            count = int(redis_manager.get(f"{STATS_PREFIX}status:{hour_key}:{code}") or 0)
            if count > 0:
                status_stats[str(code)] = count
        
        # 平均响应时间
        rt_key = f"{STATS_PREFIX}response_time:{hour_key}"
        rt_scores = client.zrange(rt_key, -100, -1, withscores=True)
        if rt_scores:
            avg_rt = sum(score for _, score in rt_scores) / len(rt_scores)
        else:
            avg_rt = 0
        
        # 慢请求列表
        slow_key = f"{STATS_PREFIX}slow:{hour_key}"
        slow_requests = client.lrange(slow_key, 0, 9)
        slow_requests = [r.decode() if isinstance(r, bytes) else r for r in slow_requests]
        
        return {
            "active_requests": active_requests,
            "total_today": total_today,
            "minute_data": minute_data,
            "path_stats": path_stats,
            "status_stats": status_stats,
            "avg_response_time_ms": round(avg_rt, 2),
            "slow_requests": slow_requests,
            "updated_at": now.isoformat()
        }
        
    except Exception as e:
        logger.error(f"获取统计数据失败: {e}")
        return {
            "error": str(e),
            "active_requests": 0,
            "total_today": 0,
            "minute_data": [],
            "path_stats": {},
            "status_stats": {},
            "avg_response_time_ms": 0,
            "slow_requests": [],
            "updated_at": now.isoformat()
        }


def get_page_stats() -> dict:
    """
    获取页面访问统计（按路径分组）
    """
    from init.redis_manager import redis_manager
    
    now = datetime.now()
    hour_key = now.strftime("%Y%m%d%H")
    
    try:
        # 获取所有路径统计
        client = redis_manager.get_client()
        pattern = f"{STATS_PREFIX}path:{hour_key}:*"
        keys = client.keys(pattern)
        
        page_stats = []
        for key in keys:
            key_str = key.decode() if isinstance(key, bytes) else key
            path = key_str.split(':')[-1]
            count = int(redis_manager.get(key) or 0)
            page_stats.append({
                "path": path,
                "count": count
            })
        
        # 按访问量排序
        page_stats.sort(key=lambda x: x["count"], reverse=True)
        
        return {
            "pages": page_stats[:50],  # 返回前50个
            "total_pages": len(page_stats),
            "hour": hour_key,
            "updated_at": now.isoformat()
        }
        
    except Exception as e:
        logger.error(f"获取页面统计失败: {e}")
        return {
            "pages": [],
            "total_pages": 0,
            "hour": hour_key,
            "updated_at": now.isoformat(),
            "error": str(e)
        }
