"""学生留宿申请控制器"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_
from models.models import ZzSsLs, ZzXs, ZzBj, ZzSsLd, ZzSsLc, ZzSsSs, ZzSsCw
from init.dependencies import DatabaseDep
from common.auth import verify_token_and_get_payload
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/student/stay", tags=["学生留宿"])


class StayApplyRequest(BaseModel):
    ls_type: str = 'weekend'
    ls_reason: str
    start_date: str  # YYYY-MM-DD
    end_date: str    # YYYY-MM-DD


def get_student_dorm_info(db, student):
    """获取学生宿舍信息（通过床位表反向查询，不依赖 cw_id 字段）"""
    bed = db.query(ZzSsCw).filter(
        ZzSsCw.zsr_id == student.id,
        ZzSsCw.zsr_type == 'student',
        ZzSsCw.zt == 1
    ).first()
    if not bed:
        return None
    room = db.query(ZzSsSs).filter(ZzSsSs.id == bed.ss_id).first()
    floor = db.query(ZzSsLc).filter(ZzSsLc.id == room.lc_id).first() if room else None
    building = db.query(ZzSsLd).filter(ZzSsLd.id == floor.ld_id).first() if floor else None
    return {
        'ld_id': building.id if building else None,
        'ld_mc': building.mc if building else '',
        'ss_id': room.id if room else None,
        'ss_ssh': room.ssh if room else '',
        'cw_id': bed.id,
        'cw_cwh': bed.cwh,
        'full_name': f"{building.mc if building else ''} {room.ssh if room else ''}室 {bed.cwh}号床"
    }


@router.get('/list')
async def get_stay_list(
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """获取学生留宿记录"""
    try:
        xs_id = current_user.get('xs_id')
        
        # 自动将过期的待审批/已批准记录标记为过期（精确到秒）
        now = datetime.now()
        db.query(ZzSsLs).filter(
            ZzSsLs.xs_id == xs_id,
            ZzSsLs.status.in_([0, 1]),
            ZzSsLs.end_date < now
        ).update({ZzSsLs.status: 3, ZzSsLs.gxsj: now}, synchronize_session='fetch')
        db.commit()

        records = db.query(ZzSsLs).filter(
            ZzSsLs.xs_id == xs_id
        ).order_by(ZzSsLs.cjsj.desc()).all()

        result = []
        for r in records:
            result.append({
                'id': r.id,
                'ls_type': r.ls_type,
                'ls_reason': r.ls_reason,
                'start_date': r.start_date.strftime('%Y-%m-%d') if r.start_date else '',
                'end_date': r.end_date.strftime('%Y-%m-%d') if r.end_date else '',
                'status': r.status,
                'approve_by': r.approve_by,
                'approve_time': r.approve_time.strftime('%Y-%m-%d %H:%M') if r.approve_time else '',
                'approve_remark': r.approve_remark,
                'cjsj': r.cjsj.strftime('%Y-%m-%d %H:%M') if r.cjsj else '',
                'dorm_info': f"{r.ld_mc or ''} {r.ss_ssh or ''}室 {r.cw_cwh or ''}号床"
            })
        return {'success': True, 'msg': '获取成功', 'data': result}
    except Exception as e:
        logger.error(f"获取留宿记录失败: {str(e)}")
        return {'success': False, 'msg': f'获取失败: {str(e)}', 'data': []}


@router.get('/check_can_apply')
async def check_can_apply(
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """检查是否可以申请留宿（上一个未过期/未取消则不能申请）"""
    try:
        xs_id = current_user.get('xs_id')
        # 查找状态为 0-待审批 或 1-已批准 且结束日期未过期的记录（精确到秒）
        active = db.query(ZzSsLs).filter(
            ZzSsLs.xs_id == xs_id,
            ZzSsLs.status.in_([0, 1]),
            ZzSsLs.end_date >= datetime.now()
        ).first()
        return {
            'success': True, 'msg': '查询成功',
            'data': {'can_apply': active is None, 'active_id': active.id if active else None}
        }
    except Exception as e:
        logger.error(f"检查留宿申请状态失败: {str(e)}")
        return {'success': False, 'msg': f'查询失败: {str(e)}', 'data': {'can_apply': False}}


@router.post('/apply')
async def apply_stay(
    request: StayApplyRequest,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """申请留宿"""
    try:
        xs_id = current_user.get('xs_id')
        student = db.query(ZzXs).filter(ZzXs.id == xs_id).first()
        if not student:
            return {'success': False, 'msg': '学生不存在', 'data': None}

        # 检查是否有未完成的申请（精确到秒）
        active = db.query(ZzSsLs).filter(
            ZzSsLs.xs_id == xs_id,
            ZzSsLs.status.in_([0, 1]),
            ZzSsLs.end_date >= datetime.now()
        ).first()
        if active:
            return {'success': False, 'msg': '您有未完成的留宿申请，不能重复申请', 'data': None}

        # 获取宿舍信息
        bj = db.query(ZzBj).filter(ZzBj.id == student.bj_id).first()
        dorm = get_student_dorm_info(db, student)

        record = ZzSsLs(
            xs_id=student.id, xs_xm=student.xm, xs_xh=student.xh,
            bj_id=student.bj_id, bj_mc=bj.mc if bj else '',
            ld_id=dorm['ld_id'] if dorm else None,
            ld_mc=dorm['ld_mc'] if dorm else '',
            ss_id=dorm['ss_id'] if dorm else None,
            ss_ssh=dorm['ss_ssh'] if dorm else '',
            cw_id=dorm['cw_id'] if dorm else None,
            cw_cwh=dorm['cw_cwh'] if dorm else '',
            ls_type=request.ls_type,
            ls_reason=request.ls_reason,
            start_date=datetime.strptime(request.start_date, '%Y-%m-%d').replace(hour=0, minute=0, second=0),
            end_date=datetime.strptime(request.end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=0),
            status=0
        )
        db.add(record)
        db.commit()

        # 给班主任发短信提醒
        try:
            if bj:
                from models.models import Teacher
                teacher = db.query(Teacher).filter(Teacher.t_id == bj.bzr_id).first()
                if teacher and teacher.t_dh:
                    from utils.sms import SMSTool
                    sms = SMSTool()
                    sms.send_by_scenario(
                        scenario='student_stay_teacher',
                        mobile=teacher.t_dh,
                        values={
                            'name': student.xm,
                            'student_id': student.xh,
                            'apply_type': '留宿',
                            'period': f'{request.start_date}至{request.end_date}',
                        },
                        xs_id=student.xh, xs_xm=student.xm,
                        userid=(teacher.t_yhm or str(teacher.t_id)),
                        username=teacher.t_xm,
                    )
        except Exception as sms_err:
            logger.warning(f"留宿申请短信通知失败: {str(sms_err)}")

        return {'success': True, 'msg': '申请成功，等待班主任审批', 'data': None}
    except Exception as e:
        db.rollback()
        logger.error(f"留宿申请失败: {str(e)}")
        return {'success': False, 'msg': f'申请失败: {str(e)}', 'data': None}


class CancelStayRequest(BaseModel):
    id: int


@router.post('/cancel')
async def cancel_stay(
    request: CancelStayRequest,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """取消留宿申请"""
    try:
        xs_id = current_user.get('xs_id')
        record = db.query(ZzSsLs).filter(ZzSsLs.id == request.id, ZzSsLs.xs_id == xs_id).first()
        if not record:
            return {'success': False, 'msg': '记录不存在', 'data': None}
        if record.status not in [0]:
            return {'success': False, 'msg': '只能取消待审批的申请', 'data': None}
        record.status = 4
        record.gxsj = datetime.now()
        db.commit()
        return {'success': True, 'msg': '已取消', 'data': None}
    except Exception as e:
        db.rollback()
        logger.error(f"取消留宿申请失败: {str(e)}")
        return {'success': False, 'msg': f'取消失败: {str(e)}', 'data': None}


@router.get('/dorm_info')
async def get_my_dorm_info(
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """获取学生宿舍信息（通过床位表反向查询）"""
    try:
        xs_id = current_user.get('xs_id')
        student = db.query(ZzXs).filter(ZzXs.id == xs_id).first()
        if not student:
            return {'success': True, 'msg': '获取成功', 'data': None}
        dorm = get_student_dorm_info(db, student)
        return {'success': True, 'msg': '获取成功', 'data': dorm}
    except Exception as e:
        logger.error(f"获取宿舍信息失败: {str(e)}")
        return {'success': False, 'msg': f'获取失败: {str(e)}', 'data': None}
