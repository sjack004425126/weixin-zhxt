from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
from models.models import Class, ZzBj, ZzXs,ZzSys
from init.dependencies import (
    get_redis, get_db,
    RedisDep, DatabaseDep, RedisManagerDep
)
from common.auth import verify_token_and_get_payload, create_token, create_refresh_token
from controllers.login import calculate_current_term  # 统一学期计算函数
import hashlib
import time
import jwt
from utils.wx_utils import WxUtils
import logging

# 创建路由器
router = APIRouter(prefix="/vocational_login", tags=["职业教育登录"])


class LoginUsernameAndPasswordRequest(BaseModel):
    username: str
    password: str


class QuickLoginRequest(BaseModel):
    """openid 快捷登录请求（wx.login code）"""
    code: str


def _bind_openid_to_student(db: Session, student: ZzXs, openid: str) -> bool:
    """把 openid 绑定到中职学生记录（供后续 openid 快捷登录使用）。

    规则（与 /bind_openid/zz 保持一致）：
      - 已有 openid 且非空 → 不覆盖（返回 False）
      - openid 已被别的学生占用 → 踢掉旧绑定，再写入
      - 同时维护 xs_wx_openid_hash（隐私合规）

    Returns: 是否成功写入绑定。
    """
    if not openid:
        return False
    try:
        from utils.hash_util import hash_openid

        current = student.xs_wx_openid
        if current and str(current).strip():
            # 已绑定：不覆盖，避免抢占他人绑定
            return False

        kicked = (
            db.query(ZzXs)
            .filter(ZzXs.xs_wx_openid == openid, ZzXs.id != student.id)
            .update(
                {"xs_wx_openid": None, "xs_wx_openid_hash": None},
                synchronize_session=False,
            )
        )
        if kicked:
            logging.warning(f"[bind_openid] 踢掉旧绑定 openid={openid} count={kicked}")

        student.xs_wx_openid = openid
        student.xs_wx_openid_hash = hash_openid(openid)
        db.commit()
        return True
    except Exception as e:
        logging.warning(f"[bind_openid] 绑定 openid 失败: {e}")
        db.rollback()
        return False


# 通过 openid 快捷登录（中职学生）
@router.post('/quickLogin')
async def quick_login_openid(login_request: QuickLoginRequest, db: Session = DatabaseDep):
    """用 wx.login code → openid，匹配中职学生信息进行登录。

    前提：用户此前至少通过一次手机号快捷登录（或账号密码登录），
    后端已把 openid 绑定到该学生。
    """
    try:
        code = login_request.code
        if not code:
            return {
                'success': False,
                'msg': '缺少关键参数',
                'data': None
            }

        # 使用 WxUtils 获取 openid
        wx_result = WxUtils.get_openid_and_session_key(code)
        if not wx_result:
            return {
                'success': False,
                'msg': '登录失败，您提供的code错误',
                'data': None
            }
        openid = wx_result.get('openid')

        # 查询中职学生：同一 openid 可能有多条，取 id 最大（当前在读）
        student = (
            db.query(ZzXs)
            .filter(ZzXs.xs_wx_openid == openid)
            .order_by(ZzXs.id.desc())
            .first()
        )
        if not student:
            return {
                'success': False,
                'msg': '当前微信还未绑定学生信息，请先使用「手机号快捷登录」或「账号密码登录」完成一次登录',
                'data': None
            }

        # 获取班级信息
        class_info = db.query(ZzBj).filter(ZzBj.id == student.bj_id).first()
        sys_info = db.query(ZzSys).first()
        if not sys_info:
            return {
                'success': False,
                'msg': '未找到系统信息',
                'data': None
            }

        has_openid = bool(student.xs_wx_openid)
        payload = {
            'xs_xh': student.xh,
            'xs_bj_id': student.bj_id,
            'xs_id': student.id,
            # ⭐ 头像上传需要：身份由 token 直接推导，前端不传身份证号
            'sfzh': student.sfzh,
            'user_type': 'vocational_student',
            'xs_xm': student.xm,
        }
        token = create_token({**payload})
        refresh_token = create_refresh_token(payload)

        response_data = {
            'xs_xh': student.xh,
            'xs_xm': student.xm,
            'xs_dh': student.xsdh,
            'xs_sfzh': student.sfzh,
            'xs_bj_id': student.bj_id,
            'nickName': student.xs_wx_nickname,
            'avatarUrl': student.xs_wx_headimgurl,
            'token': token,
            'refresh_token': refresh_token,
            'class_name': class_info.mc if class_info else '',
            'bind': has_openid,
            'current_term': calculate_current_term(sys_info.zz_dq_nd, sys_info.zz_dq_xq, student.nd, '09'),
            'xs_xjzt': student.xjzt
        }

        return {
            'success': True,
            'msg': '登录成功',
            'data': response_data
        }

    except Exception as e:
        logging.error(f"通过openid登录失败: {str(e)}")
        return {
            'success': False,
            'msg': f'登录失败: {str(e)}',
            'data': None
        }


