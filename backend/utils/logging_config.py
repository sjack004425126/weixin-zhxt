#!/usr/bin/env python3
"""
优化的日志配置
根据环境和性能需求调整日志级别和输出
"""

import os
import logging
import logging.handlers
from typing import Dict, Any
from init.config import get_config
from utils.log_setup import ensure_log_dir, get_log_dir, safe_file_handler

class OptimizedLoggingConfig:
    """优化的日志配置管理器"""
    
    # 不同环境的日志级别配置
    LOG_LEVELS = {
        'development': {
            'root': logging.DEBUG,
            'sqlalchemy.engine': logging.WARNING,  # 减少SQL日志
            'sqlalchemy.pool': logging.WARNING,
            'uvicorn.access': logging.INFO,
            'performance': logging.INFO,
            'requests': logging.DEBUG,
            'auth': logging.INFO,
            'cache': logging.INFO
        },
        'production': {
            'root': logging.INFO,
            'sqlalchemy.engine': logging.ERROR,  # 生产环境只记录错误
            'sqlalchemy.pool': logging.ERROR,
            'uvicorn.access': logging.WARNING,  # 减少访问日志
            'performance': logging.WARNING,  # 只记录慢请求和错误
            'requests': logging.WARNING,
            'auth': logging.WARNING,
            'cache': logging.ERROR
        },
        'testing': {
            'root': logging.WARNING,
            'sqlalchemy.engine': logging.ERROR,
            'sqlalchemy.pool': logging.ERROR,
            'uvicorn.access': logging.ERROR,
            'performance': logging.ERROR,
            'requests': logging.ERROR,
            'auth': logging.WARNING,
            'cache': logging.ERROR
        }
    }
    
    @staticmethod
    def setup_optimized_logging(config_name: str = 'development') -> Dict[str, Any]:
        """
        设置优化的日志配置
        
        Args:
            config_name: 配置环境名称
            
        Returns:
            日志配置信息
        """
        try:
            config = get_config(config_name)
            log_levels = OptimizedLoggingConfig.LOG_LEVELS.get(
                config_name, 
                OptimizedLoggingConfig.LOG_LEVELS['development']
            )
            
            # 创建日志目录（容错：不可写时退化为只输出到 stdout）
            log_dir = ensure_log_dir() or get_log_dir()
            
            # 配置根日志记录器
            root_logger = logging.getLogger()
            root_logger.setLevel(log_levels['root'])
            
            # 清除现有的处理器
            for handler in root_logger.handlers[:]:
                root_logger.removeHandler(handler)
            
            # 创建格式化器
            detailed_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            simple_formatter = logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s'
            )
            
            # 控制台处理器（开发环境详细，生产环境简化）
            console_handler = logging.StreamHandler()
            if config_name == 'development':
                console_handler.setFormatter(detailed_formatter)
                console_handler.setLevel(logging.DEBUG)
            else:
                console_handler.setFormatter(simple_formatter)
                console_handler.setLevel(logging.WARNING)
            
            root_logger.addHandler(console_handler)
            
            # 文件处理器配置
            handlers_config = []
            
            if config_name == 'production':
                # 生产环境：分级别记录到不同文件
                # ⚠️ 全部用 safe_file_handler：日志目录不可写时返回 None，
                #    跳过对应 handler，而不是让整个应用启动失败。
                
                # 错误日志
                error_handler = safe_file_handler(
                    f'{log_dir}/error.log',
                    max_bytes=50*1024*1024,  # 50MB
                    backup_count=10,
                )
                if error_handler:
                    error_handler.setLevel(logging.ERROR)
                    error_handler.setFormatter(detailed_formatter)
                    root_logger.addHandler(error_handler)
                    handlers_config.append('error.log')
                
                # 警告日志
                warning_handler = safe_file_handler(
                    f'{log_dir}/warning.log',
                    max_bytes=20*1024*1024,  # 20MB
                    backup_count=5,
                )
                if warning_handler:
                    warning_handler.setLevel(logging.WARNING)
                    warning_handler.setFormatter(simple_formatter)
                    # 过滤掉ERROR级别（已经记录到error.log）
                    warning_handler.addFilter(lambda record: record.levelno < logging.ERROR)
                    root_logger.addHandler(warning_handler)
                    handlers_config.append('warning.log')
                
                # 应用日志（INFO级别）
                app_handler = safe_file_handler(
                    f'{log_dir}/app.log',
                    max_bytes=10*1024*1024,  # 10MB
                    backup_count=3,
                )
                if app_handler:
                    app_handler.setLevel(logging.INFO)
                    app_handler.setFormatter(simple_formatter)
                    # 过滤掉WARNING及以上级别
                    app_handler.addFilter(lambda record: record.levelno < logging.WARNING)
                    root_logger.addHandler(app_handler)
                    handlers_config.append('app.log')
                
            else:
                # 开发/测试环境：单一日志文件
                file_handler = safe_file_handler(
                    f'{log_dir}/zhpt.log',
                    max_bytes=10*1024*1024,  # 10MB
                    backup_count=5,
                )
                if file_handler:
                    file_handler.setLevel(log_levels['root'])
                    file_handler.setFormatter(detailed_formatter)
                    root_logger.addHandler(file_handler)
                    handlers_config.append('zhpt.log')
            
            # 配置特定模块的日志级别
            for logger_name, level in log_levels.items():
                if logger_name != 'root':
                    logger = logging.getLogger(logger_name)
                    logger.setLevel(level)
            
            # 性能监控日志（单独文件）
            perf_logger = logging.getLogger('performance')
            if config_name in ['development', 'production']:
                perf_handler = safe_file_handler(
                    f'{log_dir}/performance.log',
                    max_bytes=5*1024*1024,  # 5MB
                    backup_count=3,
                )
                if perf_handler:
                    perf_handler.setFormatter(logging.Formatter(
                        '%(asctime)s - %(message)s'
                    ))
                    perf_logger.addHandler(perf_handler)
                    perf_logger.propagate = False  # 不传播到根日志记录器
                handlers_config.append('performance.log')
            
            logging.info(f"Optimized logging configured for {config_name} environment")
            
            return {
                'success': True,
                'environment': config_name,
                'log_levels': log_levels,
                'handlers': handlers_config,
                'log_directory': log_dir
            }
            
        except Exception as e:
            print(f"Failed to setup optimized logging: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    @staticmethod
    def get_logger_stats() -> Dict[str, Any]:
        """获取日志记录器统计信息"""
        try:
            loggers = {}
            
            # 获取所有活跃的日志记录器
            for name in logging.Logger.manager.loggerDict:
                logger = logging.getLogger(name)
                loggers[name] = {
                    'level': logging.getLevelName(logger.level),
                    'handlers_count': len(logger.handlers),
                    'propagate': logger.propagate
                }
            
            # 根日志记录器
            root_logger = logging.getLogger()
            loggers['root'] = {
                'level': logging.getLevelName(root_logger.level),
                'handlers_count': len(root_logger.handlers),
                'propagate': True
            }
            
            return {
                'total_loggers': len(loggers),
                'loggers': loggers
            }
            
        except Exception as e:
            return {
                'error': str(e)
            }
    
    @staticmethod
    def adjust_runtime_log_levels(adjustments: Dict[str, str]) -> Dict[str, Any]:
        """
        运行时调整日志级别
        
        Args:
            adjustments: {'logger_name': 'level_name'} 格式的调整配置
            
        Returns:
            调整结果
        """
        try:
            adjusted = {}
            failed = {}
            
            for logger_name, level_name in adjustments.items():
                try:
                    level = getattr(logging, level_name.upper())
                    logger = logging.getLogger(logger_name)
                    old_level = logging.getLevelName(logger.level)
                    logger.setLevel(level)
                    adjusted[logger_name] = {
                        'old_level': old_level,
                        'new_level': level_name.upper()
                    }
                except AttributeError:
                    failed[logger_name] = f"Invalid log level: {level_name}"
                except Exception as e:
                    failed[logger_name] = str(e)
            
            return {
                'success': len(failed) == 0,
                'adjusted': adjusted,
                'failed': failed
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

# 便捷函数
def setup_logging(config_name: str = None):
    """设置优化的日志配置"""
    if config_name is None:
        config_name = os.getenv('FASTAPI_ENV', 'development')
    
    return OptimizedLoggingConfig.setup_optimized_logging(config_name)

def get_optimized_logger(name: str) -> logging.Logger:
    """获取优化配置的日志记录器"""
    return logging.getLogger(name)
