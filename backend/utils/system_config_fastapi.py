"""
FastAPI兼容的系统配置类
"""

import redis
import json
import logging
from models.models import lw_sys
from sqlalchemy.orm import Session

class SystemConfig:
    REDIS_KEY = "zhpt:system_config"
    
    @classmethod
    def get_config(cls, redis_client=None, db_session: Session = None):
        """获取系统配置信息"""
        try:
            # 1. 尝试从Redis获取
            if redis_client:
                cached_config = redis_client.get(cls.REDIS_KEY)
                if cached_config:
                    return json.loads(cached_config)
                    
            # 2. 如果Redis中没有，从数据库获取
            if not db_session:
                from database import database
                db_session = database.get_session()
                should_close = True
            else:
                should_close = False
                
            try:
                sys_info = db_session.query(lw_sys).filter_by(id=1).first()
                if not sys_info:
                    logging.error("未找到系统配置信息")
                    return None
                    
                # 3. 转换为字典格式
                config_dict = {
                    'sys_pc': sys_info.sys_pc,  # 当前批次
                    'sys_xq1_nd': sys_info.sys_xq1_nd,  # 学期1年度
                    'sys_xs_jf': sys_info.sys_xs_jf.strftime('%Y-%m-%d %H:%M:%S') if sys_info.sys_xs_jf else None,  # 学生缴费截止时间
                    'sys_ls_jf': sys_info.sys_ls_jf.strftime('%Y-%m-%d %H:%M:%S') if sys_info.sys_ls_jf else None,  # 老师缴费截止时间
                }
                
                # 4. 存储到Redis（如果Redis可用）
                if redis_client:
                    redis_client.setex(
                        cls.REDIS_KEY,
                        3600,  # 1小时过期
                        json.dumps(config_dict, ensure_ascii=False)
                    )
                
                return config_dict
                
            finally:
                if should_close:
                    db_session.close()
                
        except Exception as e:
            logging.error(f"获取系统配置失败: {str(e)}")
            # 如果Redis出错，直接从数据库读取
            try:
                if not db_session:
                    from database import database
                    db_session = database.get_session()
                    should_close = True
                else:
                    should_close = False
                    
                try:
                    sys_info = db_session.query(lw_sys).filter_by(id=1).first()
                    if not sys_info:
                        return None
                    return {
                        'sys_pc': sys_info.sys_pc,
                        'sys_xq1_nd': sys_info.sys_xq1_nd,
                        'sys_xs_jf': sys_info.sys_xs_jf.strftime('%Y-%m-%d %H:%M:%S') if sys_info.sys_xs_jf else None,
                        'sys_ls_jf': sys_info.sys_ls_jf.strftime('%Y-%m-%d %H:%M:%S') if sys_info.sys_ls_jf else None,
                    }
                finally:
                    if should_close:
                        db_session.close()
            except Exception as e:
                logging.error(f"从数据库获取系统配置失败: {str(e)}")
                return None
    
    @classmethod
    def refresh_config(cls, redis_client=None, db_session: Session = None):
        """手动刷新配置（在更新系统配置后调用）"""
        try:
            if redis_client:
                redis_client.delete(cls.REDIS_KEY)
            return cls.get_config(redis_client, db_session)
        except Exception as e:
            logging.error(f"刷新系统配置失败: {str(e)}")
            return None
    
    @classmethod
    def update_config(cls, config_data: dict, redis_client=None, db_session: Session = None):
        """更新系统配置"""
        try:
            if not db_session:
                from database import database
                db_session = database.get_session()
                should_close = True
            else:
                should_close = False
                
            try:
                sys_info = db_session.query(lw_sys).filter_by(id=1).first()
                if not sys_info:
                    # 如果不存在，创建新记录
                    sys_info = lw_sys(id=1)
                    db_session.add(sys_info)
                
                # 更新字段
                for key, value in config_data.items():
                    if hasattr(sys_info, key):
                        setattr(sys_info, key, value)
                
                db_session.commit()
                
                # 刷新缓存
                if redis_client:
                    redis_client.delete(cls.REDIS_KEY)
                
                return True
                
            finally:
                if should_close:
                    db_session.close()
                    
        except Exception as e:
            if db_session:
                db_session.rollback()
            logging.error(f"更新系统配置失败: {str(e)}")
            return False
