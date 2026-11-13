"""
实时访问统计 API
"""
from fastapi import APIRouter, Query
from pydantic import BaseModel
from datetime import datetime, timedelta
from middleware.stats_middleware import get_realtime_stats, get_page_stats, STATS_PREFIX
from utils.wx_utils import WxUtils
import logging

router = APIRouter(prefix="/stats", tags=["访问统计"])

# 允许访问管理中心的手机号白名单（在此添加或删除管理员手机号）
MONITOR_ALLOWED_PHONES = ['18984619084', '13385153117', '15121438850']


class MonitorAuthRequest(BaseModel):
    code: str


@router.post('/auth')
async def monitor_auth(request: MonitorAuthRequest):
    """
    监控页面手机号认证
    仅用于验证手机号是否在白名单中，不查询数据库
    """
    try:
        code = request.code
        
        if not code:
            return {
                'success': False,
                'msg': '缺少code参数',
                'data': None
            }

        # 使用异步微信API获取手机号
        phone_result = await WxUtils.get_phone_number_async(code)
        
        if not phone_result or not phone_result.get('phone_info'):
            logging.error(f"获取手机号失败: {phone_result}")
            return {
                'success': False,
                'msg': '获取手机号失败，请重试',
                'data': None
            }
        
        phone = phone_result['phone_info'].get('phoneNumber')
        if not phone:
            return {
                'success': False,
                'msg': '获取手机号失败',
                'data': None
            }

        # 检查是否在白名单中
        if phone in MONITOR_ALLOWED_PHONES:
            return {
                'success': True,
                'msg': '认证成功',
                'data': {
                    'phone': phone,
                    'authorized': True
                }
            }
        else:
            return {
                'success': False,
                'msg': '您没有访问权限',
                'data': {
                    'phone': phone,
                    'authorized': False
                }
            }

    except Exception as e:
        logging.error(f"监控认证失败: {str(e)}")
        return {
            'success': False,
            'msg': f'认证失败: {str(e)}',
            'data': None
        }


@router.get('/realtime')
async def realtime_stats():
    """
    获取实时统计数据
    包含：活跃请求数、今日总请求、分钟级请求趋势、路径统计、状态码统计、响应时间、慢请求
    """
    try:
        data = get_realtime_stats()
        return {
            'success': True,
            'msg': '获取成功',
            'data': data
        }
    except Exception as e:
        return {
            'success': False,
            'msg': f'获取统计数据失败: {str(e)}',
            'data': None
        }


@router.get('/pages')
async def page_stats():
    """
    获取页面/API访问统计
    按访问量排序的路径列表
    """
    try:
        data = get_page_stats()
        return {
            'success': True,
            'msg': '获取成功',
            'data': data
        }
    except Exception as e:
        return {
            'success': False,
            'msg': f'获取页面统计失败: {str(e)}',
            'data': None
        }


@router.get('/summary')
async def stats_summary():
    """
    获取统计摘要（轻量级，适合频繁刷新）
    """
    try:
        from init.redis_manager import redis_manager
        
        now = datetime.now()
        day_key = now.strftime("%Y%m%d")
        
        active = int(redis_manager.get("zhpt:stats:active_requests") or 0)
        total = int(redis_manager.get(f"zhpt:stats:total:{day_key}") or 0)
        
        return {
            'success': True,
            'msg': '获取成功',
            'data': {
                'active_requests': active,
                'total_today': total,
                'updated_at': now.isoformat()
            }
        }
    except Exception as e:
        return {
            'success': False,
            'msg': f'获取摘要失败: {str(e)}',
            'data': None
        }


@router.get('/history')
async def stats_history(days: int = Query(default=7, ge=1, le=30)):
    """
    获取历史统计数据（按小时）
    用于查看历史高峰时段
    
    Args:
        days: 查询天数，默认7天，最多30天
    """
    try:
        from init.redis_manager import redis_manager
        
        client = redis_manager.get_client()
        now = datetime.now()
        
        # 获取指定天数内的小时级数据
        hour_data = []
        for i in range(days * 24):
            hour_time = now - timedelta(hours=i)
            hour_key = hour_time.strftime("%Y%m%d%H")
            count = int(redis_manager.get(f"{STATS_PREFIX}hour_total:{hour_key}") or 0)
            hour_data.append({
                "hour": hour_time.strftime("%Y-%m-%d %H:00"),
                "count": count
            })
        
        hour_data.reverse()
        
        # 计算每日汇总
        daily_data = {}
        for item in hour_data:
            day = item["hour"][:10]
            if day not in daily_data:
                daily_data[day] = 0
            daily_data[day] += item["count"]
        
        daily_list = [{"date": k, "count": v} for k, v in daily_data.items()]
        
        # 找出高峰时段（请求量最高的10个小时）
        peak_hours = sorted(hour_data, key=lambda x: x["count"], reverse=True)[:10]
        
        return {
            'success': True,
            'msg': '获取成功',
            'data': {
                'hour_data': hour_data,
                'daily_data': daily_list,
                'peak_hours': peak_hours,
                'days': days,
                'updated_at': now.isoformat()
            }
        }
    except Exception as e:
        return {
            'success': False,
            'msg': f'获取历史数据失败: {str(e)}',
            'data': None
        }


