"""
调试日志工具
用于详细打印数据库查询结果和其他调试信息
"""

import logging
import json
from datetime import datetime
from typing import Any, List, Dict

logger = logging.getLogger(__name__)

def debug_print_query_results(results: List[Any], title: str = "查询结果", student_id: str = None):
    """
    详细打印数据库查询结果
    
    Args:
        results: 数据库查询结果列表
        title: 打印标题
        student_id: 学生ID（可选）
    """
    
    print(f'\n{"="*60}')
    print(f'   {title}')
    print(f'{"="*60}')
    
    if student_id:
        print(f'学号: {student_id}')
    
    print(f'查询时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'结果数量: {len(results)}')
    print(f'{"-"*60}')
    
    if not results:
        print('❌ 未找到任何记录')
        print(f'{"="*60}\n')
        return
    
    for i, result in enumerate(results, 1):
        print(f'\n📋 记录 {i}:')
        
        try:
            # 尝试不同的方式转换结果为字典
            result_dict = None
            
            if hasattr(result, '_asdict'):
                # SQLAlchemy NamedTuple
                result_dict = result._asdict()
            elif hasattr(result, '__dict__'):
                # SQLAlchemy Model对象
                result_dict = {key: value for key, value in result.__dict__.items() 
                             if not key.startswith('_')}
            elif hasattr(result, 'keys') and hasattr(result, 'values'):
                # Row对象或类似字典的对象
                result_dict = dict(zip(result.keys(), result.values()))
            elif isinstance(result, (tuple, list)):
                # 元组或列表
                result_dict = {f'column_{j}': val for j, val in enumerate(result)}
            elif isinstance(result, dict):
                # 已经是字典
                result_dict = result
            else:
                # 其他类型，直接转换为字符串
                print(f'  ⚠️  无法解析的数据类型: {type(result)}')
                print(f'  原始数据: {result}')
                continue
            
            # 打印字典内容
            if result_dict:
                for key, value in result_dict.items():
                    # 格式化不同类型的值
                    if value is None:
                        formatted_value = 'NULL'
                    elif isinstance(value, datetime):
                        formatted_value = value.strftime('%Y-%m-%d %H:%M:%S')
                    elif isinstance(value, (int, float)):
                        formatted_value = str(value)
                    elif isinstance(value, str):
                        # 限制字符串长度，避免输出过长
                        formatted_value = value[:100] + '...' if len(value) > 100 else value
                    else:
                        formatted_value = str(value)
                    
                    print(f'  {key:20}: {formatted_value}')
            
        except Exception as e:
            print(f'  ❌ 解析记录时出错: {e}')
            print(f'  原始数据: {result}')
            print(f'  数据类型: {type(result)}')
    
    print(f'\n{"="*60}\n')

def debug_print_dict(data: Dict[str, Any], title: str = "字典数据"):
    """
    详细打印字典数据
    
    Args:
        data: 要打印的字典
        title: 打印标题
    """
    
    print(f'\n{"="*50}')
    print(f'   {title}')
    print(f'{"="*50}')
    
    if not data:
        print('❌ 字典为空')
        print(f'{"="*50}\n')
        return
    
    for key, value in data.items():
        if isinstance(value, datetime):
            formatted_value = value.strftime('%Y-%m-%d %H:%M:%S')
        elif isinstance(value, dict):
            formatted_value = json.dumps(value, ensure_ascii=False, indent=2)
        elif isinstance(value, (list, tuple)):
            formatted_value = f'[{len(value)} items] {str(value)[:100]}...' if len(str(value)) > 100 else str(value)
        else:
            formatted_value = str(value)
        
        print(f'{key:20}: {formatted_value}')
    
    print(f'{"="*50}\n')

def debug_print_sql_execution(sql: str, params: Dict[str, Any] = None, title: str = "SQL执行"):
    """
    打印SQL执行信息
    
    Args:
        sql: SQL语句
        params: SQL参数
        title: 打印标题
    """
    
    print(f'\n{"="*50}')
    print(f'   {title}')
    print(f'{"="*50}')
    print(f'执行时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'SQL语句:')
    print(f'{sql}')
    
    if params:
        print(f'参数:')
        for key, value in params.items():
            print(f'  {key}: {value}')
    
    print(f'{"="*50}\n')

def debug_log_to_file(message: str, filename: str = "debug.log"):
    """
    将调试信息写入文件
    
    Args:
        message: 要写入的消息
        filename: 日志文件名
    """
    
    import os
    from utils.log_setup import safe_append_line, get_log_dir

    log_file = os.path.join(get_log_dir(), filename)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    safe_append_line(log_file, f'[{timestamp}] {message}\n')

# 便捷函数
def debug_print(data: Any, title: str = "调试信息"):
    """
    通用调试打印函数
    
    Args:
        data: 要打印的数据
        title: 打印标题
    """
    
    if isinstance(data, list) and data and hasattr(data[0], '__dict__'):
        # 数据库查询结果列表
        debug_print_query_results(data, title)
    elif isinstance(data, dict):
        # 字典数据
        debug_print_dict(data, title)
    else:
        # 其他数据
        print(f'\n=== {title} ===')
        print(f'数据类型: {type(data)}')
        print(f'数据内容: {data}')
        print(f'=== {title} 结束 ===\n')

# 装饰器：自动打印函数执行信息
def debug_function(func):
    """
    装饰器：自动打印函数执行信息
    """
    def wrapper(*args, **kwargs):
        print(f'\n🔧 执行函数: {func.__name__}')
        print(f'参数: args={args}, kwargs={kwargs}')
        
        try:
            result = func(*args, **kwargs)
            print(f'✅ 函数执行成功')
            return result
        except Exception as e:
            print(f'❌ 函数执行失败: {e}')
            raise
    
    return wrapper
