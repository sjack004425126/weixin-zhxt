"""电表充值 - 学生端接口（不需要鉴权）

提供四个能力：
    1. GET /dianbiao/by-house-name?house_name=xxx
       按 house_name 前缀模糊匹配，返回第一条电表基本信息（不含 raw 大字段）。
       找不到时 success=true/data=null，前端自行提示"未匹配"。

    2. GET /dianbiao/qrcode-url/<sn>
       根据 sn 调用 MinIO Sig V4 预签名，返回 /object/<bucket>/dianbiao/<sn>.png 的访问 URL。
       失败返回 404（前端展示"二维码不存在"）。

    3. GET /dianbiao/pick-default
       取一条真实存在的电表记录（按 id 升序第一条），返回 device_id / sn / house_name，
       供测试页 / 跳转外链页填充默认参数。

    4. GET /dianbiao/pick-default?house_name=xxx
       同上，但优先取 house_name 前缀匹配到的记录（用于「先搜电表再跳转」的业务流）。

设计要点
--------
- 不需要登录态：纯查询接口（house_name 本身是个弱标识，但走的是内网中专小程序入口可接受）
- 不暴露 raw 大字段
- 复用 services/minio_service 的 sign_object_url()（与 photo_proxy / brochure 同款 Sig V4）
- 模糊匹配后端做 lower-trim，匹配逻辑为前缀 LIKE 'xxx%'
"""
import re
import logging
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from init.dependencies import DatabaseDep
from models.models import ZzDianbiaoMeter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dianbiao", tags=["电表充值"])


# ============================================================
# 输出模型
# ============================================================
class DianbiaoMeterOut(BaseModel):
    """电表输出对象（按需精简：sn / 校区 / 学员姓名 / 电价 / 基础电价 / 失效时间）"""
    id: int
    sn: str
    house_id: int
    estate_name: Optional[str] = None
    building: Optional[str] = None
    house_name: Optional[str] = None
    full_name: Optional[str] = None
    tenant_name: Optional[str] = None
    price: Optional[str] = None
    basic_price: Optional[str] = None
    expired_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


def _to_out(m: ZzDianbiaoMeter) -> dict:
    return {
        "id": m.id,
        "sn": m.sn,
        "house_id": m.house_id,
        "estate_name": m.estate_name,
        "building": m.building,
        "house_name": m.house_name,
        "full_name": m.full_name,
        "tenant_name": m.tenant_name,
        "price": m.price,
        "basic_price": m.basic_price,
        "expired_at": m.expired_at.strftime("%Y-%m-%d %H:%M:%S") if m.expired_at else None,
        "updated_at": m.updated_at.strftime("%Y-%m-%d %H:%M:%S") if m.updated_at else None,
    }


# ============================================================
# 1) 按 house_name 完全匹配
# ============================================================
@router.get("/by-house-name")
async def get_meter_by_house_name(
    house_name: str = Query(..., min_length=1, max_length=64, description="电表 house_name（模糊匹配，输入 'A10' 会同时匹配 A103, A104...）"),
    db: Session = DatabaseDep,
):
    """按 house_name 模糊匹配查询电表信息。

    - 模糊匹配：去除两端空格后用 LIKE 'xxx%' 前缀匹配（电表名有规律：A103 / A104...）
    - 找不到返回 success=true / data=[]
    """
    name = (house_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="house_name 不能为空")

    row = (
        db.query(ZzDianbiaoMeter)
        .filter(ZzDianbiaoMeter.house_name.like(f"{name}%"))
        .order_by(ZzDianbiaoMeter.id.asc())
        .first()
    )
    return {
        "success": True,
        "msg": "ok",
        "data": _to_out(row) if row else None,
    }


