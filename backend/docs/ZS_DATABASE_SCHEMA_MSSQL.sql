-- ==================== 招生报名系统数据库表结构 (SQL Server) ====================
-- 创建时间: 2025-03-13
-- 说明: 用于成人高考和"3+4"中本贯通等招生报名管理
-- 数据库: Microsoft SQL Server

-- 1. 招生类别表
IF OBJECT_ID('zs_category', 'U') IS NOT NULL
    DROP TABLE zs_category;
GO

CREATE TABLE zs_category (
    id INT IDENTITY(1,1) NOT NULL,
    code VARCHAR(50) NOT NULL,
    name NVARCHAR(100) NOT NULL,
    description NVARCHAR(MAX),
    prospectus NVARCHAR(MAX),
    sort_order INT DEFAULT 0,
    is_active INT DEFAULT 1,
    start_time DATETIME,
    end_time DATETIME,
    batch INT,
    create_time DATETIME DEFAULT GETDATE(),
    update_time DATETIME DEFAULT GETDATE(),
    CONSTRAINT PK_zs_category PRIMARY KEY (id),
    CONSTRAINT UK_zs_category_code UNIQUE (code)
);
GO

-- 创建索引
CREATE INDEX idx_zs_category_is_active ON zs_category(is_active);
CREATE INDEX idx_zs_category_sort_order ON zs_category(sort_order);
GO

-- 创建更新时间触发器
CREATE TRIGGER trg_zs_category_update
ON zs_category
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE zs_category
    SET update_time = GETDATE()
    FROM zs_category c
    INNER JOIN inserted i ON c.id = i.id;
END;
GO

-- 2. 招生通用字典表
IF OBJECT_ID('zs_dict', 'U') IS NOT NULL
    DROP TABLE zs_dict;
GO

CREATE TABLE zs_dict (
    id INT IDENTITY(1,1) NOT NULL,
    category_id INT NOT NULL,
    type VARCHAR(50) NOT NULL,
    code VARCHAR(50) NOT NULL,
    label NVARCHAR(100) NOT NULL,
    parent_code VARCHAR(50),
    sort_order INT DEFAULT 0,
    is_active INT DEFAULT 1,
    remark NVARCHAR(500),
    extra_data NVARCHAR(MAX),
    create_time DATETIME DEFAULT GETDATE(),
    update_time DATETIME DEFAULT GETDATE(),
    CONSTRAINT PK_zs_dict PRIMARY KEY (id),
    CONSTRAINT UK_zs_dict_category_type_code UNIQUE (category_id, type, code),
    CONSTRAINT FK_zs_dict_category FOREIGN KEY (category_id) REFERENCES zs_category(id) ON DELETE CASCADE
);
GO

-- 创建索引
CREATE INDEX idx_zs_dict_category_id ON zs_dict(category_id);
CREATE INDEX idx_zs_dict_type ON zs_dict(type);
CREATE INDEX idx_zs_dict_parent_code ON zs_dict(parent_code);
CREATE INDEX idx_zs_dict_is_active ON zs_dict(is_active);
GO

-- 创建更新时间触发器
CREATE TRIGGER trg_zs_dict_update
ON zs_dict
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE zs_dict
    SET update_time = GETDATE()
    FROM zs_dict d
    INNER JOIN inserted i ON d.id = i.id;
END;
GO

-- 3. 成人高等教育预报名表
IF OBJECT_ID('zs_adult_enrollment', 'U') IS NOT NULL
    DROP TABLE zs_adult_enrollment;
GO

CREATE TABLE zs_adult_enrollment (
    id INT IDENTITY(1,1) NOT NULL,
    
    -- 1. 姓名（必填）
    name NVARCHAR(50) NOT NULL,
    
    -- 2. 手机号（必填）
    phone VARCHAR(20) NOT NULL,
    
    -- 3. 意向专业及费用明细（必选）
    major_code VARCHAR(50) NOT NULL,
    
    -- 4. 选择入学后的学习中心（必选）
    learning_center_code VARCHAR(50) NOT NULL,
    
    -- 状态信息
    status INT DEFAULT 0,
    batch INT,
    submit_time DATETIME DEFAULT GETDATE(),
    audit_time DATETIME,
    auditor_id INT,
    audit_remark NVARCHAR(500),
    
    -- 微信信息
    wx_openid VARCHAR(100),
    wx_nickname NVARCHAR(100),
    wx_headimgurl VARCHAR(500),
    
    -- 时间戳
    create_time DATETIME DEFAULT GETDATE(),
    update_time DATETIME DEFAULT GETDATE(),
    
    CONSTRAINT PK_zs_adult_enrollment PRIMARY KEY (id)
);
GO

