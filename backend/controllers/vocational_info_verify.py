"""职教学生信息核对接口

提供：
- GET  /vocational_info_verify/info       获取当前学生可核对的个人信息 + 核对状态/历史
- POST /vocational_info_verify/submit     提交核对结果（确认无误 或 修改后提交）

核对状态 xs_info_verify_status（zz_xs 表）：
- pending   待核对（未提交）
- verified  已确认无误提交
- modified  已修改提交
"""

from datetime import datetime
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from common.auth import verify_token_and_get_payload
from init.dependencies import DatabaseDep
from models.models import ZzXs

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/vocational_info_verify", tags=["职教学生信息核对"])

# 核对状态枚举
STATUS_PENDING = "pending"
STATUS_VERIFIED = "verified"
STATUS_MODIFIED = "modified"

STATUS_VALUES = {STATUS_PENDING, STATUS_VERIFIED, STATUS_MODIFIED}

# 允许用户核对/修改的字段白名单
VERIFY_FIELDS = ["xm", "xb", "sfzh", "mz", "xsdh", "zzmm", "jtxxdz", "hkxz", "jzdlx", "jzxm", "jzgx", "jzdh"]

# 字段中文标签（前端展示/审查时使用）
FIELD_LABELS: Dict[str, str] = {
    "xm": "姓名",
    "xb": "性别",
    "sfzh": "身份证号",
    "mz": "民族",
    "xsdh": "联系电话",
    "zzmm": "政治面貌",
    "jtxxdz": "家庭地址",
    "hkxz": "户口性质",
    "jzdlx": "居住地类型",
    "jzxm": "监护人姓名",
    "jzgx": "监护人关系",
    "jzdh": "监护人电话",
}


def _safe_json_loads(raw: Optional[str]) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _extract_birth_date_from_idcard(sfzh: Optional[str]) -> Optional[str]:
    """从 18 位身份证号推导出生日期 YYYY-MM-DD"""
    if not sfzh or len(sfzh) < 14:
        return None
    try:
        return f"{sfzh[6:10]}-{sfzh[10:12]}-{sfzh[12:14]}"
    except Exception:
        return None


def _get_student_from_payload(payload: Dict[str, Any], db: Session) -> ZzXs:
    """根据 token payload 定位 zz_xs 学生记录"""
    xs_id = payload.get("xs_id")
    xs_xh = payload.get("xs_xh")

    student: Optional[ZzXs] = None
    if xs_id is not None:
        student = db.query(ZzXs).filter(ZzXs.id == xs_id).first()
    if student is None and xs_xh:
        student = db.query(ZzXs).filter(ZzXs.xh == xs_xh).first()

    if student is None:
        raise HTTPException(status_code=404, detail="未找到学生信息")
    return student


def _get_field_value(student: ZzXs, field: str) -> Any:
    """安全获取学生字段值"""
    return getattr(student, field, None)


@router.get("/info")
def get_verify_info(
    payload: Dict[str, Any] = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep,
):
    """获取学生基本信息 + 核对状态 + 历次记录"""
    student = _get_student_from_payload(payload, db)

    original = {f: _get_field_value(student, f) for f in VERIFY_FIELDS}
    csrq = _extract_birth_date_from_idcard(student.sfzh)

    status = student.xs_info_verify_status or STATUS_PENDING
    if status not in STATUS_VALUES:
        status = STATUS_PENDING

    record = _safe_json_loads(student.xs_info_verify_record)
    history: List[Dict[str, Any]] = record.get("history") if isinstance(record.get("history"), list) else []

    # 已提交过的，取 history 末条快照中的 original（才是修改前的真实值）
    if status != STATUS_PENDING and history:
        last = history[-1]
        original = last.get("original") or original

    return {
        "success": True,
        "msg": "ok",
        "data": {
            "student_no": student.xh,
            "student_name": student.xm,
            "original": original,
            "field_labels": FIELD_LABELS,
            "birth_date": csrq,  # 从身份证推导的展示字段，前端只读
            "status": status,
            "submitted_at": record.get("submitted_at"),
            "latest_modified": record.get("modified") or {},
            "history": history,
        },
    }


class VerifySubmitItem(BaseModel):
    field: str = Field(..., description="字段名，必须在白名单内")
    value: Optional[str] = Field(None, description="修改后的值")


class VerifySubmitRequest(BaseModel):
    changes: List[VerifySubmitItem] = Field(default_factory=list, description="修改项列表；为空表示确认无误")


@router.post("/submit")
def submit_verify_info(
    body: VerifySubmitRequest,
    payload: Dict[str, Any] = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep,
):
    """提交核对结果
    - changes 为空 -> status=verified（确认无误）
    - changes 非空 -> status=modified（已修改）且把改动回写到 zz_xs
    - 每次提交都向 xs_info_verify_record 的 history 追加一条
    """
    student = _get_student_from_payload(payload, db)

    # 当前真实值（提交时的 original）
    original = {f: _get_field_value(student, f) for f in VERIFY_FIELDS}

    # 过滤白名单并去重（保留最后一次）
    filtered_changes: Dict[str, str] = {}
    for item in body.changes or []:
        if not isinstance(item.field, str):
            continue
        if item.field not in VERIFY_FIELDS:
            raise HTTPException(status_code=400, detail=f"字段 {item.field} 不在允许核对的范围内")
        filtered_changes[item.field] = item.value if item.value is not None else ""

    # 计算本次"相对原始值"实际有变化的字段
    effective_modified: Dict[str, str] = {}
    for field, new_value in filtered_changes.items():
        old_value = original.get(field)
        if (new_value or "") != (old_value or ""):
            effective_modified[field] = new_value

    if effective_modified:
        # 回写到 zz_xs（成为最新真实值）
        for field, new_value in effective_modified.items():
            setattr(student, field, new_value)
        new_status = STATUS_MODIFIED
    else:
        new_status = STATUS_VERIFIED

    # 读取旧 record，构造新 record
    old_record = _safe_json_loads(student.xs_info_verify_record)
    history: List[Dict[str, Any]] = old_record.get("history") if isinstance(old_record.get("history"), list) else []

    submitted_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    snapshot = {
        "status": new_status,
        "submitted_at": submitted_at,
        "original": original,
        "modified": effective_modified,
    }
    history.append(snapshot)

    new_record = {
        "status": new_status,
        "submitted_at": submitted_at,
        "original": original,
        "modified": effective_modified,
        "history": history,
    }

    student.xs_info_verify_status = new_status
    student.xs_info_verify_record = json.dumps(new_record, ensure_ascii=False)

    try:
        db.commit()
        db.refresh(student)
    except Exception as e:
        db.rollback()
        logger.exception("提交核对信息失败")
        raise HTTPException(status_code=500, detail=f"保存失败: {e}")

    return {
        "success": True,
        "msg": "提交成功",
        "data": {
            "status": new_status,
            "submitted_at": submitted_at,
            "modified": effective_modified,
        },
    }
