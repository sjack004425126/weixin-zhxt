from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from models.models import lw_sys, Student, Class, ExamKc, ExamXsDt, ExamSj
from init.dependencies import (
    get_redis, get_db,
    RedisDep, DatabaseDep, RedisManagerDep
)
from common.auth import verify_token_and_get_payload, verify_token_only
from datetime import datetime
import json, requests
from sqlalchemy import text
from io import BytesIO
import logging

# 创建路由器
router = APIRouter(prefix="/student_exam", tags=["学生考试"])

# 辅助方法：获取考试类型样式
def _get_exam_type_style(lx_id, type_name):
    """根据考试类型ID和名称返回样式配置"""
    style_map = {
        1: {  # 形考1
            'color': '#1890ff',
            'background': '#e6f7ff',
            'border': '#91d5ff',
            'icon': '📋',
            'badge': 'primary'
        },
        2: {  # 形考2
            'color': '#52c41a',
            'background': '#f6ffed',
            'border': '#b7eb8f',
            'icon': '📝',
            'badge': 'success'
        },
        3: {  # 终考
            'color': '#fa541c',
            'background': '#fff2e8',
            'border': '#ffbb96',
            'icon': '🎯',
            'badge': 'warning'
        },
        4: {  # 补考
            'color': '#f5222d',
            'background': '#fff1f0',
            'border': '#ffa39e',
            'icon': '🔄',
            'badge': 'danger'
        }
    }

    # 默认样式
    default_style = {
        'color': '#722ed1',
        'background': '#f9f0ff',
        'border': '#d3adf7',
        'icon': '📄',
        'badge': 'default'
    }

    return style_map.get(lx_id, default_style)

# 辅助方法：获取成绩样式
def _get_score_style(score, is_passed):
    """根据成绩返回样式配置"""
    if score >= 90:
        return {
            'color': '#52c41a',
            'background': '#f6ffed',
            'border': '#b7eb8f',
            'level': 'excellent',
            'text': '优秀'
        }
    elif score >= 80:
        return {
            'color': '#1890ff',
            'background': '#e6f7ff',
            'border': '#91d5ff',
            'level': 'good',
            'text': '良好'
        }
    elif score >= 60:
        return {
            'color': '#faad14',
            'background': '#fffbe6',
            'border': '#ffe58f',
            'level': 'pass',
            'text': '及格'
        }
    else:
        return {
            'color': '#f5222d',
            'background': '#fff1f0',
            'border': '#ffa39e',
            'level': 'fail',
            'text': '不及格'
        }

# 辅助方法：获取状态信息
def _get_status_info(zt, zgt_zt):
    """根据客观题和主观题状态返回状态信息"""
    status_map = {
        0: {'text': '未提交', 'color': '#d9d9d9', 'icon': '⏳'},
        1: {'text': '已提交', 'color': '#52c41a', 'icon': '✅'},
        2: {'text': '已评阅', 'color': '#1890ff', 'icon': '📝'},
        3: {'text': '已完成', 'color': '#722ed1', 'icon': '🎉'}
    }

    # 综合客观题和主观题状态
    if zt == 1 and zgt_zt == 1:
        overall_status = 3  # 已完成
    elif zt == 1 or zgt_zt == 1:
        overall_status = 1  # 已提交
    else:
        overall_status = 0  # 未提交

    return status_map.get(overall_status, status_map[0])

# 辅助方法：获取题型样式
def _get_question_type_style(question_type):
    """根据题型返回样式配置"""
    type_styles = {
        '单选题': {
            'color': '#1890ff',
            'background': '#e6f7ff',
            'icon': '🔘',
            'tag_color': 'blue'
        },
        '多选题': {
            'color': '#52c41a',
            'background': '#f6ffed',
            'icon': '☑️',
            'tag_color': 'green'
        },
        '判断题': {
            'color': '#faad14',
            'background': '#fffbe6',
            'icon': '✓✗',
            'tag_color': 'orange'
        },
        '主观题': {
            'color': '#722ed1',
            'background': '#f9f0ff',
            'icon': '✍️',
            'tag_color': 'purple'
        },
        '填空题': {
            'color': '#13c2c2',
            'background': '#e6fffb',
            'icon': '📝',
            'tag_color': 'cyan'
        }
    }

    return type_styles.get(question_type, {
        'color': '#595959',
        'background': '#f5f5f5',
        'icon': '❓',
        'tag_color': 'default'
    })

# 请求模型
class SubmitExamRequest(BaseModel):
    sj_id: int
    kc_id: int
    jl_id: str
    answers: list

class SaveAnswersRequest(BaseModel):
    sj_id: int
    kc_id: int
    jl_id: str
    answers: list


