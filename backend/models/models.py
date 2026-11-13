from init.database_optimized import Base
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Boolean, Float, Numeric, BigInteger, PrimaryKeyConstraint, UniqueConstraint, Index, DECIMAL, text
from sqlalchemy.orm import relationship, backref

class Teacher(Base):
    __tablename__ = 'oa_t'  # 设置表名
    
    t_id = Column(Integer, primary_key=True) #教师ID，主键，自增
    t_yhm = Column(String(20)) #用户名
    t_mm = Column(String(32)) #密码
    t_xm = Column(String(20)) #教师姓名
    t_sfzh = Column(String(20)) #身份证号
    t_zc = Column(String(20)) #职称
    t_bm_id = Column(Integer) #部门ID
    t_xb = Column(String(1)) #性别
    t_js_id = Column(String(50)) #角色ID
    t_dlip = Column(String(20)) #登录IP
    t_dlsj = Column(DateTime) #登录时间
    t_dlcs = Column(Integer, default=0) #登录次数
    t_jyz_id = Column(Integer, default=0) #教研组ID
    t_jyz_zz = Column(Integer, default=0) #教研组组长
    t_jyz_wk = Column(Integer) #教研组文科
    t_jyz_jg = Column(Integer) #教研组经管
    t_jyz_lg = Column(Integer) #教研组理工
    t_jyz_sz = Column(Integer) #教研组数字
    t_dh = Column(String(20)) #电话
    t_dh_yzm = Column(String(10)) #电话验证码
    t_dh_time = Column(DateTime) #电话验证时间
    t_yx = Column(String(50)) #邮箱
    t_ssd = Column(String(2)) #所属地
    t_isblock = Column(Integer) #是否锁定
    t_block_time = Column(DateTime) #锁定时间
    t_bmorderid = Column(Integer) #部门排序ID
    t_issms = Column(Integer) #是否发送短信
    t_lwgh = Column(String(10)) #论文工号
    t_gzkg = Column(Integer) #工作开关
    t_gzzgly = Column(Integer) #工作主管理员
    t_lwwp = Column(Integer) #论文外聘
    t_py_kc_id = Column(Text) #评阅课程ID
    t_book_pickup_addr = Column(String(200), comment='班主任设置的新书自取地点；学生选到校领取时实时展示')
    headphoto = Column(Integer, default=0, comment='是否有照片 0-无 1-有')
    t_wx_openid = Column(String(200), comment='微信openid(教师端一键登录绑定,勿删)')
    t_wx_openid_hash = Column(String(64), comment='微信openid的SHA256哈希(隐私合规存储)')
    
    def __repr__(self):
        return f"Teacher(id={self.t_id}, name={self.t_xm})"

class Role(Base):
    __tablename__ = 'oa_js'  # 设置表名, 表名默认为类名小写
    js_id = Column(Integer, primary_key=True)  # 设置主键, 默认自增
    js_mc = Column(String(20))
    js_cd_id = Column(String(200))  # 修改为具体的长度
    
    def __repr__(self):
        return "(%s)"%(self.js_id)
    
class Menu(Base):
    __tablename__ = 'oa_cd'  # 设置表名, 表名默认为类名小写
    cd_id = Column(Integer, primary_key=True)  # 设置主键, 默认自增
    cd_mc = Column(String(20))
    cd_ym_new = Column(String(50))
    cd_fid = Column(Integer)
    cd_pxid = Column(Integer)
    
    def __repr__(self):
        return "(%s)"%(self.cd_id)



# xjzt_map = {
#     "1": "在籍", "2": "未注册", "3": "转出", "4": "休学",
#     "5": "退学", "6": "开除", "7": "毕业", "8": "异动中", "9": "超期清退"
# }
class Student(Base):
    __tablename__ = 'oa_xs'    
    xs_id = Column(Integer, primary_key=True) #学生ID，主键，自增
    xs_xm = Column(String(20)) #学生姓名
    xs_xb = Column(String(50)) #学生性别
    xs_mz = Column(String(50)) #民族
    xs_sfzh = Column(String(20)) #身份证号
    xs_mm = Column(String(50)) #密码
    xs_xh = Column(String(20)) #学号
    xs_lb = Column(Integer) #类别
    xs_bj_id = Column(Integer) #班级ID
    xs_nd = Column(Integer) #年度
    xs_xqdm = Column(String(50)) #学期代码
    xs_xjzt = Column(String(2)) #学籍状态
    xs_dh = Column(String(15)) #电话号码
    xs_dh_yzm = Column(String(50)) #电话验证码
    xs_dh_time = Column(DateTime) #电话验证时间
    xs_wx_refresh_token = Column(Text) #微信刷新token
    xs_wx_openid = Column(String(50)) #微信openid(支付等业务使用,勿删)
    xs_wx_openid_hash = Column(String(64)) #微信openid的SHA256哈希(隐私合规存储)
    xs_wx_nickname = Column(String(50)) #微信昵称
    xs_wx_headimgurl = Column(Text) #微信头像URL
    xs_wx_addtime = Column(DateTime) #微信绑定时间
    xs_dzzch = Column(String(50)) #电子注册号
    xs_bysjn = Column(String(50)) #毕业设计年
    xs_bysjy = Column(String(50)) #毕业设计月
    xs_zcdd = Column(String(50)) #注册地点
    headphoto = Column(Integer, default=0, comment='是否有照片 0-无 1-有')
    xs_info_verify_status = Column(String(20), default='pending', comment='新生信息核对状态：pending-待核对 verified-已确认无误 modified-已修改提交')
    xs_info_verify_record = Column(Text, comment='新生信息核对记录JSON，含原始值、修改值、历次提交历史')

    def __repr__(self):
        return f"Student(id={self.xs_id}, name={self.xs_xm}, student_no={self.xs_xh})"


class OaXsXxhd(Base):
    """新生信息核对表
    
    用于存储新生信息核对结果，学生通过小程序核对个人信息。
    - status = 0: 字段有错误，学生提交了修正数据
    - status = 1: 学生原始数据无误，对应的数据可以为空
    - 有记录: 学生已经核对过信息
    - 无记录: 学生没有核对过信息
    - 已核对过: 不能再次修改
    """
    __tablename__ = 'oa_xs_xxhd'
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='自增主键ID')
    xs_xh = Column(String(20), comment='学号')
    xs_xm = Column(String(20), comment='姓名')
    xs_xb = Column(String(1), comment='性别')
    xs_mz = Column(String(20), comment='民族')
    xs_sfzh = Column(String(20), comment='身份证号')
    xs_bj_id = Column(Integer, comment='班级ID')
    xs_bzr_id = Column(Integer, comment='班主任ID')
    addtime = Column(DateTime, comment='添加时间')
    xs_xm_status = Column(Integer, comment='姓名核对状态：0-有误已修正 1-无误')
    xs_xb_status = Column(Integer, comment='性别核对状态：0-有误已修正 1-无误')
    xs_sfzh_status = Column(Integer, comment='身份证号核对状态：0-有误已修正 1-无误')
    xs_mz_status = Column(Integer, comment='民族核对状态：0-有误已修正 1-无误')
    xs_cns_status = Column(Integer, comment='同意学习承诺书状态：0-未同意 1-已同意')

    def __repr__(self):
        return f"<OaXsXxhd id={self.id}, xs_xh={self.xs_xh}, xs_xm={self.xs_xm}>"


class bk_sxbkb(Base):
    """学生选课表模型"""
    __tablename__ = 'bk_sxbkb'
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='自增主键ID')
    F1 = Column(String(255), comment='姓名')  
    F2 = Column(String(255), comment='序号')  
    F3 = Column(String(255), comment='学号')  
    F4 = Column(String(255), comment='班级代码')  
    F5 = Column(String(255), comment='班级名称')  
    F6 = Column(String(255), comment='专业规则号')  
    F7 = Column(String(255), comment='专业名称')  
    F8 = Column(String(255), comment='报考课程名称')  
    F9 = Column(String(255), comment='报考课程ID')  
    F10 = Column(String(255), comment='考核方式')  
    F11 = Column(String(255), comment='是否已确认')  
    F12 = Column(String(255), comment='报考试卷号')  
    F13 = Column(String(255), comment='直属')

    def __repr__(self):
        return f'<bk_sxbkb {self.id}>'

class tzd_cj(Base):
    __tablename__ = 'tzd_cj'  # 设置表名, 表名默认为类名小写
    id = Column(Integer, primary_key=True, comment='主键ID')  # 设置主键, 默认自增
    F1 = Column(String(255), comment='考试课程名称')
    F2 = Column(String(255), comment='考试课程编号')
    F3 = Column(String(255), comment='试卷号')
    F4 = Column(String(255), ForeignKey('bk_sxbkb.F3'), comment='学号')
    F5 = Column(String(255), comment='姓名')
    F6 = Column(String(255), comment='班级代码')
    F7 = Column(String(255), comment='班级名称')
    F8 = Column(String(255), comment='学习中心')
    xxzxdm = Column(String(255), comment='学习中心代码')
    F9 = Column(String(255), comment='形考比例(%)')
    F10 = Column(String(255), comment='形考成绩')
    xkcjly = Column(String(255), comment='形考成绩来源')
    zkcjly = Column(String(255), comment='终考成绩来源')
    F11 = Column(String(255), comment='终考成绩')
    F12 = Column(String(255), comment='综合成绩')
    F13 = Column(String(255), comment='成绩完整性')
    F14 = Column(String(255), comment='合成状态')
    F15 = Column(String(255), comment='是否双及格（终考 + 综合）')
    F16 = Column(String(255), comment='总部标记状态')
    F17 = Column(String(255), comment='总部标记结果')
    F18 = Column(String(255), comment='成绩状态')
    
    def __repr__(self):
        return "(%s)"%(self.id)
    
class wxxs_xf_info(Base):
    __tablename__ = 'wxxs_xf_info'  # 设置表名, 表名默认为类名小写
    id = Column(Integer, primary_key=True)  # 设置主键, 默认自增
    F6 = Column(String(50)) #学号
    F10 = Column(String(50)) #学费1
    F11 = Column(String(50)) #书费1
    F12 = Column(String(50)) #学费2
    F13 = Column(String(50)) #书费2
    F14 = Column(String(50)) #学费3
    F15 = Column(String(50)) #书费3
    F16 = Column(String(50)) #学费4
    F17 = Column(String(50)) #书费4
    F18 = Column(String(50)) #学费5
    F19 = Column(String(50)) #书费5
    F22 = Column(String(50)) #减免费用
    
    def __repr__(self):
        return "(%s)"%(self.id)

class wxxs_xf_payinfo(Base):
    __tablename__ = 'wxxs_xf_payinfo'
    
    o_id = Column(Integer, primary_key=True)
    o_xm = Column(String(20))  # 姓名，限制20字符
    o_xh = Column(String(20))  # 学号，限制20字符
    o_sfzh = Column(String(18))  # 身份证号，限制18字符
    o_sj = Column(String(15))  # 手机号，限制15字符
    o_zyid = Column(Integer)  # 专业ID
    o_body = Column(String(50))  # 订单描述，限制50字符
    o_money = Column(Integer)  # 总金额（分）
    o_xf = Column(Integer)  # 学费（分）
    o_sf = Column(Integer)  # 书费（分）
    o_jm = Column(Integer)  # 减免金额（分）
    o_paytype = Column(String(10))  # 支付方式，限制10字符
    o_type = Column(Integer)  # 订单类型
    o_status = Column(Integer)  # 支付状态
    o_tk_status = Column(Integer)  # 退款状态
    o_close = Column(Integer)  # 关闭状态
    o_xx_status = Column(Integer)  # 下发状态
    o_xxtk_status = Column(Integer)  # 下发退款状态
    o_order_no = Column(String(30))  # 订单号，限制30字符
    o_trade_no = Column(String(50))  # 交易号，限制50字符
    o_addtime = Column(DateTime)  # 创建时间
    o_paytime = Column(String(50))  # 支付时间
    o_pc = Column(Integer)  # 批次
    o_isxs = Column(Integer)  # 是否新生
    o_ip = Column(String(15))  # IP地址，限制15字符
    o_delete = Column(Integer)  # 是否删除
    prepay_id = Column(String(255))  # 支付参数，限制255字符
    
    # 查询码
    query_code = Column(String(20), unique=True, comment='8位查询码')
    query_code_expire = Column(DateTime, comment='查询码过期时间')

    def __repr__(self):
        return f"<Order {self.o_order_no}>"

class Major(Base):
    __tablename__ = 'oa_zy' # 设置表名
    id = Column(Integer, primary_key=True) # 主键，自增
    mc = Column(String(50)) # 专业名称
    cc = Column(String(4))  # 层次
    typeid = Column(Integer) # 类型ID
    orderid = Column(Integer) # 排序ID
    isblock = Column(Integer) # 是否锁定
    xf_1 = Column(Integer)  # 学费1
    sf_1 = Column(Integer)  # 书费1

    def __repr__(self):
        return f"Major(id={self.id}, name={self.mc})"

class MajorType(Base):
    __tablename__ = 'oa_zy_type' # 设置表名
    id = Column(Integer, primary_key=True) # 主键，自增
    mc = Column(String(50)) # 类型名称
    orderid = Column(Integer) # 排序ID
    isblock = Column(Integer) # 是否锁定(0:展示, 1:隐藏)

    def __repr__(self):
        return f"MajorType(id={self.id}, name={self.mc})"

class Class(Base):
    __tablename__ = 'oa_bj'  # 设置表名
        
    bj_id = Column(Integer, primary_key=True)  # 设置主键
    bj_mc = Column(String(50)) #班级名称
    bj_bzr_id = Column(Integer) #班主任ID
    bj_planid = Column(String(20)) #教学计划ID
    bj_zcdd = Column(String(50)) #班级注册地点
    bj_zszcdd = Column(String(50)) #班级真实注册地点
    bj_bjid = Column(String(20)) #班级一平台班代码
    bj_nd = Column(Integer) #班级年度
    bj_xqdm = Column(String(20)) #班级学期代码
    bj_zyid = Column(Integer)  #班级专业ID
    bj_zy = Column(String(50))  #班级专业
    bj_cc = Column(String(20))  #班级层次
    bj_jyz = Column(Integer)  #班级教研组
    bj_zsjyz = Column(Integer)  #班级直属评阅教研组
    bj_isblock = Column(Integer)  #班级是否锁定
    bj_isfp = Column(Integer)  #班级是否分配
    bj_sdlw = Column(String(50))  #班级手动录入文字
    bj_iscg = Column(Integer)  #班级是否是成高班级
    bj_dq1_id = Column(Integer)  #班级地区ID
    bj_dq2_id = Column(Integer)  #班级地区ID
    bj_dq1_mc = Column(String(50))  #班级地区名称
    bj_dq2_mc = Column(String(50))  #班级地区名称
    bj_dq1_dm = Column(String(50))  #班级地区代码
    bj_dq2_dm = Column(String(50))  #班级地区代码

    def __repr__(self):
        return f"Class(id={self.bj_id}, name={self.bj_mc})"