# 验证用户登录,使用用户名和密码登录
@router.post('/login_by_username_and_password')
async def login_by_username_and_password(user_login_request: LoginUsernameAndPasswordRequest,db: Session = DatabaseDep,redis_client = RedisDep):
    try:
        # 获取请求数据
        username = user_login_request.username
        password = user_login_request.password
        
        if not username or not password:
            return {
                'success': False,
                'msg': '身份证号或密码不能为空',
                'data': None
            }

        # 密码加密处理
        password = hashlib.md5(password.encode()).hexdigest()
        password = password[:18]  # 取18位
        password = hashlib.md5(password.encode()).hexdigest()
        # 查询用户：同一学号可能对应多名学生（退学后重新入学的场景），
        # 按 id 降序取最新的一条，保证拿到当前在读学生
        student = (
            db.query(ZzXs)
            .filter(ZzXs.xh == username, ZzXs.mm == password)
            .order_by(ZzXs.id.desc())
            .first()
        )
        if not student:
            return {
                'success': False,
                'msg': '用户名或密码错误',
                'data': None
            }

        # 获取班级信息
        class_info = db.query(ZzBj).filter_by(id=student.bj_id).first()
        # 获取学籍状态描述
        # def get_status_desc(status_code):
        #     status_map = {
        #         "1": "在籍",
        #         "2": "未注册",
        #         "3": "转出",
        #         "4": "休学",
        #         "5": "退学",
        #         "6": "开除",
        #         "7": "毕业",
        #         "8": "异动中"
        #     }
        #     return status_map.get(status_code, "错误")
        
        has_openid = bool(student.xs_wx_openid)
        payload = {
            'xs_xh': student.xh,
            'xs_bj_id': student.bj_id,
            'xs_id': student.id,
            # ⭐ 头像上传需要：身份由 token 直接推导，前端不传身份证号
            'sfzh': student.sfzh,
            'user_type': 'vocational_student',
            'xs_xm': student.xm,
        }
        # 生成token
        token = create_token({**payload})
        refresh_token = create_refresh_token(payload)

        sys_info = db.query(ZzSys).first()
        
        response_data = {
            'xs_xh': student.xh,
            'xs_xm': student.xm,
            'xs_dh': student.xsdh,
            'xs_bj_id': student.bj_id,
            'xs_sfzh': student.sfzh,
            'nickName': student.xs_wx_nickname,
            'avatarUrl': student.xs_wx_headimgurl,
            'token': token,
            'refresh_token': refresh_token,
            'class_name': class_info.mc if class_info else '',  # 添加班级名称
            'bind': has_openid,
            'current_term': calculate_current_term(sys_info.zz_dq_nd, sys_info.zz_dq_xq, student.nd, '09'),
            'xs_xjzt': student.xjzt
        }
        
        return {
            'success': True,
            'msg': '登录成功',
            'data': response_data
        }
    except Exception as e:
        return {
            'success': False,
            'msg': f'登录失败: {str(e)}',
            'data': None
        }
    





# 手机号快捷登录（中职学生）
class PhoneQuickLoginRequest(BaseModel):
    code: str
    # 7 天手机号缓存：可选字段
    login_code: Optional[str] = None
    subject: Optional[str] = None

