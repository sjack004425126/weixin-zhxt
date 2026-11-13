"""
用户本人头像控制器（统一"查询 + 上传"）

服务于 4 个个人中心页面顶部的头像：
  - packageStudent/pages/my/my                                （开放大学学生）
  - packageVocational/pages/vocational-my/vocational-my       （中职学生）
  - packageTeacher/pages/open-teacher-my/open-teacher-my       （开放大学教师）
  - packageTeacher/pages/vocational-teacher-home/vocational-teacher-home（中职教师）

头像存储位置（与历史保持一致）：
  - 开放大学学生：私有桶  headphoto/open/<sfzh>.jpg
  - 中职学生    ：私有桶  headphoto/vocational/<sfzh>.jpg
  - 教师        ：zhxt 桶  teacher_head_photo/<t_yhm>.jpg

统一处理流水线（与原 packageStudent/pages/photo-upload 页面一致）：
  AI 抠图换底 + 美颜 → 上传 MinIO → 更新 DB → 异步同步海康（失败不阻断主流程）

设计要点：
  1. 身份完全由 JWT 推导，前端不传身份证号，杜绝越权。
  2. 抠图/美化/上传/海康同步都走 services/photo_task_service，
     前端只需"提交任务 + 轮询 /photo/task_status/{task_id}"。
  3. 新登录的 token 会带上 user_type / sfzh，老 token 用 payload 特征字段兜底推导。
"""
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from common.auth import verify_token_and_get_payload
from init.dependencies import DatabaseDep
from models.models import Student, Teacher, ZzXs
from services.minio_service import (
    check_photo_exists,
    check_teacher_headphoto_exists,
    get_photo_url,
    get_teacher_headphoto_url,
    user_type_to_headphoto_subdir,
)

router = APIRouter(prefix="/photo", tags=["用户头像"])

logger = logging.getLogger(__name__)

# 主体类型
SUBJECT_OPEN_STUDENT = "open_student"
SUBJECT_VOCATIONAL_STUDENT = "vocational_student"
SUBJECT_TEACHER = "teacher"

# 默认美颜参数（轻量美化，避免过度磨皮）
DEFAULT_AVATAR_BEAUTY = {
    "whitening_strength": 8,    # 美白 0-30
    "brightness_strength": 5,   # 亮度 -20~20
    "contrast_strength": 5,     # 对比度 -100~100
    "sharpen_strength": 2,      # 锐化 0-5
    "saturation_strength": 5,   # 饱和度 -100~100
}


# ============================================================
# 身份推导
# ============================================================
def _resolve_subject(current_user: dict, db: Session) -> Optional[dict]:
    """根据 JWT payload 推导当前用户的主体信息。

    返回结构：
        {
            "subject_type": open_student | vocational_student | teacher,
            "sfzh":        身份证号（教师可能为空 → 不同步海康）,
            "identifier":  学生=身份证号；教师=工号(t_yhm),
            "name":        姓名,
        }
    """
    if not current_user:
        return None

    # ---------- 1. 教师（payload 带 t_yhm） ----------
    t_yhm = current_user.get("t_yhm")
    if t_yhm:
        teacher = db.query(Teacher).filter_by(t_yhm=t_yhm).first()
        return {
            "subject_type": SUBJECT_TEACHER,
            "sfzh": (current_user.get("t_sfzh") or (teacher.t_sfzh if teacher else "")) or "",
            "identifier": t_yhm,
            "name": (current_user.get("t_xm") or (teacher.t_xm if teacher else "")) or "",
        }

    # ---------- 2. 学生（新 token 直接带 user_type / sfzh） ----------
    user_type = (current_user.get("user_type") or "").strip()
    sfzh = (current_user.get("sfzh") or "").strip()
    if sfzh:
        if user_type in (SUBJECT_VOCATIONAL_STUDENT, "vocational", "zz"):
            subject_type = SUBJECT_VOCATIONAL_STUDENT
        else:
            subject_type = SUBJECT_OPEN_STUDENT
        return {
            "subject_type": subject_type,
            "sfzh": sfzh,
            "identifier": sfzh,
            "name": current_user.get("xs_xm") or current_user.get("xm") or "",
        }

    # ---------- 3. 老 token 兜底：按 payload 特征字段 + DB 反查 ----------
    xs_id = current_user.get("xs_id")

    # 开放大学学生 token 特征：dq1_mc / sys_pc / bj_id
    if "dq1_mc" in current_user or "sys_pc" in current_user:
        row = db.query(Student).filter_by(xs_id=xs_id).first() if xs_id else None
        if row:
            return {
                "subject_type": SUBJECT_OPEN_STUDENT,
                "sfzh": row.xs_sfzh or "",
                "identifier": row.xs_sfzh or "",
                "name": row.xs_xm or "",
            }
        return None

    # 中职学生 token 特征：xs_bj_id
    if "xs_bj_id" in current_user:
        row = db.query(ZzXs).filter_by(id=xs_id).first() if xs_id else None
        if row:
            return {
                "subject_type": SUBJECT_VOCATIONAL_STUDENT,
                "sfzh": row.sfzh or "",
                "identifier": row.sfzh or "",
                "name": row.xm or "",
            }
        return None

    return None