class wxxs_xf_zd(Base):
    __tablename__ = 'wxxs_xf_zd'  # 设置表名, 表名默认为类名小写
    id = Column(Integer, primary_key=True)  # 设置主键, 默认自增
    bjid = Column(Integer)
    xf_1 = Column(Integer) #以分为单位
    sf_1 = Column(Integer)
    xf_2 = Column(Integer)
    sf_2 = Column(Integer)
    iszs = Column(Integer) #是否最终
    
    def __repr__(self):
        return "(%s)"%(self.id)
    
class wxxs_xf_zdgr(Base):
    __tablename__ = 'wxxs_xf_zdgr'  # 设置表名, 表名默认为类名小写
    id = Column(Integer, primary_key=True)  # 设置主键, 默认自增
    xsxh = Column(String(20))
    xf_1 = Column(Integer) #以分为单位
    sf_1 = Column(Integer)
    xf_2 = Column(Integer)
    sf_2 = Column(Integer)
    jm = Column(Integer)
    iszs = Column(Integer) #是否最终
    
    def __repr__(self):
        return "(%s)"%(self.id) 

class PaperGroup(Base):
    __tablename__ = 'lw_fz'
    
    fz_id = Column(Integer, primary_key=True) #分组ID，主键，自增
    fz_t_id = Column(Integer) #教师ID，指导教师
    fz_bj_id = Column(Integer) #班级ID
    fz_xs_id = Column(Integer) #学生ID
    fz_pc = Column(Integer) #批次

    def __repr__(self):
        return f"PaperGroup(id={self.fz_id}, teacher_id={self.fz_t_id}, student_id={self.fz_xs_id})"

    # 添加关联关系
    teacher = relationship('Teacher', 
                            foreign_keys=[fz_t_id],
                            primaryjoin='PaperGroup.fz_t_id == Teacher.t_id',
                            backref=backref('paper_groups', lazy='dynamic'))
    
    student = relationship('Student',
                            foreign_keys=[fz_xs_id],
                            primaryjoin='PaperGroup.fz_xs_id == Student.xs_id',
                            backref=backref('paper_group', uselist=False))
    
    class_ = relationship('Class',
                           foreign_keys=[fz_bj_id],
                           primaryjoin='PaperGroup.fz_bj_id == Class.bj_id',
                           backref=backref('paper_groups', lazy='dynamic'))

# 添加 TeacherUTF8 模型


class PaperRequirement(Base):
    __tablename__ = 'lw_lwyq'
    
    lwyq_id = Column(Integer, primary_key=True) #要求ID，主键，自增
    lwyq_bt = Column(String(50)) #标题
    lwyq_nr = Column(Text) #内容
    lwyq_orderid = Column(Integer) #排序ID
    lwyq_sj = Column(DateTime) #发布时间
    lwyq_t_id = Column(Integer) #教师ID
    lwyq_bj_id = Column(Integer) #班级ID

    def __repr__(self):
        return f"PaperRequirement(id={self.lwyq_id}, title={self.lwyq_bt})"

    # 添加关联关系
    teacher = relationship('Teacher',
                            foreign_keys=[lwyq_t_id],
                            primaryjoin='PaperRequirement.lwyq_t_id == Teacher.t_id',
                            backref=backref('paper_requirements', lazy='dynamic'))
    
    class_ = relationship('Class',
                           foreign_keys=[lwyq_bj_id],
                           primaryjoin='PaperRequirement.lwyq_bj_id == Class.bj_id',
                           backref=backref('paper_requirements', lazy='dynamic'))

class Paper(Base):
    __tablename__ = 'lw_lw'
    
    
    lw_id = Column(Integer, primary_key=True) #论文ID，主键，自增
    lw_bt = Column(String(200)) #论文标题
    lw_nr = Column(Text) #论文内容
    lw_wc = Column(Integer) #完成状态
    lw_tg = Column(Integer, default=0) #是否通过
    lw_pf = Column(Integer) #评分
    lw_py = Column(Text) #评语
    lw_tjsj = Column(DateTime) #提交时间
    lw_pysj = Column(DateTime) #评阅时间
    lw_xs_id = Column(Integer, ForeignKey('oa_xs.xs_id')) #学生ID
    lw_t_id = Column(Integer, ForeignKey('oa_t.t_id')) #教师ID

    # 添加关联关系 - 优化查询性能，避免N+1问题
    student = relationship('Student', backref=backref('papers', lazy='select'), lazy='select')
    teacher = relationship('Teacher', backref=backref('papers', lazy='select'), lazy='select')

    def __repr__(self):
        return f"Paper(id={self.lw_id}, title={self.lw_bt})"

class SocialPractice(Base):
    """社会实践表"""
    __tablename__ = 'kw_shsjb'
    
    id = Column(Integer, primary_key=True)  # 主键，自增
    xs_xh = Column(String(20))  # 学生学号
    xs_xm = Column(String(20))  # 学生姓名
    xs_bj_id = Column(Integer)  # 学生班级ID
    szdd = Column(String(10))  # 所在电大
    rxnj = Column(String(10))  # 入学年级
    sjdw = Column(String(20))  # 实践单位
    sjnr = Column(String(20))  # 实践内容
    hdsj_q_n = Column(Integer)  # 活动起始时间-年
    hdsj_q_y = Column(Integer)  # 活动起始时间-月
    hdsj_z_n = Column(Integer)  # 活动结束时间-年
    hdsj_z_y = Column(Integer)  # 活动结束时间-月
    sxnr = Column(Text)  # 实习内容
    shhth = Column(Text)  # 收获和体会
    wthjy = Column(Text)  # 问题和建议
    jspf = Column(Integer)  # 教师评分
    t_id = Column(Integer)  # 教师ID
    t_xm = Column(String(20))  # 教师姓名
    tjsj = Column(DateTime)  # 提交时间
    zt = Column(Integer)  # 状态

    # 添加关联关系
    student = relationship('Student',
                            foreign_keys=[xs_xh],
                            primaryjoin='SocialPractice.xs_xh == Student.xs_xh',
                            backref=backref('social_practice', uselist=False))
    
    teacher = relationship('Teacher',
                            foreign_keys=[t_id],
                            primaryjoin='SocialPractice.t_id == Teacher.t_id',
                            backref=backref('social_practices', lazy='dynamic'))
    
    class_ = relationship('Class',
                           foreign_keys=[xs_bj_id],
                           primaryjoin='SocialPractice.xs_bj_id == Class.bj_id',
                           backref=backref('social_practices', lazy='dynamic'))

    def __repr__(self):
        return f"SocialPractice(id={self.id}, student_no={self.xs_xh}, student_name={self.xs_xm})"

class lw_sys(Base):
    __tablename__ = 'lw_sys'  # 设置表名, 表名默认为类名小写
    id = Column(Integer, primary_key=True)  # 设置主键, 默认自增
    sys_jzrq = Column(DateTime) #报考关闭时间
    sys_xt_jzrq = Column(DateTime) #选题截至时间
    sys_xt_pyjzrq = Column(DateTime) #评阅选题截至时间
    sys_jd1_jzrq = Column(DateTime) 
    sys_jd1_pyjzrq = Column(DateTime) 
    sys_jd2_jzrq = Column(DateTime) 
    sys_jd2_pyjzrq = Column(DateTime) 
    sys_jd3_jzrq = Column(DateTime) 
    sys_jd3_pyjzrq = Column(DateTime) 
    sys_pc = Column(Integer) #当前批次
    sys_xq1_nd = Column(String(4))
    sys_xq1_xq = Column(String(2))
    sys_xq2_nd = Column(String(4))
    sys_xq2_xq = Column(String(2))
    sys_xq3_nd = Column(String(4))
    sys_xq3_xq = Column(String(2))
    sys_xq4_nd = Column(String(4))
    sys_xq4_xq = Column(String(2))
    sys_xq5_nd = Column(String(4))
    sys_xq5_xq = Column(String(2))
    sys_xq6_nd = Column(String(4))
    sys_xq6_xq = Column(String(2))
    sys_iscj = Column(Integer)
    sys_cjfhpc = Column(Integer)
    sys_cjfhjzrq = Column(DateTime)
    sys_isbk = Column(Integer)
    sys_istzd = Column(Integer)
    sys_iskgtzd = Column(Integer)
    sys_iskswj = Column(Integer) 
    sys_ls_jf = Column(DateTime) #老生交费截至时间
    sys_xs_jf = Column(DateTime) #新生交费截至时间
    sys_xsbm_pc = Column(Integer) #新生报名批次
    sys_wplw = Column(Integer) #是否更新应届数据、设定班级论文课程ID 0为未更新 1为已更新
    sys_zc_kssj = Column(DateTime) #自测开启时间
    sys_zc_jzsj = Column(DateTime) #自测关闭时间
    sys_zc_cs = Column(Integer) #自测最高次数
    sys_lwpc = Column(Integer)
    sys_xwyy_start = Column(DateTime) #学位英语报考开始时间
    sys_xwyy_end = Column(DateTime) #学位英语报考结束时间
    sys_wxxs_xf_tk_payinfo_switch = Column(Integer) #学生微信退书费功能开关
    dq1_id = Column(Integer) #地区1ID
    dq1_mc = Column(String(20)) #地区1名称
    sys_zcks_switch = Column(Integer) #自测考试开关

    def __repr__(self):
        return f"lw_sys({', '.join(f'{k}={v}' for k, v in self.__dict__.items() if not k.startswith('_'))})"

class GraduateRegistration(Base):
    """毕业生登记表"""
    __tablename__ = 'by_bysdjb'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    bjid = Column(Integer)  # 班级ID
    xm = Column(String(50))  # 姓名
    xh = Column(String(50))  # 学号
    csrq = Column(String(50))  # 出生日期
    xb = Column(String(50))  # 性别
    mz = Column(String(50))  # 民族
    zjlx = Column(String(50))  # 证件类型
    zjh = Column(String(50))  # 证件号
    zzmm = Column(String(50))  # 政治面貌
    xslb = Column(String(50))  # 学生类别
    xlcc = Column(String(50))  # 学历层次
    xxzy = Column(String(50))  # 学习专业
    rxsjn = Column(String(50))  # 入学时间-年
    rxsjj = Column(String(50))  # 入学时间-季
    bysjn = Column(String(50))  # 毕业时间-年
    bysjy = Column(String(50))  # 毕业时间-月
    dzzch = Column(String(50))  # 电子注册号
    
    # 联系方式
    gzdw = Column(String(50))  # 工作单位
    dwdh = Column(String(50))  # 单位电话
    sj = Column(String(50))  # 手机
    jtdh = Column(String(50))  # 家庭电话
    yx = Column(String(50))  # 邮箱
    
    # 学习经历
    qsj1 = Column(String(50))  # 起始时间1
    zsj1 = Column(String(50))  # 终止时间1
    xx1 = Column(String(50))  # 学校1
    qsj2 = Column(String(50))  # 起始时间2
    zsj2 = Column(String(50))  # 终止时间2
    xx2 = Column(String(50))  # 学校2
    qsj3 = Column(String(50))  # 起始时间3
    zsj3 = Column(String(50))  # 终止时间3
    xx3 = Column(String(50))  # 学校3
    qsj4 = Column(String(50))  # 起始时间4
    zsj4 = Column(String(50))  # 终止时间4
    xx4 = Column(String(50))  # 学校4
    qsj5 = Column(String(50))  # 起始时间5
    zsj5 = Column(String(50))  # 终止时间5
    xx5 = Column(String(50))  # 学校5
    
    # 其他信息
    bysxdw = Column(String(50))  # 毕业实习单位
    bylwtm = Column(String(50))  # 毕业论文题目
    jlhcf = Column(String(50))  # 奖励和处分
    zwjd = Column(Text)  # 自我鉴定
    qm = Column(Text)  # 签名
    tjsj = Column(DateTime)  # 提交时间
    zt = Column(Integer)  # 状态

class bk_sxbkb_z(Base):
    """学生历史成绩表模型"""
    __tablename__ = 'bk_sxbkb_z'
    
    # 主键设置
    id = Column(Integer, primary_key=True, 
                  autoincrement=True, 
                  nullable=False,
                  comment='自增主键ID')
    
    # 字段定义
    F1 = Column(String(255), nullable=True, comment='学生相关信息')
    F2 = Column(String(255), nullable=True, comment='学生相关信息')
    F3 = Column(String(255), nullable=True, comment='学号')
    F4 = Column(String(255), nullable=True, comment='课程相关信息')
    F5 = Column(String(255), nullable=True, comment='课程相关信息')
    F6 = Column(String(255), nullable=True, comment='课程相关信息')
    F7 = Column(String(255), nullable=True, comment='课程相关信息')
    F8 = Column(String(255), nullable=True, comment='课程名称')
    F9 = Column(String(255), nullable=True, comment='课程ID')
    F10 = Column(String(255), nullable=True, comment='考试相关信息')
    F11 = Column(String(255), nullable=True, comment='考试相关信息')
    F12 = Column(String(255), nullable=True, comment='学期')
    F13 = Column(String(255), nullable=True, comment='成绩')
    F14 = Column(String(255), nullable=True, comment='考试类型')

    __table_args__ = (
        # 添加主键约束
        PrimaryKeyConstraint('id', name='PK_bk_sxbkb_z'),
    )

    def __repr__(self):
        return f'<bk_sxbkb_z {self.id}>'

class tzd_cjfh(Base):
    """成绩复核表模型"""
    __tablename__ = 'tzd_cjfh'
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='自增主键ID')
    xs_xh = Column(String(20), comment='学号')
    xs_xm = Column(String(20), comment='姓名')
    xs_bj_id = Column(Integer, comment='班级ID')
    sjh = Column(String(10), comment='试卷号')
    kcid = Column(String(50), comment='课程ID')
    kcmc = Column(String(100), comment='课程名称')
    tjsj = Column(DateTime, comment='提交时间')
    pc = Column(Integer, comment='批次')
    zt = Column(Integer, comment='状态')

    def __repr__(self):
        return f"<tzd_cjfh {self.id}>"

class bk_bkb(Base):
    """报考表"""
    __tablename__ = 'bk_bkb'
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    sjh = Column(String(10), comment='试卷号')
    kcid = Column(String(10), comment='课程ID')
    kcmc = Column(String(80), comment='课程名称')
    ksdw = Column(String(10), comment='考试单位')
    xsxh = Column(String(20), comment='学生学号')
    xsid = Column(Integer, comment='学生ID')
    bjid = Column(Integer, comment='班级ID')
    bjcc = Column(String(10), comment='班级层次')
    czr = Column(Integer, comment='操作人')
    date = Column(DateTime, comment='操作时间')
    isbk = Column(Integer, comment='是否报考(1:是,0:否)')
    pc = Column(Integer, comment='批次')
    xsczr = Column(Integer, comment='学生操作人')
    isdgzk = Column(Integer, comment='是否对公转款')
    ispay = Column(Integer, comment='是否支付(1:已支付,0:未支付)')
    pay_id = Column(Integer, comment='支付ID')