-- 创建索引
CREATE INDEX idx_zs_adult_phone ON zs_adult_enrollment(phone);
CREATE INDEX idx_zs_adult_major_code ON zs_adult_enrollment(major_code);
CREATE INDEX idx_zs_adult_learning_center ON zs_adult_enrollment(learning_center_code);
CREATE INDEX idx_zs_adult_status ON zs_adult_enrollment(status);
CREATE INDEX idx_zs_adult_batch ON zs_adult_enrollment(batch);
CREATE INDEX idx_zs_adult_wx_openid ON zs_adult_enrollment(wx_openid);
CREATE INDEX idx_zs_adult_submit_time ON zs_adult_enrollment(submit_time);
GO

-- 创建更新时间触发器
CREATE TRIGGER trg_zs_adult_enrollment_update
ON zs_adult_enrollment
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE zs_adult_enrollment
    SET update_time = GETDATE()
    FROM zs_adult_enrollment e
    INNER JOIN inserted i ON e.id = i.id;
END;
GO

-- 4. 3+4中本贯通舞蹈表演专业面试考生报名表
IF OBJECT_ID('zs_vocational34_enrollment', 'U') IS NOT NULL
    DROP TABLE zs_vocational34_enrollment;
GO

CREATE TABLE zs_vocational34_enrollment (
    id INT IDENTITY(1,1) NOT NULL,
    
    -- 1. 序号（自动生成）
    serial_number VARCHAR(20),
    
    -- 2. 考生基本信息
    name NVARCHAR(50) NOT NULL,
    admission_ticket_no VARCHAR(50),
    gender VARCHAR(20) NOT NULL,
    nation VARCHAR(50),
    id_card VARCHAR(18) NOT NULL,
    junior_school_name NVARCHAR(100),
    junior_school_county NVARCHAR(100),
    is_qdn_graduate INT,
    
    -- 3. 籍贯信息
    household_type VARCHAR(50),
    household_province VARCHAR(50),
    household_city VARCHAR(50),
    household_district VARCHAR(50),
    household_address NVARCHAR(200),
    residence_province VARCHAR(50),
    residence_city VARCHAR(50),
    residence_district VARCHAR(50),
    residence_address NVARCHAR(200),
    
    -- 4. 手机号
    phone VARCHAR(20) NOT NULL,
    
    -- 5. 监护人信息
    guardian_name NVARCHAR(50),
    guardian_phone VARCHAR(20),
    guardian_relation VARCHAR(50),
    
    -- 6-9. 上传文件
    id_card_front_url VARCHAR(500),
    id_card_back_url VARCHAR(500),
    photo_url VARCHAR(500),
    consent_letter_url VARCHAR(500),
    
    -- 10. 知情确认
    is_confirmed INT DEFAULT 0,
    
    -- 11. 考生签名
    signature_url VARCHAR(500),
    
    -- 状态信息
    status INT DEFAULT 0,
    batch INT,
    submit_time DATETIME DEFAULT GETDATE(),
    audit_time DATETIME,
    auditor_id INT,
    audit_remark NVARCHAR(500),
    
    -- 微信信息
    wx_openid VARCHAR(100),
    wx_nickname NVARCHAR(100),
    wx_headimgurl VARCHAR(500),
    
    -- 时间戳
    create_time DATETIME DEFAULT GETDATE(),
    update_time DATETIME DEFAULT GETDATE(),
    
    CONSTRAINT PK_zs_vocational34_enrollment PRIMARY KEY (id),
    CONSTRAINT UK_zs_vocational34_id_card UNIQUE (id_card)
);
GO

