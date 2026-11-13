"""报名查询码生成与验证工具"""
import random
import string
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

# 查询码有效期：365天
QUERY_CODE_EXPIRE_DAYS = 365

# 查询码字符集：大写字母+数字，去掉易混淆字符 (0/O, 1/I/L)
CHARSET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'


def generate_query_code(length=8) -> str:
    """生成8位随机查询码"""
    return ''.join(random.choices(CHARSET, k=length))


def generate_unique_query_code(db: Session, table_name: str, length=8, max_retries=10) -> str:
    """生成全局唯一的查询码（跨所有报名表检查唯一性）
    
    Args:
        db: 数据库会话
        table_name: 当前表名（优先检查）
        length: 查询码长度
        max_retries: 最大重试次数
    
    Returns:
        唯一的8位查询码
    """
    all_tables = [
        'zs_adult_enrollment',
        'zs_vocational34_enrollment',
        'zs_graduate_employment_survey',
        'zz_bmxs'
    ]
    
    for _ in range(max_retries):
        code = generate_query_code(length)
        
        # 跨所有报名表检查唯一性
        is_unique = True
        for tbl in all_tables:
            result = db.execute(
                text(f"SELECT COUNT(1) FROM {tbl} WHERE query_code = :code"),
                {"code": code}
            ).scalar()
            if result and result > 0:
                is_unique = False
                break
        
        if is_unique:
            return code
    
    # 极端情况：10次都重复，用12位长度兜底
    return generate_query_code(12)


def get_query_code_expire_time() -> datetime:
    """获取查询码过期时间（当前时间 + 365天）"""
    return datetime.now() + timedelta(days=QUERY_CODE_EXPIRE_DAYS)


def is_query_code_valid(expire_time: datetime) -> bool:
    """检查查询码是否在有效期内"""
    if not expire_time:
        return False
    return datetime.now() < expire_time


# 表单类型 -> 表名/模型映射
FORM_TYPE_CONFIG = {
    'adult_exam': {
        'table': 'zs_adult_enrollment',
        'model_name': 'ZsAdultEnrollment',
        'name_field': 'name',
        'phone_field': 'phone',
        'display_name': '成人高等教育预报名',
    },
    'vocational_34': {
        'table': 'zs_vocational34_enrollment',
        'model_name': 'ZsVocational34Enrollment',
        'name_field': 'name',
        'phone_field': 'phone',
        'display_name': '3+4中本贯通报名',
    },
    'graduate_employment_survey': {
        'table': 'zs_graduate_employment_survey',
        'model_name': 'ZsGraduateEmploymentSurvey',
        'name_field': 'student_name',
        'phone_field': 'phone',
        'display_name': '毕业生就业调查',
    },
    'vocational_zzbm': {
        'table': 'zz_bmxs',
        'model_name': 'ZzBmxs',
        'name_field': 'xm',
        'phone_field': 'xsdh',
        'display_name': '中职招生报名',
    },
}