class wxxs_payinfo(Base):
    """微信支付信息表"""
    __tablename__ = 'wxxs_payinfo'
    
    o_id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    o_xh = Column(String(20), comment='学号')
    o_sfzh = Column(String(18), comment='身份证号')
    o_body = Column(String(50), comment='订单描述')
    o_money = Column(Integer, comment='支付金额')
    o_paytype = Column(String(18), comment='支付类型')
    o_type = Column(Integer, comment='订单类型')
    o_status = Column(Integer, comment='支付状态')
    o_tk_status = Column(Integer, comment='退款状态')
    o_close = Column(Integer, comment='订单关闭状态')
    o_order_no = Column(String(50), comment='商户订单号')
    o_trade_no = Column(String(50), comment='微信支付订单号')
    o_addtime = Column(DateTime, comment='创建时间')
    o_paytime = Column(DateTime)  # 支付时间
    o_pc = Column(Integer)  # 批次
    o_bkid = Column(Text, comment='报考ID列表')
    o_bkkcid = Column(Text, comment='报考课程ID列表')
    o_bkkcmc = Column(Text, comment='报考课程名称列表')
    o_delete = Column(Integer, comment='是否删除(0:未删除,1:已删除)')


class jw_chongxiu(Base):
    """重修课程信息表"""
    __tablename__ = 'jw_chongxiu'
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    xh = Column(String(20), comment='学号')
    xm = Column(String(10), comment='姓名')
    cc = Column(String(10), comment='层次')
    kcid = Column(String(10), comment='课程ID')
    kcmc = Column(String(50), comment='课程名称')
    ksdw = Column(String(10), comment='考试单位')
    pc = Column(Integer, comment='批次')

class kw_xwyy(Base):
    """学位英语信息表"""
    __tablename__ = 'kw_xwyy'
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    F1 = Column(String(100), comment='字段1')
    F2 = Column(String(100), comment='字段2')
    F3 = Column(String(100), comment='字段3')
    F4 = Column(String(100), comment='字段4')
    F5 = Column(String(100), comment='字段5')
    F6 = Column(String(100), comment='字段6')
    F7 = Column(String(100), comment='字段7')
    F8 = Column(String(100), comment='字段8')
    F9 = Column(String(100), comment='字段9')
    F10 = Column(String(100), comment='字段10')
    F11 = Column(String(100), comment='字段11')
    F12 = Column(String(100), comment='字段12')
    F13 = Column(String(100), comment='字段13')
    F14 = Column(String(100), comment='字段14')


class ZzXs(Base):
    """中职学生表"""
    __tablename__ = 'zz_xs'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    xm = Column(String(16), comment='姓名')
    xh = Column(String(11), comment='学号')
    xtxh = Column(String(30), comment='系统学号')
    nd = Column(Integer, comment='年度')
    bj_id = Column(Integer, comment='班级ID')
    zy_id = Column(Integer, comment='专业ID')
    xjzt = Column(Integer, comment='学籍状态')
    mm = Column(String(50), comment='密码')
    xb = Column(String(2), comment='性别')
    mz = Column(String(18), comment='民族')
    zzmm = Column(Integer, comment='政治面貌')
    sfzh = Column(String(18), comment='身份证号')
    xsdh = Column(String(15), comment='学生电话')
    jtxxdz = Column(String(100), comment='家庭详细地址')
    jzdlx = Column(Integer, comment='居住地类型')
    hkxz = Column(String(40), comment='户口性质')
    jzxm = Column(String(16), comment='监护人姓名')
    jzgx = Column(Integer, comment='监护人关系')
    jzdh = Column(String(15), comment='监护人电话')
    byxxssx1 = Column(String(50), comment='毕业学校所属县1')
    byxxssx2 = Column(String(50), comment='毕业学校所属县2')
    byxxssx3 = Column(String(50), comment='毕业学校所属县3')
    byxxmc = Column(String(100), comment='毕业学校名称')
    zsdx = Column(Integer, comment='招生对象')
    sfjdlk = Column(Integer, comment='是否建档立卡')
    sflset = Column(Integer, comment='是否留守儿童')
    sftwjrzn = Column(Integer, comment='是否退伍军人子女')
    xsly = Column(String(20), comment='学生来源')
    xs_wx_nickname = Column(String(50), comment='微信昵称')
    xs_wx_headimgurl = Column(String(200), comment='微信头像')
    xs_wx_openid = Column(String(200), comment='微信openid(支付等业务使用,勿删)')
    xs_wx_openid_hash = Column(String(64), comment='微信openid的SHA256哈希(隐私合规存储)')
    headphoto = Column(Integer, default=0, comment='是否有照片 0-无 1-有')
    issync = Column(Integer, default=0, comment='是否已同步到海康 0-未同步 1-已同步')
    cw_id = Column(Integer, comment='床位ID')

    # 报名相关字段
    cooperation_schoolmajor_id = Column(Integer, comment='合作学校专业ID（对应 bdzy）')
    qd = Column(String(50), comment='渠道')
    qdjs = Column(String(50), comment='渠道介绍')
    query_code = Column(String(20), comment='8位查询码')
    query_code_expire = Column(DateTime, comment='查询码过期时间')
    pinyin_initial = Column(String(100), comment='姓名拼音首字母')
    remark = Column(String(500), comment='备注')
    is_complete = Column(Integer, default=0, comment='报名完成标志：0-草稿 1-已完成')
    sfqdxf = Column(Integer, comment='是否购买校服：1-是 0-否')
    xs_info_verify_status = Column(String(20), default='pending', comment='新生信息核对状态：pending-待核对 verified-已确认无误 modified-已修改提交')
    xs_info_verify_record = Column(Text, comment='新生信息核对记录JSON，含原始值、修改值、历次提交历史')

    def __repr__(self):
        return f'<ZzXs {self.xm}-{self.xh}>'

class ZzBj(Base):
    """中职班级表"""
    __tablename__ = 'zz_bj'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    mc = Column(String(50), comment='班级名称')
    bzr_id = Column(Integer, comment='班主任ID')
    nd = Column(Integer, comment='年度')
    zy = Column(Integer, comment='专业')
    plan_id = Column(Integer, comment='教学计划ID')
    lhbx = Column(Integer, comment='联合办学')
    lhbxxxmc = Column(String(50), comment='联合办学学校名称')
    isblock = Column(Integer, comment='是否禁用')
    jss = Column(String(50), comment='教室')

    def __repr__(self):
        return f'<ZzBj {self.mc}>'


class ZzXsXjzt(Base):
    """中职学生学籍状态字典表"""
    __tablename__ = 'zz_xs_xjzt'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    mc = Column(String(50), comment='状态名称')
    zt = Column(Integer, comment='状态')

    def __repr__(self):
        return f'<ZzXsXjzt {self.mc}>'

class WxPayinfo(Base):
    """中职微信支付信息表"""
    __tablename__ = 'wx_payinfo'

    o_id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    o_xm = Column(String(20), comment='姓名')
    o_xh = Column(String(20), comment='学号')
    o_sfzh = Column(String(18), comment='身份证号')
    o_sj = Column(String(11), comment='手机号')
    o_body = Column(String(200), comment='订单内容')
    o_money = Column(Integer, comment='订单金额(分)')
    o_zsf = Column(Integer, comment='赠送费')
    o_sf = Column(Integer, comment='实付金额')
    o_paytype = Column(String(18), comment='支付类型')
    o_type = Column(Integer, comment='订单类型')
    o_status = Column(Integer, comment='支付状态')
    o_tk_status = Column(Integer, comment='退款状态')
    o_close = Column(Integer, comment='订单关闭状态')
    o_xx_status = Column(Integer, comment='学校状态')
    o_order_no = Column(String(50), comment='订单号')
    o_trade_no = Column(String(50), comment='交易号')
    o_addtime = Column(DateTime, comment='创建时间')
    o_paytime = Column(String(50), comment='支付时间')
    o_nd = Column(Integer, comment='年度')
    o_xq = Column(String(2), comment='学期')
    o_delete = Column(Integer, comment='删除状态')
    prepay_id = Column(String(255), comment='预支付ID')
    def __repr__(self):
        return f'<WxPayinfo {self.o_id}>'

class ZzBjZd(Base):
    """班级账单表"""
    __tablename__ = 'zz_bj_zd'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    bjid = Column(Integer, comment='班级ID')
    nd = Column(Integer, comment='年度')
    xq = Column(String(2), comment='学期')
    zsf = Column(Integer, comment='总收费')
    sf = Column(Integer, comment='实收费')
    wcsx = Column(Integer, comment='外出实习')
    isopen = Column(Integer, comment='是否已经启用')
    isjdlk = Column(Integer, comment='是否接待来客')

    def __repr__(self):
        return f'<ZzBjZd {self.bjid}-{self.nd}-{self.xq}>'

class ZzBjZdgr(Base):
    """班级账单个人表"""
    __tablename__ = 'zz_bj_zdgr'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    xsxh = Column(String(20), comment='学生学号')
    nd = Column(Integer, comment='年度')
    xq = Column(String(2), comment='学期')
    zsf = Column(Integer, comment='总收费')
    sf = Column(Integer, comment='实收费')

    def __repr__(self):
        return f'<ZzBjZdgr {self.xsxh}-{self.nd}-{self.xq}>'


class ZzXsZd(Base):
    """中职学生走读表"""
    __tablename__ = 'zz_xs_zd'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    xsid = Column(String(20), comment='学生学号')
    xsxh = Column(Integer, comment='学号')
    xsxm = Column(String(2), comment='姓名')
    nd = Column(Integer, comment='年度')
    xq = Column(Integer, comment='学期')
    blsj = Column(DateTime, comment='办理时间')

    def __repr__(self):
        return f'<ZzXsZd {self.xsxh}-{self.nd}-{self.xq}>'






class ZzSys(Base):
    """系统配置表"""
    __tablename__ = 'zz_sys'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    zz_nd = Column(Integer, comment='招生年度')
    zz_zsksrq = Column(DateTime, comment='招生开始日期')
    zz_zsjzrq = Column(DateTime, comment='招生结束日期')
    zz_qrxjjzrq = Column(DateTime, comment='确认学籍截止日期')
    zz_xsjfjzrq = Column(DateTime, comment='新生缴费截止日期')
    zz_xsjf_nd = Column(Integer, comment='新生缴费年度')
    zz_xsjf_xq = Column(String(2), nullable=False, comment='新生缴费学期')
    zz_dq_nd = Column(Integer, comment='当前年度')
    zz_dq_xq = Column(String(2), comment='当前学期')
    zz_lsjfjzrq = Column(DateTime, comment='老生缴费截止日期')
    zz_lsjfksrq = Column(DateTime, comment='老生缴费开始日期')
    zz_xszdksrq = Column(DateTime, comment='学生注册开始日期')
    zz_xszdjzrq = Column(DateTime, comment='学生注册截止日期')
    zz_xsbm_switch = Column(Integer, comment='学生报名开关')  # 0-关闭 1-开启

    def __repr__(self):
        return f'<ZzSys {self.id}>'

class ZzTeachingPlan(Base):
    """教学计划表"""
    __tablename__ = 'zz_teaching_plan'
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    plan_code = Column(String(20), nullable=False, comment='计划编号')
    plan_name = Column(String(50), nullable=False, comment='计划名称')
    major_id = Column(Integer, nullable=False, comment='专业ID')
    grade = Column(String(4), nullable=False, comment='年级')
    total_credit = Column(Numeric(4,1), nullable=False, comment='总学分')
    status = Column(Integer, default=1, nullable=False, comment='状态：0-禁用 1-启用')

    def __repr__(self):
        return f'<ZzTeachingPlan {self.plan_name}>'


class ZzCourse(Base):
    """课程表"""
    __tablename__ = 'zz_course'
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    course_code = Column(String(20), nullable=False, comment='课程编号')
    course_name = Column(String(50), nullable=False, comment='课程名称')
    course_type = Column(Integer, nullable=False, comment='课程类型：1-必修 2-选修 3-公共课')
    credit = Column(Numeric(3,1), nullable=False, comment='学分')
    hours = Column(Integer, nullable=False, comment='课时')
    status = Column(Integer, default=1, nullable=False, comment='课程状态：0-禁用 1-启用')

    def __repr__(self):
        return f'<ZzCourse {self.course_name}>'


class ZzPlanCourse(Base):
    """教学计划课程关联表"""
    __tablename__ = 'zz_plan_course'
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    plan_id = Column(Integer, nullable=False, comment='教学计划ID')
    course_id = Column(Integer, nullable=False, comment='课程ID')
    year = Column(Integer, nullable=False, comment='学年')
    semester = Column(String(2), nullable=False, comment='学期')
    is_required = Column(Integer, nullable=False, comment='是否必修：0-否 1-是')
    status = Column(Integer, default=1, nullable=False, comment='状态：0-禁用 1-启用')

    def __repr__(self):
        return f'<ZzPlanCourse {self.plan_id}-{self.course_id}>'


class ZzTeachingTask(Base):
    """任课表"""
    __tablename__ = 'zz_teaching_task'
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    course_id = Column(Integer, nullable=False, comment='课程ID')
    teacher_id = Column(Integer, nullable=False, comment='教师ID')
    year = Column(Integer, nullable=False, comment='学年')
    semester = Column(String(2), nullable=False, comment='学期')
    max_students = Column(Integer, nullable=False, comment='最大选课人数')
    current_students = Column(Integer, default=0, comment='当前选课人数')
    classroom = Column(String(50), nullable=False, comment='教室')
    status = Column(Integer, default=1, nullable=False, comment='状态：0-未开课 1-已开课')

    def __repr__(self):
        return f'<ZzTeachingTask {self.course_id}-{self.teacher_id}>'


class ZzCourseScore(Base):
    """成绩表"""
    __tablename__ = 'zz_course_score'
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    student_id = Column(String(20), nullable=False, comment='学号')
    course_id = Column(Integer, nullable=False, comment='课程ID')
    teaching_task_id = Column(Integer, nullable=False, comment='任课ID')
    year = Column(Integer, nullable=False, comment='学年')
    semester = Column(String(2), nullable=False, comment='学期')
    score = Column(Numeric(5,2), comment='成绩')
    score_type = Column(Integer, nullable=False, comment='成绩类型：1-正常 2-补考 3-重修')
    create_time = Column(DateTime, nullable=False, comment='创建时间')
    update_time = Column(DateTime, nullable=False, comment='更新时间')

    def __repr__(self):
        return f'<ZzCourseScore {self.student_id}-{self.course_id}>'


