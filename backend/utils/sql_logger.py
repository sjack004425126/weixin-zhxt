#!/usr/bin/env python3
"""
智能 SQL 日志管理器
提供可控制的 SQL 日志记录，避免性能影响
"""

import os
import logging
import time
from typing import Dict, Any, Optional, List
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.pool import Pool

logger = logging.getLogger(__name__)

class SQLLoggerManager:
    """SQL 日志管理器"""
    
    def __init__(self):
        self.enabled = False
        self.slow_query_threshold = 1.0  # 慢查询阈值（秒）
        self.log_slow_queries_only = True  # 只记录慢查询
        self.query_count = 0
        self.slow_query_count = 0
        self.total_query_time = 0.0
        self.query_stats = {}
        
    def enable_sql_logging(self, 
                          slow_queries_only: bool = True,
                          slow_threshold: float = 1.0,
                          log_level: str = 'INFO'):
        """
        启用 SQL 日志记录
        
        Args:
            slow_queries_only: 是否只记录慢查询
            slow_threshold: 慢查询阈值（秒）
            log_level: 日志级别
        """
        self.enabled = True
        self.log_slow_queries_only = slow_queries_only
        self.slow_query_threshold = slow_threshold
        
        # 设置 SQLAlchemy 日志级别
        sql_logger = logging.getLogger('sqlalchemy.engine')
        if slow_queries_only:
            sql_logger.setLevel(logging.WARNING)  # 只记录警告和错误
        else:
            sql_logger.setLevel(getattr(logging, log_level.upper()))
        
        logger.info(f"SQL logging enabled - slow_queries_only: {slow_queries_only}, threshold: {slow_threshold}s")
    
    def disable_sql_logging(self):
        """禁用 SQL 日志记录"""
        self.enabled = False
        
        # 禁用 SQLAlchemy 日志
        sql_logger = logging.getLogger('sqlalchemy.engine')
        sql_logger.setLevel(logging.ERROR)
        
        logger.info("SQL logging disabled")
    
    def setup_query_monitoring(self, engine: Engine):
        """设置查询监控事件"""
        
        @event.listens_for(engine, "before_cursor_execute")
        def receive_before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            """查询开始前的事件"""
            if self.enabled:
                context._query_start_time = time.time()
        
        @event.listens_for(engine, "after_cursor_execute")
        def receive_after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            """查询结束后的事件"""
            if self.enabled and hasattr(context, '_query_start_time'):
                query_time = time.time() - context._query_start_time
                self.query_count += 1
                self.total_query_time += query_time
                
                # 记录查询统计
                query_type = self._get_query_type(statement)
                if query_type not in self.query_stats:
                    self.query_stats[query_type] = {
                        'count': 0,
                        'total_time': 0.0,
                        'avg_time': 0.0,
                        'slow_count': 0
                    }
                
                self.query_stats[query_type]['count'] += 1
                self.query_stats[query_type]['total_time'] += query_time
                self.query_stats[query_type]['avg_time'] = (
                    self.query_stats[query_type]['total_time'] / 
                    self.query_stats[query_type]['count']
                )
                
                # 检查是否为慢查询
                if query_time > self.slow_query_threshold:
                    self.slow_query_count += 1
                    self.query_stats[query_type]['slow_count'] += 1
                    
                    # 记录慢查询日志
                    self._log_slow_query(statement, parameters, query_time)
                elif not self.log_slow_queries_only:
                    # 记录所有查询（如果启用）
                    self._log_query(statement, parameters, query_time)
    
    def _get_query_type(self, statement: str) -> str:
        """获取查询类型"""
        statement_upper = statement.strip().upper()
        if statement_upper.startswith('SELECT'):
            return 'SELECT'
        elif statement_upper.startswith('INSERT'):
            return 'INSERT'
        elif statement_upper.startswith('UPDATE'):
            return 'UPDATE'
        elif statement_upper.startswith('DELETE'):
            return 'DELETE'
        elif statement_upper.startswith('BEGIN'):
            return 'TRANSACTION'
        elif statement_upper.startswith('COMMIT'):
            return 'COMMIT'
        elif statement_upper.startswith('ROLLBACK'):
            return 'ROLLBACK'
        else:
            return 'OTHER'
    
    def _log_slow_query(self, statement: str, parameters: Any, query_time: float):
        """记录慢查询"""
        # 简化 SQL 语句显示
        simplified_sql = self._simplify_sql(statement)
        
        logger.warning(
            f"SLOW QUERY ({query_time:.3f}s): {simplified_sql}"
        )
        
        # 详细日志记录到专门的慢查询日志
        slow_logger = logging.getLogger('slow_queries')
        slow_logger.warning(
            f"SLOW QUERY DETAILS:\n"
            f"Time: {query_time:.3f}s\n"
            f"SQL: {statement}\n"
            f"Params: {parameters}\n"
            f"---"
        )
    
    def _log_query(self, statement: str, parameters: Any, query_time: float):
        """记录普通查询"""
        simplified_sql = self._simplify_sql(statement)
        
        logger.debug(
            f"QUERY ({query_time:.3f}s): {simplified_sql}"
        )
    
    def _simplify_sql(self, statement: str) -> str:
        """简化 SQL 语句显示"""
        # 移除多余的空白字符
        simplified = ' '.join(statement.split())
        
        # 如果太长，截断显示
        if len(simplified) > 100:
            simplified = simplified[:97] + "..."
        
        return simplified
    
    def get_query_statistics(self) -> Dict[str, Any]:
        """获取查询统计信息"""
        avg_query_time = self.total_query_time / max(self.query_count, 1)
        
        return {
            'enabled': self.enabled,
            'total_queries': self.query_count,
            'slow_queries': self.slow_query_count,
            'slow_query_rate': self.slow_query_count / max(self.query_count, 1),
            'avg_query_time': round(avg_query_time, 4),
            'total_query_time': round(self.total_query_time, 4),
            'slow_threshold': self.slow_query_threshold,
            'query_types': self.query_stats
        }
    
    def reset_statistics(self):
        """重置统计信息"""
        self.query_count = 0
        self.slow_query_count = 0
        self.total_query_time = 0.0
        self.query_stats = {}
        logger.info("Query statistics reset")
    
    def get_top_slow_queries(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最慢的查询类型"""
        sorted_queries = sorted(
            self.query_stats.items(),
            key=lambda x: x[1]['avg_time'],
            reverse=True
        )
        
        return [
            {
                'query_type': query_type,
                'avg_time': round(stats['avg_time'], 4),
                'count': stats['count'],
                'slow_count': stats['slow_count'],
                'total_time': round(stats['total_time'], 4)
            }
            for query_type, stats in sorted_queries[:limit]
        ]

# 全局 SQL 日志管理器实例
sql_logger_manager = SQLLoggerManager()

def setup_smart_sql_logging(engine: Engine, environment: str = 'development'):
    """
    设置智能 SQL 日志记录
    
    Args:
        engine: SQLAlchemy 引擎
        environment: 环境名称
    """
    
    # 设置查询监控
    sql_logger_manager.setup_query_monitoring(engine)
    
    # 根据环境配置日志策略
    if environment == 'production':
        # 生产环境：只记录慢查询（>2秒）
        sql_logger_manager.enable_sql_logging(
            slow_queries_only=True,
            slow_threshold=2.0,
            log_level='WARNING'
        )
    elif environment == 'development':
        # 开发环境：记录慢查询（>0.5秒）
        sql_logger_manager.enable_sql_logging(
            slow_queries_only=True,
            slow_threshold=0.5,
            log_level='INFO'
        )
    else:
        # 测试环境：禁用 SQL 日志
        sql_logger_manager.disable_sql_logging()
    
    logger.info(f"Smart SQL logging configured for {environment} environment")

def enable_debug_sql_logging():
    """临时启用详细 SQL 日志（调试用）"""
    sql_logger_manager.enable_sql_logging(
        slow_queries_only=False,
        slow_threshold=0.1,
        log_level='DEBUG'
    )
    logger.info("Debug SQL logging enabled")

def disable_sql_logging():
    """禁用 SQL 日志"""
    sql_logger_manager.disable_sql_logging()

def get_sql_stats():
    """获取 SQL 统计信息"""
    return sql_logger_manager.get_query_statistics()

# 环境变量控制
def auto_configure_sql_logging():
    """根据环境变量自动配置 SQL 日志"""
    enable_sql_debug = os.getenv('ENABLE_SQL_DEBUG', 'false').lower() == 'true'
    
    if enable_sql_debug:
        enable_debug_sql_logging()
        logger.info("SQL debug logging enabled via environment variable")
    else:
        disable_sql_logging()
        logger.info("SQL logging disabled for performance")