# 获取学生自测科目列表
@router.get('/subjectsList')
async def get_self_test_subjects(current_user: dict = Depends(verify_token_and_get_payload),db: Session = DatabaseDep):
    try:
        # 获取系统配置信息
        sys_info = db.query(lw_sys).filter_by(dq1_mc=current_user.get('dq1_mc')).first()
        if not sys_info:
            return {
                'success': False,
                'msg': '系统配置信息不存在',
                'data': None
            }

        # 考试开始和截止日期，格式化deadline为年月日时分秒格式
        deadline_str = sys_info.sys_zc_jzsj.strftime('%Y-%m-%d %H:%M:%S') if sys_info.sys_zc_jzsj else None

        # # 检查考试时间
        now = datetime.now()
        if now < sys_info.sys_zc_kssj:
            return {
                'success': False,
                'msg': f'自测科目还未开启，请于{sys_info.sys_zc_kssj}后访问',
                'data': None
            }

        if now > sys_info.sys_zc_jzsj:
            return {
                'success': False,
                'msg': f'自测科目已于{sys_info.sys_zc_jzsj}结束答题',
                'data': None
            }



        # 获取学生本学期报考科目，只要报考科目的课程id即可。然后用课程id去exam_kc表中查询形考和终考的考核方式
        sql =text( """
            select a.kcid,a.yzdsjh from bk_gkbkb as a,bk_gkxkb as b where a.xh=b.xh and a.kcid=b.kcid and a.xh=:xs_xh order by a.kcid
        """)

        result = db.execute(sql, {'xs_xh': current_user.get('xs_xh')}).fetchall()
        kc_ksdw_pairs = set()
        for row in result:
            kcid = row.kcid
            yzdsjh = row.yzdsjh
            if yzdsjh and str(yzdsjh).startswith('5'):
                ksdw = '分部'
            else:
                ksdw = '总部'
            kc_ksdw_pairs.add((kcid, ksdw))
        kc_ksdw_pairs = list(kc_ksdw_pairs)

        if not kc_ksdw_pairs:
            return {
                'success': True,
                'msg': '获取成功',
                'data': {
                    'subjects': []
                }
            }

        # 构造CTE的values部分
        values_str = ",\n                ".join([f"('{kcid}', '{ksdw}')" for kcid, ksdw in kc_ksdw_pairs])
        bg_cc = db.query(Class).filter_by(bj_id=current_user.get('bj_id')).first().bj_cc
        if bg_cc == '本科':
            bg_cc = '本科(专科起点)'

        # 使用CTE方式查询所有匹配的课程
        sql_kc = text(f"""
            with match_set as (
                select kcid, ksdw from (values 
                    {values_str}
                ) as match_set(kcid, ksdw)
            )
            select a.id,a.kcid,a.kcmc,a.kccc,a.ksdw,b.t_xm,b.issj 
            from exam_kc a
            outer apply (
                select top 1 t_xm, issj from exam_kc_ctjs where kc_id = a.id and dq1_mc='黔东南'
            ) b
            join match_set on a.kcid = match_set.kcid and a.ksdw = match_set.ksdw
            where (a.xkfs='自行测评' or a.zkfs='自行测评')
            and a.kccc='{bg_cc}'
        """)

        result_kc = db.execute(sql_kc).fetchall()

        subjects = []
        for row in result_kc:
            # 根据科目类型设置不同的样式标识
            subject_type = "实践类" if row.issj == 2 else "理论类"
            subject_color = "orange" if row.issj == 2 else "blue"

            # 根据考试单位设置标签样式
            unit_tag = {
                'text': row.ksdw,
                'color': 'green' if row.ksdw == '总部' else 'purple'
            }

            subject = {
                'kc_id': row.id,      #课程在该表的序号，不是课程名称的课程号
                'kcid': row.kcid,   #真正的国开课程号，用来传递到考试那里，最后在答题表需要存储
                'kcmc': row.kcmc,   #课程名称
                'kccc': row.kccc,   #课程层次
                'ksdw': row.ksdw,    #考试单位,
                'issj': row.issj,       #1为普通需要自测的科目   ，2为实践类的科目。需要到综合平台去做
                'ctjs': row.t_xm,
                # 新增样式相关字段
                'subject_type': subject_type,
                'subject_color': subject_color,
                'unit_tag': unit_tag,
                'icon': '📝' if row.issj == 1 else '🔬',  # 理论类用笔记本图标，实践类用实验图标
                'priority': 'high' if row.issj == 2 else 'normal'  # 实践类优先级高
            }
            subjects.append(subject)


        # 添加统计信息和提示
        total_subjects = len(subjects)
        theory_subjects = len([s for s in subjects if s['issj'] == 1])
        practice_subjects = len([s for s in subjects if s['issj'] == 2])

        return {
            'success': True,
            'msg': '获取成功',
            'data': {
                'deadline': deadline_str,
                'subjects': subjects,
                'statistics': {
                    'total': total_subjects,
                    'theory': theory_subjects,
                    'practice': practice_subjects
                },
                'notice': {
                    'title': '📢 考试科目自测须知',
                    'content': [
                        '每个科目最多可以答题100次，每次答题间隔30秒',
                        '形考任务一般包含形考1、形考2等多个试卷',
                        '实践类科目需要到综合平台完成',
                        '请在截止时间前完成所有自测任务'
                    ],
                    'deadline_notice': f'⏰ 自测截止时间：{deadline_str}' if deadline_str else '⏰ 暂未设置截止时间'
                },
                'ui_config': {
                    'theme_color': '#1890ff',
                    'success_color': '#52c41a',
                    'warning_color': '#faad14',
                    'error_color': '#f5222d'
                }
            }
        }

    except Exception as e:
        return {
            'success': False,
            'msg': f'获取自测科目列表失败: {str(e)}',
            'data': None
        }