class ZzCourseSelection(Base):
    """选课表"""
    __tablename__ = 'zz_course_selection'
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    student_id = Column(String(20), nullable=False, comment='学号')
    teaching_task_id = Column(Integer, nullable=False, comment='任课ID')
    year = Column(Integer, nullable=False, comment='学年')
    semester = Column(String(2), nullable=False, comment='学期')
    select_time = Column(DateTime, nullable=False, comment='选课时间')
    status = Column(Integer, default=1, nullable=False, comment='状态：0-退选 1-已选')
    create_time = Column(DateTime, nullable=False, comment='创建时间')
    update_time = Column(DateTime, nullable=False, comment='更新时间')

    def __repr__(self):
        return f'<ZzCourseSelection {self.student_id}-{self.teaching_task_id}>'

class ZzTeacher(Base):
    """中职教师表"""
    __tablename__ = 'zz_teacher'
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    teacher_code = Column(String(20), nullable=False, comment='教师编号')
    teacher_name = Column(String(20), nullable=False, comment='教师姓名')
    gender = Column(String(1), nullable=False, comment='性别：M-男 F-女')
    id_card = Column(String(18), nullable=False, comment='身份证号')
    phone = Column(String(11), comment='手机号')
    email = Column(String(50), comment='邮箱')
    department_id = Column(Integer, nullable=False, comment='部门ID')
    professional_title = Column(String(20), comment='职称')
    status = Column(Integer, default=1, nullable=False, comment='状态：0-禁用 1-启用')
    create_time = Column(DateTime, nullable=False, comment='创建时间')
    update_time = Column(DateTime, nullable=False, comment='更新时间')
    major = Column(Integer, nullable=False, comment='教师专业')

    def __repr__(self):
        return f'<ZzTeacher {self.teacher_name}>'

class ZzStCourse(Base):
    """社团课表"""
    __tablename__ = 'zz_st_course'
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    course_code = Column(String(20), nullable=False, comment='课程编号')
    course_name = Column(String(50), nullable=False, comment='课程名称')
    teacher_id = Column(Integer, nullable=False, comment='教师ID')
    credit = Column(Numeric(3,1), nullable=False, comment='学分')
    hours = Column(Integer, nullable=False, comment='课时')
    max_students = Column(Integer, nullable=False, comment='最大选课人数')
    current_students = Column(Integer, default=0, comment='当前选课人数')
    classroom = Column(String(50), nullable=False, comment='教室')
    description = Column(Text, comment='课程描述')
    status = Column(Integer, default=1, nullable=False, comment='状态：0-禁用 1-启用')
    create_time = Column(DateTime, nullable=False, comment='创建时间')
    update_time = Column(DateTime, nullable=False, comment='更新时间')
    category = Column(Integer, nullable=False, comment='类别：体育，美术，音乐，舞蹈，书法，其他')

    def __repr__(self):
        return f'<ZzStCourse {self.course_name}>'


class ZzStCourseSelection(Base):
    """社团课选课表"""
    __tablename__ = 'zz_st_course_selection'
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    student_id = Column(String(20), nullable=False, comment='学号')
    course_id = Column(Integer, nullable=False, comment='课程ID')
    year = Column(Integer, nullable=False, comment='学年')
    semester = Column(String(2), nullable=False, comment='学期')
    select_time = Column(DateTime, nullable=False, comment='选课时间')
    create_time = Column(DateTime, nullable=False, comment='创建时间')
    update_time = Column(DateTime, nullable=False, comment='更新时间')

    __table_args__ = (
        UniqueConstraint('student_id', 'course_id', 'year', 'semester', name='uk_student_course_term'),
        Index('idx_course_term', 'course_id', 'year', 'semester'),
        Index('idx_student_term', 'student_id', 'year', 'semester'),
    )

    def __repr__(self):
        return f'<ZzStCourseSelection {self.student_id}-{self.course_id}>'

class ZzStCourseTeacher(Base):
    """社团课-教师关联表（支持一门课程多个教师）"""
    __tablename__ = 'zz_st_course_teacher'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    course_id = Column(Integer, nullable=False, comment='课程ID')
    teacher_id = Column(Integer, nullable=False, comment='教师ID')
    create_time = Column(DateTime, nullable=False, default=datetime.now)

    def __repr__(self):
        return f'<ZzStCourseTeacher course={self.course_id} teacher={self.teacher_id}>'



class WxXwyyPayinfo(Base):
    """学位英语报考订单表"""
    __tablename__ = 'wx_xwyy_payinfo'

    o_id = Column(Integer, primary_key=True, autoincrement=True, comment='订单ID')
    o_xh = Column(String(20), comment='学号')
    o_sfzh = Column(String(18), comment='身份证号')
    o_body = Column(String(50), comment='订单描述')
    o_money = Column(Integer, comment='订单金额(分)')
    o_paytype = Column(String(18), comment='支付类型')
    o_type = Column(Integer, comment='订单类型')
    o_status = Column(Integer, comment='订单状态')
    o_tk_status = Column(Integer, comment='退款状态')
    o_tk_no = Column(String(50), comment='退款单号')
    o_refund_no = Column(String(50), comment='商户退款单号')
    o_refund_addtime = Column(DateTime, comment='退款申请时间')
    o_refund_success_time = Column(DateTime, comment='退款成功时间')
    o_refund_fee = Column(Integer, comment='退款金额(分)')
    o_close = Column(Integer, comment='订单关闭状态')
    o_order_no = Column(String(50), comment='商户订单号')
    o_trade_no = Column(String(50), comment='交易单号')
    o_addtime = Column(DateTime,  comment='创建时间')
    o_paytime = Column(String(50), comment='支付时间')
    o_pc = Column(String(4), comment='批次')
    o_delete = Column(Integer, comment='删除标记')
    o_shenhe = Column(Integer, comment='审核状态')

    def __repr__(self):
        return f'<WxXwyyPayinfo {self.o_order_no}>'

class WxxsSfTkpayinfo(Base):
    """书费退款支付信息表"""
    __tablename__ = 'wxxs_sf_tkpayinfo'

    o_id = Column(Integer, primary_key=True, autoincrement=True)  # 主键，自增ID
    o_xh = Column(String(50))            # 学号
    o_xm = Column(String(50))            # 学生姓名
    o_dh = Column(String(50))            # 电话
    o_money = Column(Integer)            # 金额（单位：分）
    o_openid = Column(String(50))        # 微信openid
    o_pc = Column(Integer)               # 批次号
    o_status = Column(Integer)           # 状态（0-初始值，未申请，1-已申请，并绑定openid，2-生成订单,等待学生确认收款，3-收款完成    -1 -生成订单失败）
    o_out_bill_no = Column(String(50))   # 内部系统退款申请单号
    o_create_time = Column(DateTime)     # 内部系统单子创建时间，该单子24小时内有效，超过则重新生成内部单号
    package_info = Column(String(260))   # 包信息，用于拉起支付（如用于存储扩展数据）
    o_transfer_bill_no = Column(String(100))  # 微信转账单号
    o_payment_time = Column(DateTime)    # 支付/转账时间
    o_check_state = Column(String(20))   # 微信端单子审核状态
    o_check_state_des = Column(String(20))   # 微信端单子审核状态说明


    def __repr__(self):
        return f'<WxxsSfTkpayinfo {self.o_id}>'

class JhZ(Base):
    """教学计划总表"""
    __tablename__ = 'jh_z'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    gzh = Column(String(50), comment='规则号')
    zymc = Column(String(50), comment='专业名称')
    xslx = Column(String(50), comment='学生类型')
    kcid = Column(String(50), comment='课程ID')
    kcmc = Column(String(50), comment='课程名称')
    kcxf = Column(String(50), comment='课程学分')
    kclx = Column(String(50), comment='课程类型')
    ksxq = Column(String(50), comment='开设学期')
    kcxz = Column(String(50), comment='课程性质')
    ksdw = Column(String(50), comment='考试单位')
    cc = Column(String(50), comment='层次')
    pc = Column(Integer, comment='批次')

    def __repr__(self):
        return f'<JhZ {self.kcmc}>'
    




    

# 下面的模型是用来进行高职报名的模型结束了

class ExamKc(Base):
    """考试课程表"""
    __tablename__ = 'exam_kc'
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    kcid = Column(String(50), comment='课程ID')
    kcmc = Column(String(50), comment='课程名称')
    kccc = Column(String(50), comment='课程层次')
    ksdw = Column(String(50), comment='考试单位')
    xkfs = Column(String(50), comment='形考方式')
    zkfs = Column(String(50), comment='终考方式')

    def __repr__(self):
        return f'<ExamKc {self.kcmc}>'

class ExamXsDt(Base):
    """学生答题表"""
    __tablename__ = 'exam_xs_dt'
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    xh = Column(String(50), comment='学号')
    xm = Column(String(50), comment='姓名')
    kc_id = Column(String(50), comment='课程ID', index=True)
    sj_id = Column(Integer, comment='试卷ID')
    tm_id = Column(Text, comment='题目ID列表')
    fz_id = Column(Text, comment='分值ID列表')
    dt = Column(Text, comment='答题内容')
    da = Column(Text, comment='标准答案')
    pyfs = Column(Text, comment='评分方式')
    cj = Column(Integer, comment='成绩')
    zgt_tm_id = Column(Text, comment='主观题题目ID列表')
    zgt_fz_id = Column(Text, comment='主观题分值ID列表')
    zgt_dt = Column(Text, comment='主观题答题内容')
    zgt_pyfs = Column(Text, comment='主观题评分方式')
    zgt_cj = Column(Integer, comment='主观题成绩')
    pc = Column(Integer, comment='批次')
    cs = Column(Integer, comment='次数')
    zt = Column(Integer, comment='状态')
    zgt_zt = Column(Integer, comment='主观题状态')
    tjsj = Column(DateTime, comment='提交时间')
    t_id = Column(Integer, comment='教师ID')
    pysj = Column(DateTime, comment='评阅时间')
    source = Column(String(50), comment='答题来源')

    def __repr__(self):
        return f'<ExamXsDt {self.xh}-{self.xm}>'


class ExamFppy(Base):
    """分批评阅表 - 记录教师需要评阅的学生-课程分配"""
    __tablename__ = 'exam_fppy'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    xh = Column(String(50), comment='学号')
    xm = Column(String(50), comment='姓名')
    bjdm = Column(String(50), comment='班级代码')
    bjmc = Column(String(50), comment='班级名称')
    kcid = Column(String(50), comment='课程ID')
    kcmc = Column(String(50), comment='课程名称')
    yzdsjh = Column(String(50), comment='验证码手机号')
    xkfs_paper = Column(String(50), comment='线下考试方式')
    ksfs_paper = Column(String(50), comment='线下考试方式')
    xkfs_system = Column(String(50), comment='线上考试方式')
    ksfs_system = Column(String(50), comment='线上考试方式')
    kccc = Column(String(50), comment='课程层次')
    ksdw = Column(String(50), comment='考试单位')
    t_id = Column(Integer, comment='教师ID')
    t_xm = Column(String(50), comment='教师姓名')
    dq1_id = Column(Integer, comment='地区ID')
    dq1_mc = Column(String(50), comment='地区名称')
    pc = Column(Integer, comment='批次')

    __table_args__ = (
        Index('idx_exam_fppy_pc_tid', 'pc', 't_id'),
    )

    def __repr__(self):
        return f'<ExamFppy {self.xh}-{self.kcid}>'


class CooperationSchoolMajor(Base):
    """合作院校专业表"""
    __tablename__ = 'zz_bmxs_cooperation_schoolmajor'
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    school_major_name = Column(String(50), nullable=True, comment='专业名称')
    local_major_id = Column(Integer, nullable=True, comment='本校专业ID')
    major_number = Column(Integer, nullable=True, comment='专业编号')
    zsme = Column(Integer, nullable=True, comment='招生名额')
    bmrs = Column(Integer, nullable=True, comment='报名人数')
    remark = Column(String(50), nullable=True, comment='备注')
    zs = Column(Integer, nullable=True, comment='是否展示')
    def __repr__(self):
        return f'<CooperationSchoolMajor {self.school_major_name}>'

    def to_dict(self):
        return {
            'id': self.id,
            'school_major_name': self.school_major_name,
            'local_major_id': self.local_major_id,
            'major_number': self.major_number,
            'zsme': self.zsme,
            'bmrs': self.bmrs,
            'remark': self.remark
        }

class ExamSj(Base):
    __tablename__ = 'exam_sj'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    kc_id = Column(Integer, nullable=True, comment='课程ID')
    lx_id = Column(Integer, nullable=True, comment='类型ID')
    tm_zj_id = Column(Text, nullable=True, comment='题目组卷ID')
    pc = Column(Integer, nullable=True, comment='批次')
    t_id = Column(Integer, nullable=True, comment='教师ID')
    zt = Column(Integer, nullable=True, comment='状态')

    def __repr__(self):
        return f"<ExamSj id={self.id} kc_id={self.kc_id} lx_id={self.lx_id}>"

class BkGkbkb(Base):
    """高考报考表模型"""
    __tablename__ = 'bk_gkbkb'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    xm = Column(String(50), comment='姓名')
    xslb = Column(String(50), comment='学生类别')
    xh = Column(String(50), comment='学号')
    bjdm = Column(String(50), comment='班级代码')
    bjmc = Column(String(50), comment='班级名称')
    zymc = Column(String(50), comment='专业名称')
    zydm = Column(String(50), comment='专业代码')
    kcmc = Column(String(50), comment='课程名称')
    kcid = Column(String(50), comment='课程ID')
    yzdsjh = Column(String(50), comment='原制定试卷号')
    sjhzdzt = Column(String(50), comment='试卷号制定状态')
    kxsjh = Column(String(50), comment='可选试卷号')
    pc = Column(Integer, comment='批次')
    dq1_id = Column(Integer, comment='地区1ID')
    dq1_mc = Column(String(50), comment='地区1名称')

    def __repr__(self):
        return f"<BkGkbkb id={self.id} xm={self.xm} xh={self.xh}>"


class TotalScore(Base):
    """总成绩模型 - 对应 tzd_cj_z 表"""
    __tablename__ = 'tzd_cj_z'

    id = Column(Integer, primary_key=True, autoincrement=True)
    F1 = Column(String(255), comment='课程名称')
    F2 = Column(String(255), comment='课程代码')
    F3 = Column(String(255), comment='试卷号')
    F4 = Column(String(255), comment='学生学号')
    F5 = Column(String(255), comment='学生姓名')
    F6 = Column(String(255), comment='班级代码')
    F7 = Column(String(255), comment='班级名称')
    F8 = Column(String(255), comment='学习中心')
    xxzxdm = Column(String(255), comment='学习中心代码')
    F9 = Column(String(255), comment='形考比例')
    F10 = Column(String(255), comment='形考成绩')
    xkcjly = Column(String(255), comment='形考成绩来源')
    zkcjly = Column(String(255), comment='终考成绩来源')
    F11 = Column(String(255), comment='终考成绩')
    F12 = Column(String(255), comment='综合成绩')
    F13 = Column(String(255), comment='成绩完整性')
    F14 = Column(String(255), comment='是否合成')
    F15 = Column(String(255), comment='是否双及格')
    F16 = Column(String(255), comment='是否标记')
    F17 = Column(String(255), comment='是否正常')
    F18 = Column(String(255), comment='成绩状态')
    F19 = Column(String(255), comment='考试批次')

    def __repr__(self):
        return f"<TotalScore id={self.id} F4={self.F4} F2={self.F2} F12={self.F12}>"


