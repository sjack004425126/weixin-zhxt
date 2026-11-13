from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
from models.models import jw_chongxiu,TzdCjZJsh,Student,BkGkbkb, JhZ, WxxsSfTkpayinfo, Class, bk_sxbkb, wxxs_xf_zd, wxxs_xf_zdgr, wxxs_xf_info, lw_sys, wxxs_xf_payinfo, GraduateRegistration, bk_sxbkb_z, tzd_cjfh, wxxs_payinfo, bk_bkb, Major
from init.dependencies import (
    get_redis, get_db,
    RedisDep, DatabaseDep, RedisManagerDep
)
import logging
logger = logging.getLogger(__name__)
from common.auth import verify_token_and_get_payload, verify_token_only
from datetime import datetime
from sqlalchemy import text
import random
from controllers.vocational_tuition import get_term_info  # 统一学期计算函数
import json
from utils.wx_pay import WxPayUtil
from utils.system_config import SystemConfig
from utils.wx_pay_transfer import WxPayTransfer
import logging
from utils.wx_utils import WxUtils
import re
import uuid
import time
from models.common_models import UserInfo
from utils.debug_logger import debug_print_query_results, debug_print

# 创建路由器
router = APIRouter(prefix="/student", tags=["学生信息"])

# 请求模型
class ScoreReviewRequest(BaseModel):
    course_id: str

class UpdateOrderStatusRequest(BaseModel):
    order_no: str

class GraduateRegistrationRequest(BaseModel):
    # 基本信息
    xm: str  # 姓名
    xb: str  # 性别
    mz: str  # 民族
    csrq: str  # 出生日期
    zjlx: str  # 证件类型
    zjh: str  # 证件号
    zzmm: str  # 政治面貌

    # 联系方式
    sj: str  # 手机
    jtdh: str  # 家庭电话
    dwdh: str  # 单位电话
    yx: str  # 邮箱
    dzzch: str  # 地址邮编

    # 教育信息
    xlcc: str  # 学历层次
    xslb: str  # 学生类别
    xxzy: str  # 学校专业
    rxsjn: int  # 入学时间年
    rxsjj: str  # 入学时间季

    # 工作信息
    gzdw: str  # 工作单位
    zwjd: str  # 职务/职称

    # 毕业信息
    bylwtm: str  # 毕业论文题目
    bysjn: str  # 毕业设计年
    bysjy: str  # 毕业设计月
    bysxdw: str  # 毕业实习单位
    jlhcf: str  # 奖励和处分

    # 其他信息
    xx1: str = ""  # 备用字段1
    xx2: str = ""  # 备用字段2
    xx3: str = ""  # 备用字段3
    xx4: str = ""  # 备用字段4
    xx5: str = ""  # 备用字段5

    # 时间字段
    qsj1: str = ""  # 起始时间1
    qsj2: str = ""  # 起始时间2
    qsj3: str = ""  # 起始时间3
    qsj4: str = ""  # 起始时间4
    qsj5: str = ""  # 起始时间5

    zsj1: str = ""  # 终止时间1
    zsj2: str = ""  # 终止时间2
    zsj3: str = ""  # 终止时间3
    zsj4: str = ""  # 终止时间4
    zsj5: str = ""  # 终止时间5

    # 状态
    zt: int = 0  # 状态
    id: Optional[int] = None  # ID
    tjsj: Optional[str] = None  # 提交时间

class PreBkPayRequest(BaseModel):
    courses: list
    openid_code: str

class UpdateAvatarRequest(BaseModel):
    avatarUrl: str

class WxxsBindOpenidRequest(BaseModel):
    phone: str
    verify_code: str
    openid_code: str




# 学生成绩信息，获取所有科目成绩
@router.get('/query_order_status')
async def query_order_status(order_no: str):
    """查询订单状态"""
    try:
        # 商户订单号查询订单支付结果
        wx_pay = WxPayUtil()
        query_result = wx_pay.query_order(out_trade_no=order_no)

        return query_result
    except Exception as e:
        return {
            'success': False,
            'msg': f'查询订单状态失败: {str(e)}',
            'data': None
        }





# 学生成绩信息，获取所有科目成绩
@router.get('/get_scores')
async def get_scores(current_user: dict = Depends(verify_token_and_get_payload),db: Session = DatabaseDep):
    """获取上个学期所有考试科目成绩
    Returns:
        json: 成绩信息列表
    """
    try:
        print(current_user.get('xs_xh'))
        # 1. 从bk_sxbkb表获取学生的考试科目
        subjects = db.query(BkGkbkb).filter_by(xh=current_user.get('xs_xh')).all()

        if not subjects:
            return {
                'success': False,
                'msg': '暂无考试科目信息',
                'data': None
            }
            
        # 获取所有科目的试卷号列表
        paper_ids = [subject.kcid for subject in subjects]
        
        # 2. 使用IN子句一次性查询所有科目成绩
        # 构建IN子句的参数列表
        paper_ids_str = ','.join(f"'{pid}'" for pid in paper_ids)
        
        sql = text(f"""
            SELECT 
                F1 as course_name,     -- 考试课程名称
                F9 as form_ratio,      -- 形考比例
                F10 as form_score,     -- 形考成绩
                F11 as final_score,    -- 终考成绩
                F12 as total_score,    -- 综合成绩
                F13 as complete_status, -- 成绩完整性
                F14 as synthesis_status,-- 合成状态
                F15 as double_pass,    -- 是否双及格
                F18 as score_status,   -- 成绩状态
                F2 as course_id,       -- 课程ID
                F3 as paper_id         -- 试卷号
            FROM tzd_cj 
            WHERE F4 = :student_id 
            AND F2 IN ({paper_ids_str})
        """)
        
        results = db.execute(sql, {
            'student_id': current_user.get('xs_xh')
        }).fetchall()
        
        # 3. 处理查询结果
        scores_list = []
        
        # 收集需要复核的课程ID
        review_course_ids = [result.course_id for result in results if result.score_status == "~"]
        
        # 如果有需要复核的课程，查询复核状态
        review_status_map = {}
        if review_course_ids:
            
            # 构建IN子句的课程ID字符串
            course_ids_str = ','.join(f"'{cid}'" for cid in review_course_ids)
            
            review_sql = text(f"""
                SELECT kcid, zt
                FROM tzd_cjfh
                WHERE xs_xh = :student_id
                AND kcid IN ({course_ids_str})
                AND pc = :current_pc
            """)
            
            review_results = db.execute(review_sql, {
                'student_id': current_user.get('xs_xh'),
                'current_pc': current_user.get('sys_pc')
            }).fetchall()
            
            # 创建复核状态映射
            review_status_map = {r.kcid: r.zt for r in review_results}
        
        # 合并成绩和复核状态
        for result in results:
            needs_review = result.score_status == "~" and result.course_id != "04392"
            score_dict = {
                'course_name': result.course_name,
                'course_id': result.course_id,
                'form_ratio': result.form_ratio,
                'form_score': result.form_score,
                'final_score': result.final_score,
                'total_score': result.total_score,
                'complete_status': result.complete_status,
                'synthesis_status': result.synthesis_status,
                'double_pass': result.double_pass,
                'score_status': result.score_status,
                'needs_review': needs_review,
                'review_status': review_status_map.get(result.course_id, 0) if needs_review else 0
            }
            scores_list.append(score_dict)
        
        return {
            'success': True,
            'msg': '成功',
            'data': scores_list
        }

    except Exception as e:
        logging.error(f"查询成绩出错: {str(e)}")
        return {
            'success': False,
            'msg': f'查询成绩失败: {str(e)}',
            'data': None
        }

# 计算学生当前学期（统一委托给 get_term_info）
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
        

# 学生学费信息
@router.get('/get_student_tuition')
async def get_student_tuition(current_user: dict = Depends(verify_token_and_get_payload),db: Session = DatabaseDep):
    """获取学费信息"""
    try:
        student = db.query(Student).filter_by(xs_xh=current_user.get('xs_xh')).first()
        if not student:
            return {
                'success': False,
                'msg': '未找到学生信息',
                'data': None
            }

        # 获取班级信息
        class_info = db.query(Class).filter_by(bj_id=student.xs_bj_id).first()
        if not class_info:
            return {
                'success': False,
                'msg': '无班级信息',
                'data': None
            }

        # 计算学生缴费记录和信息，并计算学生是否需要缴费================
        # 查询学费账单信息
        tuition_info = db.query(wxxs_xf_zd).filter_by(bjid=student.xs_bj_id).first()
        
        # 初始化学费信息
        fee_data = {
            'xf_1': 0,  # 第一学年学费
            'xf_2': 0,  # 第二学年学费
            'sf_1': 0,  # 第一学年书费
            'sf_2': 0   # 第二学年书费
        }

        if tuition_info:
            fee_data.update({
                'xf_1': tuition_info.xf_1 if tuition_info.xf_1 else 0,
                'xf_2': tuition_info.xf_2 if tuition_info.xf_2 else 0,
                'sf_1': tuition_info.sf_1 if tuition_info.sf_1 else 0,
                'sf_2': tuition_info.sf_2 if tuition_info.sf_2 else 0,
            })

        # 查询个人账单（如果有则覆盖班级账单）
        personal_bill = db.query(wxxs_xf_zdgr).filter_by(xsxh=student.xs_xh).first()

        if personal_bill:
            fee_data.update({
                'xf_1': personal_bill.xf_1 if personal_bill.xf_1 else fee_data['xf_1'],
                'xf_2': personal_bill.xf_2 if personal_bill.xf_2 else fee_data['xf_2'],
                'sf_1': personal_bill.sf_1 if personal_bill.sf_1 else fee_data['sf_1'],
                'sf_2': personal_bill.sf_2 if personal_bill.sf_2 else fee_data['sf_2'],
            })
        # 计算应缴总额
        total_tuition = fee_data['xf_1'] + fee_data['xf_2']  # 应缴总学费
        total_books = fee_data['sf_1'] + fee_data['sf_2']    # 应缴总书费

        # 查询实际缴费情况
        payment_info = db.query(wxxs_xf_info).filter_by(F6=student.xs_xh).first()

        # 初始化实际缴费金额
        actual_payment = {
            'paid_tuition': 0,  # 实际缴纳学费
            'paid_books': 0,    # 实际缴纳书费
            'reduction': 0      # 减免费用
        }

        # 处理第一个表(wxxs_xf_info)的缴费记录
        if payment_info:
            # 学费 
            xf1 = int(payment_info.F10) if payment_info.F10 is not None else 0
            xf2 = int(payment_info.F12) if payment_info.F12 is not None else 0
            xf3 = int(payment_info.F14) if payment_info.F14 is not None else 0
            xf4 = int(payment_info.F16) if payment_info.F16 is not None else 0
            xf5 = int(payment_info.F18) if payment_info.F18 is not None else 0
            
            # 书费 - 
            sf1 = int(payment_info.F11) if payment_info.F11 is not None else 0
            sf2 = int(payment_info.F13) if payment_info.F13 is not None else 0
            sf3 = int(payment_info.F15) if payment_info.F15 is not None else 0
            sf4 = int(payment_info.F17) if payment_info.F17 is not None else 0
            sf5 = int(payment_info.F19) if payment_info.F19 is not None else 0

            # 减免
            jm = int(payment_info.F22) if payment_info.F22 is not None else 0
            
            # 计算总额（以分为单位）
            # 缴费表存储单位是元，需要乘以100转换为分
            zxf = (xf1 + xf2 + xf3 + xf4 + xf5) * 100  # 学费转为分
            zsf = (sf1 + sf2 + sf3 + sf4 + sf5) * 100  # 书费转为分
            jm = jm * 100  # 减免转为分
            

            
            # 初始化实际缴费金额
            actual_payment['paid_tuition'] = zxf 
            actual_payment['paid_books'] = zsf 
            actual_payment['reduction'] = jm 

        # 查询并加上第二个表(wxxs_xf_payinfo)的缴费记录
        payinfo_sql = text("""
            SELECT o_xf, o_sf, o_jm 
            FROM wxxs_xf_payinfo 
            WHERE o_xh = :xsxh 
            AND o_status = 1 
            AND o_tk_status = 0 
            AND o_xxtk_status = 0
            AND o_close = 0
            AND o_delete = 0
        """)
        payinfo_results = db.execute(payinfo_sql, {'xsxh': student.xs_xh}).fetchall()
        
        # 加上本系统的缴费记录（这些金额应该已经是分为单位）
        if payinfo_results:
            for record in payinfo_results:
                # 直接加到总额上（因为已经是分为单位）
                actual_payment['paid_tuition'] += (record.o_xf or 0)   
                actual_payment['paid_books'] += (record.o_sf or 0)     
                actual_payment['reduction'] += (record.o_jm or 0)      

        # 计算剩余应缴费用------------这里需要考虑减免
        remaining_pay = (total_tuition + total_books) - (actual_payment['paid_tuition'] + actual_payment['paid_books'])-actual_payment['reduction']
        print('第一次的remaining_pay:',remaining_pay)
        # 计算退费记录
        sys_info = db.query(lw_sys).filter_by(id=1).first()
        wxxs_sf = db.query(WxxsSfTkpayinfo).filter_by(o_xh=student.xs_xh).first()
        if wxxs_sf:
            refund_info = {
                    'refund_id':wxxs_sf.o_id,
                    'refund_amount': wxxs_sf.o_money,
                    'refund_status': wxxs_sf.o_status,
                    'refund_time': wxxs_sf.o_create_time,
                    'o_payment_time': wxxs_sf.o_payment_time,
                    'package_info':wxxs_sf.package_info,
                    'o_check_state':wxxs_sf.o_check_state
                }
            
            #检测是否退费成功，成功则计入总费用中
            if wxxs_sf.o_status == 3:
                # print('退费成功，计入总费用中',wxxs_sf.o_money)
                remaining_pay = remaining_pay + wxxs_sf.o_money
        else:
            refund_info = None

        # 计算学生是否需要缴费级结束================



        user_class = db.query(Class).filter_by(bj_id=student.xs_bj_id).first()
        class_name = user_class.bj_mc if user_class else ''

        # 获取学生当前学期数
        student_term = calculate_current_term(
            sys_info.sys_xq1_nd,
            sys_info.sys_xq1_xq,
            user_class.bj_nd,
            user_class.bj_xqdm
        )
        # 构建返回数据
        return {
            'success': True,
            'msg': '获取成功',
            'data': {
                'student': {
                    'name': student.xs_xm,
                    'student_no': student.xs_xh,
                    'class_name': class_name,
                    'semester':student_term
                },
                'sys_wxxs_xf_tk_payinfo_switch':sys_info.sys_wxxs_xf_tk_payinfo_switch,
                'refund_info': refund_info,
                'tuition_info': {
                    'first_year': {
                        'tuition': fee_data['xf_1'],
                        'books': fee_data['sf_1']
                    },
                    'second_year': {
                        'tuition': fee_data['xf_2'],
                        'books': fee_data['sf_2']
                    },
                    'total': {
                        'tuition': total_tuition,
                        'books': total_books
                    },
                    'actual_payment': {
                        'tuition': actual_payment['paid_tuition'],
                        'books': actual_payment['paid_books'],
                        'reduction': actual_payment['reduction']
                    },
                    'remaining_payment': remaining_pay
                }
            }
        }

    except Exception as e:
        return {
            'success': False,
            'msg': f'获取学费信息失败: {str(e)}',
            'data': None
        }