# 获取考试统计信息仪表板
@router.get('/dashboard')
async def get_exam_dashboard(current_user: dict = Depends(verify_token_and_get_payload), db: Session = DatabaseDep):
    """获取学生考试统计仪表板信息"""
    try:
        # 获取系统配置信息
        sys_info = db.query(lw_sys).filter_by(dq1_mc=current_user.get('dq1_mc')).first()
        if not sys_info:
            return {
                'success': False,
                'msg': '系统配置信息不存在',
                'data': None
            }

        # 获取学生所有答题记录统计
        sql_stats = text("""
            SELECT
                COUNT(DISTINCT kc_id) as total_subjects,
                COUNT(*) as total_attempts,
                AVG(CAST(cj as FLOAT)) as avg_score,
                MAX(CAST(cj as FLOAT)) as max_score,
                COUNT(CASE WHEN CAST(cj as FLOAT) >= 60 THEN 1 END) as passed_attempts
            FROM exam_xs_dt
            WHERE xh = :xs_xh AND pc = :pc
        """)

        stats_result = db.execute(sql_stats, {
            'xs_xh': current_user.get('xs_xh'),
            'pc': current_user.get('sys_pc')
        }).first()

        # 获取最近的答题记录
        sql_recent = text("""
            SELECT TOP 5 kc_id, cj, zgt_cj, tjsj, cs
            FROM exam_xs_dt
            WHERE xh = :xs_xh AND pc = :pc
            ORDER BY tjsj DESC
        """)

        recent_results = db.execute(sql_recent, {
            'xs_xh': current_user.get('xs_xh'),
            'pc': current_user.get('sys_pc')
        }).fetchall()

        # 处理统计数据
        total_subjects = stats_result.total_subjects or 0
        total_attempts = stats_result.total_attempts or 0
        avg_score = round(stats_result.avg_score or 0, 1)
        max_score = stats_result.max_score or 0
        passed_attempts = stats_result.passed_attempts or 0
        pass_rate = round((passed_attempts / total_attempts * 100), 1) if total_attempts > 0 else 0

        # 处理最近答题记录
        recent_exams = []
        for record in recent_results:
            total_score = (record.cj or 0) + (record.zgt_cj or 0)
            recent_exams.append({
                'subject_id': record.kc_id,
                'score': total_score,
                'submit_time': record.tjsj.strftime('%m-%d %H:%M') if record.tjsj else '',
                'attempt': record.cs,
                'status': '优秀' if total_score >= 90 else '良好' if total_score >= 80 else '及格' if total_score >= 60 else '不及格'
            })

        return {
            'success': True,
            'msg': '获取成功',
            'data': {
                'overview': {
                    'total_subjects': total_subjects,
                    'total_attempts': total_attempts,
                    'avg_score': avg_score,
                    'max_score': max_score,
                    'pass_rate': pass_rate
                },
                'recent_exams': recent_exams,
                'deadline_info': {
                    'deadline': sys_info.sys_zc_jzsj.strftime('%Y-%m-%d %H:%M:%S') if sys_info.sys_zc_jzsj else None,
                    'is_active': datetime.now() < sys_info.sys_zc_jzsj if sys_info.sys_zc_jzsj else True
                },
                'achievements': {
                    'badges': _get_achievement_badges(total_attempts, avg_score, pass_rate),
                    'progress': _calculate_progress(total_subjects, passed_attempts)
                },
                'motivational': {
                    'message': _get_motivational_message(avg_score, pass_rate),
                    'tip': _get_study_tip(avg_score)
                }
            }
        }

    except Exception as e:
        return {
            'success': False,
            'msg': f'获取仪表板信息失败: {str(e)}',
            'data': None
        }