class Old_Zcjb(Base):
    """旧总成绩表模型 - 对应 zcjb 表"""
    __tablename__ = 'zcjb'

    sxh = Column(String(32), primary_key=True, comment='顺序号')
    xh = Column(String(13), comment='学号')
    kcid = Column(String(5), comment='课程ID')
    ksdm = Column(String(6), comment='考试代码')
    kslbdm = Column(String(3), comment='考试类别代码')
    sjh = Column(String(4), comment='试卷号')
    sjcj = Column(Integer, comment='试卷成绩')
    sjcjdm = Column(String(2), comment='试卷成绩代码')
    xkcj = Column(Integer, comment='形考成绩')
    xkcjdm = Column(String(2), comment='形考成绩代码')
    xkbl = Column(Numeric(5, 2), comment='形考比例')
    zhcj = Column(Integer, comment='综合成绩')
    zhcjdm = Column(String(2), comment='综合成绩代码')
    szxxdm = Column(String(7), comment='所在学校代码')
    jxb = Column(String(10), comment='教学班')
    xxdm = Column(String(7), comment='学校代码')
    cjly = Column(String(2), comment='成绩来源')
    qdcjsj = Column(DateTime, comment='取得成绩时间')
    kscs = Column(Integer, comment='考试次数')
    khfs = Column(String(2), comment='考核方式')
    czy = Column(String(20), comment='操作员')
    czrq = Column(DateTime, comment='操作日期')
    ksdwlxdm = Column(String(1), comment='考试单位类型代码')
    bbh = Column(Integer, comment='版本号')
    xkcjgddm = Column(String(2), comment='形考成绩获得代码')
    bzhcbz = Column(String(1), comment='标准合成标志')
    lrbz = Column(String(3), comment='录入标志')
    cgbz = Column(String(1), comment='成功标志')
    sscsj = Column(String(19), comment='实时上传时间')
    sbyy = Column(Integer, comment='失败原因')
    tjsj = Column(String(19), comment='提交时间')

    def __repr__(self):
        return f"<Old_Zcjb sxh={self.sxh} xh={self.xh} kcid={self.kcid} zhcj={self.zhcj}>"


class TzdCjZJsh(Base):
    """成绩综合表模型 - 基于 tzd_cj_z_jsh 表"""
    __tablename__ = 'tzd_cj_z_jsh'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    bjid = Column(Integer, comment='班级ID')
    bzrid = Column(Integer, comment='班主任ID')
    dq1id = Column(Integer, comment='地区1ID')
    dq2id = Column(Integer, comment='地区2ID')
    xh = Column(String(20), comment='学号')
    kcmc = Column(String(100), comment='课程名称')
    kcid = Column(String(20), comment='课程ID')
    zhcj = Column(String(10), comment='综合成绩')
    nd = Column(String(10), comment='年度')
    xqdm = Column(String(10), comment='学期代码')

    def __repr__(self):
        return f"<TzdCjZJsh id={self.id} xh={self.xh} kcmc={self.kcmc} zhcj={self.zhcj}>"


class SMSLog(Base):
    """教师短信发送记录表"""
    __tablename__ = 'sms_log'

    id = Column(Integer, primary_key=True, autoincrement=True)
    lx = Column(Integer, nullable=True, comment='类型,1:校内教师短信,2:校外短信,3:开放学生短信,4:中职学生短信,5:请销假通知')
    t_id = Column(Integer, nullable=True, comment='教师ID')
    t_xm = Column(String(50), nullable=True, comment='教师姓名')
    fssj = Column(DateTime, nullable=True, comment='发送时间')
    nr = Column(String(600), nullable=True, comment='短信内容')
    xs_id = Column(String(50), nullable=True, comment='学生ID')
    xs_xm = Column(String(50), nullable=True, comment='学生姓名')
    xs_dh = Column(String(50), nullable=True, comment='学生电话')
    num = Column(Integer, nullable=True, comment='发送数量')
    cpSubID = Column(String(50), nullable=True, comment='同步状态ID')
    send_status = Column(String(50), nullable=True, comment='同步状态(0:成功, 其他:失败)')
    status_desc = Column(String(50), nullable=True, comment='同步状态描述')
    callback_status = Column(String(1000), nullable=True, comment='腾讯云回调原始JSON报文(不解析)')
    callback_desc = Column(String(600), nullable=True, comment='腾讯云回调描述(errmsg+description)')

    def __repr__(self):
        return f"<SMSLog id={self.id} t_xm={self.t_xm} xs_dh={self.xs_dh}>"

class SMSTb(Base):
    """教师回调记录表"""
    __tablename__ = 'sms_tb'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    cpSubID = Column(String(50), comment='系统任务id')
    uPhone = Column(String(50), comment='手机号码')
    rptcode = Column(String(20), comment='答复码')

    def __repr__(self):
        return f"<TeacherSms id={self.id}>"


class DegreeEnglishRegistration(Base):
    """学位英语报名名单模型"""
    __tablename__ = 'kw_xwyybmmd'
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    xm = Column(String(50), comment='姓名')
    xh = Column(String(50), comment='学号')
    bjdm = Column(String(50), comment='班级代码')
    bjmc = Column(String(50), comment='班级名称')
    ksssxxzxmc = Column(String(50), comment='考生所属学习中心名称')
    ksssxxzxdm = Column(String(50), comment='考生所属学习中心代码')
    zymc = Column(String(50), comment='专业名称')
    zycc = Column(String(50), comment='专业层次')
    zyyylb = Column(String(50), comment='专业应用类别')
    bkkdssfb = Column(String(50), comment='报考考点所属分部')
    bkkd = Column(String(50), comment='报考考点')
    bkly = Column(String(50), comment='报考来源')
    ksly = Column(String(50), comment='考生来源')
    bkspzt = Column(String(50), comment='报考审批状态')
    
    def __repr__(self):
        return f"<DegreeEnglishRegistration id={self.id} xm={self.xm} xh={self.xh}>"



class ZzXsQxj(Base):
    """学生请销假模型"""
    __tablename__ = 'zz_xs_qxj'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    xm = Column(String(50), nullable=True, comment='姓名')
    xh = Column(String(50), nullable=True, comment='学号')
    bj_id = Column(Integer, nullable=True, comment='班级ID')
    qjlb = Column(String(50), nullable=True, comment='请假类别')
    qjsy = Column(String(200), nullable=True, comment='请假事由')
    qjsqsj = Column(DateTime, nullable=True, comment='请假申请时间')
    qjkssj = Column(DateTime, nullable=True, comment='请假开始时间')
    qjjssj = Column(DateTime, nullable=True, comment='请假结束时间')
    xslxxl = Column(String(100), nullable=True, comment='学生离校线路')
    xslxjtgj = Column(String(50), nullable=True, comment='学生离校交通工具')
    sp_bzr_tid = Column(Integer, nullable=True, comment='审批班主任ID')
    sp_bzr_xm = Column(String(50), nullable=True, comment='审批班主任姓名')
    bzr_zt = Column(Integer, nullable=True, comment='班主任审批状态，0为审批中，1为审批通过，2为审批不通过')
    sp_xsk_tid = Column(Integer, nullable=True, comment='审批学生科ID')
    sp_xsk_xm = Column(String(50), nullable=True, comment='审批学生科姓名')
    xsk_zt = Column(Integer, nullable=True, comment='学生科审批状态，0为审批中，1为审批通过，2为审批不通过')
    xjsj = Column(DateTime, nullable=True, comment='销假时间')
    xsfxxl = Column(String(100), nullable=True, comment='学生返校线路')
    xsfxjtgj = Column(String(50), nullable=True, comment='学生返校交通工具')
    xj_zt = Column(Integer, nullable=True, comment='销假状态，0为未销假，1为已销假')
    sp_xsk_sj = Column(DateTime, nullable=True, comment='学生科审核时间')
    sp_bzr_sj = Column(DateTime, nullable=True, comment='班主任审核时间')
    hik_task_id = Column(String(255), nullable=True, comment='海康下发任务id')


# ==================== 招生报名系统模型 ====================


class ZsCategory(Base):
    """招生类别表"""
    __tablename__ = 'zs_category'
    __table_args__ = {'implicit_returning': False}
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    code = Column(String(50), nullable=False, unique=True, comment='类别编码')
    name = Column(String(100), nullable=False, comment='类别名称')
    description = Column(Text, comment='类别描述')
    prospectus = Column(Text, comment='招生简章（富文本）')
    extra_info = Column(Text, comment='额外信息（JSON 字符串，键值对）')
    sort_order = Column(Integer, default=0, comment='排序')
    is_active = Column(Integer, default=1, comment='是否启用：0-禁用 1-启用')
    start_time = Column(DateTime, comment='报名开始时间')
    end_time = Column(DateTime, comment='报名结束时间')
    batch = Column(Integer, comment='当前批次')
    create_time = Column(DateTime, default=datetime.now, comment='创建时间')
    update_time = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')
    
    def __repr__(self):
        return f'<ZsCategory {self.name}>'




class ZsDict(Base):
    """招生通用字典表"""
    __tablename__ = 'zs_dict'
    __table_args__ = {'implicit_returning': False}
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    category_id = Column(Integer, nullable=False, comment='招生类别ID，关联zs_category表')
    type = Column(String(50), nullable=False, comment='字典类型')
    code = Column(String(50), nullable=False, comment='字典编码')
    label = Column(String(100), nullable=False, comment='字典标签')
    parent_code = Column(String(50), comment='父级编码，用于级联选择')
    sort_order = Column(Integer, default=0, comment='排序')
    is_active = Column(Integer, default=1, comment='是否启用：0-禁用 1-启用')
    remark = Column(String(500), comment='备注')
    extra_data = Column(Text, comment='扩展数据（JSON格式）')
    create_time = Column(DateTime, default=datetime.now, comment='创建时间')
    update_time = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')
    
    def __repr__(self):
        return f'<ZsDict {self.type}-{self.label}>'


class ZsAdultEnrollment(Base):
    """成人高等教育预报名表"""
    __tablename__ = 'zs_adult_enrollment'
    __table_args__ = {'implicit_returning': False}
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    
    # 1. 姓名（必填）
    name = Column(String(50), nullable=False, comment='姓名')
    
    # 2. 手机号（必填）
    phone = Column(String(20), nullable=False, comment='手机号')
    
    # 3. 意向专业及费用明细（必选）
    major_code = Column(String(50), nullable=False, comment='意向专业代码，关联zs_dict')
    
    # 4. 选择入学后的学习中心（必选）
    learning_center_code = Column(String(50), nullable=False, comment='学习中心代码，关联zs_dict')
    
    # 状态信息
    status = Column(Integer, default=0, comment='状态：0-待审核 1-审核通过 2-审核不通过 3-已录取')
    batch = Column(Integer, comment='批次')
    submit_time = Column(DateTime, default=datetime.now, comment='提交时间')
    audit_time = Column(DateTime, comment='审核时间')
    auditor_id = Column(Integer, comment='审核人ID')
    audit_remark = Column(String(500), comment='审核备注')
    
    # 微信信息
    wx_openid = Column(String(100), comment='微信openid')
    wx_nickname = Column(String(100), comment='微信昵称')
    wx_headimgurl = Column(String(500), comment='微信头像')
    
    # 招生老师
    recruiter = Column(String(50), comment='招生老师姓名')
    
    # 查询码
    query_code = Column(String(20), unique=True, comment='8位查询码，用于用户查看/修改报名信息')
    query_code_expire = Column(DateTime, comment='查询码过期时间')
    
    # 时间戳
    create_time = Column(DateTime, default=datetime.now, comment='创建时间')
    update_time = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')
    
    def __repr__(self):
        return f'<ZsAdultEnrollment {self.name}-{self.phone}>'


class ZsVocational34Enrollment(Base):
    """3+4中本贯通舞蹈表演专业面试考生报名表"""
    __tablename__ = 'zs_vocational34_enrollment'
    __table_args__ = {'implicit_returning': False}
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    
    # 1. 序号（自动生成）
    serial_number = Column(String(20), comment='序号')
    
    # 2. 考生基本信息
    # (1) 学生姓名
    name = Column(String(50), nullable=False, comment='学生姓名')
    
    # (2) 准考证号
    admission_ticket_no = Column(String(50), comment='准考证号')
    
    # (3) 性别
    gender = Column(String(20), nullable=False, comment='性别：male男/female女')
    
    # (4) 民族
    nation = Column(String(50), comment='民族代码，关联zs_dict')
    
    # (5) 身份证号码
    id_card = Column(String(18), nullable=False, comment='身份证号码')
    
    # (6) 原初中毕业学校全称
    junior_school_name = Column(String(100), comment='原初中毕业学校全称')
    
    # (7) 原初中毕业学校所在县份
    junior_school_county = Column(String(100), comment='原初中毕业学校所在县份')
    
    # (8) 是否黔东南州的2025年应届初中毕业生
    is_qdn_graduate = Column(String(50), comment='是否黔东南州的2025年应届初中毕业生，格式category_id:type:code')
    
    # 3. 籍贯信息
    # (1) 户口性质
    household_type = Column(String(50), comment='户口性质：agricultural农业户口/non_agricultural非农户口')
    
    # (2) 户籍详细地址
    household_province = Column(String(50), comment='户籍省份代码')
    household_city = Column(String(50), comment='户籍城市代码')
    household_district = Column(String(50), comment='户籍区县代码')
    household_address = Column(String(200), comment='户籍详细地址')
    
    # (3) 实际居住地址
    residence_province = Column(String(50), comment='实际居住省份代码')
    residence_city = Column(String(50), comment='实际居住城市代码')
    residence_district = Column(String(50), comment='实际居住区县代码')
    residence_address = Column(String(200), comment='实际居住详细地址')
    
    # 4. 手机号
    phone = Column(String(20), nullable=False, comment='手机号')

    # 4.1 面试当天是否驾车及车牌信息（不驾车填"无"，驾车填车牌号）
    interview_car_plate = Column(String(50), comment='面试当天是否驾车及车牌信息：不驾车填"无"，驾车填车牌号')

    # 5. 监护人信息
    # (1) 监护人姓名
    guardian_name = Column(String(50), comment='监护人姓名')
    
    # (2) 联系方式
    guardian_phone = Column(String(20), comment='监护人联系方式')
    
    # (3) 监护人身份
    guardian_relation = Column(String(50), comment='监护人身份：father父亲/mother母亲/other其他')
    
    # 6. 请上传考生本人身份证正面
    id_card_front_url = Column(String(500), comment='身份证正面照片URL')
    
    # 7. 请上传考生本人身份证反面
    id_card_back_url = Column(String(500), comment='身份证反面照片URL')
    
    # 8. 请上传考生本人标准证件照
    photo_url = Column(String(500), comment='标准证件照URL')
    
    # 9. 请上传考生监护人同意考生参加"3+4"舞蹈表演专业面试的知情同意书
    consent_letter_url = Column(String(500), comment='知情同意书照片URL')
    
    # 10. 知情确认（已阅读并同意）
    is_confirmed = Column(Integer, default=0, comment='知情确认：1-已确认 0-未确认')
    
    # 11. 请考生本人签名（base64编码）
    signature_base64 = Column(Text, comment='考生签名base64编码')
    
    # 状态信息
    status = Column(Integer, default=0, comment='状态：0-待审核 1-审核通过 2-审核不通过 3-已录取')
    batch = Column(Integer, comment='批次')
    submit_time = Column(DateTime, default=datetime.now, comment='提交时间')
    audit_time = Column(DateTime, comment='审核时间')
    auditor_id = Column(Integer, comment='审核人ID')
    audit_remark = Column(String(500), comment='审核备注')
    
    # 微信信息
    wx_openid = Column(String(100), comment='微信openid')
    wx_nickname = Column(String(100), comment='微信昵称')
    wx_headimgurl = Column(String(500), comment='微信头像')
    
    # 查询码
    query_code = Column(String(20), unique=True, comment='8位查询码，用于用户查看/修改报名信息')
    query_code_expire = Column(DateTime, comment='查询码过期时间')
    
    # 时间戳
    create_time = Column(DateTime, default=datetime.now, comment='创建时间')
    update_time = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')
    
    def __repr__(self):
        return f'<ZsVocational34Enrollment {self.name}-{self.phone}>'



