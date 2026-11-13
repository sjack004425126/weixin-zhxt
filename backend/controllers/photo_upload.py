"""
照片上传控制器
用于处理用户头像照片的上传
"""
from fastapi import APIRouter, Depends, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session
from models.models import Student, ZzXs
from init.dependencies import DatabaseDep
from common.auth import verify_token_and_get_payload
from services.minio_service import (
    user_type_to_headphoto_subdir,
    upload_teacher_headphoto as minio_upload_teacher_headphoto,
    check_teacher_headphoto_exists,
    get_teacher_headphoto_url,
)
import logging
import base64
import hashlib
import asyncio

router = APIRouter(prefix="/photo", tags=["照片上传"])

# 头像签名配置已统一在 services/minio_service.py 维护
# （使用 STATIC_LINK_SECRET，签名算法为 sha256(...)[:16]）


def _parse_beauty_form(
    whitening_strength: int = 0,
    brightness_strength: int = 0,
    contrast_strength: int = 0,
    sharpen_strength: int = 0,
    saturation_strength: int = 0,
) -> dict:
    """把 API 层的美颜表单参数组装成 services.hivision_processor 需要的字典。

    全部默认 0 = 不做任何美颜，**保持历史行为不变**。
    具体取值范围与裁剪逻辑统一由 services/hivision_processor.normalize_beauty 负责。
    实现与 headphoto 端共用 services/beauty_params.py（两边内容一致）。
    """
    from services.beauty_params import build_beauty_params

    return build_beauty_params(
        whitening_strength,
        brightness_strength,
        contrast_strength,
        sharpen_strength,
        saturation_strength,
    )


# ============================================================
# 签名工具（薄封装，委托 services/minio_service）
# 重构后：所有签名逻辑统一在 services/minio_service.py 维护；
# 这里仅做函数名兼容，确保 controllers 其它地方引用不变。
# ============================================================
from services.minio_service import (
    STATIC_LINK_SECRET as _STATIC_LINK_SECRET,
    verify_photo_sign as _verify_photo_sign_unified,
    sign_photo_url as _sign_photo_url_unified,
)


def generate_photo_sign(sfzh: str, timestamp: int) -> str:
    """生成图片访问签名（兼容老接口，委托到统一签名）"""
    raw = f"{sfzh}{timestamp}{_STATIC_LINK_SECRET}".encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def verify_photo_sign(sfzh: str, timestamp: int, sign: str) -> bool:
    """验证图片访问签名（兼容老接口，委托到统一签名）"""
    return _verify_photo_sign_unified(sfzh, timestamp, sign)


def get_signed_photo_url(sfzh: str, user_type: str = "open") -> str:
    """生成带签名的图片相对 URL（兼容老接口，委托到统一签名）。

    参数
    ----
    sfzh : 身份证号
    user_type : 用户类型，决定头像在 MinIO 上的子目录：
        * "open" / "student" → ``headphoto/open``
        * "vocational" / "zz" → ``headphoto/vocational``
        * "teacher"           → ``headphoto/teacher``

    返回相对路径（以 / 开头），前端拼接 BASE_URL 得到完整 URL。
    """
    subdir = user_type_to_headphoto_subdir(user_type)
    return _sign_photo_url_unified(sfzh, subdir=subdir)


# ============================================================
# 一体化照片处理流水线（抠图 → MinIO → DB → 海康同步）
# ------------------------------------------------------------
# 学生/教师自助上传头像统一走该流水线：
#   1. AI 抠图换底（HivisionIDPhotos）
#   2. 美颜（services/beauty_params.py）
#   3. 上传 MinIO
#   4. 更新 DB（headphoto=1, vocational 的 issync=0）
#   5. 异步同步海康（失败不影响主流程）
#
# 前端立即拿到 task_id，轮询 GET /photo/task_status/{task_id} 获取进度。
# ============================================================

