"""
招生简章图片管理 API（zhpt-new 重构版）

存储路径：
  公开桶 public/zs/brochure/<school_type>/<sort>.<ext>

访问方式：
  /brochure/image/<path:path>  → photo_proxy 直读公开桶（无签名）
  生产环境由 nginx /public/* 直发，并加 secure_link 防盗链；FastAPI 仅兜底

重构要点：
  - 弃用私有桶 + HMAC 签名代理（招生简章是公开资源）
  - 上传走 services/minio_service.put_brochure_image（公开桶）
  - URL 解析走 services.minio_service.resolve_url
  - 排序算法沿用 headphoto 的"客户端下载再上传"方案，避免 server-side copy_object 已知数据损坏
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import List
from pydantic import BaseModel
from io import BytesIO

from services.minio_service import (
    BUCKET_PRIVATE,
    BUCKET_PUBLIC,
    put_brochure_image,
    resolve_url,
)
from utils.minio_client import gateway
import logging
import time

router = APIRouter(prefix="/brochure", tags=["招生简章"])
logger = logging.getLogger(__name__)


# 招生简章放在公开桶 public/zs/brochure/ 下，与 minio_service._ROUTES 对齐
# 3 个 school_type 各占一个子目录，互不干扰
BROCHURE_DIRS = {
    'vocational': 'zs/brochure/vocational',
    'open':       'zs/brochure/open',
    'adult':      'zs/brochure/adult',
}


@router.get('/list/{school_type}')
async def get_brochure_list(school_type: str):
    """获取招生简章图片列表。

    数据源：私有桶 ``guizhou-zhpt-prod-private`` 下的 ``zs/brochure/<school_type>/``
    目录（与 ``put_brochure_image`` 写入路径一致）。访问通过 ``resolve_url`` 生成
    Sig V4 预签名 URL，浏览器经 ``/object/<bucket>/<key>?X-Amz-...`` → nginx →
    MinIO 验签读取。
    """
    if school_type not in BROCHURE_DIRS:
        raise HTTPException(status_code=400, detail='无效的学校类型')

    try:
        client = gateway.client
        prefix = BROCHURE_DIRS[school_type] + '/'

        # 列私有桶：路径格式 <BUCKET_PRIVATE>/zs/brochure/<school_type>/<n>.<ext>
        objects = list(client.list_objects(
            BUCKET_PRIVATE,
            prefix=prefix,
            use_api_v1=False,
            include_version=False,
        ))

        images = []
        for obj in objects:
            name = obj.object_name.replace(prefix, '')
            if name.startswith('temp_'):
                continue
            if name and name.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                try:
                    sort_key = int(name.split('.')[0])
                except Exception:
                    sort_key = 999
                images.append({
                    'name': name,
                    'path': obj.object_name,
                    'url': resolve_url(obj.object_name),
                    'sort': sort_key,
                })

        images.sort(key=lambda x: x['sort'])
        return {
            'success': True,
            'msg': '获取成功',
            'data': images,
        }
    except Exception as e:
        logger.error(f"获取招生简章列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f'获取失败: {str(e)}')


@router.post('/upload/{school_type}')
async def upload_brochure(school_type: str, file: UploadFile = File(...), sort: int = Form(...)):
    """上传招生简章图片到公开桶 public/zs/brochure/<school_type>/<sort>.<ext>

    文件名固定为 <sort>.<ext>，确保只有纯数字文件名。
    """
    if school_type not in BROCHURE_DIRS:
        raise HTTPException(status_code=400, detail='无效的学校类型')
    if sort < 1:
        raise HTTPException(status_code=400, detail='序号必须大于0')

    try:
        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'jpg'
        if ext not in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
            ext = 'jpg'
        content = await file.read()

        object_name = put_brochure_image(content, school_type, sort, ext, content_type=f"image/{ext}")

        return {
            'success': True,
            'msg': '上传成功',
            'data': {
                'name': f"{sort}.{ext}",
                'path': object_name,
                'url': resolve_url(object_name),
                'sort': sort,
            },
        }
    except Exception as e:
        logger.error(f"上传招生简章失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f'上传失败: {str(e)}')


@router.delete('/delete/{school_type}/{filename}')
async def delete_brochure(school_type: str, filename: str):
    """删除招生简章图片（公开桶）。"""
    if school_type not in BROCHURE_DIRS:
        raise HTTPException(status_code=400, detail='无效的学校类型')

    # 防御性：filename 只能含 [A-Za-z0-9._-]，防止注入穿越
    if not filename or '/' in filename or '..' in filename:
        raise HTTPException(status_code=400, detail='文件名不合法')

    try:
        object_name = f"{BROCHURE_DIRS[school_type]}/{filename}"
        ok = gateway.delete_object(BUCKET_PUBLIC, object_name)
        if not ok:
            raise HTTPException(status_code=500, detail='删除失败')
        return {
            'success': True,
            'msg': '删除成功',
            'data': None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除招生简章失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f'删除失败: {str(e)}')


class ReorderItem(BaseModel):
    old_name: str
    new_sort: int


@router.post('/reorder/{school_type}')
async def reorder_brochure(school_type: str, order: List[ReorderItem]):
    """重新排序招生简章图片。

    算法（参考 headphoto/brochure_controller，客户端下载再上传方案，
    避免 MinIO server-side copy_object 已知数据损坏）：
      1. 把每个 old_name 用 get_object 把数据读到内存 bytes，
         再用 put_object 上传到 temp_<ts>_<idx>_<old_name>。
      2. 删除所有 old_name 源文件（不删 temp）。
      3. 按 order 顺序，把每个 temp 用 get_object 读 bytes，put_object 写到
         new_sort.<ext>，再删除 temp。

    防御性：
      - 检测 old_name / new_sort 自碰撞并直接 400
      - 任一步骤抛错时清理已创建的临时文件
      - 多文件 reorder（>2 个图轮转）也安全
    """
    if school_type not in BROCHURE_DIRS:
        raise HTTPException(status_code=400, detail='无效的学校类型')
    if not order:
        raise HTTPException(status_code=400, detail='重排序列为空')

    client = gateway.client
    prefix = BROCHURE_DIRS[school_type]

    seen_old, seen_new = set(), set()
    for item in order:
        if not item.old_name or not isinstance(item.new_sort, int) or item.new_sort < 1:
            raise HTTPException(status_code=400, detail=f'非法排序项: {item}')
        if item.old_name in seen_old:
            raise HTTPException(status_code=400, detail=f'old_name 重复: {item.old_name}')
        if item.new_sort in seen_new:
            raise HTTPException(status_code=400, detail=f'new_sort 重复: {item.new_sort}')
        seen_old.add(item.old_name)
        seen_new.add(item.new_sort)

    timestamp = int(time.time() * 1000)
    # (temp_path, new_path, ext, data_bytes, content_type)
    created_temps: list[tuple[str, str, str, bytes, str]] = []

    def _safe_copy(dst_path: str, src_path: str) -> tuple[bytes, str]:
        resp = client.get_object(BUCKET_PUBLIC, src_path)
        try:
            data = resp.read()
            content_type = resp.getheader('Content-Type') or 'application/octet-stream'
        finally:
            resp.close()
            resp.release_conn()
        if not data:
            raise RuntimeError(f"源对象数据为空: {src_path}")
        client.put_object(
            BUCKET_PUBLIC, dst_path, BytesIO(data),
            length=len(data), content_type=content_type,
        )
        return data, content_type

    try:
        # Step 1: 全量备份到 temp
        for idx, item in enumerate(order):
            old_name = item.old_name
            ext = old_name.split('.')[-1] if '.' in old_name else 'jpg'
            old_path = f"{prefix}/{old_name}"
            temp_path = f"{prefix}/temp_{timestamp}_{idx}_{old_name}"
            new_path = f"{prefix}/{item.new_sort}.{ext}"
            data, content_type = _safe_copy(temp_path, old_path)
            created_temps.append((temp_path, new_path, ext, data, content_type))

        # Step 2: 删除所有源文件
        for item in order:
            old_path = f"{prefix}/{item.old_name}"
            try:
                client.remove_object(BUCKET_PUBLIC, old_path)
            except Exception as e:
                logger.warning(f"删除原文件失败: {old_path}, {str(e)}")

        # Step 3: 把 temp 里的 bytes 写到 new_path
        for (_temp_path, _new_path, _ext, _data, _ct) in created_temps:
            client.put_object(
                BUCKET_PUBLIC, _new_path, BytesIO(_data),
                length=len(_data), content_type=_ct,
            )
            client.remove_object(BUCKET_PUBLIC, _temp_path)

        created_temps.clear()
        return {
            'success': True,
            'msg': '排序成功',
            'data': None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"排序招生简章失败: {str(e)}")
        for (_temp_path, _new_path, _ext, _data, _ct) in created_temps:
            try:
                client.remove_object(BUCKET_PUBLIC, _temp_path)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f'排序失败: {str(e)}')