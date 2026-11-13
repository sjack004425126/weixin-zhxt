from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from models.models import Student, Class, ZzBjZd, ZzBjZdgr, ZzXs, ZzBj, ZzSys,ZzBmxsZzmm, WxPayinfo, ZzTeachingTask, ZzCourseSelection, ZzStCourse, ZzStCourseSelection,ZzBmxsBdzy,ZzBmxsJzdlx,ZzBmxsJzgx,ZzBmxsZsdx,ZzXsZd,Teacher, LwFeatureSwitch
from init.dependencies import (
    get_redis, get_db,
    RedisDep, DatabaseDep, RedisManagerDep
)
from common.auth import verify_token_and_get_payload, verify_token_only
from datetime import datetime
from sqlalchemy import text
import random
from utils.wx_pay import WxPayUtil
import json
from utils.system_config import SystemConfig
import logging
import time
from utils.wx_utils import WxUtils
import requests

# 创建logger实例
logger = logging.getLogger(__name__)
from services.course_selection_service import CourseSelectionService
from utils.redis_utils import RedisLock, CourseCache

# 创建路由器
router = APIRouter(prefix="/vocational_info", tags=["职业教育信息"])

# 请求模型

class CancelCourseRequest(BaseModel):
    course_id: int


# 检查功能开关是否开启。返回 (is_enabled, fail_response)。
# fail_response 为 None 表示开关开启，无需拦截；否则调用方直接 return fail_response。
def _check_feature_switch(db: Session, code: str):
    """校验 lw_feature_switch 中的功能开关。

    - 记录不存在 → 默认开启（与 feature_switch.check 接口语义一致，避免误锁未配置开关）
    - is_enabled=1  → 开启，放行
    - is_enabled=0  → 关闭，返回 success=False 响应，由调用方直接 return
    """
    sw = db.query(LwFeatureSwitch).filter(LwFeatureSwitch.code == code).first()
    if not sw or sw.is_enabled == 1:
        return True, None
    tip = sw.tip_message or '该功能已关闭，请联系管理员开启'
    return False, {'success': False, 'message': tip, 'data': None}



# 获取学期描述
def get_term_info(s_nd,sys_nd,sys_xq):
    if sys_nd -s_nd ==0:
        if sys_xq == '03':
            term_info = '第一学期'
    if sys_nd -s_nd ==1:
        if sys_xq == '03':
            term_info = '第二学期'
        else:
            term_info = '第三学期'
    if sys_nd -s_nd ==2:
        if sys_xq == '03':
            term_info = '第四学期'
        else:
            term_info = '第五学期'
    if sys_nd -s_nd ==3:
        if sys_xq == '03':
            term_info = '第六学期'
    return term_info


