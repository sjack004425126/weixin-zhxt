"""教师端 - 新生信息核对审核接口

提供：
- GET  /open_teacher/info_verify/list     所管理班级学生的核对状态（分页+搜索+筛选）
- GET  /open_teacher/info_verify/detail   单个学生的核对详情（原始值、修改项、历次历史）
- GET  /open_teacher/info_verify/export   导出有修改记录的学生为 csv（前后修改对照）
- POST /open_teacher/info_verify/reset    重置指定学生的核对状态，让学生可重新提交
"""

import csv
import io
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from common.auth import verify_token_and_get_payload
from init.dependencies import DatabaseDep
from models.models import Class, Student

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/open_teacher/info_verify", tags=["开放教育教师-信息核对"])

# 字段白名单及中文标签（与 controllers/student_info_verify.py 保持一致）
VERIFY_FIELDS = ["xs_xm", "xs_xb", "xs_sfzh", "xs_mz"]
FIELD_LABELS: Dict[str, str] = {
    "xs_xm": "姓名",
    "xs_xb": "性别",
    "xs_sfzh": "身份证号",
    "xs_mz": "民族",
}

# 状态 → 前端友好文案 / CSS 类名
STATUS_META = {
    "pending":  {"text": "待核对", "cls": "pending"},
    "verified": {"text": "已核对无误", "cls": "verified"},
    "modified": {"text": "已修改", "cls": "modified"},
}


def _safe_json_loads(raw: Optional[str]) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _get_teacher_class_ids(db: Session, t_id: Optional[int]) -> List[int]:
    """教师所管理班级 ID 列表（未屏蔽）"""
    if t_id is None:
        return []
    classes = db.query(Class).filter(
        Class.bj_bzr_id == t_id,
        or_(Class.bj_isblock == 0, Class.bj_isblock == None)
    ).all()
    return [c.bj_id for c in classes]


def _get_teacher_classes(db: Session, t_id: Optional[int]) -> List[Class]:
    if t_id is None:
        return []
    return db.query(Class).filter(
        Class.bj_bzr_id == t_id,
        or_(Class.bj_isblock == 0, Class.bj_isblock == None)
    ).order_by(Class.bj_nd.desc(), Class.bj_mc).all()


def _resolve_query_bj_ids(teacher_bj_ids: List[int], bj_id: Optional[int]) -> Optional[List[int]]:
    """校验权限并返回实际要查询的班级 ID 列表；None 表示无权限"""
    if bj_id:
        if bj_id not in teacher_bj_ids:
            return None
        return [bj_id]
    return teacher_bj_ids


