"""校园反馈模块的启动时初始化

职责：
1. 字典种子：FeedbackDict 表为空时灌入默认 scene / item 选项
2. 管理员保底：FeedbackAdmin 表无 active super 时，从硬编码白名单
   feedback_admin_whitelist.py 匹配 4+1 用户表，写入为 super 角色

设计原则：
- 幂等：每次启动都会跑，但只在数据缺失时插入，已存在的不动
- 不抛异常：种子失败只 warn，不影响应用启动（业务接口会有自己的兜底）
"""
import logging
from typing import Optional, Tuple
from sqlalchemy.orm import Session

from models.models import (
    FeedbackDict, FeedbackAdmin,
    Staff, Teacher, Student, ZzXs,
)

logger = logging.getLogger(__name__)


# ============================================================
# 字典种子
# ============================================================

# (code, label, sort_order, is_custom, feedback_type)
# 2026-09-27：scene 类目字典已废弃（不再使用），仅保留 item 类目
_ITEM_SEEDS = [
    # 维修类
    ('water_power',  '水电',           10,  False, 'repair'),
    ('desk',         '桌椅板凳',       20,  False, 'repair'),
    ('banbantong',   '班班通',         30,  False, 'repair'),
    ('training_eq',  '实训设备',       40,  False, 'repair'),
    ('facility',     '校园设施',       50,  False, 'repair'),
    # 意见建议类
    ('meal',         '饭菜质量',       100, False, 'suggestion'),
    ('price',        '价格',           110, False, 'suggestion'),
    ('guoqi',        '过期、三无产品', 120, False, 'suggestion'),
    ('service',      '服务态度',       130, False, 'suggestion'),
    ('safety',       '安全卫生',       140, False, 'suggestion'),
    # 兜底
    ('custom',       '其他',           999, True,  'both'),
]


def seed_feedback_dict(db: Session) -> None:
    """字典种子（仅在表为空时插入）"""
    try:
        if db.query(FeedbackDict).first() is not None:
            return  # 已有数据，跳过

        rows = []
        for code, label, sort_order, is_custom, ftype in _ITEM_SEEDS:
            rows.append(FeedbackDict(
                category='item', code=code, label=label,
                sort_order=sort_order, is_custom=is_custom,
                feedback_type=ftype, is_active=True,
            ))
        db.add_all(rows)
        db.commit()
        logger.info(f"✅ FeedbackDict seeded: {len(rows)} rows")
    except Exception as e:
        db.rollback()
        logger.warning(f"⚠️ FeedbackDict seed failed: {e}")


# ============================================================
# 管理员保底种子
# ============================================================

def _match_phone_to_user(db: Session, phone: str) -> Optional[Tuple[str, str, str]]:
    """按优先级在 5 张用户表里匹配手机号

    返回 (user_type, user_ref_id, name)；未匹配返回 None
    """
    if not phone:
        return None
    phone = str(phone).strip()

    # 1) 工作人员（优先级最高，因为是后勤工种）
    s = db.query(Staff).filter(Staff.phone == phone, Staff.status == 'active').first()
    if s:
        return ('staff', str(s.id), s.name or '')

    # 2) 教师（不区分开放/中职，同表）—— 这里登记为 open_teacher，因为
    #    feedback.resolve_user 中 open_teacher / vocational_teacher 都查同一张 Teacher 表
    t = db.query(Teacher).filter(Teacher.t_dh == phone).first()
    if t:
        return ('open_teacher', str(t.t_id), t.t_xm or '')

    # 3) 开放学生
    os_ = db.query(Student).filter(Student.xs_dh == phone).first()
    if os_:
        return ('open_student', str(os_.xs_id), os_.xs_xm or '')

    # 4) 中职学生
    vs = db.query(ZzXs).filter(ZzXs.xsdh == phone).first()
    if vs:
        return ('vocational_student', str(vs.id), vs.xm or '')

    return None


def ensure_super_admin_seeds(db: Session) -> None:
    """保底机制：若 FeedbackAdmin 表无 active super，从硬编码白名单回灌

    这是"应急逃生通道"，避免 super 被误删后无人能登入后台。
    日常运营**不应**依赖这个函数——所有增删走另一项目的管理端。
    """
    try:
        has_super = db.query(FeedbackAdmin).filter(
            FeedbackAdmin.role == 'super',
            FeedbackAdmin.is_active == True,  # noqa: E712
        ).first()
        if has_super:
            return

        try:
            from utils.feedback_admin_whitelist import FEEDBACK_ADMIN_WHITELIST
        except ImportError:
            logger.warning("⚠️ feedback_admin_whitelist 不存在，跳过 super 保底种子")
            return

        added = 0
        for item in FEEDBACK_ADMIN_WHITELIST:
            phone = (item.get('phone') or '').strip()
            if not phone:
                continue

            matched = _match_phone_to_user(db, phone)
            if not matched:
                logger.warning(f"⚠️ 白名单手机号 {phone} 在 5 张用户表中未匹配，跳过")
                continue
            user_type, user_ref_id, name = matched

            # 已存在则跳过（哪怕 role 不是 super，也别覆盖另一项目的配置）
            exists = db.query(FeedbackAdmin).filter(
                FeedbackAdmin.user_type == user_type,
                FeedbackAdmin.user_ref_id == user_ref_id,
            ).first()
            if exists:
                if not exists.is_active:
                    exists.is_active = True
                    exists.role = 'super'  # 重新激活并升级为 super
                    added += 1
                continue

            db.add(FeedbackAdmin(
                user_type=user_type,
                user_ref_id=user_ref_id,
                phone_snapshot=phone,
                name_snapshot=name or item.get('name', ''),
                role='super',
                department=item.get('role', ''),  # 原白名单 role 字段是部门描述
                is_active=True,
                note='auto-seeded from feedback_admin_whitelist.py',
            ))
            added += 1

        if added:
            db.commit()
            logger.info(f"✅ FeedbackAdmin super seeds: {added} rows")
    except Exception as e:
        db.rollback()
        logger.warning(f"⚠️ FeedbackAdmin super seed failed: {e}")


def run_all_seeds(db: Session) -> None:
    """启动时调用入口"""
    seed_feedback_dict(db)
    ensure_super_admin_seeds(db)