# 获取用户当前学期的缴费数据
@router.get('/paymentInfo')
async def get_payment_info(current_user: dict = Depends(verify_token_and_get_payload),db: Session = DatabaseDep):
    try:
        # 获取学生信息
        student = db.query(ZzXs).filter_by(id=current_user.get('xs_id')).first()
        if not student:
            return {
                'success': False,
                'msg': '未找到学生信息',
                'data': None
            }

        # 获取班级信息
        class_info = db.query(ZzBj).filter_by(id=student.bj_id).first()
        if not class_info:
            return {
                'success': False,
                'msg': '未找到班级信息',
                'data': None
            }

        # 获取系统配置信息
        sys_info = db.query(ZzSys).first()
        if not sys_info:
            return {
                'success': False,
                'msg': '未找到系统配置信息',
                'data': None
            }
        # 获取当前学期信息
        zz_sys = db.query(ZzSys).first()
        s_xq_des = get_term_info(student.nd,sys_info.zz_dq_nd,sys_info.zz_dq_xq)
        s_nd = sys_info.zz_dq_nd
        s_xq = sys_info.zz_dq_xq


        # 初始化变量
        s_zsf = 0  # 住宿费
        s_sf = 0   # 书本费
        isjdlk = 0  # 是否建档立卡


        # 查询个人账单
        personal_bill = db.query(ZzBjZdgr).filter_by(
            xsxh=student.xh,
            nd=s_nd,
            xq=s_xq
        ).first()

        # 查询班级账单
        class_bill = db.query(ZzBjZd).filter_by(
            bjid=student.bj_id,
            nd=s_nd,
            xq=s_xq
        ).first()
        # 判断是否建档立卡
        isjdlk = class_bill.isjdlk

        if not personal_bill:
            if not class_bill:
                return {
                    'success': False,
                    'msg': '未找到班级账单和个人账单信息',
                    'data': None
                }
            else:
                if class_bill.isopen == 0:
                    return {
                        'success': False,
                        'msg': '班级账单还未开启，暂时无法缴费',
                        'data': None
                    }
                else:
                    # 判断是否外出实习
                    if class_bill.wcsx == 1:
                        return {
                            'success': False,
                            'msg': '外出实习学期，无需缴费',
                            'data': None
                        }
                    else:
                        s_zsf = class_bill.zsf / 100
                        s_sf = class_bill.sf / 100
        else:
            if not class_bill:
                return {
                    'success': False,
                    'msg': '有个人账单，但未找到班级账单信息',
                    'data': None
                }
            else:
                if class_bill.isopen == 0:
                    return {
                        'success': False,
                        'msg': '班级账单还未开启，暂时无法缴费',
                        'data': None
                    }
                else:
                    # 判断是否建档立卡
                    isjdlk = class_bill.isjdlk
                    if isjdlk == 1:
                        s_zsf = personal_bill.zsf / 100
                        s_sf = personal_bill.sf / 100
        # 处理日期判断
        now = datetime.now()
        if now < zz_sys.zz_lsjfksrq:
            return {
                'success': False,
                'msg': '老生缴费还未开启',
                'data': None
            }

        if now > zz_sys.zz_lsjfjzrq:
            return {
                'success': False,
                'msg': '老生缴费已经结束',
                'data': None
            }
        if class_bill.isjdlk == 0 and student.sfjdlk == 1:
            return {
                'success': False,
                'msg': '非建档立卡班级的建档立卡学生无需缴费',
                'data': None
            }
        if not class_bill:
            s_zsf = 0
        
        # 是否有未支付订单
        unpaid_order = db.execute(text(
            "SELECT o_money, o_order_no,o_zsf,o_sf,o_status FROM wx_payinfo WHERE o_xh=:xh AND o_tk_status=0 AND o_close=0 AND o_nd=:nd AND o_xq=:xq"
        ), {
            'xh': student.xh,
            'nd': zz_sys.zz_dq_nd,
            'xq': zz_sys.zz_dq_xq
        }).fetchone()
        if unpaid_order:
            if unpaid_order.o_status == 1:
                return {
                    'success': False,
                    'msg': '您已缴清所有费用，无需重复缴费',
                    'data': None
                }
            elif unpaid_order.o_status == 0:
                return {
                    'success': True,
                    'msg': '获得历史订单成功',
                    'data': {
                        'order_no': unpaid_order.o_order_no,
                        'total_fee': unpaid_order.o_money,
                        'dorm_fee': unpaid_order.o_zsf,
                        'book_fee': unpaid_order.o_sf,
                        's_xq_des': s_xq_des
                    }
                }
            else:
                return {
                    'success': False,
                    'msg': '未支付订单状态错误',
                    'data': None
                }
        # 计算已交费住宿用以分为单位不用除以100
        paid_zsf = db.execute(text(
            "SELECT COALESCE(SUM(o_zsf), 0) FROM wx_payinfo WHERE o_xh=:xh AND o_status=1 AND o_tk_status=0 AND o_close=0 AND o_nd=:nd AND o_xq=:xq"
        ), {
            'xh': student.xh,
            'nd': zz_sys.zz_dq_nd,
            'xq': zz_sys.zz_dq_xq
        }).scalar()
        # 计算已交费书本费以分为单位不用除以100
        paid_sf = db.execute(text(
            "SELECT COALESCE(SUM(o_sf), 0) FROM wx_payinfo WHERE o_xh=:xh AND o_status=1 AND o_tk_status=0 AND o_close=0 AND o_nd=:nd AND o_xq=:xq"
        ), {
            'xh': student.xh,
            'nd': zz_sys.zz_dq_nd,
            'xq': zz_sys.zz_dq_xq
        }).scalar()
        # 计算总费用
        total_fee = s_zsf + s_sf
        o_body = "黔东南中等职业技术学校-学杂费-老生JSAPIX"
        o_order_no = f"{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(1000, 9999)}"
        check_order_no = db.query(WxPayinfo).filter_by(o_order_no=o_order_no).first()
        if check_order_no:
            return {
                'success': False,
                'msg': '订单号已存在',
                'data': None
            }
        # 创建订单
        order = WxPayinfo(
            o_xm=student.xm,
            o_xh=student.xh,
            o_sfzh=student.sfzh,
            o_sj=student.xsdh,
            o_body=o_body,
            o_money=total_fee,
            o_zsf=s_zsf,
            o_sf=s_sf,
            o_paytype='weixin',
            o_type=5,
            o_status=0,
            o_tk_status=0,
            o_close=0,
            o_xx_status=0,
            o_order_no=o_order_no,
            o_addtime=now,
            o_nd=sys_info.zz_dq_nd,
            o_xq=sys_info.zz_dq_xq
        )
        db.add(order)
        db.flush()
        return {
            'success': True,
            'msg': '生成订单成功',
            'data': {
                'order_no': order.o_order_no,
                'total_fee': total_fee,
                'dorm_fee': s_zsf,
                'book_fee': s_sf,
                's_xq_des': s_xq_des
            }
        }
    
    except Exception as e:
        return {
            'success': False,
            'msg': f'获取缴费信息失败: {str(e)}',
            'data': None
        }





