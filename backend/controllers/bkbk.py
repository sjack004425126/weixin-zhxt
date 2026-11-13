from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from init.dependencies import DatabaseDep
from common.auth import verify_token_and_get_payload
from datetime import datetime
from decimal import Decimal
import logging
import random

from models.models import (
    Student,
    Class,
    JhZ,
    bk_bkb,
    HeadquartersExam,
    BranchExam,
    lw_sys,
    TotalScore,
    Old_Zcjb,
    RepairTeachingPlan,
    wxxs_payinfo
)
from utils.wx_pay import WxPayUtil

logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(prefix="/bkbk", tags=["补考报考"])


# ==================== 辅助函数 ====================

def _is_before_22_autumn(year, term):
    """
    判断是否是22秋之前（需要查询旧总成绩表）
    规则：年度 < 2022 -> 是；年度==2022 且学期=春 -> 是；其余否
    """
    if year is None:
        return False
    try:
        y = int(year)
    except Exception:
        return False
    t = str(term or "").strip()
    is_spring = t in ["1", "01", "02", "春", "3", "03"]
    if y < 2022:
        return True
    if y == 2022 and is_spring:
        return True
    return False


def _get_best_score(records):
    """
    从查询结果中提取最高成绩，返回(最高数值, 原始显示值)
    """
    best_num = None
    best_raw = None
    fallback_raw = None
    for r in records:
        if hasattr(r, "_mapping"):
            val = list(r._mapping.values())[0] if r._mapping else None
        else:
            val = r[0] if isinstance(r, tuple) else r
        if val is None:
            continue
        sval = str(val).strip()
        if sval == "" or sval.lower() == "null":
            continue
        if fallback_raw is None:
            fallback_raw = sval
        try:
            num = float(sval)
            if best_num is None or num > best_num:
                best_num = num
                best_raw = sval
        except (ValueError, TypeError):
            continue
    if best_num is not None:
        return best_num, best_raw
    return None, fallback_raw


def _get_highest_score_with_old(db: Session, student_id, course_id, use_old):
    """
    获取学生某门课程的最高成绩，支持新旧成绩表
    use_old: 是否需要查询旧成绩表
    """
    # 查询新总成绩表 tzd_cj_z（TotalScore: F4=学号, F2=课程代码, F12=综合成绩）
    new_scores = db.query(TotalScore.F12).filter(
        TotalScore.F4 == student_id,
        TotalScore.F2 == course_id
    ).all()
    new_num, new_raw = _get_best_score(new_scores)

    if not use_old:
        return new_raw if new_num is not None else None

    # 查询旧成绩表 zcjb（Old_Zcjb: xh=学号, kcid=课程ID, zhcj=综合成绩）
    old_scores = db.query(Old_Zcjb.zhcj).filter(
        Old_Zcjb.xh == student_id,
        Old_Zcjb.kcid == course_id
    ).all()
    old_num, old_raw = _get_best_score(old_scores)

    # 取最高成绩
    if new_num is not None or old_num is not None:
        if new_num is not None and old_num is not None:
            return new_raw if new_num >= old_num else old_raw
        elif new_num is not None:
            return new_raw
        else:
            return old_raw
    return None


def get_system_jzrq(db: Session):
    """
    获取系统配置中的补考报考截止日期(sys_jzrq)
    """
    try:
        settings = db.query(lw_sys).first()
        if not settings:
            return None
        jzrq = settings.sys_jzrq
        if jzrq:
            return jzrq.strftime('%Y-%m-%d %H:%M:%S')
        return None
    except Exception as e:
        logger.error(f"获取系统补考报考截止日期失败: {str(e)}")
        return None


def is_reexam_registration_open(db: Session):
    """
    判断补考报名是否开放（基于系统配置的截止日期）
    """
    try:
        jzrq_str = get_system_jzrq(db)
        if not jzrq_str:
            return True
        jzrq = datetime.strptime(jzrq_str, '%Y-%m-%d %H:%M:%S')
        return datetime.now() <= jzrq
    except Exception as e:
        logger.error(f"判断补考报名状态失败: {str(e)}")
        return True