# 学生缴费信息，计算学费并生成订单，这个放弃暂时弃用了，先保留，后期删除
@router.get('/calculate_tuition')
async def calculate_tuition(current_user: dict = Depends(verify_token_and_get_payload),db: Session = DatabaseDep):
    """计算学费并生成订单"""
    try:
        # 获取当前时间
        now = datetime.now()
        
        # 首先检查缴费截止日期
        # 获取系统配置信息
        sys_info = db.query(lw_sys).filter_by(dq1_mc=current_user.get('dq1_mc')).first()
        if not sys_info:
            return {
                'success': False,
                'msg': '系统配置信息不存在',
                'data': None
            }


        # 获取学生信息
        student = db.query(Student).filter_by(xs_xh=current_user.get('xs_xh')).first()
        if not student:
            return {
                'success': False,
                'msg': '未找到学生信息',
                'data': None
            }
        
        # 检查是否有未完成的订单
        unpaid_order_sql = text("""
            SELECT  o_order_no, o_type 
            FROM wxxs_xf_payinfo 
            WHERE o_xh = :xsxh 
            AND o_status = 0 
            AND o_close = 0 
            AND o_pc = :pc
            AND o_tk_status = 0
            AND o_delete = 0
        """)
        unpaid_order = db.execute(
            unpaid_order_sql,
            {'xsxh': student.xs_xh, 'pc': sys_info.sys_pc}
        ).first()

        if unpaid_order:
            if unpaid_order.o_type == 3 or unpaid_order.o_type == 5:  # 只要微信或小程序支付的订单，其他支付方式不处理                
                
                # 确保o_addtime是datetime对象
                if isinstance(unpaid_order.o_addtime, str):
                    unpaid_order.o_addtime = datetime.strptime(unpaid_order.o_addtime, '%Y-%m-%d %H:%M:%S')

                time_diff = (now - unpaid_order.o_addtime).total_seconds()

                if time_diff < 30:  # 30秒内
                    return {
                            'success': False,
                            'msg': '请勿频繁提交订单,30秒内只能提交一次',
                            'data': None
                    }
                return {
                    'success': True,
                    'msg': '您有支付未完成的订单',
                    'data': {
                        'order_no': order.o_order_no,
                        'tuition': float(order.o_xf) / 100 if order.o_xf else 0,
                        'books': float(order.o_sf) / 100 if order.o_sf else 0,
                        'total_amount': order.o_money / 100 if order.o_money else 0,
                        'create_time': order.o_addtime.strftime('%Y-%m-%d %H:%M:%S') if order.o_addtime else None
                    }
                }
            else:
                return {
                    'success': False,
                    'msg': '已检测到已使用电脑端或手机浏览器端生成了未支付的订单，请继续使用原支付方式完成支付！',
                    'data': None
                }


        # 判断新老生缴费时间
        if student.xs_nd == sys_info.sys_xq1_nd:  # 新生
            if not sys_info.sys_xs_jf:
                return {
                    'success': False,
                    'msg': '新生缴费时间未设置',
                    'data': None
                }
            if now > sys_info.sys_xs_jf:
                return {
                    'success': False,
                    'msg': '新生缴费时间已结束',
                    'data': {
                        'deadline': sys_info.sys_xs_jf.strftime('%Y-%m-%d %H:%M:%S')
                    }
                }
        else:  # 老生
            if not sys_info.sys_ls_jf:
                return {
                    'success': False,
                    'msg': '老生缴费时间未设置',
                    'data': None
                }
            if now > sys_info.sys_ls_jf:
                return {
                    'success': False,
                    'msg': '老生缴费时间已结束',
                    'data': {
                        'deadline': sys_info.sys_ls_jf.strftime('%Y-%m-%d %H:%M:%S')
                    }
                }

        # 如果在缴费时间内，继续后续处理...
        # 获取班级信息
        class_info = db.query(Class).filter_by(bj_id=student.xs_bj_id).first()
        if not class_info:
            return {
                'success': False,
                'msg': '无该班级信息',
                'data': None
            }

        # 初始化费用变量
        xf_1 = xf_2 = sf_1 = sf_2 = 0
        yszxf = yszsf = 0  # 应收总学费、应收总书费

        # 优先查询个人账单
        personal_bill = wxxs_xf_zdgr.query.filter_by(xsxh=student.xs_xh).first()
        if personal_bill:
            # 使用个人账单数据
            xf_1 = personal_bill.xf_1 if personal_bill.xf_1 else 0
            xf_2 = personal_bill.xf_2 if personal_bill.xf_2 else 0
            sf_1 = personal_bill.sf_1 if personal_bill.sf_1 else 0
            sf_2 = personal_bill.sf_2 if personal_bill.sf_2 else 0
            
            # 计算应收总额
            yszxf = xf_1 + xf_2  # 应收总学费
            yszsf = sf_1 + sf_2  # 应收总书费
            
            
        else:
            # 如果没有个人账单，查询班级账单
            class_bill = wxxs_xf_zd.query.filter_by(bjid=student.xs_bj_id).first()
            if class_bill:
                # 使用班级账单数据
                xf_1 = class_bill.xf_1 if class_bill.xf_1 else 0
                xf_2 = class_bill.xf_2 if class_bill.xf_2 else 0
                sf_1 = class_bill.sf_1 if class_bill.sf_1 else 0
                sf_2 = class_bill.sf_2 if class_bill.sf_2 else 0
                
                # 计算应收总额
                yszxf = xf_1 + xf_2  # 应收总学费
                yszsf = sf_1 + sf_2  # 应收总书费
                
                
            else:
                # 如果班级账单也没有
                return {
                    'success': False,
                    'msg': '班级及个人账单还未创建，请联系班主任！',
                    'data': None
                }

        # 如果应缴金额为0，不允许生成订单
        if yszxf == 0 and yszsf == 0:
            return {
                'success': False,
                'msg': '应缴费用为0，无需生成订单',
                'data': None
            }

        # 统计已缴费金额
        paid_xf = paid_sf = paid_jm = 0  # 已缴学费、书费、减免

        # 查询第一个表(wxxs_xf_info)的缴费记录
        payment_info = db.query(wxxs_xf_info).filter_by(F6=student.xs_xh).first()
        if payment_info:
            # 学费
            xf1 = int(payment_info.F10) if payment_info.F10 else 0
            xf2 = int(payment_info.F12) if payment_info.F12 else 0
            xf3 = int(payment_info.F14) if payment_info.F14 else 0
            xf4 = int(payment_info.F16) if payment_info.F16 else 0
            xf5 = int(payment_info.F18) if payment_info.F18 else 0
            
            # 书费
            sf1 = payment_info.F11 or 0
            sf2 = payment_info.F13 or 0
            sf3 = payment_info.F15 or 0
            sf4 = payment_info.F17 or 0
            sf5 = payment_info.F19 or 0
            
            # 减免
            jm = payment_info.F22 if payment_info.F22 else 0
            
            # 计算总额（以分为单位）
            paid_xf = xf1 + xf2 + xf3 + xf4 + xf5  # 学费转为分
            paid_sf = sf1 + sf2 + sf3 + sf4 + sf5  # 书费转为分
            paid_jm = jm  # 减免转为分
            

        # 查询第二个表(wxxs_xf_payinfo)的缴费记录
        payinfo_sql = text("""
            SELECT o_xf, o_sf, o_jm 
            FROM wxxs_xf_payinfo 
            WHERE o_xh = :xsxh 
            AND o_status = 1 
            AND o_tk_status = 0 
            AND o_xxtk_status = 0
        """)
        payinfo_results = db.execute(payinfo_sql, {'xsxh': student.xs_xh}).fetchall()
        
        # 加上本系统的缴费记录
        if payinfo_results:
            for record in payinfo_results:
                paid_xf += (record.o_xf or 0)  # 已经是分为单位
                paid_sf += (record.o_sf or 0)  # 已经是分为单位
                paid_jm += (record.o_jm or 0)  # 已经是分为单位

        # 计算实际需要缴纳的金额（应缴 - 已缴）
        need_pay_xf = yszxf - (paid_xf + paid_jm)  # 学费需要减去减免金额
        need_pay_sf = yszsf - paid_sf
        total_need_pay = need_pay_xf + need_pay_sf


        # 判断是否需要生成订单
        if total_need_pay <= 0:
            return {
                'success': False,
                'msg': '无需缴费,已超额缴费' if total_need_pay < 0 else '无需缴费',
                'data': {
                    'overpaid': abs(total_need_pay) if total_need_pay < 0 else 0
                }
            }

        # 生成订单号（年月日时分秒+随机数）
        order_no = f"{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(1000, 9999)}"


        # 生成订单
        try:            
            # 限制字段长度
            order_body = f'黔东南开放大学-学杂费JSAPIX-{sys_info.sys_xq1_nd}-{student.xs_xh}'  # 直接使用中文字符串            
            # 确保IP地址长度不超过限制
            ip_address = request.client.host[:15] if request.client.host else ''
            
            # 创建订单对象
            new_order = wxxs_xf_payinfo(
                o_xm=student.xs_xm,
                o_xh=student.xs_xh,
                o_sfzh=student.xs_sfzh,
                o_sj=student.xs_dh,
                o_zyid=class_info.bj_zyid,
                o_body=order_body,
                o_money=total_need_pay,  # 确保是整数
                o_xf=need_pay_xf,  # 确保是整数
                o_sf=need_pay_sf,  # 确保是整数
                o_jm=0,  # 减免金额
                o_paytype='weixin',  # 固定使用微信支付
                o_type=5,  # 5表示小程序支付
                o_status=0,  # 0表示未支付
                o_tk_status=0,  # 0表示未退款
                o_close=0,  # 0表示未关闭
                o_xx_status=0,  # 0表示未下发
                o_xxtk_status=0,  # 0表示未退款
                o_order_no=order_no[:30],  # 订单号限制30字符
                o_addtime=datetime.now(),
                o_pc=sys_info.sys_pc,  # 批次
                o_delete=0,  # 0表示未删除
                o_isxs=1 if student.xs_nd == sys_info.sys_xq1_nd else 0,  # 是否新生
                o_ip=ip_address
            )
            # 保存订单
            db.add(new_order)
            db.commit()
            # 返回订单信息
            return {
                'success': True,
                'msg': '订单创建成功',
                'data': {
                    'order_no': new_order.o_order_no,
                    'tuition': new_order.o_xf if new_order.o_xf else 0,
                    'books': new_order.o_sf if new_order.o_sf else 0,
                    'total_amount': new_order.o_money if new_order.o_money else 0,
                    'create_time': new_order.o_addtime.strftime('%Y-%m-%d %H:%M:%S') if new_order.o_addtime else None
                }
            }
        except Exception as e:
            return {
                'success': False,
                'msg': f'订单生成失败: {str(e)}',
                'data': None
            }
    except Exception as e:
        return {
            'success': False,
            'msg': '计算错误，生成订单异常，请稍后重试',
            'data': None
        }



# 更新订单支付状态
@router.post('/updateOrderStatus')
async def update_order_status(update_request: UpdateOrderStatusRequest,_: dict = Depends(verify_token_only),db: Session = DatabaseDep):
    """更新订单支付状态"""
    try:
        # 获取请求参数
        order_no = update_request.order_no
        
        if not order_no:
            return {
                'success': False,
                'msg': '缺少必要参数',
                'data': None
            }
        # 查询订单信息
        to_update_order = db.query(wxxs_xf_payinfo).filter_by(o_order_no=order_no).first()
        if not to_update_order:
            return {
                'success': False,
                'msg': '订单不存在',
                'data': None
            }
        # 商户订单号查询订单支付结果
        wx_pay = WxPayUtil()
        query_result = wx_pay.query_order(out_trade_no=order_no)

        # 检查查询结果是否成功，并且订单状态为成功
        if  query_result.get('success'):
            # 因为各种原因延迟支付，但是支付成功，更新订单状态
            to_update_order.o_status = 1
            to_update_order.o_trade_no = query_result['transaction_id']
            to_update_order.o_paytime = query_result['success_time']
            db.commit()
            return {
                'success': True,
                'msg':'订单支付成功并已更新',
                'data':None
            }
        else:
            return {
                'success': False,
                'msg': '订单支付未支付成功，请重试或联系管理员',
                'data': None
            }
    except Exception as e:
        return {
            'success': False,
            'msg': f'支付成功，但更新订单状态失败: {str(e)}',
            'data': None
        }

