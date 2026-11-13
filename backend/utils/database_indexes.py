#!/usr/bin/env python3
"""
数据库索引优化建议和管理
基于常用查询模式提供索引建议
"""

from typing import List, Dict, Any
from sqlalchemy import text, Index
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)

class DatabaseIndexManager:
    """数据库索引管理器"""
    
    # 推荐的索引配置
    RECOMMENDED_INDEXES = {
        # 学生表索引
        'oa_xs': [
            {
                'name': 'idx_xs_xh',
                'columns': ['xs_xh'],
                'unique': True,
                'comment': '学号唯一索引，用于登录和查询'
            },
            {
                'name': 'idx_xs_bj_id',
                'columns': ['xs_bj_id'],
                'unique': False,
                'comment': '班级ID索引，用于按班级查询学生'
            },
            {
                'name': 'idx_xs_nd_xjzt',
                'columns': ['xs_nd', 'xs_xjzt'],
                'unique': False,
                'comment': '年度和学籍状态复合索引'
            },
            {
                'name': 'idx_xs_sfzh',
                'columns': ['xs_sfzh'],
                'unique': True,
                'comment': '身份证号索引'
            },
            {
                'name': 'idx_xs_dh',
                'columns': ['xs_dh'],
                'unique': False,
                'comment': '电话号码索引，用于验证码发送'
            }
        ],
        
        # 教师表索引
        'oa_t': [
            {
                'name': 'idx_t_yhm',
                'columns': ['t_yhm'],
                'unique': True,
                'comment': '教师用户名唯一索引'
            },
            {
                'name': 'idx_t_bm_id',
                'columns': ['t_bm_id'],
                'unique': False,
                'comment': '部门ID索引'
            },
            {
                'name': 'idx_t_sfzh',
                'columns': ['t_sfzh'],
                'unique': True,
                'comment': '教师身份证号索引'
            }
        ],
        
        # 论文表索引
        'lw_lw': [
            {
                'name': 'idx_lw_xs_id',
                'columns': ['lw_xs_id'],
                'unique': False,
                'comment': '学生ID索引，用于查询学生论文'
            },
            {
                'name': 'idx_lw_t_id',
                'columns': ['lw_t_id'],
                'unique': False,
                'comment': '教师ID索引，用于查询指导论文'
            },
            {
                'name': 'idx_lw_wc_tg',
                'columns': ['lw_wc', 'lw_tg'],
                'unique': False,
                'comment': '完成状态和通过状态复合索引'
            },
            {
                'name': 'idx_lw_tjsj',
                'columns': ['lw_tjsj'],
                'unique': False,
                'comment': '提交时间索引，用于时间范围查询'
            }
        ],
        
        # 班级表索引
        'oa_bj': [
            {
                'name': 'idx_bj_nd',
                'columns': ['bj_nd'],
                'unique': False,
                'comment': '年度索引'
            },
            {
                'name': 'idx_bj_zy_id',
                'columns': ['bj_zy_id'],
                'unique': False,
                'comment': '专业ID索引'
            }
        ],
        
        # 订单表索引
        'wxxs_payinfo': [
            {
                'name': 'idx_payinfo_xh',
                'columns': ['o_xh'],
                'unique': False,
                'comment': '学号索引，用于查询学生订单'
            },
            {
                'name': 'idx_payinfo_status',
                'columns': ['o_status'],
                'unique': False,
                'comment': '订单状态索引'
            },
            {
                'name': 'idx_payinfo_addtime',
                'columns': ['o_addtime'],
                'unique': False,
                'comment': '创建时间索引'
            },
            {
                'name': 'idx_payinfo_pc_delete',
                'columns': ['o_pc', 'o_delete'],
                'unique': False,
                'comment': '批次和删除状态复合索引'
            }
        ]
    }
    
    @staticmethod
    def generate_index_sql(table_name: str, index_config: Dict[str, Any]) -> str:
        """生成创建索引的SQL语句"""
        index_name = index_config['name']
        columns = ', '.join(index_config['columns'])
        unique = 'UNIQUE ' if index_config.get('unique', False) else ''
        
        sql = f"CREATE {unique}INDEX {index_name} ON {table_name} ({columns})"
        return sql
    
    @staticmethod
    def check_index_exists(db: Session, table_name: str, index_name: str) -> bool:
        """检查索引是否存在"""
        try:
            sql = text("""
                SELECT COUNT(*) as count
                FROM sys.indexes i
                INNER JOIN sys.objects o ON i.object_id = o.object_id
                WHERE o.name = :table_name AND i.name = :index_name
            """)
            
            result = db.execute(sql, {
                'table_name': table_name,
                'index_name': index_name
            }).fetchone()
            
            return result[0] > 0 if result else False
            
        except Exception as e:
            logger.error(f"Failed to check index existence: {e}")
            return False
    
    @staticmethod
    def get_missing_indexes(db: Session) -> List[Dict[str, Any]]:
        """获取缺失的推荐索引"""
        missing_indexes = []
        
        for table_name, indexes in DatabaseIndexManager.RECOMMENDED_INDEXES.items():
            for index_config in indexes:
                index_name = index_config['name']
                
                if not DatabaseIndexManager.check_index_exists(db, table_name, index_name):
                    missing_indexes.append({
                        'table': table_name,
                        'index_name': index_name,
                        'columns': index_config['columns'],
                        'unique': index_config.get('unique', False),
                        'comment': index_config.get('comment', ''),
                        'sql': DatabaseIndexManager.generate_index_sql(table_name, index_config)
                    })
        
        return missing_indexes
    
    @staticmethod
    def create_recommended_indexes(db: Session, dry_run: bool = True) -> Dict[str, Any]:
        """创建推荐的索引"""
        missing_indexes = DatabaseIndexManager.get_missing_indexes(db)
        
        if not missing_indexes:
            return {
                'success': True,
                'message': 'All recommended indexes already exist',
                'created_count': 0,
                'indexes': []
            }
        
        created_indexes = []
        failed_indexes = []
        
        for index_info in missing_indexes:
            try:
                if not dry_run:
                    # 实际创建索引
                    db.execute(text(index_info['sql']))
                    db.commit()
                    logger.info(f"Created index: {index_info['index_name']}")
                
                created_indexes.append(index_info)
                
            except Exception as e:
                logger.error(f"Failed to create index {index_info['index_name']}: {e}")
                failed_indexes.append({
                    'index_info': index_info,
                    'error': str(e)
                })
                if not dry_run:
                    db.rollback()
        
        return {
            'success': len(failed_indexes) == 0,
            'message': f"{'Would create' if dry_run else 'Created'} {len(created_indexes)} indexes",
            'dry_run': dry_run,
            'created_count': len(created_indexes),
            'failed_count': len(failed_indexes),
            'created_indexes': created_indexes,
            'failed_indexes': failed_indexes
        }
    
    @staticmethod
    def analyze_query_performance(db: Session, sql: str, params: Dict = None) -> Dict[str, Any]:
        """分析查询性能"""
        try:
            # 获取查询执行计划
            explain_sql = f"SET SHOWPLAN_ALL ON; {sql}; SET SHOWPLAN_ALL OFF;"
            
            if params:
                result = db.execute(text(explain_sql), params)
            else:
                result = db.execute(text(explain_sql))
            
            # 这里可以解析执行计划，提供优化建议
            # 由于SQL Server的执行计划比较复杂，这里简化处理
            
            return {
                'success': True,
                'message': 'Query analysis completed',
                'recommendations': [
                    'Consider adding indexes on frequently queried columns',
                    'Use LIMIT/TOP to reduce result set size',
                    'Consider using EXISTS instead of IN for subqueries'
                ]
            }
            
        except Exception as e:
            logger.error(f"Failed to analyze query: {e}")
            return {
                'success': False,
                'message': f'Query analysis failed: {str(e)}',
                'recommendations': []
            }
    
    @staticmethod
    def get_table_statistics(db: Session, table_name: str) -> Dict[str, Any]:
        """获取表统计信息"""
        try:
            # 获取表行数
            count_sql = text(f"SELECT COUNT(*) as row_count FROM {table_name}")
            row_count = db.execute(count_sql).fetchone()[0]
            
            # 获取表大小信息
            size_sql = text("""
                SELECT 
                    t.name AS table_name,
                    SUM(a.total_pages) * 8 AS total_space_kb,
                    SUM(a.used_pages) * 8 AS used_space_kb,
                    (SUM(a.total_pages) - SUM(a.used_pages)) * 8 AS unused_space_kb
                FROM sys.tables t
                INNER JOIN sys.indexes i ON t.object_id = i.object_id
                INNER JOIN sys.partitions p ON i.object_id = p.object_id AND i.index_id = p.index_id
                INNER JOIN sys.allocation_units a ON p.partition_id = a.container_id
                WHERE t.name = :table_name
                GROUP BY t.name
            """)
            
            size_result = db.execute(size_sql, {'table_name': table_name}).fetchone()
            
            return {
                'table_name': table_name,
                'row_count': row_count,
                'total_space_kb': size_result[1] if size_result else 0,
                'used_space_kb': size_result[2] if size_result else 0,
                'unused_space_kb': size_result[3] if size_result else 0
            }
            
        except Exception as e:
            logger.error(f"Failed to get table statistics: {e}")
            return {
                'table_name': table_name,
                'error': str(e)
            }

# 全局索引管理器实例
index_manager = DatabaseIndexManager()