# 生成老生学费预交费信息，用于老生缴费
@router.get('/prePayment')
async def create_pre_payment(order_no: str,openid: str = None,_: dict = Depends(verify_token_only),db: Session = DatabaseDep):
    """生成学费预交费信息
    
    Args:
        order_no (str): 订单号
        
    Returns:
        json: {
            "code": 0,
            "msg": "success",
            "data": {
                "order_no": "订单号",
                "total_fee": "总费用",
                "dorm_fee": "住宿费",
                "book_fee": "书本费",
                "term_desc": "学期描述"
            }
        }
    """
    try:
        if not order_no:
            raise HTTPException(status_code=400, detail={
                'code': 1,
                'msg': '订单号不能为空',
                'data': None
            })

        # 获取订单信息
        order = db.query(WxPayinfo).filter_by(o_order_no=order_no).first()
        if not order:
            return {
                'code': 1,
                'msg': '未找到订单信息',
                'data': None
            }

        # 获取学生信息
        student = db.query(ZzXs).filter_by(xh=order.o_xh).first()
        if not student:
            return {
                'code': 1,
                'msg': '未找到学生信息',
                'data': None
            }

        # 获取系统配置信息
        sys_config = db.query(ZzSys).first()
        if not sys_config:
            return {
                'code': 1,
                'msg': '未找到系统配置信息',
                'data': None
            }

        # 获取学期描述
        s_xq_des = get_term_info(student.nd, sys_config.zz_dq_nd, sys_config.zz_dq_xq)

        # 检查订单状态
        if order.o_status == 1:
            return {
                'code': 1,
                'msg': '该订单已支付，无需重复缴费',
                'data': None
            }
        elif order.o_status != 0:
            return {
                'code': 1,
                'msg': '订单状态异常',
                'data': None
            }

        # 检查缴费时间
        now = datetime.now()
        if not (sys_config.zz_lsjfksrq <= now <= sys_config.zz_lsjfjzrq):
            if now < sys_config.zz_lsjfksrq:
                return {
                    'code': 1,
                    'msg': '老生缴费还未开启',
                    'data': None
                }
            else:
                return {
                    'code': 1,
                    'msg': '老生缴费已经结束',
                    'data': None
                }

        

        # 生成微信服务器的支付订单，并返回支付参数
        wx_pay = WxPayUtil()
        pay_result = wx_pay.create_pay_info(
            openid=openid,
            out_trade_no=order.o_order_no,
            total_fee=order.o_money*100,  #暂时测试用1元来支付
            # total_fee=1,
            description=f'{student.xm}缴纳{s_xq_des}学费'
        )


        if pay_result and pay_result.get('code') == 0:
            response_data = pay_result.get('data', {})
            response_data['orderNo'] = order_no
            return {
                'code': 0,
                'msg': '支付参数生成成功',
                'data': response_data
            }
        else:
            error_msg = pay_result.get('msg', '支付参数生成失败') if pay_result else '支付参数生成失败'
            # 如果是订单号重复的错误，尝试查询原订单状态
            if 'INVALID_REQUEST' in error_msg and '商户订单号重复' in error_msg:
                # 查询微信支付订单状态
                query_result = wx_pay.query_order(out_trade_no=order_no)
                if query_result and query_result.get('code') == 0:
                    # 更新本地订单状态
                    print("查询微信支付订单状态：",query_result)

            return {
                'code': 1,
                'msg': error_msg,
                'data': None
            }
    except Exception as e:
        logging.error(f"生成预交费信息失败: {str(e)}")
        raise HTTPException(status_code=500, detail={
            'code': 1,
            'msg': f'生成预交费信息失败: {str(e)}',
            'data': None
        })



# 更新订单支付状态
@router.get('/updateOrderStatus')
async def update_order_status(order_no: str,_: dict = Depends(verify_token_only),db: Session = DatabaseDep):
    """更新订单支付状态
    
    Args:
        order_no (str): 订单号
        
    Returns:
        json: {
            "code": 0,
            "msg": "success",
            "data": {
                "order_no": "订单号",
                "status": "订单状态",
                "pay_time": "支付时间"
            }
        }
    """
    try:
        if not order_no:
            raise HTTPException(status_code=400, detail={
                'code': 1,
                'msg': '缺少必要参数',
                'data': None
            })
            
        
        # 商户订单号查询订单支付结果
        wx_pay = WxPayUtil()
        query_result = wx_pay.query_order(out_trade_no=order_no)
        
        # 检查查询结果
        if not query_result or 'trade_state' not in query_result:
            raise HTTPException(status_code=500, detail={
                'code': 1,
                'msg': '查询订单失败',
                'data': None
            })
            
        # 检查支付状态
        if query_result['trade_state'] != 'SUCCESS':
            raise HTTPException(status_code=400, detail={
                'code': 1,
                'msg': f'订单未支付成功,当前状态: {query_result["trade_state_desc"]}',
                'data': None
            })

        # 从返回数据中提取需要的参数
        transaction_id = query_result['transaction_id']  # 微信支付订单号
        success_time = datetime.strptime(
            query_result['success_time'].replace('T', ' ').split('+')[0],
            '%Y-%m-%d %H:%M:%S'
        )  # 支付成功时间
        
        try:
            # 更新本地订单状态信息
            order = db.query(WxPayinfo).filter_by(o_order_no=order_no).first()
            if order:
                order.o_status = 1  # 更新为已支付
                order.o_trade_no = transaction_id
                order.o_paytime = success_time
                db.commit()

                return {
                    'code': 0,
                    'msg': '订单支付成功并已更新',
                    'data': {
                        'order_no': order_no,
                        'transaction_id': transaction_id,
                        'pay_time': success_time.strftime('%Y-%m-%d %H:%M:%S')
                    }
                }
            else:
                raise HTTPException(status_code=404, detail={
                    'code': 1,
                    'msg': '本地订单不存在',
                    'data': None
                })

        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail={
                'code': 1,
                'msg': f'更新订单状态失败: {str(e)}',
                'data': None
            })
            
    except Exception as e:
        raise HTTPException(status_code=500, detail={
            'code': 1,
            'msg': f'更新订单状态失败: {str(e)}',
            'data': None
        })