# 获取用户订单列表
@router.get('/getOrderList')
async def get_order_list(current_user: dict = Depends(verify_token_and_get_payload),db: Session = DatabaseDep):
    """获取用户订单列表"""
    try:
        # 计算学生是否需要缴费，第三个学期以后才需要缴费================
        sys_info = db.query(lw_sys).filter_by(dq1_mc=current_user.get('dq1_mc')).first()
        student = db.query(Student).filter_by(xs_xh=current_user.get('xs_xh')).first()


        # 通过账单计算是否欠费，如果欠费，判断是否已经有未缴费订单，没有则需要生成订单
        tuition_info = db.query(wxxs_xf_zd).filter_by(bjid=student.xs_bj_id).first()
        
        # 初始化学费信息
        fee_data = {
            'xf_1': 0,  # 第一学年学费
            'xf_2': 0,  # 第二学年学费
            'sf_1': 0,  # 第一学年书费
            'sf_2': 0   # 第二学年书费
        }

        if tuition_info:
            fee_data.update({
                'xf_1': tuition_info.xf_1 if tuition_info.xf_1 else 0,
                'xf_2': tuition_info.xf_2 if tuition_info.xf_2 else 0,
                'sf_1': tuition_info.sf_1 if tuition_info.sf_1 else 0,
                'sf_2': tuition_info.sf_2 if tuition_info.sf_2 else 0,
            })

        # 查询个人账单（如果有则覆盖班级账单）
        personal_bill = db.query(wxxs_xf_zdgr).filter_by(xsxh=student.xs_xh).first()

        if personal_bill:
            fee_data.update({
                'xf_1': personal_bill.xf_1 if personal_bill.xf_1 else fee_data['xf_1'],
                'xf_2': personal_bill.xf_2 if personal_bill.xf_2 else fee_data['xf_2'],
                'sf_1': personal_bill.sf_1 if personal_bill.sf_1 else fee_data['sf_1'],
                'sf_2': personal_bill.sf_2 if personal_bill.sf_2 else fee_data['sf_2'],
            })
        # 计算应缴总额
        total_tuition = fee_data['xf_1'] + fee_data['xf_2']  # 应缴总学费
        total_books = fee_data['sf_1'] + fee_data['sf_2']    # 应缴总书费

        # 查询线下缴费记录（wxxs_xf_info），同时用于计算已缴金额
        payment_info = db.query(wxxs_xf_info).filter_by(F6=student.xs_xh).first()

        # 初始化实际缴费金额
        actual_payment = {
            'paid_tuition': 0,
            'paid_books': 0,
            'reduction': 0
        }
        # 线下订单列表（从 wxxs_xf_info 按学期拆分）
        offline_orders = []

        if payment_info:
            # 每学期 (学费字段, 书费字段, 学期描述)
            semester_fields = [
                (payment_info.F10, payment_info.F11, '第一学期'),
                (payment_info.F12, payment_info.F13, '第二学期'),
                (payment_info.F14, payment_info.F15, '第三学期'),
                (payment_info.F16, payment_info.F17, '第四学期'),
                (payment_info.F18, payment_info.F19, '第五学期'),
            ]
            jm = int(payment_info.F22) * 100 if payment_info.F22 is not None else 0
            actual_payment['reduction'] = jm

            for xf_raw, sf_raw, semester_label in semester_fields:
                xf = int(xf_raw) * 100 if xf_raw is not None else 0  # 元转分
                sf = int(sf_raw) * 100 if sf_raw is not None else 0
                if xf == 0 and sf == 0:
                    continue
                actual_payment['paid_tuition'] += xf
                actual_payment['paid_books'] += sf
                offline_orders.append({
                    'o_id': None,
                    'o_order_no': '',           # 线下无订单号
                    'o_addtime': None,
                    'o_paytime': None,
                    'o_money': xf + sf,
                    'o_xf': xf,
                    'o_sf': sf,
                    'o_jm': 0,
                    'o_status': 1,              # 线下已缴视为已支付
                    'o_status_desc': '已支付（线下）',
                    'o_body': f'黔东南开放大学-线下缴费-{semester_label}',
                })

        # 查询线上缴费记录（wxxs_xf_payinfo），同时用于计算已缴金额
        wx_pay = WxPayUtil()
        online_orders = db.query(wxxs_xf_payinfo).filter_by(
            o_xh=current_user.get('xs_xh'), o_close=0, o_delete=0
        ).order_by(wxxs_xf_payinfo.o_addtime.asc()).all()

        online_order_list = []
        for order in online_orders:
            # 未支付但有交易号，向微信查询最新状态
            if order.o_status == 0 and order.o_trade_no:
                pay_result = wx_pay.query_order(order.o_order_no)
                if pay_result.get('success'):
                    order.o_status = 1
                    order.o_paytime = pay_result['success_time']
                    order.o_trade_no = pay_result['transaction_id']
                    db.commit()

            # 已支付的线上订单计入已缴金额
            if order.o_status == 1 and order.o_tk_status == 0 and order.o_xxtk_status == 0:
                actual_payment['paid_tuition'] += (order.o_xf or 0)
                actual_payment['paid_books'] += (order.o_sf or 0)
                actual_payment['reduction'] += (order.o_jm or 0)

            status_desc = {
                0: '待支付',
                1: '已支付',
                2: '已取消',
                3: '已退款'
            }.get(order.o_status, '未知状态')

            online_order_list.append({
                'o_id': order.o_id,
                'o_order_no': order.o_order_no,
                'o_addtime': order.o_addtime,
                'o_paytime': order.o_paytime,
                'o_money': order.o_money,
                'o_xf': order.o_xf,
                'o_sf': order.o_sf,
                'o_jm': order.o_jm,
                'o_status': order.o_status,
                'o_status_desc': status_desc,
                'o_body': order.o_body
            })

        # 计算剩余应缴费用
        remaining_pay = (
            (total_tuition + total_books)
            - (actual_payment['paid_tuition'] + actual_payment['paid_books'])
            - actual_payment['reduction']
        )

        # 线下订单排在前面，线上订单按时间倒序在后
        order_list = offline_orders + online_order_list

        return {
            'success': True,
            'msg': '获取成功',
            'data': {
                'order_list': order_list,
                'needPay': remaining_pay > 0,
                'pending_info': {
                    'money': remaining_pay if remaining_pay > 0 else 0,
                    'xf': total_tuition - actual_payment['paid_tuition'],
                    'sf': total_books - actual_payment['paid_books'],
                    'jm': actual_payment['reduction'],
                    'body': '黔东南开放大学-在线缴费',
                } if remaining_pay > 0 else None
            }
        }
    except Exception as e:
        return {
            'success': False,
            'msg': f'查询订单列表失败: {str(e)}',
            'data': None
        }


# 获取毕业生登记表信息
@router.get('/get_graduate_registration')
async def get_graduate_registration(current_user: dict = Depends(verify_token_and_get_payload),db: Session = DatabaseDep):
    """获取毕业生登记表信息"""
    try:

        user_xs = db.query(Student).filter_by(xs_xh=current_user.get('xs_xh')).first()
        # 查询是否已存在登记表
        reg = db.query(GraduateRegistration).filter_by(xh=user_xs.xs_xh).first()

        # 获取班级信息
        class_info = db.query(Class).filter_by(bj_id=user_xs.xs_bj_id).first()
        if not class_info:
            return {
                'success': False,
                'msg': '未找到班级信息',
                'data': None
            }
            
        # 判断学生类别和学历层次
        student_type = ""
        education_level = ""
        if user_xs.xs_xh[7] == "2":  # 第8位是2
            education_level = "专科起点本科"
            if user_xs.xs_xh[6] == "1":
                student_type = "开放教育本科"
            elif user_xs.xs_xh[6] == "4":
                student_type = "一村一名大学生"
        elif user_xs.xs_xh[7] == "4":  # 第8位是4
            education_level = "专科"
            if user_xs.xs_xh[6] == "1":
                student_type = "开放教育专科"
            elif user_xs.xs_xh[6] == "4":
                student_type = "一村一名大学生"
                
        # 从身份证号获取出生日期
        birth_date = None
        if user_xs.xs_sfzh and len(user_xs.xs_sfzh) >= 14:
            birth_date = user_xs.xs_sfzh[6:14]  # 提取身份证中的出生日期部分
            
        # 判断入学季节
        admission_season = ""
        if class_info.bj_xqdm == "03":
            admission_season = "春季"
        elif class_info.bj_xqdm == "09":
            admission_season = "秋季"
        
        if not reg:
            # 返回基本信息模板，使用registration格式
            return {
                'success': True,
                'msg': '未找到登记表，请先填写登记表',
                'data': {
                    'is_graduate': user_xs.xs_xjzt == "7",  # 是否毕业
                    'is_locked': False,  # 未找到记录时默认未锁定
                    'registration': {
                        'id': None,
                        'xm': user_xs.xs_xm,
                        'csrq': birth_date,
                        'xb': user_xs.xs_xb,
                        'mz': user_xs.xs_mz,
                        'zjlx': "身份证" if user_xs.xs_sfzh else "",
                        'zjh': user_xs.xs_sfzh,
                        'zzmm': "",
                        'xslb': student_type,
                        'xlcc': education_level,
                        'xxzy': class_info.bj_zy,
                        'rxsjn': class_info.bj_nd,
                        'rxsjj': admission_season,
                        'bysjn': user_xs.xs_bysjn,
                        'bysjy': user_xs.xs_bysjy,
                        'dzzch': user_xs.xs_dzzch,
                        'gzdw': "",
                        'dwdh': "",
                        'sj': user_xs.xs_dh,
                        'jtdh': "",
                        'yx': "",
                        'study_experience': [
                            {
                                'qsj': "",
                                'zsj': "",
                                'xx': ""
                            }
                        ],
                        'bysxdw': "",
                        'bylwtm': "",
                        'jlhcf': "",
                        'zwjd': "",
                        'zt': 0,
                        'tjsj': None
                    }
                }
            }
        
        # 构建学习经历列表
        study_experience = []
        for i in range(1, 6):  # 遍历5条学习经历
            qsj = getattr(reg, f'qsj{i}')
            zsj = getattr(reg, f'zsj{i}')
            xx = getattr(reg, f'xx{i}')
            # 只有当所有字段都不为空时才添加
            if qsj and zsj and xx:
                study_experience.append({
                    'qsj': qsj,
                    'zsj': zsj,
                    'xx': xx
                })
        
        # 如果存在登记表，返回完整信息
        return {
            'success': True,
            'msg': '获取成功',
            'data': {
                'is_graduate': user_xs.xs_xjzt == "7",  # 是否毕业
                'is_locked': reg.zt == 1,  # 1表示锁定
                'registration': {
                    'id': reg.id,
                    'xm': reg.xm,
                    'csrq': reg.csrq,
                    'xb': reg.xb,
                    'mz': reg.mz,
                    'zjlx': reg.zjlx,
                    'zjh': reg.zjh,
                    'zzmm': reg.zzmm,
                    'xslb': reg.xslb,
                    'xlcc': reg.xlcc,
                    'xxzy': reg.xxzy,
                    'rxsjn': reg.rxsjn,
                    'rxsjj': reg.rxsjj,
                    'bysjn': reg.bysjn,
                    'bysjy': reg.bysjy,
                    'dzzch': reg.dzzch,
                    'gzdw': reg.gzdw,
                    'dwdh': reg.dwdh,
                    'sj': reg.sj,
                    'jtdh': reg.jtdh,
                    'yx': reg.yx,
                    'study_experience': study_experience,
                    'bysxdw': reg.bysxdw,
                    'bylwtm': reg.bylwtm,
                    'jlhcf': reg.jlhcf,
                    'zwjd': reg.zwjd,
                    'zt': reg.zt,
                    'tjsj': reg.tjsj.strftime('%Y-%m-%d %H:%M:%S') if reg.tjsj else None
                }
            }
        }
    except Exception as e:
        return {
            'success': False,
            'msg': f'获取登记表失败: {str(e)}',
            'data': None
        }

# 保存毕业生登记表
@router.post('/save_graduate_registration')
async def save_graduate_registration(registration_data: GraduateRegistrationRequest,current_user: dict = Depends(verify_token_and_get_payload),db: Session = DatabaseDep):
    """保存毕业生登记表"""
    try:
        # 将Pydantic模型转换为字典
        data = registration_data.dict()

        # 验证必填字段
        required_fields = ['xm','xb','csrq','mz','zzmm','zjlx','zjh','sj','xlcc','xslb','xxzy','rxsjn','rxsjj','bysjn','bysjy','bylwtm','zwjd']

        for field in required_fields:
            if not data.get(field):
                return {
                    'success': False,
                    'msg': f'缺少必填字段: {field}',
                    'data': None
                }

        # 检查是否已存在登记表
        reg = db.query(GraduateRegistration).filter_by(xh=current_user.get('xs_xh')).first()
        if reg:
            if reg.zt == 1:
                return {
                    'success': False,
                    'msg': '登记表已锁定,无法修改',
                    'data': None
                }

            # 更新现有登记表
            for field, value in data.items():
                if hasattr(reg, field):
                    setattr(reg, field, value)
            reg.tjsj = datetime.now()

        else:
            # 创建新登记表
            data['xh'] = current_user.get('xs_xh')
            data['bjid'] = current_user.get('bj_id')
            data['tjsj'] = datetime.now()
            data['zt'] = 0
            reg = GraduateRegistration(**data)
            db.add(reg)
            
        try:
            db.commit()
            return {
                'success': True,
                'msg': '保存成功',
                'data': None
            }
        except Exception as e:
            db.rollback()
            return {
                'success': False,
                'msg': f'保存失败: {str(e)}',
                'data': None
            }
    except Exception as e:
        return {
            'success': False,
            'msg': f'操作失败: {str(e)}',
            'data': None
        }

# 获取毕业证领取状态
@router.get('/get_diploma_status')
async def get_diploma_status(current_user: dict = Depends(verify_token_and_get_payload),db: Session = DatabaseDep):
    try:
        user_xs = db.query(Student).filter_by(xs_xh=current_user.get('xs_xh')).first()
        # 查询毕业证信息
        sql = text("""
            SELECT * FROM by_byzmd WHERE xh = :student_no
        """)
        result = db.execute(sql, {"student_no": user_xs.xs_xh}).first()
        
        # 构建返回数据
        diploma_info = None
        if result:
            diploma_info = {
                "batch": result.bypc,  # 毕业批次
                "id": result.xhid,  # 序号ID
                "name": result.xm,  # 姓名
                "gender": result.xb,  # 性别
                "student_no": result.xh,  # 学号
                "education_level": result.cc,  # 层次
                "major": result.zymc,  # 专业名称
                "status": result.zt,  # 领取状态
                "receive_time": result.lqsj.strftime('%Y-%m-%d %H:%M:%S') if result.lqsj else None  # 领取时间
            }
        
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
            
        response_data = {
            "diploma_info": diploma_info,
            "student_info": {
                "id": user_xs.xs_id,
                "name": user_xs.xs_xm,
                "student_no": user_xs.xs_xh,
                "status": get_status_desc(user_xs.xs_xjzt)
            },
            "notice": {
                "general": "如果无记录，则为你未毕业或者毕业证还未到，请耐心等待。",
                "time": "学校规定为每学期每周的周二和周四为毕业证领取时间，其余时间不办理毕业证领取。",
                "process": [
                    "1、到系统内填写电子毕业生登记表，由班主任封存好档案袋。",
                    "2、到学校综合楼九楼908财务室办理费用核对，核对无误后由财务室给予毕业证领条。",
                    "3、持领条找班主任签字后，拿好密封档案袋。",
                    "4、持签字后的领条到综合楼八楼805办公室领取毕业证。"
                ],
                "location": "以上流程适用于在凯里就读的学生，如果你不在凯里就读请直接咨询相关老师。"
            }
        }
        
        return {
            "success": True,
            "msg": "success",
            "data": response_data
        }
        
    except Exception as e:
        return {
            "success": False,
            "msg": f"查询失败：{str(e)}",
            "data": None
        }