@router.get("/list")
def get_info_verify_list(
    bj_id: Optional[int] = Query(None, description="班级ID，不传则查所管理全部班级"),
    status_filter: Optional[str] = Query(
        None,
        description="状态筛选: pending-待核对 / verified-已核对无误 / modified-有修改"
    ),
    has_modification: Optional[bool] = Query(
        None, description="是否仅显示有修改项的学生"
    ),
    keyword: Optional[str] = Query(None, description="搜索关键词（学号/姓名/身份证号）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(80, ge=1, le=200),
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep,
):
    """班级学生信息核对状态列表（分页）"""
    try:
        t_id = current_user.get("t_id")
        teacher_classes = _get_teacher_classes(db, t_id)
        teacher_bj_ids = [c.bj_id for c in teacher_classes]

        # 班级名映射（用于前端展示）
        class_name_map = {c.bj_id: (c.bj_mc or "") for c in teacher_classes}

        query_bj_ids = _resolve_query_bj_ids(teacher_bj_ids, bj_id)
        if query_bj_ids is None:
            raise HTTPException(status_code=403, detail="无权限查看该班级")
        if not query_bj_ids:
            return {
                "success": True, "msg": "获取成功",
                "data": {
                    "students": [], "total": 0,
                    "all_count": 0, "pending_count": 0,
                    "verified_count": 0, "modified_count": 0,
                    "page": page, "page_size": page_size,
                },
            }

        students_query = db.query(Student).filter(Student.xs_bj_id.in_(query_bj_ids))
        all_count = students_query.count()

        # 状态筛选
        if status_filter in STATUS_META:
            students_query = students_query.filter(
                Student.xs_info_verify_status == status_filter
            )

        if keyword and keyword.strip():
            kw = keyword.strip()
            students_query = students_query.filter(
                or_(
                    Student.xs_xm.like(f"%{kw}%"),
                    Student.xs_xh.like(f"%{kw}%"),
                    Student.xs_sfzh.like(f"%{kw}%"),
                )
            )

        # 取全部待渲染（含过滤后），后置再做 modified 过滤（要解析 JSON）
        candidates = students_query.order_by(Student.xs_id.desc()).all()

        rows: List[Dict[str, Any]] = []
        for s in candidates:
            status = s.xs_info_verify_status or "pending"
            if status not in STATUS_META:
                status = "pending"
            record = _safe_json_loads(s.xs_info_verify_record)
            modified = record.get("modified") or {}
            modification_count = len(modified)

            if has_modification is True and modification_count == 0:
                continue
            if has_modification is False and modification_count > 0:
                continue

            rows.append({
                "id": s.xs_id,
                "xm": s.xs_xm,
                "xh": s.xs_xh,
                "bj_id": s.xs_bj_id,
                "bj_mc": class_name_map.get(s.xs_bj_id, ""),
                "xb": s.xs_xb,
                "status": status,
                "status_text": STATUS_META[status]["text"],
                "submitted_at": record.get("submitted_at"),
                "modified_fields": list(modified.keys()),
                "modification_count": modification_count,
                "history_count": len(record.get("history") or []),
            })

        total = len(rows)

        # 统计（在 has_modification 过滤之前基于全班级）
        all_in_classes = db.query(Student.xs_info_verify_status, func.count(Student.xs_id)).filter(
            Student.xs_bj_id.in_(query_bj_ids)
        ).group_by(Student.xs_info_verify_status).all()
        status_stats_raw = dict(all_in_classes)
        pending_count = status_stats_raw.get("pending", 0) + status_stats_raw.get(None, 0)
        verified_count = status_stats_raw.get("verified", 0)
        modified_count = status_stats_raw.get("modified", 0)

        # 分页
        start = (page - 1) * page_size
        paged = rows[start:start + page_size]

        return {
            "success": True, "msg": "获取成功",
            "data": {
                "students": paged,
                "total": total,
                "all_count": all_count,
                "pending_count": pending_count,
                "verified_count": verified_count,
                "modified_count": modified_count,
                "page": page,
                "page_size": page_size,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("获取信息核对列表失败")
        return {"success": False, "msg": f"获取失败: {e}", "data": None}


@router.get("/detail")
def get_info_verify_detail(
    xs_id: int = Query(..., description="学生 ID"),
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep,
):
    """单个学生的核对详情：原始值、当前值、修改项、历次提交历史"""
    try:
        t_id = current_user.get("t_id")
        teacher_bj_ids = _get_teacher_class_ids(db, t_id)

        student = db.query(Student).filter(Student.xs_id == xs_id).first()
        if not student:
            raise HTTPException(status_code=404, detail="学生不存在")
        if student.xs_bj_id not in teacher_bj_ids:
            raise HTTPException(status_code=403, detail="无权限查看该学生")

        status = student.xs_info_verify_status or "pending"
        if status not in STATUS_META:
            status = "pending"

        record = _safe_json_loads(student.xs_info_verify_record)
        original = record.get("original") or {}
        modified = record.get("modified") or {}
        history = record.get("history") or []

        # 当前真实值（数据库）
        current = {f: getattr(student, f, None) for f in VERIFY_FIELDS}

        # diff：原始 → 当前 = 修改后值
        diffs = []
        for f in VERIFY_FIELDS:
            old_v = original.get(f, "") or ""
            cur_v = current.get(f, "") or ""
            diffs.append({
                "field": f,
                "label": FIELD_LABELS.get(f, f),
                "old": old_v,
                "new": cur_v,
                "changed": (old_v != cur_v),
            })

        return {
            "success": True, "msg": "获取成功",
            "data": {
                "student_no": student.xs_xh,
                "student_name": student.xs_xm,
                "status": status,
                "status_text": STATUS_META[status]["text"],
                "submitted_at": record.get("submitted_at"),
                "original": original,
                "current": current,
                "modified": modified,
                "field_labels": FIELD_LABELS,
                "diffs": diffs,
                "history": history,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("获取信息核对详情失败")
        return {"success": False, "msg": f"获取失败: {e}", "data": None}


@router.get("/export")
def export_info_verify(
    bj_id: Optional[int] = Query(None, description="班级ID"),
    only_modified: bool = Query(True, description="默认只导出有修改的学生"),
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep,
):
    """导出 csv：每个学生一行，只包含有修改的字段（原值 → 修改后值）"""
    try:
        t_id = current_user.get("t_id")
        teacher_classes = _get_teacher_classes(db, t_id)
        teacher_bj_ids = [c.bj_id for c in teacher_classes]
        class_name_map = {c.bj_id: (c.bj_mc or "") for c in teacher_classes}

        query_bj_ids = _resolve_query_bj_ids(teacher_bj_ids, bj_id)
        if query_bj_ids is None:
            raise HTTPException(status_code=403, detail="无权限")
        if not query_bj_ids:
            raise HTTPException(status_code=404, detail="无班级数据")

        students = db.query(Student).filter(
            Student.xs_bj_id.in_(query_bj_ids)
        ).order_by(Student.xs_bj_id, Student.xs_xh).all()

        # 第一次遍历：只保留有修改的学生，同时收集所有被修改过的字段键
        modified_students: List[tuple] = []
        all_modified_keys: set = set()

        for s in students:
            record = _safe_json_loads(s.xs_info_verify_record)
            original = record.get("original") or {}
            modified = record.get("modified") or {}
            status = s.xs_info_verify_status or "pending"
            if status not in STATUS_META:
                status = "pending"
            modification_count = len(modified)

            if only_modified and modification_count == 0:
                continue

            # 记录所有被修改的字段键
            if modification_count > 0:
                all_modified_keys.update(modified.keys())

            modified_students.append((s, record, status, modification_count))

        if not modified_students:
            # 无数据也返回空文件，浏览器能正常下载
            csv_bytes = "\ufeff".encode("utf-8")
            filename = f"info_verify_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            return StreamingResponse(
                io.BytesIO(csv_bytes),
                media_type="text/csv",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "Content-Type": "text/csv; charset=utf-8",
                    "X-Exported-Count": "0",
                },
            )

        # 动态表头：基本信息 + 每个被修改的字段两列（原始值 → 修改后值）
        # 按 FIELD_LABELS 顺序排序，保持一致性
        sorted_keys = sorted(all_modified_keys, key=lambda f: VERIFY_FIELDS.index(f) if f in VERIFY_FIELDS else 99)
        base_headers = ["学号", "姓名", "班级", "核对状态", "提交时间"]
        field_headers: List[str] = []
        for f in sorted_keys:
            label = FIELD_LABELS.get(f, f)
            field_headers.append(f"{label}-原值")
            field_headers.append(f"{label}-修改后")

        headers = base_headers + field_headers

        buf = io.StringIO()
        writer = csv.writer(buf, dialect="excel")
        writer.writerow(headers)

        for s, record, status, modification_count in modified_students:
            original = record.get("original") or {}
            submitted_at = record.get("submitted_at") or ""

            base_row = [
                s.xs_xh or "",
                s.xs_xm or "",
                class_name_map.get(s.xs_bj_id, ""),
                STATUS_META[status]["text"],
                submitted_at,
            ]
            field_rows: List[str] = []
            for f in sorted_keys:
                field_rows.append(original.get(f, "") or "")
                field_rows.append(getattr(s, f, "") or "")

            writer.writerow(base_row + field_rows)

        csv_text = buf.getvalue()
        buf.close()
        csv_bytes = ("\ufeff" + csv_text).encode("utf-8")

        filename = f"info_verify_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        return StreamingResponse(
            io.BytesIO(csv_bytes),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": "text/csv; charset=utf-8",
                "X-Exported-Count": str(len(modified_students)),
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("导出信息核对失败")
        raise HTTPException(status_code=500, detail=f"导出失败: {e}")


class ResetRequest(BaseModel):
    xs_id: int


@router.post("/reset")
def reset_student_verify(
    body: ResetRequest,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep,
):
    """重置学生的核对状态，让学生可重新提交。

    仅对 verified / modified 状态生效；pending 状态无意义直接返回成功。
    重置后 xs_info_verify_status → pending，xs_info_verify_record → None。
    """
    try:
        t_id = current_user.get("t_id")
        teacher_bj_ids = _get_teacher_class_ids(db, t_id)

        student = db.query(Student).filter(Student.xs_id == body.xs_id).first()
        if not student:
            raise HTTPException(status_code=404, detail="学生不存在")
        if student.xs_bj_id not in teacher_bj_ids:
            raise HTTPException(status_code=403, detail="无权限操作该学生")

        current_status = student.xs_info_verify_status or "pending"
        if current_status == "pending":
            return {"success": True, "msg": "该学生已是待核对状态，无需重置", "data": None}

        student.xs_info_verify_status = "pending"
        student.xs_info_verify_record = None

        db.commit()
        logger.info(f"教师 {t_id} 重置了学生 {body.xs_id} 的核对状态 → pending")

        return {
            "success": True,
            "msg": f"已重置，学生可重新提交核对",
            "data": {"xs_id": body.xs_id, "new_status": "pending"},
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("重置核对状态失败")
        return {"success": False, "msg": f"重置失败: {e}", "data": None}