# 获取社团课列表
@router.get('/get_st_courses')
async def get_st_courses(keyword: str = '',current_user: dict = Depends(verify_token_and_get_payload),db: Session = DatabaseDep):
    try:
        # 获取系统配置信息
        sys_info = db.query(ZzSys).first()
        if not sys_info:
            return {
                'success': False,
                'msg': '未找到系统配置信息',
                'data': None
            }
            
        # 获取当前学年学期
        current_year = sys_info.zz_dq_nd
        current_semester = sys_info.zz_dq_xq
        

        # 获取学生信息
        student = db.query(ZzXs).filter_by(id=current_user.get('xs_id')).first()
        if not student:
            return {
                'success': False,
                'msg': '未找到学生信息',
                'data': None
            }
        # 构建查询条件
        where_conditions = ["c.status = 1"]
        query_params = {}
        
        # 添加关键词搜索条件
        if keyword:
            where_conditions.append("(c.course_name LIKE :keyword OR c.course_code LIKE :keyword)")
            query_params['keyword'] = f'%{keyword}%'
            
        # 查询社团课列表（含多教师）
        query = text(f"""
            SELECT
                c.id as course_id,
                c.course_code,
                c.course_name,
                c.credit,
                c.hours,
                c.max_students,
                c.current_students,
                c.classroom,
                c.description,
                c.category,
                c.status as course_status,
                ct.teacher_id,
                oa.t_xm as teacher_name,
                oa.t_zc as professional_title
            FROM zz_st_course c
            LEFT JOIN zz_st_course_teacher ct ON ct.course_id = c.id
            LEFT JOIN oa_t oa ON oa.t_id = ct.teacher_id
            WHERE {' AND '.join(where_conditions)}
            ORDER BY c.id, ct.id
        """)

        result = db.execute(query, query_params)

        # 按课程聚合多教师
        course_map = {}
        for row in result:
            cid = row.course_id
            if cid not in course_map:
                course_map[cid] = {
                    'course_id': cid,
                    'course_code': row.course_code,
                    'course_name': row.course_name,
                    'credit': float(row.credit),
                    'hours': row.hours,
                    'max_students': row.max_students,
                    'current_students': row.current_students,
                    'classroom': row.classroom,
                    'description': row.description,
                    'course_status': row.course_status,
                    'available_slots': row.max_students - row.current_students,
                    'category': row.category,
                    # 教师信息（多教师）
                    'teacher_ids': [],
                    '_teachers': {},  # {teacher_id: {name, title}}
                }
            entry = course_map[cid]
            if row.teacher_id is not None and row.teacher_id not in entry['teacher_ids']:
                entry['teacher_ids'].append(row.teacher_id)
            # teacher_id 为空时用临时 key，避免丢数据
            key = row.teacher_id if row.teacher_id is not None else f'_none_{len(entry["teacher_ids"])}'
            if key not in entry['_teachers']:
                entry['_teachers'][key] = {'name': row.teacher_name or '', 'title': row.professional_title or ''}

        courses = []
        for c in course_map.values():
            # teacher_name：仅姓名，逗号拼接
            names = [t['name'] for t in c['_teachers'].values() if t['name']]
            c['teacher_name'] = '、'.join(names)
            # professional_title：取第一位（兼容旧字段）
            titles = [t['title'] for t in c['_teachers'].values() if t['title']]
            c['professional_title'] = titles[0] if titles else ''
            # teachers 数组：{name, title}，按 teacher_ids 顺序
            c['teachers'] = [
                c['_teachers'][tid] for tid in c['teacher_ids'] if tid in c['_teachers']
            ]
            # 补充 teacher_id 为空的教师
            for k, v in c['_teachers'].items():
                if str(k).startswith('_none_') and v not in c['teachers']:
                    c['teachers'].append(v)
            c.pop('_teachers', None)
            courses.append(c)
            
        # 查询已选课程（含多教师）
        selected_courses_query = text("""
            SELECT
                c.id as course_id,
                c.course_name,
                ct.teacher_id,
                oa.t_xm as teacher_name,
                oa.t_zc as professional_title,
                c.classroom,
                c.description
            FROM zz_st_course_selection s
            LEFT JOIN zz_st_course c ON s.course_id = c.id
            LEFT JOIN zz_st_course_teacher ct ON ct.course_id = c.id
            LEFT JOIN oa_t oa ON oa.t_id = ct.teacher_id
            WHERE s.student_id = :student_id
            AND s.year = :year
            AND s.semester = :semester
            ORDER BY c.id, ct.id
        """)

        selected_courses_result = db.execute(selected_courses_query, {
            'student_id': student.id,
            'year': current_year,
            'semester': current_semester
        })

        selected_map = {}

        for row in selected_courses_result:
            cid = row.course_id
            if cid not in selected_map:
                selected_map[cid] = {
                    'course_id': cid,
                    'course_name': row.course_name,
                    'classroom': row.classroom,
                    'description': row.description,
                    'teacher_ids': [],
                    '_teachers': {},  # {teacher_id: {name, title}}
                }
            entry = selected_map[cid]
            key = row.teacher_id if row.teacher_id is not None else f'_none_{len(entry["teacher_ids"])}'
            if key not in entry['_teachers']:
                entry['_teachers'][key] = {'name': row.teacher_name or '', 'title': row.professional_title or ''}
            if row.teacher_id is not None and row.teacher_id not in entry['teacher_ids']:
                entry['teacher_ids'].append(row.teacher_id)

        selected_courses = []
        for sc in selected_map.values():
            # teacher_name：仅姓名，逗号拼接
            names = [t['name'] for t in sc['_teachers'].values() if t['name']]
            sc['teacher_name'] = '、'.join(names)
            # teachers 数组：{name, title}
            sc['teachers'] = [
                sc['_teachers'][tid] for tid in sc['teacher_ids'] if tid in sc['_teachers']
            ]
            for k, v in sc['_teachers'].items():
                if str(k).startswith('_none_') and v not in sc['teachers']:
                    sc['teachers'].append(v)
            sc.pop('_teachers', None)
            sc.pop('teacher_ids', None)
            selected_courses.append(sc)
            
        return {
            'success': True,
            'msg': '获取成功',
            'data': {
                'courses': courses,
                'selected_courses': selected_courses
            }
        }

    except Exception as e:
        return {
            'success': False,
            'msg': f'获取社团课列表失败：{str(e)}',
            'data': None
        }