@router.post('/score/review')
async def update_score_review(
    review_request: ScoreReviewRequest,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    try:
        course_id = review_request.course_id
        action = 'apply'  # 默认为申请复核
        user_xs = db.query(Student).filter_by(xs_xh=current_user.xs_xh).first()
        if not user_xs:
            return {
                'code': 1,
                'msg': '用户信息不存在',
                'data': None
            }
        # 参数验证
        if not course_id or not action:
            return {
                'code': 1,
                'msg': '缺少必要参数',
                'data': None
            }
            
        if action not in ['apply', 'cancel']:
            return {
                'code': 1,
                'msg': '无效的操作类型',
                'data': None
            }
            
        # 获取系统配置
        sys_config = SystemConfig.get_config()
        if not sys_config:
            return {
                'code': 1,
                'msg': '系统配置信息不存在',
                'data': None
            }
            
        # 查询是否存在复核记录
        review = tzd_cjfh.query.filter_by(
            xs_xh=user_xs.xs_xh,
            kcid=course_id,
            pc=sys_config['sys_pc']  # 使用缓存的配置
        ).first()
        
        current_time = datetime.now()
        
        if action == 'apply':
            if review:
                # 更新提交时间
                review.tjsj = current_time
                review.zt = 1  # 更新状态为已申请
            else:
                # 创建新记录
                review = tzd_cjfh(
                    xs_xh=user_xs.xs_xh,
                    xs_xm=user_xs.xs_xm,
                    xs_bj_id=user_xs.xs_bj_id,
                    kcid=course_id,
                    pc=sys_config['sys_pc'],
                    tjsj=current_time,
                    zt=1  # 1表示已申请
                )
                db.session.add(review)
        else:  # cancel
            if review:
                # 更新状态为未申请
                review.tjsj = current_time
                review.zt = 0
            else:
                # 创建新记录，状态为未申请
                review = tzd_cjfh(
                    xs_xh=user_xs.xs_xh,
                    xs_xm=user_xs.xs_xm,
                    xs_bj_id=user_xs.xs_bj_id,
                    kcid=course_id,
                    pc=user_info.sys_pc,
                    tjsj=current_time,
                    zt=0  # 0表示未申请
                )
                db.session.add(review)
                
        try:
            db.session.commit()
            return {
                'code': 0,
                'msg': '操作成功',
                'data': None
            }
        except Exception as e:
            db.session.rollback()
            return {
                'code': 1,
                'msg': f'数据库操作失败: {str(e)}',
                'data': None
            }
            
    except Exception as e:
        return {
            'code': 1,
            'msg': f'操作失败: {str(e)}',
            'data': None
        }

# 获取形势与政策成绩
@router.get('/get_politics_scores')
async def get_politics_scores(user_info: dict = Depends(verify_token_and_get_payload),db: Session = DatabaseDep):
    try:
        user_xs = db.query(Student).filter_by(xs_xh=user_info.get('xs_xh')).first()
        if not user_xs:
            return {
                'success': False,
                'msg': '用户信息不存在',
                'data': None
            }
        # 1. 查询及格次数
        sql = text("""
            SELECT COUNT(id) as pass_count 
            FROM kw_xsyzc 
            WHERE CONVERT(FLOAT, cj) >= 60 
            AND xh = :student_no
        """)
        pass_count_result = db.execute(sql, {"student_no": user_xs.xs_xh}).scalar()
        pass_count = pass_count_result if pass_count_result else 0
        
        # 2. 查询国开登记成绩
        sql = text("""
            SELECT MAX(F12) as registered_score 
            FROM tzd_cj_z 
            WHERE F4 = :student_no 
            AND F2 = '04392'
        """)
        registered_score_result = db.execute(sql, {"student_no": user_xs.xs_xh}).scalar()
        registered_score = registered_score_result if registered_score_result else None
        
        # 3. 查询历次成绩列表
        sql = text("""
            SELECT id, xh, xm, cj, kspc, pc 
            FROM kw_xsyzc 
            WHERE xh = :student_no 
            ORDER BY pc
        """)
        scores_result = db.execute(sql, {"student_no": user_xs.xs_xh}).fetchall()
        
        # 构建成绩列表
        scores = []
        for score in scores_result:
            scores.append({
                "id": score.id,
                "student_no": score.xh,
                "name": score.xm,
                "score": float(score.cj) if score.cj else None,
                "exam_batch": score.kspc,
                "semester": score.pc
            })
            
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
            "student_info": {
                "id": user_xs.xs_id,
                "name": user_xs.xs_xm,
                "student_no": user_xs.xs_xh,
                "status": get_status_desc(user_xs.xs_xjzt)
            },
            "summary": {
                "pass_count": pass_count,
                "registered_score": registered_score
            },
            "notice": {
                "requirement": "20秋至22春入学的学生需要有4次及格次数，22秋及22秋以后入学的学生需要有5次及格次数"
            },
            "scores": scores
        }
        
        return {
            "success": True,
            "msg": "success",
            "data": response_data
        }
        
    except Exception as e:
        return {
            "success": False,
            "msg": f"查询失败：{str(e)}",
            "data": None
        }



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

# 获取考试通知单
@router.get('/get_exam_notice')
async def get_exam_notice(user_info: dict = Depends(verify_token_and_get_payload),db: Session = DatabaseDep):

    try:
        user_xs = db.query(Student).filter_by(xs_xh=user_info.get('xs_xh')).first()
        if not user_xs:
            return {
                'success': False,
                'msg': '用户信息不存在',
                'data': None
            }
        # 1. 检查系统是否已导入最新考试通知单
        # 获取系统配置信息
        sys_info = db.query(lw_sys).filter_by(dq1_mc=user_info.get('dq1_mc')).first()
        if not sys_info:
            return {
                'success': False,
                'msg': '系统配置信息不存在',
                'data': None
            }
        
        if not sys_info.sys_istzd:
            return {
                'success': False,
                'msg': '最新考试通知单数据还未导入',
                'data': None
            }

        # 2. 获取学生的考试信息
        # 首先找到学生记录所在行
        sql = text("""
            SELECT id, F1 FROM tzd_kc 
            WHERE F1 LIKE :student_no
        """)
        result = db.execute(sql, {"student_no": f'%{user_xs.xs_xh}%'}).first()
        
        if not result:
            return {
                'success': False,
                'msg': '未找到考试信息',
                'data': {
                    'student_info': {
                        'id': user_xs.xs_id,
                        'name': user_xs.xs_xm,
                        'student_no': user_xs.xs_xh,
                        'status': get_status_desc(user_xs.xs_xjzt)
                    },
                    'exams': []
                }
            }
 
        # 获取考试信息（从学生记录后两行开始）
        start_id = result.id + 2
        exams = []
        
        # 循环读取考试信息，直到遇到非数字的试卷号
        while True:
            sql = text("""
                SELECT id, F1, F2, F3, F4, F5, F6, F7, F8, F9 
                FROM tzd_kc 
                WHERE id = :id
            """)
            exam = db.execute(sql, {"id": start_id}).first()
            
            if not exam or not exam.F1 or not exam.F1.strip().isdigit():
                break
            exams.append({
                'paper_no': exam.F1,        # 试卷号
                'subject': exam.F2,         # 考试科目
                'exam_type': exam.F3,       # 考核方式
                'room_no': exam.F4,         # 考场号
                'seat_no': exam.F5,         # 座位号
                'exam_date': exam.F6,       # 考试日期
                'exam_time': exam.F7,       # 考试时间
                'is_makeup': exam.F8,       # 是否留考
                'classroom': exam.F9        # 教室
            })            
            start_id += 1
        
        # 循环结束，返回数据
        return {
            'success': True,
            'msg': '获取成功',
            'data': {
                'student_info': {
                    'id': user_xs.xs_id,
                    'name': user_xs.xs_xm,
                    'student_no': user_xs.xs_xh,
                    'status': get_status_desc(user_xs.xs_xjzt)
                },
                'exams': exams
            }
        }
    except Exception as e:
        return {
            'success': False,
            'msg': f'获取考试通知单失败: {str(e)}',
            'data': None
        }

# 获取学生教学计划中的所有课程
@router.get('/courses')
async def get_student_courses(user_info: dict = Depends(verify_token_and_get_payload),db: Session = DatabaseDep):
    try:

        # 获取学生的所有课程
        courses = db.query(BkSxbkb).filter_by(F3=user_info.get('xs_xh')).all()

        # 构建课程列表
        course_list = []
        for course in courses:
            course_list.append({
                'course_name': course.F8,      # 报考课程名称
                'course_id': course.F9,        # 报考课程ID
                'exam_method': course.F10,     # 考核方式
                'paper_no': course.F12,        # 报考试卷号
                'direct': course.F13           # 直属
            })
            
        # 构建返回数据
        response_data = {
            'courses': course_list
        }
        
        return {
            'code': 0,
            'msg': '获取成功',
            'data': response_data
        }
        
    except Exception as e:
        return {
            'code': 1,
            'msg': f'获取学生课程信息失败: {str(e)}',
            'data': None
        }



