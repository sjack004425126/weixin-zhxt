"""开放教育学生新书领取登记接口

提供：
- GET  /student_book_pickup/status   查询当前批次登记状态 + 上一批次邮寄地址参考
- POST /student_book_pickup/submit   提交/修改本批次领取方式

规则：
- 批次 pc 以后端实时查询 lw_sys.sys_pc 为准，不信任 token 中的 sys_pc
- 同一 (xs_xh, pc) 只保留一条记录，重复提交为 UPDATE，支持随时修改
- pickup_type 为英文语义字符串枚举：self_pickup-到校领取 / mail-邮寄
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from sqlalchemy.orm import Session

from common.auth import verify_token_and_get_payload
from init.dependencies import DatabaseDep
from models.models import Student, OaXsBookPickup, lw_sys, Teacher, Class

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/student_book_pickup", tags=["开放教育学生-新书领取登记"])

PickupType = Literal["self_pickup", "mail"]

PICKUP_TYPE_LABELS: Dict[str, str] = {
    "self_pickup": "到校领取",
    "mail": "邮寄",
}

_PHONE_RE = re.compile(r"^1\d{10}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _get_current_pc(db: Session) -> Optional[int]:
    """实时查询系统当前批次，lw_sys 单行表取第一条"""
    try:
        sys_info = db.query(lw_sys).first()
        if sys_info and sys_info.sys_pc is not None:
            return int(sys_info.sys_pc)
    except Exception as e:
        logger.warning(f"查询当前批次失败: {e}")
    return None


def _get_student_from_payload(payload: Dict[str, Any], db: Session) -> Student:
    xs_id = payload.get("xs_id")
    xs_xh = payload.get("xs_xh")
    student: Optional[Student] = None
    if xs_id is not None:
        student = db.query(Student).filter(Student.xs_id == xs_id).first()
    if student is None and xs_xh:
        student = db.query(Student).filter(Student.xs_xh == xs_xh).first()
    if student is None:
        raise HTTPException(status_code=404, detail="未找到学生信息")
    return student


def _get_pickup_site(db: Session, student: Student) -> Optional[Dict[str, Any]]:
    """查询学生班主任设置的自取地点：oa_xs.xs_bj_id → oa_bj.bj_bzr_id → oa_t

    返回 {address, teacher_name, teacher_phone, has_address}，实时查询不做快照。
    班主任未设置地址时 address 为空串，前端兜底显示联系班主任。
    """
    try:
        if not student.xs_bj_id:
            return None
        bj = db.query(Class).filter(Class.bj_id == student.xs_bj_id).first()
        if not bj or not bj.bj_bzr_id:
            return None
        teacher = db.query(Teacher).filter(Teacher.t_id == bj.bj_bzr_id).first()
        if not teacher:
            return None
        addr = (getattr(teacher, "t_book_pickup_addr", None) or "").strip()
        return {
            "address": addr,
            "has_address": bool(addr),
            "teacher_name": teacher.t_xm or "",
            "teacher_phone": teacher.t_dh or "",
        }
    except Exception as e:
        logger.warning(f"查询自取地点失败: {e}")
        return None


def _record_to_dict(r: Optional[OaXsBookPickup]) -> Optional[Dict[str, Any]]:
    if r is None:
        return None
    return {
        "pickup_type": r.pickup_type,
        "pickup_type_text": PICKUP_TYPE_LABELS.get(r.pickup_type, r.pickup_type or ""),
        "pickup_date": r.pickup_date or "",
        "receiver_name": r.receiver_name or "",
        "receiver_phone": r.receiver_phone or "",
        "province": r.province or "",
        "city": r.city or "",
        "district": r.district or "",
        "detail_addr": r.detail_addr or "",
        "updated_at": r.updatetime.strftime("%Y-%m-%d %H:%M:%S") if r.updatetime else "",
    }


@router.get("/status")
def get_pickup_status(
    payload: Dict[str, Any] = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep,
):
    """查询当前批次是否已登记 + 上一批次邮寄地址参考"""
    student = _get_student_from_payload(payload, db)
    pc = _get_current_pc(db)
    if pc is None:
        raise HTTPException(status_code=500, detail="系统批次未配置，请联系管理员")

    current = (
        db.query(OaXsBookPickup)
        .filter(OaXsBookPickup.xs_xh == student.xs_xh, OaXsBookPickup.pc == pc)
        .first()
    )

    # 上一批次：该生 pc 小于当前批次的最大一条（仅当其为 mail 时用于快捷填充）
    last = (
        db.query(OaXsBookPickup)
        .filter(OaXsBookPickup.xs_xh == student.xs_xh, OaXsBookPickup.pc < pc)
        .order_by(OaXsBookPickup.pc.desc())
        .first()
    )
    last_mail = None
    if last and last.pickup_type == "mail":
        last_mail = {
            "pc": last.pc,
            "receiver_name": last.receiver_name or "",
            "receiver_phone": last.receiver_phone or "",
            "province": last.province or "",
            "city": last.city or "",
            "district": last.district or "",
            "detail_addr": last.detail_addr or "",
        }

    return {
        "success": True,
        "msg": "ok",
        "data": {
            "pc": pc,
            "filled": current is not None,
            "current": _record_to_dict(current),
            "last_mail": last_mail,
            "pickup_type_labels": PICKUP_TYPE_LABELS,
            "pickup_site": _get_pickup_site(db, student),
        },
    }


class BookPickupSubmitRequest(BaseModel):
    pickup_type: PickupType = Field(..., description="领取方式: self_pickup-到校领取 / mail-邮寄")
    pickup_date: Optional[str] = Field(None, description="到校领取日期 YYYY-MM-DD")
    receiver_name: Optional[str] = Field(None, description="收件人姓名")
    receiver_phone: Optional[str] = Field(None, description="收件人电话")
    province: Optional[str] = Field(None, description="省")
    city: Optional[str] = Field(None, description="市")
    district: Optional[str] = Field(None, description="区/县")
    detail_addr: Optional[str] = Field(None, description="详细地址")


def _clean(v: Optional[str]) -> str:
    return (v or "").strip()


@router.post("/submit")
def submit_pickup(
    body: BookPickupSubmitRequest,
    payload: Dict[str, Any] = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep,
):
    """提交/修改本批次领取登记（upsert，不限修改次数）"""
    student = _get_student_from_payload(payload, db)
    pc = _get_current_pc(db)
    if pc is None:
        raise HTTPException(status_code=500, detail="系统批次未配置，请联系管理员")

    pickup_type: str = body.pickup_type
    pickup_date = _clean(body.pickup_date)
    receiver_name = _clean(body.receiver_name)
    receiver_phone = _clean(body.receiver_phone)
    province = _clean(body.province)
    city = _clean(body.city)
    district = _clean(body.district)
    detail_addr = _clean(body.detail_addr)

    if pickup_type == "self_pickup":
        if not pickup_date:
            raise HTTPException(status_code=400, detail="请选择到校领取的大概日期")
        if not _DATE_RE.match(pickup_date):
            raise HTTPException(status_code=400, detail="日期格式不正确，应为 YYYY-MM-DD")
        try:
            datetime.strptime(pickup_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="日期不正确，请重新选择")
        # 到校领取时清空邮寄字段，避免脏数据
        receiver_name = receiver_phone = province = city = district = detail_addr = ""
    elif pickup_type == "mail":
        if not receiver_name:
            raise HTTPException(status_code=400, detail="请填写收件人姓名")
        if not receiver_phone:
            raise HTTPException(status_code=400, detail="请填写收件人电话")
        if not _PHONE_RE.match(receiver_phone):
            raise HTTPException(status_code=400, detail="收件人电话格式不正确（需11位手机号）")
        if not province or not city or not district:
            raise HTTPException(status_code=400, detail="请选择省/市/区")
        if not detail_addr:
            raise HTTPException(status_code=400, detail="请填写详细地址")
        pickup_date = ""
    else:
        raise HTTPException(status_code=400, detail="领取方式不正确")

    try:
        record = (
            db.query(OaXsBookPickup)
            .filter(OaXsBookPickup.xs_xh == student.xs_xh, OaXsBookPickup.pc == pc)
            .first()
        )
        now = datetime.now()
        if record is None:
            record = OaXsBookPickup(
                xs_xh=student.xs_xh,
                xs_xm=student.xs_xm,
                xs_bj_id=student.xs_bj_id,
                pc=pc,
                pickup_type=pickup_type,
                pickup_date=pickup_date or None,
                receiver_name=receiver_name or None,
                receiver_phone=receiver_phone or None,
                province=province or None,
                city=city or None,
                district=district or None,
                detail_addr=detail_addr or None,
                addtime=now,
                updatetime=now,
            )
            db.add(record)
        else:
            record.xs_xm = student.xs_xm
            record.xs_bj_id = student.xs_bj_id
            record.pickup_type = pickup_type
            record.pickup_date = pickup_date or None
            record.receiver_name = receiver_name or None
            record.receiver_phone = receiver_phone or None
            record.province = province or None
            record.city = city or None
            record.district = district or None
            record.detail_addr = detail_addr or None
            record.updatetime = now

        db.commit()
        db.refresh(record)
        logger.info(f"新书领取登记: xs_xh={student.xs_xh} pc={pc} type={pickup_type}")

        return {
            "success": True,
            "msg": "提交成功",
            "data": {
                "pc": pc,
                "submitted_at": record.updatetime.strftime("%Y-%m-%d %H:%M:%S") if record.updatetime else "",
                "current": _record_to_dict(record),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("保存新书领取登记失败")
        raise HTTPException(status_code=500, detail=f"保存失败: {e}")