def calculate_class_semester_number(db: Session, class_obj):
    """
    根据班级的年度和学期与系统配置表比对计算实际学期编号
    返回: 1-5 的学期编号，None 表示无法计算
    """
    try:
        if not class_obj:
            return None
        sys_settings = db.query(lw_sys).first()
        if not sys_settings:
            return None

        class_year = str(class_obj.bj_nd)
        class_semester = str(class_obj.bj_xqdm)

        # 与系统配置的4个学期进行比对
        for i in range(1, 5):
            nd = getattr(sys_settings, f'sys_xq{i}_nd', None)
            xq = getattr(sys_settings, f'sys_xq{i}_xq', None)
            if class_year == str(nd) and class_semester == str(xq):
                return i

        # 都不匹配，说明是第5学期及以后
        return 5
    except Exception as e:
        logger.error(f"计算班级学期编号异常: {str(e)}")
        return None


def get_teaching_plans_by_semester(db: Session, plan_id, semester):
    """
    根据学期筛选教学计划
    学期规则：
    - 第1学期：不生成任何课程
    - 第2学期：只读取 ksxq包含1 的课程
    - 第3学期：读取 ksxq包含1或2 的课程
    - 第4学期：读取 ksxq包含1或2或3 的课程
    - 第5学期：读取所有课程
    """
    try:
        semester = int(semester)
        if semester == 1:
            return []

        if semester in [2, 3, 4]:
            ksxq_conditions = []
            for i in range(1, semester):
                ksxq_conditions.append(
                    or_(
                        JhZ.ksxq.like(f'{i},%'),
                        JhZ.ksxq.like(f'%,{i},%'),
                        JhZ.ksxq.like(f'%,{i}'),
                        JhZ.ksxq == str(i)
                    )
                )
            return db.query(JhZ).filter(
                and_(JhZ.gzh == plan_id, or_(*ksxq_conditions))
            ).all()

        if semester == 5:
            return db.query(JhZ).filter(JhZ.gzh == plan_id).all()

        return []
    except (ValueError, TypeError):
        return []


# ==================== 请求模型 ====================

class RegisterRequest(BaseModel):
    course_id: str
    course_name: str
    college_name: Optional[str] = None


class CancelRequest(BaseModel):
    course_id: str


class PayRequest(BaseModel):
    code: str  # 微信登录code，用于获取openid


# ==================== 路由 ====================

