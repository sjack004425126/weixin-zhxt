"""心理咨询预约系统（纯预约制，不做叫号）

设计要点
--------
1. 老师按「号段」排号：每个号段可单独指定 **咨询日期** 与 **咨询地点**，
   同一场次可排到不同日期、不同地点（如上午 A 栋 201、下午 B 栋 301）。
2. 学生预约即取号：**预约号就是真实咨询顺序**（段内按预约先后递增）。
3. 不签到、不叫号、不排队：
   - 预约后不来，到该号段结束时自动视为未赴约（cancelled）。
   - 老师可手动把某条预约标记为「已咨询 / 未赴约」。
4. 历史记录只返回近期 5 条，前端折叠展开。

状态机
------
  booked(已预约) -> attended(已咨询)
                  -> cancelled(未赴约 / 学生取消 / 时段结束自动作废)

隐私原则：公开列表只显示预约代号（如 A01），不暴露来访者真实姓名。
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from models.models import (
    ZzCounselSchedule, ZzCounselSlot, ZzCounselBooking, ZzXs, ZzBj, Teacher,
    ZzBmxsBdzy, ZzBmxsJzdlx, ZzBmxsJzgx, ZzBmxsZsdx, ZzBmxsZzmm,
)
from init.dependencies import DatabaseDep
from common.auth import verify_token_and_get_payload
from datetime import datetime, date, timedelta
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/counsel", tags=["心理咨询预约"])

# 学生可提前预约天数（仅支持 2 天内，含当天）
BOOK_ADVANCE_DAYS = 2

# 历史记录默认展示条数（前端折叠展开）
HISTORY_LIMIT = 5
# 历史记录最大返回条数：预约记录折叠展开只在本地切换，后端最多只给最新 10 条
HISTORY_MAX = 10


def _slot_end_dt(slot) -> Optional[datetime]:
    try:
        if slot and slot.end_time:
            return slot.end_time
    except Exception:
        pass
    return None


def _slot_is_expired(slot) -> bool:
    """号段是否已过期（日期已过，或当天结束时间已过）"""
    n = _days_ahead(slot)
    if n is None:
        return False
    if n < 0:
        return True
    if n == 0:
        try:
            end = _slot_end_dt(slot)
            if end and end < datetime.now():
                return True
        except Exception:
            pass
    return False


def _active_booking_for_student(db: Session, xh: str):
    """该学生当前未完成的预约（booked 且号段未过期）：有则不可再约。

    结束标记 = attended（老师已确认咨询完成/已访谈）或 cancelled（含过期自动作废），
    结束后即可重新预约；booked 但号段已过期的也视为可重约，不再拦截。
    """
    if not xh:
        return None, None
    rows = db.query(ZzCounselBooking).filter(
        ZzCounselBooking.xh == xh,
        ZzCounselBooking.status == 'booked',
    ).order_by(ZzCounselBooking.book_time.desc(), ZzCounselBooking.id.desc()).all()
    for b in rows:
        slot = db.query(ZzCounselSlot).filter(ZzCounselSlot.id == b.slot_id).first()
        if slot is not None and _slot_is_expired(slot):
            continue
        return b, slot
    return None, None


def _slot_day(slot) -> Optional[date]:
    try:
        if not slot or not slot.counsel_date:
            return None
        v = slot.counsel_date
        if isinstance(v, datetime):
            return v.date()
        if isinstance(v, date):
            return v
        return None
    except Exception:
        return None


def _days_ahead(slot) -> Optional[int]:
    d = _slot_day(slot)
    if d is None:
        return None
    return (d - date.today()).days


def _within_advance(slot) -> bool:
    n = _days_ahead(slot)
    return n is not None and 0 <= n <= BOOK_ADVANCE_DAYS


# ============================================================
# 工具函数
# ============================================================

def _fmt(dt) -> Optional[str]:
    return dt.strftime('%Y-%m-%d %H:%M') if dt else None


def _fmt_hm(dt) -> Optional[str]:
    """HH:MM"""
    return dt.strftime('%H:%M') if dt else None


def _fmt_date(dt) -> Optional[str]:
    """YYYY-MM-DD"""
    return dt.strftime('%Y-%m-%d') if dt else None


def _require_teacher(current_user: dict):
    return bool(current_user.get('is_vocational_teacher') or current_user.get('t_id') is not None)


# 场次状态归一化：兼容历史遗留的 'calling'（旧叫号中）-> 'published'
def _norm_schedule_status(status: str) -> str:
    if status == 'calling':
        return 'published'
    return status or 'draft'


def _slot_of(db: Session, schedule_id: int):
    return db.query(ZzCounselSlot).filter(
        ZzCounselSlot.schedule_id == schedule_id
    ).order_by(ZzCounselSlot.counsel_date, ZzCounselSlot.sort_order, ZzCounselSlot.id).all()


def _active_count(db: Session, slot_id: int) -> int:
    """号段内已占号源数（booked 待咨询 + attended 已咨询都占坑位）"""
    return db.query(func.count(ZzCounselBooking.id)).filter(
        ZzCounselBooking.slot_id == slot_id,
        ZzCounselBooking.status.in_(['booked', 'attended'])).scalar() or 0


def _next_slot_seq(db: Session, slot_id: int) -> int:
    """取该号段「最小可用序号」，保证有效预约号连续无空洞。

    背景：预约号即真实咨询顺序。若按 max+1 递增，取消后重约会留下空洞
    （如 A01 被取消，下一位拿到 A03），老师端名单看起来像断号。
    这里只把「未取消」的预约视为占用，最小缺失序号即为下一个号，
    使当前有效名单始终是 A01..A0N 连续编号。
    """
    used = {r[0] for r in db.query(ZzCounselBooking.slot_seq).filter(
        ZzCounselBooking.slot_id == slot_id,
        ZzCounselBooking.status.in_(['booked', 'attended']),
        ZzCounselBooking.slot_seq.isnot(None)).all()}
    n = 1
    while n in used:
        n += 1
    return n


# ============================================================
# 视图构建
# ============================================================

def _slot_view(db: Session, s: ZzCounselSlot) -> dict:
    """号段视图（日期 + 时间 + 地点 + 类别 + 余号）

    附带 2 天预约窗口标记，前端据此禁用超前号段：
    - days_ahead: 距今天数（0=当天）
    - within_advance: 是否在 2 天内（含当天）
    - bookable: open 且有余号且在窗口内
    """
    cnt = _active_count(db, s.id)
    left = max(0, (s.quota or 0) - cnt)
    within = _within_advance(s)
    return {
        'id': s.id,
        'slot_tag': s.slot_tag,
        'counsel_date': _fmt_date(s.counsel_date),
        'time_range': f"{_fmt_hm(s.start_time)} - {_fmt_hm(s.end_time)}",
        'start_time': _fmt(s.start_time),
        'end_time': _fmt(s.end_time),
        'quota': s.quota,
        'booked': cnt,
        'left': left,
        'category': s.category or '',
        'location': s.location or '',
        'room_name': s.location or '',
        'status': s.status,
        'days_ahead': _days_ahead(s),
        'within_advance': within,
        'bookable': bool(s.status == 'open' and left > 0 and within),
    }


def _booking_view(b: ZzCounselBooking, masked: bool = True) -> dict:
    """预约单视图

    masked=True  -> 面向学生/公屏，只给代号，不含姓名
    masked=False -> 面向老师，可含姓名/学号/电话
    """
    data = {
        'id': b.id,
        'booking_id': b.id,
        'display_no': b.display_no,
        'code': b.display_no,
        'ticket_no': b.ticket_no,
        'slot_seq': b.slot_seq,
        'schedule_id': b.schedule_id,
        'slot_id': b.slot_id,
        'slot_tag': b.slot_tag,
        'category': b.category or '',
        'room_name': b.room_name or '',
        'location': b.room_name or '',
        'status': b.status,
        'book_time': _fmt(b.book_time),
        'remark': b.remark or '',
    }
    if not masked:
        data.update({
            'xs_id': b.xs_id,
            'xm': b.xm,
            'xh': b.xh,
            'bj_mc': b.bj_mc,
            'xsdh': b.xsdh,
            'phone_suffix': b.phone_suffix or '',
        })
    return data


def _dict_mc(db: Session, model, _id):
    """字典表 id -> mc，查不到返回原文/空"""
    if _id in (None, '', 0):
        return ''
    try:
        row = db.query(model).filter(model.id == _id).first()
        return (row.mc if row and hasattr(row, 'mc') else '') or ''
    except Exception:
        return ''


def _student_profile_view(db: Session, stu: ZzXs) -> dict:
    """学生全部档案（供教师端预约卡片展开参考）"""
    if not stu:
        return {}
    try:
        from controllers.photo_upload import get_signed_photo_url as _photo_url
    except Exception:
        _photo_url = None
    photo_url = None
    try:
        if stu.headphoto == 1 and stu.sfzh and _photo_url:
            photo_url = _photo_url(stu.sfzh, user_type='vocational')
    except Exception:
        photo_url = None
    bj_mc = ''
    bzr_name = ''
    bzr_phone = ''
    bzr_id = None
    try:
        if stu.bj_id:
            bj = db.query(ZzBj).filter(ZzBj.id == stu.bj_id).first()
            bj_mc = bj.mc if bj and bj.mc else ''
            if bj and bj.bzr_id:
                bzr_id = bj.bzr_id
                try:
                    t = db.query(Teacher).filter(Teacher.t_id == bj.bzr_id).first()
                    if t:
                        bzr_name = t.t_xm or ''
                        bzr_phone = t.t_dh or ''
                except Exception:
                    pass
    except Exception:
        pass
    return {
        'xs_id': stu.id,
        'xm': stu.xm or '',
        'xh': stu.xh or '',
        'xb': stu.xb or '',
        'mz': stu.mz or '',
        'sfzh': stu.sfzh or '',
        'xsdh': stu.xsdh or '',
        'bj_id': stu.bj_id,
        'bj_mc': bj_mc or '',
        'bzr_id': bzr_id,
        'bzr_name': bzr_name or '',
        'bzr_phone': bzr_phone or '',
        'zy_id': stu.zy_id,
        'zymc': _dict_mc(db, ZzBmxsBdzy, stu.zy_id),
        'zzmm': _dict_mc(db, ZzBmxsZzmm, stu.zzmm),
        'jzdlx': _dict_mc(db, ZzBmxsJzdlx, stu.jzdlx),
        'hkxz': stu.hkxz or '',
        'jtxxdz': stu.jtxxdz or '',
        'jzxm': stu.jzxm or '',
        'jzgx': _dict_mc(db, ZzBmxsJzgx, stu.jzgx),
        'jzdh': stu.jzdh or '',
        'byxxmc': stu.byxxmc or '',
        'zsdx': _dict_mc(db, ZzBmxsZsdx, stu.zsdx),
        'sfjdlk': stu.sfjdlk,
        'sflset': stu.sflset,
        'xsly': stu.xsly or '',
        'xjzt': stu.xjzt,
        'headphoto': stu.headphoto or 0,
        'photo_url': photo_url,
    }


# ============================================================
# 老师端：我的预约管理台（单台制，无场次列表）
# 约定：每位教师有且仅有一个「当前场次」承载所有号段；
# 打开管理台即自动获取或创建，无需再建场次/发布。
# ============================================================

def _get_or_create_current_schedule(db: Session, current_user: dict) -> ZzCounselSchedule:
    """取教师当前场次：最近一条未结束的；没有则自动创建一个已发布的。"""
    t_id = current_user.get('t_id')
    s = db.query(ZzCounselSchedule).filter(
        ZzCounselSchedule.counselor_t_id == t_id,
        ZzCounselSchedule.status != 'finished'
    ).order_by(ZzCounselSchedule.id.desc()).first()
    if s:
        # 兼容历史 draft/calling，一律视为可用的已发布台
        if _norm_schedule_status(s.status) != 'published':
            s.status = 'published'
            db.commit()
            db.refresh(s)
        return s
    s = ZzCounselSchedule(
        title=f"{current_user.get('t_xm', '')}的心理咨询",
        counsel_date=datetime.now(),
        counselor_t_id=t_id,
        counselor_name=current_user.get('t_xm', ''),
        status='published',
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


class IdReq(BaseModel):
    schedule_id: Optional[int] = None


class AddSlotReq(BaseModel):
    """新增一个号段（日期与地点均可单独指定；场次自动取当前台）"""
    schedule_id: Optional[int] = None
    counsel_date: Optional[str] = None   # YYYY-MM-DD，缺省用今天
    start_time: str                       # HH:MM
    end_time: str                         # HH:MM
    quota: int
    category: Optional[str] = None        # 咨询项目类别（教师自行填写）
    location: Optional[str] = None        # 咨询地点（号段级自定义）


def t_id_match(s: ZzCounselSchedule, current_user: dict) -> bool:
    return s.counselor_t_id == current_user.get('t_id')


def _resolve_schedule(db: Session, current_user: dict, schedule_id: Optional[int] = None) -> Optional[ZzCounselSchedule]:
    """解析场次：给了 id 就按 id 取（归属当前教师），没给就取当前台。"""
    if schedule_id:
        s = db.query(ZzCounselSchedule).filter(ZzCounselSchedule.id == schedule_id).first()
        if s and t_id_match(s, current_user):
            return s
    return _get_or_create_current_schedule(db, current_user)


@router.get('/teacher/desk')
async def teacher_desk(current_user: dict = Depends(verify_token_and_get_payload), db: Session = DatabaseDep):
    """教师预约管理台：自动获取或创建当前台（前端直进详情页用，无需传 id）"""
    if not _require_teacher(current_user):
        return {'success': False, 'msg': '仅教师可操作', 'data': None}
    s = _get_or_create_current_schedule(db, current_user)
    return {'success': True, 'msg': 'ok', 'data': {'schedule_id': s.id}}


@router.post('/teacher/schedule/finish')
async def finish_schedule(req: IdReq, current_user: dict = Depends(verify_token_and_get_payload), db: Session = DatabaseDep):
    """结束当前台：未赴约的预约自动作废（schedule_id 可不传，默认当前台）"""
    if not _require_teacher(current_user):
        return {'success': False, 'msg': '仅教师可操作', 'data': None}
    s = _resolve_schedule(db, current_user, req.schedule_id)
    if not s:
        return {'success': False, 'msg': '场次不存在', 'data': None}
    rows = db.query(ZzCounselBooking).filter(
        ZzCounselBooking.schedule_id == s.id, ZzCounselBooking.status == 'booked').all()
    for b in rows:
        b.status = 'cancelled'
    for sl in _slot_of(db, s.id):
        sl.status = 'closed'
    s.status = 'finished'
    db.commit()
    return {'success': True, 'msg': f'场次已结束，{len(rows)} 个未赴约预约已作废', 'data': {'cancelled': len(rows)}}


@router.post('/teacher/slot/add')
async def add_slot(req: AddSlotReq, current_user: dict = Depends(verify_token_and_get_payload), db: Session = DatabaseDep):
    """新增号段：可指定具体日期与咨询地点（场次自动取当前台）"""
    if not _require_teacher(current_user):
        return {'success': False, 'msg': '仅教师可操作', 'data': None}
    s = _resolve_schedule(db, current_user, req.schedule_id)
    if not s:
        return {'success': False, 'msg': '场次不存在', 'data': None}
    try:
        base_date = s.counsel_date or datetime.now()
        slot_date = datetime.strptime(req.counsel_date, '%Y-%m-%d') if req.counsel_date else base_date
        st = datetime.strptime(f"{slot_date.strftime('%Y-%m-%d')} {req.start_time}", '%Y-%m-%d %H:%M')
        et = datetime.strptime(f"{slot_date.strftime('%Y-%m-%d')} {req.end_time}", '%Y-%m-%d %H:%M')
    except ValueError:
        return {'success': False, 'msg': '日期/时间格式错误', 'data': None}
    if et <= st:
        return {'success': False, 'msg': '结束时间须晚于开始时间', 'data': None}
    if req.quota <= 0:
        return {'success': False, 'msg': '放号数量须大于 0', 'data': None}

    existing = _slot_of(db, s.id)
    # 按天编号：同一咨询日期内按创建时间排 A/B/C…，每天重排（不再全局累加）
    try:
        _day = slot_date.date() if isinstance(slot_date, datetime) else slot_date
        same_day = [x for x in existing if _slot_day(x) == _day]
    except Exception:
        same_day = []
    tags = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    tag = tags[len(same_day)] if len(same_day) < len(tags) else str(len(same_day) + 1)
    sl = ZzCounselSlot(
        schedule_id=s.id, sort_order=len(existing),
        slot_tag=tag, counsel_date=slot_date, start_time=st, end_time=et,
        quota=req.quota,
        category=(req.category or '').strip()[:50],
        location=(req.location or '').strip()[:100],
        status='open')
    db.add(sl)
    db.commit()
    db.refresh(sl)
    return {'success': True, 'msg': '号段已发布', 'data': _slot_view(db, sl)}


class DelSlotReq(BaseModel):
    schedule_id: Optional[int] = None
    slot_id: int


@router.post('/teacher/slot/delete')
async def delete_slot(req: DelSlotReq, current_user: dict = Depends(verify_token_and_get_payload), db: Session = DatabaseDep):
    """删除号段（仅允许删除还没有预约的号段；场次默认当前台）"""
    if not _require_teacher(current_user):
        return {'success': False, 'msg': '仅教师可操作', 'data': None}
    s = _resolve_schedule(db, current_user, req.schedule_id)
    if not s:
        return {'success': False, 'msg': '场次不存在', 'data': None}
    sl = db.query(ZzCounselSlot).filter(
        ZzCounselSlot.id == req.slot_id, ZzCounselSlot.schedule_id == s.id).first()
    if not sl:
        return {'success': False, 'msg': '号段不存在', 'data': None}
    used = _active_count(db, sl.id)
    if used:
        return {'success': False, 'msg': f'该号段已有 {used} 个预约，不能删除', 'data': None}
    db.delete(sl)
    db.commit()
    return {'success': True, 'msg': '号段已删除', 'data': None}


class SettleSlotReq(BaseModel):
    """结算号段：未赴约的预约作废"""
    schedule_id: Optional[int] = None
    slot_id: int


@router.post('/teacher/slot/settle')
async def settle_slot(req: SettleSlotReq, current_user: dict = Depends(verify_token_and_get_payload), db: Session = DatabaseDep):
    """号段结束：未赴约的预约自动作废（不来即取消；场次默认当前台）"""
    if not _require_teacher(current_user):
        return {'success': False, 'msg': '仅教师可操作', 'data': None}
    s = _resolve_schedule(db, current_user, req.schedule_id)
    if not s:
        return {'success': False, 'msg': '场次不存在', 'data': None}
    rows = db.query(ZzCounselBooking).filter(
        ZzCounselBooking.schedule_id == s.id,
        ZzCounselBooking.slot_id == req.slot_id,
        ZzCounselBooking.status == 'booked').all()
    for b in rows:
        b.status = 'cancelled'
    sl = db.query(ZzCounselSlot).filter(ZzCounselSlot.id == req.slot_id).first()
    if sl:
        sl.status = 'closed'
    db.commit()
    return {'success': True, 'msg': f'号段已结束，{len(rows)} 个未赴约预约已作废', 'data': {'cancelled': len(rows)}}


class MarkStatusReq(BaseModel):
    booking_id: int
    status: str  # attended / cancelled


@router.post('/teacher/booking/mark')
async def teacher_mark_booking(req: MarkStatusReq, current_user: dict = Depends(verify_token_and_get_payload), db: Session = DatabaseDep):
    """老师手动标记：已咨询 / 未赴约 / 取消预约（取消后号源自动释放）"""
    if not _require_teacher(current_user):
        return {'success': False, 'msg': '仅教师可操作', 'data': None}
    if req.status not in ('attended', 'cancelled'):
        return {'success': False, 'msg': '状态非法', 'data': None}
    b = db.query(ZzCounselBooking).filter(ZzCounselBooking.id == req.booking_id).first()
    if not b:
        return {'success': False, 'msg': '预约单不存在', 'data': None}
    if b.status == 'cancelled' and req.status == 'attended':
        return {'success': False, 'msg': '已作废的预约不能改为已咨询', 'data': None}
    b.status = req.status
    # 老师取消后释放号源：满员号段重新开放
    if req.status == 'cancelled':
        try:
            sl = db.query(ZzCounselSlot).filter(ZzCounselSlot.id == b.slot_id).first()
            if sl and sl.status == 'full':
                sl.status = 'open'
        except Exception:
            pass
    db.commit()
    return {'success': True, 'msg': '已标记', 'data': _booking_view(b, masked=False)}


@router.get('/teacher/booking/profile')
async def teacher_booking_profile(booking_id: int, current_user: dict = Depends(verify_token_and_get_payload), db: Session = DatabaseDep):
    """教师端：按预约单查看学生全部档案（点击卡片展开用）"""
    if not _require_teacher(current_user):
        return {'success': False, 'msg': '仅教师可操作', 'data': None}
    b = db.query(ZzCounselBooking).filter(ZzCounselBooking.id == booking_id).first()
    if not b:
        return {'success': False, 'msg': '预约单不存在', 'data': None}
    stu = None
    try:
        if b.xs_id:
            stu = db.query(ZzXs).filter(ZzXs.id == b.xs_id).first()
        if stu is None and b.xh:
            stu = db.query(ZzXs).filter(ZzXs.xh == b.xh).order_by(ZzXs.id.desc()).first()
    except Exception:
        stu = None
    profile = _student_profile_view(db, stu)
    # 兜底：档案缺失时至少回填预约单上的快照
    if not profile.get('xm'):
        profile.update({'xm': b.xm or '', 'xh': b.xh or '', 'bj_mc': b.bj_mc or '', 'xsdh': b.xsdh or ''})
    slot = db.query(ZzCounselSlot).filter(ZzCounselSlot.id == b.slot_id).first()
    return {'success': True, 'msg': 'ok', 'data': {
        'booking': _booking_view(b, masked=False),
        'slot': _slot_view(db, slot) if slot else None,
        'student': profile,
    }}


class RemarkReq(BaseModel):
    booking_id: int
    remark: Optional[str] = ''


@router.post('/teacher/remark')
async def teacher_remark(req: RemarkReq, current_user: dict = Depends(verify_token_and_get_payload), db: Session = DatabaseDep):
    """保存老师备注（学生不可见）"""
    if not _require_teacher(current_user):
        return {'success': False, 'msg': '仅教师可操作', 'data': None}
    b = db.query(ZzCounselBooking).filter(ZzCounselBooking.id == req.booking_id).first()
    if not b:
        return {'success': False, 'msg': '预约单不存在', 'data': None}
    b.remark = req.remark or ''
    db.commit()
    return {'success': True, 'msg': '备注已保存', 'data': None}


@router.get('/teacher/schedule/detail')
async def teacher_schedule_detail(schedule_id: Optional[int] = None, current_user: dict = Depends(verify_token_and_get_payload), db: Session = DatabaseDep):
    """老师端管理台详情：号段列表 + 各号段预约名单（私有，含姓名）。

    直进模式：不传 schedule_id 即自动取当前台（兼容老前端传 id）。
    """
    if not _require_teacher(current_user):
        return {'success': False, 'msg': '仅教师可操作', 'data': None}
    s = _resolve_schedule(db, current_user, schedule_id)
    if not s:
        return {'success': False, 'msg': '场次不存在', 'data': None}

    slots = []
    all_slots = _slot_of(db, s.id)
    # 只取前 5 天的号段，避免太多无法显示（按 counsel_date 升序取前 5 个不同日期）
    keep_dates = []
    seen = set()
    for sl in all_slots:
        d = _fmt_date(getattr(sl, 'counsel_date', None))
        if d not in seen:
            seen.add(d)
            keep_dates.append(d)
        if len(keep_dates) >= 5:
            break
    keep_set = set(keep_dates)
    for sl in all_slots:
        if _fmt_date(getattr(sl, 'counsel_date', None)) not in keep_set:
            continue
        rows = db.query(ZzCounselBooking).filter(
            ZzCounselBooking.slot_id == sl.id,
            ZzCounselBooking.status != 'cancelled').order_by(
                ZzCounselBooking.slot_seq, ZzCounselBooking.id).all()
        item = _slot_view(db, sl)
        item['tickets'] = [_booking_view(b, masked=False) for b in rows]
        slots.append(item)

    return {'success': True, 'msg': 'ok', 'data': {
        'schedule_id': s.id,
        'title': s.title,
        'counsel_date': _fmt_date(s.counsel_date),
        'status': s.status,
        'doctor_name': s.counselor_name or '',
        'slots': slots,
    }}


# ============================================================
# 学生端
# ============================================================

@router.get('/open_list')
async def open_list(current_user: dict = Depends(verify_token_and_get_payload), db: Session = DatabaseDep):
    """可预约场次列表（与教师单台制对齐：每位教师只展示最新一条未结束场次，最新在前）"""
    xh = current_user.get('xs_xh')
    rows = db.query(ZzCounselSchedule).filter(
        ZzCounselSchedule.status.in_(['published', 'calling'])
    ).order_by(ZzCounselSchedule.id.desc()).all()
    # 单台制对齐：同一教师有多条 published 时只留最新一条，避免学生点进老场次
    seen_teacher = set()
    filtered = []
    for r in rows:
        key = r.counselor_t_id if r.counselor_t_id is not None else f'schedule-{r.id}'
        if key in seen_teacher:
            continue
        seen_teacher.add(key)
        filtered.append(r)
    rows = filtered
    out = []
    for r in rows:
        slots = _slot_of(db, r.id)
        mine = None
        if xh:
            # 列表角标只显示「未完成」的预约：已咨询/已取消/已过期都不再占位，可重约
            _ab, _ = _active_booking_for_student(db, xh)
            if _ab is not None and _ab.schedule_id == r.id:
                mine = {'display_no': _ab.display_no, 'code': _ab.display_no,
                        'status': _ab.status, 'slot_id': _ab.slot_id}
        out.append({
            'id': r.id, 'title': r.title,
            'counsel_date': _fmt_date(r.counsel_date),
            'status': _norm_schedule_status(r.status),
            'doctor_name': r.counselor_name or '',
            'counselor_t_id': r.counselor_t_id,
            'slots': [_slot_view(db, s) for s in slots],
            'mine': mine,
        })
    return {'success': True, 'msg': 'ok', 'data': out}


class BookReq(BaseModel):
    slot_id: int
    phone_suffix: Optional[str] = None


@router.post('/book')
async def book(req: BookReq, current_user: dict = Depends(verify_token_and_get_payload), db: Session = DatabaseDep):
    """预约取号：预约号即真实咨询顺序（仅支持提前 2 天内，含当天）"""
    xh = current_user.get('xs_xh')
    if not xh:
        return {'success': False, 'msg': '仅学生可预约', 'data': None}
    slot = db.query(ZzCounselSlot).filter(ZzCounselSlot.id == req.slot_id).first()
    if not slot or slot.status != 'open':
        return {'success': False, 'msg': '该号段不可预约', 'data': None}
    # 提前 2 天窗口校验（含当天，过期号段也不可约）
    _ahead = _days_ahead(slot)
    if _ahead is None or _ahead < 0:
        return {'success': False, 'msg': '该号段已过期，不可预约', 'data': None}
    if _ahead > BOOK_ADVANCE_DAYS:
        return {'success': False, 'msg': f'仅支持提前 {BOOK_ADVANCE_DAYS} 天内预约', 'data': None}
    sched = db.query(ZzCounselSchedule).filter(ZzCounselSchedule.id == slot.schedule_id).first()
    if not sched or _norm_schedule_status(sched.status) != 'published':
        return {'success': False, 'msg': '场次未开放预约', 'data': None}

    # 同一学生全局只允许一条「未完成」预约：booked 且号段未过期
    # 结束标记 = attended（老师已确认咨询完成/已访谈）或 cancelled（含过期作废），结束后可重约；
    # booked 但号段已过期的也视为已结束，可重约
    # 注：同一号段重复点两次由下面的 same-slot 检查先拦，避免撞唯一索引 500
    # 同一号段内已有未取消单（booked 待咨询 / attended 已咨询）则不可再约该段；
    # 已咨询可重约的是「其他号段」，同段重复给友好提示而不是 500
    same = db.query(ZzCounselBooking).filter(
        ZzCounselBooking.slot_id == slot.id, ZzCounselBooking.xh == xh,
        ZzCounselBooking.status.in_(['booked', 'attended'])).first()
    if same:
        return {'success': False, 'msg': f'您已预约 {same.display_no}，不可重复预约', 'data': None}
    active, active_slot = _active_booking_for_student(db, xh)
    if active:
        tag = active.display_no or ''
        return {'success': False, 'msg': f'您已有未完成的预约 {tag}，完成后才能再次预约', 'data': None}

    cnt = _active_count(db, slot.id)
    if cnt >= (slot.quota or 0):
        slot.status = 'full'
        db.commit()
        return {'success': False, 'msg': '该号段已约满', 'data': None}

    stu = db.query(ZzXs).filter(ZzXs.xh == xh).order_by(ZzXs.id.desc()).first()
    bj_mc = ''
    if stu and stu.bj_id:
        bj = db.query(ZzBj).filter(ZzBj.id == stu.bj_id).first()
        if bj:
            bj_mc = bj.mc or ''

    max_ticket = db.query(func.max(ZzCounselBooking.ticket_no)).filter(
        ZzCounselBooking.schedule_id == slot.schedule_id,
        ZzCounselBooking.status.in_(['booked', 'attended'])).scalar() or 0
    slot_seq = _next_slot_seq(db, slot.id)
    ticket_no = max_ticket + 1
    display_no = f"{slot.slot_tag}{slot_seq:02d}"

    b = ZzCounselBooking(
        schedule_id=slot.schedule_id, slot_id=slot.id,
        xs_id=stu.id if stu else None, xh=xh,
        xm=stu.xm if stu else current_user.get('xs_xm', ''),
        bj_id=stu.bj_id if stu else None, bj_mc=bj_mc,
        xsdh=stu.xsdh if stu else '',
        category=slot.category or '',
        phone_suffix=(req.phone_suffix or '').strip()[:4] or None,
        room_name=slot.location or '',
        ticket_no=ticket_no, slot_seq=slot_seq, slot_tag=slot.slot_tag,
        display_no=display_no,
        status='booked', book_time=datetime.now(),
    )
    db.add(b)
    if cnt + 1 >= (slot.quota or 0):
        slot.status = 'full'
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        # 并发重复点/已存在未完成预约撞唯一索引时，给友好提示而不是 500
        try:
            msg = str(getattr(e, 'orig', e) or e)
        except Exception:
            msg = str(e)
        if 'uq_counsel_slot_xh' in msg or '重复键' in msg or 'duplicate' in msg.lower():
            return {'success': False, 'msg': '您已预约该号段，不可重复预约', 'data': None}
        logger.exception('counsel book commit failed')
        return {'success': False, 'msg': '预约失败，请稍后重试', 'data': None}
    db.refresh(b)
    return {'success': True, 'msg': f'预约成功，您的号码牌是 {display_no}',
            'data': {'display_no': display_no, 'code': display_no, 'booking_id': b.id}}


class CancelReq(BaseModel):
    booking_id: int


@router.post('/cancel')
async def cancel(req: CancelReq, current_user: dict = Depends(verify_token_and_get_payload), db: Session = DatabaseDep):
    """学生取消预约（已关闭：预约后不可取消，需联系老师由老师端取消）"""
    return {'success': False, 'msg': '预约后不可取消，如需取消请联系咨询老师', 'data': None}


@router.get('/my_ticket')
async def my_ticket(schedule_id: int, current_user: dict = Depends(verify_token_and_get_payload), db: Session = DatabaseDep):
    """我的预约（客户端卡片1）：含咨询顺序、日期、地点；附 has_active 是否还有未完成预约"""
    xh = current_user.get('xs_xh')
    b = db.query(ZzCounselBooking).filter(
        ZzCounselBooking.schedule_id == schedule_id, ZzCounselBooking.xh == xh,
        ZzCounselBooking.status != 'cancelled').order_by(ZzCounselBooking.book_time.desc(), ZzCounselBooking.id.desc()).first()
    active, _ = _active_booking_for_student(db, xh) if xh else (None, None)
    has_active = active is not None
    active_no = active.display_no if active else ''
    if not b:
        return {'success': True, 'msg': 'ok', 'data': {'mine': None, 'has_active': has_active, 'active_no': active_no}}
    slot = db.query(ZzCounselSlot).filter(ZzCounselSlot.id == b.slot_id).first()
    sched = db.query(ZzCounselSchedule).filter(ZzCounselSchedule.id == schedule_id).first()
    # 前方还有多少个同号段未完成的预约（就是真实咨询顺序）
    ahead = db.query(func.count(ZzCounselBooking.id)).filter(
        ZzCounselBooking.slot_id == b.slot_id,
        ZzCounselBooking.status.in_(['booked', 'attended']),
        ZzCounselBooking.slot_seq < (b.slot_seq or 0)).scalar() or 0
    return {'success': True, 'msg': 'ok', 'data': {
        'mine': {
            'booking_id': b.id, 'display_no': b.display_no, 'code': b.display_no,
            'status': b.status, 'slot_id': b.slot_id, 'slot_tag': b.slot_tag,
            'slot_seq': b.slot_seq,
            'counsel_date': _fmt_date(slot.counsel_date) if slot else '',
            'slot_time': f"{_fmt_hm(slot.start_time)} - {_fmt_hm(slot.end_time)}" if slot else '',
            'category': b.category or '',
            'room_name': b.room_name or (slot.location if slot else ''),
            'location': b.room_name or (slot.location if slot else ''),
            'ahead': ahead,
            'phone_suffix': b.phone_suffix or '',
            'book_time': _fmt(b.book_time),
            'title': sched.title if sched else '',
        },
        'has_active': has_active, 'active_no': active_no, }}


@router.get('/board')
async def board(schedule_id: int, current_user: dict = Depends(verify_token_and_get_payload), db: Session = DatabaseDep):
    """预约看板（客户端卡片2）：只展示可预约的号段，严格只显示代号"""
    s = db.query(ZzCounselSchedule).filter(ZzCounselSchedule.id == schedule_id).first()
    if not s:
        return {'success': False, 'msg': '场次不存在', 'data': None}
    slots = _slot_of(db, s.id)
    return {'success': True, 'msg': 'ok', 'data': {
        'schedule_id': s.id,
        'title': s.title,
        'counsel_date': _fmt_date(s.counsel_date),
        'status': s.status,
        'doctor_name': s.counselor_name or '',
        'slots': [_slot_view(db, sl) for sl in slots],
    }}


@router.get('/my_history')
async def my_history(limit: int = HISTORY_LIMIT, current_user: dict = Depends(verify_token_and_get_payload), db: Session = DatabaseDep):
    """我的历史预约记录（后端最多只返回最新 10 条，折叠展开由前端本地切换）"""
    # 前端折叠只在本地切片，不再传大 limit；这里钳制防止一次取太多
    try:
        limit = int(limit or HISTORY_LIMIT)
    except (TypeError, ValueError):
        limit = HISTORY_LIMIT
    limit = max(1, min(limit, HISTORY_MAX))
    xh = current_user.get('xs_xh')
    if not xh:
        return {'success': True, 'msg': 'ok', 'data': {'list': [], 'total': 0, 'limit': limit}}

    total = db.query(func.count(ZzCounselBooking.id)).filter(
        ZzCounselBooking.xh == xh).scalar() or 0
    rows = db.query(ZzCounselBooking).filter(
        ZzCounselBooking.xh == xh).order_by(
        ZzCounselBooking.book_time.desc(), ZzCounselBooking.id.desc()).limit(HISTORY_MAX).all()

    items = []
    for b in rows:
        slot = db.query(ZzCounselSlot).filter(ZzCounselSlot.id == b.slot_id).first()
        items.append({
            'booking_id': b.id,
            'display_no': b.display_no,
            'status': b.status,
            'status_text': {'booked': '待咨询', 'attended': '已咨询',
                            'cancelled': '已取消'}.get(b.status, b.status),
            'counsel_date': _fmt_date(slot.counsel_date) if slot else '',
            'slot_time': f"{_fmt_hm(slot.start_time)} - {_fmt_hm(slot.end_time)}" if slot else '',
            'category': b.category or '',
            'location': b.room_name or (slot.location if slot else ''),
            'book_time': _fmt(b.book_time),
        })
    return {'success': True, 'msg': 'ok', 'data': {
        'list': items[:limit],
        'total': total,
        'limit': limit,
        'has_more': total > limit,
    }}
