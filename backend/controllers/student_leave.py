from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
from models.models import ZzXsQxj, Student, ZzXs
from init.dependencies import DatabaseDep
from common.auth import verify_token_and_get_payload
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/student/leave", tags=["学生请销假"])


class LeaveApplyRequest(BaseModel):
    """请假申请请求"""
    qjlb: str  # 请假类别：病假、事假、其他
    qjsy: str  # 请假事由
    qjkssj: str  # 请假开始时间
    qjjssj: str  # 请假结束时间
    xslxxl: str  # 学生离校线路
    xslxjtgj: str  # 学生离校交通工具


class LeaveCancelRequest(BaseModel):
    """销假请求"""
    leave_id: int  # 请假记录ID
    xsfxxl: str  # 学生返校线路
    xsfxjtgj: str  # 学生返校交通工具


@router.get('/list')
async def get_leave_list(
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """获取学生请假记录列表"""
    try:
        xh = current_user.get('xs_xh')
        
        leaves = db.query(ZzXsQxj).filter(
            ZzXsQxj.xh == xh
        ).order_by(ZzXsQxj.qjsqsj.desc()).all()
        
        leave_list = []
        for leave in leaves:
            leave_list.append({
                'id': leave.id,
                'xm': leave.xm,
                'xh': leave.xh,
                'qjlb': leave.qjlb,
                'qjsy': leave.qjsy,
                'qjsqsj': leave.qjsqsj.strftime('%Y-%m-%d %H:%M:%S') if leave.qjsqsj else None,
                'qjkssj': leave.qjkssj.strftime('%Y-%m-%d %H:%M:%S') if leave.qjkssj else None,
                'qjjssj': leave.qjjssj.strftime('%Y-%m-%d %H:%M:%S') if leave.qjjssj else None,
                'xslxxl': leave.xslxxl,
                'xslxjtgj': leave.xslxjtgj,
                'bzr_zt': leave.bzr_zt,
                'sp_bzr_xm': leave.sp_bzr_xm,
                'xsk_zt': leave.xsk_zt,
                'sp_xsk_xm': leave.sp_xsk_xm,
                'xj_zt': leave.xj_zt,
                'xjsj': leave.xjsj.strftime('%Y-%m-%d %H:%M:%S') if leave.xjsj else None,
                'xsfxxl': leave.xsfxxl,
                'xsfxjtgj': leave.xsfxjtgj
            })
        
        return {
            'success': True,
            'msg': '获取请假记录成功',
            'data': leave_list
        }
    except Exception as e:
        logger.error(f"获取请假记录失败: {str(e)}")
        return {
            'success': False,
            'msg': f'获取请假记录失败: {str(e)}',
            'data': None
        }


@router.get('/detail/{leave_id}')
async def get_leave_detail(
    leave_id: int,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """获取请假详情"""
    try:
        xh = current_user.get('xs_xh')
        
        leave = db.query(ZzXsQxj).filter(
            ZzXsQxj.id == leave_id,
            ZzXsQxj.xh == xh
        ).first()
        
        if not leave:
            return {
                'success': False,
                'msg': '请假记录不存在',
                'data': None
            }
        
        return {
            'success': True,
            'msg': '获取请假详情成功',
            'data': {
                'id': leave.id,
                'xm': leave.xm,
                'xh': leave.xh,
                'bj_id': leave.bj_id,
                'qjlb': leave.qjlb,
                'qjsy': leave.qjsy,
                'qjsqsj': leave.qjsqsj.strftime('%Y-%m-%d %H:%M:%S') if leave.qjsqsj else None,
                'qjkssj': leave.qjkssj.strftime('%Y-%m-%d %H:%M:%S') if leave.qjkssj else None,
                'qjjssj': leave.qjjssj.strftime('%Y-%m-%d %H:%M:%S') if leave.qjjssj else None,
                'xslxxl': leave.xslxxl,
                'xslxjtgj': leave.xslxjtgj,
                'sp_bzr_tid': leave.sp_bzr_tid,
                'sp_bzr_xm': leave.sp_bzr_xm,
                'bzr_zt': leave.bzr_zt,
                'sp_xsk_tid': leave.sp_xsk_tid,
                'sp_xsk_xm': leave.sp_xsk_xm,
                'xsk_zt': leave.xsk_zt,
                'xj_zt': leave.xj_zt,
                'xjsj': leave.xjsj.strftime('%Y-%m-%d %H:%M:%S') if leave.xjsj else None,
                'xsfxxl': leave.xsfxxl,
                'xsfxjtgj': leave.xsfxjtgj
            }
        }
    except Exception as e:
        logger.error(f"获取请假详情失败: {str(e)}")
        return {
            'success': False,
            'msg': f'获取请假详情失败: {str(e)}',
            'data': None
        }


@router.get('/check_can_apply')
async def check_can_apply(
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """检查是否可以申请请假（是否有未销假的记录）"""
    try:
        xh = current_user.get('xs_xh')
        
        # 查询是否有未销假的请假记录
        uncanceled_leave = db.query(ZzXsQxj).filter(
            ZzXsQxj.xh == xh,
            ZzXsQxj.xj_zt == 0  # 未销假
        ).first()
        
        if uncanceled_leave:
            return {
                'success': True,
                'msg': '存在未销假的请假记录',
                'data': {
                    'can_apply': False,
                    'reason': '您有未销假的请假记录，请先销假后再申请新的请假',
                    'leave_id': uncanceled_leave.id
                }
            }
        
        return {
            'success': True,
            'msg': '可以申请请假',
            'data': {
                'can_apply': True,
                'reason': None,
                'leave_id': None
            }
        }
    except Exception as e:
        logger.error(f"检查是否可以申请请假失败: {str(e)}")
        return {
            'success': False,
            'msg': f'检查失败: {str(e)}',
            'data': None
        }


@router.post('/apply')
async def apply_leave(
    request: LeaveApplyRequest,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """申请请假"""
    try:
        xh = current_user.get('xs_xh')
        bj_id = current_user.get('xs_bj_id')
        
        # 从数据库查询学生信息获取姓名
        from models.models import ZzXs, ZzBj, Teacher
        student = db.query(ZzXs).filter(ZzXs.xh == xh).first()
        if not student:
            return {
                'success': False,
                'msg': '学生信息不存在',
                'data': None
            }
        xm = student.xm
        
        # 查询班级信息获取班主任ID和姓名
        sp_bzr_tid = None
        sp_bzr_xm = None
        if bj_id:
            class_info = db.query(ZzBj).filter(ZzBj.id == bj_id).first()
            if class_info and class_info.bzr_id:
                sp_bzr_tid = class_info.bzr_id
                # 查询班主任姓名
                teacher = db.query(Teacher).filter(Teacher.t_id == class_info.bzr_id).first()
                if teacher:
                    sp_bzr_xm = teacher.t_xm
        
        # 检查是否有未销假的请假记录
        uncanceled_leave = db.query(ZzXsQxj).filter(
            ZzXsQxj.xh == xh,
            ZzXsQxj.xj_zt == 0
        ).first()
        
        if uncanceled_leave:
            return {
                'success': False,
                'msg': '您有未销假的请假记录，请先销假后再申请新的请假',
                'data': None
            }
        
        # 验证请假类别
        valid_types = ['病假', '事假', '其他']
        if request.qjlb not in valid_types:
            return {
                'success': False,
                'msg': '请假类别无效',
                'data': None
            }
        
        # 解析时间
        try:
            qjkssj = datetime.strptime(request.qjkssj, '%Y-%m-%d %H:%M:%S')
            qjjssj = datetime.strptime(request.qjjssj, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return {
                'success': False,
                'msg': '时间格式错误，请使用 YYYY-MM-DD HH:MM:SS 格式',
                'data': None
            }
        
        # 验证时间
        if qjkssj >= qjjssj:
            return {
                'success': False,
                'msg': '请假结束时间必须晚于开始时间',
                'data': None
            }
        
        # 创建请假记录
        new_leave = ZzXsQxj(
            xm=xm,
            xh=xh,
            bj_id=bj_id,
            qjlb=request.qjlb,
            qjsy=request.qjsy,
            qjsqsj=datetime.now(),
            qjkssj=qjkssj,
            qjjssj=qjjssj,
            xslxxl=request.xslxxl,
            xslxjtgj=request.xslxjtgj,
            sp_bzr_tid=sp_bzr_tid,  # 班主任ID
            sp_bzr_xm=sp_bzr_xm,    # 班主任姓名
            bzr_zt=0,  # 班主任审批状态：审批中
            xsk_zt=0,  # 学生科审批状态：审批中
            xj_zt=0    # 销假状态：未销假
        )
        
        db.add(new_leave)
        db.commit()
        db.refresh(new_leave)
        
        # 发送短信通知班主任
        try:
            if sp_bzr_tid:
                # 查询班主任手机号
                from models.models import Teacher
                teacher = db.query(Teacher).filter(Teacher.t_id == sp_bzr_tid).first()
                if teacher and teacher.t_dh:
                    from utils.sms_tencent import SMSTencentTool
                    sms_tool = SMSTencentTool()
                    
                    # 格式化时间（不带年份，与留宿场景的时间格式保持一致，
                    # 避免同一模板下变量长度差异过大）
                    qjkssj = qjkssj.strftime('%m-%d %H:%M')
                    qjjssj = qjjssj.strftime('%m-%d %H:%M')

                    # 发送短信
                    sms_result = sms_tool.send_by_scenario(
                        scenario='student_leave_teacher',
                        mobile=teacher.t_dh,
                        values={
                            'name': xm,
                            'student_id': xh,
                            'apply_type': request.qjlb,
                            'period': f'{qjkssj}至{qjjssj}',
                        },
                        xs_id=student.id,
                        xs_xm=student.xm,
                        userid=(teacher.t_yhm or str(teacher.t_id)),
                        username=teacher.t_xm,
                    )
                    if sms_result.get('success'):
                        logger.info(f"请假申请短信发送成功: 班主任={sp_bzr_xm}, 手机号={teacher.t_dh}")
                    else:
                        logger.warning(f"请假申请短信发送失败: {sms_result.get('msg')}")
                else:
                    logger.warning(f"班主任手机号不存在，无法发送短信: 班主任ID={sp_bzr_tid}")
        except Exception as sms_error:
            # 短信发送失败不影响请假申请流程
            logger.error(f"发送请假申请短信异常: {str(sms_error)}")
        
        return {
            'success': True,
            'msg': '请假申请提交成功',
            'data': {
                'leave_id': new_leave.id
            }
        }
    except Exception as e:
        db.rollback()
        logger.error(f"申请请假失败: {str(e)}")
        return {
            'success': False,
            'msg': f'申请请假失败: {str(e)}',
            'data': None
        }


@router.get('/check_access_record/{leave_id}')
async def check_access_record(
    leave_id: int,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """查询门禁记录（销假前验证）"""
    try:
        xh = current_user.get('xs_xh')
        
        # 查询请假记录
        leave = db.query(ZzXsQxj).filter(
            ZzXsQxj.id == leave_id,
            ZzXsQxj.xh == xh
        ).first()
        
        if not leave:
            return {
                'success': False,
                'msg': '请假记录不存在',
                'data': None
            }
        
        # 查询门禁记录（使用学号和姓名）
        from utils.access_control import access_control_api
        
        now = datetime.now()
        # 计算查询时间范围：从申请开始时间到现在，但不超过3个月
        start_time = leave.qjkssj
        time_diff = now - start_time
        if time_diff > timedelta(days=90):
            start_time = now - timedelta(days=90)
        logger.info(f"数据库时间: {start_time} ~ {now}")
        access_result = await access_control_api.check_return_record(
            student_id=xh,
            person_name=leave.xm,
            start_time=start_time,
            end_time=now
        )
        
        return {
            'success': True,
            'msg': '查询成功',
            'data': {
                'access_check': access_result
            }
        }
    except Exception as e:
        logger.error(f"查询门禁记录失败: {str(e)}")
        return {
            'success': False,
            'msg': f'查询门禁记录失败: {str(e)}',
            'data': None
        }


@router.post('/cancel')
async def cancel_leave(
    request: LeaveCancelRequest,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """销假"""
    try:
        xh = current_user.get('xs_xh')
        
        # 查询请假记录
        leave = db.query(ZzXsQxj).filter(
            ZzXsQxj.id == request.leave_id,
            ZzXsQxj.xh == xh
        ).first()
        
        if not leave:
            return {
                'success': False,
                'msg': '请假记录不存在',
                'data': None
            }
        
        # 检查是否已销假
        if leave.xj_zt == 1:
            return {
                'success': False,
                'msg': '该请假记录已销假',
                'data': None
            }
        
        # 检查审批状态：班主任和学生科都必须审批通过
        if leave.bzr_zt != 1 or leave.xsk_zt != 1:
            return {
                'success': False,
                'msg': '请假申请尚未全部审批通过，无法销假',
                'data': None
            }
        
        # 检查是否在请假时段内
        now = datetime.now()
        if now < leave.qjkssj:
            return {
                'success': False,
                'msg': '请假尚未开始，无法销假',
                'data': None
            }
        
        # 查询门禁记录，验证学生是否有回校记录（使用学号和姓名）
        from utils.access_control import access_control_api
        
        # 计算查询时间范围：从申请开始时间到现在，但不超过3个月
        start_time = leave.qjkssj
        time_diff = now - start_time
        if time_diff > timedelta(days=90):
            start_time = now - timedelta(days=90)
        
        access_result = await access_control_api.check_return_record(
            student_id=xh,
            person_name=leave.xm,
            start_time=start_time,
            end_time=now
        )
        
        # 验证是否有回校记录
        if not access_result.get('has_return'):
            return {
                'success': False,
                'msg': f"未检测到回校记录，无法销假。{access_result.get('message', '')}",
                'data': {
                    'access_check': access_result
                }
            }
        
        logger.info(f"学生 {leave.xm} 销假验证通过，回校时间: {access_result.get('return_time')}")
        
        # 更新销假信息
        leave.xj_zt = 1
        leave.xjsj = now
        leave.xsfxxl = request.xsfxxl
        leave.xsfxjtgj = request.xsfxjtgj
        
        db.commit()
        
        return {
            'success': True,
            'msg': f"销假成功。{access_result.get('message', '')}",
            'data': {
                'access_check': access_result
            }
        }
    except Exception as e:
        db.rollback()
        logger.error(f"销假失败: {str(e)}")
        return {
            'success': False,
            'msg': f'销假失败: {str(e)}',
            'data': None
        }


@router.put('/update/{leave_id}')
async def update_leave(
    leave_id: int,
    request: LeaveApplyRequest,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """修改请假申请（仅在未审批时可修改）"""
    try:
        xh = current_user.get('xs_xh')
        
        # 查询请假记录
        leave = db.query(ZzXsQxj).filter(
            ZzXsQxj.id == leave_id,
            ZzXsQxj.xh == xh
        ).first()
        
        if not leave:
            return {
                'success': False,
                'msg': '请假记录不存在',
                'data': None
            }
        
        # 检查是否已有审批（任一审批状态不为0则不能修改）
        if leave.bzr_zt != 0 or leave.xsk_zt != 0:
            return {
                'success': False,
                'msg': '请假申请已有审批记录，无法修改',
                'data': None
            }
        
        # 验证请假类别
        valid_types = ['病假', '事假', '其他']
        if request.qjlb not in valid_types:
            return {
                'success': False,
                'msg': '请假类别无效',
                'data': None
            }
        
        # 解析时间
        try:
            qjkssj = datetime.strptime(request.qjkssj, '%Y-%m-%d %H:%M:%S')
            qjjssj = datetime.strptime(request.qjjssj, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return {
                'success': False,
                'msg': '时间格式错误，请使用 YYYY-MM-DD HH:MM:SS 格式',
                'data': None
            }
        
        # 验证时间
        if qjkssj >= qjjssj:
            return {
                'success': False,
                'msg': '请假结束时间必须晚于开始时间',
                'data': None
            }
        
        # 更新请假信息
        leave.qjlb = request.qjlb
        leave.qjsy = request.qjsy
        leave.qjkssj = qjkssj
        leave.qjjssj = qjjssj
        leave.xslxxl = request.xslxxl
        leave.xslxjtgj = request.xslxjtgj
        
        db.commit()
        
        return {
            'success': True,
            'msg': '修改请假申请成功',
            'data': None
        }
    except Exception as e:
        db.rollback()
        logger.error(f"修改请假申请失败: {str(e)}")
        return {
            'success': False,
            'msg': f'修改请假申请失败: {str(e)}',
            'data': None
        }