# 学生选课（优化版本：Redis分布式锁 + 学生级限流 + 优先缓存）
@router.get('/select_st_course')
async def select_st_course(course_id: int, current_user: dict = Depends(verify_token_and_get_payload),
                          db: Session = DatabaseDep, redis_client = RedisDep):
    """学生选社团课"""
    try:
        if not course_id:
            return {
                'success': False,
                'message': '缺少必要参数',
                'data': None
            }

        # ========== 功能开关校验：st_club_signup 关闭时直接拒绝 ==========
        ok, fail_resp = _check_feature_switch(db, 'st_club_signup')
        if not ok:
            return fail_resp

        # 获取系统配置信息
        sys_info = db.query(ZzSys).first()
        if not sys_info:
            return {
                'success': False,
                'message': '未找到系统配置信息',
                'data': None
            }

        # 获取当前学年学期
        current_year = sys_info.zz_dq_nd
        current_semester = sys_info.zz_dq_xq

        # 获取学生ID
        student_id = current_user.get('xs_id')
        if not student_id:
            return {
                'success': False,
                'message': '用户信息异常',
                'data': None
            }

        # ========== 学生级限流（防恶意频繁操作） ==========
        # 规则：10 秒内最多 3 次选课请求
        if redis_client:
            try:
                rate_key = f"rate:select_st_course:{student_id}"
                current_count = redis_client.incr(rate_key)
                if current_count == 1:
                    redis_client.expire(rate_key, 10)
                if current_count > 3:
                    ttl = redis_client.ttl(rate_key)
                    return {
                        'success': False,
                        'message': f'操作过于频繁，请 {ttl if ttl > 0 else 10} 秒后再试',
                        'data': None
                    }
            except Exception as e:
                logger.warning(f"学生限流检查异常，继续执行: {str(e)}")

        # ========== Redis 快速预检：是否已选（避免每次都查数据库） ==========
        selected_set_key = f"st_course:selected:{student_id}:{current_year}:{current_semester}"
        if redis_client:
            try:
                if redis_client.sismember(selected_set_key, str(course_id)):
                    return {'success': False, 'message': '您已经选过这门课程', 'data': None}
            except Exception as e:
                logger.warning(f"Redis 已选预检异常，继续执行: {str(e)}")

        # ========== Redis 分布式锁 ==========
        redis_lock = None
        use_redis_lock = False
        lock_key = f"course_select_{course_id}"

        try:
            if redis_client:
                redis_lock = RedisLock(redis_client, lock_key, timeout=10, retry_delay=0.1)
                if redis_lock.acquire_sync(max_retries=10):  # 最多等待1秒
                    use_redis_lock = True
                else:
                    logger.warning(f"获取Redis锁失败，降级到数据库锁: {lock_key}")
        except Exception as e:
            logger.warning(f"Redis锁异常，降级到数据库锁: {str(e)}")

        try:
            # 在锁保护下执行选课逻辑
            # 获取课程信息（使用数据库行锁）
            course = db.query(ZzStCourse).filter(
                ZzStCourse.id == course_id
            ).with_for_update().first()

            if not course:
                return {
                    'success': False,
                    'message': '课程不存在',
                    'data': None
                }

            # 检查课程状态
            if course.status != 1:
                return {
                    'success': False,
                    'message': '课程已禁用',
                    'data': None
                }

            # 检查是否已经选过这门课（硬查找：表里只有已选记录，无 status 字段）
            existing_selection = db.query(ZzStCourseSelection).filter_by(
                student_id=student_id,
                course_id=course_id,
                year=current_year,
                semester=current_semester
            ).first()

            if existing_selection:
                # 同步 Redis 已选集合，防止下次漏判
                if redis_client:
                    try:
                        redis_client.sadd(selected_set_key, str(course_id))
                        redis_client.expire(selected_set_key, 86400 * 30)
                    except Exception:
                        pass
                return {
                    'success': False,
                    'message': '您已经选过这门课程',
                    'data': None
                }

            # 在锁定状态下检查课程名额（关键：防止超卖）
            if course.current_students >= course.max_students:
                return {
                    'success': False,
                    'message': '课程已满，选课失败',
                    'data': None
                }

            # 创建选课记录（硬插入，不再有 status=0 软删除状态）
            new_selection = ZzStCourseSelection(
                student_id=student_id,
                course_id=course_id,
                year=current_year,
                semester=current_semester,
                select_time=datetime.now(),
                create_time=datetime.now(),
                update_time=datetime.now()
            )
            db.add(new_selection)

            # 更新当前选课人数
            course.current_students += 1
            course.update_time = datetime.now()

            # 提交事务
            db.commit()

            # ========== 同步 Redis 缓存（写后立即可见） ==========
            if redis_client:
                try:
                    # 1. 记录学生已选课程（用于快速预检）
                    redis_client.sadd(selected_set_key, str(course_id))
                    redis_client.expire(selected_set_key, 86400 * 30)
                    # 2. 更新课程缓存中的 current_students
                    course_cache_key = f"course_info:{course_id}"
                    cached = redis_client.get(course_cache_key)
                    if cached:
                        try:
                            import json as _json
                            course_data = _json.loads(cached)
                            course_data['current_students'] = course.current_students
                            course_data['updated_at'] = datetime.now().isoformat()
                            redis_client.set(course_cache_key, _json.dumps(course_data), ex=300)
                        except Exception:
                            pass
                except Exception as e:
                    logger.warning(f"同步 Redis 缓存失败: {str(e)}")

            return {
                'success': True,
                'message': '选课成功',
                'data': {
                    'course_id': course_id,
                    'course_name': course.course_name,
                    'current_students': course.current_students,
                    'max_students': course.max_students
                }
            }

        finally:
            # 确保释放Redis锁（如果使用了）
            if use_redis_lock and redis_lock:
                try:
                    redis_lock.release_sync()
                except Exception as e:
                    logger.warning(f"释放Redis锁失败: {str(e)}")

    except Exception as e:
        db.rollback()
        # 详细的错误信息记录
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"选课接口异常: {str(e)}")
        logger.error(f"详细错误信息: {error_details}")

        return {
            'success': False,
            'message': f'选课失败：{str(e)}',
            'data': {
                'error_type': type(e).__name__,
                'error_details': str(e)
            }
        }