# 获取预支付信息
@router.get('/payXfByOrderNo')
async def payByOrderNo(openid_code: str,db: Session = DatabaseDep,current_user: dict = Depends(verify_token_and_get_payload)):
    try:
        # 计算学生是否需要缴费，第三个学期以后才需要缴费================
        sys_info = db.query(lw_sys).filter_by(dq1_mc=current_user.get('dq1_mc')).first()
        student = db.query(Student).filter_by(xs_xh=current_user.get('xs_xh')).first()


        # 通过账单计算是否欠费，如果欠费，判断是否已经有未缴费订单，没有则需要生成订单
        tuition_info = db.query(wxxs_xf_zd).filter_by(bjid=student.xs_bj_id).first()
        
        # 初始化学费信息
        fee_data = {
            'xf_1': 0,  # 第一学年学费
            'xf_2': 0,  # 第二学年学费
            'sf_1': 0,  # 第一学年书费
            'sf_2': 0   # 第二学年书费
        }

        if tuition_info:
            fee_data.update({
                'xf_1': tuition_info.xf_1 if tuition_info.xf_1 else 0,
                'xf_2': tuition_info.xf_2 if tuition_info.xf_2 else 0,
                'sf_1': tuition_info.sf_1 if tuition_info.sf_1 else 0,
                'sf_2': tuition_info.sf_2 if tuition_info.sf_2 else 0,
            })

        # 查询个人账单（如果有则覆盖班级账单）
        personal_bill = db.query(wxxs_xf_zdgr).filter_by(xsxh=student.xs_xh).first()

        if personal_bill:
            fee_data.update({
                'xf_1': personal_bill.xf_1 if personal_bill.xf_1 else fee_data['xf_1'],
                'xf_2': personal_bill.xf_2 if personal_bill.xf_2 else fee_data['xf_2'],
                'sf_1': personal_bill.sf_1 if personal_bill.sf_1 else fee_data['sf_1'],
                'sf_2': personal_bill.sf_2 if personal_bill.sf_2 else fee_data['sf_2'],
            })
        # 计算应缴总额
        total_tuition = fee_data['xf_1'] + fee_data['xf_2']  # 应缴总学费
        total_books = fee_data['sf_1'] + fee_data['sf_2']    # 应缴总书费

        # 查询实际缴费情况
        payment_info = db.query(wxxs_xf_info).filter_by(F6=student.xs_xh).first()

        # 初始化实际缴费金额
        actual_payment = {
            'paid_tuition': 0,  # 实际缴纳学费
            'paid_books': 0,    # 实际缴纳书费
            'reduction': 0      # 减免费用
        }

        # 处理第一个表(wxxs_xf_info)的缴费记录
        if payment_info:
            # 学费 
            xf1 = int(payment_info.F10) if payment_info.F10 is not None else 0
            xf2 = int(payment_info.F12) if payment_info.F12 is not None else 0
            xf3 = int(payment_info.F14) if payment_info.F14 is not None else 0
            xf4 = int(payment_info.F16) if payment_info.F16 is not None else 0
            xf5 = int(payment_info.F18) if payment_info.F18 is not None else 0
            
            # 书费 - 
            sf1 = int(payment_info.F11) if payment_info.F11 is not None else 0
            sf2 = int(payment_info.F13) if payment_info.F13 is not None else 0
            sf3 = int(payment_info.F15) if payment_info.F15 is not None else 0
            sf4 = int(payment_info.F17) if payment_info.F17 is not None else 0
            sf5 = int(payment_info.F19) if payment_info.F19 is not None else 0

            # 减免
            jm = int(payment_info.F22) if payment_info.F22 is not None else 0
            
            # 计算总额（以分为单位）
            # 缴费表存储单位是元，需要乘以100转换为分
            zxf = (xf1 + xf2 + xf3 + xf4 + xf5) * 100  # 学费转为分
            zsf = (sf1 + sf2 + sf3 + sf4 + sf5) * 100  # 书费转为分
            jm = jm * 100  # 减免转为分
            

            
            # 初始化实际缴费金额
            actual_payment['paid_tuition'] = zxf 
            actual_payment['paid_books'] = zsf 
            actual_payment['reduction'] = jm 

        # 查询并加上第二个表(wxxs_xf_payinfo)的缴费记录
        payinfo_sql = text("""
            SELECT o_xf, o_sf, o_jm 
            FROM wxxs_xf_payinfo 
            WHERE o_xh = :xsxh 
            AND o_status = 1 
            AND o_tk_status = 0 
            AND o_xxtk_status = 0
            AND o_delete = 0
            AND o_close = 0
        """)
        payinfo_results = db.execute(payinfo_sql, {'xsxh': student.xs_xh}).fetchall()

        # 使用调试工具详细打印查询结果
        # debug_print_query_results(
        #     results=payinfo_results,
        #     title="缴费信息查询结果",
        #     student_id=student.xs_xh
        # )

        # 同时写入日志文件
        # logger.info(f'缴费信息查询 - 学号: {student.xs_xh}, 结果数量: {len(payinfo_results)}')
        # 加上本系统的缴费记录（这些金额应该已经是分为单位）
        if payinfo_results:
            for record in payinfo_results:
                # 直接加到总额上（因为已经是分为单位）
                actual_payment['paid_tuition'] += (record.o_xf or 0)   
                actual_payment['paid_books'] += (record.o_sf or 0)     
                actual_payment['reduction'] += (record.o_jm or 0)      




        # 计算剩余应缴费用------------这里需要考虑减免（应交学费-已交学费-减免，如果小于0，则剩余应缴费用为0）
        remaining_pay = (total_tuition + total_books) - (actual_payment['paid_tuition'] + actual_payment['paid_books'])-actual_payment['reduction']



        if remaining_pay <= 0:
            return {
                'success': False,
                'msg': '已交费用超过应缴费用，不需要再缴费',
                'data': None
            }

        # 查询订单信息
        toPayOrder = db.query(wxxs_xf_payinfo).filter_by(o_xh=current_user.get('xs_xh'),o_status=0,o_close=0,o_tk_status=0,o_delete=0).first()
        wx_pay = WxPayUtil()
        wx_util = WxUtils()
        openidResult = wx_util.get_openid_and_session_key(openid_code)
        openid = openidResult.get('openid')
        if toPayOrder:
            if toPayOrder.o_type != 5:
                return {
                    'success': False,
                    'msg': '该订单不是小程序生成的订单，请使用使用原方式缴费',
                    'data': None
                }

            
            query_result = wx_pay.query_order(toPayOrder.o_order_no)

            # 'SUCCESS': '支付成功',
            # 'REFUND': '转入退款',
            # 'NOTPAY': '未支付',
            # 'CLOSED': '已关闭',
            # 'REVOKED': '已撤销',
            # 'USERPAYING': '用户支付中',
            # 'PAYERROR': '支付失败',
            # 'UNKNOWN': '未知错误'
            if query_result.get('trade_state') == 'SUCCESS':
                toPayOrder.o_status = 1
                toPayOrder.o_paytime = query_result['success_time']
                toPayOrder.o_trade_no = query_result['transaction_id']
                db.commit()
                return {
                    'success': False,
                    'msg': '订单已支付，不需要再缴费',
                    'data': None
                }
            elif query_result.get('trade_state') == 'NOTPAY':
                # 这种情况，原来的订单号还可以用，重新下单生成新的微信那边的订单号即可



                pay_result = wx_pay.create_pay_info(
                    openid=openid,
                    out_trade_no=toPayOrder.o_order_no,
                    total_fee=toPayOrder.o_money, 
                    description=toPayOrder.o_body,
                    business_type='wxxs_xf_payinfo'
                )
                if pay_result.get('success'):
                    toPayOrder.prepay_id = pay_result['prepay_id']
                    db.commit()
                    return {
                        'success': True,
                        'msg': '获取支付参数成功',
                        'data': pay_result['pay_params']
                    }
                else:
                    return {
                        'success': False,
                        'msg': pay_result['req_des']+':'+pay_result['error_code']+':'+pay_result['error_desc'],
                        'data': None
                    }
            else:
                # 订单已关闭/撤销/失败，关闭旧订单，重新生成新订单
                toPayOrder.o_close = 1
                db.commit()
                toPayOrder = None  # 置空，走下面的新建订单逻辑

        if toPayOrder is None:
            # 生成订单
            # 生成订单号 (学号 + 时间戳)
            order_no = f"LSJF{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(1000, 9999)}"
            toPayOrder = wxxs_xf_payinfo(
                o_xm=student.xs_xm,
                o_xh=student.xs_xh,
                o_sfzh=student.xs_sfzh,
                o_sj=student.xs_dh,
                o_body=f'黔东南开放大学-老生缴纳第二年剩余学费-{student.xs_xm}-JSAPIX',
                o_money=remaining_pay,
                o_xf=total_tuition-actual_payment['paid_tuition'],
                o_sf=total_books-actual_payment['paid_books'],
                o_jm=actual_payment['reduction'],
                o_paytype='weixin',
                o_type='5',
                o_status=0,
                o_tk_status=0,
                o_close=0,
                o_delete='0',
                o_addtime=datetime.now(),
                o_pc = sys_info.sys_pc,
                o_isxs='0',
                o_order_no=order_no,
                o_xxtk_status=0,
                o_xx_status=0
            )
            db.add(toPayOrder)
            db.commit()

        # 临时测试用
        # print(current_user.get('xs_xh'))
        # if current_user.get('xs_xh') == '2252001253085' :
        #     feiyong = 1
        # else:
        #     feiyong = toPayOrder.o_money

        
        pay_result = wx_pay.create_pay_info(
            openid=openid,
            out_trade_no=toPayOrder.o_order_no,
            total_fee=toPayOrder.o_money,
            description=toPayOrder.o_body,
            business_type='wxxs_xf_payinfo'
        )
        # 需要同时判断请求状态和业务状态来确定返回的参数
        if pay_result.get('success'):
            toPayOrder.prepay_id = pay_result['prepay_id']
            db.commit()
            return {
                'success': True,
                'msg': '创建支付订单成功',
                'data': pay_result['pay_params']
            }
        else:
            if pay_result.get('req_code'):
                return {
                    'success': False,
                    'msg': pay_result['req_des']+':'+pay_result['error_code']+':'+pay_result['error_desc'],
                    'data': None
                }
            else:
                return {
                    'success': False,
                    'msg': pay_result['req_des']+':'+pay_result['error_code']+':'+pay_result['error_desc'],
                    'data': None
                }
    except Exception as e:
        return {
            'success': False,
            'msg': f'生成支付参数失败: {str(e)}',
            'data': None
        }



def get_all_scores(student_id, formatted_plan_courses, db: Session):
    """获取所有成绩信息，包括综合成绩、网考成绩等
    :param student_id: 学号
    :param formatted_courses: 格式化后的课程信息列表
    :return: 成绩信息列表
    """
    try:
        if not formatted_plan_courses:
            return {
                'code': True,
                'msg': 'success',
                'data': []
            }

        # 提取课程ID列表
        course_ids = [course['kcid'] for course in formatted_plan_courses]
        course_ids_str = "','".join(course_ids)
        
        # 创建结果列表，初始化为formatted_courses的副本
        results = []
        for course in formatted_plan_courses:
            course_copy = course.copy()
            # 添加新字段
            course_copy.update({
                'xk_score': None,  # 校考成绩
                'xk_bl': None,     # 形考比例
                'zk_score': None,  # 中考成绩
                'zh_score': None,  # 综合成绩
                'sjg': None,       # 是否双及格
                'status': None,    # 成绩状态
                'source': None     # 成绩来源
            })
            results.append(course_copy)
        
        # 创建课程ID到结果对象的映射，方便后续更新
        course_map = {course['kcid']: course for course in results}
        # 1. 批量查询zcjb表的最高综合成绩
        zcjb_sql = f"""
                    WITH RankedScores AS (
                        SELECT
                            xh,
                            kcid,
                            sjh,
                            zhcj,
                            ROW_NUMBER() OVER (PARTITION BY kcid ORDER BY zhcj DESC) as rn
                        FROM zcjb
                        WHERE xh = '{student_id}' 
                        AND kcid IN ('{course_ids_str}')
                    )
                    SELECT
                        xh,
                        kcid,
                        sjh,
                        zhcj
                    FROM RankedScores
                    WHERE rn = 1;
        """
        # 使用当前会话执行原生SQL，保持事务一致性
        result_zcjb = db.execute(text(zcjb_sql))
        for row in result_zcjb:
            if row.kcid in course_map:
                course_map[row.kcid]['zh_score'] = str(row.zhcj) if row.zhcj is not None else None
                course_map[row.kcid]['xk_score'] = None
                course_map[row.kcid]['zk_score'] = None
                course_map[row.kcid]['sjh'] = row.sjh
                course_map[row.kcid]['source'] = 'zcjb'

        # 2. 批量查询tzd_cj_z表的所有成绩
        # F9,F10,F11,F12,F15，F18
        # 形考成绩，形考比例，终考成绩，综合成绩，是否双及格，成绩状态
        # "xk_score": F9
        # "xk_bl": F10
        # "zk_score": F11
        # "zh_score": F12
        # "sjg": F15
        # "status":F18
        tzd_sql = f"""
                    WITH RankedScores AS (
                        SELECT
                            id,
                            F3 as sjh,
                            F4 as xh,
                            F2 as kcid,
                            F12,
                            F9 as xk_bl,
                            F10 as xk_score,
                            F11 as zk_score,
                            F15 as sjg,
                            F18 as status,
                            ROW_NUMBER() OVER (PARTITION BY F2 ORDER BY F12 DESC) as rn
                        FROM tzd_cj_z
                        WHERE F4 = '{student_id}'
                        AND F2 IN ('{course_ids_str}')
                    )
                    SELECT
                        id,
                        sjh,
                        xh,
                        kcid,
                        F12 as zh_score,
                        xk_score,
                        xk_bl,
                        zk_score,
                        sjg,
                        status
                    FROM RankedScores
                    WHERE rn = 1;
        """
        # 用于存储每个课程的成绩记录
        try:
            # 执行两个查询，使用当前会话保持事务一致性
            result_tzd_cj_z = list(db.execute(text(tzd_sql)))
            result_zcjb = list(db.execute(text(zcjb_sql)))
                
                
            # 将两个结果转换为字典，方便查找
            tzd_cj_z_map = {}
            zcjb_map = {}
            
            # 处理 tzd_cj_z 表的结果
            for row in result_tzd_cj_z:
                try:
                    # 将行转换为字典
                    row_dict = dict(row._mapping)
                    
                    if row_dict['kcid'] not in tzd_cj_z_map:  # 使用 kcid 作为课程ID
                        tzd_cj_z_map[row_dict['kcid']] = {
                            'sjh': row_dict.get('sjh'),      # 试卷号
                            'xk_score': row_dict.get('xk_score'),  # 形考成绩
                            'xk_bl': row_dict.get('xk_bl'),    # 形考比例
                            'zk_score': row_dict.get('zk_score'), # 终考成绩
                            'zh_score': row_dict.get('zh_score'), # 综合成绩
                            'sjg': row_dict.get('sjg'),      # 是否双及格
                            'status': row_dict.get('status')    # 成绩状态
                        }
                except Exception as e:
                    continue
            
            # 处理 zcjb 表的结果
            for row in result_zcjb:
                try:
                    # 将行转换为字典
                    row_dict = dict(row._mapping)                        
                    if row_dict['kcid'] not in zcjb_map:
                        zcjb_map[row_dict['kcid']] = {
                            'sjh': row_dict.get('sjh'),
                            'xk_score': None,
                            'xk_bl': None,
                            'zk_score': None,
                            'zh_score': row_dict.get('zhcj'),  # 综合成绩
                            'sjg': None,
                            'status': None
                        }
                except Exception as e:
                    continue
            
            #遍历每个课程，比较成绩并选择
            for course in results:
                try:
                    kcid = course['kcid']
                    row_tzd = tzd_cj_z_map.get(kcid)
                    row_zcjb = zcjb_map.get(kcid)
                    
                    # 如果两个表都没有成绩，继续下一个
                    if not row_tzd and not row_zcjb:
                        continue
                        
                    # 获取两个表的成绩
                    tzd_score = row_tzd['zh_score'] if row_tzd else None
                    zcjb_score = row_zcjb['zh_score'] if row_zcjb else None
                    
                    # 判断成绩类型和大小
                    selected_row = None
                    selected_source = None
                    
                    # 如果两个表都有成绩
                    if tzd_score is not None and zcjb_score is not None:
                        # 尝试转换为数字进行比较
                        try:
                            tzd_num = float(tzd_score)
                            zcjb_num = float(zcjb_score)
                            # 如果都能转为数字，取较高的
                            if tzd_num >= zcjb_num:
                                selected_row = row_tzd
                                selected_source = 'tzd_cj_z'
                            else:
                                selected_row = row_zcjb
                                selected_source = 'zcjb'
                        except (ValueError, TypeError):
                            # 如果转换失败，说明至少有一个是文字
                            # 如果都是文字，优先取tzd_cj_z的值
                            selected_row = row_tzd
                            selected_source = 'tzd_cj_z'
                    else:
                        # 如果只有一个表有成绩，取有成绩的那个
                        if tzd_score is not None:
                            selected_row = row_tzd
                            selected_source = 'tzd_cj_z'
                        elif zcjb_score is not None:
                            selected_row = row_zcjb
                            selected_source = 'zcjb'
                    
                    # 如果没有找到有效成绩，继续下一个
                    if not selected_row:
                        continue
                        
                    # 更新课程信息
                    if selected_source == 'tzd_cj_z':
                        course.update({
                            'sjh': selected_row['sjh'],
                            'xk_score': str(selected_row['xk_score']) if selected_row['xk_score'] is not None else None,
                            'xk_bl': str(selected_row['xk_bl']) if selected_row['xk_bl'] is not None else None,
                            'zk_score': str(selected_row['zk_score']) if selected_row['zk_score'] is not None else None,
                            'zh_score': str(selected_row['zh_score']) if selected_row['zh_score'] is not None else None,
                            'sjg': str(selected_row['sjg']) if selected_row['sjg'] is not None else None,
                            'status': str(selected_row['status']) if selected_row['status'] is not None else None,
                            'source': 'tzd_cj_z'
                        })
                    else:
                        course.update({
                            'sjh': selected_row['sjh'],
                            'xk_score': None,
                            'xk_bl': None,
                            'zk_score': None,
                            'zh_score': str(selected_row['zh_score']) if selected_row['zh_score'] is not None else None,
                            'sjg': None,
                            'status': None,
                            'source': 'zcjb'
                        })
                        
                    
                except Exception as e:
                    continue
        except Exception as e:
            raise

        # 3. 处理特殊课程
        special_courses = []
        
        # 英语课程
        eng_courses = [c for c in results if c['kcid'] in ['01818', '04020', '04016', '04012', '04008', '04004']]
        if eng_courses:
            # 查询网考成绩（英语）
            wkcjb_eng_sql = f"""
                SELECT DISTINCT xh, wkkm, cjdm, kssj
                FROM wkcjb 
                WHERE xh = '{student_id}' 
                AND wkkm = '63' 
                AND cjdm = '&&'
                ORDER BY kssj DESC
            """
            eng_net_pass = False
            # 使用当前会话执行查询
            result = db.execute(text(wkcjb_eng_sql))
            if result.rowcount > 0:
                eng_net_pass = True
            
            # 更新英语课程成绩
            if eng_net_pass:
                for course in eng_courses:
                    course['zh_score'] = '网替合格'
                    course['source'] = 'wkcjb'
                    special_courses.append(course['kcid'])
        
        # 计算机课程
        comp_courses = [c for c in results if c['kcid'] == '00808']
        if comp_courses:
            # 查询计算机网考成绩
            wkcjb_comp_sql = f"""
                SELECT DISTINCT xh
                FROM wkcjb 
                WHERE xh = '{student_id}' 
                AND wkkm = '69' 
                AND cjdm = '&&'
            """
            comp_net_pass = False
            # 使用当前会话执行查询
            result = db.execute(text(wkcjb_comp_sql))
            if result.rowcount > 0:
                comp_net_pass = True
            
            # 如果没有网考合格，检查免考
            comp_exempt = False
            if not comp_net_pass:
                wkmkb_sql = f"""
                    SELECT DISTINCT xh
                    FROM wkmkb 
                    WHERE xh = '{student_id}' 
                    AND mkkm = '04'
                """
                # 使用当前会话执行查询
                result = db.execute(text(wkmkb_sql))
                if result.rowcount > 0:
                    comp_exempt = True
            
            # 更新计算机课程成绩
            for course in comp_courses:
                if comp_net_pass:
                    course['zh_score'] = '网考合格'
                    course['source'] = 'wkcjb'
                    special_courses.append(course['kcid'])
                elif comp_exempt:
                    course['zh_score'] = '免考合格'
                    course['source'] = 'wkmkb'
                    special_courses.append(course['kcid'])
        
        # 4. 处理没有成绩的课程
        for course in results:
            if course['source'] is None and course['kcid'] not in special_courses:
                course['zh_score'] = '无考试记录'
                course['source'] = None

        return {
            'success': True,
            'msg': 'success',
            'data': results
        }

    except Exception as e:
        return {
            'success': False,
            'msg': f'获取成绩信息失败: {str(e)}',
            'data': None
        }


