"""
选课服务
处理选课队列和业务逻辑
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional
from sqlalchemy.orm import Session
from models.models import ZzStCourse, ZzStCourseSelection, ZzSys
from utils.redis_utils import RedisLock, CourseCache, CourseSelectionQueue

logger = logging.getLogger(__name__)

class CourseSelectionService:
    """选课服务类"""
    
    def __init__(self, redis_client):
        self.redis_client = redis_client
        self.course_cache = CourseCache(redis_client)
        self.selection_queue = CourseSelectionQueue(redis_client)
    
    async def add_to_selection_queue(self, course_id: int, student_id: str, current_user: dict, 
                                   current_year: int, current_semester: str) -> Dict:
        """
        添加选课请求到队列
        
        Args:
            course_id: 课程ID
            student_id: 学生ID
            current_user: 当前用户信息
            current_year: 当前学年
            current_semester: 当前学期
            
        Returns:
            Dict: 操作结果
        """
        try:
            # 构造请求数据
            request_data = {
                'student_id': student_id,
                'course_id': course_id,
                'current_user': current_user,
                'current_year': current_year,
                'current_semester': current_semester,
                'request_time': datetime.now().isoformat()
            }
            
            # 添加到队列
            success = self.selection_queue.add_to_queue(course_id, student_id, request_data)
            
            if success:
                queue_length = self.selection_queue.get_queue_length(course_id)
                return {
                    'success': True,
                    'message': f'选课请求已加入队列，当前排队人数: {queue_length}',
                    'data': {
                        'queue_position': queue_length,
                        'course_id': course_id
                    }
                }
            else:
                return {
                    'success': False,
                    'message': '加入选课队列失败',
                    'data': None
                }
                
        except Exception as e:
            logger.error(f"添加选课请求到队列失败: {str(e)}")
            return {
                'success': False,
                'message': f'系统错误: {str(e)}',
                'data': None
            }
    
    async def process_course_selection(self, db: Session, course_id: int, queue_item: Dict) -> Dict:
        """
        处理单个选课请求
        
        Args:
            db: 数据库会话
            course_id: 课程ID
            queue_item: 队列项数据
            
        Returns:
            Dict: 处理结果
        """
        try:
            student_id = queue_item['student_id']
            request_data = queue_item['request_data']
            current_year = request_data['current_year']
            current_semester = request_data['current_semester']
            
            # 使用分布式锁确保并发安全
            async with RedisLock(self.redis_client, f"course_select_{course_id}", timeout=30):
                
                # 从数据库获取最新的课程信息
                course = db.query(ZzStCourse).filter(
                    ZzStCourse.id == course_id
                ).with_for_update().first()
                
                if not course:
                    return {
                        'success': False,
                        'message': '课程不存在',
                        'data': None
                    }
                
                # 检查课程状态
                if course.status != 1:
                    return {
                        'success': False,
                        'message': '课程已禁用',
                        'data': None
                    }
                
                # 检查是否已经选过这门课
                existing_selection = db.query(ZzStCourseSelection).filter_by(
                    student_id=student_id,
                    course_id=course_id,
                    year=current_year,
                    semester=current_semester
                ).first()

                if existing_selection:
                    return {
                        'success': False,
                        'message': '您已经选过这门课程',
                        'data': None
                    }

                # 检查课程名额
                if course.current_students >= course.max_students:
                    return {
                        'success': False,
                        'message': '课程已满，选课失败',
                        'data': None
                    }

                # 创建新的选课记录
                new_selection = ZzStCourseSelection(
                    student_id=student_id,
                    course_id=course_id,
                    year=current_year,
                    semester=current_semester,
                    select_time=datetime.now(),
                    create_time=datetime.now(),
                    update_time=datetime.now()
                )
                db.add(new_selection)
                
                # 更新课程选课人数
                course.current_students += 1
                course.update_time = datetime.now()
                
                # 提交数据库事务
                db.commit()
                
                # 更新缓存
                course_data = {
                    'id': course.id,
                    'course_name': course.course_name,
                    'current_students': course.current_students,
                    'max_students': course.max_students,
                    'status': course.status,
                    'updated_at': datetime.now().isoformat()
                }
                self.course_cache.set_course_info(course_id, course_data)
                
                return {
                    'success': True,
                    'message': '选课成功',
                    'data': {
                        'course_id': course_id,
                        'course_name': course.course_name,
                        'current_students': course.current_students,
                        'max_students': course.max_students
                    }
                }
                
        except Exception as e:
            db.rollback()
            logger.error(f"处理选课请求失败: {str(e)}")
            return {
                'success': False,
                'message': f'选课失败: {str(e)}',
                'data': None
            }
    
    async def get_course_info_with_cache(self, db: Session, course_id: int) -> Optional[Dict]:
        """
        获取课程信息（优先从缓存获取）
        
        Args:
            db: 数据库会话
            course_id: 课程ID
            
        Returns:
            Dict: 课程信息
        """
        try:
            # 先从缓存获取
            cached_info = self.course_cache.get_course_info(course_id)
            if cached_info:
                logger.debug(f"从缓存获取课程信息: {course_id}")
                return cached_info
            
            # 缓存未命中，从数据库获取
            course = db.query(ZzStCourse).filter_by(id=course_id).first()
            if not course:
                return None
            
            course_data = {
                'id': course.id,
                'course_name': course.course_name,
                'current_students': course.current_students,
                'max_students': course.max_students,
                'status': course.status,
                'teacher_id': course.teacher_id,
                'credit': float(course.credit),
                'hours': course.hours,
                'classroom': course.classroom,
                'description': course.description,
                'category': course.category,
                'updated_at': datetime.now().isoformat()
            }
            
            # 设置缓存
            self.course_cache.set_course_info(course_id, course_data)
            logger.debug(f"从数据库获取并缓存课程信息: {course_id}")
            
            return course_data
            
        except Exception as e:
            logger.error(f"获取课程信息失败: {str(e)}")
            return None
    
    async def cancel_course_selection(self, db: Session, course_id: int, student_id: str,
                                    current_year: int, current_semester: str) -> Dict:
        """
        取消选课
        
        Args:
            db: 数据库会话
            course_id: 课程ID
            student_id: 学生ID
            current_year: 当前学年
            current_semester: 当前学期
            
        Returns:
            Dict: 操作结果
        """
        try:
            # 使用分布式锁确保并发安全
            async with RedisLock(self.redis_client, f"course_cancel_{course_id}", timeout=30):
                
                # 获取选课记录
                existing_selection = db.query(ZzStCourseSelection).filter_by(
                    student_id=student_id,
                    course_id=course_id,
                    year=current_year,
                    semester=current_semester
                ).first()

                if not existing_selection:
                    return {
                        'success': False,
                        'message': '您未选择该课程',
                        'data': None
                    }

                # 获取课程信息
                course = db.query(ZzStCourse).filter(
                    ZzStCourse.id == course_id
                ).with_for_update().first()

                if not course:
                    return {
                        'success': False,
                        'message': '课程不存在',
                        'data': None
                    }

                # 硬删除选课记录
                db.delete(existing_selection)
                
                # 更新课程当前选课人数
                if course.current_students > 0:
                    course.current_students -= 1
                course.update_time = datetime.now()
                
                # 提交数据库事务
                db.commit()
                
                # 更新缓存
                self.course_cache.update_current_students(course_id, course.current_students)
                
                return {
                    'success': True,
                    'message': '退选成功',
                    'data': {
                        'course_id': course_id,
                        'course_name': course.course_name,
                        'current_students': course.current_students,
                        'max_students': course.max_students
                    }
                }
                
        except Exception as e:
            db.rollback()
            logger.error(f"取消选课失败: {str(e)}")
            return {
                'success': False,
                'message': f'退选失败: {str(e)}',
                'data': None
            }