# 学生退选社团课（优化版本：支持Redis分布式锁）
@router.get('/cancel_st_course')
async def cancel_st_course(course_id: int, current_user: dict = Depends(verify_token_and_get_payload),
                          db: Session = DatabaseDep, redis_client = RedisDep):
    """学生退选社团课"""
    try:
        if not course_id:
            return {
                'success': False,
                'message': '缺少必要参数',
                'data': None
            }

        # ========== 功能开关校验：st_club_signup 关闭时直接拒绝 ==========
        ok, fail_resp = _check_feature_switch(db, 'st_club_signup')
        if not ok:
            return fail_resp

        # 获取系统配置信息
        sys_info = db.query(ZzSys).first()
        if not sys_info:
            return {
                'success': False,
                'message': '未找到系统配置信息',
                'data': None
            }

        # 获取当前学年学期
        current_year = sys_info.zz_dq_nd
        current_semester = sys_info.zz_dq_xq

        # 获取学生ID
        student_id = current_user.get('xs_id')
        if not student_id:
            return {
                'success': False,
                'message': '用户信息异常',
                'data': None
            }

        # ========== 学生级限流（防恶意频繁退选） ==========
        # 规则：10 秒内最多 3 次退选请求
        selected_set_key = f"st_course:selected:{student_id}:{current_year}:{current_semester}"
        if redis_client:
            try:
                rate_key = f"rate:cancel_st_course:{student_id}"
                current_count = redis_client.incr(rate_key)
                if current_count == 1:
                    redis_client.expire(rate_key, 10)
                if current_count > 3:
                    ttl = redis_client.ttl(rate_key)
                    return {
                        'success': False,
                        'message': f'操作过于频繁，请 {ttl if ttl > 0 else 10} 秒后再试',
                        'data': None
                    }
            except Exception as e:
                logger.warning(f"学生限流检查异常，继续执行: {str(e)}")

        # ========== Redis 快速预检：是否已选 ==========
        if redis_client:
            try:
                if not redis_client.sismember(selected_set_key, str(course_id)):
                    # Redis 中不存在，再去 DB 兜底确认
                    pass
            except Exception as e:
                logger.warning(f"Redis 已选预检异常，继续执行: {str(e)}")

        # ========== Redis 分布式锁 ==========
        redis_lock = None
        use_redis_lock = False
        lock_key = f"course_cancel_{course_id}"

        try:
            if redis_client:
                redis_lock = RedisLock(redis_client, lock_key, timeout=10, retry_delay=0.1)
                if redis_lock.acquire_sync(max_retries=10):
                    use_redis_lock = True
                else:
                    logger.warning(f"获取Redis锁失败，降级到数据库锁: {lock_key}")
        except Exception as e:
            logger.warning(f"Redis锁异常，降级到数据库锁: {str(e)}")

        try:
            # 获取选课记录（硬查找：表里只有已选记录）
            existing_selection = db.query(ZzStCourseSelection).filter_by(
                student_id=student_id,
                course_id=course_id,
                year=current_year,
                semester=current_semester
            ).first()

            if not existing_selection:
                return {
                    'success': False,
                    'message': '您未选择该课程',
                    'data': None
                }

            # 获取课程信息（使用数据库行锁）
            course = db.query(ZzStCourse).filter(
                ZzStCourse.id == course_id
            ).with_for_update().first()

            if not course:
                return {
                    'success': False,
                    'message': '课程不存在',
                    'data': None
                }

            # 硬删除选课记录（不再保留 status=0 的"退选"记录）
            db.delete(existing_selection)

            # 更新课程当前选课人数，确保不会小于0
            if course.current_students > 0:
                course.current_students -= 1
            course.update_time = datetime.now()

            # 提交事务
            db.commit()

            # ========== 同步 Redis 缓存 ==========
            if redis_client:
                try:
                    # 1. 从学生已选集合中移除
                    redis_client.srem(selected_set_key, str(course_id))
                    # 2. 更新课程缓存中的 current_students
                    course_cache_key = f"course_info:{course_id}"
                    cached = redis_client.get(course_cache_key)
                    if cached:
                        try:
                            import json as _json
                            course_data = _json.loads(cached)
                            course_data['current_students'] = course.current_students
                            course_data['updated_at'] = datetime.now().isoformat()
                            redis_client.set(course_cache_key, _json.dumps(course_data), ex=300)
                        except Exception:
                            pass
                except Exception as e:
                    logger.warning(f"同步 Redis 缓存失败: {str(e)}")

            return {
                'success': True,
                'message': '退选成功',
                'data': {
                    'course_id': course_id,
                    'course_name': course.course_name,
                    'current_students': course.current_students,
                    'max_students': course.max_students
                }
            }

        finally:
            # 确保释放Redis锁（如果使用了）
            if use_redis_lock and redis_lock:
                try:
                    redis_lock.release_sync()
                except Exception as e:
                    logger.warning(f"释放Redis锁失败: {str(e)}")

    except Exception as e:
        db.rollback()
        # 详细的错误信息记录
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"退选接口异常: {str(e)}")
        logger.error(f"详细错误信息: {error_details}")

        # 在服务器环境中打印错误（便于调试）
        print(f"[ERROR] 退选接口异常: {str(e)}")
        print(f"[ERROR] 详细错误: {error_details}")

        return {
            'success': False,
            'message': f'退选失败：{str(e)}',
            'data': {
                'error_type': type(e).__name__,
                'error_details': str(e)
            }
        }