@router.post('/process_photo_async')
async def process_photo_async(
    photo: UploadFile = File(...),
    sfzh: str = Form(...),
    user_type: str = Form(default="student"),
    size_name: str = Form(default="two_inch"),
    bg_color_name: str = Form(default="blue"),
    uploaded_by_teacher: bool = Form(default=False),
    whitening_strength: int = Form(default=0),
    brightness_strength: int = Form(default=0),
    contrast_strength: int = Form(default=0),
    sharpen_strength: int = Form(default=0),
    saturation_strength: int = Form(default=0),
    db: Session = DatabaseDep,
    current_user: dict = Depends(verify_token_and_get_payload),
):
    """
    一体化照片处理流水线(高并发推荐):
      1. AI 抠图换底
      2. 上传 MinIO
      3. 更新 DB(headphoto=1, vocational 的 issync=0)
      4. 异步同步海康(失败不影响主流程)

    立即返回 task_id,前端轮询 GET /photo/task_status/{task_id} 获取结果。

    Args:
        photo:              原始照片文件
        sfzh:               身份证号
        user_type:          student-开放大学 / vocational-中职
        size_name:          one_inch/two_inch/...
        bg_color_name:      blue/white/red/light_blue
        uploaded_by_teacher:是否教师代传(教师模式可覆盖已有照片)
        whitening_strength: 美白强度 0-30（默认 0 = 不美颜）
        brightness_strength: 亮度 -20~20（默认 0）
        contrast_strength: 对比度 -100~100（默认 0）
        sharpen_strength:   锐化 0-5（默认 0）
        saturation_strength:饱和度 -100~100（默认 0）
    """
    try:
        # ---- 鉴权 debug 日志(帮助定位 token 失败) ----
        logging.info(
            f"[process_photo_async] sfzh={sfzh}, user_type={user_type}, "
            f"uploaded_by_teacher={uploaded_by_teacher}, "
            f"current_user.sub={current_user.get('sub') if current_user else None}, "
            f"current_user.user_type={current_user.get('user_type') if current_user else None}, "
            f"current_user.role={current_user.get('role') if current_user else None}"
        )

        # ---- 参数校验 ----
        file_content = await photo.read()
        if not file_content:
            return {'success': False, 'msg': '照片内容为空', 'data': None}
        if len(file_content) > 5 * 1024 * 1024:
            return {'success': False, 'msg': '照片大小不能超过5MB', 'data': None}
        if not sfzh:
            return {'success': False, 'msg': '缺少身份证号参数', 'data': None}

        # ---- 鉴权:学生 token 必须与传入的 sfzh 一致(教师可代传) ----
        token_sfzh = current_user.get('sfzh') if current_user else None
        token_user_type = current_user.get('user_type') if current_user else None
        token_role = current_user.get('role') if current_user else None
        is_teacher_token = (
            current_user.get('is_vocational_teacher') or
            current_user.get('is_open_teacher') or
            current_user.get('t_id') is not None
        )
        if not uploaded_by_teacher:
            if is_teacher_token:
                # 教师 token 不带 uploaded_by_teacher flag 时不允许(必须是教师代传模式)
                return {'success': False, 'msg': '教师代传请确认操作', 'data': None}
            if token_role == 'student_photo':
                # 学生自拍:token 里的 sfzh 必须等于入参 sfzh
                if token_sfzh != sfzh:
                    return {'success': False, 'msg': '无权为他人上传照片', 'data': None}
                # token 的 user_type 也需匹配
                expected_ut = 'vocational' if user_type == 'vocational' else 'student'
                if token_user_type != expected_ut:
                    return {'success': False, 'msg': '用户类型不匹配', 'data': None}
            elif token_user_type not in ('admin', 'staff'):
                # 其他普通 token 不允许非教师模式下调用
                return {'success': False, 'msg': '无上传权限', 'data': None}

        # ---- 权限检查:学生自己上传且已有照片则不允许 ----
        if user_type == "vocational":
            user = db.query(ZzXs).filter_by(sfzh=sfzh).first()
        else:
            user = db.query(Student).filter_by(xs_sfzh=sfzh).first()

        if not user:
            return {'success': False, 'msg': '用户不存在', 'data': None}
        if not uploaded_by_teacher and user.headphoto == 1:
            return {'success': False, 'msg': '您已上传过照片，不能重复上传', 'data': None}

        # ---- 创建任务(后台异步跑整条流水线) ----
        from services.photo_task_service import create_photo_task
        task_id = await create_photo_task(
            file_content=file_content,
            sfzh=sfzh,
            user_type=user_type,
            size_name=size_name,
            bg_color_name=bg_color_name,
            uploaded_by_teacher=uploaded_by_teacher,
            beauty=_parse_beauty_form(
                whitening_strength,
                brightness_strength,
                contrast_strength,
                sharpen_strength,
                saturation_strength,
            ),
        )

        return {
            'success': True,
            'msg': '任务已创建，请轮询获取结果',
            'data': {'task_id': task_id},
        }
    except Exception as e:
        logging.error(f"创建照片处理任务失败: {str(e)}")
        return {'success': False, 'msg': f'创建任务失败: {str(e)}', 'data': None}


