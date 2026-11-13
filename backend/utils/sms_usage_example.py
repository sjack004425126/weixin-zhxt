"""
TeacherSms 模型使用示例
展示如何在代码中使用短信发送记录模型
"""

from models.models import TeacherSms
from utils.sms_status_codes import get_status_description, is_success
from datetime import datetime
from sqlalchemy.orm import Session


def save_sms_record(
    db: Session,
    t_id: int,
    t_xm: str,
    xs_xm: str,
    xs_dh: str,
    nr: str,
    num: int,
    cpSubID: str,
    status_code: int
):
    """
    保存短信发送记录
    
    Args:
        db: 数据库会话
        t_id: 教师ID
        t_xm: 教师姓名
        xs_xm: 学生姓名
        xs_dh: 学生电话
        nr: 短信内容
        num: 发送条数
        cpSubID: 短信平台返回的子ID
        status_code: 发送状态码 (0 表示成功)
    
    Returns:
        TeacherSms: 创建的短信记录对象
    """
    try:
        sms_record = TeacherSms(
            t_id=t_id,
            t_xm=t_xm,
            fssj=datetime.now(),
            nr=nr,
            xs_xm=xs_xm,
            xs_dh=xs_dh,
            num=num,
            cpSubID=cpSubID,
            send_status=status_code,
            status_desc=get_status_description(status_code)
        )
        
        db.add(sms_record)
        db.commit()
        
        return {
            'success': True,
            'msg': '短信记录保存成功',
            'data': {
                'id': sms_record.id,
                'status': 'success' if is_success(status_code) else 'failed',
                'status_desc': sms_record.status_desc
            }
        }
    except Exception as e:
        db.rollback()
        return {
            'success': False,
            'msg': f'短信记录保存失败: {str(e)}',
            'data': None
        }


def query_sms_records(
    db: Session,
    t_id: int = None,
    xs_dh: str = None,
    send_status: int = None,
    limit: int = 100
):
    """
    查询短信发送记录
    
    Args:
        db: 数据库会话
        t_id: 教师ID (可选)
        xs_dh: 学生电话 (可选)
        send_status: 发送状态 (可选，0 表示成功)
        limit: 返回记录数限制
    
    Returns:
        list: 短信记录列表
    """
    try:
        query = db.query(TeacherSms)
        
        if t_id:
            query = query.filter_by(t_id=t_id)
        
        if xs_dh:
            query = query.filter_by(xs_dh=xs_dh)
        
        if send_status is not None:
            query = query.filter_by(send_status=send_status)
        
        records = query.order_by(TeacherSms.fssj.desc()).limit(limit).all()
        
        return {
            'success': True,
            'msg': '查询成功',
            'data': [
                {
                    'id': r.id,
                    't_xm': r.t_xm,
                    'xs_xm': r.xs_xm,
                    'xs_dh': r.xs_dh,
                    'fssj': r.fssj.isoformat() if r.fssj else None,
                    'num': r.num,
                    'send_status': r.send_status,
                    'status_desc': r.status_desc
                }
                for r in records
            ]
        }
    except Exception as e:
        return {
            'success': False,
            'msg': f'查询失败: {str(e)}',
            'data': None
        }


def get_sms_statistics(db: Session, t_id: int = None):
    """
    获取短信发送统计信息
    
    Args:
        db: 数据库会话
        t_id: 教师ID (可选)
    
    Returns:
        dict: 统计信息
    """
    try:
        query = db.query(TeacherSms)
        
        if t_id:
            query = query.filter_by(t_id=t_id)
        
        total = query.count()
        success = query.filter_by(send_status=0).count()
        failed = total - success
        
        return {
            'success': True,
            'msg': '统计成功',
            'data': {
                'total': total,
                'success': success,
                'failed': failed,
                'success_rate': f"{(success/total*100):.2f}%" if total > 0 else "0%"
            }
        }
    except Exception as e:
        return {
            'success': False,
            'msg': f'统计失败: {str(e)}',
            'data': None
        }