@router.get('/list')
def get_list(
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """
    返回学生应修课程列表，并标注每门课的最高成绩和是否可报名补考。
    """
    try:
        student = db.query(Student).filter_by(xs_xh=current_user.get('xs_xh')).first()
        if not student:
            return {'success': False, 'msg': '未找到学生信息', 'data': None}

        if not student.xs_bj_id:
            return {'success': False, 'msg': '未找到学生班级信息', 'data': None}

        clazz = db.query(Class).filter_by(bj_id=student.xs_bj_id).first()
        if not clazz:
            return {'success': False, 'msg': '班级不存在', 'data': None}

        plan_id = (clazz.bj_planid or "").strip()
        if not plan_id:
            return {'success': False, 'msg': '班级未配置教学计划', 'data': None}

        semester = calculate_class_semester_number(db, clazz)
        if semester is None:
            return {'success': False, 'msg': '无法计算学生所在学期', 'data': None}

        plans = get_teaching_plans_by_semester(db, plan_id, semester)
        plans = sorted(plans, key=lambda p: (p.ksxq or '', p.id))

        use_old = _is_before_22_autumn(student.xs_nd, student.xs_xqdm)

        # 获取当前批次并预加载该学生的报考记录
        settings = db.query(lw_sys).first()
        pc = getattr(settings, 'sys_pc', None) if settings else None
        try:
            reg_query = db.query(bk_bkb).filter_by(xsxh=student.xs_xh)
            if pc is not None:
                reg_query = reg_query.filter_by(pc=pc)
            regs = reg_query.all()
        except Exception:
            regs = []
        reg_map = {}
        for r in regs:
            key = (r.kcid or '')
            if key and key not in reg_map:
                reg_map[key] = r

        registration_open = is_reexam_registration_open(db)

        plan_list = []
        for p in plans:
            kcid = p.kcid or ""
            try:
                highest = _get_highest_score_with_old(db, student.xs_xh, kcid, use_old)
            except Exception:
                highest = None

            is_pass = False
            if highest is not None:
                try:
                    is_pass = Decimal(highest) >= Decimal('60.0')
                except Exception:
                    is_pass = False

            can_register = (not is_pass) and registration_open

            var_reg = reg_map.get(kcid)
            register_status = '已报考' if var_reg else '未报考'
            if var_reg:
                ispay_val = getattr(var_reg, 'ispay', None)
                if ispay_val == 1:
                    pay_status = '已支付'
                elif ispay_val == 2:
                    pay_status = '待支付'
                else:
                    pay_status = '未支付'
            else:
                pay_status = '-'

            plan_list.append({
                "gzh": p.gzh or "",
                "kcmc": p.kcmc or "",
                "kcid": kcid,
                "kcxf": p.kcxf or "",
                "kclx": p.kclx or "",
                "ksxq": p.ksxq or "",
                "kcxz": p.kcxz or "",
                "ksdw": p.ksdw or "",
                "cc": getattr(p, 'cc', '') or "",
                "pc": getattr(p, 'pc', '') or "",
                "dj": getattr(p, 'dj', '') or "",
                "zk": getattr(p, 'zk', '') or "",
                "highest_score": highest,
                "is_pass": is_pass,
                "can_register": can_register,
                "register_status": register_status,
                "pay_status": pay_status
            })

        # 补修课（本科层次）
        repair_plan_list = []
        class_level = (clazz.bj_cc or "").strip()
        is_undergraduate = bool(class_level and "本科" in class_level)
        if is_undergraduate and clazz.bj_zy and clazz.bj_nd is not None and clazz.bj_xqdm:
            batch_code = f"{clazz.bj_nd}{clazz.bj_xqdm}"
            repair_plans = (
                db.query(RepairTeachingPlan).filter(
                    RepairTeachingPlan.F2 == clazz.bj_zy,
                    RepairTeachingPlan.F7 == batch_code
                )
                .order_by(RepairTeachingPlan.id.asc())
                .all()
            )
            for rp in repair_plans:
                kcid = rp.F4 or ""
                try:
                    highest = _get_highest_score_with_old(db, student.xs_xh, kcid, use_old)
                except Exception:
                    highest = None
                is_pass = False
                if highest is not None:
                    try:
                        is_pass = Decimal(highest) >= Decimal('60.0')
                    except Exception:
                        is_pass = False
                can_register = (not is_pass) and registration_open
                var_reg = reg_map.get(kcid)
                register_status = '已报考' if var_reg else '未报考'
                if var_reg:
                    ispay_val = getattr(var_reg, 'ispay', None)
                    if ispay_val == 1:
                        pay_status = '已支付'
                    elif ispay_val == 2:
                        pay_status = '待支付'
                    else:
                        pay_status = '未支付'
                else:
                    pay_status = '-'

                repair_plan_list.append({
                    "zymc": rp.F2 or "",
                    "kcid": kcid,
                    "kcmc": rp.F5 or "",
                    "xf": rp.F6 or "",
                    "pc": rp.F7 or "",
                    "highest_score": highest,
                    "is_pass": is_pass,
                    "can_register": can_register,
                    "register_status": register_status,
                    "pay_status": pay_status
                })

        # 系统补考截止时间
        reexam_deadline = None
        if settings and getattr(settings, 'sys_jzrq', None):
            try:
                reexam_deadline = settings.sys_jzrq.strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                reexam_deadline = str(settings.sys_jzrq)

        # 学籍状态映射
        xjzt_code = getattr(student, 'xs_xjzt', None)
        xjzt_map = {
            "1": "在籍", "2": "未注册", "3": "转出", "4": "休学",
            "5": "退学", "6": "开除", "7": "毕业", "8": "异动中", "9": "超期清退"
        }
        xjzt_desc = xjzt_map.get(str(xjzt_code), "未知")

        return {
            'success': True,
            'msg': 'success',
            'data': {
                "student": {
                    "xh": student.xs_xh or "",
                    "xm": student.xs_xm or "",
                    "bj_id": student.xs_bj_id,
                    "bj_mc": clazz.bj_mc or "",
                    "xjzt": xjzt_code,
                    "xjzt_desc": xjzt_desc
                },
                "reexam_deadline": reexam_deadline,
                "registration_open": registration_open,
                "plan_list": plan_list,
                "repair_plan": repair_plan_list
            }
        }

    except Exception as e:
        logger.error(f"获取补考课程失败: {str(e)}")
        return {'success': False, 'msg': f'获取补考课程失败: {str(e)}', 'data': None}


@router.post('/register')
def register_reexam(
    register_request: RegisterRequest,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """
    学生提交补考报名
    """
    try:
        student = db.query(Student).filter_by(xs_xh=current_user.get('xs_xh')).first()
        if not student:
            return {'success': False, 'msg': '学生不存在', 'data': None}

        kcid = register_request.course_id
        kcmc = register_request.course_name
        ksdw = register_request.college_name
        if not kcid or not kcmc:
            return {'success': False, 'msg': '课程ID或课程名称缺失', 'data': None}

        # 检查报名是否开放
        if not is_reexam_registration_open(db):
            return {'success': False, 'msg': '补考报名已关闭', 'data': None}

        settings = db.query(lw_sys).first()
        pc = getattr(settings, 'sys_pc', None) if settings else None

        # 1) 检查是否存在待支付订单
        try:
            pending_pay = db.query(bk_bkb).filter_by(
                xsczr=getattr(student, 'xs_id', None), pc=pc, isbk=1, ispay=2
            ).first()
            if pending_pay:
                return {'success': False, 'msg': '系统内检测有待支付订单，请先完成该订单支付后再进行报考操作。', 'data': None}
        except Exception:
            pass

        # 2) 形势与政策特殊处理（kcid == "04392"）
        if kcid == "04392":
            try:
                clazz = db.query(Class).filter_by(bj_id=student.xs_bj_id).first()
                if clazz and getattr(clazz, 'bj_nd', None) is not None:
                    bj_nd = getattr(clazz, 'bj_nd', None)
                    bj_xqdm = getattr(clazz, 'bj_xqdm', None)
                    if bj_nd <= 2020:
                        if bj_nd == 2020 and str(bj_xqdm or '') == '09':
                            return {'success': False, 'msg': '形势与政策该门课程考核方式特殊，20级秋季学生暂不收取补考费，具体咨询班主任。', 'data': None}
                    else:
                        return {'success': False, 'msg': f'形势与政策该门课程考核方式特殊，{bj_nd}级学生暂不收取补考费，具体咨询班主任。', 'data': None}
            except Exception:
                pass

        # 3) 学位类课程不允许报考
        if kcmc and "学位" in kcmc:
            return {'success': False, 'msg': '学位相关课程考核方式特殊，不需要进行报考', 'data': None}

        # 4) 本学期报考科目不能超过15门
        try:
            reg_count = db.query(bk_bkb).filter_by(
                xsid=getattr(student, 'xs_id', None), pc=pc
            ).count()
            if reg_count >= 15:
                return {'success': False, 'msg': '报考科目不能大于15门课程，具体咨询班主任。', 'data': None}
        except Exception:
            pass

        # 检查是否已报名同门课程
        existing = db.query(bk_bkb).filter_by(xsxh=student.xs_xh, kcid=kcid, pc=pc).first()
        if existing:
            return {'success': False, 'msg': '您已报名该课程的补考', 'data': None}

        # 查询试卷号和班级层次
        sjh = ''
        bjcc = None
        is_repair = False
        try:
            clazz = db.query(Class).filter_by(bj_id=student.xs_bj_id).first()
            bjcc = getattr(clazz, 'bj_cc', None) if clazz else None

            # 判断是否为补修课（仅本科层次）
            if clazz and clazz.bj_zy and clazz.bj_nd is not None and clazz.bj_xqdm:
                class_level = (clazz.bj_cc or "").strip()
                if "本科" in class_level:
                    batch_code = f"{clazz.bj_nd}{clazz.bj_xqdm}"
                    repair_course = db.query(RepairTeachingPlan).filter(
                        RepairTeachingPlan.F4 == kcid,
                        RepairTeachingPlan.F2 == clazz.bj_zy,
                        RepairTeachingPlan.F7 == batch_code
                    ).first()
                    if repair_course:
                        is_repair = True

            if ksdw and str(ksdw).strip() == '总部':
                exam = db.query(HeadquartersExam).filter_by(kcid=kcid, zycc=bjcc, ksdw=ksdw).first()
            else:
                exam = db.query(BranchExam).filter_by(kcid=kcid, zycc=bjcc, ksdw=ksdw).first()

            if exam and getattr(exam, 'sjh', None):
                sjh = exam.sjh
        except Exception as e:
            logger.error(f"查询试卷号异常: {str(e)}")

        # 创建报名记录（补修课直接设为已支付，免费）
        new = bk_bkb(
            sjh=sjh or '000000',
            kcid=kcid,
            kcmc=kcmc,
            ksdw=ksdw if not is_repair else '分部',
            xsxh=student.xs_xh,
            xsid=getattr(student, 'xs_id', None),
            bjid=student.xs_bj_id,
            bjcc=bjcc,
            czr=None,
            date=datetime.now(),
            isbk=1,
            pc=pc,
            xsczr=getattr(student, 'xs_id', None),
            isdgzk=1 if is_repair else 0,
            ispay=1 if is_repair else 0,
            pay_id=None
        )
        db.add(new)
        db.flush()
        return {'success': True, 'msg': '报名成功', 'data': {"id": new.id}}

    except Exception as e:
        logger.error(f"补考报名失败: {str(e)}")
        db.rollback()
        return {'success': False, 'msg': f'补考报名失败: {str(e)}', 'data': None}


@router.post('/cancel')
def cancel_reexam(
    cancel_request: CancelRequest,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """
    取消补考报名：仅当 ispay != 1 且 ispay != 2 时允许删除
    """
    try:
        student = db.query(Student).filter_by(xs_xh=current_user.get('xs_xh')).first()
        if not student:
            return {'success': False, 'msg': '学生不存在', 'data': None}

        kcid = cancel_request.course_id
        if not kcid:
            return {'success': False, 'msg': '课程ID缺失', 'data': None}

        # 获取当前批次
        settings = db.query(lw_sys).first()
        pc = getattr(settings, 'sys_pc', None) if settings else None

        # 查找报考记录
        reg = db.query(bk_bkb).filter_by(xsxh=student.xs_xh, kcid=kcid, pc=pc).first()
        if not reg:
            return {'success': False, 'msg': '未找到报考记录', 'data': None}

        # 检查支付状态
        ispay = getattr(reg, 'ispay', None)
        if ispay == 1:
            return {'success': False, 'msg': '报考已支付，不允许取消', 'data': None}
        if ispay == 2:
            return {'success': False, 'msg': '存在待支付订单，请继续支付，不允许取消', 'data': None}

        # 删除记录
        try:
            db.delete(reg)
            db.flush()
            return {'success': True, 'msg': '取消成功', 'data': None}
        except Exception as e:
            db.rollback()
            logger.error(f"取消报名删除失败: {str(e)}")
            return {'success': False, 'msg': f'取消报名失败: {str(e)}', 'data': None}

    except Exception as e:
        logger.error(f"取消报名失败: {str(e)}")
        return {'success': False, 'msg': f'取消报名失败: {str(e)}', 'data': None}


@router.get('/my_registrations')
def my_registrations(
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """
    返回学生已报名的补考记录
    """
    try:
        regs = db.query(bk_bkb).filter_by(
            xsxh=current_user.get('xs_xh')
        ).order_by(bk_bkb.date.desc()).all()

        out = []
        for r in regs:
            out.append({
                "id": r.id,
                "kcid": r.kcid,
                "kcmc": r.kcmc,
                "date": r.date.strftime('%Y-%m-%d %H:%M:%S') if r.date else None,
                "ispay": r.ispay,
                "pay_id": r.pay_id
            })

        return {'success': True, 'msg': 'success', 'data': out}

    except Exception as e:
        logger.error(f"查询我的补考报名失败: {str(e)}")
        return {'success': False, 'msg': f'查询我的补考报名失败: {str(e)}', 'data': None}



@router.post('/pay')
def create_makeup_payment(
    pay_request: PayRequest,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """
    为已报考且未支付的补考课程创建合并支付订单，并调用微信下单返回支付参数。
    每科补考费22元，补修课免费（后端报考时已标记ispay=1）。
    流程：
    1. 先检查是否有未完成的支付订单 → 有则复用（处理用户取消支付后重新支付的场景）
    2. 没有未完成订单 → 查 ispay in (0,2) 的报考记录创建新订单
    """
    try:
        student = db.query(Student).filter_by(xs_xh=current_user.get('xs_xh')).first()
        if not student:
            return {'success': False, 'msg': '学生不存在', 'data': None}

        settings = db.query(lw_sys).first()
        if not settings:
            return {'success': False, 'msg': '系统设置不存在', 'data': None}
        sys_pc = getattr(settings, 'sys_pc', None) or 0

        wx_pay = WxPayUtil()

        # ===== 第一步：检查是否存在未完成的补考支付订单 =====
        pending_order = db.query(wxxs_payinfo).filter_by(
            o_xh=student.xs_xh, o_status=0, o_close=0, o_delete=0, o_pc=sys_pc
        ).first()

        # 支付方式字典：o_type -> 描述
        PAY_TYPE_MAP = {
            1: '电脑浏览器',
            2: '手机浏览器',
            3: '微信浏览器',
            4: '线下',
            5: '小程序',
        }

        if pending_order:
            # 检查原订单是否为小程序支付，非小程序订单不能在此继续支付
            order_type = getattr(pending_order, 'o_type', None)
            if order_type != 5:
                type_desc = PAY_TYPE_MAP.get(order_type, '其他')
                return {'success': False, 'msg': f'检测到您有未完成的补考支付订单，原支付方式为「{type_desc}」，请使用原方式继续缴费。', 'data': None}

            # 先查询微信端该订单是否已支付（处理回调延迟的情况）
            try:
                pay_query = wx_pay.query_order(pending_order.o_order_no)
                if pay_query.get('success'):
                    pending_order.o_status = 1
                    pending_order.o_trade_no = pay_query.get('transaction_id', '')
                    pending_order.o_paytime = pay_query.get('success_time')
                    # 将关联的报考记录标记为已支付
                    if pending_order.o_bkkcid:
                        for kid in pending_order.o_bkkcid.split(','):
                            kid = kid.strip()
                            if kid:
                                r = db.query(bk_bkb).filter_by(xsxh=student.xs_xh, kcid=kid, pc=sys_pc).first()
                                if r:
                                    r.ispay = 1
                    db.flush()
                    return {'success': False, 'msg': '检测到您已完成支付，无需重复支付', 'data': None}
            except Exception:
                pass

            # 微信端未支付，复用该订单继续下单
            order = pending_order
        else:
            # ===== 第二步：没有未完成订单，查找需要支付的报考记录 =====
            # ispay=0 新报考未支付，ispay=2 之前创建过订单但订单已关闭/删除
            regs = db.query(bk_bkb).filter(
                bk_bkb.xsxh == student.xs_xh,
                bk_bkb.pc == sys_pc,
                bk_bkb.ispay.in_([0, 2])
            ).all()
            if not regs:
                return {'success': False, 'msg': '没有需要支付的报考记录', 'data': None}

            # 创建新的合并订单
            unit_fee_yuan = 22  # 每科22元 = 2200分
            total_money_yuan = unit_fee_yuan * len(regs)

            now = datetime.now()
            o_order_no = f"BK{now.strftime('%Y%m%d%H%M%S')}{random.randint(1000, 9999)}"

            order = wxxs_payinfo(
                o_xh=student.xs_xh,
                o_sfzh=getattr(student, 'xs_sfzh', '') or '',
                o_body=f'{student.xs_xm}-{student.xs_xh}-补考费',
                o_money=total_money_yuan,
                o_paytype='weixin',
                o_type=5,
                o_status=0,
                o_tk_status=0,
                o_close=0,
                o_order_no=o_order_no,
                o_addtime=now,
                o_pc=sys_pc,
                o_bkid=','.join([str(r.id) for r in regs]),
                o_bkkcid=','.join([r.kcid or '' for r in regs]),
                o_bkkcmc=','.join([r.kcmc or '' for r in regs]),
                o_delete=0
            )
            db.add(order)
            db.flush()

            # 将报考记录统一标记为待支付
            for r in regs:
                r.ispay = 2
            db.flush()

        # ===== 第三步：获取openid并调用微信下单 =====
        from utils.wx_utils import WxUtils
        wx_result = WxUtils.get_openid_and_session_key(pay_request.code)
        if not wx_result:
            return {'success': False, 'msg': '获取openid失败，请重试', 'data': None}
        openid = wx_result['openid']

        pay_result = wx_pay.create_pay_info(
            openid=openid,
            out_trade_no=order.o_order_no,
            total_fee=order.o_money*100,  #表存储的是元为单位，要*100
            description=order.o_body,
            business_type='wxxs_payinfo'
        )

        if pay_result.get('success'):
            # 计算课程数（从订单关联的课程ID中获取）
            course_count = len(order.o_bkkcid.split(',')) if order.o_bkkcid else 0
            return {
                'success': True,
                'msg': '创建支付订单成功',
                'data': {
                    'pay_params': pay_result['pay_params'],
                    'order_no': order.o_order_no,
                    'total_money': order.o_money,
                    'course_count': course_count
                }
            }
        else:
            error_msg = pay_result.get('req_des', '') or ''
            error_code = pay_result.get('error_code', '') or ''
            error_desc = pay_result.get('error_desc', '') or ''
            return {
                'success': False,
                'msg': f'微信下单失败: {error_msg} {error_code} {error_desc}'.strip(),
                'data': None
            }

    except Exception as e:
        logger.error(f"创建补考支付订单失败: {str(e)}")
        db.rollback()
        return {'success': False, 'msg': f'创建支付订单失败: {str(e)}', 'data': None}

