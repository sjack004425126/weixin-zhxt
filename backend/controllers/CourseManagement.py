from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from models.models import lw_sys, Student, Class, ExamKc, ExamXsDt, ExamSj
from init.dependencies import (
    get_redis, get_db,
    RedisDep, DatabaseDep, RedisManagerDep
)
from common.auth import verify_token_and_get_payload,verify_token_only
from controllers.vocational_tuition import get_term_info  # 统一学期计算函数
from utils.course_utils import ASSESSMENT_METHOD_MAP
from datetime import datetime
import json, requests
from sqlalchemy import text, bindparam
from io import BytesIO
import logging

# 创建路由器
router = APIRouter(prefix="/course_management", tags=["课程管理"])


# 获取本学期需要学习的课程的考核方式，考试时间
@router.get('/get_course_list')
async def get_course_list(current_user: dict = Depends(verify_token_and_get_payload),db: Session = DatabaseDep):
    """
    获取学生所选课程列表及其详细考核方式。
    """
    try:
        # 1. 获取系统和班级信息
        sys_info = db.query(lw_sys).filter_by(dq1_mc=current_user.get('dq1_mc')).first()
        if not sys_info:
            return {
                'success': False,
                'message': '系统配置信息不存在',
                'data': None
            }

        class_info = db.query(Class).filter_by(bj_id=current_user.get('bj_id')).first()
        if not class_info:
            return {
                'success': False,
                'message': '班级信息不存在',
                'data': None
            }
        
        bg_cc = "本科(专科起点)" if class_info.bj_cc == '本科' else class_info.bj_cc

        # 2. 获取学生本学期报考的基础课程信息
        sql = text("""
            SELECT b.kcid, b.kcmc, b.ksdw, b.xkcs 
            FROM bk_gkbkb AS a, bk_gkxkb AS b 
            WHERE a.xh=b.xh AND a.kcid=b.kcid AND a.xh=:xs_xh 
            ORDER BY b.ksdw
        """)
        result = db.execute(sql, {'xs_xh': current_user.get('xs_xh')}).fetchall()
        course_dict = {row.kcid: dict(row._mapping) for row in result}

        # 3. 按"总部"和"分部"分离课程ID
        zongbu_kcids = [k for k, v in course_dict.items() if v['ksdw'] == '总部']
        fenbu_kcids = [k for k, v in course_dict.items() if v['ksdw'] == '分部']
        
        # 4. 获取并合并总部的课程详情
        if zongbu_kcids:
            zb_sql = text("SELECT * FROM bk_zb WHERE zycc=:zycc AND kcid IN :kcids").bindparams(bindparam('kcids', expanding=True))
            zb_results = db.execute(zb_sql, {'zycc': bg_cc, 'kcids': zongbu_kcids}).fetchall()
            for row in zb_results:
                details = dict(row._mapping)
                kcid = details['kcid']
                if kcid in course_dict:
                    course_dict[kcid].update({
                        'xkfs': details.get('xkfs'),
                        'zkfs': (details.get('kslx') or '') + (details.get('ksfs') or ''),
                        'kssj': details.get('kssj'),
                        'sjh': details.get('sjh'),
                        'sjg': details.get('sfsjg'),
                        'xkbl': details.get('xkbl')+"%"
                    })
                    xkbl = details.get('xkbl')
                    course_dict[kcid]['zkbl'] = str(100 - int(xkbl) if xkbl and xkbl.isdigit() else None)+"%"
        
        # 5. 获取并合并分部的课程详情
        if fenbu_kcids:
            fb_sql = text("SELECT * FROM bk_fb WHERE zycc=:zycc AND kcid IN :kcids").bindparams(bindparam('kcids', expanding=True))
            fb_results = db.execute(fb_sql, {'zycc': bg_cc, 'kcids': fenbu_kcids}).fetchall()
            for row in fb_results:
                details = dict(row._mapping)
                kcid = details['kcid']
                if kcid in course_dict:
                    course_dict[kcid].update({
                        'xkfs': details.get('xkfs'),
                        'zkfs': details.get('ksfs'),
                        'kssj': str(sys_info.sys_zc_kssj) + "至" + str(sys_info.sys_zc_jzsj),
                        'sjh': details.get('sjh'),
                        'sjg': details.get('sfsjg'),
                        'xkbl': details.get('xkbl')+"%"
                    })
                    xkbl = details.get('xkbl')
                    course_dict[kcid]['zkbl'] = str(100 - int(xkbl) if xkbl and xkbl.isdigit() else None)+"%"




        # 6. 通过tzd_kc表，获取课程的考试教室和考试时间

        course_info_time = get_student_exam_courses(current_user.get('xs_xh'), db)


        # 优化：用sjh建立索引，单层循环
        sjh_to_item = {str(item.get('sjh')): item for item in course_dict.values()}
        for course in course_info_time:
            sjh = str(course.get('F1'))
            item = sjh_to_item.get(sjh)
            if item:
                item['ksfs'] = course.get('F3')
                item['ksdd'] = course.get('F4')
                item['kssj'] = (course.get('F6') or '') + " " + (course.get('F7') or '')

        # 7. 确定课程类型（kmlx）并生成最终列表
        final_course_list = list(course_dict.values())
        for course in final_course_list:
            # 确定课程类型
            xkcs = course.get('xkcs')
            course['kmlx'] = '正考科目' if xkcs == '1' else '补考科目'

            # 替换考核方式描述
            original_xkfs = course.get('xkfs')
            original_zkfs = course.get('zkfs')
            course['xkfs'] = ASSESSMENT_METHOD_MAP.get(original_xkfs, original_xkfs)
            course['zkfs'] = ASSESSMENT_METHOD_MAP.get(original_zkfs, original_zkfs)
        return {
            'success': True,
            'msg': '获取成功',
            'data': final_course_list
        }


    except Exception as e:
        logging.error(f"get_course_list 发生错误: {e}", exc_info=True)
        return {
            'success': False,
            'msg': f'系统错误: {str(e)}',
            'data': None
        }


