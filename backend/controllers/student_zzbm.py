from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from models.models import WxPayinfo, Student, ZzBj, Teacher, ZzXs, ZzBmxsJzdlx, ZzBmxsJzgx, ZzBmxsQd, ZzBmxsXx, ZzBmxsZsdx, ZzBmxsZzmm, ZzBmxsBdzy, lw_sys, ZzSys
from init.dependencies import (
    get_redis, get_db,
    RedisDep, DatabaseDep, RedisManagerDep, get_current_user
)
from common.auth import verify_token_and_get_payload, verify_token_only
from datetime import datetime
from sqlalchemy import text, true, func
from sqlalchemy.exc import OperationalError, IntegrityError
import random
from utils.wx_pay import WxPayUtil
from utils.system_config import SystemConfig
from utils.wx_pay_transfer import WxPayTransfer
import logging
logger = logging.getLogger(__name__)
from utils.wx_utils import WxUtils
from utils.wx_qr_code import WxQrCode
from utils.admission_notice import AdmissionNotice
from utils.redis_utils import RedisLock
from utils.sms import SMSTool
import re
import uuid
import time
import json
import urllib.parse
import pypinyin


def get_pinyin_initial(name: str) -> str:
    """提取姓名的拼音首字母"""
    if not name:
        return ''
    try:
        pinyin_list = pypinyin.lazy_pinyin(name, style=pypinyin.Style.FIRST_LETTER)
        return ''.join(pinyin_list).upper()
    except Exception:
        return ''

# 请求模型（必须在路由之前定义）
class CreateZzbmRequest(BaseModel):
    xm: str
    xb: str
    mz: str
    zzmm: int
    sfzh: str
    xsdh: str
    jtxxdz: str
    jzdlx: int
    hkxz: str
    jzxm: str
    jzgx: int
    jzdh: str
    bdzy: int
    byxxssx1: str = ""
    byxxssx2: str = ""
    byxxssx3: str = ""
    byxxmc: str = ""
    zsdx: int = None
    sfjdlk: int = 0
    sflset: int = 0
    sftwjrzn: int = 0
    xsly: str = ""
    qd: int = None
    qdjs: str = ""
    sfqdxf: int = None

class PreCreateRequest(BaseModel):
    sfzh: str
    xsdh: str
    bdzy: int

    model_config = {"populate_by_name": True}

class UpdateInfoRequest(BaseModel):
    id: int
    xm: str = None
    xb: str = None
    mz: str = None
    zzmm: int = None
    sfzh: str = None
    xsdh: str = None
    jtxxdz: str = None
    jzdlx: int = None
    hkxz: str = None
    jzxm: str = None
    jzgx: int = None
    jzdh: str = None
    bdzy: int = None
    byxxssx1: str = None
    byxxssx2: str = None
    byxxssx3: str = None
    byxxmc: str = None
    zsdx: int = None
    sfjdlk: int = None
    sflset: int = None
    sftwjrzn: int = None
    xsly: str = None
    qd: int = None
    qdjs: str = None
    sfqdxf: int = None
    remark: str = None
    is_complete: int = None

    model_config = {"populate_by_name": True}

class GenerateQrcodeRequest(BaseModel):
    introducer: str
    width: int = 430

# 创建路由器
router = APIRouter(prefix="/zzbm", tags=["学生中职报名"])

# ================================================================
# 检查是否已报名（用于第一步填写身份证和电话后检查）
# ================================================================
@router.get('/check_enrolled')
async def check_enrolled(
    sfzh: str = None,
    xsdh: str = None,
    db: Session = DatabaseDep,
):
    """检查身份证号是否已报名"""
    try:
        if not sfzh:
            return {'success': False, 'msg': '缺少身份证号', 'data': None}
        
        # 检查是否已报名（查任何记录，草稿也拦截，只查新生 nd=26）
        existing = db.query(ZzXs).filter(
            ZzXs.sfzh == sfzh.upper(),
            ZzXs.nd == 26
        ).first()
        
        if existing:
            # 已报名：返回 success=true + bm=true，业务上表示"已报名模式"
            # 不返回任何记录详情，避免通过枚举身份证号泄露信息
            return {
                'success': True,
                'msg': '已报名',
                'data': {
                    'bm': True
                }
            }
        else:
            return {
                'success': True,
                'msg': '未报名',
                'data': {
                    'bm': False
                }
            }
    except Exception as e:
        logger.error(f'检查报名状态失败: {str(e)}')
        return {'success': False, 'msg': f'检查报名状态失败：{str(e)}', 'data': None}

# ================================================================
# 已报名用户身份二次验证：发送报名手机号验证码
# ================================================================
class SendEnrollmentVerifyCodeRequest(BaseModel):
    sfzh: str

@router.post('/send_enrollment_verify_code')
async def send_enrollment_verify_code(
    request: SendEnrollmentVerifyCodeRequest,
    redis_client=RedisDep,
    db: Session = DatabaseDep,
):
    """发送报名手机号验证码（已报名用户进入编辑模式前的安全验证）

    业务流程：
    1. 根据身份证号查找报名记录，取出 xsdh（报名时填写的手机号）
    2. 生成 6 位验证码，存入 Redis（5 分钟过期）
    3. 调用短信网关向 xsdh 发送验证码
    """
    try:
        sfzh = (request.sfzh or '').strip().upper()
        if not sfzh:
            return {'success': False, 'msg': '缺少身份证号', 'data': None}

        bmxs = db.query(ZzXs).filter(
            ZzXs.sfzh == sfzh,
            ZzXs.nd == 26
        ).first()
        if not bmxs or not bmxs.xsdh:
            return {'success': False, 'msg': '未找到报名记录或未登记手机号', 'data': None}

        # 频率限制：同一身份证 60 秒内只能发一次
        cooldown_key = f"zzbm:enroll_verify:cooldown:{sfzh}"
        if redis_client.get(cooldown_key):
            return {'success': False, 'msg': '验证码发送过于频繁，请稍后再试', 'data': None}

        # 生成 6 位验证码
        verify_code = ''.join(random.choices('0123456789', k=6))
        code_key = f"zzbm:enroll_verify:code:{sfzh}"
        redis_client.setex(code_key, 300, verify_code)
        # 设置冷却（60 秒）
        redis_client.setex(cooldown_key, 60, '1')

        # 发送短信
        try:
            sms_tool = SMSTool()
            result = sms_tool.send_verify_sms(bmxs.xsdh, verify_code)
            if not result or not result.get('success'):
                logger.warning(f'报名验证码发送失败 sfzh={sfzh}, err={result.get("msg") if result else "未知"}')
                return {'success': False, 'msg': '验证码发送失败，请稍后再试', 'data': None}
        except Exception as sms_err:
            logger.error(f'报名验证码短信异常: {sms_err}')
            return {'success': False, 'msg': '验证码发送失败，请稍后再试', 'data': None}

        # 不返回验证码本身，仅返回掩码后的手机号供前端展示
        masked = bmxs.xsdh[:3] + '****' + bmxs.xsdh[-4:]
        return {
            'success': True,
            'msg': '验证码已发送',
            'data': {
                'masked_phone': masked,
                'expire_seconds': 300
            }
        }
    except Exception as e:
        logger.error(f'发送报名验证码失败: {str(e)}')
        return {'success': False, 'msg': f'发送验证码失败：{str(e)}', 'data': None}


