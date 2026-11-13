"""
就业推荐控制器（zhpt-new 重构版）

图片存储：
  私有桶 private/jytj/<timestamp>.<ext>

访问方式：
  /job/image/{filename:path}?t=<ts>&s=<sign>  → photo_proxy 直读私有桶（HMAC 签名 + 管理员 Token）

重构要点：
  - 删除原 controller 内的 /job/image/{filename} 路由（已迁移到 photo_proxy）
  - 签名函数委托 services/minio_service.sign_object_url / verify_object_sign
  - URL 替换函数委托 services.minio_service.resolve_url（自动路由公开/私有）
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from init.database_optimized import get_db
from models.models import JobRecommendation
import logging
import re

from services.minio_service import sign_object_url, resolve_url

logger = logging.getLogger(__name__)
router = APIRouter()


def get_signed_job_image_url(object_name: str) -> str:
    """生成就业推荐配图的签名代理 URL（私有桶 private/jytj/...）。

    委托 services/minio_service.sign_object_url。
    返回相对路径（以 / 开头），前端拼 BASE_URL 得到完整 URL。
    """
    return sign_object_url(object_name)


def replace_content_images(content: str) -> str:
    """替换文章内容中的图片 URL 为代理 URL

    图片 src 格式：/private/jytj/<file>.<ext> 或 /headphoto/jytj/<file>.<ext>（历史）
    需要替换为：/job/image/<file>?t=&s=（前端拼 BASE_URL）
    """
    if not content:
        return content

    def replace_private(match):
        # match.group(1) 是 private/jytj/ 之后的路径
        path = match.group(1)
        return f'src="{get_signed_job_image_url(path)}"'

    # 匹配 src="/private/jytj/xxx" 或 src='/private/jytj/xxx'
    content = re.sub(
        r'src=["\']/private/jytj/([^"\']+)["\']',
        replace_private,
        content,
    )

    # 匹配 src="/headphoto/jytj/xxx"（历史路径，转写为 private/jytj/）
    def replace_legacy(match):
        path = match.group(1)
        return f'src="{get_signed_job_image_url(path)}"'

    content = re.sub(
        r'src=["\']/headphoto/jytj/([^"\']+)["\']',
        replace_legacy,
        content,
    )

    # 也匹配完整 URL 形式（http(s)://...）
    content = re.sub(
        r'src=["\']https?://[^"\']*?/(?:private|headphoto)/jytj/([^"\']+)["\']',
        replace_legacy,
        content,
    )

    return content


@router.get('/job/list')
def get_job_list(
    page: int = 1,
    page_size: int = 10,
    keyword: str = '',
    db: Session = Depends(get_db)
):
    """获取就业推荐文章列表（分页+搜索）"""
    try:
        query = db.query(JobRecommendation).filter(
            JobRecommendation.is_published == 1
        )

        if keyword and keyword.strip():
            kw = f'%{keyword.strip()}%'
            query = query.filter(
                (JobRecommendation.title.like(kw)) |
                (JobRecommendation.summary.like(kw))
            )

        total = query.count()
        items = query.order_by(
            JobRecommendation.sort_order.desc(),
            JobRecommendation.create_time.desc(),
            JobRecommendation.view_count.desc()
        ).offset((page - 1) * page_size).limit(page_size).all()

        return {
            'success': True,
            'msg': '获取成功',
            'data': {
                'total': total,
                'page': page,
                'page_size': page_size,
                'list': [{
                    'id': item.id,
                    'title': item.title,
                    'cover_image': replace_content_images(item.cover_image) if item.cover_image else '',
                    'summary': item.summary,
                    'view_count': item.view_count or 0,
                    'author': item.author,
                    'create_time': item.create_time.strftime('%Y-%m-%d') if item.create_time else ''
                } for item in items]
            }
        }
    except Exception as e:
        logger.error(f'获取就业推荐列表失败: {str(e)}')
        raise HTTPException(status_code=500, detail=f'获取列表失败: {str(e)}')


@router.get('/job/detail/{article_id}')
def get_job_detail(article_id: int, db: Session = Depends(get_db)):
    """获取文章详情并增加浏览量"""
    try:
        article = db.query(JobRecommendation).filter(
            JobRecommendation.id == article_id,
            JobRecommendation.is_published == 1
        ).first()

        if not article:
            raise HTTPException(status_code=404, detail='文章不存在')

        article.view_count = (article.view_count or 0) + 1
        db.commit()

        return {
            'success': True,
            'msg': '获取成功',
            'data': {
                'id': article.id,
                'title': article.title,
                'cover_image': replace_content_images(article.cover_image) if article.cover_image else '',
                'content': replace_content_images(article.content),
                'summary': article.summary,
                'view_count': article.view_count,
                'author': article.author,
                'create_time': article.create_time.strftime('%Y-%m-%d %H:%M') if article.create_time else ''
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f'获取文章详情失败: {str(e)}')
        raise HTTPException(status_code=500, detail=f'获取详情失败: {str(e)}')


# 注：/job/image/{filename:path} 路由已迁移到 controllers/photo_proxy.py
#   - HMAC 签名（t + s 参数，由 services.minio_service.sign_object_url 生成）
#   - 管理员 Token 也可直接访问（Depends(_try_admin)）
# 这里不再重复定义。