# 辅助方法：获取成就徽章
def _get_achievement_badges(attempts, avg_score, pass_rate):
    """根据答题情况返回成就徽章"""
    badges = []

    if attempts >= 10:
        badges.append({'name': '勤奋学习者', 'icon': '📚', 'color': '#1890ff'})
    if avg_score >= 90:
        badges.append({'name': '学霸', 'icon': '🏆', 'color': '#52c41a'})
    if pass_rate >= 80:
        badges.append({'name': '稳定发挥', 'icon': '🎯', 'color': '#722ed1'})
    if attempts >= 50:
        badges.append({'name': '刷题达人', 'icon': '💪', 'color': '#fa541c'})

    return badges

# 辅助方法：计算进度
def _calculate_progress(total_subjects, passed_attempts):
    """计算学习进度"""
    if total_subjects == 0:
        return {'percentage': 0, 'status': 'not_started'}

    progress = min(100, (passed_attempts / total_subjects) * 100)

    if progress >= 90:
        status = 'excellent'
    elif progress >= 70:
        status = 'good'
    elif progress >= 50:
        status = 'normal'
    else:
        status = 'need_effort'

    return {'percentage': round(progress, 1), 'status': status}

# 辅助方法：获取激励信息
def _get_motivational_message(avg_score, pass_rate):
    """根据成绩返回激励信息"""
    if avg_score >= 90:
        return "🌟 表现优异！继续保持这种学习状态！"
    elif avg_score >= 80:
        return "👍 学习效果很好，再接再厉！"
    elif avg_score >= 60:
        return "💪 基础扎实，可以挑战更高分数！"
    else:
        return "📖 加油学习，相信你一定能够进步！"

# 辅助方法：获取学习建议
def _get_study_tip(avg_score):
    """根据平均分返回学习建议"""
    if avg_score >= 90:
        return "保持当前的学习方法，可以尝试帮助其他同学"
    elif avg_score >= 80:
        return "可以尝试总结错题，进一步提高准确率"
    elif avg_score >= 60:
        return "建议多做练习，加强对知识点的理解"
    else:
        return "建议先复习基础知识，再进行答题练习"


