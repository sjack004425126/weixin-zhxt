# -*- coding: utf-8 -*-
"""
开放教育教师 - 评阅管理

数据结构（exam_xs_dt）：
- 每条记录 = 一个学生在一个科目一次考试的所有题目答案
- t_id: 评阅教师ID（直接用此字段查询，不通过班级学生关联）
- kc_id: 课程代码字符串，如 '00815'
- zgt_tm_id: 主观题题目ID，逗号分隔，如 '49519' 或 '49502,49503'
- zgt_fz_id: 主观题各题分值，逗号分隔
- zgt_dt: 主观题学生答案，逗号分隔
- zgt_pyfs: 主观题各题评分，逗号分隔，评完一题写入对应位置
- zgt_zt: null/0=未全部评完，1=已全部评完锁定
- zt: 1=已提交答卷

批阅状态：
- 按题目维度：看 zgt_pyfs[i] 是否有值
- 整体锁定：所有题都有分后自动设 zgt_zt=1，之后拒绝修改
"""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_, text as sa_text
from models.models import ExamKc, ExamXsDt, ExamFppy, lw_sys, ExamTmZj
from init.dependencies import DatabaseDep
from common.auth import verify_token_and_get_payload
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/open_teacher", tags=["开放教育教师-评阅管理"])


def _parse_comma(s) -> list:
    """按 | 或 , 分割（兼容历史数据），保留空位（不过滤空字符串），兼容 bytes 类型"""
    if not s:
        return []
    if isinstance(s, bytes):
        s = s.decode('utf-8', errors='ignore')
    s = str(s)
    # 优先按 | 分割；如果没有 | 但有 , ，按 , 分割（兼容旧数据）
    sep = '|' if '|' in s else ','
    return [x.strip() for x in s.split(sep)]


def _safe_int(v, default=0) -> int:
    try:
        return int(float(str(v)))
    except (TypeError, ValueError):
        return default


def _get_current_pc(db) -> int:
    sys_info = db.query(lw_sys).first()
    return sys_info.sys_pc if sys_info else None


def _query_by_tid_pc(db, t_id, pc, extra_filters=None) -> list:
    """
    先用 EXISTS 子查询通过 exam_fppy 确定该教师待批阅的学生-课程组合，
    再去 exam_xs_dt 查找实际答题记录。
    避免直接查 exam_xs_dt.t_id，而是通过分派表确定目标。
    """
    fppy_subq = db.query(ExamFppy).filter(
        ExamFppy.pc == pc,
        ExamFppy.t_id == t_id,
        ExamFppy.xh.isnot(None),
        ExamFppy.kcid.isnot(None),
    ).subquery()

    q = db.query(ExamXsDt).filter(
        ExamXsDt.pc == pc,
        # 移除 zt == 1 条件，只要该学生有主观题需要批阅就显示（无论是否已答题）
        ExamXsDt.zgt_tm_id.isnot(None),
        sa_text("DATALENGTH(exam_xs_dt.zgt_tm_id) > 0"),
        ExamXsDt.kc_id == fppy_subq.c.kcid,
        ExamXsDt.xh == fppy_subq.c.xh,
    )
    if extra_filters:
        q = q.filter(*extra_filters)
    return q.all()