@router.get('/task_status/{task_id}')
async def get_photo_task_status(
    task_id: str,
    current_user: dict = Depends(verify_token_and_get_payload),
):
    """
    查询照片处理任务状态

    返回字段:
        status:   pending / processing / uploading / syncing / completed / failed
        progress: 0-100
        step:     当前步骤中文描述
        result:   完成时返回 { photo_url, sfzh }
        error:    失败时的错误文案
    """
    try:
        from services.photo_task_service import get_task_status
        task_data = await get_task_status(task_id)

        if not task_data:
            return {'success': False, 'msg': '任务不存在或已过期', 'data': None}

        # 进度保护:失败/完成时强制 progress=100
        status = task_data.get("status")
        progress = task_data.get("progress", 0)
        if status == "completed" or status == "failed":
            progress = 100

        return {
            'success': True,
            'msg': '查询成功',
            'data': {
                'status': status,
                'progress': progress,
                'step': task_data.get("step", ""),
                'result': task_data.get("result") if status == "completed" else None,
                'error': task_data.get("error"),
                'created_at': task_data.get("created_at"),
                'completed_at': task_data.get("completed_at"),
            }
        }
    except Exception as e:
        logging.error(f"查询任务状态失败: {str(e)}")
        return {'success': False, 'msg': f'查询失败: {str(e)}', 'data': None}


@router.get('/queue_info')
async def get_photo_queue_info():
    """
    获取照片处理队列信息
    """
    try:
        from services.photo_task_service import get_queue_info
        info = get_queue_info()

        return {
            'success': True,
            'msg': '查询成功',
            'data': info
        }

    except Exception as e:
        logging.error(f"获取队列信息失败: {str(e)}")
        return {
            'success': False,
            'msg': f'查询失败: {str(e)}',
            'data': None
        }


# ============================================================
# 教师头像上传（zhxt 桶专用）
# ------------------------------------------------------------
# 教师上传个人头像专用接口：
#   - 上传到 zhxt 桶下 teacher_head_photo/<username>.jpg
#   - 文件名采用教师用户名（oa_t.t_yhm），按用户名唯一定位
#   - 同名覆盖：支持教师后续修改头像，无需新建接口
#   - 无需更新 DB 表字段（教师头像不维护在 oa_t 上，单纯按 key 存储）
# ============================================================
class UploadTeacherHeadphotoRequest(BaseModel):
    photo_base64: str
    ext: str = "jpg"  # 文件扩展名，默认 jpg
    # 抠图换底参数（与学生证件照流程一致）
    # 默认：蓝底二寸。
    # size_name: one_inch / two_inch / small_one_inch / small_two_inch / large_one_inch / large_two_inch
    # bg_color_name: blue / white / red / light_blue
    # enable_cutout=True 时调用 HivisionIDPhotos 智能抠图；False 时原图上传（向后兼容）
    size_name: str = "two_inch"
    bg_color_name: str = "blue"
    enable_cutout: bool = True  # 是否启用抠图；False 时原图上传
    # 美颜参数：默认全 0 = 不美颜（保持历史行为）
    # whitening_strength: 美白 0-30 / brightness: 亮度 -20~20 / contrast: 对比度 -100~100
    # sharpen: 锐化 0-5 / saturation: 饱和度 -100~100
    whitening_strength: int = 0
    brightness_strength: int = 0
    contrast_strength: int = 0
    sharpen_strength: int = 0
    saturation_strength: int = 0