# 获得科目下的所有试卷，如形考1试卷，形考2试卷
@router.get('/get_sj_list')
async def get_sj_list(kc_id: int,current_user: dict = Depends(verify_token_and_get_payload),db: Session = DatabaseDep):
    try:
        if not kc_id:
            return {
                'success': False,
                'msg': '课程ID不能为空',
                'data': None
            }

        # 获取试卷类型信息
        sql_exam_types = text("""
            SELECT a.id, a.kc_id, a.pc, a.zt,a.lx_id, b.mc
            FROM exam_sj a
            INNER JOIN exam_sj_lx b ON a.lx_id = b.id
            WHERE pc = :pc and a.kc_id = :kc_id
        """)
        result = db.execute(sql_exam_types, {'pc': current_user.get('sys_pc'), 'kc_id': kc_id}).fetchall()
        
        sj_list = []
        for row in result:
            # 根据试卷类型设置不同的样式
            exam_type_style = _get_exam_type_style(row.lx_id, row.mc)

            exame = {
                'sj_id': row.id,  #试卷表的id列
                'sj_zt': row.zt,
                'sj_lx_id': row.lx_id,
                'sj_type_mc': row.mc,
                # 新增样式相关字段
                'type_style': exam_type_style,
                'status_text': '已开启' if row.zt == 1 else '未开启',
                'status_color': 'success' if row.zt == 1 else 'warning',
                'icon': exam_type_style['icon']
            }
            sj_list.append(exame)
        
        sys_info = db.query(lw_sys).filter_by(dq1_mc=current_user.get('dq1_mc')).first()
        if not sys_info:
            return {
                'success': False,
                'msg': '系统配置信息不存在',
                'data': None
            }
        # 需要遍历每一个试卷，然后查询该试卷学生的答题基本信息
        # 遍历每个试卷,查询学生答题记录
        for sj in sj_list:
            # 查询该试卷的学生答题记录（只查询已提交的记录，zt=1）
            dt_records = db.query(ExamXsDt).filter_by(
                xh=current_user.get('xs_xh'),
                sj_id=sj['sj_id'],
                pc=current_user.get('sys_pc'),
                zt=1
            ).order_by(ExamXsDt.cs.desc()).all()
            
            # 添加答题记录数量
            sj['dt_num'] = len(dt_records)
            
            # 转换答题记录为字典格式
            sj_dt = []
            for record in dt_records:
                # 计算总成绩和状态
                total_score = (record.cj or 0) + (record.zgt_cj or 0)
                is_passed = total_score >= 60

                # 根据成绩设置样式
                score_style = _get_score_style(total_score, is_passed)

                # 根据状态设置状态文本
                status_info = _get_status_info(record.zt, record.zgt_zt)

                dt_info = {
                    'cj': record.cj,  # 客观题成绩
                    'zgt_cj': record.zgt_cj,  # 主观题成绩
                    'zt': record.zt,  # 客观题状态
                    'zgt_zt': record.zgt_zt,  # 主观题状态
                    'tjsj': record.tjsj.strftime('%Y-%m-%d %H:%M:%S') if record.tjsj else None,  # 提交时间
                    'pysj': record.pysj.strftime('%Y-%m-%d %H:%M:%S') if record.pysj else None,  # 评阅时间
                    'cs': record.cs,  # 答题次数
                    'tm_id': record.tm_id,
                    'zgt_tm_id': record.zgt_tm_id,
                    # 新增样式相关字段
                    'total_score': total_score,
                    'is_passed': is_passed,
                    'score_style': score_style,
                    'status_info': status_info,
                    'attempt_badge': f"第{record.cs}次" if record.cs else "未知"
                }
                sj_dt.append(dt_info)
            
            # 将答题记录添加到试卷信息中
            sj['sj_dt'] = sj_dt
        # 计算统计信息
        total_papers = len(sj_list)
        completed_papers = len([sj for sj in sj_list if sj['dt_num'] > 0])
        available_papers = len([sj for sj in sj_list if sj['sj_zt'] == 1])

        return {
            'success': True,
            'msg': '获取成功',
            'data': {
                'sj_list': sj_list,
                'sys_zcks_switch': sys_info.sys_zcks_switch,
                'statistics': {
                    'total_papers': total_papers,
                    'completed_papers': completed_papers,
                    'available_papers': available_papers,
                    'completion_rate': round((completed_papers / total_papers * 100), 1) if total_papers > 0 else 0
                },
                'tips': {
                    'title': '💡 答题小贴士',
                    'items': [
                        '建议先完成形考1，再进行形考2',
                        '每次答题都会记录成绩，可多次尝试提高分数',
                        '主观题需要等待老师评阅才能看到最终成绩',
                        '答题时请仔细阅读题目，确认后再提交'
                    ]
                },
                'progress_config': {
                    'colors': {
                        'excellent': '#52c41a',  # 90分以上
                        'good': '#1890ff',       # 80-89分
                        'pass': '#faad14',       # 60-79分
                        'fail': '#f5222d'        # 60分以下
                    }
                }
            }
        }

    except Exception as e:
        logging.error(f"获取自测科目列表失败: {str(e)}")
        return {
            'code': 1,
            'msg': f'获取自测科目列表失败: {str(e)}',
            'data': None
        }




# 获取答题记录列表
@router.get('/get_exam_records')
async def get_exam_records(kc_id: int, sj_id: int, current_user: dict = Depends(verify_token_and_get_payload), db: Session = DatabaseDep):
    try:
        records = db.query(ExamXsDt).filter_by(
            xh=current_user.get('xs_xh'),
            sj_id=sj_id,
            pc=current_user.get('sys_pc')
        ).order_by(ExamXsDt.cs.desc()).all()

        record_list = []
        for record in records:
            record_list.append({
                'id': str(record.id),
                'zt': record.zt,
                'cs': record.cs,
                'cj': record.cj,
                'tjsj': record.tjsj.strftime('%Y-%m-%d %H:%M:%S') if record.tjsj else None
            })

        return {
            'success': True,
            'msg': '获取记录成功',
            'data': {
                'records': record_list
            }
        }
    except Exception as e:
        return {
            'success': False,
            'msg': f'获取记录失败: {str(e)}',
            'data': None
        }

