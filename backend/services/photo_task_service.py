"""
照片处理任务服务
使用 Redis 存储任务状态，支持异步处理和状态查询

v2 重构：
- 上传后端处理完成后，自动上传 MinIO + 更新 DB + 异步同步海康
- 前端只负责选图 + 轮询，不需要再传 base64
"""
import asyncio
import uuid
import logging
import base64
from typing import Optional, Dict, Any
from enum import Enum
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# 任务状态枚举
class TaskStatus(str, Enum):
    PENDING = "pending"            # 等待处理
    PROCESSING = "processing"      # AI 抠图中
    UPLOADING = "uploading"        # 上传 MinIO 中
    SYNCING = "syncing"            # 同步海康中
    COMPLETED = "completed"        # 全部完成
    FAILED = "failed"              # 失败


# 任务配置
TASK_EXPIRE_SECONDS = 3600        # 任务结果保存1小时
MAX_CONCURRENT_TASKS = 5          # 最大并发任务数
TASK_TIMEOUT = 60                 # 单个任务超时时间（秒）

# 线程池执行器（用于CPU密集型任务）
_executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_TASKS, thread_name_prefix="photo_task_")

# 任务信号量
_task_semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)


def _get_task_key(task_id: str) -> str:
    """获取任务的Redis键"""
    return f"zhpt:photo_task:{task_id}"


def _generate_task_id() -> str:
    """生成唯一任务ID"""
    return str(uuid.uuid4())[:8]


# ============================================================
# Redis 读写辅助
# ============================================================
def _save_task(task_key: str, data: Dict[str, Any]) -> None:
    from init.redis_manager import redis_manager
    redis_manager.set(task_key, data, ex=TASK_EXPIRE_SECONDS)


def _read_task(task_key: str) -> Dict[str, Any]:
    from init.redis_manager import redis_manager
    return redis_manager.get(task_key) or {}


# ============================================================
# 创建任务
# ============================================================
async def create_photo_task(
    file_content: bytes,
    sfzh: str,
    user_type: str = "student",
    size_name: str = "two_inch",
    bg_color_name: str = "blue",
    uploaded_by_teacher: bool = False,
    beauty: Optional[Dict[str, Any]] = None,
) -> str:
    """
    创建照片处理任务（含抠图、上传 MinIO、同步海康的完整流水线）

    Args:
        file_content: 原始图片二进制数据
        sfzh:         身份证号
        user_type:    用户类型(student / vocational)
        size_name:    尺寸名称
        bg_color_name:背景色
        uploaded_by_teacher: 是否由教师上传(权限)
        beauty:       美颜参数（默认全 0 = 不美颜）

    Returns:
        task_id
    """
    task_id = _generate_task_id()
    task_key = _get_task_key(task_id)

    task_data = {
        "status": TaskStatus.PENDING,
        "created_at": datetime.now().isoformat(),
        "progress": 0,
        "step": "排队中",
        "sfzh": sfzh,
        "user_type": user_type,
        "size_name": size_name,
        "bg_color_name": bg_color_name,
        "uploaded_by_teacher": uploaded_by_teacher,
        "beauty": beauty or {},
        "result": None,
        "error": None,
        "completed_at": None,
    }

    _save_task(task_key, task_data)

    # 启动异步流水线
    asyncio.create_task(
        _process_photo_pipeline(
            task_id, file_content, sfzh, user_type, size_name,
            bg_color_name, uploaded_by_teacher, beauty or {}
        )
    )

    logger.info(f"创建照片处理任务: {task_id} (sfzh={sfzh})")
    return task_id


