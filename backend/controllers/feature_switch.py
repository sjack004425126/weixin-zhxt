from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from models.models import LwFeatureSwitch
from init.dependencies import DatabaseDep
from common.auth import verify_token_and_get_payload
from datetime import datetime

router = APIRouter(prefix="/feature_switch", tags=["功能开关"])


def _serialize_switch(s: LwFeatureSwitch) -> dict:
    return {
        'code': s.code,
        'name': s.name,
        'is_enabled': s.is_enabled,
        'sort_order': s.sort_order,
        'remark': s.remark,
        'tip_message': s.tip_message,
    }


# ============================================================
# 公开接口：查询所有开关状态（供小程序首页调用）
# ============================================================

@router.get('/all')
async def get_all_switches(db: Session = DatabaseDep):
    """获取所有功能开关状态"""
    switches = db.query(LwFeatureSwitch).order_by(LwFeatureSwitch.sort_order).all()
    return {
        'success': True,
        'msg': '获取成功',
        'data': [_serialize_switch(s) for s in switches]
    }


@router.get('/check/{code}')
async def check_switch(code: str, db: Session = DatabaseDep):
    """检查指定功能是否开启，返回开关状态和提示词。

    设计约定：
    - is_enabled=true 时返回空 tip_message（启用状态无需展示"暂停"文案，避免误导）
    - is_enabled=false 时返回数据库中配置的 tip_message，供前端弹窗提示
    """
    switch = db.query(LwFeatureSwitch).filter(LwFeatureSwitch.code == code).first()
    if not switch:
        return {
            'success': True,
            'msg': '功能不存在，默认开启',
            'data': {'is_enabled': True, 'tip_message': ''}
        }
    is_enabled = switch.is_enabled == 1
    return {
        'success': True,
        'msg': '获取成功',
        'data': {
            'is_enabled': is_enabled,
            # 仅在关闭时返回提示文案；启用时清空，避免返回"已暂停"误导前端
            'tip_message': '' if is_enabled else (switch.tip_message or '该功能已关闭，请联系管理员开启'),
        }
    }


# ============================================================
# 管理接口：开关的增删改查（需管理员权限）
# ============================================================

class SwitchUpdateRequest(BaseModel):
    code: str
    is_enabled: int = 1          # 1=开启 0=关闭
    name: str = ''
    remark: str = ''
    tip_message: str = ''
    sort_order: int = 0


@router.post('/update')
async def update_switch(
    req: SwitchUpdateRequest,
    user_info: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """更新功能开关及提示词（需管理员登录）"""
    switch = db.query(LwFeatureSwitch).filter(LwFeatureSwitch.code == req.code).first()
    if not switch:
        raise HTTPException(status_code=404, detail='功能不存在')

    switch.is_enabled = req.is_enabled
    if req.name:
        switch.name = req.name
    if req.remark:
        switch.remark = req.remark
    if req.tip_message is not None:
        switch.tip_message = req.tip_message
    if req.sort_order:
        switch.sort_order = req.sort_order
    switch.updated_at = datetime.now()

    db.commit()
    return {
        'success': True,
        'msg': f"「{switch.name}」{'开启' if req.is_enabled == 1 else '关闭'}成功",
        'data': _serialize_switch(switch)
    }


@router.get('/list')
async def list_switches(
    user_info: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """获取所有开关列表（管理端）"""
    switches = db.query(LwFeatureSwitch).order_by(LwFeatureSwitch.sort_order).all()
    return {
        'success': True,
        'msg': '获取成功',
        'data': [
            {
                'id': s.id,
                **_serialize_switch(s),
                'created_at': s.created_at.strftime('%Y-%m-%d %H:%M:%S') if s.created_at else '',
                'updated_at': s.updated_at.strftime('%Y-%m-%d %H:%M:%S') if s.updated_at else '',
            }
            for s in switches
        ]
    }