@router.get('/review/courses')
async def get_review_courses(
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """获取当前批次分配给该教师的、有主观题的课程列表"""
    try:
        pc = _get_current_pc(db)
        t_id = current_user.get('t_id')
        logger.info(f"[review/courses] t_id={t_id}, pc={pc}")

        if not pc:
            return {'success': False, 'msg': '未找到当前批次配置', 'data': None}

        records = _query_by_tid_pc(db, t_id, pc)
        logger.info(f"[review/courses] 查到记录数={len(records)}")

        if not records:
            # 诊断：分别用各条件查，定位是哪个筛选项把数据挡住了
            try:
                from sqlalchemy import func
                cnt_tid = db.query(func.count(ExamXsDt.id)).filter(ExamXsDt.t_id == t_id).scalar()
                cnt_tid_pc = db.query(func.count(ExamXsDt.id)).filter(
                    ExamXsDt.t_id == t_id, ExamXsDt.pc == pc
                ).scalar()
                cnt_tid_pc_zt = db.query(func.count(ExamXsDt.id)).filter(
                    ExamXsDt.t_id == t_id, ExamXsDt.pc == pc, ExamXsDt.zt == 1
                ).scalar()
                cnt_pc_zgt = db.query(func.count(ExamXsDt.id)).filter(
                    ExamXsDt.pc == pc, ExamXsDt.zt == 1,
                    ExamXsDt.zgt_tm_id.isnot(None),
                    sa_text("DATALENGTH(exam_xs_dt.zgt_tm_id) > 0"),
                ).scalar()
                # 该批次下 t_id 的分布（前10个），用于判断测试数据的 t_id 是否就是当前登录教师
                tid_rows = db.query(ExamXsDt.t_id, func.count(ExamXsDt.id)).filter(
                    ExamXsDt.pc == pc,
                    ExamXsDt.zgt_tm_id.isnot(None),
                    sa_text("DATALENGTH(exam_xs_dt.zgt_tm_id) > 0"),
                ).group_by(ExamXsDt.t_id).all()
                logger.warning(
                    f"[review/courses][诊断] t_id={t_id} pc={pc} | "
                    f"按t_id={cnt_tid} | +pc={cnt_tid_pc} | +zt=1={cnt_tid_pc_zt} | "
                    f"该批次有主观题记录(不限t_id)={cnt_pc_zgt} | "
                    f"该批次主观题记录的t_id分布(前10)={tid_rows[:10]}"
                )
            except Exception as diag_err:
                logger.warning(f"[review/courses][诊断失败] {diag_err}")
            return {'success': True, 'msg': '获取成功', 'data': []}

        # 查课程名称
        kc_ids = list(set(r.kc_id for r in records if r.kc_id))
        kc_map = {}
        for kc_id in kc_ids:
            kc = db.query(ExamKc).filter(ExamKc.kcid == str(kc_id)).first()
            if kc:
                kc_map[kc_id] = kc

        # 按 kc_id 聚合
        course_dict = {}
        for r in records:
            key = r.kc_id
            if key not in course_dict:
                kc = kc_map.get(key)
                course_dict[key] = {
                    'kc_id': key,
                    'pc': pc,
                    'kcmc': kc.kcmc if kc else f'课程{key}',
                    'total': 0,
                    'pending': 0,
                    'done': 0,
                }
            course_dict[key]['total'] += 1
            # 判断该记录是否有未评分的题：pyfs 里有空位或长度不足
            tm_ids = _parse_comma(r.zgt_tm_id)
            pyfs = _parse_comma(r.zgt_pyfs)
            has_pending = any(
                i >= len(pyfs) or pyfs[i] == ''
                for i in range(len(tm_ids))
            ) if tm_ids else False
            if has_pending:
                course_dict[key]['pending'] += 1
            else:
                course_dict[key]['done'] += 1

        course_list = sorted(course_dict.values(), key=lambda x: x['pending'], reverse=True)
        return {'success': True, 'msg': '获取成功', 'data': course_list}
    except Exception as e:
        logger.error(f"获取评阅课程列表失败: {str(e)}")
        return {'success': False, 'msg': f'获取失败: {str(e)}', 'data': None}


@router.get('/review/questions')
async def get_review_questions(
    kc_id: str = Query(..., description="课程代码，如 00815"),
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """获取某课程的主观题列表（按题目聚合，含待评阅人数）"""
    try:
        pc = _get_current_pc(db)
        t_id = current_user.get('t_id')
        logger.info(f"[review/questions] kc_id={kc_id}, t_id={t_id}, pc={pc}")

        records = _query_by_tid_pc(db, t_id, pc, [ExamXsDt.kc_id == kc_id])
        logger.info(f"[review/questions] 记录数={len(records)}")
        if not records:
            return {'success': True, 'msg': '获取成功', 'data': []}

        r0 = records[0]
        logger.info(f"[review/questions] 第一条: id={r0.id}, zgt_tm_id={str(r0.zgt_tm_id)[:100]}, zgt_fz_id={str(r0.zgt_fz_id)[:50]}, zgt_pyfs={str(r0.zgt_pyfs)[:50]}")

        # 按题目位置聚合
        question_map = {}
        for rec in records:
            tm_ids = _parse_comma(rec.zgt_tm_id)
            fz_ids = _parse_comma(rec.zgt_fz_id)
            pyfs_list = _parse_comma(rec.zgt_pyfs)

            for i, tm_id in enumerate(tm_ids):
                if not tm_id:
                    continue
                if tm_id not in question_map:
                    fz = _safe_int(fz_ids[i]) if i < len(fz_ids) else 0
                    question_map[tm_id] = {
                        'tm_id': tm_id,
                        'tm_index': i,
                        'fz': fz,
                        'total': 0,
                        'pending': 0,
                        'reviewed': 0,
                    }
                question_map[tm_id]['total'] += 1
                # 该题是否已评分：pyfs 对应位置有非空值
                scored = i < len(pyfs_list) and pyfs_list[i] != ''
                if scored:
                    question_map[tm_id]['reviewed'] += 1
                else:
                    question_map[tm_id]['pending'] += 1

        questions = sorted(question_map.values(), key=lambda x: x['tm_index'])
        for q in questions:
            fz = q['fz']
            # 快捷分数：每10%一档，覆盖全分段，去重后降序
            if fz <= 10:
                # 小分值题：每1分一档
                scores = list(range(fz, -1, -1))
            else:
                # 大分值题：每10%一档 + 边界值，去重排序
                step_scores = set()
                for p in range(100, -1, -10):
                    step_scores.add(int(fz * p / 100))
                # 补充常用分数点
                for p in [95, 85, 75, 65, 55]:
                    step_scores.add(int(fz * p / 100))
                scores = sorted(step_scores, reverse=True)
            q['quick_scores'] = scores

        return {'success': True, 'msg': '获取成功', 'data': questions}
    except Exception as e:
        logger.error(f"获取题目列表失败: {str(e)}")
        return {'success': False, 'msg': f'获取失败: {str(e)}', 'data': None}


@router.get('/review/answers')
async def get_question_answers(
    kc_id: str = Query(...),
    tm_id: str = Query(..., description="题目ID"),
    tm_index: int = Query(..., description="题目在 zgt_tm_id 中的位置(0-based)"),
    only_pending: int = Query(0, description="1=只看未评阅，0=全部"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """获取某题目下所有学生的答案列表（分页）"""
    try:
        pc = _get_current_pc(db)
        t_id = current_user.get('t_id')

        records = _query_by_tid_pc(db, t_id, pc, [ExamXsDt.kc_id == kc_id])
        records.sort(key=lambda x: x.xh or '')
        logger.info(f"[review/answers] kc_id={kc_id}, tm_id={tm_id}, tm_index={tm_index}, 记录数={len(records)}")
        if records:
            r0 = records[0]
            tm_ids_parsed = _parse_comma(r0.zgt_tm_id)
            logger.info(f"[review/answers] 第一条 zgt_tm_id原始={str(r0.zgt_tm_id)[:80]}, 解析={tm_ids_parsed}, tm_id在其中={tm_id in tm_ids_parsed}")

        answer_list = []
        for rec in records:
            tm_ids = _parse_comma(rec.zgt_tm_id)
            if tm_id not in tm_ids:
                continue
            idx = tm_ids.index(tm_id)

            fz_ids = _parse_comma(rec.zgt_fz_id)
            pyfs_list = _parse_comma(rec.zgt_pyfs)
            dt_list = _parse_comma(rec.zgt_dt)

            answer = dt_list[idx] if idx < len(dt_list) else ''
            fz = _safe_int(fz_ids[idx]) if idx < len(fz_ids) else 0

            current_score = None
            if idx < len(pyfs_list) and pyfs_list[idx] != '':
                try:
                    current_score = float(pyfs_list[idx])
                except (ValueError, TypeError):
                    pass

            is_locked = rec.zgt_zt == 1
            this_scored = current_score is not None

            answer_list.append({
                'record_id': rec.id,
                'xh': rec.xh,
                'xm': rec.xm,
                'tm_index': idx,
                'answer': answer,
                'fz': fz,
                'current_score': current_score,
                'is_locked': is_locked,
                'this_scored': this_scored,
            })

        if only_pending:
            answer_list = [a for a in answer_list if not a['this_scored']]

        total = len(answer_list)
        start = (page - 1) * page_size
        paged = answer_list[start:start + page_size]

        return {
            'success': True, 'msg': '获取成功',
            'data': {'answers': paged, 'total': total, 'page': page, 'page_size': page_size}
        }
    except Exception as e:
        logger.error(f"获取答案列表失败: {str(e)}")
        return {'success': False, 'msg': f'获取失败: {str(e)}', 'data': None}


class ScoreRequest(BaseModel):
    record_id: int
    tm_index: int
    score: float


@router.post('/review/score')
async def submit_score(
    req: ScoreRequest,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """
    给某学生某题打分。
    - 允许重复评分（修改已评分的题）
    - 每次评分后重新计算 zgt_cj 和 zgt_zt
    - 只有所有主观题都有分数时才设 zgt_zt=1
    """
    try:
        record = db.query(ExamXsDt).filter(ExamXsDt.id == req.record_id).first()
        if not record:
            return {'success': False, 'msg': '答题记录不存在'}

        tm_ids = _parse_comma(record.zgt_tm_id)
        fz_ids = _parse_comma(record.zgt_fz_id)
        total_questions = len(tm_ids)

        if req.tm_index >= total_questions:
            return {'success': False, 'msg': f'题目位置超出范围（共{total_questions}题）'}

        # 验证分数范围
        if req.tm_index < len(fz_ids):
            max_score = _safe_int(fz_ids[req.tm_index])
            if req.score > max_score:
                return {'success': False, 'msg': f'分数不能超过题目分值 {max_score} 分'}
        if req.score < 0:
            return {'success': False, 'msg': '分数不能为负数'}

        # 更新 zgt_pyfs 对应位置（允许覆盖已有分数）
        pyfs_list = _parse_comma(record.zgt_pyfs)
        while len(pyfs_list) < total_questions:
            pyfs_list.append('')
        pyfs_list[req.tm_index] = str(int(req.score))
        record.zgt_pyfs = '|'.join(pyfs_list)

        # 重新计算主观题总分，判断是否所有题都已评完
        total_zgt = 0
        all_scored = True
        for s in pyfs_list:
            if s == '' or s is None:
                all_scored = False
            else:
                try:
                    total_zgt += float(s)
                except (ValueError, TypeError):
                    all_scored = False

        record.zgt_cj = int(total_zgt)
        # 当所有主观题都评分后，自动锁定
        if all_scored:
            record.zgt_zt = 1
        record.t_id = current_user.get('t_id')
        record.pysj = datetime.now()
        db.commit()

        return {
            'success': True,
            'msg': '评分成功' + ('，该学生所有主观题已全部评完' if all_scored else ''),
            'data': {'zgt_pyfs': record.zgt_pyfs, 'zgt_cj': record.zgt_cj, 'all_scored': all_scored}
        }
    except Exception as e:
        db.rollback()
        logger.error(f"评分失败: {str(e)}")
        return {'success': False, 'msg': f'评分失败: {str(e)}'}


@router.get('/review/question_detail')
async def get_question_detail(
    tm_id: str = Query(..., description="题目ID（exam_tm_zj.id）"),
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """获取题目详情（题干 + 参考答案）"""
    try:
        q = db.query(ExamTmZj).filter(ExamTmZj.id == _safe_int(tm_id)).first()
        if not q:
            return {'success': False, 'msg': f'未找到题目（ID={tm_id}）', 'data': None}

        return {
            'success': True,
            'msg': '获取成功',
            'data': {
                'id': q.id,
                'tx': q.tx or '主观题',
                'tg': q.tg or '',
                'da': q.da or '',
                'fz': q.fz or 0,
            }
        }
    except Exception as e:
        logger.error(f"获取题目详情失败: {str(e)}")
        return {'success': False, 'msg': f'获取失败: {str(e)}', 'data': None}


@router.get('/review/finish_check')
async def finish_check(
    kc_id: str = Query(...),
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """
    统计该科目所有学生的答题完成情况：
    - 客观题：zt=1 表示已提交
    - 主观题：zgt_tm_id 有值，且 zgt_pyfs 每个位置都有分数
    - zgt_zt=1 表示已锁定
    """
    try:
        pc = _get_current_pc(db)
        t_id = current_user.get('t_id')
        records = _query_by_tid_pc(db, t_id, pc, [ExamXsDt.kc_id == kc_id])

        student_list = []
        for rec in records:
            tm_ids = _parse_comma(rec.zgt_tm_id)
            fz_ids = _parse_comma(rec.zgt_fz_id)
            pyfs_list = _parse_comma(rec.zgt_pyfs)
            total_zgt = len(tm_ids)

            # 统计主观题评分情况
            scored_count = sum(
                1 for i in range(total_zgt)
                if i < len(pyfs_list) and pyfs_list[i] != ''
            )
            all_zgt_scored = (scored_count == total_zgt) and total_zgt > 0

            # 客观题：zt=1 表示已提交
            obj_done = rec.zt == 1

            # 计算主观题总分
            zgt_total_score = 0
            for s in pyfs_list:
                if s and s != '':
                    try:
                        zgt_total_score += float(s)
                    except (ValueError, TypeError):
                        pass

            student_list.append({
                'record_id': rec.id,
                'xh': rec.xh,
                'xm': rec.xm,
                'obj_done': obj_done,
                'obj_score': rec.cj,
                'zgt_total': total_zgt,
                'zgt_scored': scored_count,
                'zgt_score': int(zgt_total_score),
                'all_zgt_scored': all_zgt_scored,
                'is_locked': rec.zgt_zt == 1,
                'can_lock': all_zgt_scored and rec.zgt_zt != 1,
                'total_score': (rec.cj or 0) + int(zgt_total_score),
            })

        # 未锁定且已评完的排前，未评完的排中，已锁定的排后
        def sort_key(s):
            if not s['is_locked'] and s['all_zgt_scored']:
                return 0
            if not s['is_locked'] and not s['all_zgt_scored']:
                return 1
            return 2
        student_list.sort(key=sort_key)

        # 汇总统计
        total = len(student_list)
        locked = sum(1 for s in student_list if s['is_locked'])
        all_scored = sum(1 for s in student_list if s['all_zgt_scored'])
        pending = sum(1 for s in student_list if not s['all_zgt_scored'])

        return {
            'success': True, 'msg': '获取成功',
            'data': {
                'students': student_list,
                'total': total,
                'locked': locked,
                'all_scored': all_scored,
                'pending': pending,
            }
        }
    except Exception as e:
        logger.error(f"完成情况检查失败: {str(e)}")
        return {'success': False, 'msg': f'获取失败: {str(e)}', 'data': None}


class BatchLockRequest(BaseModel):
    record_ids: list  # 要锁定的 record_id 列表


@router.post('/review/batch_lock')
async def batch_lock(
    req: BatchLockRequest,
    current_user: dict = Depends(verify_token_and_get_payload),
    db: Session = DatabaseDep
):
    """
    批量锁定答题记录（设置 zgt_zt=1）。
    只允许锁定主观题全部评完的记录，已锁定的跳过。
    一旦锁定不可解锁。
    """
    try:
        if not req.record_ids:
            return {'success': False, 'msg': '未选择任何记录'}

        success_count = 0
        skip_count = 0
        fail_list = []

        for rid in req.record_ids:
            record = db.query(ExamXsDt).filter(ExamXsDt.id == int(rid)).first()
            if not record:
                fail_list.append(str(rid))
                continue
            if record.zgt_zt == 1:
                skip_count += 1
                continue

            # 验证主观题是否全部评完
            tm_ids = _parse_comma(record.zgt_tm_id)
            pyfs_list = _parse_comma(record.zgt_pyfs)
            all_scored = all(
                i < len(pyfs_list) and pyfs_list[i] != ''
                for i in range(len(tm_ids))
            ) if tm_ids else False

            if not all_scored:
                fail_list.append(f"{record.xm}({record.xh})")
                continue

            record.zgt_zt = 1
            success_count += 1

        db.commit()

        msg = f'锁定成功 {success_count} 条'
        if skip_count:
            msg += f'，已锁定跳过 {skip_count} 条'
        if fail_list:
            msg += f'，主观题未评完无法锁定 {len(fail_list)} 条'

        return {'success': True, 'msg': msg, 'data': {'success': success_count, 'skip': skip_count, 'fail': len(fail_list)}}
    except Exception as e:
        db.rollback()
        logger.error(f"批量锁定失败: {str(e)}")
        return {'success': False, 'msg': f'锁定失败: {str(e)}'}