@router.post('/phone_quick_login')
async def phone_quick_login(request: PhoneQuickLoginRequest, db: Session = DatabaseDep):
    """通过微信获取手机号，然后匹配中职学生信息进行登录"""
    try:
        code = request.code
        if not code:
            return {
                'success': False,
                'msg': '缺少code参数',
                'data': None
            }

        # 使用WxUtils获取手机号
        wx_util = WxUtils()
        phone_result = wx_util.get_phone_number(code)

        logging.info(f"获取手机号结果: {phone_result}")

        if not phone_result:
            return {
                'success': False,
                'msg': '获取手机号失败',
                'data': None
            }

        phone_info = phone_result.get('phone_info', {})
        phone_number = phone_info.get('phoneNumber') or phone_info.get('purePhoneNumber')

        if not phone_number:
            return {
                'success': False,
                'msg': '获取手机号失败',
                'data': None
            }

        # 归一化手机号
        from common import phone_cache as _phone_cache
        pure_phone = _phone_cache.normalize_phone(phone_number)
        masked_phone = _phone_cache.mask_phone(pure_phone)

        # 查询中职学生表，通过手机号匹配：
        # 同一手机号可能绑定多名学生（退学后重新入学的场景），
        # 按 id 降序取最新的一条，保证拿到当前在读学生
        student = (
            db.query(ZzXs)
            .filter(ZzXs.xsdh == phone_number)
            .order_by(ZzXs.id.desc())
            .first()
        )

        if not student:
            return {
                'success': False,
                'msg': '该手机号未绑定学生信息',
                'data': None
            }

        # 获取班级信息
        class_info = db.query(ZzBj).filter(ZzBj.id == student.bj_id).first()
        if not class_info:
            return {
                'success': False,
                'msg': '未找到班级信息',
                'data': None
            }

        sys_info = db.query(ZzSys).first()
        if not sys_info:
            return {
                'success': False,
                'msg': '未找到系统信息',
                'data': None
            }

        has_openid = bool(student.xs_wx_openid)
        payload = {
            'xs_xh': student.xh,
            'xs_bj_id': student.bj_id,
            'xs_id': student.id,
            # ⭐ 头像上传需要：身份由 token 直接推导，前端不传身份证号
            'sfzh': student.sfzh,
            'user_type': 'vocational_student',
            'xs_xm': student.xm,
        }
        # 生成token
        token = create_token({**payload})
        refresh_token = create_refresh_token(payload)

        # 构建返回数据
        response_data = {
            'xs_xh': student.xh,
            'xs_xm': student.xm,
            'xs_dh': student.xsdh,
            'xs_sfzh': student.sfzh,
            'xs_bj_id': student.bj_id,
            'nickName': student.xs_wx_nickname,
            'avatarUrl': student.xs_wx_headimgurl,
            'token': token,
            'refresh_token': refresh_token,
            'class_name': class_info.mc if class_info else '',  # 添加班级名称
            'bind': has_openid,
            'current_term': calculate_current_term(sys_info.zz_dq_nd, sys_info.zz_dq_xq, student.nd, '09'),
            'xs_xjzt': student.xjzt,
            'masked_phone': masked_phone,
        }

        # 7 天手机号缓存写入
        cache_written = False
        openid_bound = False
        try:
            if request.login_code:
                openid = _phone_cache.resolve_openid_by_login_code(request.login_code)
                if openid:
                    # 首次手机号登录：把 openid 绑到该学生，供后续 openid 快捷登录使用
                    openid_bound = _bind_openid_to_student(db, student, openid)
                    if request.subject:
                        cache_written = _phone_cache.write_phone_cache(
                            openid=openid,
                            pure_phone=pure_phone,
                            role='self',
                            subject=request.subject,
                            extra={
                                'masked_phone': masked_phone,
                                'sfzh': student.sfzh or '',
                                'xm': student.xm,
                                'xs_id': student.id,
                                'bj_id': student.bj_id,
                            },
                        )
        except Exception as _e:
            logging.warning(f"[phone_cache] vocational_login.phone_quick_login 写缓存失败: {_e}")

        response_data['cache_written'] = cache_written
        response_data['openid_bound'] = openid_bound

        return {
            'success': True,
            'msg': '登录成功',
            'data': response_data
        }

    except Exception as e:
        logging.error(f"手机号快捷登录失败: {str(e)}")
        return {
            'success': False,
            'msg': f'登录失败: {str(e)}',
            'data': None
        }