class VerifyEnrollmentCodeRequest(BaseModel):
    sfzh: str
    verify_code: str

@router.post('/verify_enrollment_code')
async def verify_enrollment_code(
    request: VerifyEnrollmentCodeRequest,
    redis_client=RedisDep,
    db: Session = DatabaseDep,
):
    """校验报名验证码

    成功时返回 success=true；前端拿到这个结果后才能继续加载详情/进入编辑模式。
    验证后立即删除 Redis 中的验证码（一次性）。
    """
    try:
        sfzh = (request.sfzh or '').strip().upper()
        code = (request.verify_code or '').strip()

        if not sfzh or not code:
            return {'success': False, 'msg': '缺少身份证号或验证码', 'data': None}

        code_key = f"zzbm:enroll_verify:code:{sfzh}"
        stored = redis_client.get(code_key)
        if not stored:
            return {'success': False, 'msg': '验证码已过期，请重新发送', 'data': None}

        # 处理 bytes
        if isinstance(stored, bytes):
            stored = stored.decode('utf-8')

        if code != stored:
            return {'success': False, 'msg': '验证码不正确', 'data': None}

        # 验证通过：删除验证码（一次性），并下发一个短期"已验证"令牌供后续接口使用
        redis_client.delete(code_key)
        verify_token = uuid.uuid4().hex
        token_key = f"zzbm:enroll_verify:passport:{sfzh}"
        # 15 分钟内调用 get_enrollment_detail_by_sfzh 视为已通过身份验证
        redis_client.setex(token_key, 900, verify_token)

        return {
            'success': True,
            'msg': '验证成功',
            'data': {
                'verify_token': verify_token,
                'expire_seconds': 900
            }
        }
    except Exception as e:
        logger.error(f'校验报名验证码失败: {str(e)}')
        return {'success': False, 'msg': f'校验失败：{str(e)}', 'data': None}


# ================================================================
# 预创建报名记录（选专业后立即落盘）
# ================================================================
@router.post('/pre_create')
async def pre_create_enrollment(
    request: PreCreateRequest,
    db: Session = DatabaseDep,
    redis=RedisDep,
):
    """预创建报名记录（仅填身份证、电话、专业）"""
    try:
        sfzh = request.sfzh
        xsdh = request.xsdh
        bdzy = request.bdzy

        # 验证身份证格式
        sfzh_upper = sfzh.upper()
        sfzh_pattern = r'^[1-9]\d{5}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]$'
        if not re.match(sfzh_pattern, sfzh_upper):
            return {'success': False, 'msg': '身份证号格式不正确', 'data': None}
        
        # 验证手机号
        phone_pattern = r'^1[3-9]\d{9}$'
        if not re.match(phone_pattern, xsdh):
            return {'success': False, 'msg': '手机号格式不正确', 'data': None}
        
        # 检查是否已报名（只查新生 nd=26）
        existing = db.query(ZzXs).filter(
            ZzXs.sfzh == sfzh_upper,
            ZzXs.nd == 26
        ).first()
        if existing:
            return {'success': False, 'msg': '该身份证号已报名，不能重复报名', 'data': None}
        
        # 调用核心报名逻辑
        data = {
            'sfzh': sfzh_upper,
            'xsdh': xsdh,
            'cooperation_schoolmajor_id': bdzy,
            # 以下字段预创建时为空，后续步骤补充
            'xm': '',
            'xb': '',
            'mz': '',
            'zzmm': 0,
            'jtxxdz': '',
            'jzdlx': 0,
            'hkxz': '',
            'jzxm': '',
            'jzgx': 0,
            'jzdh': '',
            'byxxssx1': '',
            'byxxssx2': '',
            'byxxssx3': '',
            'byxxmc': '',
            'zsdx': 0,
            'sfjdlk': 0,
            'sflset': 0,
            'sftwjrzn': 0,
            'xsly': '',
            'qd': 0,
            'qdjs': '',
            'sfqdxf': 0,
        }
        
        result = execute_student_registration(data, db, redis_client=redis)
        
        if result['success']:
            return {
                'success': True,
                'msg': '预报名成功',
                'data': {
                    'id': result['data']['id'],
                    'major_name': result['data']['major_name'],
                    'query_code': result['data'].get('query_code')
                }
            }
        else:
            return {'success': False, 'msg': result['msg'], 'data': None}
            
    except Exception as e:
        logger.error(f'预创建报名记录失败: {str(e)}')
        return {'success': False, 'msg': f'预创建报名记录失败：{str(e)}', 'data': None}

