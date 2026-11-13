"""
问卷调查模块 - SQLAlchemy 模型（zhpt-new 副本）

说明：
- 与 headphoto/backend/app/models/models.py 同步追加的 17 张表字段保持 1:1 对齐
- zhpt-new 主键统一用 Integer(与项目内已有 oa_* / zz_* 表风格一致)
- 与 docs/survey/04-data-model/01-tables.md 一致
"""
from datetime import datetime
from sqlalchemy import (Boolean, Column, DateTime, ForeignKey, Index,
                        Integer, Numeric, String, Text)
from init.database_optimized import Base


class OaSurveySurvey(Base):
    """问卷主表"""
    __tablename__ = 'oa_survey_survey'

    sid = Column(Integer, primary_key=True, autoincrement=True, comment='问卷ID')
    survey_code = Column(String(16), unique=True, nullable=True, comment='分享码(6-8位字母数字)')
    survey_type = Column(String(16), nullable=False, comment='SURVEY/REGISTRATION/VOTE/EXAM')
    title = Column(String(200), nullable=False, comment='问卷标题')
    description = Column(Text, comment='问卷描述')
    creator_id = Column(Integer, nullable=False, comment='创建者用户ID')
    dept_id = Column(Integer, comment='部门ID（多租户隔离）')
    status = Column(String(16), nullable=False, default='DRAFT', comment='DRAFT/PUBLISHED/CLOSED/ARCHIVED')
    settings = Column(Text, comment='问卷设置 JSON 字符串')
    sub_config = Column(Text, comment='子业务配置 JSON(signup/vote/exam 子项)')
    market = Column(Text, comment='发布渠道 JSON')
    is_anonymous = Column(Boolean, nullable=False, default=False)
    need_audit = Column(Boolean, nullable=False, default=False, comment='是否需要审核(仅 REGISTRATION 问卷生效)')
    allow_users = Column(Text, comment='允许填写人员 JSON [{type:"ZZ_XS"|"ZZ_T"|"OA_XS"|"OA_T"|"HP_STAFF",id:123}]')
    # ---- 答题次数限制(同一 wx_openid+device_id 指纹) ----
    # submit_limit=0 表示不限制(只受 max_answers 约束);
    # submit_limit>0 时按 submit_limit_period 周期计数
    # 周期:once=终身限 N 次;day=自然日内限 N 次;week=自然周内限 N 次;
    #      month=自然月内限 N 次;forever=每天最多 1 次(永远可填,适合打卡)
    submit_limit = Column(Integer, nullable=False, default=0)
    submit_limit_period = Column(String(16), default='once')
    max_answers = Column(Integer, nullable=False, default=0, comment='最大答卷数,0=不限')
    start_at = Column(DateTime, comment='开始时间')
    end_at = Column(DateTime, comment='结束时间')
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)
    archived_at = Column(DateTime, comment='归档时间(软删除标记)')

    __table_args__ = (
        Index('idx_survey_status', 'status'),
        Index('idx_survey_creator', 'creator_id'),
    )

    def __repr__(self):
        return f'<OaSurveySurvey {self.sid} {self.title}>'