# 创建空答题记录
@router.post('/create_exam_record')
async def create_exam_record(request: dict, current_user: dict = Depends(verify_token_and_get_payload), db: Session = DatabaseDep):
    try:
        kc_id = request.get('kc_id')
        sj_id = request.get('sj_id')

        if not kc_id or not sj_id:
            return {
                'success': False,
                'msg': '参数不完整',
                'data': None
            }

        all_records = db.query(ExamXsDt).filter_by(
            xh=current_user.get('xs_xh'),
            sj_id=sj_id,
            pc=current_user.get('sys_pc')
        ).all()
        
        exam_xs_dt_num = len(all_records)

        if exam_xs_dt_num >= 3:
            return {
                'success': False,
                'msg': '已达到最大考试次数（3次）',
                'data': None
            }
        
        next_cs = exam_xs_dt_num + 1
        if next_cs > 3:
            return {
                'success': False,
                'msg': '考试次数不能超过3次',
                'data': None
            }

        kcid = db.query(ExamKc).filter_by(id=kc_id).first().kcid
        user_xs = db.query(Student).filter_by(xs_xh=current_user.get('xs_xh')).first()

        new_record = ExamXsDt(
            xh=user_xs.xs_xh,
            xm=user_xs.xs_xm,
            kc_id=kcid,
            sj_id=sj_id,
            tm_id='',
            fz_id='',
            dt='',
            da='',
            cj=0,
            zgt_tm_id='',
            zgt_fz_id='',
            zgt_dt='',
            zgt_pyfs='',
            pc=current_user.get('sys_pc'),
            cs=next_cs,
            zt=0,
            zgt_zt=0,
            zgt_cj=0,
            tjsj=datetime.now(),
            source='小程序'
        )
        db.add(new_record)
        db.commit()
        db.refresh(new_record)

        return {
            'success': True,
            'msg': '创建记录成功',
            'data': {
                'jl_id': str(new_record.id)
            }
        }
    except Exception as e:
        db.rollback()
        return {
            'success': False,
            'msg': f'创建记录失败: {str(e)}',
            'data': None
        }

# 保存答题答案（不提交）
@router.post('/save_exam_answers')
async def save_exam_answers(save_request: SaveAnswersRequest, current_user: dict = Depends(verify_token_and_get_payload), db: Session = DatabaseDep):
    try:
        jl_id = save_request.jl_id
        answers = save_request.answers

        if not jl_id or not answers:
            return {
                'success': False,
                'msg': '参数不完整',
                'data': None
            }

        record = db.query(ExamXsDt).filter_by(
            id=int(jl_id),
            xh=current_user.get('xs_xh')
        ).first()

        if not record:
            return {
                'success': False,
                'msg': '记录不存在',
                'data': None
            }

        if record.zt == 1:
            return {
                'success': False,
                'msg': '该记录已提交，无法修改',
                'data': None
            }

        answer_dict = {item["tm_id"]: item["tm_dt"] for item in answers}
        tm_ids = ','.join(str(answer.get('tm_id')) for answer in answers)
        
        sql_paper = text(f"""
            select * from exam_tm_zj where id in ({tm_ids}) 
            """)
        result = db.execute(sql_paper).fetchall()
        sj_tm_list = []
        for row in result:
            tm = {
                'id': row.id,
                'tx': row.tx,
                'fz': row.fz,
                'da': row.da,
            }
            sj_tm_list.append(tm)
        
        merged_tm_list = [
            {**tm, "dt": answer_dict.get(tm["id"], '')}
            for tm in sj_tm_list
        ]

        type_map = {
            "主观题": "主观题",
            "单选题": "非主观题",
            "多选题": "非主观题",
            "判断题": "非主观题"
        }

        categorized = {
            "主观题": [],
            "非主观题": []
        }
        
        for tm in merged_tm_list:
            category = type_map.get(tm["tx"], "未知类型")
            categorized[category].append(tm)

        zgt_dt_str = '|'.join(str(tm.get('dt', '')) for tm in categorized['主观题'])
        zgt_tm_id_str = ','.join(str(tm.get('id', '')) for tm in categorized['主观题'])
        zgt_fz_str = ','.join(str(tm.get('fz', '')) for tm in categorized['主观题'])

        da_str = '|'.join(str(tm.get('da', '')) for tm in categorized['非主观题'])
        dt_str = '|'.join(str(tm.get('dt', '')) for tm in categorized['非主观题'])
        tm_id_str = ','.join(str(tm.get('id', '')) for tm in categorized['非主观题'])
        fz_str = ','.join(str(tm.get('fz', '')) for tm in categorized['非主观题'])

        record.tm_id = tm_id_str
        record.fz_id = fz_str
        record.dt = dt_str
        record.da = da_str
        record.zgt_tm_id = zgt_tm_id_str
        record.zgt_fz_id = zgt_fz_str
        record.zgt_dt = zgt_dt_str

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