def _subdir_of(subject_type: str) -> str:
    """学生头像在私有桶中的子目录。"""
    if subject_type == SUBJECT_VOCATIONAL_STUDENT:
        return user_type_to_headphoto_subdir("vocational")
    return user_type_to_headphoto_subdir("open")


# ============================================================
# 查询本人头像
# ============================================================
@router.get("/my_avatar")
async def get_my_avatar(
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep,
):
    """查询当前登录用户的头像状态。

    返回：
        has_photo:   是否已有头像（MinIO 文件为准）
        photo_url:   头像预签名 URL（没有则 None）
        can_upload:  是否允许上传（恒为 True，允许覆盖更新）
        subject_type: open_student / vocational_student / teacher
        name:        用户姓名
    """
    try:
        subject = _resolve_subject(current_user, db)
        if not subject:
            return {"success": False, "msg": "无法识别当前用户身份", "data": None}

        subject_type = subject["subject_type"]

        if subject_type == SUBJECT_TEACHER:
            identifier = subject["identifier"]
            exists = check_teacher_headphoto_exists(identifier)
            photo_url = get_teacher_headphoto_url(identifier) if exists else None
        else:
            identifier = subject["identifier"]
            if not identifier:
                return {"success": False, "msg": "当前用户缺少身份证号，无法定位头像", "data": None}
            subdir = _subdir_of(subject_type)
            exists = check_photo_exists(identifier, subdir=subdir)
            photo_url = get_photo_url(identifier, subdir=subdir) if exists else None

        return {
            "success": True,
            "msg": "查询成功",
            "data": {
                "has_photo": bool(exists),
                "photo_url": photo_url,
                "can_upload": True,
                "subject_type": subject_type,
                "name": subject["name"],
            },
        }
    except Exception as e:
        logger.error(f"查询本人头像失败: {str(e)}")
        return {"success": False, "msg": f"查询失败: {str(e)}", "data": None}


# ============================================================
# 上传本人头像（异步任务）
# ============================================================
class UploadMyAvatarResult(BaseModel):
    task_id: str


@router.post("/upload_my_avatar")
async def upload_my_avatar(
    photo: UploadFile = File(...),
    size_name: str = Form(default="two_inch"),
    bg_color_name: str = Form(default="blue"),
    whitening_strength: int = Form(default=DEFAULT_AVATAR_BEAUTY["whitening_strength"]),
    brightness_strength: int = Form(default=DEFAULT_AVATAR_BEAUTY["brightness_strength"]),
    contrast_strength: int = Form(default=DEFAULT_AVATAR_BEAUTY["contrast_strength"]),
    sharpen_strength: int = Form(default=DEFAULT_AVATAR_BEAUTY["sharpen_strength"]),
    saturation_strength: int = Form(default=DEFAULT_AVATAR_BEAUTY["saturation_strength"]),
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep,
):
    """上传当前登录用户本人的头像。

    后端自动完成：AI 抠图换底 + 美颜 → 上传 MinIO → 更新 DB → 异步同步海康。

    立即返回 task_id，前端轮询 GET /photo/task_status/{task_id} 获取结果。
    """
    try:
        subject = _resolve_subject(current_user, db)
        if not subject:
            return {"success": False, "msg": "无法识别当前用户身份", "data": None}

        file_content = await photo.read()
        if not file_content:
            return {"success": False, "msg": "照片内容为空", "data": None}
        if len(file_content) > 5 * 1024 * 1024:
            return {"success": False, "msg": "照片大小不能超过5MB", "data": None}

        if subject["subject_type"] != SUBJECT_TEACHER and not subject["identifier"]:
            return {"success": False, "msg": "当前用户缺少身份证号，无法上传头像", "data": None}

        from services.beauty_params import build_beauty_params
        from services.photo_task_service import create_avatar_task

        beauty = build_beauty_params(
            whitening_strength,
            brightness_strength,
            contrast_strength,
            sharpen_strength,
            saturation_strength,
        )

        task_id = await create_avatar_task(
            file_content=file_content,
            subject_type=subject["subject_type"],
            sfzh=subject["sfzh"],
            identifier=subject["identifier"],
            size_name=size_name,
            bg_color_name=bg_color_name,
            beauty=beauty,
        )

        return {
            "success": True,
            "msg": "任务已创建，请轮询获取结果",
            "data": {"task_id": task_id},
        }
    except Exception as e:
        logger.error(f"上传本人头像失败: {str(e)}")
        return {"success": False, "msg": f"上传失败: {str(e)}", "data": None}