# ================================================================
# 更新报名记录（后续步骤完善信息）
# ================================================================
@router.post('/update_info')
async def update_enrollment_info(
    request: UpdateInfoRequest,
    db: Session = DatabaseDep,
    redis=RedisDep,
):
    """更新报名记录信息"""
    try:
        id = request.id
        bdzy = request.bdzy

        # 获取当前报名记录（只查新生 nd=26）
        bmxs = db.query(ZzXs).filter(ZzXs.id == id, ZzXs.nd == 26).first()
        if not bmxs:
            return {'success': False, 'msg': '报名记录不存在', 'data': None}
        
        # 如果要更换专业，需要处理名额变动
        old_cooperation_schoolmajor_id = bmxs.cooperation_schoolmajor_id
        new_cooperation_schoolmajor_id = bdzy if bdzy is not None else old_cooperation_schoolmajor_id

        if bdzy is not None and bdzy != old_cooperation_schoolmajor_id:
            # 专业变更：需要分布式锁
            lock = RedisLock(redis, key=f"zzbm:major:change:{id}", timeout=15, retry_delay=0.15)
            if not lock.acquire_sync(max_retries=10):
                return {'success': False, 'msg': '系统繁忙，请稍后重试', 'data': None}

            try:
                # 1. 释放原专业名额
                if old_cooperation_schoolmajor_id:
                    db.execute(text("""
                        UPDATE zz_bmxs_cooperation_schoolmajor
                        SET bmrs = bmrs - 1
                        WHERE id = :id AND bmrs > 0
                    """), {"id": old_cooperation_schoolmajor_id})

                # 2. 检查新专业是否有名额
                new_major = db.execute(text("""
                    SELECT id, zsme FROM zz_bmxs_cooperation_schoolmajor WITH (UPDLOCK, ROWLOCK)
                    WHERE id = :id
                """), {"id": bdzy}).first()

                if not new_major:
                    return {'success': False, 'msg': '选择的专业不存在', 'data': None}

                current_bmrs_result = db.execute(text("""
                    SELECT COUNT(*) as bmrs_count
                    FROM zz_xs
                    WHERE cooperation_schoolmajor_id = :cooperation_schoolmajor_id AND nd = 26
                """), {"cooperation_schoolmajor_id": bdzy}).first()
                current_bmrs = current_bmrs_result.bmrs_count if current_bmrs_result else 0

                if current_bmrs >= (new_major.zsme or 0):
                    return {'success': False, 'msg': '新选择的专业已满额', 'data': None}

                # 3. 占用新专业名额
                update_result = db.execute(text("""
                    UPDATE zz_bmxs_cooperation_schoolmajor
                    SET bmrs = bmrs + 1
                    WHERE id = :id AND bmrs < zsme
                """), {"id": bdzy})

                if update_result.rowcount == 0:
                    return {'success': False, 'msg': '新选择的专业名额不足', 'data': None}

                # 4. 更新报名记录的专业
                bmxs.cooperation_schoolmajor_id = bdzy
                
            finally:
                lock.release_sync()
        
        # 更新其他字段
        update_fields = {
            'xb': request.xb, 'mz': request.mz, 'zzmm': request.zzmm, 'sfzh': request.sfzh,
            'xsdh': request.xsdh, 'jtxxdz': request.jtxxdz, 'jzdlx': request.jzdlx, 'hkxz': request.hkxz,
            'jzxm': request.jzxm, 'jzgx': request.jzgx, 'jzdh': request.jzdh,
            'byxxssx1': request.byxxssx1, 'byxxssx2': request.byxxssx2, 'byxxssx3': request.byxxssx3,
            'byxxmc': request.byxxmc, 'zsdx': request.zsdx, 'sfjdlk': request.sfjdlk,
            'sflset': request.sflset, 'sftwjrzn': request.sftwjrzn,
            'xsly': request.xsly, 'qd': request.qd, 'qdjs': request.qdjs, 'sfqdxf': request.sfqdxf,
            'remark': request.remark,
        }
        
        for field, value in update_fields.items():
            if value is not None:
                setattr(bmxs, field, value)
        
        # 更新姓名和拼音首字母（姓名变化时才更新拼音）
        if request.xm is not None and request.xm != bmxs.xm:
            bmxs.xm = request.xm
            bmxs.pinyin_initial = get_pinyin_initial(request.xm)
        
        # 身份证大写
        if bmxs.sfzh:
            bmxs.sfzh = bmxs.sfzh.upper()

        # 标记为已完成（仅当未显式传 is_complete 时默认置1）
        # 允许前端通过 is_complete 字段来控制完成状态
        if request.is_complete is None:
            bmxs.is_complete = 1

        db.commit()
        
        return {
            'success': True,
            'msg': '更新成功',
            'data': {'id': bmxs.id}
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f'更新报名记录失败: {str(e)}')
        return {'success': False, 'msg': f'更新报名记录失败：{str(e)}', 'data': None}

# ================================================================
# 获取报名记录详情（用于提交后获取查询码）
# ================================================================
@router.get('/get_enrollment_detail_by_sfzh')
async def get_enrollment_detail_by_sfzh(
    sfzh: str,
    verify_token: str = None,
    db: Session = DatabaseDep,
    redis_client=RedisDep,
):
    """按身份证号获取报名记录完整信息（用于 step0 已报名加载编辑模式）

    安全要求：必须传入 verify_token（由 /verify_enrollment_code 返回），否则拒绝。
    防止他人通过猜测/偷取身份证号直接拉取他人报名详情。
    """
    try:
        sfzh = (sfzh or '').strip().upper()

        # 验证 token：必须先通过短信验证码
        if not verify_token:
            return {'success': False, 'msg': '请先完成报名手机号短信验证', 'data': None}
        token_key = f"zzbm:enroll_verify:passport:{sfzh}"
        stored_token = redis_client.get(token_key)
        if isinstance(stored_token, bytes):
            stored_token = stored_token.decode('utf-8')
        if not stored_token or stored_token != verify_token:
            return {'success': False, 'msg': '验证已过期，请重新进行短信验证', 'data': None}

        bmxs = db.query(ZzXs).filter(
            ZzXs.sfzh == sfzh,
            ZzXs.nd == 26
        ).first()
        if not bmxs:
            return {'success': False, 'msg': '未找到报名记录', 'data': None}

        from models.models import WxPayinfo
        has_paid = False
        pay_time = None
        amount = None
        if bmxs.sfzh:
            zz_sys = db.query(ZzSys).first()
            pay_record = db.query(WxPayinfo).filter(
                func.upper(WxPayinfo.o_sfzh) == func.upper(bmxs.sfzh),
                WxPayinfo.o_xq == (zz_sys.zz_xsjf_xq if zz_sys else None),
                WxPayinfo.o_sfzh.isnot(None)
            ).first()
            if pay_record:
                has_paid = True
                if pay_record.o_date:
                    pay_time = pay_record.o_date.strftime('%Y-%m-%d %H:%M')
                if pay_record.o_amt:
                    amount = pay_record.o_amt

        return {
            'success': True,
            'msg': '获取成功',
            'data': {
                'record': {
                    'id': bmxs.id,
                    'xm': bmxs.xm,
                    'xb': bmxs.xb,
                    'mz': bmxs.mz,
                    'zzmm': bmxs.zzmm,
                    'sfzh': bmxs.sfzh,
                    'xsdh': bmxs.xsdh,
                    'jtxxdz': bmxs.jtxxdz,
                    'jzdlx': bmxs.jzdlx,
                    'hkxz': bmxs.hkxz,
                    'jzxm': bmxs.jzxm,
                    'jzgx': bmxs.jzgx,
                    'jzdh': bmxs.jzdh,
                    'cooperation_schoolmajor_id': bmxs.cooperation_schoolmajor_id,
                    'byxxssx1': bmxs.byxxssx1,
                    'byxxssx2': bmxs.byxxssx2,
                    'byxxssx3': bmxs.byxxssx3,
                    'byxxmc': bmxs.byxxmc,
                    'zsdx': bmxs.zsdx,
                    'sfjdlk': bmxs.sfjdlk,
                    'sflset': bmxs.sflset,
                    'sftwjrzn': bmxs.sftwjrzn,
                    'xsly': bmxs.xsly,
                    'qd': bmxs.qd,
                    'qdjs': bmxs.qdjs,
                    'sfqdxf': bmxs.sfqdxf,
                    'remark': bmxs.remark or '',
                    'is_complete': bmxs.is_complete,
                    'query_code': bmxs.query_code,
                },
                'payment_info': {
                    'has_paid': has_paid,
                    'status_text': '已缴费' if has_paid else '未缴费',
                    'pay_time': pay_time,
                    'amount': amount
                }
            }
        }
    except Exception as e:
        logger.error(f'按身份证获取报名详情失败: {str(e)}')
        return {'success': False, 'msg': f'获取报名详情失败：{str(e)}', 'data': None}


@router.get('/get_enrollment_detail')
async def get_enrollment_detail(
    id: int,
    db: Session = DatabaseDep,
):
    """获取报名记录详情（只查新生 nd=26）"""
    try:
        bmxs = db.query(ZzXs).filter(ZzXs.id == id, ZzXs.nd == 26).first()
        if not bmxs:
            return {'success': False, 'msg': '报名记录不存在', 'data': None}

        return {
            'success': True,
            'msg': '获取成功',
            'data': {
                'id': bmxs.id,
                'xm': bmxs.xm,
                'sfzh': bmxs.sfzh,
                'query_code': bmxs.query_code,
                'cooperation_schoolmajor_id': bmxs.cooperation_schoolmajor_id,
                'remark': bmxs.remark or '',
                'is_complete': bmxs.is_complete,
            }
        }
    except Exception as e:
        logger.error(f'获取报名详情失败: {str(e)}')
        return {'success': False, 'msg': f'获取报名详情失败：{str(e)}', 'data': None}