-- 创建索引
CREATE INDEX idx_zs_vocational34_phone ON zs_vocational34_enrollment(phone);
CREATE INDEX idx_zs_vocational34_name ON zs_vocational34_enrollment(name);
CREATE INDEX idx_zs_vocational34_status ON zs_vocational34_enrollment(status);
CREATE INDEX idx_zs_vocational34_batch ON zs_vocational34_enrollment(batch);
CREATE INDEX idx_zs_vocational34_wx_openid ON zs_vocational34_enrollment(wx_openid);
CREATE INDEX idx_zs_vocational34_submit_time ON zs_vocational34_enrollment(submit_time);
GO

-- 创建更新时间触发器
CREATE TRIGGER trg_zs_vocational34_enrollment_update
ON zs_vocational34_enrollment
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE zs_vocational34_enrollment
    SET update_time = GETDATE()
    FROM zs_vocational34_enrollment e
    INNER JOIN inserted i ON e.id = i.id;
END;
GO

-- ==================== 初始化数据 ====================

-- 插入招生类别初始数据
INSERT INTO zs_category (code, name, description, prospectus, sort_order, is_active, batch) VALUES
(N'adult_exam', N'成人高等教育2025年预报名', N'成人高等教育招生', N'<h2>成人高等教育2025年预报名招生简章</h2><p>欢迎报考成人高等教育...</p>', 1, 1, 1),
(N'vocational_34', N'3+4中本贯通舞蹈表演专业', N'中职与本科贯通培养舞蹈表演专业', N'<h2>3+4中本贯通舞蹈表演专业招生简章</h2><p>黔南民族师范学院与黔东南中等职业技术学校...</p>', 2, 1, 1);
GO

-- ==================== 成人高等教育字典数据 ====================

-- 专业字典（category_id=1 成人高考，type=zyyx）
INSERT INTO zs_dict (category_id, type, code, label, sort_order, is_active, extra_data) VALUES
(1, 'zyyx', 'zzyx01', N'汉语言文学专升本（学制2.5年，按学年制收费，每年1300元）', 1, 1, N'{"tuition": 1300, "duration": "2.5年", "quota": 100, "level": "专升本"}'),
(1, 'zyyx', 'zzyx02', N'土木工程专升本（学制2.5年，按学年制收费，每年1300元）', 2, 1, N'{"tuition": 1300, "duration": "2.5年", "quota": 80, "level": "专升本"}'),
(1, 'zyyx', 'zzyx03', N'行政管理专升本（学制2.5年，按学年制收费，每年1300元）', 3, 1, N'{"tuition": 1300, "duration": "2.5年", "quota": 60, "level": "专升本"}'),
(1, 'zyyx', 'zzyx04', N'现代农业经济管理高起专（学制2.5年，按学年制收费，每年1300元）', 4, 1, N'{"tuition": 1300, "duration": "2.5年", "quota": 50, "level": "高起专"}'),
(1, 'zyyx', 'zzyx05', N'机械制造及自动化高起专（学制2.5年，按学年制收费，每年1300元）', 5, 1, N'{"tuition": 1300, "duration": "2.5年", "quota": 70, "level": "高起专"}'),
(1, 'zyyx', 'zzyx06', N'行政管理高起专（学制2.5年，按学年制收费，每年1300元）', 6, 1, N'{"tuition": 1300, "duration": "2.5年", "quota": 70, "level": "高起专"}');
GO

-- 学习中心字典（category_id=1 成人高考，type=xxzx）
INSERT INTO zs_dict (category_id, type, code, label, sort_order, is_active, extra_data) VALUES
(1, 'xxzx', 'xxzx01', N'黔东南开放大学直属', 1, 1, N'{"address": "凯里市", "contact": "0855-12345678", "capacity": 500}'),
(1, 'xxzx', 'xxzx02', N'锦屏开放教育学院（黔东南开放大学锦屏分校）', 2, 1, N'{"address": "锦屏县", "contact": "0855-12345678", "capacity": 400}'),
(1, 'xxzx', 'xxzx03', N'岑巩开放教育学院（黔东南开放大学岑巩分校）', 3, 1, N'{"address": "岑巩县", "contact": "0855-12345678", "capacity": 300}'),
(1, 'xxzx', 'xxzx04', N'从江开放教育学院（黔东南开放大学从江分校）', 4, 1, N'{"address": "从江县", "contact": "0855-12345678", "capacity": 350}'),
(1, 'xxzx', 'xxzx05', N'丹寨开放教育学院（黔东南开放大学丹寨分校）', 5, 1, N'{"address": "丹寨县", "contact": "0855-12345678", "capacity": 350}'),
(1, 'xxzx', 'xxzx06', N'雷山开放教育学院（黔东南开放大学雷山分校）', 6, 1, N'{"address": "雷山县", "contact": "0855-12345678", "capacity": 350}');
GO