# 获取课程信息（支持缓存）
@router.get('/get_course_info')
async def get_course_info(course_id: int, db: Session = DatabaseDep, redis_client = RedisDep):
    """获取课程详细信息"""
    try:
        if not course_id:
            return {
                'success': False,
                'message': '缺少必要参数',
                'data': None
            }

        # 初始化选课服务
        selection_service = CourseSelectionService(redis_client)

        # 获取课程信息（优先从缓存）
        course_info = await selection_service.get_course_info_with_cache(db, course_id)

        if not course_info:
            return {
                'success': False,
                'message': '课程不存在',
                'data': None
            }

        return {
            'success': True,
            'message': '获取成功',
            'data': course_info
        }

    except Exception as e:
        logger.error(f"获取课程信息异常: {str(e)}")
        return {
            'success': False,
            'message': f'获取失败：{str(e)}',
            'data': None
        }

# 获取选课队列状态
@router.get('/get_selection_queue_status')
async def get_selection_queue_status(course_id: int, redis_client = RedisDep):
    """获取指定课程的选课队列状态"""
    try:
        if not course_id:
            return {
                'success': False,
                'message': '缺少必要参数',
                'data': None
            }

        from utils.redis_utils import CourseSelectionQueue
        selection_queue = CourseSelectionQueue(redis_client)

        queue_length = selection_queue.get_queue_length(course_id)

        return {
            'success': True,
            'message': '获取成功',
            'data': {
                'course_id': course_id,
                'queue_length': queue_length,
                'status': 'active' if queue_length > 0 else 'idle'
            }
        }

    except Exception as e:
        logger.error(f"获取队列状态异常: {str(e)}")
        return {
            'success': False,
            'message': f'获取失败：{str(e)}',
            'data': None
        }

# 清除课程缓存（管理员接口）
@router.post('/clear_course_cache')
async def clear_course_cache(course_id: int, current_user: dict = Depends(verify_token_and_get_payload),
                           redis_client = RedisDep):
    """清除指定课程的缓存"""
    try:
        # 这里可以添加管理员权限检查
        # if not is_admin(current_user):
        #     return {'success': False, 'message': '权限不足'}

        if not course_id:
            return {
                'success': False,
                'message': '缺少必要参数',
                'data': None
            }

        from utils.redis_utils import CourseCache
        course_cache = CourseCache(redis_client)

        success = course_cache.delete_course_cache(course_id)

        return {
            'success': success,
            'message': '清除成功' if success else '清除失败',
            'data': {'course_id': course_id}
        }

    except Exception as e:
        logger.error(f"清除缓存异常: {str(e)}")
        return {
            'success': False,
            'message': f'清除失败：{str(e)}',
            'data': None
        }



# 更新用户头像
@router.get('/updateAvatar')
async def update_avatar(avatarUrl: str,current_user: dict = Depends(verify_token_and_get_payload),db: Session = DatabaseDep):
    if not avatarUrl:
        return {
            'success': False,
            'msg': '缺少头像URL',
            'data': None
        }
        
    try:
        # 更新用户头像
        student = db.query(ZzXs).filter_by(id=current_user.get('xs_id')).first()
        student.xs_wx_headimgurl = avatarUrl
        db.commit()
        
        return {
            'success': True,
            'msg': '更新头像成功',
            'data': None
        }
    except Exception as db_error:
        db.rollback()
        return {
            'success': False,
            'msg': f'更新头像失败: {str(db_error)}',
            'data': None
        }




# 获取用户个人信息
@router.get('/get_student_info')
def get_student_info(current_user: dict = Depends(verify_token_and_get_payload),db: Session = DatabaseDep):
    try:
        # 查询学生基本信息
        student = db.query(ZzXs).filter_by(id=current_user.get('xs_id')).first()
        if not student:
            return {
                'success': False,
                'msg': '未找到学生信息',
                'data': None
            }
        zymc = db.query(ZzBmxsBdzy).filter_by(id=student.zy_id).first()
        jzdlx = db.query(ZzBmxsJzdlx).filter_by(id=student.jzdlx).first()
        jzgx = db.query(ZzBmxsJzgx).filter_by(id=student.jzgx).first()
        zsdx = db.query(ZzBmxsZsdx).filter_by(id=student.zsdx).first()
        zzmm = db.query(ZzBmxsZzmm).filter_by(id=student.zzmm).first()
        bjmc = db.query(ZzBj).filter_by(id=student.bj_id).first()
        ex_info = {
            'jzdlx': jzdlx.mc if jzdlx else None,
            'jzgx': jzgx.mc if jzgx else None,
            'zsdx': zsdx.mc if zsdx else None,
            'zymc': zymc.mc if zymc else None,
            'zzmm': zzmm.mc if zzmm else None,
            'bjmc': bjmc.mc if bjmc else None
        }


        return {
            'success': True,
            'msg': '成功',
            'data': {
                'student':student,
                'ex_info':ex_info
            }
        }
    except Exception as e:
        return {
            'success': False,
            'msg': f'获取学生信息失败: {str(e)}',
            'data': None
        }


