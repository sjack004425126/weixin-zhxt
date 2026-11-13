from flask import current_app
import redis
import json
from models.models import lw_sys

class SystemConfig:
    REDIS_KEY = 'system:config'
    CACHE_TIMEOUT = 24 * 60 * 60  # 24小时的缓存时间
    
    @classmethod
    def get_config(cls):
        """获取系统配置信息"""
        try:
            # 1. 尝试从Redis获取
            redis_client = current_app.redis
            cached_config = redis_client.get(cls.REDIS_KEY)
            
            if cached_config:
                return json.loads(cached_config)
                
            # 2. 如果Redis中没有，从数据库获取
            sys_info = lw_sys.query.filter_by(id=1).first()
            if not sys_info:
                current_app.logger.error("未找到系统配置信息")
                return None
                
            # 3. 转换为字典格式
            config_dict = {
                'sys_pc': sys_info.sys_pc,  # 当前批次
                'sys_xq1_nd': sys_info.sys_xq1_nd,  # 学期年度
                'sys_xs_jf': sys_info.sys_xs_jf.strftime('%Y-%m-%d %H:%M:%S') if sys_info.sys_xs_jf else None,  # 新生缴费截止时间
                'sys_ls_jf': sys_info.sys_ls_jf.strftime('%Y-%m-%d %H:%M:%S') if sys_info.sys_ls_jf else None,  # 老生缴费截止时间
                # ... 其他需要的配置字段
            }
            
            # 4. 存入Redis
            redis_client.setex(
                cls.REDIS_KEY,
                cls.CACHE_TIMEOUT,
                json.dumps(config_dict)
            )
            
            return config_dict
            
        except Exception as e:
            current_app.logger.error(f"获取系统配置失败: {str(e)}")
            # 如果Redis出错，直接从数据库读取
            try:
                sys_info = lw_sys.query.filter_by(id=1).first()
                if not sys_info:
                    return None
                    
                return {
                    'sys_pc': sys_info.sys_pc,
                    'sys_xq1_nd': sys_info.sys_xq1_nd,
                    'sys_xs_jf': sys_info.sys_xs_jf.strftime('%Y-%m-%d %H:%M:%S') if sys_info.sys_xs_jf else None,
                    'sys_ls_jf': sys_info.sys_ls_jf.strftime('%Y-%m-%d %H:%M:%S') if sys_info.sys_ls_jf else None,
                }
            except Exception as e:
                current_app.logger.error(f"从数据库获取系统配置失败: {str(e)}")
                return None
    
    @classmethod
    def refresh_config(cls):
        """手动刷新配置（在更新系统配置后调用）"""
        try:
            redis_client = current_app.redis
            redis_client.delete(cls.REDIS_KEY)
            return cls.get_config()
        except Exception as e:
            current_app.logger.error(f"刷新系统配置失败: {str(e)}")
            return None 