from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from models.models import ZzSsLd, ZzSsLc, ZzSsSs, ZzSsCw, ZzXs, ZzBj
from init.dependencies import DatabaseDep
from common.auth import verify_token_and_get_payload
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dormitory", tags=["宿舍管理"])


# ========== 请求模型 ==========

class BuildingRequest(BaseModel):
    mc: str
    bz: Optional[str] = None
    px: Optional[int] = 0

class FloorRequest(BaseModel):
    ld_id: int
    lc: int
    bz: Optional[str] = None

class RoomRequest(BaseModel):
    lc_id: int
    ssh: str
    bz: Optional[str] = None

class BedRequest(BaseModel):
    ss_id: int
    cwh: str

class AssignBedRequest(BaseModel):
    student_id: int
    cw_id: Optional[int] = None  # None表示取消分配


# ========== 楼栋管理 ==========

@router.get('/buildings')
async def get_buildings(
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """获取楼栋列表"""
    try:
        buildings = db.query(ZzSsLd).filter(
            ZzSsLd.zt == 1
        ).order_by(ZzSsLd.px, ZzSsLd.id).all()

        result = []
        for b in buildings:
            # 统计楼栋下的宿舍数和入住人数
            floor_ids = [f.id for f in db.query(ZzSsLc).filter(ZzSsLc.ld_id == b.id, ZzSsLc.zt == 1).all()]
            room_count = 0
            bed_count = 0
            used_count = 0
            if floor_ids:
                rooms = db.query(ZzSsSs).filter(ZzSsSs.lc_id.in_(floor_ids), ZzSsSs.zt == 1).all()
                room_count = len(rooms)
                room_ids = [r.id for r in rooms]
                if room_ids:
                    bed_count = db.query(ZzSsCw).filter(ZzSsCw.ss_id.in_(room_ids), ZzSsCw.zt == 1).count()
                    # 统计已入住床位数（通过 zsr_id/zsr_type 反查）
                    used_count = db.query(ZzSsCw).filter(
                        ZzSsCw.ss_id.in_(room_ids),
                        ZzSsCw.zt == 1,
                        ZzSsCw.zsr_type == 'student',
                        ZzSsCw.zsr_id.isnot(None)
                    ).count()

            result.append({
                'id': b.id, 'mc': b.mc, 'bz': b.bz, 'px': b.px,
                'room_count': room_count, 'bed_count': bed_count, 'used_count': used_count
            })

        return {'success': True, 'msg': '获取成功', 'data': result}
    except Exception as e:
        logger.error(f"获取楼栋列表失败: {str(e)}")
        return {'success': False, 'msg': f'获取失败: {str(e)}', 'data': []}


@router.post('/building/add')
async def add_building(
    request: BuildingRequest,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """添加楼栋"""
    try:
        building = ZzSsLd(mc=request.mc, bz=request.bz, px=request.px)
        db.add(building)
        db.commit()
        db.refresh(building)
        return {'success': True, 'msg': '添加成功', 'data': {'id': building.id}}
    except Exception as e:
        db.rollback()
        logger.error(f"添加楼栋失败: {str(e)}")
        return {'success': False, 'msg': f'添加失败: {str(e)}', 'data': None}


@router.post('/building/update')
async def update_building(
    id: int,
    request: BuildingRequest,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """修改楼栋"""
    try:
        building = db.query(ZzSsLd).filter(ZzSsLd.id == id).first()
        if not building:
            return {'success': False, 'msg': '楼栋不存在', 'data': None}
        building.mc = request.mc
        building.bz = request.bz
        building.px = request.px
        db.commit()
        return {'success': True, 'msg': '修改成功', 'data': None}
    except Exception as e:
        db.rollback()
        logger.error(f"修改楼栋失败: {str(e)}")
        return {'success': False, 'msg': f'修改失败: {str(e)}', 'data': None}


@router.post('/building/delete')
async def delete_building(
    id: int,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """删除楼栋（软删除）"""
    try:
        building = db.query(ZzSsLd).filter(ZzSsLd.id == id).first()
        if not building:
            return {'success': False, 'msg': '楼栋不存在', 'data': None}
        building.zt = 0
        db.commit()
        return {'success': True, 'msg': '删除成功', 'data': None}
    except Exception as e:
        db.rollback()
        logger.error(f"删除楼栋失败: {str(e)}")
        return {'success': False, 'msg': f'删除失败: {str(e)}', 'data': None}


# ========== 楼层管理 ==========

@router.get('/floors')
async def get_floors(
    ld_id: int,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """获取楼层列表"""
    try:
        floors = db.query(ZzSsLc).filter(
            ZzSsLc.ld_id == ld_id, ZzSsLc.zt == 1
        ).order_by(ZzSsLc.lc).all()

        result = []
        for f in floors:
            room_count = db.query(ZzSsSs).filter(ZzSsSs.lc_id == f.id, ZzSsSs.zt == 1).count()
            result.append({'id': f.id, 'ld_id': f.ld_id, 'lc': f.lc, 'bz': f.bz, 'room_count': room_count})

        return {'success': True, 'msg': '获取成功', 'data': result}
    except Exception as e:
        logger.error(f"获取楼层列表失败: {str(e)}")
        return {'success': False, 'msg': f'获取失败: {str(e)}', 'data': []}


@router.post('/floor/add')
async def add_floor(
    request: FloorRequest,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """添加楼层"""
    try:
        existing = db.query(ZzSsLc).filter(
            ZzSsLc.ld_id == request.ld_id, ZzSsLc.lc == request.lc, ZzSsLc.zt == 1
        ).first()
        if existing:
            return {'success': False, 'msg': '该楼层已存在', 'data': None}
        floor = ZzSsLc(ld_id=request.ld_id, lc=request.lc, bz=request.bz)
        db.add(floor)
        db.commit()
        db.refresh(floor)
        return {'success': True, 'msg': '添加成功', 'data': {'id': floor.id}}
    except Exception as e:
        db.rollback()
        logger.error(f"添加楼层失败: {str(e)}")
        return {'success': False, 'msg': f'添加失败: {str(e)}', 'data': None}


@router.post('/floor/delete')
async def delete_floor(
    id: int,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """删除楼层（软删除）"""
    try:
        floor = db.query(ZzSsLc).filter(ZzSsLc.id == id).first()
        if not floor:
            return {'success': False, 'msg': '楼层不存在', 'data': None}
        floor.zt = 0
        db.commit()
        return {'success': True, 'msg': '删除成功', 'data': None}
    except Exception as e:
        db.rollback()
        logger.error(f"删除楼层失败: {str(e)}")
        return {'success': False, 'msg': f'删除失败: {str(e)}', 'data': None}


# ========== 宿舍管理 ==========

@router.get('/rooms')
async def get_rooms(
    lc_id: int,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """获取楼层下的宿舍列表（仅概要信息，不含床位详情）"""
    try:
        rooms = db.query(ZzSsSs).filter(
            ZzSsSs.lc_id == lc_id, ZzSsSs.zt == 1, ZzSsSs.kr == 1
        ).order_by(ZzSsSs.ssh).all()

        result = []
        for r in rooms:
            # 用子查询统计床位数和已入住数（避免加载所有床位对象）
            bed_count = db.query(func.count(ZzSsCw.id)).filter(
                ZzSsCw.ss_id == r.id, ZzSsCw.zt == 1
            ).scalar() or 0
            used_count = db.query(func.count(ZzSsCw.id)).filter(
                ZzSsCw.ss_id == r.id,
                ZzSsCw.zt == 1,
                ZzSsCw.zsr_type == 'student',
                ZzSsCw.zsr_id.isnot(None)
            ).scalar() or 0

            result.append({
                'id': r.id,
                'ssh': r.ssh,
                'bz': r.bz,
                'bed_count': bed_count,
                'used_count': used_count
            })

        return {'success': True, 'msg': '获取成功', 'data': result}
    except Exception as e:
        logger.error(f"获取宿舍列表失败: {str(e)}")
        return {'success': False, 'msg': f'获取失败: {str(e)}', 'data': []}


@router.get('/room/beds')
async def get_room_beds(
    ss_id: int,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """获取指定宿舍的床位及入住信息（按需加载，用户点击宿舍时才调用）"""
    try:
        room = db.query(ZzSsSs).filter(
            ZzSsSs.id == ss_id, ZzSsSs.zt == 1, ZzSsSs.kr == 1
        ).first()
        if not room:
            return {'success': False, 'msg': '宿舍不存在', 'data': None}

        beds = db.query(ZzSsCw).filter(
            ZzSsCw.ss_id == ss_id, ZzSsCw.zt == 1
        ).order_by(ZzSsCw.cwh).all()

        bed_list = []
        for bed in beds:
            # 通过 zsr_id/zsr_type 反查入住学生（权威字段）
            student = None
            if bed.zsr_type == 'student' and bed.zsr_id:
                student = db.query(ZzXs).filter(ZzXs.id == bed.zsr_id).first()
            bed_info = {
                'id': bed.id, 'cwh': bed.cwh,
                'student': None
            }
            if student:
                bj = db.query(ZzBj).filter(ZzBj.id == student.bj_id).first()
                bed_info['student'] = {
                    'id': student.id, 'xm': student.xm, 'xh': student.xh,
                    'bj_id': student.bj_id,
                    'bj_mc': bj.mc if bj else '',
                    'xsdh': student.xsdh or '',
                    'jzdh': student.jzdh or ''
                }
            bed_list.append(bed_info)

        return {
            'success': True, 'msg': '获取成功',
            'data': {
                'id': room.id,
                'ssh': room.ssh,
                'bz': room.bz,
                'beds': bed_list
            }
        }
    except Exception as e:
        logger.error(f"获取宿舍床位失败: {str(e)}")
        return {'success': False, 'msg': f'获取失败: {str(e)}', 'data': None}


@router.post('/room/add')
async def add_room(
    request: RoomRequest,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """添加宿舍"""
    try:
        room = ZzSsSs(lc_id=request.lc_id, ssh=request.ssh, bz=request.bz)
        db.add(room)
        db.commit()
        db.refresh(room)
        return {'success': True, 'msg': '添加成功', 'data': {'id': room.id}}
    except Exception as e:
        db.rollback()
        logger.error(f"添加宿舍失败: {str(e)}")
        return {'success': False, 'msg': f'添加失败: {str(e)}', 'data': None}


@router.post('/room/delete')
async def delete_room(
    id: int,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """删除宿舍（软删除）"""
    try:
        room = db.query(ZzSsSs).filter(ZzSsSs.id == id).first()
        if not room:
            return {'success': False, 'msg': '宿舍不存在', 'data': None}
        room.zt = 0
        db.commit()
        return {'success': True, 'msg': '删除成功', 'data': None}
    except Exception as e:
        db.rollback()
        logger.error(f"删除宿舍失败: {str(e)}")
        return {'success': False, 'msg': f'删除失败: {str(e)}', 'data': None}


# ========== 床位管理 ==========

@router.post('/bed/add')
async def add_bed(
    request: BedRequest,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """添加床位"""
    try:
        bed = ZzSsCw(ss_id=request.ss_id, cwh=request.cwh)
        db.add(bed)
        db.commit()
        db.refresh(bed)
        return {'success': True, 'msg': '添加成功', 'data': {'id': bed.id}}
    except Exception as e:
        db.rollback()
        logger.error(f"添加床位失败: {str(e)}")
        return {'success': False, 'msg': f'添加失败: {str(e)}', 'data': None}


@router.post('/bed/delete')
async def delete_bed(
    id: int,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """删除床位（软删除）"""
    try:
        bed = db.query(ZzSsCw).filter(ZzSsCw.id == id).first()
        if not bed:
            return {'success': False, 'msg': '床位不存在', 'data': None}
        # 先清除该床位上的学生关联（cw_id 是历史垃圾字段，一并清理）
        db.query(ZzXs).filter(ZzXs.cw_id == id).update({ZzXs.cw_id: None})
        # 清理床位上的住宿人冗余字段
        bed.zsr_id = None
        bed.zsr_type = None
        bed.zsr_xm = None
        bed.zt = 0
        db.commit()
        return {'success': True, 'msg': '删除成功', 'data': None}
    except Exception as e:
        db.rollback()
        logger.error(f"删除床位失败: {str(e)}")
        return {'success': False, 'msg': f'删除失败: {str(e)}', 'data': None}


# ========== 学生住宿分配 ==========

@router.post('/assign')
async def assign_bed(
    request: AssignBedRequest,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """分配/取消学生床位（以 zz_ss_cw 的 zsr_id/zsr_type/zsr_xm 为权威字段）"""
    try:
        student = db.query(ZzXs).filter(ZzXs.id == request.student_id).first()
        if not student:
            return {'success': False, 'msg': '学生不存在', 'data': None}

        # ========== 取消分配 ==========
        if request.cw_id is None:
            # 通过 zsr_id 反查学生当前所在床位
            old_bed = db.query(ZzSsCw).filter(
                ZzSsCw.zsr_id == student.id,
                ZzSsCw.zsr_type == 'student',
                ZzSsCw.zt == 1
            ).first()
            if old_bed:
                old_bed.zsr_id = None
                old_bed.zsr_type = None
                old_bed.zsr_xm = None
            # 兼容历史垃圾数据：如果 cw_id 还有值，一并清除
            if student.cw_id:
                student.cw_id = None
            db.commit()
            return {'success': True, 'msg': '已取消分配', 'data': None}

        # ========== 分配床位 ==========
        bed = db.query(ZzSsCw).filter(ZzSsCw.id == request.cw_id, ZzSsCw.zt == 1).first()
        if not bed:
            return {'success': False, 'msg': '床位不存在或已禁用', 'data': None}

        # 检查床位是否已被其他学生占用（以 zsr_id 为权威判断）
        if bed.zsr_type == 'student' and bed.zsr_id and bed.zsr_id != student.id:
            return {'success': False, 'msg': f'该床位已被 {bed.zsr_xm or bed.zsr_id} 占用', 'data': None}

        # 学生换床：先把旧床位上的冗余字段清除（通过 zsr_id 找旧床位）
        old_bed = db.query(ZzSsCw).filter(
            ZzSsCw.zsr_id == student.id,
            ZzSsCw.zsr_type == 'student',
            ZzSsCw.zt == 1,
            ZzSsCw.id != request.cw_id
        ).first()
        if old_bed:
            old_bed.zsr_id = None
            old_bed.zsr_type = None
            old_bed.zsr_xm = None
            db.flush()

        # 写权威字段：zz_ss_cw 的 zsr_id/zsr_type/zsr_xm
        bed.zsr_type = 'student'
        bed.zsr_id = student.id
        bed.zsr_xm = student.xm

        # 清掉 zz_xs.cw_id 这个垃圾字段（指向旧 ID 的冗余数据，避免误导）
        if student.cw_id:
            student.cw_id = None

        db.commit()
        return {'success': True, 'msg': '分配成功', 'data': None}
    except Exception as e:
        db.rollback()
        logger.error(f"分配床位失败: {str(e)}")
        return {'success': False, 'msg': f'分配失败: {str(e)}', 'data': None}


# ========== 按班级查看住宿情况 ==========

@router.get('/class_dormitory')
async def get_class_dormitory(
    bj_id: int,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """获取班级学生住宿情况"""
    try:
        bj_ids = current_user.get('bj_ids', [])
        if bj_id not in bj_ids:
            return {'success': False, 'msg': '无权限查看该班级', 'data': {'students': []}}

        students = db.query(ZzXs).filter(ZzXs.bj_id == bj_id).order_by(ZzXs.xb, ZzXs.xm).all()

        student_list = []
        for s in students:
            dorm_info = None
            # 通过 zz_ss_cw.zsr_id 反向匹配学生的床位，再找楼栋
            bed = db.query(ZzSsCw).filter(
                ZzSsCw.zsr_id == s.id,
                ZzSsCw.zsr_type == 'student',
                ZzSsCw.zt == 1
            ).first()
            if bed:
                room = db.query(ZzSsSs).filter(ZzSsSs.id == bed.ss_id).first()
                if room:
                    floor = db.query(ZzSsLc).filter(ZzSsLc.id == room.lc_id).first()
                    building = db.query(ZzSsLd).filter(ZzSsLd.id == floor.ld_id).first() if floor else None
                    dorm_info = {
                        'ld_mc': building.mc if building else '',
                        'lc': floor.lc if floor else '',
                        'ssh': room.ssh,
                        'ss_id': room.id,
                        'ss_label': f"{building.mc if building else ''}{floor.lc if floor else ''}层{room.ssh}室",
                        'cwh': bed.cwh,
                        'cw_id': bed.id,
                        'full_name': f"{building.mc if building else ''}{room.ssh}-{bed.cwh}"
                    }

            student_list.append({
                'id': s.id, 'xm': s.xm, 'xh': s.xh,
                'xb': s.xb or '',  # 性别：男/女
                'xsdh': s.xsdh or '',
                'xjzt': s.xjzt,
                'dorm_info': dorm_info
            })

        # 统计
        total = len(student_list)
        assigned = sum(1 for s in student_list if s['dorm_info'])
        unassigned = total - assigned

        return {
            'success': True, 'msg': '获取成功',
            'data': {
                'students': student_list,
                'total': total, 'assigned': assigned, 'unassigned': unassigned
            }
        }
    except Exception as e:
        logger.error(f"获取班级住宿情况失败: {str(e)}")
        return {'success': False, 'msg': f'获取失败: {str(e)}', 'data': {'students': []}}


# ========== 获取所有宿舍树形结构（用于选择器） ==========

@router.get('/tree')
async def get_dormitory_tree(
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """获取宿舍树形结构（楼栋-楼层-宿舍-床位）"""
    try:
        buildings = db.query(ZzSsLd).filter(ZzSsLd.zt == 1).order_by(ZzSsLd.px, ZzSsLd.id).all()
        tree = []
        for b in buildings:
            floors = db.query(ZzSsLc).filter(ZzSsLc.ld_id == b.id, ZzSsLc.zt == 1).order_by(ZzSsLc.lc).all()
            floor_list = []
            for f in floors:
                rooms = db.query(ZzSsSs).filter(ZzSsSs.lc_id == f.id, ZzSsSs.zt == 1).order_by(ZzSsSs.ssh).all()
                room_list = []
                for r in rooms:
                    beds = db.query(ZzSsCw).filter(ZzSsCw.ss_id == r.id, ZzSsCw.zt == 1).order_by(ZzSsCw.cwh).all()
                    bed_list = []
                    for bed in beds:
                        # 通过 zsr_id/zsr_type 反查入住学生（权威字段）
                        occupied = None
                        if bed.zsr_type == 'student' and bed.zsr_id:
                            occupied = db.query(ZzXs).filter(ZzXs.id == bed.zsr_id).first()
                        bed_list.append({
                            'id': bed.id, 'cwh': bed.cwh,
                            'occupied': bool(occupied),
                            'student_name': occupied.xm if occupied else None
                        })
                    room_list.append({'id': r.id, 'ssh': r.ssh, 'beds': bed_list})
                floor_list.append({'id': f.id, 'lc': f.lc, 'rooms': room_list})
            tree.append({'id': b.id, 'mc': b.mc, 'floors': floor_list})

        return {'success': True, 'msg': '获取成功', 'data': tree}
    except Exception as e:
        logger.error(f"获取宿舍树失败: {str(e)}")
        return {'success': False, 'msg': f'获取失败: {str(e)}', 'data': []}