@router.post('/clear')
async def clear_stats():
    """
    清空所有统计数据，重新开始统计
    """
    try:
        from init.redis_manager import redis_manager
        
        client = redis_manager.get_client()
        
        # 获取所有统计相关的键
        pattern = f"{STATS_PREFIX}*"
        keys = client.keys(pattern)
        
        if keys:
            # 批量删除
            client.delete(*keys)
        
        return {
            'success': True,
            'msg': f'已清空 {len(keys)} 条统计数据',
            'data': {
                'cleared_count': len(keys)
            }
        }
    except Exception as e:
        return {
            'success': False,
            'msg': f'清空统计数据失败: {str(e)}',
            'data': None
        }


@router.get('/api_ranking')
async def api_ranking(hours: int = Query(default=24, ge=1, le=168)):
    """
    获取API访问排行榜
    
    Args:
        hours: 统计时间范围（小时），默认24小时，最多168小时（7天）
    """
    try:
        from init.redis_manager import redis_manager
        
        client = redis_manager.get_client()
        now = datetime.now()
        
        # 汇总指定时间范围内的路径统计
        api_counts = {}
        for i in range(hours):
            hour_time = now - timedelta(hours=i)
            hour_key = hour_time.strftime("%Y%m%d%H")
            pattern = f"{STATS_PREFIX}path:{hour_key}:*"
            keys = client.keys(pattern)
            
            for key in keys:
                key_str = key.decode() if isinstance(key, bytes) else key
                path = key_str.split(':')[-1]
                count = int(redis_manager.get(key) or 0)
                if path not in api_counts:
                    api_counts[path] = 0
                api_counts[path] += count
        
        # 排序
        ranking = sorted(
            [{"path": k, "count": v} for k, v in api_counts.items()],
            key=lambda x: x["count"],
            reverse=True
        )
        
        return {
            'success': True,
            'msg': '获取成功',
            'data': {
                'ranking': ranking[:50],  # 返回前50个
                'total_apis': len(ranking),
                'hours': hours,
                'updated_at': now.isoformat()
            }
        }
    except Exception as e:
        return {
            'success': False,
            'msg': f'获取API排行失败: {str(e)}',
            'data': None
        }


@router.get('/daily_ranking')
async def daily_ranking(date: str = Query(..., description="日期，格式：YYYY-MM-DD")):
    """
    获取指定日期的API访问排行榜
    
    Args:
        date: 日期，格式：YYYY-MM-DD
    """
    try:
        from init.redis_manager import redis_manager
        
        client = redis_manager.get_client()
        
        # 解析日期
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return {
                'success': False,
                'msg': '日期格式错误，请使用 YYYY-MM-DD 格式',
                'data': None
            }
        
        # 汇总该日期24小时内的路径统计
        api_counts = {}
        total_requests = 0
        
        for hour in range(24):
            hour_time = target_date.replace(hour=hour)
            hour_key = hour_time.strftime("%Y%m%d%H")
            pattern = f"{STATS_PREFIX}path:{hour_key}:*"
            keys = client.keys(pattern)
            
            for key in keys:
                key_str = key.decode() if isinstance(key, bytes) else key
                path = key_str.split(':')[-1]
                count = int(redis_manager.get(key) or 0)
                if path not in api_counts:
                    api_counts[path] = 0
                api_counts[path] += count
                total_requests += count
        
        # 排序
        ranking = sorted(
            [{"path": k, "count": v} for k, v in api_counts.items()],
            key=lambda x: x["count"],
            reverse=True
        )
        
        return {
            'success': True,
            'msg': '获取成功',
            'data': {
                'date': date,
                'ranking': ranking[:30],  # 返回前30个
                'total_apis': len(ranking),
                'total_requests': total_requests
            }
        }
    except Exception as e:
        return {
            'success': False,
            'msg': f'获取日期排行失败: {str(e)}',
            'data': None
        }