def get_student_exam_courses(xs_xh, db: Session):
    # 1. 查找包含学号的那一行
    sql_find = text("SELECT id FROM tzd_kc WHERE F1 LIKE :xh")
    result = db.execute(sql_find, {'xh': f'%学号：{xs_xh}%'}).first()
    if not result:
        return []

    start_id = result.id + 2

    # 2. 一次性查出后面所有行（假设最多不会超过35门课）
    sql_courses = text("SELECT TOP 35 * FROM tzd_kc WHERE id >= :start_id ORDER BY id ASC")
    rows = db.execute(sql_courses, {'start_id': start_id}).fetchall()

    courses = []
    for row in rows:
        f1 = row.F1
        if not f1 or not str(f1).isdigit() or (isinstance(f1, str) and "考点名称:黔东南" in f1):
            break
        courses.append({k: getattr(row, k) for k in row._mapping})
    return courses




# 获取所有学期课程的成绩，判断是否及格。
@router.get('/get_course_list_all')
async def get_course_list_all(current_user: dict = Depends(verify_token_and_get_payload),db: Session = DatabaseDep):
    """
    获取学生所选课程列表及其详细考核方式。
    """
    try:
        # 1. 获取系统和班级信息
        sys_info = db.query(lw_sys).filter_by(dq1_mc=current_user.get('dq1_mc')).first()
        if not sys_info:
            return {'code': 1, 'message': '系统配置信息不存在', 'data': None}
        student = db.query(Student).filter_by(xs_xh=current_user.get('xs_xh')).first()
        if not student:
            return {'code': 1, 'message': '学生信息不存在', 'data': None}
        class_info = db.query(Class).filter_by(bj_id=current_user.get('bj_id')).first()
        if not class_info:
            return {'code': 1, 'message': '班级信息不存在', 'data': None}
        
        
        # 2. 获取学生本学期报考的基础课程信息
        if class_info.bj_cc == '本科':
            cc = '本科(专科起点)'
        else:
            cc = class_info.bj_cc

        sql = text("""
            SELECT kcid,kcmc,kcxf,ksxq,kcxz,ksdw from jh_z where gzh=:bj_planid and cc=:bj_cc order by ksxq
        """)
        result = db.execute(sql, {'bj_planid': class_info.bj_planid,'bj_cc':cc}).fetchall()
        course_dict = {row.kcid: dict(row._mapping) for row in result}

        # 获取教学计划所有课程的成绩，但是对于高于当前学期的课程，不需要获取成绩
        current_term = calculate_current_term(sys_info.sys_xq1_nd, sys_info.sys_xq1_xq, student.xs_nd, student.xs_xqdm)

        get_all_scores(current_user.get('xs_xh'), course_dict, current_term, db)
        return {
            'success': True,
            'message': '获取成功',
            'data': list(course_dict.values())
        }
    except Exception as e:
        logging.error(f"get_course_list 发生错误: {e}", exc_info=True)
        return {
            'success': False,
            'msg': f'系统错误: {str(e)}',
            'data': None
        }