-- ==================== 3+4中本贯通字典数据 ====================

-- 性别字典（category_id=2）
INSERT INTO zs_dict (category_id, type, code, label, sort_order, is_active) VALUES
(2, 'gender', 'male', N'男', 1, 1),
(2, 'gender', 'female', N'女', 2, 1);
GO

-- 民族字典（category_id=2）
INSERT INTO zs_dict (category_id, type, code, label, sort_order, is_active) VALUES
(2, 'nation', 'han', N'汉族', 1, 1),
(2, 'nation', 'miao', N'苗族', 2, 1),
(2, 'nation', 'dong', N'侗族', 3, 1),
(2, 'nation', 'buyi', N'布依族', 4, 1),
(2, 'nation', 'shui', N'水族', 5, 1),
(2, 'nation', 'yao', N'瑶族', 6, 1),
(2, 'nation', 'zhuang', N'壮族', 7, 1),
(2, 'nation', 'tujia', N'土家族', 8, 1),
(2, 'nation', 'hui', N'回族', 9, 1),
(2, 'nation', 'yi', N'彝族', 10, 1),
(2, 'nation', 'gelao', N'仡佬族', 11, 1),
(2, 'nation', 'bai', N'白族', 12, 1),
(2, 'nation', 'other', N'其他', 99, 1);
GO

-- 户口性质字典（category_id=2）
INSERT INTO zs_dict (category_id, type, code, label, sort_order, is_active) VALUES
(2, 'household_type', 'agricultural', N'农业户口', 1, 1),
(2, 'household_type', 'non_agricultural', N'非农户口', 2, 1);
GO

-- 监护人关系字典（category_id=2）
INSERT INTO zs_dict (category_id, type, code, label, sort_order, is_active) VALUES
(2, 'guardian_relation', 'father', N'父亲', 1, 1),
(2, 'guardian_relation', 'mother', N'母亲', 2, 1),
(2, 'guardian_relation', 'other', N'其他', 3, 1);
GO

-- 省份字典（category_id=2，贵州省及周边）
INSERT INTO zs_dict (category_id, type, code, label, parent_code, sort_order, is_active) VALUES
(2, 'province', '520000', N'贵州省', NULL, 1, 1),
(2, 'province', '430000', N'湖南省', NULL, 2, 1),
(2, 'province', '450000', N'广西壮族自治区', NULL, 3, 1),
(2, 'province', '530000', N'云南省', NULL, 4, 1);
GO

-- 贵州省城市字典（category_id=2）
INSERT INTO zs_dict (category_id, type, code, label, parent_code, sort_order, is_active) VALUES
(2, 'city', '520100', N'贵阳市', '520000', 1, 1),
(2, 'city', '520200', N'六盘水市', '520000', 2, 1),
(2, 'city', '520300', N'遵义市', '520000', 3, 1),
(2, 'city', '520400', N'安顺市', '520000', 4, 1),
(2, 'city', '520500', N'毕节市', '520000', 5, 1),
(2, 'city', '520600', N'铜仁市', '520000', 6, 1),
(2, 'city', '522300', N'黔西南布依族苗族自治州', '520000', 7, 1),
(2, 'city', '522600', N'黔东南苗族侗族自治州', '520000', 8, 1),
(2, 'city', '522700', N'黔南布依族苗族自治州', '520000', 9, 1);
GO