class ZsGraduateEmploymentSurvey(Base):
    """毕业生就业情况与就业需求调查表"""
    __tablename__ = 'zs_graduate_employment_survey'
    __table_args__ = {'implicit_returning': False}

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')

    # Q1 学生信息（学号 + 姓名 + 身份证；班级与学生主体可由 student_no 关联 zz_xs 反查）
    student_no = Column(String(50), comment='学号')
    student_name = Column(String(50), nullable=False, comment='学生姓名')
    id_card = Column(String(20), comment='身份证号')

    # Q2 手机号
    phone = Column(String(20), nullable=False, comment='手机号码')

    # Q3 是否精准服务（1-是 2-否）
    precise_service = Column(String(10), comment='是否精准服务')

    # Q4 毕业去向（1-11）
    destination = Column(String(20), comment='毕业去向：1签订合同就业/2应征义务兵/3自主创业/4灵活就业/5普通高考升学/6职教高考升学/7出国出境升学/8贯通培养升学/9待就业/10不就业拟升学/11其他暂不就业')

    # Q5 征兵办公室全称（destination=2时）
    military_office = Column(String(200), comment='征兵办公室全称')

    # Q6 升学层次（1-本科 2-专科）
    education_level = Column(String(20), comment='升学层次')

    # Q7 录取高校名称（字典）
    college_code = Column(String(50), comment='录取高校代码')
    college_name = Column(String(200), comment='录取高校名称')

    # Q8 录取专业（字典）
    major_code = Column(String(50), comment='录取专业代码')
    major_name = Column(String(200), comment='录取专业名称')

    # Q9 录取分数
    admission_score = Column(String(50), comment='录取分数')

    # Q10 合同或协议签订情况（1-4）
    contract_type = Column(String(20), comment='合同签订情况')

    # Q11 就业渠道（1-3）
    employment_channel = Column(String(20), comment='就业渠道')

    # Q12 工作单位名称
    company_name = Column(String(200), comment='工作单位名称')

    # Q13 就业单位省份/城市
    work_province_city = Column(String(100), comment='单位所在省份城市')

    # Q14 单位详细地址
    work_address = Column(String(500), comment='单位详细地址')

    # Q15 单位性质（1-5）
    company_nature = Column(String(20), comment='单位性质')

    # Q16 所处行业（1-22）
    industry = Column(String(20), comment='所处行业')

    # Q17 工作岗位（1-251 或自定义）
    position = Column(String(50), comment='工作岗位')
    position_name = Column(String(100), comment='工作岗位名称')

    # Q18 月薪
    monthly_salary = Column(String(20), comment='当前月薪')

    # Q19 就业凭证文件URL
    certificate_url = Column(String(500), comment='就业凭证文件URL')

    # Q20 满意度（1-5）
    satisfaction = Column(String(20), comment='就业现状满意度')

    # Q21 是否需要学校推荐就业（1-是 2-否）
    need_recommendation = Column(String(10), comment='是否需要就业推荐')

    # Q22 意见或建议
    feedback = Column(Text, comment='其他意见或建议')

    # 批次（对应 zs_category.batch，提交时写入）
    batch = Column(Integer, comment='批次（提交时所属招生类别的当前批次）')

    # 查询码
    query_code = Column(String(20), unique=True, comment='8位查询码，用于用户查看/修改报名信息')
    query_code_expire = Column(DateTime, comment='查询码过期时间')

    # 时间戳
    submit_time = Column(DateTime, default=datetime.now, comment='提交时间')
    create_time = Column(DateTime, default=datetime.now, comment='创建时间')
    update_time = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    def __repr__(self):
        return f'<ZsGraduateEmploymentSurvey {self.student_name}-{self.phone}>'


class JobRecommendation(Base):
    """就业推荐文章表"""
    __tablename__ = 'zs_job_recommendation'
    __table_args__ = {'implicit_returning': False}
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    title = Column(String(200), nullable=False, comment='文章标题')
    cover_image = Column(String(500), comment='封面图片URL')
    content = Column(Text, comment='文章内容（富文本）')
    summary = Column(String(500), comment='文章摘要')
    view_count = Column(Integer, default=0, comment='点击率/浏览量')
    sort_order = Column(Integer, default=0, comment='排序')
    is_published = Column(Integer, default=1, comment='是否发布：0-草稿 1-已发布')
    author = Column(String(50), comment='作者')
    create_time = Column(DateTime, default=datetime.now, comment='创建时间')
    update_time = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')
    
    def __repr__(self):
        return f'<JobRecommendation {self.title}>'



class HeadquartersExam(Base):
    """总部考试文件模型"""
    __tablename__ = 'bk_zb'  # 设置表名

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    zycc = Column(String(50), comment='专业层次')
    kcid = Column(String(50), comment='课程ID')
    kcmc = Column(String(50), comment='课程名称')
    xkbl = Column(String(50), comment='形考比例')
    ksfs = Column(String(50), comment='考试方式')
    kssc = Column(String(50), comment='考试时长')
    sjh = Column(String(50), comment='试卷号')
    kssj = Column(String(50), comment='考试时间')
    xdgj = Column(String(50), comment='携带工具')
    sfsjg = Column(String(50), comment='是否双及格')
    jsdw = Column(String(10), comment='建设单位')
    bz = Column(String(100), comment='备注')
    kslx = Column(String(50), comment='考试类型')
    ksdw = Column(String(10), comment='考试单位')
    xkfs = Column(String(50), comment='形考方式')

    def __repr__(self):
        return f"<HeadquartersExam(id={self.id}, kcmc={self.kcmc})>"


class BranchExam(Base):
    """分部考试文件模型"""
    __tablename__ = 'bk_fb'  # 设置表名

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    zycc = Column(String(50), comment='专业层次')
    kcmc = Column(String(50), comment='课程名称')
    kcid = Column(String(50), comment='课程ID')
    sjh = Column(String(50), comment='试卷号')
    xkbl = Column(String(50), comment='形考比例')
    xkfs = Column(String(50), comment='形考方式')
    ksfs = Column(String(50), comment='考试方式')
    ksdw = Column(String(50), comment='考试单位')

    def __repr__(self):
        return f"<BranchExam(id={self.id}, kcmc={self.kcmc})>"



class RepairTeachingPlan(Base):
    """补修课教学计划模型"""
    __tablename__ = 'jhbx'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    F1 = Column(String(200), comment='序号')
    F2 = Column(String(200), comment='专业名称')
    F3 = Column(String(200), comment='专业代码')
    F4 = Column(String(200), comment='课程ID')
    F5 = Column(String(200), comment='课程名称')
    F6 = Column(String(200), comment='学分')
    F7 = Column(String(200), comment='批次')

    def __repr__(self):
        return f'<RepairTeachingPlan {self.id}>'


class BannedWord(Base):
    """短信违禁词表"""
    __tablename__ = 'sms_banned_word'
    __table_args__ = {'implicit_returning': False}

    id = Column(Integer, primary_key=True, autoincrement=True)
    word = Column(String(100), nullable=False, unique=True, comment='违禁词')
    status = Column(String(20), nullable=False, default='pending', comment='状态: banned/pending/safe')
    source = Column(String(20), nullable=False, default='manual', comment='来源: manual/detect/ai')
    detect_count = Column(Integer, default=0, comment='检测次数')
    last_detect_time = Column(DateTime, nullable=True, comment='最后检测时间')
    create_time = Column(DateTime, default=datetime.now, comment='创建时间')
    update_time = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    def __repr__(self):
        return f'<BannedWord {self.word} status={self.status}>'


# ============================================
# 宿舍管理模块
# ============================================

# ============================================
# 宿舍管理模块
# ============================================

class ZzSsLd(Base):
    """宿舍楼栋表"""
    __tablename__ = 'zz_ss_ld'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    mc = Column(String(50), nullable=False, comment='楼栋名称')
    bz = Column(String(200), comment='备注')
    px = Column(Integer, default=0, comment='排序')
    zt = Column(Integer, default=1, comment='状态 1-启用 0-禁用')
    cjsj = Column(DateTime, default=datetime.now, comment='创建时间')
    gxsj = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    def __repr__(self):
        return f'<ZzSsLd {self.mc}>'


class ZzSsLc(Base):
    """宿舍楼层表"""
    __tablename__ = 'zz_ss_lc'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    ld_id = Column(Integer, nullable=False, comment='楼栋ID')
    lc = Column(Integer, nullable=False, comment='楼层号')
    cwsl = Column(Integer, default=30, comment='宿舍槽位数量（虚线框数量，如20则上下各10）')
    bz = Column(String(200), comment='备注')
    zt = Column(Integer, default=1, comment='状态 1-启用 0-禁用')

    def __repr__(self):
        return f'<ZzSsLc 楼栋{self.ld_id}-{self.lc}层>'


class ZzSsSs(Base):
    """宿舍表"""
    __tablename__ = 'zz_ss_ss'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    lc_id = Column(Integer, nullable=False, comment='楼层ID')
    ssh = Column(String(20), nullable=False, comment='宿舍号')
    cwsl = Column(Integer, default=8, comment='床位槽位数量（6人间=6，8人间=8）')
    kr = Column(Integer, default=1, comment='是否可入住 1-可住 0-不可住（楼梯间/空房占位）')
    bz = Column(String(200), comment='备注')
    px = Column(Integer, default=0, comment='排序位置，0=未安排')
    zt = Column(Integer, default=1, comment='状态 1-启用 0-禁用')

    def __repr__(self):
        return f'<ZzSsSs {self.ssh}>'


class ZzSsCw(Base):
    """宿舍床位表"""
    __tablename__ = 'zz_ss_cw'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    ss_id = Column(Integer, nullable=False, comment='宿舍ID')
    cwh = Column(String(10), nullable=False, comment='床位号')
    px = Column(Integer, default=0, comment='排序位置，0=未安排')
    zsr_type = Column(String(10), comment='住宿人类型: student')
    zsr_id = Column(Integer, comment='住宿人ID')
    zsr_xm = Column(String(50), comment='住宿人姓名（冗余）')
    zt = Column(Integer, default=1, comment='状态 1-启用 0-禁用')

    def __repr__(self):
        return f'<ZzSsCw 宿舍{self.ss_id}-床位{self.cwh}>'


class ZzSsBq(Base):
    """宿舍标签表（楼层/宿舍/床位通用）"""
    __tablename__ = 'zz_ss_bq'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    target_type = Column(String(10), nullable=False, comment='关联类型: floor/room/bed')
    target_id = Column(Integer, nullable=False, comment='关联目标ID')
    bq = Column(String(50), nullable=False, comment='标签名称')
    cjsj = Column(DateTime, default=datetime.now, comment='创建时间')

    def __repr__(self):
        return f'<ZzSsBq {self.target_type}:{self.target_id} - {self.bq}>'


class ZzSsLs(Base):
    """留宿申请表"""
    __tablename__ = 'zz_ss_ls'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    xs_id = Column(Integer, nullable=False, comment='学生ID')
    xs_xm = Column(String(50), comment='学生姓名（冗余）')
    xs_xh = Column(String(50), comment='学号（冗余）')
    bj_id = Column(Integer, comment='班级ID')
    bj_mc = Column(String(50), comment='班级名称（冗余）')
    ld_id = Column(Integer, comment='楼栋ID')
    ld_mc = Column(String(50), comment='楼栋名称（冗余）')
    ss_id = Column(Integer, comment='宿舍ID')
    ss_ssh = Column(String(20), comment='宿舍号（冗余）')
    cw_id = Column(Integer, comment='床位ID')
    cw_cwh = Column(String(10), comment='床位号（冗余）')
    ls_type = Column(String(20), default='weekend', comment='留宿类型: weekend-周末 holiday-假期 other-其他')
    ls_reason = Column(String(500), comment='留宿原因')
    start_date = Column(DateTime, nullable=False, comment='留宿开始日期')
    end_date = Column(DateTime, nullable=False, comment='留宿结束日期')
    status = Column(Integer, default=0, comment='状态: 0-待审批 1-已批准 2-已拒绝 3-已过期 4-已取消')
    approve_by = Column(String(50), comment='审批人')
    approve_time = Column(DateTime, comment='审批时间')
    approve_remark = Column(String(200), comment='审批备注')
    cjsj = Column(DateTime, default=datetime.now, comment='申请时间')
    gxsj = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    def __repr__(self):
        return f'<ZzSsLs {self.xs_xm} {self.start_date}-{self.end_date}>'


class SituationPolicyScore(Base):
    """形势与政策成绩表"""
    __tablename__ = 'kw_xsyzc'

    id = Column(Integer, primary_key=True, autoincrement=True)
    xh = Column(String(20), comment='学号')
    xm = Column(String(20), comment='姓名')
    xxzx = Column(String(50), comment='学习中心')
    rxnd = Column(String(20), comment='入学年度')
    cc = Column(String(10), comment='层次')
    sjh = Column(String(10), comment='试卷号')
    cj = Column(String(10), comment='成绩')
    kspc = Column(String(10), comment='考试批次')
    pc = Column(Integer, comment='批次')

    def __repr__(self):
        return f"<SituationPolicyScore(id={self.id}, xh={self.xh})>"