# 获取考试题目
@router.get('/get_exame_paper')
async def get_exame_paper(kc_id: int, sj_id: int, jl_id: int = None, _: dict = Depends(verify_token_only), db: Session = DatabaseDep):
    try:
        if not kc_id or not sj_id:
            raise HTTPException(status_code=400, detail={
                'code': 1,
                'msg': '参数不完整',
                'data': None
            })

        # 获取考试科目名称
        kc_name = db.query(ExamKc).filter_by(id=kc_id).first().kcmc

        # 去题目表取题目
        sql_paper = text(f"""
            select * from exam_tm_zj where sj_id=:sj_id order by tx,id
            """)
        result = db.execute(sql_paper, {'sj_id': sj_id}).fetchall()


        sj_tm_list = []
        question_types = {}  # 统计题型

        for row in result:
            # 统计题型
            question_types[row.tx] = question_types.get(row.tx, 0) + 1

            # 根据题型设置样式
            type_style = _get_question_type_style(row.tx)

            tm = {
                'tm_id': row.id,
                'tx': row.tx,
                'tg': row.tg,
                'xxA': row.xxA,
                'xxB': row.xxB,
                'xxC': row.xxC,
                'xxD': row.xxD,
                # 新增样式相关字段
                'type_style': type_style,
                'question_number': len(sj_tm_list) + 1  # 题目序号
            }
            sj_tm_list.append(tm)

        # 计算题目统计信息
        total_questions = len(sj_tm_list)

        return {
            'code': 0,
            'msg': '获取成功',
            'data': {
                'kc_name': kc_name,
                'sj_tm_list': sj_tm_list,
                'exam_info': {
                    'total_questions': total_questions,
                    'question_types': question_types,
                    'estimated_time': total_questions * 2,  # 预估答题时间（分钟）
                },
                'exam_tips': {
                    'title': '📋 答题须知',
                    'rules': [
                        '请仔细阅读每道题目，确认答案后再进行下一题',
                        '单选题和判断题只能选择一个答案',
                        '多选题可以选择多个答案，请全部选中正确选项',
                        '主观题请详细作答，字数不少于50字',
                        '答题完成后请检查一遍再提交'
                    ],
                    'time_tip': f'建议答题时间：{total_questions * 2}分钟'
                },
                'ui_settings': {
                    'show_progress': True,
                    'auto_save': True,
                    'confirm_submit': True
                }
            }
        }

    except Exception as e:
        logging.error(f"获取自测科目列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail={
            'code': 1,
            'msg': f'获取自测科目列表失败: {str(e)}',
            'data': None
        })