# ============================================================
# 异步流水线：抠图 → MinIO → 海康 → DB
# ============================================================
async def _process_photo_pipeline(
    task_id: str,
    file_content: bytes,
    sfzh: str,
    user_type: str,
    size_name: str,
    bg_color_name: str,
    uploaded_by_teacher: bool,
    beauty: Optional[Dict[str, Any]] = None,
):
    task_key = _get_task_key(task_id)

    # ---- 0. 入口信号量 ----
    try:
        await asyncio.wait_for(_task_semaphore.acquire(), timeout=30.0)
    except asyncio.TimeoutError:
        _update(task_key, status=TaskStatus.FAILED, error="服务器繁忙，请稍后重试", completed=True)
        logger.warning(f"任务 {task_id} 获取信号量超时")
        return

    try:
        # ---- 1. AI 抠图 ----
        _update(task_key, status=TaskStatus.PROCESSING, progress=10, step="AI 正在抠图...")

        loop = asyncio.get_event_loop()

        def _do_process():
            from services.hivision_processor import process_id_photo
            return process_id_photo(
                file_content,
                size_name=size_name,
                bg_color_name=bg_color_name,
                beauty=beauty or {}
            )

        processed_content = await asyncio.wait_for(
            loop.run_in_executor(_executor, _do_process),
            timeout=TASK_TIMEOUT
        )

        processed_b64 = base64.b64encode(processed_content).decode("utf-8")
        _update(task_key, progress=50, step="抠图完成")

        # ---- 2. 上传 MinIO ----
        _update(task_key, status=TaskStatus.UPLOADING, progress=55, step="正在上传 MinIO...")

        from services.minio_service import upload_photo, user_type_to_headphoto_subdir
        subdir = user_type_to_headphoto_subdir(user_type)
        await asyncio.to_thread(upload_photo, sfzh, processed_content, "image/jpeg", subdir)
        _update(task_key, progress=75, step="上传 MinIO 完成")

        # ---- 3. 更新 DB ----
        from init.dependencies import get_db_sync
        from models.models import Student, ZzXs

        sync_db = get_db_sync()
        student_name = ""
        try:
            if user_type == "vocational":
                user = sync_db.query(ZzXs).filter_by(sfzh=sfzh).first()
                if user:
                    user.headphoto = 1
                    user.issync = 0  # 海康同步是附加流程,失败不影响主流程
                    student_name = user.xm or ""
            else:
                user = sync_db.query(Student).filter_by(xs_sfzh=sfzh).first()
                if user:
                    user.headphoto = 1
                    student_name = user.xs_xm or ""
            sync_db.commit()
        except Exception as db_err:
            sync_db.rollback()
            logger.error(f"更新 headphoto 失败: sfzh={sfzh}, error={db_err}")
        finally:
            sync_db.close()

        _update(task_key, progress=85, step="数据库已更新")

        # ---- 4. 同步海康(失败不影响主流程) ----
        _update(task_key, status=TaskStatus.SYNCING, progress=90, step="正在同步海康...")

        try:
            from services.hikvision_sync_service import get_hikvision_sync_service
            svc = get_hikvision_sync_service()
            hk_result = await svc.sync_photo_to_hikvision(sfzh, processed_b64)

            # 海康成功后再更新 issync=1
            if hk_result.get("success"):
                db2 = get_db_sync()
                try:
                    if user_type == "vocational":
                        u = db2.query(ZzXs).filter_by(sfzh=sfzh).first()
                        if u:
                            u.issync = 1
                    else:
                        # 开放大学没有 issync 字段,跳过
                        pass
                    db2.commit()
                except Exception:
                    db2.rollback()
                finally:
                    db2.close()
                logger.info(f"海康同步成功 sfzh={sfzh}")
            else:
                logger.warning(f"海康同步失败 sfzh={sfzh}: {hk_result.get('message')}")
        except Exception as hk_err:
            # 海康是附加流程,不阻断主流程
            logger.error(f"海康同步异常 sfzh={sfzh}: {hk_err}")

        # ---- 5. 完成 ----
        from services.minio_service import get_photo_url as _signed_photo_url
        photo_url = _signed_photo_url(sfzh, subdir=subdir)

        _update(
            task_key,
            status=TaskStatus.COMPLETED,
            progress=100,
            step="处理完成",
            completed=True,
            result={
                "photo_url": photo_url,
                "sfzh": sfzh,
            },
        )
        logger.info(f"任务 {task_id} 全部完成")

    except asyncio.TimeoutError:
        _update(task_key, status=TaskStatus.FAILED, error="图片处理超时，请重试", completed=True)
        logger.error(f"任务 {task_id} 处理超时")
    except ValueError as e:
        _update(task_key, status=TaskStatus.FAILED, error=str(e), completed=True)
        logger.warning(f"任务 {task_id} 业务失败: {e}")
    except Exception as e:
        _update(
            task_key,
            status=TaskStatus.FAILED,
            error="照片处理失败，请确保照片中有清晰的人像，建议重新拍摄",
            completed=True,
        )
        logger.error(f"任务 {task_id} 处理失败: {e}")
    finally:
        _task_semaphore.release()