class ExamTmZj(Base):
    """考试题目组卷表（主观题题干和参考答案）"""
    __tablename__ = 'exam_tm_zj'

    id = Column(Integer, primary_key=True, autoincrement=True)
    lx_id = Column(Integer, comment='类型ID')
    exam_kc_id = Column(Integer, comment='考试课程ID')
    sj_id = Column(Integer, comment='试卷ID')
    tx = Column(String(50), comment='题型')
    tg = Column(Text, comment='题干')
    da = Column(String(200), comment='参考答案')
    xxA = Column(String(200), comment='选项A')
    xxB = Column(String(200), comment='选项B')
    xxC = Column(String(200), comment='选项C')
    xxD = Column(String(200), comment='选项D')
    t_id = Column(Integer, comment='出题教师ID')
    fz = Column(Integer, comment='分值')

    def __repr__(self):
        return f'<ExamTmZj {self.id}>'


class FeedbackTicket(Base):
    """校园问题反馈工单表。

    2026-09-28 方案 C：双列独立存储地点信息（一次性解决）。
    - location_dict_text：仅 chip 拼接的字典原值序列，"|"分隔 → 精确 token 筛选
    - location_user_text：仅用户备注（自由文本）→ 单列 LIKE
    - location_text     ：合并展示串（list|" · "|+note，仅展示用，不参与搜索）
    """
    __tablename__ = 'hp_feedback_ticket'

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_no = Column(String(32), index=True, comment='工单号')
    category = Column(String(20), comment='repair维修 / suggestion意见建议')
    content = Column(Text)
    # 2026-09-28 方案 C：地点拆两列分别存储，第三方展示合并到 location_text。
    location_text = Column(String(500), nullable=True, index=True,
                           comment='地点-展示合并串（仅展示，不参与搜索）')
    location_dict_text = Column(String(500), nullable=True, index=True,
                                comment='地点-列表段（仅 chip 拼接字典原值，"|"分隔，用于 token 精确匹配）')
    location_user_text = Column(String(500), nullable=True, index=True,
                                comment='地点-备注段（仅用户手写，自由文本，用于 LIKE 模糊搜索）')
    repair_type_text = Column(String(64), nullable=True, index=True,
                              comment='维修类型自由文本（用户输入/字典选中，模糊搜索用）')
    images = Column(Text, comment='JSON数组,反馈附图相对路径')
    urgency = Column(String(10), default='normal', comment='normal/urgent')
    is_anonymous = Column(Integer, default=0, comment='是否匿名 0/1')

    reporter_user_type = Column(String(30), index=True, comment='open_student/vocational_student/open_teacher/vocational_teacher')
    reporter_id = Column(String(50), index=True, comment='学号或工号')
    reporter_name = Column(String(50))
    reporter_phone = Column(String(20))
    reporter_dept = Column(String(50), comment='班级或部门')

    status = Column(String(20), default='pending', index=True, comment='pending/processing/done/rejected/cancelled')
    handle_remark = Column(Text, comment='处理意见')
    handle_images = Column(Text, comment='JSON数组,处理后照片')
    handle_at = Column(DateTime)
    handler_name = Column(String(50))
    handler_phone = Column(String(20))
    sms_cpSubID = Column(String(50), comment='办结通知短信任务ID')
    reject_reason = Column(String(500))

    is_deleted = Column(Integer, default=0, index=True, comment='软删除:0未删除 1已删除')
    deleted_at = Column(DateTime, comment='删除时间')
    deleted_by = Column(String(50), comment='删除操作人姓名')

    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self):
        return f'<FeedbackTicket {self.ticket_no} {self.status}>'


class FeedbackTimeline(Base):
    """反馈工单时间线"""
    __tablename__ = 'hp_feedback_timeline'

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_id = Column(Integer, index=True)
    action = Column(String(20), comment='submit/process/done/reject/cancel/comment')
    operator_name = Column(String(50))
    operator_phone = Column(String(20))
    remark = Column(Text)
    created_at = Column(DateTime, default=datetime.now)

    def __repr__(self):
        return f'<FeedbackTimeline ticket={self.ticket_id} action={self.action}>'


# ============================================================
# 校园反馈相关 - 工作人员、字典、管理员
# ============================================================

class Staff(Base):
    """工作人员表（保洁、维修、保卫、食堂等非教师/学生岗位）

    用途：校园反馈模块的"工作人员"身份来源，可作为反馈提交人，也可被授权为反馈管理员/处理者。
    """
    __tablename__ = 'hp_staff'

    id          = Column(Integer, primary_key=True, autoincrement=True)
    name        = Column(String(64), nullable=False, index=True, comment='姓名')
    phone       = Column(String(11), nullable=False, index=True, comment='手机号（登录用）')
    department  = Column(String(64), comment='部门：后勤科 / 保卫科 / 校办 / 食堂...')
    position    = Column(String(64), comment='岗位：维修工 / 保洁 / 司机 / 厨师...')
    id_card     = Column(String(18), comment='身份证号（可空）')
    status      = Column(String(8), default='active', index=True, comment='active / inactive')
    note        = Column(String(255), comment='备注')
    created_at  = Column(DateTime, default=datetime.now)
    updated_at  = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self):
        return f'<Staff {self.name}-{self.phone}>'


class FeedbackDict(Base):
    """反馈字典表（场景 / 物品类型 / 后期可加紧急程度等）

    category + code 组合唯一。前端按 category 拉取列表后渲染 chip。
    is_custom=True 的项前端选中后会弹自定义输入框（兜底"其他"）。
    """
    __tablename__ = 'hp_feedback_dict'

    id              = Column(Integer, primary_key=True, autoincrement=True)
    category        = Column(String(32), nullable=False, index=True,
                             comment="字典类目：'scene' 场景 / 'item' 物品类型 / 'repair_type' 维修类型")
    code            = Column(String(32), nullable=False, comment='业务编码：canteen/meal/...')
    label           = Column(String(64), nullable=False, comment='展示文案：食堂 / 饭菜质量')
    icon            = Column(String(64), comment='前端图标 key（可空）')
    sort_order      = Column(Integer, default=0, index=True, comment='排序，小的在前')
    is_active       = Column(Boolean, default=True, index=True, comment='是否启用')
    is_custom       = Column(Boolean, default=False,
                             comment='True 表示"其他"兜底项，前端选中后弹输入框')
    feedback_type   = Column(String(16), default='both',
                             comment="该选项适用于哪类反馈：'repair' 仅维修 / 'suggestion' 仅意见 / 'both' 通用")
    extra_data      = Column(Text, comment='扩展数据 JSON 字符串（如维修类型的工种分组：{"group":"水管类"}）')
    created_at      = Column(DateTime, default=datetime.now)
    updated_at      = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        UniqueConstraint('category', 'code', name='uq_feedback_dict_cat_code'),
        Index('ix_feedback_dict_cat_active_order', 'category', 'is_active', 'sort_order'),
    )

    def __repr__(self):
        return f'<FeedbackDict {self.category}:{self.code} {self.label}>'



class FeedbackAdmin(Base):
    """反馈管理员表（取代硬编码白名单 feedback_admin_whitelist.py）

    通过 user_type + user_ref_id 多态绑定到 4 个用户表（staff/teacher/student）；
    phone_snapshot / name_snapshot 为冗余快照，登录时按手机号一次定位身份与角色，
    避免跨 5 张用户表 JOIN。

    role 取值：
      super   - 系统管理员（可增删其他管理员；本期暂未实现 UI，由另一项目维护此表）
      manager - 后勤负责人 / 分管校长（看全部 + 办结 + 转派 + 驳回 + 删除）
      handler - 执行者（仅看自己被指派 / 自己 scope_codes 内的工单 + 办结）
      viewer  - 只读（仅查看，常用于上级巡查）
    """
    __tablename__ = 'hp_feedback_admin'

    id              = Column(Integer, primary_key=True, autoincrement=True)

    user_type       = Column(String(20), nullable=False,
                             comment='staff / open_teacher / vocational_teacher / open_student / vocational_student')
    user_ref_id     = Column(String(50), nullable=False, comment='对应用户表主键的字符串形式')

    phone_snapshot  = Column(String(11), nullable=False, index=True, comment='冗余手机号，快速定位')
    name_snapshot   = Column(String(64), comment='冗余姓名')

    role            = Column(String(16), nullable=False, default='handler',
                             comment='super / manager / handler / viewer')
    department      = Column(String(64), comment='部门（可空，用于按部门转派）')
    scope_codes     = Column(String(255),
                             comment="handler 限定可处理的字典 code，逗号分隔。如 'canteen,shop'；空表示无限制")

    is_active            = Column(Boolean, default=True, index=True)
    can_view_suggestion  = Column(Boolean, default=False,
                                  comment='是否允许查看"意见建议"类工单，默认 False')
    created_by      = Column(Integer, comment='添加者的 FeedbackAdmin.id')
    created_at      = Column(DateTime, default=datetime.now)
    updated_at      = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    note            = Column(String(255))

    __table_args__ = (
        UniqueConstraint('user_type', 'user_ref_id', name='uq_feedback_admin_user'),
        Index('ix_feedback_admin_phone_active', 'phone_snapshot', 'is_active'),
    )

    def __repr__(self):
        return f'<FeedbackAdmin {self.user_type}:{self.user_ref_id} role={self.role}>'


class FeedbackLocation(Base):
    """反馈地点字典表（树形三级：楼栋 → 楼层 → 房间）

    三级级联：parent_id=NULL 表示楼栋（如教学楼A），level=1；
              parent_id=楼栋ID 表示楼层，level=2；
              parent_id=楼层ID 表示房间，level=3。

    full_path 字段冗余完整路径（如 "教学楼A/3楼/301教室"），避免前端展示需要拼接。
    """
    __tablename__ = 'hp_feedback_location'

    id          = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    parent_id   = Column(Integer, nullable=True, index=True, comment='上级地点ID（自引用）')
    code        = Column(String(64), nullable=False, comment='业务编码')
    name        = Column(String(64), nullable=False, comment='地点名称')
    level       = Column(Integer, nullable=False, comment='1=楼栋 2=楼层 3=房间')
    full_path   = Column(String(255), nullable=False, comment='冗余完整路径（如：教学楼A/3楼/301教室）')
    # 2026-09-27：新增 type_code 用于按任意地点类型聚合（楼栋/楼层/房间号/区域...）。
    # 老节点默认 '地点'，新节点可指定业务类型。
    type_code   = Column(String(32), nullable=True, index=True, comment='地点类型（楼栋/楼层/房间号/区域等）')
    sort_order  = Column(Integer, default=0, index=True, comment='排序')
    is_active   = Column(Boolean, default=True, index=True, comment='是否启用')
    created_at  = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at  = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    __table_args__ = (
        UniqueConstraint('parent_id', 'code', name='uq_feedback_loc_parent_code'),
    )

    def __repr__(self):
        return f'<FeedbackLocation {self.level}L: {self.full_path}>'


class FeedbackLocationType(Base):
    """反馈地点类型（独立排序表，2026-09-29）

    业务说明：
      原方案把"地点类型"用 type_code 字符串扁平化在 hp_feedback_location，
      类型的整体排序借用"该 type 下最小 sort_order"，管理页无法直接调整。
      现把类型的排序字段独立出来：(type_code, sort_order) 一一对应。
    """
    __tablename__ = 'hp_feedback_location_type'

    type_code   = Column(String(64), primary_key=True, comment='地点类型编码')
    sort_order  = Column(Integer, nullable=False, default=0, index=True, comment='类型排序')
    created_at  = Column(DateTime, default=datetime.now)
    updated_at  = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self):
        return f'<FeedbackLocationType {self.type_code} sort={self.sort_order}>'





# 中高职贯通专业表


class ZzBmxs(Base):
    """招生报名学生表"""
    __tablename__ = 'zz_bmxs'
    __table_args__ = {'implicit_returning': False}

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    xm = Column(String(50), comment='姓名')
    xb = Column(String(50), comment='性别')
    mz = Column(String(50), comment='民族')
    zzmm = Column(Integer, comment='政治面貌')
    sfzh = Column(String(50), comment='身份证号')
    xsdh = Column(String(50), comment='学生电话')
    jtxxdz = Column(String(100), comment='家庭详细地址')
    jzdlx = Column(Integer, comment='居住地类型')
    hkxz = Column(String(50), comment='户口性质')
    jzxm = Column(String(50), comment='家长姓名')
    jzgx = Column(Integer, comment='家长关系')
    jzdh = Column(String(50), comment='家长电话')
    bdzy = Column(Integer, comment='报读专业')
    byxxssx1 = Column(String(50), comment='毕业学校省市县1')
    byxxssx2 = Column(String(50), comment='毕业学校省市县2')
    byxxssx3 = Column(String(50), comment='毕业学校省市县3')
    byxxmc = Column(String(100), comment='毕业学校名称')
    zsdx = Column(Integer, comment='招生对象')
    sfjdlk = Column(Integer, comment='是否建档立卡')
    sflset = Column(Integer, comment='是否留守儿童')
    sftwjrzn = Column(Integer, comment='是否退役军人子女')
    xsly = Column(String(50), comment='学生来源')
    qd = Column(Integer, comment='渠道')
    qdjs = Column(String(50), comment='渠道介绍')
    pc = Column(Integer, comment='批次')
    tjsj = Column(DateTime, comment='提交时间')
    sfqdxf = Column(Integer, nullable=True, comment='是否购买校服：1-是 0-否')

    # 查询码
    query_code = Column(String(20), unique=True, comment='8位查询码，用于用户查看/修改报名信息')
    query_code_expire = Column(DateTime, comment='查询码过期时间')

    # 拼音首字母（移动端搜索用）
    pinyin_initial = Column(String(100), nullable=True, comment='姓名拼音首字母')
    # 备注
    remark = Column(String(500), nullable=True, comment='备注')
    # 报名完成标志：0=草稿（仅填写身份证/电话，未完善全部信息）1=已完成
    is_complete = Column(Integer, nullable=False, default=0, comment='报名完成标志：0-草稿 1-已完成')

    def __repr__(self):
        return f'<ZzBmxs {self.xm}>'