@router.post('/upload_teacher_headphoto')
async def upload_teacher_headphoto(
    request: UploadTeacherHeadphotoRequest,
    current_user: dict = Depends(verify_token_and_get_payload),
):
    """
    教师上传个人头像到 zhxt 桶(集成智能抠图,与学生流程一致)

    入参:
        photo_base64:    Base64 编码的照片数据(不含前缀,如 data:image/jpeg;base64,)
        ext:             文件扩展名,默认 jpg
        bg_color_name:   blue/white/red/light_blue,默认 blue(蓝底)
        size_name:       one_inch/two_inch/...,默认 two_inch
        enable_cutout:   True=启用抠图(默认),False=原图直传(向后兼容)

    文件名: zhxt/teacher_head_photo/<t_yhm>.<ext>

    流程(参考 services/photo_task_service._process_photo_pipeline):
        1. AI 抠图换底(HivisionIDPhotos)
        2. 上传 zhxt 桶(同名覆盖)
    """
    try:
        username = current_user.get('t_yhm')
        if not username:
            return {
                'success': False,
                'msg': '当前用户未携带用户名(t_yhm)，无法上传头像',
                'data': None
            }

        # ⭐ 不再做"headphoto 字段幂等闸门" —— 头像是否存在的唯一权威源是 MinIO 文件。
        # 教师头像允许多次上传（同名覆盖）；如需"仅允许一次"由前端根据 check_teacher_headphoto 自行禁用入口。

        photo_base64 = request.photo_base64
        if not photo_base64:
            return {
                'success': False,
                'msg': '缺少照片数据',
                'data': None
            }

        # 移除可能的 data URL 前缀
        if ',' in photo_base64:
            photo_base64 = photo_base64.split(',')[1]

        try:
            file_content = base64.b64decode(photo_base64)
        except Exception as e:
            return {
                'success': False,
                'msg': f'Base64 解码失败: {str(e)}',
                'data': None
            }

        if not file_content:
            return {
                'success': False,
                'msg': '照片内容为空',
                'data': None
            }

        if len(file_content) > 5 * 1024 * 1024:
            return {
                'success': False,
                'msg': '照片大小不能超过5MB',
                'data': None
            }

        ext = (request.ext or 'jpg').lstrip('.').lower() or 'jpg'

        # ---------- 抠图处理 ----------
        # 参考学生 process_photo_async 流程
        # 1) 抠图换底;2) 上传 zhxt 桶
        cutout_applied = False
        if request.enable_cutout:
            try:
                from services.hivision_processor import process_id_photo

                loop = asyncio.get_event_loop()

                def _do_cutout():
                    return process_id_photo(
                        file_content,
                        size_name=request.size_name,
                        bg_color_name=request.bg_color_name,
                        beauty=_parse_beauty_form(
                            request.whitening_strength,
                            request.brightness_strength,
                            request.contrast_strength,
                            request.sharpen_strength,
                            request.saturation_strength,
                        ),
                    )

                processed_content = await asyncio.wait_for(
                    loop.run_in_executor(None, _do_cutout),
                    timeout=60,  # 与 photo_task_service.TASK_TIMEOUT 一致
                )
                cutout_applied = True
                logging.info(
                    f"[upload_teacher_headphoto] 抠图完成: username={username}, "
                    f"size_name={request.size_name}, bg_color_name={request.bg_color_name}"
                )
            except asyncio.TimeoutError:
                logging.warning(
                    f"[upload_teacher_headphoto] 抠图超时(60s),改为原图上传: username={username}"
                )
                processed_content = file_content
            except Exception as cutout_err:
                # 抠图失败不阻断上传(参考 photo_task_service 的容错:保留原图)
                logging.error(
                    f"[upload_teacher_headphoto] 抠图失败,改为原图上传: "
                    f"username={username}, error={str(cutout_err)}"
                )
                processed_content = file_content
        else:
            processed_content = file_content

        # ---------- 上传 zhxt 桶 ----------
        # 同名覆盖语义：教师多次上传会直接替换
        # 注意：必须用 minio_upload_teacher_headphoto（加前缀避免与本文件路由同名函数冲突）
        await asyncio.to_thread(
            minio_upload_teacher_headphoto,
            username=username,
            file_content=processed_content,
            content_type='image/jpeg',  # 抠图后统一输出 JPEG
            ext=ext,
        )

        # ---------- 头像状态由 MinIO 文件决定，不再写 oa_t.headphoto ----------
        # （oa_t.headphoto 字段保留但不再作为教师头像的判定来源）

        photo_url = get_teacher_headphoto_url(username, ext=ext)

        return {
            'success': True,
            'msg': '教师头像上传成功' + ('(已智能抠图换底)' if cutout_applied else ''),
            'data': {
                'photo_url': photo_url,
                'username': username,
                'path': f'zhxt/teacher_head_photo/{username}.{ext}',
                'cutout_applied': cutout_applied,
            }
        }
    except Exception as e:
        logging.error(f"教师头像上传失败: {str(e)}")
        return {
            'success': False,
            'msg': f'上传失败: {str(e)}',
            'data': None
        }


