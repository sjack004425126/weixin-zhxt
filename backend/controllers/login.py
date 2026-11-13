from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
from models.models import Student, Class, lw_sys
from init.dependencies import (
    get_redis, get_db,
    RedisDep, DatabaseDep, RedisManagerDep
)
from controllers.vocational_tuition import get_term_info  # 统一学期计算函数
from common.auth import create_token, create_refresh_token, verify_refresh_token
import hashlib
import time
import jwt
from utils.wx_utils import WxUtils
from utils.sms import SMSTool
import random
import re
import logging
from common.auth import verify_token_and_get_payload, verify_token_only

# 创建路由器
router = APIRouter(prefix="/login", tags=["用户登录"])

# 请求模型
class VerifyUserRequest(BaseModel):
    username: str
    password: str
    code: str
    version: str = None

class QuickLoginRequest(BaseModel):
    code: str



# 用户名和密码登录，并返回用户对象。
@router.post('/login_by_username_and_password')
async def login_by_username_and_password(verify_request: VerifyUserRequest,db: Session = DatabaseDep):
    """验证用户登录"""
    try:
        username = verify_request.username
        password = verify_request.password
        code = verify_request.code
        version = verify_request.version

        if not username or not password or not code:
            return {
                'success': False,
                'msg': '用户名或密码或code不能为空',
                'data': None
            }

        # 密码加密处理
        password = hashlib.md5(password.encode()).hexdigest()
        password = password[:18]  # 取18位
        password = hashlib.md5(password.encode()).hexdigest()


        # 查询用户
        # 学生可能存在重复读的情况，按id逆序取最新一条
        user_xs = db.query(Student).filter(
            Student.xs_xh == username,
            Student.xs_mm == password
        ).order_by(Student.xs_id.desc()).first()

        if not user_xs:
            return {
                'success': False,
                'msg': '用户名或密码错误',
                'data': None
            }

        # 获取openid和session_key
        wx_result_openid = WxUtils.get_openid_and_session_key(code)
        if not wx_result_openid:
            return {
                'success': False,
                'msg': '获取openid失败，请重试',
                'data': None
            }

        # 获取班级信息
        class_info = db.query(Class).filter_by(bj_id=user_xs.xs_bj_id).first()
        sys_info = db.query(lw_sys).filter_by(dq1_mc=class_info.bj_dq1_mc).first()
        sys_pc = sys_info.sys_pc
        current_term = calculate_current_term(sys_info.sys_xq1_nd, sys_info.sys_xq1_xq, user_xs.xs_nd, user_xs.xs_xqdm)
        # 获取学籍状态描述
        def get_status_desc(status_code):
            status_map = {
                "1": "在籍",
                "2": "未注册",
                "3": "转出",
                "4": "休学",
                "5": "退学",
                "6": "开除",
                "7": "毕业",
                "8": "异动中"
            }
            return status_map.get(status_code, "错误")

        has_openid = bool(user_xs.xs_wx_openid)

        # 生成token需要的保存的payload
        payload = {
            'xs_id': user_xs.xs_id,
            'xs_xh': user_xs.xs_xh,
            'dq1_mc': class_info.bj_dq1_mc,
            'bj_id': user_xs.xs_bj_id,
            'sys_pc': sys_pc,
            # ⭐ 头像上传需要：身份由 token 直接推导，前端不传身份证号
            'sfzh': user_xs.xs_sfzh,
            'user_type': 'open_student',
            'xs_xm': user_xs.xs_xm,
        }
        # 生成token
        token = create_token({**payload})
        refresh_token = create_refresh_token(payload)

        response_data = {
            'xs_xh': user_xs.xs_xh,
            'xs_xm': user_xs.xs_xm,
            'xs_cc': class_info.bj_cc,
            'xs_dh': user_xs.xs_dh,
            'nickName': user_xs.xs_wx_nickname,
            'avatarUrl': user_xs.xs_wx_headimgurl,
            'bind': has_openid,
            'token': token,
            'refresh_token': refresh_token,
            'class_name': class_info.bj_mc if class_info else '',
            'status': get_status_desc(user_xs.xs_xjzt),
            'current_term': current_term
        }

        return {
            'success': True,
            'msg': '登录成功',
            'data': response_data
        }

    except Exception as e:
        logging.error(f"登录异常: {str(e)}")
        return {
            'success': False,
            'msg': f'验证异常: {str(e)}',
            'data': None
        }