class LwFeatureSwitch(Base):
    """首页核心功能开关表"""
    __tablename__ = 'lw_feature_switch'
    __table_args__ = {'implicit_returning': False}

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    code = Column(String(50), unique=True, nullable=False, comment='功能编码（唯一标识）')
    name = Column(String(100), nullable=False, comment='功能名称')
    is_enabled = Column(Integer, nullable=False, default=1, comment='开关状态：1=开启 0=关闭')
    sort_order = Column(Integer, nullable=False, default=0, comment='排序号')
    remark = Column(String(500), nullable=True, comment='备注说明')
    tip_message = Column(String(500), nullable=True, comment='关闭时前端展示的提示词')
    created_at = Column(DateTime, nullable=False, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    def __repr__(self):
        return f'<LwFeatureSwitch {self.code}={self.is_enabled}>'


class LwConfig(Base):
    """系统配置表"""
    __tablename__ = 'lw_config'
    __table_args__ = {'implicit_returning': False}

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    key = Column(String(100), unique=True, nullable=False, comment='配置键（唯一标识）')
    value = Column(String(4000), nullable=True, comment='配置值')
    description = Column(String(500), nullable=True, comment='配置描述说明')
    category = Column(String(50), nullable=True, default='general', comment='配置分类')
    is_enabled = Column(Integer, nullable=False, default=1, comment='是否启用：1=启用 0=禁用')
    sort_order = Column(Integer, nullable=False, default=0, comment='排序号')
    created_at = Column(DateTime, nullable=False, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    def __repr__(self):
        return f'<LwConfig {self.key}={self.value}>'


class ZzBmxsJzdlx(Base):
    """招生报名学生居住地类型表"""
    __tablename__ = 'zz_bmxs_jzdlx'
    __table_args__ = {'implicit_returning': False}

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    mc = Column(String(50), comment='名称')
    px = Column(Integer, comment='排序')
    yc = Column(Integer, comment='隐藏')

    def __repr__(self):
        return f'<ZzBmxsJzdlx {self.mc}>'


class ZzBmxsJzgx(Base):
    """招生报名学生家长关系表"""
    __tablename__ = 'zz_bmxs_jzgx'
    __table_args__ = {'implicit_returning': False}

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    mc = Column(String(50), comment='名称')
    px = Column(Integer, comment='排序')
    yc = Column(Integer, comment='隐藏')

    def __repr__(self):
        return f'<ZzBmxsJzgx {self.mc}>'


class ZzBmxsQd(Base):
    """招生报名学生渠道表"""
    __tablename__ = 'zz_bmxs_qd'
    __table_args__ = {'implicit_returning': False}

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    mc = Column(String(100), comment='名称')
    px = Column(Integer, comment='排序')
    yc = Column(Integer, comment='隐藏')

    def __repr__(self):
        return f'<ZzBmxsQd {self.mc}>'


class ZzBmxsXx(Base):
    """招生报名学生学校表"""
    __tablename__ = 'zz_bmxs_xx'
    __table_args__ = {'implicit_returning': False}

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    xy = Column(String(100), comment='学院')
    px = Column(Integer, comment='排序')
    yc = Column(Integer, comment='隐藏')

    def __repr__(self):
        return f'<ZzBmxsXx {self.xy}>'


class ZzBmxsZsdx(Base):
    """招生报名学生招生对象表"""
    __tablename__ = 'zz_bmxs_zsdx'
    __table_args__ = {'implicit_returning': False}

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    mc = Column(String(50), comment='名称')
    px = Column(Integer, comment='排序')
    yc = Column(Integer, comment='隐藏')

    def __repr__(self):
        return f'<ZzBmxsZsdx {self.mc}>'


class ZzBmxsZzmm(Base):
    """招生报名学生政治面貌表"""
    __tablename__ = 'zz_bmxs_zzmm'
    __table_args__ = {'implicit_returning': False}

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    mc = Column(String(50), comment='名称')
    px = Column(Integer, comment='排序')
    yc = Column(Integer, comment='隐藏')

    def __repr__(self):
        return f'<ZzBmxsZzmm {self.mc}>'


class ZzBmxsBdzy(Base):
    """招生报名学生报读专业表"""
    __tablename__ = 'zz_bmxs_bdzy'
    __table_args__ = {'implicit_returning': False}

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    mc = Column(String(50), comment='名称')
    px = Column(Integer, comment='排序')
    yc = Column(Integer, comment='隐藏')
    zs = Column(Integer, comment='是否展示')
    zsf = Column(Integer, comment='住宿费')
    sf = Column(Integer, comment='书费')
    xx_id = Column(Integer, comment='学校ID')
    bz = Column(String(50), comment='备注')
    zsme = Column(Integer, comment='招生名额')
    bmrs = Column(Integer, comment='报名人数')

    def __repr__(self):
        return f'<ZzBmxsBdzy {self.mc}>'


class ZzBmxsLocalMajor(Base):
    """招生报名本校专业表"""
    __tablename__ = 'zz_bmxs_local_major'
    __table_args__ = {'implicit_returning': False}

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    major_name = Column(String(50), nullable=False, comment='专业名称')
    major_number = Column(String(50), nullable=False, comment='专业代码')
    pc = Column(Integer, nullable=False, comment='批次')
    zsf = Column(Integer, comment='住宿费')
    xf = Column(Integer, comment='学费')
    sf = Column(Integer, comment='书费')
    zs = Column(Integer, comment='是否展示')

    def __repr__(self):
        return f'<ZzBmxsLocalMajor {self.major_name}>'


class ZzDianbiaoMeter(Base):
    """电表（迁移自 chongzhi.meters）

    字段结构与 chongzhi 项目保持一致；二维码以 sn.png 形式存放于 MinIO
    私有桶 guizhou-zhpt-prod-private 的 /dianbiao/ 子目录下，由后端做 Sig V4
    预签名后供前端直接访问。
    """
    __tablename__ = 'zz_dianbiao_meters'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID（自增，与 chongzhi 同源）')
    device_id = Column(Integer, unique=True, nullable=False, index=True, comment='管家婆 device_id')
    sn = Column(String(64), unique=True, nullable=False, index=True, comment='电表 SN（MinIO 二维码文件名 <sn>.png）')
    mac = Column(String(64), nullable=True, comment='电表 MAC')
    house_id = Column(Integer, nullable=False, index=True, comment='管家婆 house_id')

    estate_name = Column(String(128), nullable=True, comment='校区/宿舍区名称')
    building = Column(String(64), nullable=True, comment='楼栋')
    house_name = Column(String(64), nullable=True, index=True, comment='宿舍/房间号（完全匹配键）')
    full_name = Column(String(255), nullable=True, comment='完整名称')

    tenant_name = Column(String(64), nullable=True, comment='租户/住户姓名')
    status = Column(String(32), nullable=True, comment='状态：occupied / vacant 等')

    resident_count = Column(Integer, nullable=False, default=0, comment='入住人数')

    price = Column(String(16), nullable=True, comment='当前电价')
    basic_price = Column(String(16), nullable=True, comment='基础电价')
    du = Column(String(32), nullable=True, comment='剩余度数')
    total = Column(String(32), nullable=True, comment='累计总用电量(度)')
    total_money = Column(String(32), nullable=True, comment='累计总充值金额(元)')
    total_recharge = Column(Integer, nullable=True, comment='累计充值次数')

    online_status = Column(Integer, nullable=True, comment='在线状态')
    is_disabled = Column(Integer, nullable=True, comment='是否停用')
    recharge_disabled = Column(Integer, nullable=True, comment='是否禁用充值')
    expired_at = Column(DateTime, nullable=True, comment='到期时间')
    month_limit = Column(String(32), nullable=True, comment='月度额度')
    month_recharge = Column(String(32), nullable=True, comment='月度已充值')
    qrcode = Column(String(255), nullable=True, comment='二维码源 URL（chongzhi 留底）')

    raw = Column(Text, nullable=True, comment='原始 raw JSON（迁移自 chongzhi）')
    remote_synced_at = Column(DateTime, nullable=True, comment='管家婆最近同步时间')

    created_at = Column(DateTime, default=datetime.now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')

    def __repr__(self):
        return f'<ZzDianbiaoMeter {self.sn} - {self.house_name}>'


class OaXsBookPickup(Base):
    """开放教育学生新书领取登记表

    每个学期统计一次，批次(pc)取自 lw_sys.sys_pc，后端实时查询不信任 token。
    同一 (xs_xh, pc) 只保留一条记录，重复提交为 UPDATE，支持随时修改。

    领取方式 pickup_type 为英文语义字符串枚举：
    - self_pickup: 到校领取(需填写 pickup_date，格式 YYYY-MM-DD)
    - mail: 邮寄(需填写收件人 receiver_name / 电话 receiver_phone /
      省市区 province/city/district / 详细地址 detail_addr)
    """
    __tablename__ = 'oa_xs_book_pickup'
    __table_args__ = (
        UniqueConstraint('xs_xh', 'pc', name='uq_book_pickup_xh_pc'),
        Index('ix_book_pickup_xh_pc', 'xs_xh', 'pc'),
        {'implicit_returning': False},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    xs_xh = Column(String(20), nullable=False, comment='学号')
    xs_xm = Column(String(20), comment='姓名(冗余)')
    xs_bj_id = Column(Integer, comment='班级ID(冗余，方便按班统计)')
    pc = Column(Integer, nullable=False, comment='批次，取自 lw_sys.sys_pc')
    pickup_type = Column(String(16), nullable=False, comment='领取方式: self_pickup-到校领取 / mail-邮寄')
    pickup_date = Column(String(20), comment='到校领取日期 YYYY-MM-DD (self_pickup时必填)')
    receiver_name = Column(String(20), comment='收件人姓名 (mail时必填)')
    receiver_phone = Column(String(15), comment='收件人电话 (mail时必填)')
    province = Column(String(50), comment='省 (mail时必填)')
    city = Column(String(50), comment='市 (mail时必填)')
    district = Column(String(50), comment='区/县 (mail时必填)')
    detail_addr = Column(String(200), comment='详细地址 (mail时必填)')
    addtime = Column(DateTime, default=datetime.now, comment='创建时间')
    updatetime = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='最后修改时间')

    def __repr__(self):
        return f'<OaXsBookPickup {self.xs_xh} pc={self.pc} type={self.pickup_type}>'


# ============================================================
# 心理咨询预约模块（纯预约制，不做叫号）
# 规则锁定：
#  - 每个号段（slot）可指定「咨询日期 + 诊疗地点」，同一场次可排不同日期/地点
#  - 预约号（slot_seq 段内序号 / display_no）即真实诊疗顺序，按预约先后生成
#  - 不签到、不叫号、不排队；预约后不来，默认视为未到（cancelled）
#  - 唯一约束：同一号段同一学生只允许一条「有效预约」（cancelled 不占用）
# ============================================================


class ZzCounselSchedule(Base):
    """心理咨询场次（老师发布的一次咨询活动，可跨多天/多地点）"""
    __tablename__ = 'zz_counsel_schedule'
    __table_args__ = {'implicit_returning': False}

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    title = Column(String(100), nullable=False, comment='场次标题，如11-13下午咨询')
    counsel_date = Column(DateTime, comment='咨询日期（场次默认日期）')
    counselor_t_id = Column(Integer, comment='咨询老师ID')
    counselor_name = Column(String(20), comment='咨询老师姓名（冗余）')
    status = Column(String(16), default='draft', comment='draft草稿/published已发布/finished已结束/cancelled取消')
    create_time = Column(DateTime, default=datetime.now, comment='创建时间')
    update_time = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    def __repr__(self):
        return f'<ZzCounselSchedule {self.id}-{self.title}>'


class ZzCounselSlot(Base):
    """心理咨询号段（分时段排号；日期与诊疗地点均可在号段级自定义）"""
    __tablename__ = 'zz_counsel_slot'
    __table_args__ = {'implicit_returning': False}

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    schedule_id = Column(Integer, nullable=False, index=True, comment='场次ID')
    sort_order = Column(Integer, default=0, comment='排序')
    slot_tag = Column(String(4), comment='段标签A/B/C')
    counsel_date = Column(DateTime, comment='该号段的咨询日期（控制排某天）')
    start_time = Column(DateTime, nullable=False, comment='开始时间（完整日期时间）')
    end_time = Column(DateTime, nullable=False, comment='结束时间（完整日期时间）')
    quota = Column(Integer, nullable=False, comment='本段号源数')
    category = Column(String(50), comment='咨询项目类别（教师自行填写）')
    location = Column(String(100), comment='诊疗地点（号段级自定义，如实训2栋301）')
    status = Column(String(16), default='open', comment='open可约/full已满/closed已结束')

    def __repr__(self):
        return f'<ZzCounselSlot {self.schedule_id}-{self.slot_tag}>'


class ZzCounselBooking(Base):
    """心理咨询预约单（一人一号）

    唯一约束说明：
    同一号段内 booked（待就诊）+ attended（已到诊/已访谈）均占位，
    不可重复预约同段（由 /book 前置检查拦截并给友好提示）；
    不同号段重约不受该索引影响（slot_id 不同）。
    因此 filtered unique index 对「未取消 + 真实学号」生效：
      WHERE status <> 'cancelled' AND xh <> ''
    幂等：建索引前先清理同一 (slot_id, xh) 的多条 booked。
    """
    __tablename__ = 'zz_counsel_booking'
    __table_args__ = (
        Index('ix_counsel_sched_status', 'schedule_id', 'status'),
        Index('ix_counsel_slot_seq', 'slot_id', 'status', 'slot_seq'),
        Index('uq_counsel_slot_xh_active', 'slot_id', 'xh', unique=True,
              mssql_where=text("status <> 'cancelled' AND xh <> ''"),
              sqlite_where=text("status <> 'cancelled' AND xh <> ''")),
        {'implicit_returning': False},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    schedule_id = Column(Integer, nullable=False, index=True, comment='场次ID')
    slot_id = Column(Integer, nullable=False, index=True, comment='号段ID')
    xs_id = Column(Integer, comment='学生ID')
    xh = Column(String(20), comment='学号')
    xm = Column(String(20), comment='姓名（冗余）')
    bj_id = Column(Integer, comment='班级ID（冗余）')
    bj_mc = Column(String(50), comment='班级名称（冗余）')
    xsdh = Column(String(15), comment='学生电话快照')
    ticket_no = Column(Integer, comment='全场号1..N')
    slot_seq = Column(Integer, comment='段内号（即真实诊疗顺序）')
    slot_tag = Column(String(4), comment='段标签快照')
    display_no = Column(String(10), comment='展示号如A01（严格匿名，只显示代号）')
    category = Column(String(50), comment='咨询项目类别快照')
    phone_suffix = Column(String(4), comment='手机后4位（选填，个人核对用）')
    room_name = Column(String(100), comment='诊疗地点快照（号段级地点）')
    status = Column(String(16), default='booked', comment='booked已预约/attended已到诊/cancelled未到取消')
    book_time = Column(DateTime, default=datetime.now, comment='预约时间')
    remark = Column(Text, comment='老师备注（学生不可见）')
    create_time = Column(DateTime, default=datetime.now, comment='创建时间')
    update_time = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    def __repr__(self):
        return f'<ZzCounselBooking {self.display_no} {self.xm} {self.status}>'