# 获取学生详细成绩信息
# @router.get('/scores/detail')
# async def get_detailed_scores(user_info: dict = Depends(verify_token_and_get_payload),db: Session = DatabaseDep):
#     try:
#         # 获取系统配置信息
#         sys_info = db.query(lw_sys).filter_by(dq1_mc=user_info['dq1_mc']).first()
#         if not sys_info:    
#             return {
#                 'code': 1,
#                 'message': '系统配置信息不存在',
#                 'data': None
#             }
#         class_info = db.query(Class).filter_by(bj_id=user_info['bj_id']).first()
#         if not class_info:
#             return {
#                 'code': 1,
#                 'msg': '未找到班级信息',
#                 'data': None
#             }
            
#         # 获取班级计划信息
#         # 获取班级计划信息
#         plan_id = class_info.bj_planid
#         education_level = class_info.bj_cc  # 层次
#         student_pc = str(class_info.bj_nd) + class_info.bj_xqdm
#         system_pc = str(sys_info.sys_xq1_nd) + str(sys_info.sys_xq1_xq)
#         major = class_info.bj_zy  # 专业
#         # 获取教学计划课程列表
#         formatted_plan_courses = get_plan_courses_newJHZ(plan_id,education_level,student_pc,system_pc,major,db)
        
#         if not formatted_plan_courses:
#             return {
#                 'code': 1,
#                 'msg': '未找到课程信息',
#                 'data': None
#             }
#         # 获取成绩信息
#         score_result = get_all_scores(user_info['xs_xh'], formatted_plan_courses, db)
#         return jsonify(score_result)
        
#     except Exception as e:
#         return {
#             'code': 500,
#             'message': f'获取详细成绩信息失败: {str(e)}',
#             'data': None
#         }


# 获取学生报考状态信息
# @router.get('/scores/get_bk_detail')
# async def get_bk_detail(current_user: dict = Depends(verify_token_and_get_payload),db: Session = DatabaseDep):

#     try:
#         # 获取系统配置信息
#         sys_info = db.query(lw_sys).filter_by(dq1_mc=current_user.get('dq1_mc')).first()
#         if not sys_info:
#             return {
#                 'success': False,
#                 'msg': '系统配置信息不存在',
#                 'data': None
#             }
#         student = db.query(Student).filter_by(xs_xh=current_user.get('xs_xh')).first()
#         class_info = db.query(Class).filter_by(bj_id=current_user.get('bj_id')).first()
#         if not class_info:
#             return {
#                 'success': False,
#                 'msg': '未找到班级信息',
#                 'data': None
#             }

#         student_all_courses = db.query(TzdCjZJsh).filter_by(xh=current_user.get('xs_xh'),nd=student.xs_nd,xqdm=student.xs_xqdm).all()
#         student_chongxiu_courses = db.query(jw_chongxiu).filter_by(xh=current_user.get('xs_xh'),pc = sys_info.sys_pc).all()
#         # 获取学生报考记录
#         student_bk_records = db.query(bk_bkb).filter_by(xsxh=current_user.get('xs_xh'),pc = sys_info.sys_pc).all()

#         # 处理数据：筛选不及格课程和重修课程
#         failed_courses = []

#         # 1. 处理重修课程 - 无条件加入补考课程中
#         for chongxiu_course in student_chongxiu_courses:
#             # 查询该课程的报考状态
#             bk_status = None
#             for bk_record in student_bk_records:
#                 if bk_record.kcid == chongxiu_course.kcid:
#                     bk_status = {
#                         'is_registered': bk_record.isbk == 1,  # 根据isbk字段判断是否已报考
#                         'ispay': bk_record.ispay,  # 直接返回ispay字段：1=已支付，2=待支付，0=无意义
#                         'registration_time': bk_record.bksj if hasattr(bk_record, 'bksj') else None
#                     }
#                     break

#             if not bk_status:
#                 bk_status = {
#                     'is_registered': False,  # 没有记录则报考为false
#                     'ispay': 0,  # 没有记录时ispay为0
#                     'registration_time': None
#                 }

#             failed_courses.append({
#                 'course_id': chongxiu_course.kcid,
#                 'course_name': chongxiu_course.kcmc,
#                 'score': None,  # 重修课程没有原始成绩
#                 'type': 'chongxiu',  # 标记为重修课程
#                 'registration_status': bk_status
#             })

#         # 2. 处理所有课程成绩 - 只取小于60分的课程
#         for course in student_all_courses:
#             try:
#                 # 将成绩字符串转换为浮点数
#                 score_float = float(course.zhcj) if course.zhcj and course.zhcj.replace('.', '').isdigit() else 0.0

#                 # 只处理小于60分的课程
#                 if score_float < 60.0:
#                     # 检查是否已经在重修课程中（避免重复）
#                     is_duplicate = any(fc['course_id'] == course.kcid for fc in failed_courses)

#                     if not is_duplicate:
#                         # 查询该课程的报考状态
#                         bk_status = None
#                         for bk_record in student_bk_records:
#                             if bk_record.kcid == course.kcid:
#                                 bk_status = {
#                                     'is_registered': bk_record.isbk == 1,  # 根据isbk字段判断是否已报考
#                                     'ispay': bk_record.ispay,  # 直接返回ispay字段：1=已支付，2=待支付，0=无意义
#                                     'registration_time': bk_record.bksj if hasattr(bk_record, 'bksj') else None
#                                 }
#                                 break

#                         if not bk_status:
#                             bk_status = {
#                                 'is_registered': False,  # 没有记录则报考为false
#                                 'ispay': 0,  # 没有记录时ispay为0
#                                 'registration_time': None
#                             }

#                         failed_courses.append({
#                             'course_id': course.kcid,
#                             'course_name': course.kcmc,
#                             'score': score_float,
#                             'type': 'failed',  # 标记为不及格课程
#                             'registration_status': bk_status
#                         })
#             except (ValueError, TypeError) as e:
#                 # 如果成绩转换失败，记录日志但继续处理
#                 logger.warning(f"成绩转换失败: 课程{course.kcmc}, 成绩{course.zhcj}, 错误: {str(e)}")
#                 continue


#         un_pay_order = db.query(wxxs_payinfo).filter_by(o_xh=current_user.get('xs_xh'),o_status=0,o_close=0,o_tk_status =0,o_pc = sys_info.sys_pc).first()


















        







#         return {
#             'success': True,
#             'msg': '获取补考课程信息成功',
#             'data': {
#                 'failed_courses': failed_courses,  # 需要补考的课程列表
#                 'un_pay_order': un_pay_order,  # 未支付订单
#                 'bKCloseDate': int(sys_info.sys_jzrq.timestamp()) if sys_info.sys_jzrq else None,
#             }
#         }
        
#     except Exception as e:
#         return {
#             'success': False,
#             'msg': f'获取详细成绩信息失败: {str(e)}',
#             'data': None
#         }

