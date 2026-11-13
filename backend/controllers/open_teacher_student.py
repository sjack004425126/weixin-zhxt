from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import case, func, or_, and_
from models.models import Teacher, Student, Class, TzdCjZJsh, bk_bkb, lw_sys, BannedWord, SMSLog
from init.dependencies import DatabaseDep
from common.auth import verify_token_and_get_payload
from controllers.login import calculate_current_term
from datetime import datetime
import logging
import re

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/open_teacher", tags=["开放教育教师-学生管理"])


@router.get('/classes')
async def get_classes(
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """获取教师担任班主任的班级列表"""
    try:
        t_id = current_user.get('t_id')
        class_list = db.query(Class).filter(
            Class.bj_bzr_id == t_id,
            or_(Class.bj_isblock == 0, Class.bj_isblock == None)
        ).order_by(Class.bj_nd.desc(), Class.bj_mc).all()

        classes = [{'id': c.bj_id, 'name': c.bj_mc} for c in class_list]
        return {'success': True, 'msg': '获取成功', 'data': classes}
    except Exception as e:
        logger.error(f"获取班级列表失败: {str(e)}")
        return {'success': False, 'msg': f'获取失败: {str(e)}', 'data': None}


@router.get('/students')
async def get_student_list(
    bj_id: Optional[int] = Query(None, description="班级ID，不传则查全部"),
    xjzt_filter: Optional[str] = Query(None, description="学籍状态筛选"),
    keyword: Optional[str] = Query(None, description="搜索关键词（学号/姓名/电话）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(80, ge=1, le=200),
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """获取学生列表（分页）"""
    try:
        t_id = current_user.get('t_id')

        # 获取教师所有班级ID
        teacher_classes = db.query(Class).filter(
            Class.bj_bzr_id == t_id,
            or_(Class.bj_isblock == 0, Class.bj_isblock == None)
        ).all()
        teacher_bj_ids = [c.bj_id for c in teacher_classes]

        if bj_id:
            if bj_id not in teacher_bj_ids:
                return {'success': False, 'msg': '无权限查看该班级', 'data': None}
            query_bj_ids = [bj_id]
        else:
            query_bj_ids = teacher_bj_ids

        if not query_bj_ids:
            return {'success': True, 'msg': '获取成功', 'data': {'students': [], 'total': 0, 'all_count': 0, 'page': page, 'page_size': page_size, 'xjzt_stats': {}}}

        query = db.query(Student).filter(Student.xs_bj_id.in_(query_bj_ids))

        if xjzt_filter:
            query = query.filter(Student.xs_xjzt == xjzt_filter)

        if keyword and keyword.strip():
            kw = keyword.strip()
            query = query.filter(
                or_(
                    Student.xs_xm.like(f'%{kw}%'),
                    Student.xs_xh.like(f'%{kw}%'),
                    Student.xs_dh.like(f'%{kw}%')
                )
            )

        total = query.count()
        students = query.order_by(Student.xs_id.desc()).offset((page - 1) * page_size).limit(page_size).all()

        # 统计各学籍状态人数（全班级）
        all_count = db.query(Student).filter(Student.xs_bj_id.in_(query_bj_ids)).count()
        xjzt_stats_raw = db.query(Student.xs_xjzt, func.count(Student.xs_id)).filter(
            Student.xs_bj_id.in_(query_bj_ids)
        ).group_by(Student.xs_xjzt).all()
        xjzt_stats = {}
        for k, v in xjzt_stats_raw:
            if k is not None:
                xjzt_stats[k] = v

        # 获取照片URL
        from controllers.photo_upload import get_signed_photo_url

        # 班级名称映射（截取到"科"字为止，如"2022秋学前教育专科"）
        class_name_map = {}
        for c in teacher_classes:
            name = c.bj_mc or ''
            idx = name.find('科')
            if idx >= 0:
                name = name[:idx + 1]
            class_name_map[c.bj_id] = name

        student_list = []
        for s in students:
            photo_url = None
            if s.headphoto == 1 and s.xs_sfzh:
                photo_url = get_signed_photo_url(s.xs_sfzh, user_type="open")
            student_list.append({
                'id': s.xs_id,
                'xm': s.xs_xm,
                'xh': s.xs_xh,
                'xb': s.xs_xb,
                'sfzh': s.xs_sfzh,
                'dh': s.xs_dh,
                'mz': s.xs_mz,
                'xjzt': s.xs_xjzt,
                'headphoto': s.headphoto or 0,
                'photo_url': photo_url,
                'class_name': class_name_map.get(s.xs_bj_id, ''),
            })

        return {
            'success': True,
            'msg': '获取成功',
            'data': {
                'students': student_list,
                'total': total,
                'all_count': all_count,
                'page': page,
                'page_size': page_size,
                'xjzt_stats': xjzt_stats
            }
        }
    except Exception as e:
        logger.error(f"获取学生列表失败: {str(e)}")
        return {'success': False, 'msg': f'获取失败: {str(e)}', 'data': None}


@router.get('/student/detail')
async def get_student_detail(
    student_id: int = Query(..., description="学生ID"),
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """获取学生详细信息"""
    try:
        t_id = current_user.get('t_id')
        student = db.query(Student).filter(Student.xs_id == student_id).first()
        if not student:
            return {'success': False, 'msg': '学生不存在', 'data': None}

        # 验证班级归属
        bj = db.query(Class).filter(
            Class.bj_id == student.xs_bj_id, Class.bj_bzr_id == t_id
        ).first()
        if not bj:
            return {'success': False, 'msg': '无权限查看该学生', 'data': None}

        from controllers.photo_upload import get_signed_photo_url
        photo_url = None
        if student.headphoto == 1 and student.xs_sfzh:
            photo_url = get_signed_photo_url(student.xs_sfzh, user_type="open")

        return {
            'success': True,
            'msg': '获取成功',
            'data': {
                'id': student.xs_id,
                'xm': student.xs_xm,
                'xh': student.xs_xh,
                'xb': student.xs_xb,
                'mz': student.xs_mz,
                'sfzh': student.xs_sfzh,
                'dh': student.xs_dh,
                'xjzt': student.xs_xjzt,
                'class_name': bj.bj_mc if bj else '',
                'zy': bj.bj_zy if bj else '',
                'cc': bj.bj_cc if bj else '',
                'headphoto': student.headphoto or 0,
                'photo_url': photo_url,
                'dzzch': student.xs_dzzch,
            }
        }
    except Exception as e:
        logger.error(f"获取学生详情失败: {str(e)}")
        return {'success': False, 'msg': f'获取失败: {str(e)}', 'data': None}


class BatchSmsRequest(BaseModel):
    bj_id: int
    student_ids: List[int]
    content: str


class UpdateStudentPhoneRequest(BaseModel):
    student_id: int
    new_phone: str  # 11 位手机号


@router.post('/student/update_phone')
async def update_student_phone(
    request: UpdateStudentPhoneRequest,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """班主任修改本班学生的联系电话

    - 仅允许修改本人担任班主任的班级学生
    - 仅校验 11 位大陆手机号格式
    - 记录原值与新值到 sms_log 表（lx=99 标记为电话修改），便于追溯
    """
    try:
        t_id = current_user.get('t_id')
        t_xm = current_user.get('t_xm', '')

        new_phone = (request.new_phone or '').strip()
        if not re.match(r'^1[3-9]\d{9}$', new_phone):
            return {'success': False, 'msg': '手机号格式不正确，需为 11 位 1[3-9] 开头的号码', 'data': None}

        student = db.query(Student).filter(Student.xs_id == request.student_id).first()
        if not student:
            return {'success': False, 'msg': '学生不存在', 'data': None}

        # 权限校验：该学生必须属于当前教师担任班主任的班级
        bj = db.query(Class).filter(
            Class.bj_id == student.xs_bj_id,
            Class.bj_bzr_id == t_id,
            or_(Class.bj_isblock == 0, Class.bj_isblock == None)
        ).first()
        if not bj:
            return {'success': False, 'msg': '无权限修改该学生', 'data': None}

        old_phone = student.xs_dh or ''
        if old_phone == new_phone:
            return {'success': True, 'msg': '手机号未变更', 'data': {'id': student.xs_id, 'dh': new_phone}}

        student.xs_dh = new_phone
        # 记录修改流水，便于审计（lx=99 表示教师修改学生电话）
        log = SMSLog(
            lx=99, t_id=t_id, t_xm=t_xm,
            fssj=datetime.now(), nr=f'修改联系电话：{old_phone} -> {new_phone}',
            xs_id=str(student.xs_id), xs_xm=student.xs_xm, xs_dh=new_phone,
            num=0, send_status='0', status_desc='教师修改学生电话'
        )
        db.add(log)
        db.commit()

        return {
            'success': True,
            'msg': '手机号已更新',
            'data': {'id': student.xs_id, 'dh': new_phone, 'old_phone': old_phone}
        }
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logger.error(f"更新学生电话失败: {str(e)}")
        return {'success': False, 'msg': f'更新失败: {str(e)}', 'data': None}


@router.post('/batch_sms')
async def batch_sms_notify(
    request: BatchSmsRequest,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """批量短信通知学生"""
    try:
        t_id = current_user.get('t_id')
        bj = db.query(Class).filter(
            Class.bj_id == request.bj_id, Class.bj_bzr_id == t_id
        ).first()
        if not bj:
            return {'success': False, 'msg': '无权限操作该班级', 'data': None}

        students = db.query(Student).filter(
            Student.xs_id.in_(request.student_ids),
            Student.xs_bj_id == request.bj_id
        ).all()

        if not students:
            return {'success': False, 'msg': '未找到学生', 'data': None}

        from utils.sms import SMSTool
        sms_tool = SMSTool()

        success_count = 0
        fail_count = 0
        no_phone_count = 0

        for s in students:
            phone = s.xs_dh
            if not phone:
                no_phone_count += 1
                continue
            try:
                result = sms_tool.send_by_scenario(
                    scenario='notify',
                    mobile=phone,
                    values={'content': request.content},
                    xs_id=str(s.xs_id), xs_xm=s.xs_xm,
                )
                if result.get('success'):
                    success_count += 1
                else:
                    fail_count += 1
            except Exception as e:
                logger.error(f"发送短信失败 {s.xs_xm}: {str(e)}")
                fail_count += 1

        return {
            'success': True,
            'msg': f'发送完成：成功{success_count}人，失败{fail_count}人，无号码{no_phone_count}人',
            'data': {
                'success_count': success_count,
                'fail_count': fail_count,
                'no_phone_count': no_phone_count
            }
        }
    except Exception as e:
        logger.error(f"批量短信通知失败: {str(e)}")
        return {'success': False, 'msg': f'发送失败: {str(e)}', 'data': None}


# ========== 毕业生登记表管理 ==========

@router.get('/graduate/list')
async def get_graduate_list(
    bj_id: Optional[int] = Query(None, description="班级ID，不传则查全部"),
    zt_filter: Optional[str] = Query(None, description="状态筛选: submitted/unsubmitted"),
    keyword: Optional[str] = Query(None, description="搜索关键词（学号/姓名/电话）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(80, ge=1, le=200),
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """获取班级学生的毕业生登记表状态列表（分页）"""
    try:
        from models.models import GraduateRegistration

        t_id = current_user.get('t_id')
        teacher_classes = db.query(Class).filter(
            Class.bj_bzr_id == t_id,
            or_(Class.bj_isblock == 0, Class.bj_isblock == None)
        ).all()
        teacher_bj_ids = [c.bj_id for c in teacher_classes]

        if bj_id:
            if bj_id not in teacher_bj_ids:
                return {'success': False, 'msg': '无权限查看该班级', 'data': None}
            query_bj_ids = [bj_id]
        else:
            query_bj_ids = teacher_bj_ids

        if not query_bj_ids:
            return {'success': True, 'msg': '获取成功', 'data': {'students': [], 'total': 0, 'all_count': 0, 'submitted_count': 0, 'unsubmitted_count': 0, 'page': page, 'page_size': page_size}}

        # 查询学生
        student_query = db.query(Student).filter(Student.xs_bj_id.in_(query_bj_ids))
        all_students = student_query.all()
        all_xh_list = [s.xs_xh for s in all_students if s.xs_xh]

        # 查询已提交的登记表
        submitted_regs = {}
        if all_xh_list:
            regs = db.query(GraduateRegistration).filter(
                GraduateRegistration.xh.in_(all_xh_list)
            ).all()
            for r in regs:
                submitted_regs[r.xh] = r

        # 构建完整列表
        full_list = []
        dh_map = {}
        for s in all_students:
            reg = submitted_regs.get(s.xs_xh)
            has_submitted = reg is not None and reg.zt == 1
            if s.xs_xh:
                dh_map[s.xs_xh] = s.xs_dh or ''
            full_list.append({
                'id': s.xs_id,
                'xm': s.xs_xm,
                'xh': s.xs_xh,
                'xjzt': s.xs_xjzt,
                'submitted': has_submitted,
                'tjsj': reg.tjsj.strftime('%Y-%m-%d') if reg and reg.tjsj else None,
            })

        # 统计
        all_count = len(all_students)
        submitted_count = sum(1 for s in all_students if submitted_regs.get(s.xs_xh) and submitted_regs[s.xs_xh].zt == 1)
        unsubmitted_count = all_count - submitted_count

        total = len(full_list)
        # 状态筛选
        if zt_filter == 'submitted':
            full_list = [s for s in full_list if s['submitted']]
            total = len(full_list)
        elif zt_filter == 'unsubmitted':
            full_list = [s for s in full_list if not s['submitted']]
            total = len(full_list)
        # 关键词搜索
        if keyword and keyword.strip():
            kw = keyword.strip().lower()
            full_list = [
                s for s in full_list
                if (s.get('xm') and kw in s['xm'].lower())
                or (s.get('xh') and kw in s['xh'].lower())
                or (dh_map.get(s.get('xh') or '', '') and kw in dh_map[s['xh']].lower())
            ]
            total = len(full_list)
        # 按ID逆序排序
        full_list.sort(key=lambda x: x['id'], reverse=True)
        # 分页
        start = (page - 1) * page_size
        paged_list = full_list[start:start + page_size]

        return {
            'success': True,
            'msg': '获取成功',
            'data': {
                'students': paged_list,
                'total': total,
                'all_count': all_count,
                'submitted_count': submitted_count,
                'unsubmitted_count': unsubmitted_count,
                'page': page,
                'page_size': page_size
            }
        }
    except Exception as e:
        logger.error(f"获取毕业生登记表列表失败: {str(e)}")
        return {'success': False, 'msg': f'获取失败: {str(e)}', 'data': None}


# ========== 毕业证领取管理 ==========

@router.get('/diploma/list')
async def get_diploma_list(
    bj_id: Optional[int] = Query(None, description="班级ID，不传则查全部"),
    zt_filter: Optional[str] = Query(None, description="状态筛选: received/unreceived/norecord"),
    keyword: Optional[str] = Query(None, description="搜索关键词（学号/姓名/电话）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(80, ge=1, le=200),
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """获取班级学生的毕业证领取状态列表（分页）"""
    try:
        from sqlalchemy import text as sa_text

        t_id = current_user.get('t_id')
        teacher_classes = db.query(Class).filter(
            Class.bj_bzr_id == t_id,
            or_(Class.bj_isblock == 0, Class.bj_isblock == None)
        ).all()
        teacher_bj_ids = [c.bj_id for c in teacher_classes]

        if bj_id:
            if bj_id not in teacher_bj_ids:
                return {'success': False, 'msg': '无权限查看该班级', 'data': None}
            query_bj_ids = [bj_id]
        else:
            query_bj_ids = teacher_bj_ids

        if not query_bj_ids:
            return {'success': True, 'msg': '获取成功', 'data': {'students': [], 'total': 0, 'all_count': 0, 'received_count': 0, 'unreceived_count': 0, 'norecord_count': 0, 'page': page, 'page_size': page_size}}

        # 查询学生
        all_students = db.query(Student).filter(Student.xs_bj_id.in_(query_bj_ids)).all()
        all_xh_list = [s.xs_xh for s in all_students if s.xs_xh]

        # 查询毕业证名单
        diploma_map = {}
        if all_xh_list:
            placeholders = ','.join([f':xh{i}' for i in range(len(all_xh_list))])
            params = {f'xh{i}': xh for i, xh in enumerate(all_xh_list)}
            sql = sa_text(f"SELECT xh, xm, zt, lqsj, zsbh, cc, zymc, bypc FROM by_byzmd WHERE xh IN ({placeholders})")
            rows = db.execute(sql, params).fetchall()
            for r in rows:
                diploma_map[r.xh] = r

        # 构建列表并筛选
        full_list = []
        dh_map = {}
        received_count = 0
        unreceived_count = 0
        norecord_count = 0

        for s in all_students:
            if s.xs_xh:
                dh_map[s.xs_xh] = s.xs_dh or ''
            diploma = diploma_map.get(s.xs_xh)
            if diploma:
                is_received = diploma.zt == 1
                if is_received:
                    received_count += 1
                else:
                    unreceived_count += 1
                status = 'received' if is_received else 'unreceived'
            else:
                norecord_count += 1
                status = 'norecord'

            full_list.append({
                'id': s.xs_id,
                'xm': s.xs_xm,
                'xh': s.xs_xh,
                'xjzt': s.xs_xjzt,
                'status': status,
                'zsbh': diploma.zsbh if diploma else None,
                'lqsj': diploma.lqsj.strftime('%Y-%m-%d') if diploma and diploma.lqsj else None,
            })

        all_count = len(all_students)
        # 状态筛选
        if zt_filter:
            full_list = [s for s in full_list if s['status'] == zt_filter]
        # 关键词搜索
        if keyword and keyword.strip():
            kw = keyword.strip().lower()
            full_list = [
                s for s in full_list
                if (s.get('xm') and kw in s['xm'].lower())
                or (s.get('xh') and kw in s['xh'].lower())
                or (dh_map.get(s.get('xh') or '', '') and kw in dh_map[s['xh']].lower())
            ]
        total = len(full_list)
        # 按ID逆序排序
        full_list.sort(key=lambda x: x['id'], reverse=True)
        start = (page - 1) * page_size
        paged_list = full_list[start:start + page_size]

        return {
            'success': True,
            'msg': '获取成功',
            'data': {
                'students': paged_list,
                'total': total,
                'all_count': all_count,
                'received_count': received_count,
                'unreceived_count': unreceived_count,
                'norecord_count': norecord_count,
                'page': page,
                'page_size': page_size
            }
        }
    except Exception as e:
        logger.error(f"获取毕业证领取列表失败: {str(e)}")
        return {'success': False, 'msg': f'获取失败: {str(e)}', 'data': None}


# ========== 书费退费管理 ==========

@router.get('/refund/list')
async def get_refund_list(
    bj_id: Optional[int] = Query(None, description="班级ID，不传则查全部"),
    status_filter: Optional[int] = Query(None, description="状态筛选: 0/1/2/3/-2(无记录)"),
    keyword: Optional[str] = Query(None, description="搜索关键词（学号/姓名/电话）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(80, ge=1, le=200),
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """获取班级学生的书费退费列表（分页）"""
    try:
        from models.models import WxxsSfTkpayinfo

        t_id = current_user.get('t_id')
        teacher_classes = db.query(Class).filter(
            Class.bj_bzr_id == t_id,
            or_(Class.bj_isblock == 0, Class.bj_isblock == None)
        ).all()
        teacher_bj_ids = [c.bj_id for c in teacher_classes]

        if bj_id:
            if bj_id not in teacher_bj_ids:
                return {'success': False, 'msg': '无权限查看该班级', 'data': None}
            query_bj_ids = [bj_id]
        else:
            query_bj_ids = teacher_bj_ids

        if not query_bj_ids:
            return {'success': True, 'msg': '获取成功', 'data': {'students': [], 'total': 0, 'page': page, 'page_size': page_size, 'stats': {}}}

        # 查询学生
        all_students = db.query(Student).filter(Student.xs_bj_id.in_(query_bj_ids)).all()
        all_xh_list = [s.xs_xh for s in all_students if s.xs_xh]

        # 查询退费记录
        refund_map = {}
        if all_xh_list:
            records = db.query(WxxsSfTkpayinfo).filter(
                WxxsSfTkpayinfo.o_xh.in_(all_xh_list)
            ).all()
            for r in records:
                refund_map[r.o_xh] = r

        # 状态文本映射
        status_text_map = {
            0: '未申请', 1: '已申请', 2: '待确认', 3: '已完成', -1: '失败'
        }

        # 构建列表
        full_list = []
        dh_map = {}
        stats = {'total': 0, 'no_record': 0, 's0': 0, 's1': 0, 's2': 0, 's3': 0, 's_fail': 0}

        for s in all_students:
            if s.xs_xh:
                dh_map[s.xs_xh] = s.xs_dh or ''
            refund = refund_map.get(s.xs_xh)
            if refund:
                st = refund.o_status if refund.o_status is not None else 0
                if st == 0:
                    stats['s0'] += 1
                elif st == 1:
                    stats['s1'] += 1
                elif st == 2:
                    stats['s2'] += 1
                elif st == 3:
                    stats['s3'] += 1
                else:
                    stats['s_fail'] += 1
            else:
                st = None
                stats['no_record'] += 1

            full_list.append({
                'id': s.xs_id,
                'xm': s.xs_xm,
                'xh': s.xs_xh,
                'status': st,
                'status_text': status_text_map.get(st, '无记录') if st is not None else '无记录',
                'money': round(refund.o_money / 100, 2) if refund and refund.o_money else 0,
                'payment_time': refund.o_payment_time.strftime('%Y-%m-%d') if refund and refund.o_payment_time else None,
                'out_bill_no': refund.o_out_bill_no if refund else None,
            })

        stats['total'] = len(all_students)
        # 状态筛选
        if status_filter is not None:
            if status_filter == -2:
                full_list = [s for s in full_list if s['status'] is None]
            else:
                full_list = [s for s in full_list if s['status'] == status_filter]
        # 关键词搜索
        if keyword and keyword.strip():
            kw = keyword.strip().lower()
            full_list = [
                s for s in full_list
                if (s.get('xm') and kw in s['xm'].lower())
                or (s.get('xh') and kw in s['xh'].lower())
                or (dh_map.get(s.get('xh') or '', '') and kw in dh_map[s['xh']].lower())
            ]
        total = len(full_list)
        # 按ID逆序排序
        full_list.sort(key=lambda x: x['id'], reverse=True)
        start = (page - 1) * page_size
        paged_list = full_list[start:start + page_size]

        return {
            'success': True,
            'msg': '获取成功',
            'data': {
                'students': paged_list,
                'total': total,
                'page': page,
                'page_size': page_size,
                'stats': stats
            }
        }
    except Exception as e:
        logger.error(f"获取书费退费列表失败: {str(e)}")
        return {'success': False, 'msg': f'获取失败: {str(e)}', 'data': None}


# ========== 报考管理 ==========

def _is_fail_score(zhcj):
    """判断成绩是否不及格"""
    if zhcj is None or zhcj == '' or zhcj == 'NULL':
        return True
    try:
        return float(zhcj) < 60
    except (ValueError, TypeError):
        return True


@router.get('/exam/list')
async def get_exam_list(
    bj_id: Optional[int] = Query(None, description="班级ID，不传则查全部"),
    status_filter: Optional[str] = Query(None, description="状态筛选: registered/unregistered/partial"),
    keyword: Optional[str] = Query(None, description="搜索关键词（学号/姓名/电话）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(80, ge=1, le=200),
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """获取班级学生的报考管理列表（按学生分组，显示不及格科目数量和报考状态）"""
    try:
        t_id = current_user.get('t_id')
        teacher_classes = db.query(Class).filter(
            Class.bj_bzr_id == t_id,
            or_(Class.bj_isblock == 0, Class.bj_isblock == None)
        ).all()
        teacher_bj_ids = [c.bj_id for c in teacher_classes]

        if bj_id:
            if bj_id not in teacher_bj_ids:
                return {'success': False, 'msg': '无权限查看该班级', 'data': None}
            query_bj_ids = [bj_id]
        else:
            query_bj_ids = teacher_bj_ids

        if not query_bj_ids:
            return {'success': True, 'msg': '获取成功', 'data': {'students': [], 'total': 0, 'page': page, 'page_size': page_size, 'stats': {}}}

        # 获取系统当前批次
        sys_info = db.query(lw_sys).first()
        current_pc = sys_info.sys_pc if sys_info else None

        # 查询不及格科目记录
        fail_records = db.query(TzdCjZJsh).filter(
            TzdCjZJsh.bjid.in_(query_bj_ids)
        ).all()

        fail_records = [r for r in fail_records if _is_fail_score(r.zhcj)]

        # 获取学生
        all_students = db.query(Student).filter(Student.xs_bj_id.in_(query_bj_ids)).all()
        student_map = {s.xs_xh: s for s in all_students if s.xs_xh}

        # 按学号分组不及格科目
        student_fail_map = {}
        for r in fail_records:
            if r.xh not in student_fail_map:
                student_fail_map[r.xh] = []
            student_fail_map[r.xh].append(r)

        # 批量查询报考记录
        bk_map = {}
        if current_pc and fail_records:
            all_xh = list(set([r.xh for r in fail_records]))
            # 分批查询避免参数限制
            for i in range(0, len(all_xh), 500):
                batch_xh = all_xh[i:i+500]
                bk_records = db.query(bk_bkb).filter(
                    and_(bk_bkb.xsxh.in_(batch_xh), bk_bkb.pc == current_pc)
                ).all()
                for bk in bk_records:
                    key = (bk.xsxh, bk.kcid)
                    bk_map[key] = bk

        # 构建学生列表
        full_list = []
        dh_map = {}
        stats = {'total': 0, 'has_fail': 0, 'no_fail': 0, 'all_registered': 0, 'partial': 0, 'none_registered': 0}

        for s in all_students:
            xh = s.xs_xh
            if xh:
                dh_map[xh] = s.xs_dh or ''
            fails = student_fail_map.get(xh, [])
            fail_count = len(fails)

            if fail_count == 0:
                stats['no_fail'] += 1
                continue  # 没有不及格科目的学生不显示

            stats['has_fail'] += 1

            # 统计该学生的报考情况
            registered_count = 0
            paid_count = 0
            unpaid_count = 0
            for f in fails:
                bk = bk_map.get((xh, f.kcid))
                if bk:
                    registered_count += 1
                    if bk.ispay == 1:
                        paid_count += 1
                    else:
                        unpaid_count += 1

            unregistered_count = fail_count - registered_count

            if registered_count == fail_count:
                student_status = 'all_registered'
                stats['all_registered'] += 1
            elif registered_count == 0:
                student_status = 'none_registered'
                stats['none_registered'] += 1
            else:
                student_status = 'partial'
                stats['partial'] += 1

            full_list.append({
                'id': s.xs_id,
                'xm': s.xs_xm,
                'xh': xh,
                'fail_count': fail_count,
                'registered_count': registered_count,
                'paid_count': paid_count,
                'unpaid_count': unpaid_count,
                'unregistered_count': unregistered_count,
                'status': student_status,
            })

        stats['total'] = len(all_students)
        # 状态筛选
        if status_filter:
            full_list = [s for s in full_list if s['status'] == status_filter]
        # 关键词搜索
        if keyword and keyword.strip():
            kw = keyword.strip().lower()
            full_list = [
                s for s in full_list
                if (s.get('xm') and kw in s['xm'].lower())
                or (s.get('xh') and kw in s['xh'].lower())
                or (dh_map.get(s.get('xh') or '', '') and kw in dh_map[s['xh']].lower())
            ]
        total = len(full_list)
        # 按ID逆序排序
        full_list.sort(key=lambda x: x['id'], reverse=True)
        start = (page - 1) * page_size
        paged_list = full_list[start:start + page_size]

        return {
            'success': True,
            'msg': '获取成功',
            'data': {
                'students': paged_list,
                'total': total,
                'page': page,
                'page_size': page_size,
                'stats': stats
            }
        }
    except Exception as e:
        logger.error(f"获取报考管理列表失败: {str(e)}")
        return {'success': False, 'msg': f'获取失败: {str(e)}', 'data': None}


@router.get('/exam/detail')
async def get_exam_detail(
    xh: str = Query(..., description="学号"),
    bj_id: Optional[int] = Query(None, description="班级ID"),
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """获取某个学生的不及格科目详情及报考状态"""
    try:
        t_id = current_user.get('t_id')
        teacher_classes = db.query(Class).filter(
            Class.bj_bzr_id == t_id,
            or_(Class.bj_isblock == 0, Class.bj_isblock == None)
        ).all()
        teacher_bj_ids = [c.bj_id for c in teacher_classes]

        if not teacher_bj_ids:
            return {'success': False, 'msg': '无权限', 'data': None}

        sys_info = db.query(lw_sys).first()
        current_pc = sys_info.sys_pc if sys_info else None

        # 查询该学生所有不及格科目
        records = db.query(TzdCjZJsh).filter(TzdCjZJsh.bjid.in_(teacher_bj_ids), TzdCjZJsh.xh == xh).all()
        fail_records = [r for r in records if _is_fail_score(r.zhcj)]

        # 查询报考记录
        bk_records_map = {}
        if current_pc and fail_records:
            bk_list = db.query(bk_bkb).filter(
                and_(bk_bkb.xsxh == xh, bk_bkb.pc == current_pc)
            ).all()
            for bk in bk_list:
                bk_records_map[bk.kcid] = bk

        courses = []
        for r in fail_records:
            bk = bk_records_map.get(r.kcid)
            if bk:
                if bk.ispay == 1:
                    bk_status = '已支付'
                elif bk.ispay == 0:
                    bk_status = '未支付'
                elif bk.ispay == 2:
                    bk_status = '待支付'
                else:
                    bk_status = '已报考'
            else:
                bk_status = '未报考'

            courses.append({
                'kcid': r.kcid,
                'kcmc': r.kcmc,
                'zhcj': r.zhcj,
                'bk_status': bk_status,
            })

        return {
            'success': True,
            'msg': '获取成功',
            'data': {
                'xh': xh,
                'courses': courses,
                'total': len(courses)
            }
        }
    except Exception as e:
        logger.error(f"获取报考详情失败: {str(e)}")
        return {'success': False, 'msg': f'获取失败: {str(e)}', 'data': None}


# ========== 违禁词接口 ==========

@router.get('/banned_words')
async def get_banned_words(
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """获取所有banned状态的违禁词"""
    try:
        words = db.query(BannedWord).filter(BannedWord.status == 'banned').all()
        return {
            'success': True,
            'msg': '获取成功',
            'data': [{'id': w.id, 'word': w.word} for w in words]
        }
    except Exception as e:
        logger.error(f"获取违禁词失败: {str(e)}")
        return {'success': False, 'msg': f'获取失败: {str(e)}', 'data': None}


# ========== 短信发送（带日志记录） ==========

class SmsSendRequest(BaseModel):
    student_ids: List[int]
    content: str


@router.post('/send_sms')
async def send_sms_to_students(
    request: SmsSendRequest,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """向选中的学生发送短信，记录日志到sms_log表"""
    try:
        t_id = current_user.get('t_id')
        t_xm = current_user.get('t_xm', '')

        # 验证教师权限并获取学生
        teacher_classes = db.query(Class).filter(
            Class.bj_bzr_id == t_id,
            or_(Class.bj_isblock == 0, Class.bj_isblock == None)
        ).all()
        teacher_bj_ids = [c.bj_id for c in teacher_classes]

        if not teacher_bj_ids:
            return {'success': False, 'msg': '无权限', 'data': None}

        students = db.query(Student).filter(
            Student.xs_id.in_(request.student_ids),
            Student.xs_bj_id.in_(teacher_bj_ids)
        ).all()

        if not students:
            return {'success': False, 'msg': '未找到学生', 'data': None}

        from utils.sms import SMSTool
        sms_tool = SMSTool()

        success_count = 0
        fail_count = 0
        no_phone_count = 0

        for s in students:
            phone = s.xs_dh
            if not phone:
                no_phone_count += 1
                # 记录无号码日志
                log = SMSLog(
                    lx=3, t_id=t_id, t_xm=t_xm,
                    fssj=datetime.now(), nr=request.content,
                    xs_id=str(s.xs_id), xs_xm=s.xs_xm, xs_dh='',
                    num=1, send_status='-1', status_desc='无手机号'
                )
                db.add(log)
                continue
            try:
                result = sms_tool.send_by_scenario(
                    scenario='notify',
                    mobile=phone,
                    values={'content': request.content},
                    xs_id=str(s.xs_id), xs_xm=s.xs_xm, lx=3, t_id=t_id, t_xm=t_xm,
                )
                if result.get('success'):
                    success_count += 1
                else:
                    fail_count += 1
            except Exception as e:
                logger.error(f"发送短信失败 {s.xs_xm}: {str(e)}")
                fail_count += 1

        db.commit()

        return {
            'success': True,
            'msg': f'发送完成：成功{success_count}人，失败{fail_count}人，无号码{no_phone_count}人',
            'data': {
                'success_count': success_count,
                'fail_count': fail_count,
                'no_phone_count': no_phone_count
            }
        }
    except Exception as e:
        logger.error(f"短信发送失败: {str(e)}")
        return {'success': False, 'msg': f'发送失败: {str(e)}', 'data': None}


# ========== 班级管理 ==========

@router.get('/class/list')
async def get_class_list(
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """获取教师所有班级的统计信息（班级名称、人数、毕业人数、毕业率、学期）"""
    try:
        t_id = current_user.get('t_id')
        teacher_classes = db.query(Class).filter(
            Class.bj_bzr_id == t_id,
            or_(Class.bj_isblock == 0, Class.bj_isblock == None)
        ).order_by(Class.bj_nd.desc(), Class.bj_mc).all()

        if not teacher_classes:
            return {'success': True, 'msg': '获取成功', 'data': []}

        bj_ids = [c.bj_id for c in teacher_classes]

        # 查询系统学期信息（按地区）
        dq1_names = list(set(c.bj_dq1_mc for c in teacher_classes if c.bj_dq1_mc))
        sys_infos = db.query(lw_sys).filter(lw_sys.dq1_mc.in_(dq1_names)).all() if dq1_names else []
        sys_map = {s.dq1_mc: s for s in sys_infos}

        # 批量统计每个班级的总人数
        total_counts = db.query(
            Student.xs_bj_id, func.count(Student.xs_id)
        ).filter(Student.xs_bj_id.in_(bj_ids)).group_by(Student.xs_bj_id).all()
        total_map = {bj_id: cnt for bj_id, cnt in total_counts}

        # 批量统计每个班级的毕业人数 (xjzt=7)
        grad_counts = db.query(
            Student.xs_bj_id, func.count(Student.xs_id)
        ).filter(Student.xs_bj_id.in_(bj_ids), Student.xs_xjzt == '7').group_by(Student.xs_bj_id).all()
        grad_map = {bj_id: cnt for bj_id, cnt in grad_counts}

        result = []
        for c in teacher_classes:
            total = total_map.get(c.bj_id, 0)
            graduated = grad_map.get(c.bj_id, 0)
            rate = round(graduated / total * 100, 1) if total > 0 else 0

            # 计算当前学期
            current_term = None
            if c.bj_dq1_mc and c.bj_nd and c.bj_xqdm:
                sys_info = sys_map.get(c.bj_dq1_mc)
                if sys_info and sys_info.sys_xq1_nd and sys_info.sys_xq1_xq:
                    current_term = calculate_current_term(
                        sys_info.sys_xq1_nd, sys_info.sys_xq1_xq,
                        str(c.bj_nd), str(c.bj_xqdm)
                    )

            # 学期显示
            xq = ''
            if current_term:
                xq = f"第{current_term}学期"
            elif c.bj_nd:
                xq = f"{c.bj_nd}"
                if c.bj_xqdm:
                    xq += f"({c.bj_xqdm})"

            result.append({
                'id': c.bj_id,
                'name': c.bj_mc,
                'zy': c.bj_zy or '',
                'cc': c.bj_cc or '',
                'total': total,
                'graduated': graduated,
                'grad_rate': rate,
                'xq': xq,
            })

        return {'success': True, 'msg': '获取成功', 'data': result}
    except Exception as e:
        logger.error(f"获取班级列表失败: {str(e)}")
        return {'success': False, 'msg': f'获取失败: {str(e)}', 'data': None}


class ClassSmsSendRequest(BaseModel):
    class_ids: List[int]
    content: str


@router.post('/class/send_sms')
async def send_sms_to_classes(
    request: ClassSmsSendRequest,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """向选中班级的所有学生发送短信"""
    try:
        t_id = current_user.get('t_id')
        t_xm = current_user.get('t_xm', '')

        teacher_classes = db.query(Class).filter(
            Class.bj_bzr_id == t_id,
            Class.bj_id.in_(request.class_ids),
            or_(Class.bj_isblock == 0, Class.bj_isblock == None)
        ).all()

        if not teacher_classes:
            return {'success': False, 'msg': '无权限操作', 'data': None}

        valid_bj_ids = [c.bj_id for c in teacher_classes]
        students = db.query(Student).filter(Student.xs_bj_id.in_(valid_bj_ids)).all()

        if not students:
            return {'success': False, 'msg': '班级中没有学生', 'data': None}

        from utils.sms import SMSTool
        sms_tool = SMSTool()

        success_count = 0
        fail_count = 0
        no_phone_count = 0

        for s in students:
            phone = s.xs_dh
            if not phone:
                no_phone_count += 1
                log = SMSLog(
                    lx=3, t_id=t_id, t_xm=t_xm,
                    fssj=datetime.now(), nr=request.content,
                    xs_id=str(s.xs_id), xs_xm=s.xs_xm, xs_dh='',
                    num=1, send_status='-1', status_desc='无手机号'
                )
                db.add(log)
                continue
            try:
                result = sms_tool.send_by_scenario(
                    scenario='notify',
                    mobile=phone,
                    values={'content': request.content},
                    xs_id=str(s.xs_id), xs_xm=s.xs_xm, lx=3, t_id=t_id, t_xm=t_xm,
                )
                if result.get('success'):
                    success_count += 1
                else:
                    fail_count += 1
            except Exception as e:
                logger.error(f"发送短信失败 {s.xs_xm}: {str(e)}")
                fail_count += 1

        db.commit()

        return {
            'success': True,
            'msg': f'发送完成：成功{success_count}人，失败{fail_count}人，无号码{no_phone_count}人',
            'data': {'success_count': success_count, 'fail_count': fail_count, 'no_phone_count': no_phone_count}
        }
    except Exception as e:
        logger.error(f"班级短信发送失败: {str(e)}")
        return {'success': False, 'msg': f'发送失败: {str(e)}', 'data': None}


# ========== 形势与政策管理 ==========

@router.get('/xsyzc/list')
async def get_xsyzc_list(
    bj_id: Optional[int] = Query(None, description="班级ID，不传则查全部"),
    pass_counts: Optional[str] = Query(None, description="及格次数筛选，逗号分隔，如 1,2,3"),
    xjzt_filter: Optional[str] = Query(None, description="学籍状态筛选"),
    keyword: Optional[str] = Query(None, description="搜索关键词（学号/姓名/电话）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """获取班级学生形势与政策及格次数列表（分页）"""
    try:
        from models.models import SituationPolicyScore

        t_id = current_user.get('t_id')
        teacher_classes = db.query(Class).filter(
            Class.bj_bzr_id == t_id,
            or_(Class.bj_isblock == 0, Class.bj_isblock == None)
        ).all()
        teacher_bj_ids = [c.bj_id for c in teacher_classes]

        if bj_id:
            if bj_id not in teacher_bj_ids:
                return {'success': False, 'msg': '无权限查看该班级', 'data': None}
            query_bj_ids = [bj_id]
        else:
            query_bj_ids = teacher_bj_ids

        if not query_bj_ids:
            return {'success': True, 'msg': '获取成功', 'data': {'students': [], 'total': 0, 'all_count': 0, 'page': page, 'page_size': page_size, 'stats': {}, 'xjzt_stats': {}}}

        # 解析次数筛选
        filter_counts = None
        if pass_counts:
            try:
                filter_counts = [int(x.strip()) for x in pass_counts.split(',') if x.strip()]
            except ValueError:
                filter_counts = None

        # 查询所有学生
        all_students = db.query(Student).filter(Student.xs_bj_id.in_(query_bj_ids)).order_by(Student.xs_xh).all()
        all_xh_list = [s.xs_xh for s in all_students if s.xs_xh]

        if not all_xh_list:
            return {'success': True, 'msg': '获取成功', 'data': {'students': [], 'total': 0, 'all_count': 0, 'page': page, 'page_size': page_size, 'stats': {}, 'xjzt_stats': {}}}

        # 批量查询所有学生的形势与政策成绩（一次查询）
        all_scores = db.query(
            SituationPolicyScore.xh,
            SituationPolicyScore.cj
        ).filter(
            SituationPolicyScore.xh.in_(all_xh_list),
            SituationPolicyScore.cj.isnot(None)
        ).all()

        # 按学号分组，计算及格次数
        pass_count_map = {}
        for row in all_scores:
            cj_raw = row.cj
            if not cj_raw or cj_raw == '' or cj_raw == 'NULL':
                continue
            try:
                if float(cj_raw) >= 60:
                    pass_count_map[row.xh] = pass_count_map.get(row.xh, 0) + 1
            except (ValueError, TypeError):
                continue

        # 构建完整列表，同时统计学籍状态分布
        full_list = []
        stats = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        xjzt_stats = {}
        for s in all_students:
            cnt = pass_count_map.get(s.xs_xh, 0)
            stats[min(cnt, 5)] = stats.get(min(cnt, 5), 0) + 1
            xjzt = s.xs_xjzt or ''
            if xjzt:
                xjzt_stats[xjzt] = xjzt_stats.get(xjzt, 0) + 1
            full_list.append({
                'id': s.xs_id,
                'xm': s.xs_xm,
                'xh': s.xs_xh,
                'dh': s.xs_dh,
                'xjzt': xjzt,
                'pass_count': cnt,
            })

        # 学籍状态筛选
        if xjzt_filter:
            full_list = [s for s in full_list if s['xjzt'] == xjzt_filter]

        # 次数筛选
        if filter_counts is not None:
            full_list = [s for s in full_list if s['pass_count'] in filter_counts]

        # 关键词搜索（xsyzc 列表项已含 dh）
        if keyword and keyword.strip():
            kw = keyword.strip().lower()
            full_list = [
                s for s in full_list
                if (s.get('xm') and kw in s['xm'].lower())
                or (s.get('xh') and kw in s['xh'].lower())
                or (s.get('dh') and kw in (s['dh'] or '').lower())
            ]

        total = len(full_list)
        start = (page - 1) * page_size
        paged_list = full_list[start:start + page_size]

        return {
            'success': True,
            'msg': '获取成功',
            'data': {
                'students': paged_list,
                'total': total,
                'all_count': len(all_students),
                'page': page,
                'page_size': page_size,
                'stats': stats,
                'xjzt_stats': xjzt_stats,
            }
        }
    except Exception as e:
        logger.error(f"获取形势与政策列表失败: {str(e)}")
        return {'success': False, 'msg': f'获取失败: {str(e)}', 'data': None}