class OaSurveyQuestion(Base):
    """题目表"""
    __tablename__ = 'oa_survey_question'

    id = Column(Integer, primary_key=True, autoincrement=True)
    sid = Column(Integer, ForeignKey('oa_survey_survey.sid', ondelete='CASCADE'), nullable=False)
    qid = Column(String(32), nullable=False, comment='业务题目ID(q_001)')
    qtype = Column(String(32), nullable=False, comment='SINGLE/MULTI/TEXT/SCORE/NPS/...')
    title = Column(Text, comment='题目标题')
    description = Column(Text)
    required = Column(Boolean, nullable=False, default=False)
    options = Column(Text, comment='选项 JSON 字符串')
    logic = Column(Text, comment='逻辑 JSON 字符串')
    score = Column(Numeric(10, 2), default=0)
    correct_answer = Column(Text)
    # ---- 量表 / 评分题专有字段 ----
    score_min = Column(Integer, default=1, comment='量表最低值(RATE/SCALE/NPS 用)')
    score_max = Column(Integer, default=5, comment='量表最高值(RATE/SCALE/NPS 用, NPS 强制 10)')
    score_unit = Column(String(16), comment='评分单位,如"分""星"')
    score_style = Column(String(16), default='AUTO', comment='评分展示样式: AUTO/STAR/SLIDER/NUMBER')
    scale_left_label = Column(String(64), comment='量表题最左端标签,如"非常不满意"')
    scale_right_label = Column(String(64), comment='量表题最右端标签,如"非常满意"')
    # ---- 滑动条题专有字段 ----
    slider_min = Column(Integer, default=0, comment='滑动条最小值')
    slider_max = Column(Integer, default=100, comment='滑动条最大值')
    slider_step = Column(Integer, default=1, comment='滑动条步长')
    slider_unit = Column(String(16), comment='滑动条单位')
    media_url = Column(String(500), comment='媒体URL')
    order_no = Column(Integer, nullable=False, default=0)
    bank_id = Column(Integer, comment='来源题库ID')
    random_seed = Column(Integer, comment='随机种子(测评抽题用)')

    __table_args__ = (Index('idx_question_sid_order', 'sid', 'order_no'),)

    def __repr__(self):
        return f'<OaSurveyQuestion {self.qid} type={self.qtype}>'


class OaSurveyQuestionLogic(Base):
    """题目跳转/显示逻辑"""
    __tablename__ = 'oa_survey_question_logic'

    id = Column(Integer, primary_key=True, autoincrement=True)
    question_id = Column(Integer, ForeignKey('oa_survey_question.id', ondelete='CASCADE'), nullable=False)
    type = Column(String(16), nullable=False, comment='JUMP/SHOW/HIDE/REF')
    trigger_qid = Column(String(32))
    op = Column(String(16), comment='EQ/NEQ/LT/GT/CONTAINS')
    logic_value = Column(Text, comment='比较值(JSON 字符串,因 value 是 SQL 关键字)')
    target_qid = Column(String(32))
    target_kind = Column(String(16))
    ref_kind = Column(String(16))
    ref_dest = Column(String(16))
    logic_group = Column(String(16), nullable=False, default='AND')

    __table_args__ = (Index('idx_logic_question', 'question_id'),)


class OaSurveyQuestionBank(Base):
    """题库"""
    __tablename__ = 'oa_survey_question_bank'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    category_id = Column(Integer)
    dept_id = Column(Integer)
    created_by = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    status = Column(String(16), nullable=False, default='ACTIVE')

    __table_args__ = (Index('idx_bank_status', 'status'),)


class OaSurveyBankItem(Base):
    """题库题目"""
    __tablename__ = 'oa_survey_bank_item'

    id = Column(Integer, primary_key=True, autoincrement=True)
    bank_id = Column(Integer, ForeignKey('oa_survey_question_bank.id', ondelete='CASCADE'), nullable=False)
    content = Column(Text)
    options = Column(Text)
    correct_answer = Column(Text)
    score = Column(Numeric(10, 2), default=0)
    difficulty = Column(String(16))
    analysis = Column(Text)
    media_url = Column(String(500))
    status = Column(String(16), nullable=False, default='ACTIVE')

    __table_args__ = (
        Index('idx_bankitem_bank', 'bank_id'),
        Index('idx_bankitem_status', 'status'),
    )