# 通过openid快速登录
@router.post('/quickLogin')
async def quickLogin_openid(login_request: QuickLoginRequest,db: Session = DatabaseDep):
    try:
        code = login_request.code
        if not code:
            return {
                'success': False,
                'msg': '缺少关键参数',
                'data': None
            }

        # 使用WxUtils获取openid
        wx_util = WxUtils()
        openidResult = wx_util.get_openid_and_session_key(code)
        if not openidResult:
            return {
                'success': False,
                'msg': '登录失败，您提供的code错误',
                'data': None
            }
        openid = openidResult.get('openid')

        # 查询学生信息
        user_xs = db.query(Student).filter_by(xs_wx_openid=openid).order_by(Student.xs_id.desc()).first()
        if not user_xs:
            return {
                'success': False,
                'msg': '当前微信还未绑定学生信息，请先使用「手机号快捷登录」或「账号密码登录」完成一次登录',
                'data': None
            }

        # 获取班级信息
        class_info = db.query(Class).filter_by(bj_id=user_xs.xs_bj_id).first()
        sys_info = db.query(lw_sys).filter_by(dq1_mc=class_info.bj_dq1_mc).first()
        current_term = calculate_current_term(sys_info.sys_xq1_nd, sys_info.sys_xq1_xq, user_xs.xs_nd, user_xs.xs_xqdm)
        # 生成token需要的保存的payload
        payload = {
            'xs_id': user_xs.xs_id,
            'xs_xh': user_xs.xs_xh,
            'dq1_mc': class_info.bj_dq1_mc,
            'bj_id': user_xs.xs_bj_id,
            'sys_pc': sys_info.sys_pc,
        }
        # 生成token
        token = create_token({**payload})
        refresh_token = create_refresh_token(payload)
        has_openid = bool(user_xs.xs_wx_openid)

        # 获取学籍状态描述
        def get_status_desc(status_code):
            status_map = {
                "1": "在籍",
                "2": "未注册",
                "3": "转出",
                "4": "休学",
                "5": "退学",
                "6": "开除",
                "7": "毕业",
                "8": "异动中"
            }
            return status_map.get(status_code, "错误")

        # 构建返回数据
        response_data = {
            'xs_xh': user_xs.xs_xh,
            'xs_xm': user_xs.xs_xm,
            'xs_cc': class_info.bj_cc,
            'xs_dh': user_xs.xs_dh,
            'xs_bj_id': user_xs.xs_bj_id,
            'nickName': user_xs.xs_wx_nickname,
            'avatarUrl': user_xs.xs_wx_headimgurl,
            'token': token,
            'refresh_token': refresh_token,
            'class_name': class_info.bj_mc if class_info else '',
            'status': get_status_desc(user_xs.xs_xjzt),
            'bind': has_openid,
            'current_term': current_term
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



# 发送学生验证码
@router.get('/xwyy_get_phone_code')
async def xwyy_get_phone_code(phone: str,db: Session = DatabaseDep,redis_client = RedisDep,current_user: dict = Depends(verify_token_and_get_payload)):
    try:
        # 验证手机号格式
        if not phone or not re.match(r'^1[3-9]\d{9}$', phone):
            return {
                'success': False,
                'msg': '无效的手机号码格式',
                'data': None
            }

        # user = db.query(Student).filter_by(xs_dh=phone,xs_xh=current_user.get('xs_xh')).first()
        # if not user:
        #     return {
        #         'success': False,
        #         'msg': '您的电话和系统中注册的电话不一致，无法申请退费，请联系班主任',
        #         'data': None
        #     }
        

        # 生成6位随机验证码
        verify_code = ''.join(random.choices('0123456789', k=6))

        # 存储验证码到Redis，设置5分钟过期
        redis_key = f"zhpt:xwyy_verify_code:{phone}"
        redis_client.setex(redis_key, 300, verify_code)  # 300秒 = 5分钟

        # 发送验证码短信
        sms_tool = SMSTool()
        result = sms_tool.send_verify_sms(phone, verify_code)
        if result['success']:
            return {
                'success': True,
                'msg': '验证码已发送',
                'data': None
            }
        else:
            return {
                'success': False,
                'msg': f'发送验证码失败: {result["msg"]}',
                'data': None
            }
    except Exception as e:
        return {
            'success': False,
            'msg': f'发送验证码失败: {str(e)}',
            'data': None
        }
    


# 计算当前学期（统一委托给 get_term_info，保持参数顺序不变）
def calculate_current_term(sys_nd, sys_xq, xs_nd, xs_xq):
    """计算学生当前学期
    
    Args:
        sys_nd (str): 系统当前年度
        sys_xq (str): 系统当前学期（'03' 或 '09'）
        xs_nd (str): 学生入学年度
        xs_xq (str): 学生入学学期
        
    Returns:
        int: 当前学期数（最小为 1，上限不限制）
    """
    return get_term_info(xs_nd, sys_nd, sys_xq)


# 手机号快捷登录（普通学生）
class PhoneQuickLoginRequest(BaseModel):
    code: str
    # 兼容 7 天手机号缓存：可选字段
    login_code: Optional[str] = None
    subject: Optional[str] = None  # 如 student_info / user_center


def _bind_openid_to_student(db: Session, user_xs: Student, openid: str) -> bool:
    """把 openid 绑定到学生记录（供后续 openid 快捷登录使用）。

    规则（与 /bind_openid/zs 保持一致）：
      - 已有 openid 且非空 → 不覆盖（返回 False）
      - openid 已被别的学生占用 → 踢掉旧绑定，再写入
      - 同时维护 xs_wx_openid_hash（隐私合规）

    Returns: 是否成功写入绑定。
    """
    if not openid:
        return False
    try:
        from utils.hash_util import hash_openid

        current = user_xs.xs_wx_openid
        if current and str(current).strip():
            # 已绑定：不覆盖，避免抢占他人绑定
            return False

        kicked = (
            db.query(Student)
            .filter(Student.xs_wx_openid == openid, Student.xs_id != user_xs.xs_id)
            .update(
                {"xs_wx_openid": None, "xs_wx_openid_hash": None},
                synchronize_session=False,
            )
        )
        if kicked:
            logging.warning(f"[bind_openid] 踢掉旧绑定 openid={openid} count={kicked}")

        user_xs.xs_wx_openid = openid
        user_xs.xs_wx_openid_hash = hash_openid(openid)
        db.commit()
        return True
    except Exception as e:
        logging.warning(f"[bind_openid] 绑定 openid 失败: {e}")
        db.rollback()
        return False


@router.post('/phone_quick_login')
async def phone_quick_login(request: PhoneQuickLoginRequest, db: Session = DatabaseDep):
    """通过微信获取手机号，然后匹配学生信息进行登录"""
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

        # 查询学生表，通过手机号匹配
        # 学生可能存在重复读的情况（同一电话对应多条），按id逆序取最新一条
        user_xs = db.query(Student).filter(Student.xs_dh == phone_number).order_by(Student.xs_id.desc()).first()

        if not user_xs:
            return {
                'success': False,
                'msg': '该手机号未绑定学生信息',
                'data': None
            }

        # 获取班级信息
        class_info = db.query(Class).filter(Class.bj_id == user_xs.xs_bj_id).first()
        if not class_info:
            return {
                'success': False,
                'msg': '未找到班级信息',
                'data': None
            }

        sys_info = db.query(lw_sys).filter(lw_sys.dq1_mc == class_info.bj_dq1_mc).first()
        if not sys_info:
            return {
                'success': False,
                'msg': '未找到系统信息',
                'data': None
            }

        sys_pc = sys_info.sys_pc
        current_term = calculate_current_term(sys_info.sys_xq1_nd, sys_info.sys_xq1_xq, user_xs.xs_nd, user_xs.xs_xqdm)

        # 获取学籍状态描述
        def get_status_desc(status_code):
            status_map = {
                "1": "在籍",
                "2": "未注册",
                "3": "转出",
                "4": "休学",
                "5": "退学",
                "6": "开除",
                "7": "毕业",
                "8": "异动中"
            }
            return status_map.get(status_code, "错误")

        has_openid = bool(user_xs.xs_wx_openid)

        # 生成token需要的保存的payload
        payload = {
            'xs_id': user_xs.xs_id,
            'xs_xh': user_xs.xs_xh,
            'dq1_mc': class_info.bj_dq1_mc,
            'bj_id': user_xs.xs_bj_id,
            'sys_pc': sys_pc,
            # ⭐ 头像上传需要：身份由 token 直接推导，前端不传身份证号
            'sfzh': user_xs.xs_sfzh,
            'user_type': 'open_student',
            'xs_xm': user_xs.xs_xm,
        }
        # 生成token
        token = create_token({**payload})
        refresh_token = create_refresh_token(payload)

        response_data = {
            'xs_xh': user_xs.xs_xh,
            'xs_xm': user_xs.xs_xm,
            'xs_cc': class_info.bj_cc,
            'xs_dh': user_xs.xs_dh,
            'nickName': user_xs.xs_wx_nickname,
            'avatarUrl': user_xs.xs_wx_headimgurl,
            'bind': has_openid,
            'token': token,
            'refresh_token': refresh_token,
            'class_name': class_info.bj_mc if class_info else '',
            'status': get_status_desc(user_xs.xs_xjzt),
            'current_term': current_term,
            # 7 天手机号缓存：返回手机号供前端展示
            'masked_phone': masked_phone,
        }

        # 7 天手机号缓存写入（兼容旧前端：未传 login_code 时仅返回，不写）
        cache_written = False
        openid_bound = False
        try:
            if request.login_code:
                openid = _phone_cache.resolve_openid_by_login_code(request.login_code)
                if openid:
                    # 首次手机号登录：把 openid 绑到该学生，供后续 openid 快捷登录使用
                    openid_bound = _bind_openid_to_student(db, user_xs, openid)
                    if request.subject:
                        cache_written = _phone_cache.write_phone_cache(
                            openid=openid,
                            pure_phone=pure_phone,
                            role='self',
                            subject=request.subject,
                            extra={
                                'masked_phone': masked_phone,
                                'sfzh': getattr(user_xs, 'xs_sfzh', None) or '',
                                'xm': user_xs.xs_xm,
                                'xs_id': user_xs.xs_id,
                                'bj_id': user_xs.xs_bj_id,
                            },
                        )
        except Exception as _e:
            logging.warning(f"[phone_cache] phone_quick_login 写缓存失败: {_e}")

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



# ============== 统一 Token 刷新接口 ==============

class RefreshTokenRequest(BaseModel):
    refresh_token: str


@router.post('/refresh_token')
async def refresh_token_endpoint(req: RefreshTokenRequest):
    """用 refresh_token 换取新的 access_token 和 refresh_token"""
    try:
        payload = verify_refresh_token(req.refresh_token)
        new_access_token = create_token({**payload})
        new_refresh_token = create_refresh_token(payload)
        return {
            'success': True,
            'msg': 'ok',
            'data': {
                'token': new_access_token,
                'refresh_token': new_refresh_token
            }
        }
    except jwt.ExpiredSignatureError:
        return {
            'success': False,
            'msg': 'refresh_token 已过期，请重新登录',
            'data': None
        }
    except Exception as e:
        return {
            'success': False,
            'msg': f'刷新失败: {str(e)}',
            'data': None
        }