-- 黔东南州区县字典（category_id=2）
INSERT INTO zs_dict (category_id, type, code, label, parent_code, sort_order, is_active) VALUES
(2, 'district', '522601', N'凯里市', '522600', 1, 1),
(2, 'district', '522622', N'黄平县', '522600', 2, 1),
(2, 'district', '522623', N'施秉县', '522600', 3, 1),
(2, 'district', '522624', N'三穗县', '522600', 4, 1),
(2, 'district', '522625', N'镇远县', '522600', 5, 1),
(2, 'district', '522626', N'岑巩县', '522600', 6, 1),
(2, 'district', '522627', N'天柱县', '522600', 7, 1),
(2, 'district', '522628', N'锦屏县', '522600', 8, 1),
(2, 'district', '522629', N'剑河县', '522600', 9, 1),
(2, 'district', '522630', N'台江县', '522600', 10, 1),
(2, 'district', '522631', N'黎平县', '522600', 11, 1),
(2, 'district', '522632', N'榕江县', '522600', 12, 1),
(2, 'district', '522633', N'从江县', '522600', 13, 1),
(2, 'district', '522634', N'雷山县', '522600', 14, 1),
(2, 'district', '522635', N'麻江县', '522600', 15, 1),
(2, 'district', '522636', N'丹寨县', '522600', 16, 1);
GO

-- ==================== 添加表注释 (SQL Server 扩展属性) ====================

EXEC sp_addextendedproperty 'MS_Description', N'招生类别表', 'SCHEMA', 'dbo', 'TABLE', 'zs_category';
EXEC sp_addextendedproperty 'MS_Description', N'主键ID', 'SCHEMA', 'dbo', 'TABLE', 'zs_category', 'COLUMN', 'id';
EXEC sp_addextendedproperty 'MS_Description', N'类别编码', 'SCHEMA', 'dbo', 'TABLE', 'zs_category', 'COLUMN', 'code';
EXEC sp_addextendedproperty 'MS_Description', N'类别名称', 'SCHEMA', 'dbo', 'TABLE', 'zs_category', 'COLUMN', 'name';
EXEC sp_addextendedproperty 'MS_Description', N'招生简章（富文本HTML）', 'SCHEMA', 'dbo', 'TABLE', 'zs_category', 'COLUMN', 'prospectus';

EXEC sp_addextendedproperty 'MS_Description', N'招生通用字典表', 'SCHEMA', 'dbo', 'TABLE', 'zs_dict';
EXEC sp_addextendedproperty 'MS_Description', N'成人高等教育预报名表', 'SCHEMA', 'dbo', 'TABLE', 'zs_adult_enrollment';
EXEC sp_addextendedproperty 'MS_Description', N'3+4中本贯通舞蹈表演专业面试考生报名表', 'SCHEMA', 'dbo', 'TABLE', 'zs_vocational34_enrollment';
GO

-- ==================== 查询示例 ====================

-- 查询成人高考的所有专业
-- SELECT * FROM zs_dict WHERE category_id = 1 AND type = 'zyyx' AND is_active = 1 ORDER BY sort_order;

-- 查询成人高考的所有学习中心
-- SELECT * FROM zs_dict WHERE category_id = 1 AND type = 'xxzx' AND is_active = 1 ORDER BY sort_order;

-- 查询黔东南州下的所有区县
-- SELECT * FROM zs_dict WHERE category_id = 2 AND type = 'district' AND parent_code = '522600' AND is_active = 1 ORDER BY sort_order;

-- 查询成人高考报名记录
-- SELECT * FROM zs_adult_enrollment WHERE status = 0 ORDER BY submit_time DESC;

-- 查询3+4报名记录
-- SELECT * FROM zs_vocational34_enrollment WHERE status = 0 ORDER BY submit_time DESC;

-- 统计成人高考各专业报名人数
-- SELECT d.label AS major_name, COUNT(e.id) AS enrollment_count 
-- FROM zs_adult_enrollment e 
-- LEFT JOIN zs_dict d ON e.major_code = d.code AND d.type = 'major' 
-- GROUP BY e.major_code, d.label
-- ORDER BY enrollment_count DESC;

-- 统计3+4报名的性别分布
-- SELECT 
--   CASE WHEN gender = 'male' THEN N'男' ELSE N'女' END AS gender_name,
--   COUNT(*) AS count
-- FROM zs_vocational34_enrollment
-- GROUP BY gender;