class OaSurveyAnswer(Base):
    """答卷主表"""
    __tablename__ = 'oa_survey_answer'

    aid = Column(Integer, primary_key=True, autoincrement=True)
    sid = Column(Integer, ForeignKey('oa_survey_survey.sid'), nullable=False)
    user_id = Column(Integer)
    # ---- 答题用户身份字段(快照) ----
    # user_type 内置枚举:STUDENT/TEACHER/PARENT/STAFF/ANONYMOUS,允许自定义扩展
    user_type = Column(String(16), nullable=False, default='ANONYMOUS', comment='答题者类型')
    user_name = Column(String(64), comment='用户名/姓名字符串快照')
    user_no = Column(String(32), comment='学号/工号快照')
    wx_openid = Column(String(64))  # 支付等业务使用,勿删
    wx_openid_hash = Column(String(64))  # 微信openid的SHA256哈希(问卷匿名合规存储)
    device_id = Column(String(64))
    ip = Column(String(64))
    ua = Column(String(255))
    status = Column(String(16), nullable=False, default='NEW', comment='NEW/SUBMITTED/INVALID')
    duration_sec = Column(Integer, default=0)
    submit_time = Column(DateTime)
    score = Column(Numeric(10, 2))
    is_passed = Column(Boolean)
    payload = Column(Text, comment='提交 payload JSON')
    extra = Column(Text)

    __table_args__ = (
        Index('idx_answer_sid_status', 'sid', 'status'),
        Index('idx_answer_user', 'user_id'),
        Index('idx_answer_wx', 'wx_openid'),
        Index('idx_answer_wx_hash', 'wx_openid_hash'),
    )

    def __repr__(self):
        return f'<OaSurveyAnswer {self.aid} sid={self.sid}>'


class OaSurveyAnswerDetail(Base):
    """答卷明细"""
    __tablename__ = 'oa_survey_answer_detail'

    id = Column(Integer, primary_key=True, autoincrement=True)
    aid = Column(Integer, ForeignKey('oa_survey_answer.aid', ondelete='CASCADE'), nullable=False)
    qid = Column(String(32), nullable=False)
    qtype = Column(String(32), nullable=False)
    detail_value = Column(Text, comment='答案值(避开 SQL 保留字 value)')
    value_text = Column(Text)
    score = Column(Numeric(10, 2))
    is_correct = Column(Boolean)

    __table_args__ = (Index('idx_detail_aid_qid', 'aid', 'qid'),)


class OaSurveyShortLink(Base):
    """短链接(code → sid)"""
    __tablename__ = 'oa_survey_short_link'

    code = Column(String(12), primary_key=True)
    sid = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    expires_at = Column(DateTime)

    __table_args__ = (Index('idx_shortlink_sid', 'sid'),)


class OaSurveyVoteCounter(Base):
    """投票计数(高频更新)"""
    __tablename__ = 'oa_survey_vote_counter'

    sid = Column(Integer, primary_key=True)
    qid = Column(String(32), primary_key=True)
    option_id = Column(String(32), primary_key=True)
    count = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, nullable=False, default=datetime.now)
    version = Column(Integer, nullable=False, default=0)

    __table_args__ = (Index('idx_votecounter_sid', 'sid'),)


class OaSurveyVoteRecord(Base):
    """投票明细(用于风控/防重)"""
    __tablename__ = 'oa_survey_vote_record'

    id = Column(Integer, primary_key=True, autoincrement=True)
    sid = Column(Integer, nullable=False)
    qid = Column(String(32), nullable=False)
    option_id = Column(String(32), nullable=False)
    aid = Column(Integer)
    wx_openid_hash = Column(String(64))  # 投票者openid的SHA256哈希(匿名投票合规存储)
    user_id = Column(Integer)
    ip = Column(String(64))
    ua = Column(String(255))
    submitted_at = Column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = (
        Index('idx_vote_sid', 'sid'),
        Index('idx_vote_openid_hash', 'wx_openid_hash'),
    )