# 执行学生报名的核心业务逻辑，使用事务确保原子性,针对SQL Server优化的简化版本,给路由调用
def execute_student_registration(data, db: Session, redis_client=None, max_retries=3):
    # 第一层防线：Redis 分布式锁（跨进程/跨实例串行化同一专业的并发报名）
    lock = None
    if redis_client:
        lock = RedisLock(
            redis_client,
            key=f"zzbm:major:{data['cooperation_schoolmajor_id']}",
            timeout=15,        # 锁最多持有 15 秒，防止异常时锁不释放
            retry_delay=0.15
        )
        if not lock.acquire_sync(max_retries=10):
            return {
                'success': False,
                'msg': '系统繁忙，请稍后重试',
                'data': None
            }

    try:
      for attempt in range(max_retries):
        try:
            # 步骤1：加 UPDLOCK+ROWLOCK 行级锁，将同一专业的并发请求串行化，避免超卖
            current_cooperation_schoolmajor_id = db.execute(
                text("""
                    SELECT id, zsme, bmrs, cooperation_school, cooperation_major
                    FROM zz_bmxs_cooperation_schoolmajor WITH (UPDLOCK, ROWLOCK)
                    WHERE id = :id
                """),
                {"id": data['cooperation_schoolmajor_id']}
            ).first()

            if not current_cooperation_schoolmajor_id:
                return {
                    'success': False,
                    'msg': '选择的专业不存在',
                    'data': None
                }

            # 步骤2：检查名额是否充足
            zsme = current_cooperation_schoolmajor_id.zsme if current_cooperation_schoolmajor_id.zsme is not None else 0
            # 从数据库实时查询该专业的实际报名人数
            current_bmrs_result = db.execute(
                text("""
                    SELECT COUNT(*) as bmrs_count
                    FROM zz_xs
                    WHERE cooperation_schoolmajor_id = :cooperation_schoolmajor_id AND nd = 26
                """),
                {"cooperation_schoolmajor_id": data['cooperation_schoolmajor_id']}
            ).first()

            current_bmrs = current_bmrs_result.bmrs_count if current_bmrs_result else 0
            remaining = zsme - current_bmrs
            if remaining <= 0:
                return {
                    'success': False,
                    'msg': '您选择的报名专业已满额',
                    'data': None
                }

            # 步骤3：检查学生是否已报名（防止重复报名，只查已完成 is_complete=1 的记录）
            existing_bmxs = db.execute(
                text("""
                    SELECT id FROM zz_xs
                    WHERE sfzh = :sfzh AND nd = 26 AND is_complete = 1
                """),
                {"sfzh": data['sfzh']}
            ).first()

            if existing_bmxs:
                return {
                    'success': False,
                    'msg': '您已报名，不能重复报名',
                    'data': None
                }

            # 步骤4：使用原子操作插入报名记录并更新计数
            # 使用SQL Server的MERGE语句或者分步操作确保原子性
            try:
                # 插入报名记录
                new_bmxs = ZzXs(
                    xm=data['xm'],
                    xb=data['xb'],
                    mz=data['mz'],
                    zzmm=data['zzmm'],
                    sfzh=data['sfzh'],
                    xsdh=data['xsdh'],
                    jtxxdz=data['jtxxdz'],
                    jzdlx=data['jzdlx'],
                    hkxz=data['hkxz'],
                    jzxm=data['jzxm'],
                    jzgx=data['jzgx'],
                    jzdh=data['jzdh'],
                    cooperation_schoolmajor_id=data['cooperation_schoolmajor_id'],
                    byxxssx1=data.get('byxxssx1', ''),
                    byxxssx2=data.get('byxxssx2', ''),
                    byxxssx3=data.get('byxxssx3', ''),
                    byxxmc=data.get('byxxmc', ''),
                    zsdx=data.get('zsdx'),
                    sfjdlk=data.get('sfjdlk', 0),
                    sflset=data.get('sflset', 0),
                    sftwjrzn=data.get('sftwjrzn', 0),
                    xsly=data.get('xsly', ''),
                    qd=data.get('qd'),
                    qdjs=data.get('qdjs', ''),
                    sfqdxf=data.get('sfqdxf', 0),
                    nd=26,
                    is_complete=0
                )

                db.add(new_bmxs)

                # 更新专业报名人数：WHERE bmrs < zsme 为兑底防超卖内层防线
                update_result = db.execute(
                    text("""
                        UPDATE zz_bmxs_cooperation_schoolmajor
                        SET bmrs = bmrs + 1
                        WHERE id = :id AND bmrs < zsme
                    """),
                    {"id": data['cooperation_schoolmajor_id']}
                )

                if update_result.rowcount == 0:
                    db.rollback()
                    return {
                        'success': False,
                        'msg': '您选择的报名专业已满额，请重新选择',
                        'data': None
                    }

                # 提交事务
                db.commit()

                # 生成查询码并发送短信
                try:
                    from utils.query_code import generate_query_code, get_query_code_expire_time
                    from models.models import ZsAdultEnrollment, ZsVocational34Enrollment, ZsGraduateEmploymentSurvey
                    
                    # 生成唯一查询码（用ORM查询避免raw SQL在commit后的session问题）
                    for _retry in range(10):
                        query_code = generate_query_code()
                        # 检查跨表唯一性
                        exists = (
                            db.query(ZzXs).filter(ZzXs.query_code == query_code).first() or
                            db.query(ZsAdultEnrollment).filter(ZsAdultEnrollment.query_code == query_code).first() or
                            db.query(ZsVocational34Enrollment).filter(ZsVocational34Enrollment.query_code == query_code).first() or
                            db.query(ZsGraduateEmploymentSurvey).filter(ZsGraduateEmploymentSurvey.query_code == query_code).first()
                        )
                        if not exists:
                            break
                    
                    new_bmxs.query_code = query_code
                    new_bmxs.query_code_expire = get_query_code_expire_time()
                    db.commit()
                    
                    # 短信通知用户查询码
                    from utils.sms import SMSTool
                    sms_tool = SMSTool()
                    sms_tool.send_by_scenario(
                        scenario='query_code',
                        mobile=data['xsdh'],
                        values={
                            'name': data['xm'],
                            'query_code': query_code,
                            'biz_name': '中职自主报名',
                        },
                        xs_xm=data['xm'],
                    )
                except Exception as qc_err:
                    logger.warning(f'报名成功但查询码生成/短信发送失败: {qc_err}')
                    query_code = None

                return {
                    'success': True,
                    'msg': '报名成功',
                    'data': {
                        'id': new_bmxs.id,
                        'major_name': f"{current_cooperation_schoolmajor_id.cooperation_school}-{current_cooperation_schoolmajor_id.cooperation_major}",
                        'current_bmrs': current_bmrs + 1,
                        'zsme': zsme,
                        'query_code': query_code
                    }
                }

            except Exception as inner_e:
                db.rollback()
                raise inner_e

        except (OperationalError, IntegrityError) as e:
            # 确保事务回滚
            db.rollback()

            error_msg = str(e).lower()

            # 检查是否是可重试的错误
            if any(keyword in error_msg for keyword in ['timeout', 'deadlock', 'lock wait', 'duplicate']):
                if attempt < max_retries - 1:
                    # 等待一段时间后重试
                    time.sleep(0.1 * (attempt + 1))  # 递增等待时间
                    logging.warning(f"报名操作重试 {attempt + 1}/{max_retries}: {str(e)}")
                    continue
                else:
                    return {
                        'success': False,
                        'code': 1001,
                        'msg': '系统繁忙，请稍后重试',
                        'data': None
                    }
            else:
                return {
                    'success': False,
                    'code': 500,
                    'msg': f'报名失败：{str(e)}',
                    'data': None
                }

        except Exception as e:
            # 确保事务回滚
            db.rollback()

            return {
                'success': False,
                'code': 500,
                'msg': f'报名失败：{str(e)}',
                'data': None
            }

      # 所有重试都失败了
      return {
          'success': False,
          'code': 1001,
          'msg': '系统繁忙，请稍后重试',
          'data': None
      }
    finally:
        # 无论成功失败，都释放 Redis 分布式锁
        if lock:
            lock.release_sync()