def get_all_scores(student_id, formatted_plan_courses, current_term, db: Session):
    """获取所有成绩信息，包括综合成绩、网考成绩等
    :param student_id: 学号
    :param formatted_courses: 格式化后的课程信息列表
    :return: 成绩信息列表
    """
    try:
        if not formatted_plan_courses:
            return

        # 提取需要查询成绩的课程ID列表（开课学期 < 当前学期）
        course_ids = []
        for kcid, course_info in formatted_plan_courses.items():
            try:
                # 仅处理小于当前学期的课程
                if course_info.get('ksxq') is not None and int(course_info['ksxq']) < current_term:
                    course_ids.append(kcid)
            except (ValueError, TypeError):
                # 如果ksxq不是有效数字，则忽略
                continue
        
        course_ids_str = "','".join(course_ids)
        print('course_ids_str:', course_ids_str)
        # 如果没有需要查询成绩的课程，后续的数据库查询将返回空结果，无需特殊处理

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
        result_zcjb = db.execute(text(zcjb_sql))
        for row in result_zcjb:
            if row.kcid in formatted_plan_courses:
                formatted_plan_courses[row.kcid]['zh_score'] = str(row.zhcj) if row.zhcj is not None else None
                formatted_plan_courses[row.kcid]['xk_score'] = None
                formatted_plan_courses[row.kcid]['zk_score'] = None
                formatted_plan_courses[row.kcid]['sjh'] = row.sjh
                formatted_plan_courses[row.kcid]['source'] = 'zcjb'

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
            # 执行两个查询
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
            for kcid in formatted_plan_courses.keys():
                try:
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

                        formatted_plan_courses[kcid]['zh_score'] = str(selected_row['zh_score']) if selected_row['zh_score'] is not None else None
                        formatted_plan_courses[kcid]['xk_score'] = str(selected_row['xk_score']) if selected_row['xk_score'] is not None else None
                        formatted_plan_courses[kcid]['zk_score'] = str(selected_row['zk_score']) if selected_row['zk_score'] is not None else None
                        formatted_plan_courses[kcid]['sjh'] = selected_row['sjh']
                        formatted_plan_courses[kcid]['source'] = 'tzd_cj_z'
                        formatted_plan_courses[kcid]['xk_bl'] = selected_row['xk_bl']
                    else:

                        formatted_plan_courses[kcid]['zh_score'] = str(selected_row['zh_score']) if selected_row['zh_score'] is not None else None
                        formatted_plan_courses[kcid]['xk_score'] = None
                        formatted_plan_courses[kcid]['zk_score'] = None
                        formatted_plan_courses[kcid]['sjh'] = selected_row['sjh']
                        formatted_plan_courses[kcid]['xk_bl'] = selected_row['xk_bl']
                except Exception as e:
                    continue
        except Exception as e:
            raise

        # print('formatted_plan_courses',formatted_plan_courses)

        # 3. 处理特殊课程
        special_courses = []
        
        # 英语课程，改动会同步更新formatted_plan_courses，是对原始数据的引用
        eng_courses = [c for c in formatted_plan_courses.values() if c['kcid'] in ['01818', '04020', '04016', '04012', '04008', '04004']]
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
            result = db.execute(text(wkcjb_eng_sql))
            if result.rowcount > 0:
                eng_net_pass = True
            
            # 更新英语课程成绩
            if eng_net_pass:
                for course in eng_courses:
                    kcid = course['kcid']
                    formatted_plan_courses[kcid]['zh_score'] = '网替合格'
                    formatted_plan_courses[kcid]['source'] = 'wkcjb'
                    special_courses.append(course['kcid'])
        
        # 计算机课程，改动comp_courses，formatted_plan_courses会同步修改。
        comp_courses = [c for c in formatted_plan_courses.values() if c['kcid'] == '00808']
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
                result = db.execute(text(wkmkb_sql))
                if result.rowcount > 0:
                    comp_exempt = True
            
            # 更新计算机课程成绩
            for course in comp_courses:
                kcid = course['kcid']
                if comp_net_pass:
                    formatted_plan_courses[kcid]['zh_score'] = '网考合格'
                    formatted_plan_courses[kcid]['source'] = 'wkcjb'
                elif comp_exempt:
                    formatted_plan_courses[kcid]['zh_score'] = '免考合格'
                    formatted_plan_courses[kcid]['source'] = 'wkmkb'
                    special_courses.append(course['kcid'])

        # 4. 处理课程状态，如"未到开考学期"或"无考试记录"
        for course in formatted_plan_courses.values():
            kcid = course['kcid']
            course_term = course.get('ksxq')
            
            # 检查课程是否未到开考学期
            try:
                if course_term is not None and int(course_term) >= current_term:
                    course['zh_score'] = '未到开课学期'
                    course['source'] = None
                    continue
            except (ValueError, TypeError):
                # ksxq不是有效数字，跳过此检查
                pass

            # 为没有成绩的已开课课程设置状态
            if 'source' not in course and kcid not in special_courses:
                course['zh_score'] = '无考试记录'
                course['source'] = None
        
    except Exception as e:
        logging.error(f"获取成绩信息失败: {e}", exc_info=True)
        raise  # 重新抛出异常，让接口调用方能感知到错误
        


# 计算当前学期（统一委托给 get_term_info）
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