# =============================================
# 走读证：根据当前年度/学期，判断当前学生是否在 zz_xs_zd 名录中
# 仅在校生本人在个人中心查看。
# =============================================
@router.get('/get_zoudou_card')
def get_zoudou_card(current_user: dict = Depends(verify_token_and_get_payload),
                    db: Session = DatabaseDep):
    """返回走读证信息。

    设计要点：
    - 系统当前年度 `zz_dq_nd` / 当前学期 `zz_dq_xq` 直接取 `zz_sys` 单条记录；
      （多个 nd/xq 都不命中即视为本期未办理走读）
    - 走读表的关联键是 **`ZzXs.id == ZzXsZd.xsid`**（主键 id，不是学号 xh）；
      这是正解，否则同一姓名 + 同班存在多个历史学号时会误匹配。
    - nd 在 `zz_xs_zd` 和 `zz_sys` 中均以**整数的"末两位"**存储
      （例如 2026 学年 = 26），直接用 Integer 比较。
    - xq 在 `zz_xs_zd` 和 `zz_sys` 中均以**字符串**存储（如 "09"），保持字符串比较，
      不要再 int(...) 转换，否则 "09" 会变成 9 与库里 "09" 不匹配。
    - 多个 nd/xq 都不命中即视为本期未办理走读。
    - 走读证展示需要的扩展字段：班级名称、班主任姓名、学生证件照 URL（带签名）。
    """
    try:
        xs_id = current_user.get('xs_id')
        xs_xh = current_user.get('xs_xh')

        if not xs_xh:
            return {
                'success': False,
                'msg': '未找到当前登录学生信息',
                'data': None
            }

        student = db.query(ZzXs).filter(ZzXs.xh == xs_xh).first()
        if not student:
            return {
                'success': False,
                'msg': '学生信息不存在',
                'data': None
            }

        # 1) 读系统当前年度/学期
        sys_info = db.query(ZzSys).first()
        dq_nd = sys_info.zz_dq_nd if sys_info else None
        dq_xq = sys_info.zz_dq_xq if sys_info else None

        # 兜底：xs_id 拿不到时，至少能给学生展示当前年度/学期，便于后续调试
        base_info = {
            'xm': student.xm,
            'xh': student.xh,
            'sfzh': student.sfzh,
            'bj_id': student.bj_id,
            'dq_nd': dq_nd,
            'dq_xq': dq_xq,
        }

        if dq_nd is None or dq_xq is None or dq_xq == '':
            # 系统未配置当前年度/学期 → 当作未办理走读
            return {
                'success': True,
                'msg': '系统未配置当前年度/学期',
                'data': {**base_info, 'valid': False,
                         'reason': '系统未配置当前年度/学期，请联系管理员'}
            }

        # 2) 在走读名单里查当前学期记录
        #    关联键：ZzXs.id == ZzXsZd.xsid（学生主键）
        #    nd/xq 直接与系统当前值比较，不再做类型转换（库里都是字符串/整数原样存储）
        zd_query = db.query(ZzXsZd).filter(
            ZzXsZd.xsid == student.id,
            ZzXsZd.nd == dq_nd,
            ZzXsZd.xq == dq_xq,
        )
        zd_record = zd_query.order_by(ZzXsZd.blsj.desc()).first()

        if not zd_record:
            return {
                'success': True,
                'msg': '未在走读名单中',
                'data': {**base_info, 'valid': False,
                         'reason': f'本学期（{dq_nd} 学年 第{dq_xq}学期）未办理走读'}
            }

        # 4) 命中：补全展示信息
        class_name = ''
        bzr_name = ''
        bzr_phone = ''
        if student.bj_id:
            bj = db.query(ZzBj).filter(ZzBj.id == student.bj_id).first()
            if bj:
                class_name = bj.mc or ''
                if bj.bzr_id:
                    teacher = db.query(Teacher).filter(Teacher.t_id == bj.bzr_id).first()
                    if teacher:
                        bzr_name = teacher.t_xm or ''
                        bzr_phone = teacher.t_dh or ''

        # 5) 头像签名 URL（中职类型）
        photo_url = None
        try:
            if student.headphoto == 1 and student.sfzh:
                from controllers.photo_upload import get_signed_photo_url
                photo_url = get_signed_photo_url(student.sfzh, user_type='vocational')
        except Exception as _e:
            logger.warning(f'生成走读证照片签名 URL 失败: {_e}')

        return {
            'success': True,
            'msg': '在册',
            'data': {
                **base_info,
                'valid': True,
                'class_name': class_name,
                'bzr_name': bzr_name,
                'bzr_phone': bzr_phone,
                'photo_url': photo_url,
                'blsj': zd_record.blsj.strftime('%Y-%m-%d') if zd_record.blsj else None,
            }
        }
    except Exception as e:
        logger.error(f'获取走读证信息失败: {e}')
        return {
            'success': False,
            'msg': f'获取走读证信息失败: {str(e)}',
            'data': None
        }