# 获取报名统计信息，用于监控和数据校验
def get_registration_statistics(db: Session, nd: int = 26):
    try:
        # 获取专业统计信息 - SQL Server兼容语法
        major_stats = db.execute(
            text("""
                SELECT
                    s.id,
                    s.cooperation_school,
                    s.cooperation_major,
                    s.zsme as quota,
                    s.bmrs as recorded_count,
                    COUNT(b.id) as actual_count,
                    (s.zsme - s.bmrs) as remaining_quota,
                    CASE
                        WHEN s.zsme > 0 THEN ROUND((CAST(s.bmrs AS FLOAT) / CAST(s.zsme AS FLOAT)) * 100, 2)
                        ELSE 0
                    END as registration_rate
                FROM zz_bmxs_cooperation_schoolmajor s
                LEFT JOIN zz_xs b ON s.id = b.cooperation_schoolmajor_id AND b.nd = :nd
                GROUP BY s.id, s.cooperation_school, s.cooperation_major, s.zsme, s.bmrs
                ORDER BY registration_rate DESC
            """),
            {"nd": nd}
        ).fetchall()

        # 检查数据一致性
        inconsistent_majors = []
        total_quota = 0
        total_registered = 0
        total_actual = 0

        for stat in major_stats:
            total_quota += stat.quota or 0
            total_registered += stat.recorded_count or 0
            total_actual += stat.actual_count or 0

            if stat.recorded_count != stat.actual_count:
                inconsistent_majors.append({
                    'major_id': stat.id,
                    'major_name': f"{stat.cooperation_school}-{stat.cooperation_major}",
                    'recorded_count': stat.recorded_count,
                    'actual_count': stat.actual_count,
                    'difference': stat.actual_count - stat.recorded_count
                })

        # 检查超额报名
        over_quota_majors = []
        for stat in major_stats:
            if stat.quota and stat.recorded_count > stat.quota:
                over_quota_majors.append({
                    'major_id': stat.id,
                    'major_name': f"{stat.cooperation_school}-{stat.cooperation_major}",
                    'quota': stat.quota,
                    'registered': stat.recorded_count,
                    'over_count': stat.recorded_count - stat.quota
                })

        return {
            'success': True,
            'data': {
                'batch': nd,
                'summary': {
                    'total_majors': len(major_stats),
                    'total_quota': total_quota,
                    'total_registered': total_registered,
                    'total_actual': total_actual,
                    'remaining_quota': total_quota - total_registered,
                    'overall_rate': round((total_registered / total_quota) * 100, 2) if total_quota > 0 else 0
                },
                'major_statistics': [
                    {
                        'major_id': stat.id,
                        'major_name': f"{stat.cooperation_school}-{stat.cooperation_major}",
                        'quota': stat.quota,
                        'registered': stat.recorded_count,
                        'actual': stat.actual_count,
                        'remaining': stat.remaining_quota,
                        'rate': stat.registration_rate
                    }
                    for stat in major_stats
                ],
                'data_issues': {
                    'inconsistent_count': len(inconsistent_majors),
                    'inconsistent_majors': inconsistent_majors,
                    'over_quota_count': len(over_quota_majors),
                    'over_quota_majors': over_quota_majors
                }
            }
        }

    except Exception as e:
        return {
            'success': False,
            'message': f'获取统计信息失败：{str(e)}',
            'data': None
        }



# 获取报名信息，用于前端展示
@router.get('/check_zz_bm_switch')
async def check_zz_bm_switch(db: Session = DatabaseDep):
    try:
        zz_sys = db.query(ZzSys).first()
        return {
            'success': True,
            'msg': '获取报名信息成功',
            'data': zz_sys.zz_xsbm_switch
        }
    except Exception as e:
        return {
            'success': False,
            'message': f'获取报名信息失败：{str(e)}',
            'data': None
        }


# 实时查询某专业的剩余名额（前端第四步确认页刷新用）
@router.get('/get_remaining_spots')
async def get_remaining_spots(major_id: int, db: Session = DatabaseDep):
    try:
        major = db.execute(
            text("""
                SELECT id, zsme, cooperation_school, cooperation_major
                FROM zz_bmxs_cooperation_schoolmajor
                WHERE id = :id
            """),
            {"id": major_id}
        ).first()

        if not major:
            return {'success': False, 'msg': '专业不存在', 'data': None}

        actual_count = db.execute(
            text("""
                SELECT COUNT(*) FROM zz_xs
                WHERE cooperation_schoolmajor_id = :cooperation_schoolmajor_id AND nd = 26
            """),
            {"cooperation_schoolmajor_id": major_id}
        ).scalar()

        zsme = major.zsme or 0
        remaining = max(0, zsme - actual_count)

        return {
            'success': True,
            'data': {
                'major_id': major_id,
                'zsme': zsme,
                'actual_count': actual_count,
                'remaining': remaining
            }
        }
    except Exception as e:
        return {'success': False, 'msg': f'查询失败：{str(e)}', 'data': None}