def _update(task_key: str, **fields) -> None:
    """局部更新任务状态"""
    data = _read_task(task_key)
    data.update(fields)
    _save_task(task_key, data)


# ============================================================
# 查询接口
# ============================================================
async def get_task_status(task_id: str) -> Optional[Dict[str, Any]]:
    """获取任务状态(完整数据)"""
    task_key = _get_task_key(task_id)
    data = _read_task(task_key)
    return data or None


async def get_task_result(task_id: str) -> Optional[str]:
    """仅当任务完成时返回 base64(本重构后不再使用,保留兼容)"""
    task_data = await get_task_status(task_id)
    if task_data and task_data.get("status") == TaskStatus.COMPLETED:
        return task_data.get("result")
    return None


def get_queue_info() -> Dict[str, Any]:
    return {
        "max_concurrent": MAX_CONCURRENT_TASKS,
        "available_slots": _task_semaphore._value,
        "task_timeout": TASK_TIMEOUT,
        "result_expire": TASK_EXPIRE_SECONDS,
    }


# ============================================================
# 用户本人头像任务（v3）
# ------------------------------------------------------------
# 与学生照片流水线（create_photo_task）共用抠图/美颜/上传/海康能力，
# 区别：
#   1. 主体可以是学生（开放/中职）或教师，教师头像走 zhxt 桶
#   2. 允许覆盖更新（不像学生照片那样"已有照片禁止重复上传"）
#   3. 教师无身份证号时跳过海康同步
# ============================================================
SUBJECT_TEACHER = "teacher"


async def create_avatar_task(
    file_content: bytes,
    subject_type: str,
    sfzh: str,
    identifier: str,
    size_name: str = "two_inch",
    bg_color_name: str = "blue",
    beauty: Optional[Dict[str, Any]] = None,
) -> str:
    """创建"本人头像"处理任务，返回 task_id。

    Args:
        file_content: 原始图片二进制
        subject_type: open_student / vocational_student / teacher
        sfzh:         身份证号（教师可为空 → 不做海康同步）
        identifier:   学生=身份证号；教师=工号(t_yhm)
        size_name:    尺寸名称
        bg_color_name:背景色
        beauty:       美颜参数
    """
    task_id = _generate_task_id()
    task_key = _get_task_key(task_id)

    task_data = {
        "status": TaskStatus.PENDING,
        "created_at": datetime.now().isoformat(),
        "progress": 0,
        "step": "排队中",
        "task_kind": "avatar",
        "subject_type": subject_type,
        "sfzh": sfzh,
        "identifier": identifier,
        "size_name": size_name,
        "bg_color_name": bg_color_name,
        "beauty": beauty or {},
        "result": None,
        "error": None,
        "completed_at": None,
    }

    _save_task(task_key, task_data)

    asyncio.create_task(
        _process_avatar_pipeline(
            task_id, file_content, subject_type, sfzh, identifier,
            size_name, bg_color_name, beauty or {},
        )
    )

    logger.info(f"创建头像处理任务: {task_id} (subject_type={subject_type}, identifier={identifier})")
    return task_id


