from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from models.models import LwConfig
from init.dependencies import DatabaseDep
from common.auth import verify_token_and_get_payload
from datetime import datetime

router = APIRouter(prefix="/config", tags=["系统配置"])


def _serialize_config(c: LwConfig) -> dict:
    return {
        'id': c.id,
        'key': c.key,
        'value': c.value,
        'description': c.description,
        'category': c.category,
        'is_enabled': c.is_enabled,
        'sort_order': c.sort_order,
        'created_at': c.created_at.strftime('%Y-%m-%d %H:%M:%S') if c.created_at else '',
        'updated_at': c.updated_at.strftime('%Y-%m-%d %H:%M:%S') if c.updated_at else '',
    }


# ============================================================
# 公开接口：根据 key 获取配置值
# ============================================================

@router.get('/{key}')
async def get_config_by_key(key: str, db: Session = DatabaseDep):
    """根据 key 获取配置值"""
    config = db.query(LwConfig).filter(LwConfig.key == key).first()
    if not config:
        raise HTTPException(status_code=404, detail=f'配置项 "{key}" 不存在')
    if config.is_enabled == 0:
        raise HTTPException(status_code=403, detail=f'配置项 "{key}" 已禁用')
    return {
        'success': True,
        'msg': '获取成功',
        'data': {
            'key': config.key,
            'value': config.value,
            'description': config.description,
        }
    }


@router.get('/all')
async def get_all_configs(db: Session = DatabaseDep):
    """获取所有配置项（供管理后台使用）"""
    configs = db.query(LwConfig).order_by(LwConfig.sort_order, LwConfig.id).all()
    return {
        'success': True,
        'msg': '获取成功',
        'data': [_serialize_config(c) for c in configs]
    }


@router.get('/category/{category}')
async def get_configs_by_category(category: str, db: Session = DatabaseDep):
    """根据分类获取配置项"""
    configs = db.query(LwConfig).filter(
        LwConfig.category == category,
        LwConfig.is_enabled == 1
    ).order_by(LwConfig.sort_order).all()
    return {
        'success': True,
        'msg': '获取成功',
        'data': [{'key': c.key, 'value': c.value, 'description': c.description} for c in configs]
    }


# ============================================================
# 管理接口：配置的增删改（需管理员权限）
# ============================================================

class ConfigUpdateRequest(BaseModel):
    key: str
    value: str = ''
    description: str = ''
    category: str = 'general'
    is_enabled: int = 1
    sort_order: int = 0


@router.post('/update')
async def update_config(
    req: ConfigUpdateRequest,
    user_info: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """更新或创建配置项（需管理员登录）"""
    config = db.query(LwConfig).filter(LwConfig.key == req.key).first()

    if config:
        # 更新已有配置
        config.value = req.value
        if req.description is not None:
            config.description = req.description
        if req.category is not None:
            config.category = req.category
        if req.is_enabled is not None:
            config.is_enabled = req.is_enabled
        if req.sort_order is not None:
            config.sort_order = req.sort_order
        config.updated_at = datetime.now()
        db.commit()
        return {
            'success': True,
            'msg': f'配置项 "{req.key}" 更新成功',
            'data': _serialize_config(config)
        }
    else:
        # 创建新配置
        new_config = LwConfig(
            key=req.key,
            value=req.value,
            description=req.description,
            category=req.category,
            is_enabled=req.is_enabled,
            sort_order=req.sort_order,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        db.add(new_config)
        db.commit()
        db.refresh(new_config)
        return {
            'success': True,
            'msg': f'配置项 "{req.key}" 创建成功',
            'data': _serialize_config(new_config)
        }


@router.delete('/{key}')
async def delete_config(
    key: str,
    user_info: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """删除配置项（需管理员登录）"""
    config = db.query(LwConfig).filter(LwConfig.key == key).first()
    if not config:
        raise HTTPException(status_code=404, detail=f'配置项 "{key}" 不存在')

    db.delete(config)
    db.commit()
    return {
        'success': True,
        'msg': f'配置项 "{key}" 删除成功'
    }