# 获取报名信息，用于前端展示
@router.get('/get_new_zzbm_info')
async def get_new_zzbm_info(db: Session = DatabaseDep):
    try:
        # 创建空的报名学生对象
        empty_bmxs = {
            'xm': '',
            'xb': '',
            'mz': '',
            'zzmm': None,
            'sfzh': '',
            'xsdh': '',
            'jtxxdz': '',
            'jzdlx': None,
            'hkxz': '',
            'jzxm': '',
            'jzgx': None,
            'jzdh': '',
            'cooperation_schoolmajor_id': None,
            'byxxssx1': '',
            'byxxssx2': '',
            'byxxssx3': '',
            'byxxmc': '',
            'zsdx': None,
            'sfjdlk': 0,
            'sflset': 0,
            'sftwjrzn': 0,
            'xsly': '',
            'qd': None,
            'qdjs': '',
            'sfqdxf': 0
        }

        # 获取学校列表
        # 获取所有专业列表，并按学校ID分组


        
        #获取专业和合作院校的对象
        # 获取试卷类型信息
        sql_cooperation_schoolmajor_id = text("""
            select a.id,a.major_name,b.id as school_major_name_id ,b.cooperation_school,b.cooperation_major,b.zsme,b.bmrs,b.remark from zz_bmxs_local_major as a 
            left join zz_bmxs_cooperation_schoolmajor as b 
            on a.id = b.local_major_id
            where a.zs = 1 and b.zs = 1
        """)
        result = db.execute(sql_cooperation_schoolmajor_id).fetchall()

        bdzy_list = {}

        for row in result:
            id,major_name,school_major_name_id,cooperation_school,cooperation_major,zsme,bmrs,remark = row

            # 如果本地专业不在列表中，则新建对象
            if id not in bdzy_list:
                bdzy_list[id] = {
                    'id': id,
                    'major_name': major_name,
                    'cooperation_schoolmajors': []
                }
            # 如果合作院校专业不在列表中，则新建对象
            if school_major_name_id is not None:
                bdzy_list[id]['cooperation_schoolmajors'].append ({
                    'school_major_name_id': school_major_name_id,
                    'cooperation_school': cooperation_school,
                    'cooperation_major':cooperation_major,
                    'zsme':zsme,
                    'bmrs': bmrs,
                    'remark':remark
                })



        # 获取政治面貌列表
        zzmm_list = db.query(ZzBmxsZzmm).filter_by(yc=0).order_by(ZzBmxsZzmm.px).all()
        zzmm_options = [{'id': zzmm.id, 'name': zzmm.mc} for zzmm in zzmm_list]

        # 获取家长类型列表
        jzdlx_list = db.query(ZzBmxsJzdlx).filter_by(yc=0).order_by(ZzBmxsJzdlx.px).all()
        jzdlx_options = [{'id': jzdlx.id, 'name': jzdlx.mc} for jzdlx in jzdlx_list]

        # 获取家长关系列表
        jzgx_list = db.query(ZzBmxsJzgx).filter_by(yc=0).order_by(ZzBmxsJzgx.px).all()
        jzgx_options = [{'id': jzgx.id, 'name': jzgx.mc} for jzgx in jzgx_list]

        # 获取招生对象列表
        zsdx_list = db.query(ZzBmxsZsdx).filter_by(yc=0).order_by(ZzBmxsZsdx.px).all()
        zsdx_options = [{'id': zsdx.id, 'name': zsdx.mc} for zsdx in zsdx_list]

        # 获取渠道列表
        qd_list = db.query(ZzBmxsQd).filter_by(yc=0).order_by(ZzBmxsQd.px).all()
        qd_options = [{'id': qd.id, 'name': qd.mc} for qd in qd_list]

        # 获取当前年度
        current_year = datetime.now().year

        # 返回数据
        return {
            'success': True,
            'msg': '获取成功',
            'data': {
                'options': {
                    'bdzy_list': list(bdzy_list.values()),   #这里只取值，不用键了。很关键。
                    'zzmm': zzmm_options,
                    'jzdlx': jzdlx_options,
                    'jzgx': jzgx_options,
                    'zsdx': zsdx_options,
                    'qd': qd_options
                },
                'current_year': current_year
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail={
            'success': False,
            'msg': f'获取数据失败：{str(e)}',
            'data': None
        })



# ================================================================
# 新建报名记录
# ================================================================

# 新建报名记录
@router.post('/create_zzbm')
async def create_zzbm(
    create_request: CreateZzbmRequest,
    db: Session = DatabaseDep,
    redis=RedisDep,
    current_user: dict = Depends(get_current_user),
):
    try:
        # 将Pydantic模型转换为字典
        data = create_request.dict()

        # 验证必填字段
        required_fields = ['xm', 'xb', 'mz', 'zzmm', 'sfzh', 'xsdh', 'jtxxdz',
                         'jzdlx', 'hkxz', 'jzxm', 'jzgx', 'jzdh', 'cooperation_schoolmajor_id',
                         'sfqdxf']

        for field in required_fields:
            if field not in data or data[field] is None or data[field] == '':
                raise HTTPException(status_code=400, detail={
                    'success': False,
                    'msg': f'缺少必填字段：{field}',
                    'data': None
                })

        # 把 sfqdxf 强制转换为合法整数 0 或 1，避免 Pydantic 默认值掩盖前端错传
        try:
            data['sfqdxf'] = int(data['sfqdxf'])
            if data['sfqdxf'] not in (0, 1):
                data['sfqdxf'] = 1 if data['sfqdxf'] else 0
        except (TypeError, ValueError):
            data['sfqdxf'] = 0

        # 将身份证号码转换为大写
        data['sfzh'] = data['sfzh'].upper()
        sfzh_pattern = r'^[1-9]\d{5}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]$'
        if not re.match(sfzh_pattern, data['sfzh']):
            raise HTTPException(status_code=400, detail={
                'success': False,
                'msg': '身份证号码格式不正确',
                'data': None
            })

        # 验证学生电话号码格式
        phone_pattern = r'^1[3-9]\d{9}$'
        if not re.match(phone_pattern, data['xsdh']):
            raise HTTPException(status_code=400, detail={
                'success': False,
                'msg': '学生电话号码格式不正确',
                'data': None
            })

        # 验证监护人电话号码格式
        if not re.match(phone_pattern, data['jzdh']):
            raise HTTPException(status_code=400, detail={
                'success': False,
                'msg': '监护人电话号码格式不正确',
                'data': None
            })

        # 判断是否能报名
        current_zzxs = db.query(ZzXs).filter_by(sfzh=data['sfzh']).first()

        if current_zzxs and current_zzxs.xjzt == 1:
            return {
                'success': False,
                'msg': '您还在籍，不能报名',
                'data': None
            }

        current_zz_bmxs = db.query(ZzXs).filter_by(sfzh=data['sfzh'], nd=26).first()
        if current_zz_bmxs:
            return {
                'success': False,
                'msg': '您已报名，不能重复报名',
                'data': None
            }

        # 调用报名服务函数执行核心业务逻辑
        result = execute_student_registration(data, db, redis_client=redis)

        return {
            'success': result['success'],
            'msg': result['msg'],
            'data': result['data']
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail={
            'success': False,
            'msg': f'报名失败：{str(e)}',
            'data': None
        })




# ============获取报名统计信息API,要做权限控制，只有管理员可以访问，目前暂时不做权限控制============
@router.get('/registration_statistics')
async def get_registration_statistics_api(nd: int = 26, db: Session = DatabaseDep):
    try:
        result = get_registration_statistics(db, nd)

        if result['success']:
            return {
                'success': 0,
                'msg': '获取统计信息成功',
                'data': result['data']
            }
        else:
            return {
                'success': 1,
                'msg': result['message'],
                'data': None
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail={
            'success': 500,
            'msg': f'获取统计信息失败：{str(e)}',
            'data': None
        })



# ============修复报名人数统计不一致的问题 ，只有管理员可以访问，目前暂时不做权限控制============
@router.post('/fix_registration_count')
async def fix_registration_count(db: Session = DatabaseDep):
    try:
        # 修复所有专业的报名人数 - 分步骤执行，兼容SQL Server
        # 首先获取需要修复的专业列表
        majors_to_fix = db.execute(
            text("""
                SELECT DISTINCT cooperation_schoolmajor_id
                FROM zz_xs
                WHERE nd = 26 AND cooperation_schoolmajor_id IS NOT NULL
            """)
        ).fetchall()

        updated_count = 0

        # 逐个更新每个专业的报名人数
        for major in majors_to_fix:
            major_id = major.cooperation_schoolmajor_id

            # 获取该专业的实际报名人数
            actual_count = db.execute(
                text("""
                    SELECT COUNT(*) as cnt
                    FROM zz_xs
                    WHERE cooperation_schoolmajor_id = :major_id AND nd = 26
                """),
                {"major_id": major_id}
            ).scalar()

            # 更新专业表中的报名人数
            update_result = db.execute(
                text("""
                    UPDATE zz_bmxs_cooperation_schoolmajor
                    SET bmrs = :actual_count
                    WHERE id = :major_id
                """),
                {"actual_count": actual_count, "major_id": major_id}
            )

            if update_result.rowcount > 0:
                updated_count += 1

        db.commit()

        # 获取修复后的统计信息
        stats_result = get_registration_statistics(db, 26)

        return {
            'success': 0,
            'msg': f'修复完成，共更新了 {updated_count} 个专业的报名人数',
            'data': {
                'updated_count': updated_count,
                'total_majors': len(majors_to_fix),
                'statistics': stats_result['data'] if stats_result['success'] else None
            }
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail={
            'success': 500,
            'msg': f'修复失败：{str(e)}',
            'data': None
        })




# 生成中职报名推广二维码接口（无需认证），base64数据
@router.post('/generate_qrcode')
async def generate_qrcode(qrcode_request: GenerateQrcodeRequest):
    try:
        # 获取推广人姓名参数
        introducer = qrcode_request.introducer
        if not introducer:
            raise HTTPException(status_code=400, detail={
                'success': False,
                'msg': '缺少必填参数：introducer（推广人姓名）',
                'data': None
            })

        # 获取可选的宽度参数
        width = qrcode_request.width

        # 验证宽度参数
        if not isinstance(width, int) or width < 280 or width > 1280:
            raise HTTPException(status_code=400, detail={
                'success': False,
                'msg': '宽度参数错误，必须是280-1280之间的整数',
                'data': None
            })

        # 使用WxQrCode工具类生成二维码
        result = WxQrCode.generate_zzbm_qrcode(introducer, width)

        # 返回结果
        if result['success']:
            return {
                'success': True,
                'msg': result['message'],
                'data': {
                    'qrcode_base64': result['data']
                }
            }
        else:
            raise HTTPException(status_code=500, detail={
                'success': False,
                'msg': result['message'],
                'data': None
            })

    except Exception as e:
        logging.error(f"生成中职报名二维码异常: {str(e)}")
        raise HTTPException(status_code=500, detail={
            'success': False,
            'msg': f'生成二维码失败：{str(e)}',
            'data': None
        })



# 生成录取通知书接口（无需认证）- 返回Base64数据
# 接收学生姓名、专业、开学日期、落款日期，生成填写好的录取通知书PDF
@router.get('/generate_admission_notice')
async def generate_admission_notice(student_name: str,major: str,start_date: str,issue_date: str):
    try:
        # 验证必填参数
        if not all([student_name, major, start_date, issue_date]):
            raise HTTPException(status_code=400, detail={
                'success': 400,
                'msg': '缺少必填参数：student_name（学生姓名）、major（专业）、start_date（开学日期）、issue_date（落款日期）',
                'data': None
            })

        # 验证参数格式和内容
        admission_notice = AdmissionNotice()
        is_valid, error_msg = admission_notice.validate_student_info(
            student_name, major, start_date, issue_date
        )

        if not is_valid:
            raise HTTPException(status_code=400, detail={
                'success': 400,
                'msg': f'参数验证失败：{error_msg}',
                'data': None
            })

        # 生成录取通知书
        result = admission_notice.create_filled_notice(
            student_name, major, start_date, issue_date
        )

        # 返回结果
        if result['success']:
            return {
                'success': 0,
                'msg': result['message'],
                'data': {
                    'pdf_base64': result['data'],
                    'filename': result['filename'],
                    'student_name': student_name,
                    'major': major,
                    'start_date': start_date,
                    'issue_date': issue_date
                }
            }
        else:
            raise HTTPException(status_code=500, detail={
                'success': 500,
                'msg': result['message'],
                'data': None
            })

    except Exception as e:
        logging.error(f"生成录取通知书异常: {str(e)}")
        raise HTTPException(status_code=500, detail={
            'success': 500,
            'msg': f'生成录取通知书失败：{str(e)}',
            'data': None
        })




# 生成录取通知书接口（无需认证）- 返回标准数据格式，PDF数据放在data中
@router.get('/generate_admission_notice_pdf_data')
async def generate_admission_notice_pdf_data(o_id: str,db: Session = DatabaseDep):

    # return {
    #     'success': False,
    #     'msg': '录取通知书下载暂时未开通，请等候通知',
    #     'data': None
    # }

    try:
        # 验证必填参数
        if not o_id:
            return {
                'success': False,
                'msg': '缺少必填参数：o_id（订单号）',
                'data': None
            }
        get_payment_info = db.query(WxPayinfo).filter_by(o_id=o_id).first()
        if not get_payment_info:
            return {
                'success': False,
                'msg': '参数错误，请联系管理员',
                'data': None
            }
        # 姓名优先取订单表的 o_xm，如果为空则从报名表 bmxs_info.xm 兜底
        raw_name = get_payment_info.o_xm
        sys_info = db.query(ZzSys).first()
        bmxs_info = db.query(ZzXs).filter_by(sfzh=get_payment_info.o_sfzh, nd=26).first()
        if not bmxs_info:
            return {
                'success': False,
                'msg': '未找到该学生的报名信息，请联系管理员',
                'data': None
            }
        student_name = (raw_name.strip() if raw_name and raw_name.strip() else None) or (bmxs_info.xm.strip() if bmxs_info.xm and bmxs_info.xm.strip() else None)
        logging.info(f"[通知书] o_id={o_id}, raw_name='{raw_name}', bmxs.xm='{bmxs_info.xm}', final_name='{student_name}'")
        cooperation_schoolmajor_id = bmxs_info.cooperation_schoolmajor_id

        # 获取专业信息
        sql_cooperation_schoolmajor_id = text("""
            select a.id,a.major_name,b.id as school_major_name_id ,b.cooperation_school,b.cooperation_major,b.zsme,b.bmrs,b.remark from zz_bmxs_local_major as a
            left join zz_bmxs_cooperation_schoolmajor as b
            on a.id = b.local_major_id
            where b.id = :cooperation_schoolmajor_id and a.zs = 1
        """)

        result = db.execute(sql_cooperation_schoolmajor_id, {"cooperation_schoolmajor_id": cooperation_schoolmajor_id}).first()
        if not result:
            return {
                'success': False,
                'msg': '参数错误，请联系管理员',
                'data': None
            }

        major = result.major_name
        start_date = '2026-08-29'
        end_date = '2026-08-30'
        issue_date = datetime.now().strftime('%Y-%m-%d')

        # 构建水印文字：学校名 + 姓名 + 手机尾号 + 日期时间
        phone = (bmxs_info.xsdh or '').strip()
        phone_tail = f'****{phone[-4:]}' if len(phone) >= 4 else ''
        now = datetime.now()
        time_str = f'{now.year}-{str(now.month).zfill(2)}-{str(now.day).zfill(2)} {str(now.hour).zfill(2)}:{str(now.minute).zfill(2)}'
        parts = ['黔东南中等职业技术学校', student_name]
        if phone_tail:
            parts.append(phone_tail)
        parts.append(time_str)
        watermark_text = ' · '.join(parts)

        # 生成录取通知书
        admission_notice = AdmissionNotice()
        pdf_bytes = admission_notice.get_pdf_bytes(
            student_name, major, start_date, end_date, issue_date,
            watermark_text=watermark_text
        )

        if not pdf_bytes:
            return {
                'success': False,
                'msg': '生成录取通知书失败',
                'data': None
            }

        # 将PDF转换为Base64编码
        import base64
        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')

        # 生成文件名
        filename = f'录取通知书_{student_name}_{datetime.now().strftime("%Y%m%d")}.pdf'

        return {
            'success': True,
            'msg': '录取通知书生成成功',
            'data': {
                'pdf_base64': pdf_base64,
                'filename': filename,
                'content_type': 'application/pdf',
                'file_size': len(pdf_bytes),
                'student_name': student_name,
                'major': major,
                'start_date': start_date,
                'end_date': end_date,
                'issue_date': issue_date
            }
        }

    except Exception as e:
        logging.error(f"生成录取通知书PDF异常: {str(e)}")
        return {
            'success': False,
            'msg': f'生成录取通知书失败：{str(e)}',
            'data': None
        }



@router.get('/query_student_class_info')
async def query_student_class_info(sfzh: str, db: Session = DatabaseDep):
    try:
        from models.models import ZzSsCw, ZzSsSs, ZzSsLc, ZzSsLd
        
        sys_info = db.query(ZzSys).first()
        student = db.query(ZzXs).filter_by(sfzh=sfzh).first()
        if not student:
            return {
                'success': False,
                'msg': '没有您的学生信息',
                'data': None
            }
        class_info = db.query(ZzBj).filter_by(id=student.bj_id).first()
        if not class_info:
            return {
                'success': False,
                'msg': '学校还未给您分班，请耐心等待',
                'data': None
            }
        master_teacher = db.query(Teacher).filter_by(t_id=class_info.bzr_id).first()
        if not master_teacher:
            logging.warning(f"学生 {sfzh} 的班级 {class_info.mc} 未分配班主任 bzr_id={class_info.bzr_id}")

        # 查询寝室信息：通过学生在 zz_ss_cw 表的 zsr_id 关联反向查询
        dorm_info = None
        if student.id:
            dorm_sql = text("""
                SELECT 
                    cw.id as cw_id,
                    cw.cwh as cwh,
                    ss.id as ss_id,
                    ss.ssh as ssh,
                    ss.cwsl as cwsl,
                    lc.id as lc_id,
                    lc.lc as lc,
                    ld.id as ld_id,
                    ld.mc as ld_mc
                FROM zz_ss_cw cw
                LEFT JOIN zz_ss_ss ss ON cw.ss_id = ss.id
                LEFT JOIN zz_ss_lc lc ON ss.lc_id = lc.id
                LEFT JOIN zz_ss_ld ld ON lc.ld_id = ld.id
                WHERE cw.zsr_id = :xs_id AND cw.zsr_type = 'student' AND cw.zt = 1
            """)
            dorm_result = db.execute(dorm_sql, {"xs_id": student.id}).first()
            if dorm_result:
                ld_mc = dorm_result.ld_mc or ''
                ssh = dorm_result.ssh or ''
                cwh = dorm_result.cwh or ''
                cwsl = dorm_result.cwsl or 8  # 默认8人间
                # 拼接寝室完整名称：A栋-103室-7号床位
                full_dorm = f"{ld_mc}-{ssh}室-{cwh}号床位"
                dorm_info = {
                    'ld_mc': ld_mc,
                    'ssh': ssh,
                    'cwh': cwh,
                    'cwsl': cwsl,  # 寝室床位数（6人间/8人间）
                    'full_dorm': full_dorm
                }

        student_info = {
            'xm': student.xm,
            'xh': student.xh,
            'sfzh': student.sfzh,
            'bj_mc': class_info.mc,
            'jss': class_info.jss or '',  # 教室
            't_xm': master_teacher.t_xm if master_teacher else '',
            't_dh': master_teacher.t_dh if master_teacher else '',
            'dorm_info': dorm_info  # 寝室信息
        }

        return {
            'success': True,
            'msg': '查询成功',
            'data': {
                'student_info': student_info
            }
        }

    except Exception as e:
        logging.error(f"查询学生班级信息异常: {str(e)}")
        return {
            'success': False,
            'msg': f'查询失败：{str(e)}',
            'data': None
        }


# ============================================================
# 管理员接口：批量修复 zz_bmxs.is_complete 字段
# 规则：xm、xb、mz 三个字段都有值 -> is_complete=1
#       否则 -> is_complete=0
# ============================================================
@router.post('/admin/fix_is_complete')
async def admin_fix_is_complete(db: Session = DatabaseDep):
    """
    批量修复 is_complete 字段。
    只要 xm、xb、mz 都有值就标记为已完成（is_complete=1），其余为草稿（is_complete=0）。
    """
    try:
        # 修复：xm/xb/mz 都有值的设为 1，其余设为 0（只修复新生 nd=26）
        fix_sql = text("""
            UPDATE zz_xs
            SET is_complete = CASE
                WHEN xm IS NOT NULL AND xm <> ''
                     AND xb IS NOT NULL AND xb <> ''
                     AND mz IS NOT NULL AND mz <> ''
                THEN 1
                ELSE 0
            END
            WHERE nd = 26
        """)
        result = db.execute(fix_sql)
        db.commit()

        # 统计
        total_sql = text("SELECT COUNT(*) as total FROM zz_xs WHERE nd = 26")
        total = db.execute(total_sql).scalar()

        complete_sql = text("SELECT COUNT(*) as complete FROM zz_xs WHERE nd = 26 AND is_complete = 1")
        complete = db.execute(complete_sql).scalar()

        return {
            'success': True,
            'msg': '修复完成',
            'data': {
                'total': total,
                'complete': complete,
                'draft': total - complete,
            }
        }
    except Exception as e:
        db.rollback()
        return {
            'success': False,
            'msg': f'修复失败：{str(e)}',
            'data': None
        }