# 交卷
@router.post('/submit_exam')
async def submit_exam(submit_request: SubmitExamRequest, current_user: dict = Depends(verify_token_and_get_payload), db: Session = DatabaseDep):
    try:
        sj_id = submit_request.sj_id
        kc_id = submit_request.kc_id
        jl_id = submit_request.jl_id
        answers = submit_request.answers
        
        if not sj_id or not kc_id or not jl_id or not answers:
            return {
                'success': False,
                'msg': '参数不完整',
                'data': None
            }

        record = db.query(ExamXsDt).filter_by(
            id=int(jl_id),
            xh=current_user.get('xs_xh'),
            sj_id=sj_id,
            pc=current_user.get('sys_pc')
        ).first()

        if not record:
            return {
                'success': False,
                'msg': '答题记录不存在',
                'data': None
            }

        if record.zt == 1:
            return {
                'success': False,
                'msg': '该记录已提交，无法重复提交',
                'data': None
            }
        answer_dict = {item["tm_id"]: item["tm_dt"] for item in answers}
        tm_ids = ','.join(str(answer.get('tm_id')) for answer in answers)
        sql_paper = text(f"""
            select * from exam_tm_zj where id in ({tm_ids}) 
            """)
        result = db.execute(sql_paper).fetchall()
        sj_tm_list = []
        for row in result:
            tm = {
                'id': row.id,
                'tx': row.tx,
                'fz': row.fz,
                'da': row.da,
            }
            sj_tm_list.append(tm)
        merged_tm_list = [
            {**tm, "dt": answer_dict.get(tm["id"], '')}
            for tm in sj_tm_list
        ]
        # 定义类型映射（非主观题的子类型 -> 统一分类）
        type_map = {
            "主观题": "主观题",
            "单选题": "非主观题",
            "多选题": "非主观题",
            "判断题": "非主观题"
        }

        categorized = {
            "主观题": [],
            "非主观题": []
        }
        for tm in merged_tm_list:
            category = type_map.get(tm["tx"], "未知类型")
            categorized[category].append(tm)

        zgt_dt_str = '|'.join(str(tm.get('dt', '')) for tm in categorized['主观题'])
        zgt_tm_id_str = ','.join(str(tm.get('id', '')) for tm in categorized['主观题'])
        zgt_fz_str = ','.join(str(tm.get('fz', '')) for tm in categorized['主观题'])

        da_str = '|'.join(str(tm.get('da', '')) for tm in categorized['非主观题'])
        dt_str = '|'.join(str(tm.get('dt', '')) for tm in categorized['非主观题'])
        tm_id_str = ','.join(str(tm.get('id', '')) for tm in categorized['非主观题'])
        fz_str = ','.join(str(tm.get('fz', '')) for tm in categorized['非主观题'])

        fzgt_total_score = 0
        for tm in categorized['非主观题']:
            if str(tm.get('dt', '')).strip() == str(tm.get('da', '')).strip():
                fz = tm.get('fz', 0)
                fzgt_total_score += fz

        exame_sj = db.query(ExamSj).filter_by(id=sj_id).first()
        if not exame_sj:
            return {
                'success': False,
                'msg': '试卷不存在',
                'data': None
            }

        zgt_zt = 0
        if exame_sj.lx_id == 1 or exame_sj.lx_id == 2:
            zgt_zt = 1

        record.tm_id = tm_id_str
        record.fz_id = fz_str
        record.dt = dt_str
        record.da = da_str
        record.cj = fzgt_total_score
        record.zgt_tm_id = zgt_tm_id_str
        record.zgt_fz_id = zgt_fz_str
        record.zgt_dt = zgt_dt_str
        record.zt = 1
        record.zgt_zt = zgt_zt
        record.zgt_cj = 0
        record.tjsj = datetime.now()
        
        db.commit()

        total_questions = len(categorized['非主观题'])
        correct_answers = sum(1 for tm in categorized['非主观题']
                            if str(tm.get('dt', '')).strip() == str(tm.get('da', '')).strip())
        accuracy_rate = round((correct_answers / total_questions * 100), 1) if total_questions > 0 else 0

        return {
            'success': True,
            'msg': '交卷成功！',
            'data': {
                'submit_result': {
                    'attempt_number': record.cs,
                    'objective_score': fzgt_total_score,
                    'total_questions': total_questions,
                    'correct_answers': correct_answers,
                    'accuracy_rate': accuracy_rate,
                    'submit_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'has_subjective': len(categorized['主观题']) > 0
                },
                'feedback': {
                    'title': '🎉 提交成功',
                    'message': f'您的第{record.cs}次答题已提交成功！',
                    'score_info': f'客观题得分：{fzgt_total_score}分',
                    'accuracy_info': f'客观题正确率：{accuracy_rate}%',
                    'next_steps': [
                        '客观题成绩已自动计算完成',
                        '主观题需要等待老师评阅' if len(categorized['主观题']) > 0 else '本次答题已全部完成',
                        '您可以继续尝试其他试卷或重新答题提高成绩'
                    ]
                },
                'performance': {
                    'level': 'excellent' if accuracy_rate >= 90 else 'good' if accuracy_rate >= 80 else 'pass' if accuracy_rate >= 60 else 'need_improvement',
                    'color': '#52c41a' if accuracy_rate >= 90 else '#1890ff' if accuracy_rate >= 80 else '#faad14' if accuracy_rate >= 60 else '#f5222d'
                }
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail={
            'success': False,
            'msg': f'交卷失败: {str(e)}',
            'data': None
        })



# 获取题目中的图片地址展示
@router.get('/image/{image_path:path}')
async def get_exam_image(image_path: str):

    try:
        # 拼接服务器A上图片的完整路径
        image_url = f'http://172.16.100.101/{image_path}'
        
        # 向服务器A发送请求获取图片数据
        response = requests.get(image_url, timeout=5)
        
        # 检查响应状态
        if response.status_code != 200:
            logging.error(f"获取图片失败: HTTP {response.status_code}")
            raise HTTPException(status_code=404, detail={
                'code': 1,
                'msg': '获取图片失败',
                'data': None
            })

        # 获取图片的MIME类型
        content_type = response.headers.get('content-type', 'image/jpeg')

        # 将图片数据转换为Base64编码并返回标准数据格式
        import base64
        
        # 将图片数据转换为Base64编码
        image_base64 = base64.b64encode(response.content).decode('utf-8')
        
        # 获取文件名
        filename = image_path.split('/')[-1]
        
        return {
            'success': True,
            'msg': '获取图片成功',
            'data': {
                'image_base64': image_base64,
                'filename': filename,
                'content_type': content_type,
                'file_size': len(response.content),
                'image_path': image_path
            }
        }

    except requests.exceptions.Timeout:
        logging.error("获取图片超时")
        raise HTTPException(status_code=504, detail={
            'code': 1,
            'msg': '获取图片超时',
            'data': None
        })

    except requests.exceptions.RequestException as e:
        logging.error(f"获取图片请求异常: {str(e)}")
        raise HTTPException(status_code=500, detail={
            'code': 1,
            'msg': '获取图片失败',
            'data': None
        })

    except Exception as e:
        logging.error(f"获取图片失败: {str(e)}")
        raise HTTPException(status_code=500, detail={
            'code': 1,
            'msg': '获取图片失败',
            'data': None
        })

