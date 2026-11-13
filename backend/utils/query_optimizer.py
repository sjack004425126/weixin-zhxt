#!/usr/bin/env python3
"""
数据库查询优化工具
提供预加载、批量查询等优化功能，避免N+1查询问题
"""

from typing import List, Dict, Any, Optional, Type
from sqlalchemy.orm import Session, joinedload, selectinload, subqueryload
from sqlalchemy import and_, or_, text
from models.models import Student, Teacher, Paper, Class, Major
import logging

logger = logging.getLogger(__name__)

class QueryOptimizer:
    """查询优化器"""
    
    @staticmethod
    def get_students_with_papers(db: Session, student_ids: List[int] = None, 
                                limit: int = None) -> List[Student]:
        """
        获取学生及其论文信息，避免N+1查询
        使用 joinedload 预加载关联数据
        """
        query = db.query(Student).options(
            joinedload(Student.papers).joinedload(Paper.teacher)
        )
        
        if student_ids:
            query = query.filter(Student.xs_id.in_(student_ids))
        
        if limit:
            query = query.limit(limit)
        
        return query.all()
    
    @staticmethod
    def get_teachers_with_papers(db: Session, teacher_ids: List[int] = None,
                                limit: int = None) -> List[Teacher]:
        """
        获取教师及其指导的论文信息，避免N+1查询
        """
        query = db.query(Teacher).options(
            selectinload(Teacher.papers).selectinload(Paper.student)
        )
        
        if teacher_ids:
            query = query.filter(Teacher.t_id.in_(teacher_ids))
        
        if limit:
            query = query.limit(limit)
        
        return query.all()
    
    @staticmethod
    def get_papers_with_relations(db: Session, paper_ids: List[int] = None,
                                 limit: int = None) -> List[Paper]:
        """
        获取论文及其关联的学生和教师信息
        """
        query = db.query(Paper).options(
            joinedload(Paper.student),
            joinedload(Paper.teacher)
        )
        
        if paper_ids:
            query = query.filter(Paper.lw_id.in_(paper_ids))
        
        if limit:
            query = query.limit(limit)
        
        return query.all()
    
    @staticmethod
    def get_students_by_class_batch(db: Session, class_ids: List[int]) -> Dict[int, List[Student]]:
        """
        批量获取多个班级的学生信息
        返回 {class_id: [students]} 的字典
        """
        if not class_ids:
            return {}
        
        students = db.query(Student).filter(Student.xs_bj_id.in_(class_ids)).all()
        
        # 按班级ID分组
        result = {}
        for student in students:
            class_id = student.xs_bj_id
            if class_id not in result:
                result[class_id] = []
            result[class_id].append(student)
        
        return result
    
    @staticmethod
    def get_student_counts_by_class(db: Session, class_ids: List[int] = None) -> Dict[int, int]:
        """
        批量获取班级学生数量统计
        """
        query = db.query(Student.xs_bj_id, db.func.count(Student.xs_id).label('count'))
        
        if class_ids:
            query = query.filter(Student.xs_bj_id.in_(class_ids))
        
        query = query.group_by(Student.xs_bj_id)
        
        result = {}
        for class_id, count in query.all():
            result[class_id] = count
        
        return result
    
    @staticmethod
    def get_students_with_class_info(db: Session, student_ids: List[int] = None,
                                   limit: int = None) -> List[Student]:
        """
        获取学生及其班级信息，使用JOIN避免N+1查询
        """
        query = db.query(Student).join(Class, Student.xs_bj_id == Class.bj_id)
        
        if student_ids:
            query = query.filter(Student.xs_id.in_(student_ids))
        
        if limit:
            query = query.limit(limit)
        
        return query.all()
    
    @staticmethod
    def bulk_update_students(db: Session, updates: List[Dict[str, Any]]) -> int:
        """
        批量更新学生信息
        
        Args:
            updates: [{'id': student_id, 'data': {'field': 'value'}}]
        
        Returns:
            更新的记录数
        """
        if not updates:
            return 0
        
        updated_count = 0
        try:
            for update in updates:
                student_id = update['id']
                data = update['data']
                
                result = db.query(Student).filter(Student.xs_id == student_id).update(data)
                updated_count += result
            
            db.commit()
            logger.info(f"Bulk updated {updated_count} student records")
            return updated_count
            
        except Exception as e:
            db.rollback()
            logger.error(f"Bulk update failed: {e}")
            raise
    
    @staticmethod
    def get_paginated_students(db: Session, page: int = 1, page_size: int = 20,
                              filters: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        分页获取学生信息，包含总数统计
        
        Returns:
            {
                'items': [students],
                'total': total_count,
                'page': current_page,
                'page_size': page_size,
                'pages': total_pages
            }
        """
        query = db.query(Student)
        
        # 应用过滤条件
        if filters:
            if 'class_id' in filters:
                query = query.filter(Student.xs_bj_id == filters['class_id'])
            if 'year' in filters:
                query = query.filter(Student.xs_nd == filters['year'])
            if 'status' in filters:
                query = query.filter(Student.xs_xjzt == filters['status'])
            if 'name' in filters:
                query = query.filter(Student.xs_xm.like(f"%{filters['name']}%"))
        
        # 获取总数
        total = query.count()
        
        # 分页查询
        offset = (page - 1) * page_size
        items = query.offset(offset).limit(page_size).all()
        
        # 计算总页数
        total_pages = (total + page_size - 1) // page_size
        
        return {
            'items': items,
            'total': total,
            'page': page,
            'page_size': page_size,
            'pages': total_pages
        }
    
    @staticmethod
    def execute_optimized_raw_query(db: Session, sql: str, params: Dict[str, Any] = None) -> List[Dict]:
        """
        执行优化的原生SQL查询
        """
        try:
            if params:
                result = db.execute(text(sql), params)
            else:
                result = db.execute(text(sql))
            
            # 转换为字典列表
            columns = result.keys()
            rows = []
            for row in result.fetchall():
                rows.append(dict(zip(columns, row)))
            
            return rows
            
        except Exception as e:
            logger.error(f"Raw query execution failed: {e}")
            raise

# 全局查询优化器实例
query_optimizer = QueryOptimizer()

# 便捷函数
def get_students_optimized(db: Session, **kwargs) -> List[Student]:
    """优化的学生查询"""
    return query_optimizer.get_students_with_papers(db, **kwargs)

def get_teachers_optimized(db: Session, **kwargs) -> List[Teacher]:
    """优化的教师查询"""
    return query_optimizer.get_teachers_with_papers(db, **kwargs)

def paginate_query(db: Session, model: Type, page: int = 1, page_size: int = 20,
                  filters: Dict[str, Any] = None) -> Dict[str, Any]:
    """通用分页查询"""
    if model == Student:
        return query_optimizer.get_paginated_students(db, page, page_size, filters)
    else:
        # 其他模型的通用分页逻辑
        query = db.query(model)
        
        # 这里可以根据需要添加通用过滤逻辑
        
        total = query.count()
        offset = (page - 1) * page_size
        items = query.offset(offset).limit(page_size).all()
        total_pages = (total + page_size - 1) // page_size
        
        return {
            'items': items,
            'total': total,
            'page': page,
            'page_size': page_size,
            'pages': total_pages
        }