@router.get('/check_teacher_headphoto')
async def check_teacher_headphoto(
    current_user: dict = Depends(verify_token_and_get_payload),
):
    """
    查询当前登录教师的个人头像是否存在

    返回:
        has_photo:   是否已上传(MinIO 中存在文件) — 唯一权威来源
        can_upload:  前端是否允许"上传头像"按钮可点击
                     - False 时按钮置灰,前端应禁止调 upload_teacher_headphoto
                     - 规则: has_photo=true → False；否则 True（允许用户首次上传）
        photo_url:   头像签名 URL(已存在则返回,否则返回 None)
        username:    教师用户名

    注意：头像存在与否的判定**完全以 MinIO 文件为准**，不再读 oa_t.headphoto 字段。
    """
    try:
        username = current_user.get('t_yhm')
        if not username:
            return {
                'success': False,
                'msg': '当前用户未携带用户名(t_yhm)',
                'data': None
            }

        # ⭐ 唯一权威源：MinIO 文件是否存在
        exists = check_teacher_headphoto_exists(username)
        can_upload = not exists

        photo_url = get_teacher_headphoto_url(username) if exists else None
        return {
            'success': True,
            'msg': '查询成功',
            'data': {
                'has_photo': exists,
                'can_upload': can_upload,
                'photo_url': photo_url,
                'username': username,
                'path': f'zhxt/teacher_head_photo/{username}.jpg',
            }
        }
    except Exception as e:
        logging.error(f"查询教师头像失败: {str(e)}")
        return {
            'success': False,
            'msg': f'查询失败: {str(e)}',
            'data': None
        }


# 注：以下两条路由（/photo/get_headphoto/{sfzh} 与 /photo/zs_image/{filename}）
# 已迁移到 controllers/photo_proxy.py 统一代理：
#   - /photo/get_headphoto/{sfzh}            → photo_proxy.get_headphoto
#   - /photo/zs_image/{filename:path}        → photo_proxy.get_zs_image
# 这里不再重复定义，避免与 photo_proxy 路由冲突。