async def _process_avatar_pipeline(
    task_id: str,
    file_content: bytes,
    subject_type: str,
    sfzh: str,
    identifier: str,
    size_name: str,
    bg_color_name: str,
    beauty: Optional[Dict[str, Any]] = None,
):
    """头像处理流水线：抠图+美颜 → 上传 MinIO → 更新 DB → 同步海康。"""
    task_key = _get_task_key(task_id)

    # ---- 0. 入口信号量 ----
    try:
        await asyncio.wait_for(_task_semaphore.acquire(), timeout=30.0)
    except asyncio.TimeoutError:
        _update(task_key, status=TaskStatus.FAILED, error="服务器繁忙，请稍后重试", completed=True)
        logger.warning(f"头像任务 {task_id} 获取信号量超时")
        return

    is_teacher = subject_type == SUBJECT_TEACHER

    try:
        # ---- 1. AI 抠图 + 美颜 ----
        _update(task_key, status=TaskStatus.PROCESSING, progress=15, step="AI 正在抠图美化...")

        loop = asyncio.get_event_loop()

        def _do_process():
            from services.hivision_processor import process_id_photo
            return process_id_photo(
                file_content,
                size_name=size_name,
                bg_color_name=bg_color_name,
                beauty=beauty or {},
            )

        processed_content = await asyncio.wait_for(
            loop.run_in_executor(_executor, _do_process),
            timeout=TASK_TIMEOUT,
        )

        processed_b64 = base64.b64encode(processed_content).decode("utf-8")
        _update(task_key, progress=55, step="抠图美化完成")

        # ---- 2. 上传 MinIO ----
        _update(task_key, status=TaskStatus.UPLOADING, progress=65, step="正在上传 MinIO...")

        from services.minio_service import (
            get_photo_url as _signed_photo_url,
            get_teacher_headphoto_url,
            upload_photo,
            upload_teacher_headphoto,
            user_type_to_headphoto_subdir,
        )

        if is_teacher:
            await asyncio.to_thread(
                upload_teacher_headphoto,
                username=identifier,
                file_content=processed_content,
                content_type="image/jpeg",
                ext="jpg",
            )
            photo_url = get_teacher_headphoto_url(identifier)
        else:
            subdir = user_type_to_headphoto_subdir(
                "vocational" if subject_type == "vocational_student" else "open"
            )
            await asyncio.to_thread(
                upload_photo, identifier, processed_content, "image/jpeg", subdir
            )
            photo_url = _signed_photo_url(identifier, subdir=subdir)

        _update(task_key, progress=80, step="上传完成")

        # ---- 3. 更新 DB（学生标记 headphoto=1） ----
        if not is_teacher:
            from init.dependencies import get_db_sync
            from models.models import Student, ZzXs

            sync_db = get_db_sync()
            try:
                if subject_type == "vocational_student":
                    user = sync_db.query(ZzXs).filter_by(sfzh=identifier).first()
                    if user:
                        user.headphoto = 1
                        user.issync = 0
                else:
                    user = sync_db.query(Student).filter_by(xs_sfzh=identifier).first()
                    if user:
                        user.headphoto = 1
                sync_db.commit()
            except Exception as db_err:
                sync_db.rollback()
                logger.error(f"更新 headphoto 失败: identifier={identifier}, error={db_err}")
            finally:
                sync_db.close()

        _update(task_key, progress=88, step="数据库已更新")

        # ---- 4. 同步海康（失败不阻断主流程；教师无身份证号则跳过） ----
        if sfzh:
            _update(task_key, status=TaskStatus.SYNCING, progress=92, step="正在同步海康...")
            try:
                from services.hikvision_sync_service import get_hikvision_sync_service
                svc = get_hikvision_sync_service()
                hk_result = await svc.sync_photo_to_hikvision(sfzh, processed_b64)

                if hk_result.get("success"):
                    # 中职学生同步成功后标记 issync=1
                    if subject_type == "vocational_student":
                        from init.dependencies import get_db_sync
                        db2 = get_db_sync()
                        try:
                            u = db2.query(ZzXs).filter_by(sfzh=identifier).first()
                            if u:
                                u.issync = 1
                            db2.commit()
                        except Exception:
                            db2.rollback()
                        finally:
                            db2.close()
                    logger.info(f"海康同步成功 sfzh={sfzh}")
                else:
                    logger.warning(f"海康同步失败 sfzh={sfzh}: {hk_result.get('message')}")
            except Exception as hk_err:
                logger.error(f"海康同步异常 sfzh={sfzh}: {hk_err}")
        else:
            logger.info(f"头像任务 {task_id} 无身份证号，跳过海康同步")

        # ---- 5. 完成 ----
        _update(
            task_key,
            status=TaskStatus.COMPLETED,
            progress=100,
            step="处理完成",
            completed=True,
            result={
                "photo_url": photo_url,
                "identifier": identifier,
                "subject_type": subject_type,
            },
        )
        logger.info(f"头像任务 {task_id} 全部完成")

    except asyncio.TimeoutError:
        _update(task_key, status=TaskStatus.FAILED, error="图片处理超时，请重试", completed=True)
        logger.error(f"头像任务 {task_id} 处理超时")
    except ValueError as e:
        _update(task_key, status=TaskStatus.FAILED, error=str(e), completed=True)
        logger.warning(f"头像任务 {task_id} 业务失败: {e}")
    except Exception as e:
        _update(
            task_key,
            status=TaskStatus.FAILED,
            error="照片处理失败，请确保照片中有清晰的人像，建议重新拍摄",
            completed=True,
        )
        logger.error(f"头像任务 {task_id} 处理失败: {e}")
    finally:
        _task_semaphore.release()