# 报考/取消报考接口
@router.get('/toggle_bk_registration')
async def toggle_bk_registration(
    course_id: str,
    action: str,  # 'register' 或 'cancel'
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """
    报考/取消报考接口

    Args:
        course_id: 课程ID
        action: 操作类型 ('register' 或 'cancel')

    Returns:
        操作结果
    """
    try:
        # 获取系统配置信息
        sys_info = db.query(lw_sys).filter_by(dq1_mc=current_user.get('dq1_mc')).first()
        if not sys_info:
            return {
                'success': False,
                'msg': '系统配置信息不存在',
                'data': None
            }

        # 检查是否有未支付订单
        unpaid_order = db.query(wxxs_payinfo).filter_by(
            o_xh=current_user.get('xs_xh'),
            o_status=0,
            o_close=0,
            o_tk_status=0,
            o_pc=sys_info.sys_pc
        ).first()

        if unpaid_order:
            return {
                'success': False,
                'msg': '您还有未支付的订单，请先支付后再进行操作',
                'data': None
            }

        # 检查报考截止时间
        if sys_info.sys_jzrq:
            import datetime
            now = datetime.datetime.now()
            if now > sys_info.sys_jzrq:
                return {
                    'success': False,
                    'msg': '报考已截止',
                    'data': None
                }

        # 查找现有的报考记录
        existing_record = db.query(bk_bkb).filter_by(
            xsxh=current_user.get('xs_xh'),
            kcid=course_id,
            pc=sys_info.sys_pc
        ).first()

        if action == 'register':
            # 报考操作
            if existing_record:
                # 如果已经有记录，更新 isbk 为 1
                existing_record.isbk = 1
                db.commit()

                return {
                    'success': True,
                    'msg': '报考成功',
                    'data': {
                        'course_id': course_id,
                        'is_registered': True,
                        'is_paid': False
                    }
                }
            else:
                # 创建新的报考记录

















                new_record = bk_bkb(
                    xsxh=current_user.get('xs_xh'),
                    kcid=course_id,
                    pc=sys_info.sys_pc,
                    isbk=1,
                    ispay=0,  # 待支付状态
                    date=datetime.datetime.now()
                )
                db.add(new_record)
                db.commit()

                return {
                    'success': True,
                    'msg': '报考成功',
                    'data': {
                        'course_id': course_id,
                        'is_registered': True,
                        'is_paid': False
                    }
                }

        elif action == 'cancel':
            # 取消报考操作
            if existing_record:
                if existing_record.ispay == 1:
                    return {
                        'success': False,
                        'msg': '已缴费的课程不能取消报考',
                        'data': None
                    }

                # 设置 isbk 为 0
                existing_record.isbk = 0
                existing_record.ispay = 0  # 重置支付状态
                db.commit()

                return {
                    'success': True,
                    'msg': '取消报考成功',
                    'data': {
                        'course_id': course_id,
                        'is_registered': False,
                        'is_paid': False
                    }
                }
            else:
                return {
                    'success': False,
                    'msg': '未找到报考记录',
                    'data': None
                }
        else:
            return {
                'success': False,
                'msg': '无效的操作类型',
                'data': None
            }

    except Exception as e:
        logger.error(f"报考/取消报考操作失败: {str(e)}")
        return {
            'success': False,
            'msg': f'操作失败: {str(e)}',
            'data': None
        }

# 获取教学计划总表
def get_plan_courses_newJHZ(plan_id,education_level,student_pc,system_pc,major,db: Session):
    course_ids = []
    formatted_courses = []

    current_semester = calculate_semester(student_pc,system_pc)
    # 根据学期构建查询SQL
    if current_semester == 1:
        return {
            'success': False,
            'msg': '第一学期没有课程信息',
            'data': None
        }
    if current_semester == 2:
        sql = text(f"""
            SELECT * FROM jh_z 
            WHERE gzh = :plan_id AND pc = :pc AND (ksxq LIKE '1%') 
            ORDER BY ksxq ASC
        """)
    elif current_semester == 3:
        sql = text(f"""
            SELECT * FROM jh_z 
            WHERE gzh = :plan_id AND pc = :pc AND (ksxq LIKE '1%' OR ksxq LIKE '2%') 
            ORDER BY ksxq ASC
        """)
    elif current_semester == 4:
        sql = text(f"""
            SELECT * FROM jh_z 
            WHERE gzh = :plan_id AND pc = :pc AND (ksxq LIKE '1%' OR ksxq LIKE '2%' OR ksxq LIKE '3%') 
            ORDER BY ksxq ASC
        """)
    else:
        sql = text(f"""
            SELECT * FROM jh_z 
            WHERE gzh = :plan_id AND pc = :pc
            ORDER BY ksxq ASC
        """)
    plan_courses = db.execute(sql, {"plan_id": plan_id,"pc": student_pc}).fetchall()
    if not plan_courses:
        return None
    for course in plan_courses:
        try:
            # 尝试通过属性访问
            if hasattr(course, 'id'):
                course_info = {
                    'kcid': course.kcid, #课程ID
                    'course_name': course.kcmc, #课程名称
                    'course_xuefen': course.kcxf, #学分
                    'course_type': course.kclx,    #统设，非统设
                    'course_semester': course.ksxq,   #建议开设学期
                    'course_xingzhi': course.kcxz,  #必修，选修
                    'course_exam_unit': course.ksdw  #考试单位，总部分部
                }
            if course_info['kcid']:
                course_ids.append(course_info['kcid'])
                formatted_courses.append(course_info)
        except Exception as e:
            continue

    # 处理补修课程
    if education_level == '本科':
        sql2 = text(f"""
            select * from jhbx 
            where F2='{major}' and F7='{student_pc}' 
            order by id asc
        """)
        bx_courses = db.execute(sql2).fetchall()

        for bx_course in bx_courses:
            try:
                # 创建补修课程信息
                bx_course_info = {
                    'kcid': bx_course.F4, #课程ID
                    'course_name': bx_course.F5, #课程名称
                    'course_xuefen': bx_course.F6, #学分
                    'course_type': '非统设',    #统设，非统设
                    'course_semester': '1',   #建议开设学期
                    'course_xingzhi': '补修',  #必修，选修
                    'course_exam_unit': '分部' #考试单位，总部分部
                }
                
                # 添加到课程列表和ID列表中
                if bx_course_info['kcid']:
                    course_ids.append(bx_course_info['kcid'])
                    formatted_courses.append(bx_course_info)
            except Exception as e:
                continue
    return formatted_courses

def calculate_semester(student_batch, current_batch):
    """计算当前学期数
    
    Args:
        student_batch (str): 学生批次,如202403 
        current_batch (str): 当前批次,如202503
        
    Returns:
        int: 当前学期数
    """
    try:
        # 提取年份和学期
        student_year = int(student_batch[:4])
        student_term = int(student_batch[4:])
        current_year = int(current_batch[:4]) 
        current_term = int(current_batch[4:])

        # 计算年份差
        year_diff = current_year - student_year

        # 计算学期差
        # 03表示第一学期，09表示第二学期
        student_term_num = 1 if student_term == 3 else 2
        current_term_num = 1 if current_term == 3 else 2

        # 计算总学期数
        total_terms = year_diff * 2 + (current_term_num - student_term_num) + 1

        # 确保学期数在1-6之间
        return max(1, min(total_terms,16))

    except Exception as e:
        print(f"计算学期失败: {str(e)}")
        return 1



# 处理课程的报考状态
def get_course_bk_status(student_id, formatted_courses, sys_pc,db: Session):
    try:
        if not formatted_courses:
            return formatted_courses
            
        # 获取所有课程ID
        course_ids = [course.get('kcid') for course in formatted_courses if course.get('kcid')]
        if not course_ids:
            return formatted_courses
            
        # 将课程ID列表转换为逗号分隔的字符串
        course_ids_str = "','".join(course_ids)
        
        # 构建SQL查询bk_bkb表
        bk_sql = f"""
            SELECT kcid, ispay 
            FROM bk_bkb 
            WHERE xsxh = '{student_id}' 
            AND pc = {sys_pc}
            AND kcid IN ('{course_ids_str}')
        """
        
        # 创建课程映射
        course_map = {course['kcid']: course for course in formatted_courses}
        




        # 执行查询并更新课程信息
        result = db.execute(text(bk_sql))
        for row in result:
            if row.kcid in course_map and row.ispay==1:
                course_map[row.kcid]['isBk'] = True
                course_map[row.kcid]['payStatus'] = row.ispay
            else:
                course_map[row.kcid]['isBk'] = False
                course_map[row.kcid]['payStatus'] = row.ispay
        # 设置未找到的课程的默认值
        for course in formatted_courses:
            if 'isBk' not in course:
                course['isBk'] = False
                course['payStatus'] = 5
                
        return formatted_courses
        
    except Exception as e:
        return formatted_courses


class BkPayInfo(BaseModel):
    courses: list
    openid_code: str

# 补考科目报名接口----要恢复
@router.post('/courses/preBkPay')
async def courses_preBkPay(bk_pay_info: BkPayInfo,current_user: dict = Depends(verify_token_and_get_payload),db: Session = DatabaseDep):
    try:

        # 获取请求数据
        courses = bk_pay_info.courses
        openid_code = bk_pay_info.openid_code
        if not courses or not openid_code:
            return {
                'success': False,
                'msg': '缺少必要参数',
                'data': None
            }
            
        if not isinstance(courses, list) or len(courses) == 0:
            return {
                'success': False,
                'msg': '课程信息格式错误',
                'data': None
            }
        # 检查报考科目数量是否超过15科
        if len(courses) > 15:
            return {
                'success': False,
                'msg': '最多只能报考15科课程',
                'data': None
            }
        

        user_xs = db.query(Student).filter_by(xs_xh=current_user.get('xs_xh')).first()
        # 检查是否有未完成的订单
        unpaid_order_sql = text("""
            SELECT id
            FROM bk_bkb 
            WHERE xsxh = :student_id 
            AND pc = :sys_pc
            AND ispay = 2
        """)
        unpaid_order = db.execute(
            unpaid_order_sql, 
            {"student_id": current_user.get('xs_xh'), "sys_pc": current_user.get('sys_pc')}
        ).all()

        if unpaid_order and len(unpaid_order) > 0:
            return {
                'success': False,
                'msg': '您还有未完成的订单，请先完成订单支付',
                'data': None
            }

        # 生成订单号 (学号 + 时间戳)
        order_no = f"bk{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(1000, 9999)}"
        # 检查是否存在相同的订单号
        if db.query(wxxs_payinfo).filter_by(o_order_no=order_no).first():
            return {
                'success': False,
                'msg': '订单号已存在',
                'data': None
            }

        # 获取学生班级信息
        class_info = db.query(Class).filter_by(bj_id=user_xs.xs_bj_id).first()
        if not class_info:
            return {
                'success': False,
                'msg': '未找到班级信息',
                'data': None
            }
            
        current_time = datetime.now()
        # 计算总费用
        total_money = sum(course['fee'] for course in courses)
        description = f'黔东南开放大学-{current_user.get("sys_pc")}批次补考费-{user_xs.xs_xm}-{user_xs.xs_xh}-JSAPIX'

        # # 如果总费用为0（全部是免费课程），直接标记为已支付
        # if total_money == 0:
        #     try:
        #         # 直接更新报考记录为已支付状态
        #         for course in courses:
        #             bk_bkb_info = db.query(bk_bkb).filter_by(
        #                 xsxh=user_xs.xs_xh,
        #                 kcid=course.get('course_id'),
        #                 pc=current_user.get('sys_pc'),
        #                 ispay=2
        #             ).first()
        #             if bk_bkb_info:
        #                 bk_bkb_info.ispay = 1  # 标记为已支付
        #                 bk_bkb_info.isdgzk = 1  # 补修课标记

        #         db.commit()
        #         return {
        #             'success': True,
        #             'msg': '免费课程报考成功',
        #             'data': {
        #                 'is_free': True,
        #                 'message': '所选课程均为免费课程，报考已完成'
        #             }
        #         }
        #     except Exception as e:
        #         db.rollback()
        #         return {
        #             'success': False,
        #             'msg': f'免费课程报考失败: {str(e)}',
        #             'data': None
        #         }

        try:
            # 1. 先创建微信支付记录
            new_pay_info = wxxs_payinfo(
                o_xh=user_xs.xs_xh,
                o_sfzh=user_xs.xs_sfzh,
                o_body=description,
                o_money=total_money,
                o_paytype='weixin',
                o_type=5,  # 5表示小程序补考报名
                o_status=0,  # 未支付
                o_tk_status=0,  # 未退款
                o_close=0,  # 未关闭
                o_delete=0,  # 未删除
                o_order_no=order_no,
                o_addtime=current_time,
                o_pc=str(current_user.get('sys_pc'))
            )
            db.add(new_pay_info)
            db.flush()  # 刷新会话以获取新插入记录的ID

            # 2. 创建报考记录并收集信息
            bk_ids = []
            course_ids = []
            course_names = []
            for course in courses:
                # 检查该课程的补考记录是否已经存在
                print(course.get('course_id'))
                bk_bkb_info = db.query(bk_bkb).filter_by(xsxh=user_xs.xs_xh,kcid=course.get('course_id'),pc=current_user.get('sys_pc'),ispay=0).first()
                if bk_bkb_info:
                    bk_bkb_info.pay_id=new_pay_info.o_id
                    bk_bkb_info.ispay=2
                    #补修课的报考不收钱，所以对其进行标记 1表示已报考，0表示未报考
                    if '#' in course.get('course_name'):
                        bk_bkb_info.isdgzk = 1
                    db.flush()
                    bk_ids.append(str(bk_bkb_info.id))
                    course_ids.append(bk_bkb_info.kcid)
                    course_names.append(bk_bkb_info.kcmc)
                else:
                    return {
                        'success': False,
                        'msg': '您报考的课程不存在，请检查后重试',
                        'data': None
                    }

            # 3. 更新支付记录的报考信息
            new_pay_info.o_bkid = ','.join(bk_ids)
            new_pay_info.o_bkkcid = ','.join(course_ids)
            new_pay_info.o_bkkcmc = ','.join(course_names)
            db.commit()

            # 4. 获取openid
            wx_util = WxUtils()
            openidResult = wx_util.get_openid_and_session_key(openid_code)
            if not openidResult:
                return {
                    'success': False,
                    'msg': '获取openid失败',
                    'data': None
                }
            openid = openidResult.get('openid')

            # 5. 生成微信预支付订单
            wx_pay = WxPayUtil()
            pay_result = wx_pay.create_pay_info(
                openid=openid,
                out_trade_no=order_no,
                total_fee=new_pay_info.o_money*100,
                description=new_pay_info.o_body
            )

            if pay_result.get('success'):
                return {
                    'success': True,
                    'msg': '创建支付订单成功',
                    'data': pay_result['pay_params']
                }
            else:
                if pay_result.get('req_code'):
                    return {
                        'success': False,
                        'msg': pay_result['req_des']+':'+pay_result['error_code']+':'+pay_result['error_desc'],
                        'data': None
                    }
                else:
                    return {
                        'success': False,
                        'msg': pay_result['req_des']+':'+pay_result['error_code']+':'+pay_result['error_desc'],
                        'data': None
                    }
        except Exception as e:
            # 发生异常时回滚事务
            db.rollback()
            return {
                'success': False,
                'msg': f'创建支付记录或报考记录失败: {str(e)}',
                'data': None
            }
            
    except Exception as e:
        return {
            'success': False,
            'msg': f'补考报名缴费失败: {str(e)}',
            'data': None
        }

class UpdateBkPayStatusRequest(BaseModel):
    order_no: str

# 缴纳补考费以后，更新订单支付状态
@router.post('/updateBkPayStatus')
async def updateBkPayStatus(update_request: UpdateBkPayStatusRequest,db: Session = DatabaseDep):
    """更新订单支付状态"""
    try:
        # 获取请求参数
        order_no = update_request.order_no
        
        if not order_no:
            return {
                'success': False,
                'msg': '缺少必要参数',
                'data': None
            }
            
        to_pay_order = db.query(wxxs_payinfo).filter_by(o_order_no=order_no).first()
        if not to_pay_order:
            return {
                'success': False,
                'msg': '订单不存在',
                'data': None
            }
        
        # 商户订单号查询订单支付结果
        wx_pay = WxPayUtil()
        pay_result = wx_pay.query_order(out_trade_no=order_no)
        
        
        # 检查查询结果是否成功，并且订单状态为成功
        if  pay_result.get('success'):
            # 因为各种原因延迟支付，但是支付成功，更新订单状态
            to_pay_order.o_status = '1'
            to_pay_order.o_trade_no = pay_result['transaction_id']
            to_pay_order.o_paytime = pay_result['success_time']
            db.commit()
            # 更新报考记录信息
            # 查询并更新所有相关记录
            db.query(bk_bkb).filter_by(pay_id=to_pay_order.o_id).update({
                'isbk': 1,
                'ispay': 1
            })
            db.commit()
            return {
                'success': True,
                'msg':'缴费成功',
                'data':None
            }
        else:
            return {
                'success': False,
                'msg': '缴费失败',
                'data': None
            }           
    except Exception as e:
        return {
            'success': False,
            'msg': f'更新订单状态失败: {str(e)}',
            'data': None
        }

# 获取预支付信息
@router.get('/payBkByOrderNo')
async def payBkByOrderNo(order_id: str,openid_code: str,current_user: dict = Depends(verify_token_and_get_payload),db: Session = DatabaseDep):
    try:
        



        # 获取请求参数
        if not order_id or not openid_code:
            return {
                'success': False,
                'msg': '缺少订单编号或者openid_code',
                'data': None
            }

        # 查询订单信息
        order = db.query(wxxs_payinfo).filter_by(o_id=order_id).first()
        if not order:
            return {
                'success': False,
                'msg': '订单不存在',
                'data': None
            }

        # 检查订单状态
        if order.o_status != 0:
            return {
                'success': False,
                'msg': '订单状态异常',
                'data': None    
            }
        if order.o_type != 5:
            return {
                'success': False,
                'msg': '该订单不是在小程序生成，请使用原方式支付（请尝试手机浏览器或者电脑端）',
                'data': None
            }

        if isinstance(order.o_addtime, str):
            order.o_addtime = datetime.strptime(order.o_addtime, '%Y-%m-%d %H:%M:%S')
        now = datetime.now()
        time_diff = (now - order.o_addtime).total_seconds()

        if time_diff < 30:  # 30秒内
            return {
                'success': False,
                'msg': '请勿频繁提交订单,30秒内只能提交一次',
                'data': None 
            }

        # 获取学生信息
        student = db.query(Student).filter_by(xs_xh=order.o_xh).first()
        if not student:
            return {
                'success': False,
                'msg': '学生信息不存在',
                'data': None
            }

        # 向微信服务器获取openid

        wx_openid_result = WxUtils.get_openid_and_session_key(openid_code)
        if not wx_openid_result:
            return {
                'success': False,
                'msg': '获取openid失败',
                'data': None
            }

        openid = wx_openid_result['openid']

        # 生成微信服务器的支付订单，并返回支付参数
        wx_pay = WxPayUtil()

        pay_result = wx_pay.create_pay_info(
            openid=openid,
            out_trade_no=order.o_order_no,
            total_fee=order.o_money*100,
            description=order.o_body
        )

        # 检查 pay_result 是否为 None
        if pay_result is None:
            return {
                'success': False,
                'msg': '生成支付参数失败: 支付服务返回空结果',
                'data': None
            }

        # 需要同时判断请求状态和业务状态来确定返回的参数
        if pay_result.get('success'):
            return {
                'success': True,
                'msg': '创建支付订单成功',
                'data': pay_result['pay_params']
            }
        else:
            if pay_result.get('req_code'):
                return {
                    'success': False,
                    'msg': pay_result.get('req_des', '未知错误') + ':' + pay_result.get('error_code', '') + ':' + pay_result.get('error_desc', ''),
                    'data': None
                }
            else:
                return {
                    'success': False,
                    'msg': pay_result.get('req_des', '未知错误') + ':' + pay_result.get('error_code', '') + ':' + pay_result.get('error_desc', ''),
                    'data': None
                }

    except Exception as e:
        return {
            'success': False,
            'msg': f'生成支付参数失败: {str(e)}',
            'data': None
        }



# 更新用户微信头像
@router.post('/updateAvatar')
async def update_avatar(avatar_request: UpdateAvatarRequest,current_user: dict = Depends(verify_token_and_get_payload),db: Session = DatabaseDep):  

    avatar_url = avatar_request.avatarUrl
    if not avatar_url:
        return {
            'success': False,
            'msg': '缺少头像URL',
            'data': None
        }

    try:
        # 更新用户头像
        user_xs = db.query(Student).filter_by(xs_xh=current_user.get('xs_xh')).first()
        if not user_xs:
            return {
                'success': False,
                'msg': '用户信息不存在',
                'data': None
            }
        user_xs.xs_wx_headimgurl = avatar_url
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

    

# 添加获取是否开启退书费功能
@router.get('/get_wxxs_xf_tk_payinfo_switch')
async def get_wxxs_xf_tk_payinfo_switch(user_info: dict = Depends(verify_token_and_get_payload),db: Session = DatabaseDep):
    try:
        sys_info = db.query(lw_sys).filter_by(dq1_mc=user_info.get('dq1_mc')).first()
        if not sys_info:
            return {
                'code': 1,
                'msg': '系统参数不存在',
                'data': None
            }
        
        if sys_info.sys_wxxs_xf_tk_payinfo_switch != '1':
            return {
                'code': 1,
                'msg': '系统参数未开启退书费功能',
                'data': None
            }
        return {
            'code': 0,
            'msg': '获取退书费功能状态成功',
            'data': None
        }
    except Exception as e:
        return {
            'code': 1,
            'msg': f'获取退书费功能状态失败: {str(e)}',
            'data': None
        }


# 学生微信绑定openid并申请退书费
@router.post('/wxxs_checkPhoneCode_BindOpenid_genOrder')
async def wxxs_checkPhoneCode_BindOpenid_genOrder(bind_request: WxxsBindOpenidRequest,current_user: dict = Depends(verify_token_and_get_payload),db: Session = DatabaseDep,redis_client = RedisDep):
    try:
        # 获取参数
        phone = bind_request.phone
        verify_code = bind_request.verify_code
        openid_code = bind_request.openid_code

        # 验证参数
        if not all([phone, verify_code, openid_code]):
            return {
                'success': False,
                'msg': '缺少必要参数',
                'data': None
            }
        
        # 获取系统配置信息
        sys_info = db.query(lw_sys).filter_by(dq1_mc=current_user.get('dq1_mc')).first()
        if not sys_info:
            return {
                'success': False,
                'message': '系统配置信息不存在',
                'data': None
            }
        if sys_info.sys_wxxs_xf_tk_payinfo_switch != 1:
            return {
                'success': False,
                'msg': '系统参数未开启退书费功能',
                'data': None
            }

        # 验证手机号格式
        if not re.match(r'^1[3-9]\d{9}$', phone):
            return {
                'success': False,
                'msg': '无效的手机号码格式',
                'data': None
            }
        
        # 从Redis获取验证码
        redis_key = f"zhpt:xwyy_verify_code:{phone}"
        stored_code = redis_client.get(redis_key)
        if not stored_code:
            return {
                'success': False,
                'msg': '验证码已过期',
                'data': None
            }
            
        # 验证码比对（处理可能的字节串情况）
        if isinstance(stored_code, bytes):
            stored_code = stored_code.decode()
        
        if verify_code != stored_code:
            return {
                'success': False,
                'msg': '验证码错误',
                'data': None
            }





        # 删除验证码
        redis_client.delete(redis_key)
        # 检查是否有记录
        wxxs_sf_payinfo = db.query(WxxsSfTkpayinfo).filter_by(o_xh=current_user.get('xs_xh')).first()
        if not wxxs_sf_payinfo :
            return {
                'success': False,
                'msg': '学校还没有退费计划，请稍后再试',
                'data': None
            }


        wx_util = WxUtils()
        openidResult = wx_util.get_openid_and_session_key(openid_code)
        if not openidResult:
            return {
                'success': False,
                'msg': '获取openid失败',
                'data': None
            }
        openid = openidResult.get('openid')
        wxxs_sf_payinfo.o_openid = openid
        wxxs_sf_payinfo.o_status = 1
        db.commit()
        # 向微信服务器申请转账并生成清单及参数，成功后把参数返回给前端拉起确认收款
        return pre_wx_transfer_with_record(wxxs_sf_payinfo, sys_info.sys_pc, db)
    except Exception as e:
        return {
            'success': False,
            'msg': f'申请失败: {str(e)}',
            'data': None
        }

# 向微信服务器申请转账并生成清单及参数，成功后把参数返回给前端拉起确认收款（优化版本，直接传入记录对象）
def pre_wx_transfer_with_record(wxxs_sf_tk_payinfo, sys_pc, db):
    try:
        # 获取请求参数
        out_bill_no = f"TK{int(time.time())}{str(uuid.uuid4().int)[:6]}"
        transfer_remark = f'{wxxs_sf_tk_payinfo.o_xh}|{wxxs_sf_tk_payinfo.o_xm}|{sys_pc}|书费退费'  # 转账备注

        # 调用转账工具类
        wx_transfer = WxPayTransfer()

        # 发起转账申请，生成微信端订单
        result = wx_transfer.transfer(
            openid=wxxs_sf_tk_payinfo.o_openid,
            user_name=wxxs_sf_tk_payinfo.o_xm,
            transfer_amount=wxxs_sf_tk_payinfo.o_money,
            transfer_remark=transfer_remark,
            out_bill_no=out_bill_no
        )

        if not result.get('out_bill_no'):
            wxxs_sf_tk_payinfo.o_check_state = result['code']
            wxxs_sf_tk_payinfo.o_check_state_des = result['message']
            db.commit()
            return {
                'success': False,
                'msg': "退费申请发生错误:" + str(result),
                'data': None
            }

        # 如果生成转账订单成功,则存储订单状态，并转到小程序让用户确认收款
        wxxs_sf_tk_payinfo.o_out_bill_no = result['out_bill_no']
        # 将 ISO 格式时间转换为 SQL Server 可接受的格式
        create_time = datetime.fromisoformat(result['create_time'].replace('Z', '+00:00'))
        wxxs_sf_tk_payinfo.o_create_time = create_time.strftime('%Y-%m-%d %H:%M:%S')
        wxxs_sf_tk_payinfo.package_info = result['package_info']
        wxxs_sf_tk_payinfo.o_transfer_bill_no = result['transfer_bill_no']
        wxxs_sf_tk_payinfo.o_check_state = result['state']
        wxxs_sf_tk_payinfo.o_status = 2
        db.commit()
        return {
            'success': True,
            'msg': '生成转账订单成功',
            'data': None
        }

    except Exception as e:
        return {
            'success': False,
            'msg': f'生成转账订单异常: {str(e)}',
            'data': None
        }

# 向微信服务器申请转账并生成清单及参数，成功后把参数返回给前端拉起确认收款（原版本，保持兼容性）
def pre_wx_transfer(xh,sys_pc,db):
    try:
        # 获取请求参数
        out_bill_no = f"TK{int(time.time())}{str(uuid.uuid4().int)[:6]}"
        wxxs_sf_tk_payinfo = db.query(WxxsSfTkpayinfo).filter_by(o_xh = xh).first()

        # 检查查询结果是否为空
        if not wxxs_sf_tk_payinfo:
            return {
                'success': False,
                'msg': f'未找到学号 {xh} 的退费记录',
                'data': None
            }

        transfer_remark = f'{wxxs_sf_tk_payinfo.o_xh}|{wxxs_sf_tk_payinfo.o_xm}|{sys_pc}|书费退费'  # 转账备注

        # 调用转账工具类
        wx_transfer = WxPayTransfer()
        
        # 发起转账申请，生成微信端订单
        result = wx_transfer.transfer(
            openid=wxxs_sf_tk_payinfo.o_openid,
            user_name=wxxs_sf_tk_payinfo.o_xm,
            transfer_amount=wxxs_sf_tk_payinfo.o_money,
            transfer_remark=transfer_remark,
            out_bill_no=out_bill_no
        )
        
        if not result.get('out_bill_no'):
            wxxs_sf_tk_payinfo.o_check_state = result.get('code', 'UNKNOWN')
            wxxs_sf_tk_payinfo.o_check_state_des = result.get('message', '未知错误')
            db.commit()
            return {
                'success': False,
                'msg': "退费申请发生错误:" + str(result),
                'data': None
            }

        # 如果生成转账订单成功,则存储订单状态，并转到小程序让用户确认收款
        wxxs_sf_tk_payinfo.o_out_bill_no = result['out_bill_no']
        # 将 ISO 格式时间转换为 SQL Server 可接受的格式
        create_time = datetime.fromisoformat(result['create_time'].replace('Z', '+00:00'))
        wxxs_sf_tk_payinfo.o_create_time = create_time.strftime('%Y-%m-%d %H:%M:%S')
        wxxs_sf_tk_payinfo.package_info = result['package_info']
        wxxs_sf_tk_payinfo.o_transfer_bill_no = result['transfer_bill_no']
        wxxs_sf_tk_payinfo.o_check_state = result['state']
        wxxs_sf_tk_payinfo.o_status = 2
        db.commit()
        return {
            'success': True,
            'msg': '生成转账订单成功',
            'data': None
        }
        
    except Exception as e:
        return {
            'success': False,
            'msg': f'生成转账订单异常: {str(e)}',
            'data': None
        }

# 更新退书费订单状态
@router.get('/update_wxxs_tk_payinfo_complete')
async def update_wxxs_tk_payinfo_complete(refund_id: str,_: dict = Depends(verify_token_only),db: Session = DatabaseDep):
    try:
        wxxs_xf_tk_payinfo = db.query(WxxsSfTkpayinfo).filter_by(o_id=refund_id).first()
        if not wxxs_xf_tk_payinfo:
            return {
                'code': 1,
                'msg': '订单不存在',
                'data': None
            }
        
        # 调用转账工具类
        wx_transfer = WxPayTransfer()
        
        # 发起转账
        result = wx_transfer.query_transfer_status(wxxs_xf_tk_payinfo.o_out_bill_no)
        
        if result.get('state') == 'SUCCESS':
            wxxs_xf_tk_payinfo.o_status = 3  # 更新状态为完成
            # 将 ISO 格式时间转换为 SQL Server 可接受的格式
            payment_time = datetime.fromisoformat(result['update_time'].replace('Z', '+00:00'))
            wxxs_xf_tk_payinfo.o_payment_time = payment_time.strftime('%Y-%m-%d %H:%M:%S')
            wxxs_xf_tk_payinfo.o_check_state = result['state']
            db.session.commit()
            return {
                'code': 0,
                'msg': '转账已完成',
                'data': None
            }
        elif result.get('state') == 'WAIT_USER_CONFIRM':
            wxxs_xf_tk_payinfo.o_status = 2  # 更新状态为5，等用户收款
            wxxs_xf_tk_payinfo.o_check_state = result['state']
            db.session.commit()
            return {
                'code': 1,
                'msg': f'转账状态: {result.get("state")}',
                'data': None
            }
        else:
            wxxs_xf_tk_payinfo.o_check_state = result['state']
            wxxs_xf_tk_payinfo.o_check_state_des = result['fail_reason']
            db.session.commit()
            return {
                'code': 1,
                'msg': f'转账状态: {result.get("state")}',
                'data': None
            }
            
    except Exception as e:
        return {
            'code': 1,
            'msg': f'查询转账状态异常: {str(e)}',
            'data': None
        }

# 获取报考科目和费用信息
@router.get('/bk_payment_info')
async def get_bk_payment_info(
    user_info: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """
    获取学生的报考科目和费用信息
    用于确认支付页面显示
    """
    try:
        # 获取学生信息
        student = db.query(Student).filter_by(xs_xh=user_info.get('xs_xh')).first()
        if not student:
            return {
                'success': False,
                'msg': '学生信息不存在',
                'data': None
            }

        # 获取系统配置信息
        sys_info = db.query(lw_sys).filter_by(dq1_mc=user_info.get('dq1_mc')).first()
        if not sys_info:
            return {
                'success': False,
                'msg': '系统配置信息不存在',
                'data': None
            }


        print(student.xs_xh)
        print(sys_info.sys_pc)
        # 查询学生的报考记录 - 筛选已报考且待支付的课程
        bk_records = db.query(bk_bkb).filter(
            bk_bkb.xsxh == student.xs_xh,
            bk_bkb.pc == sys_info.sys_pc,
            bk_bkb.isbk == 1,  # 已报考
            bk_bkb.ispay == 0   # 待支付
        ).all()

        if not bk_records:
            return {
                'success': True,
                'msg': '没有待支付的报考科目',
                'data': {
                    'courses': [],
                    'total_amount': 0,
                    'student_info': {
                        'name': student.xs_xm,
                        'student_no': student.xs_xh
                    }
                }
            }

        # 构建课程列表
        courses = []
        total_amount = 0

        for record in bk_records:
            # 根据课程名称判断费用
            # 补修课程（课程名称包含#）不收费，其他课程收费
            if '#' in record.kcmc:
                course_fee = 0  # 补修课程免费
            else:
                course_fee = 22  # 正常补考课程费用（单位：元）

            course_info = {
                'id': record.id,
                'course_id': record.kcid,
                'course_name': record.kcmc,
                'exam_unit': record.ksdw,
                'fee': course_fee
            }

            courses.append(course_info)
            total_amount += course_fee

        return {
            'success': True,
            'msg': '获取报考科目信息成功',
            'data': {
                'courses': courses,
                'total_amount': total_amount,
                'student_info': {
                    'name': student.xs_xm,
                    'student_no': student.xs_xh
                },
                'payment_info': {
                    'batch': sys_info.sys_pc,
                    'deadline': int(sys_info.sys_jzrq.timestamp()) if sys_info.sys_jzrq else None
                }
            }
        }

    except Exception as e:
        logger.error(f"获取报考科目信息失败: {str(e)}")
        return {
            'success': False,
            'msg': f'获取报考科目信息失败: {str(e)}',
            'data': None
        }