# ============================================================
# 3) 取一条真实电表记录（给测试页 / 跳转页填默认参数）
# ============================================================
@router.get("/pick-default")
async def pick_default_meter(
    house_name: Optional[str] = Query(None, max_length=64, description="可选：优先取该名称前缀匹配到的电表；不传则取 id 最小的一条"),
    db: Session = DatabaseDep,
):
    """取一条 zz_dianbiao_meters 记录，供测试页填充 device_id / sn。

    - 传 house_name：按前缀 LIKE 'xxx%' 取第一条
    - 不传：按 id 升序取第一条（保证结果稳定、便于复现）

    返回字段：id / device_id / sn / house_name / estate_name / building
    """
    name = (house_name or "").strip()

    q = db.query(ZzDianbiaoMeter)
    if name:
        q = q.filter(ZzDianbiaoMeter.house_name.like(f"{name}%"))
    # 不传 house_name 时随机取，方便每次刷新看到不同电表
    if name:
        row = q.order_by(ZzDianbiaoMeter.id.asc()).first()
    else:
        import random as _rand
        all_ids = [r.id for r in q.all()]
        if not all_ids:
            row = None
        else:
            row = db.query(ZzDianbiaoMeter).filter(
                ZzDianbiaoMeter.id == _rand.choice(all_ids)
            ).first()

    if not row:
        return {
            "success": True,
            "msg": "ok",
            "data": None,
        }

    return {
        "success": True,
        "msg": "ok",
        "data": {
            "id": row.id,
            "device_id": row.device_id,
            "sn": row.sn,
            "house_id": row.house_id,
            "estate_name": row.estate_name,
            "building": row.building,
            "house_name": row.house_name,
            "full_name": row.full_name,
        },
    }


# ============================================================
# 2) 获取电表二维码的 MinIO 预签名 URL（/object/...）
# ============================================================
_SN_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


@router.get("/qrcode-url/{sn}")
async def get_meter_qrcode_url(
    sn: str,
    expires: int = Query(600, ge=60, le=3600, description="签名 URL 有效期（秒），默认 600，最大 3600"),
):
    """根据 sn 生成 MinIO Sig V4 预签名 URL（参考 photo_proxy.minio 签名方式）。

    - sn：电表 SN，必须在 [A-Za-z0-9_-]{1,64} 范围内（与 chongzhi qrcode.py 同款校验）
    - 返回：`/object/<bucket>/dianbiao/<sn>.png?X-Amz-...`（前端拿到的相对路径，
       前端走 BASE_URL 拼成完整 URL）

    错误码：
        400 - sn 不合法
        404 - 文件不存在 / MinIO 不可用
    """
    raw = (sn or "").strip()
    if not _SN_RE.match(raw):
        raise HTTPException(status_code=400, detail="非法的 sn")

    # MinIO 内路径：dianbiao/<sn>.png
    object_key = f"dianbiao/{raw}.png"

    # 复用 zhpt-new 已有的 minio_service Sig V4 工具
    # 失败情况：
    #   1) gateway 不可用（降级模式）→ 返回 503
    #   2) 对象不存在（S3Error NoSuchKey）→ 返回 404
    try:
        from services.minio_service import BUCKET_PRIVATE, sign_object_url, gateway
        if not gateway.available:
            logger.warning("MinIO 不可用：%s", raw)
            raise HTTPException(status_code=503, detail="MinIO 服务暂不可用")
        try:
            gateway.stat(BUCKET_PRIVATE, object_key)
        except Exception:
            logger.info("电表二维码不存在: %s/%s", BUCKET_PRIVATE, object_key)
            raise HTTPException(status_code=404, detail=f"二维码不存在: {raw}")
        signed = sign_object_url(object_key, bucket=BUCKET_PRIVATE)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("生成电表二维码 URL 失败: %s - %s", raw, e)
        raise HTTPException(status_code=500, detail="生成二维码 URL 失败")

    return {
        "success": True,
        "msg": "ok",
        "data": {
            "sn": raw,
            "url": signed,
            "expires_in": int(expires),
        },
    }