class OaSurveySignupAudit(Base):
    """报名审核状态机"""
    __tablename__ = 'oa_survey_signup_audit'

    aid = Column(Integer, primary_key=True)
    sid = Column(Integer, nullable=False)
    applicant_id = Column(Integer, nullable=False)
    status = Column(String(16), nullable=False, default='PENDING')
    reviewer_id = Column(Integer)
    audit_at = Column(DateTime)
    reason = Column(Text)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index('idx_signup_status', 'status'),
        Index('idx_signup_sid_status', 'sid', 'status'),
    )


class OaSurveySignin(Base):
    """报名签到"""
    __tablename__ = 'oa_survey_signup_signin'

    id = Column(Integer, primary_key=True, autoincrement=True)
    aid = Column(Integer, nullable=False)
    signed_at = Column(DateTime, nullable=False, default=datetime.now)
    signin_lat = Column(Numeric(10, 6))
    signin_lng = Column(Numeric(10, 6))
    device_id = Column(String(64))
    method = Column(String(16), nullable=False, default='online')

    __table_args__ = (
        Index('idx_signin_aid', 'aid'),
        Index('idx_signin_signed_at', 'signed_at'),
    )


class OaSurveyExamPaper(Base):
    """测评试卷快照"""
    __tablename__ = 'oa_survey_exam_paper'

    aid = Column(Integer, primary_key=True)
    sid = Column(Integer, nullable=False)
    question_ids = Column(Text)
    question_seed = Column(Integer)
    total_score = Column(Numeric(10, 2))
    rule_text = Column(Text)

    __table_args__ = (Index('idx_exampaper_sid', 'sid'),)


class OaSurveyExamResult(Base):
    """测评结果/报告"""
    __tablename__ = 'oa_survey_exam_result'

    aid = Column(Integer, primary_key=True)
    sid = Column(Integer, nullable=False, comment='冗余 sid,无 FK,统计按 sid 取')
    score = Column(Numeric(10, 2))
    is_passed = Column(Boolean)
    result_level = Column(String(8), comment='等级(level 是 SQL 关键字)')
    section_scores = Column(Text)
    advice = Column(Text)
    rank_pct = Column(Numeric(5, 2))

    __table_args__ = (Index('idx_examresult_sid', 'sid'),)


class OaSurveyStatCache(Base):
    """统计缓存(用于大屏加速)"""
    __tablename__ = 'oa_survey_stat_cache'

    id = Column(Integer, primary_key=True, autoincrement=True)
    sid = Column(Integer, nullable=False)
    type = Column(String(32), nullable=False)
    qid = Column(String(32))
    payload = Column(Text)
    valid_until = Column(DateTime)

    __table_args__ = (Index('idx_statcache_sid_type', 'sid', 'type'),)


class OaSurveyBlacklist(Base):
    """风控黑名单"""
    __tablename__ = 'oa_survey_blacklist'

    id = Column(Integer, primary_key=True, autoincrement=True)
    scope = Column(String(16), nullable=False, comment='ip/wx_openid/device_id/user_id')
    blacklist_value = Column(String(64), nullable=False, comment='具体值(value 是 SQL 关键字)')
    blacklist_value_hash = Column(String(64), comment='blacklist_value为openid时的SHA256哈希')
    reason = Column(String(255))
    created_at = Column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = (Index('idx_blacklist_scope_value', 'scope', 'blacklist_value'),)


class OaSurveyOperationLog(Base):
    """管理端操作日志"""
    __tablename__ = 'oa_survey_operation_log'

    id = Column(Integer, primary_key=True, autoincrement=True)
    action = Column(String(20), nullable=False)
    actor_id = Column(Integer)
    actor_name = Column(String(50))
    sid = Column(Integer)
    aid = Column(Integer)
    occurred_at = Column(DateTime, nullable=False, default=datetime.now)
    diff = Column(Text)

    __table_args__ = (
        Index('idx_oplog_sid', 'sid'),
        Index('idx_oplog_actor', 'actor_id'),
        Index('idx_oplog_occurred', 'occurred_at'),
    )
