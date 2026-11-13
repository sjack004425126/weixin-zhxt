-- ==================== 招生报名系统数据库表结构 ====================
-- 创建时间: 2025-03-13
-- 说明: 用于成人高考和"3+4"中本贯通等招生报名管理

-- 1. 招生类别表
CREATE TABLE `zs_category` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `code` VARCHAR(50) NOT NULL COMMENT '类别编码',
  `name` VARCHAR(100) NOT NULL COMMENT '类别名称',
  `description` TEXT COMMENT '类别描述',
  `prospectus` TEXT COMMENT '招生简章（富文本HTML）',
  `sort_order` INT DEFAULT 0 COMMENT '排序',
  `is_active` INT DEFAULT 1 COMMENT '是否启用：0-禁用 1-启用',
  `start_time` DATETIME COMMENT '报名开始时间',
  `end_time` DATETIME COMMENT '报名结束时间',
  `batch` INT COMMENT '当前批次',
  `create_time` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_code` (`code`),
  KEY `idx_is_active` (`is_active`),
  KEY `idx_sort_order` (`sort_order`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='招生类别表';

-- 2. 招生通用字典表
CREATE TABLE `zs_dict` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `category_id` INT NOT NULL COMMENT '招生类别ID，关联zs_category表',
  `type` VARCHAR(50) NOT NULL COMMENT '字典类型：gender性别/nation民族/major专业/learning_center学习中心/province省份/city城市/district区县/household_type户口性质/guardian_relation监护人关系等',
  `code` VARCHAR(50) NOT NULL COMMENT '字典编码',
  `label` VARCHAR(100) NOT NULL COMMENT '字典标签',
  `parent_code` VARCHAR(50) COMMENT '父级编码，用于级联选择（如：省市区三级联动）',
  `sort_order` INT DEFAULT 0 COMMENT '排序',
  `is_active` INT DEFAULT 1 COMMENT '是否启用：0-禁用 1-启用',
  `remark` VARCHAR(500) COMMENT '备注',
  `extra_data` TEXT COMMENT '扩展数据（JSON格式，如：学费、学制、招生人数等）',
  `create_time` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_category_type_code` (`category_id`, `type`, `code`),
  KEY `idx_category_id` (`category_id`),
  KEY `idx_type` (`type`),
  KEY `idx_parent_code` (`parent_code`),
  KEY `idx_is_active` (`is_active`),
  CONSTRAINT `fk_zs_dict_category` FOREIGN KEY (`category_id`) REFERENCES `zs_category` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='招生通用字典表';

-- 3. 成人高等教育预报名表
CREATE TABLE `zs_adult_enrollment` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  
  -- 1. 姓名（必填）
  `name` VARCHAR(50) NOT NULL COMMENT '姓名',
  
  -- 2. 手机号（必填）
  `phone` VARCHAR(20) NOT NULL COMMENT '手机号',
  
  -- 3. 意向专业及费用明细（必选）
  `major_code` VARCHAR(50) NOT NULL COMMENT '意向专业代码，关联zs_dict',
  
  -- 4. 选择入学后的学习中心（必选）
  `learning_center_code` VARCHAR(50) NOT NULL COMMENT '学习中心代码，关联zs_dict',
  
  -- 状态信息
  `status` INT DEFAULT 0 COMMENT '状态：0-待审核 1-审核通过 2-审核不通过 3-已录取',
  `batch` INT COMMENT '批次',
  `submit_time` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '提交时间',
  `audit_time` DATETIME COMMENT '审核时间',
  `auditor_id` INT COMMENT '审核人ID',
  `audit_remark` VARCHAR(500) COMMENT '审核备注',
  
  -- 微信信息
  `wx_openid` VARCHAR(100) COMMENT '微信openid',
  `wx_nickname` VARCHAR(100) COMMENT '微信昵称',
  `wx_headimgurl` VARCHAR(500) COMMENT '微信头像',
  
  -- 时间戳
  `create_time` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  
  PRIMARY KEY (`id`),
  KEY `idx_phone` (`phone`),
  KEY `idx_major_code` (`major_code`),
  KEY `idx_learning_center_code` (`learning_center_code`),
  KEY `idx_status` (`status`),
  KEY `idx_batch` (`batch`),
  KEY `idx_wx_openid` (`wx_openid`),
  KEY `idx_submit_time` (`submit_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='成人高等教育预报名表';

-- 4. 3+4中本贯通舞蹈表演专业面试考生报名表
CREATE TABLE `zs_vocational34_enrollment` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  
  -- 1. 序号（自动生成）
  `serial_number` VARCHAR(20) COMMENT '序号',
  
  -- 2. 考生基本信息
  `name` VARCHAR(50) NOT NULL COMMENT '学生姓名',
  `admission_ticket_no` VARCHAR(50) COMMENT '准考证号',
  `gender` VARCHAR(20) NOT NULL COMMENT '性别：male男/female女',
  `nation` VARCHAR(50) COMMENT '民族代码，关联zs_dict',
  `id_card` VARCHAR(18) NOT NULL COMMENT '身份证号码',
  `junior_school_name` VARCHAR(100) COMMENT '原初中毕业学校全称',
  `junior_school_county` VARCHAR(100) COMMENT '原初中毕业学校所在县份',
  `is_qdn_graduate` INT COMMENT '是否黔东南州的2025年应届初中毕业生：1-是 0-否',
  
  -- 3. 籍贯信息
  `household_type` VARCHAR(50) COMMENT '户口性质：agricultural农业户口/non_agricultural非农户口',
  `household_province` VARCHAR(50) COMMENT '户籍省份代码',
  `household_city` VARCHAR(50) COMMENT '户籍城市代码',
  `household_district` VARCHAR(50) COMMENT '户籍区县代码',
  `household_address` VARCHAR(200) COMMENT '户籍详细地址',
  `residence_province` VARCHAR(50) COMMENT '实际居住省份代码',
  `residence_city` VARCHAR(50) COMMENT '实际居住城市代码',
  `residence_district` VARCHAR(50) COMMENT '实际居住区县代码',
  `residence_address` VARCHAR(200) COMMENT '实际居住详细地址',
  
  -- 4. 手机号
  `phone` VARCHAR(20) NOT NULL COMMENT '手机号',
  
  -- 5. 监护人信息
  `guardian_name` VARCHAR(50) COMMENT '监护人姓名',
  `guardian_phone` VARCHAR(20) COMMENT '监护人联系方式',
  `guardian_relation` VARCHAR(50) COMMENT '监护人身份：father父亲/mother母亲/other其他',
  
  -- 6-9. 上传文件
  `id_card_front_url` VARCHAR(500) COMMENT '身份证正面照片URL',
  `id_card_back_url` VARCHAR(500) COMMENT '身份证反面照片URL',
  `photo_url` VARCHAR(500) COMMENT '标准证件照URL',
  `consent_letter_url` VARCHAR(500) COMMENT '知情同意书照片URL',
  
  -- 10. 知情确认
  `is_confirmed` INT DEFAULT 0 COMMENT '知情确认：1-已确认 0-未确认',
  
  -- 11. 考生签名
  `signature_url` VARCHAR(500) COMMENT '考生签名图片URL',
  
  -- 状态信息
  `status` INT DEFAULT 0 COMMENT '状态：0-待审核 1-审核通过 2-审核不通过 3-已录取',
  `batch` INT COMMENT '批次',
  `submit_time` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '提交时间',
  `audit_time` DATETIME COMMENT '审核时间',
  `auditor_id` INT COMMENT '审核人ID',
  `audit_remark` VARCHAR(500) COMMENT '审核备注',
  
  -- 微信信息
  `wx_openid` VARCHAR(100) COMMENT '微信openid',
  `wx_nickname` VARCHAR(100) COMMENT '微信昵称',
  `wx_headimgurl` VARCHAR(500) COMMENT '微信头像',
  
  -- 时间戳
  `create_time` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_id_card` (`id_card`),
  KEY `idx_phone` (`phone`),
  KEY `idx_name` (`name`),
  KEY `idx_status` (`status`),
  KEY `idx_batch` (`batch`),
  KEY `idx_wx_openid` (`wx_openid`),
  KEY `idx_submit_time` (`submit_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='3+4中本贯通舞蹈表演专业面试考生报名表';

-- ==================== 初始化数据 ====================

-- 插入招生类别初始数据
INSERT INTO `zs_category` (`code`, `name`, `description`, `prospectus`, `sort_order`, `is_active`, `batch`) VALUES
('adult_exam', '成人高等教育2025年预报名', '成人高等教育招生', '<h2>成人高等教育2025年预报名招生简章</h2><p>欢迎报考成人高等教育...</p>', 1, 1, 1),
('vocational_34', '3+4中本贯通舞蹈表演专业', '中职与本科贯通培养舞蹈表演专业', '<h2>3+4中本贯通舞蹈表演专业招生简章</h2><p>黔南民族师范学院与黔东南中等职业技术学校...</p>', 2, 1, 1);

-- ==================== 成人高等教育字典数据 ====================

-- 专业字典（category_id=1 成人高考）
INSERT INTO `zs_dict` (`category_id`, `type`, `code`, `label`, `sort_order`, `is_active`, `extra_data`) VALUES
(1, 'major', 'computer_science', '计算机科学与技术', 1, 1, '{"tuition": 2400, "duration": "2.5年", "quota": 100, "level": "专升本"}'),
(1, 'major', 'accounting', '会计学', 2, 1, '{"tuition": 2200, "duration": "2.5年", "quota": 80, "level": "专升本"}'),
(1, 'major', 'business_admin', '工商管理', 3, 1, '{"tuition": 2200, "duration": "2.5年", "quota": 60, "level": "专升本"}'),
(1, 'major', 'law', '法学', 4, 1, '{"tuition": 2000, "duration": "2.5年", "quota": 50, "level": "专升本"}'),
(1, 'major', 'nursing', '护理学', 5, 1, '{"tuition": 2600, "duration": "2.5年", "quota": 70, "level": "专升本"}');

-- 学习中心字典（category_id=1 成人高考）
INSERT INTO `zs_dict` (`category_id`, `type`, `code`, `label`, `sort_order`, `is_active`, `extra_data`) VALUES
(1, 'learning_center', 'center_beijing', '北京学习中心', 1, 1, '{"address": "北京市海淀区", "contact": "010-12345678", "capacity": 500}'),
(1, 'learning_center', 'center_shanghai', '上海学习中心', 2, 1, '{"address": "上海市浦东新区", "contact": "021-12345678", "capacity": 400}'),
(1, 'learning_center', 'center_guangzhou', '广州学习中心', 3, 1, '{"address": "广州市天河区", "contact": "020-12345678", "capacity": 300}'),
(1, 'learning_center', 'center_shenzhen', '深圳学习中心', 4, 1, '{"address": "深圳市南山区", "contact": "0755-12345678", "capacity": 350}');

-- ==================== 3+4中本贯通字典数据 ====================

-- 性别字典（category_id=2）
INSERT INTO `zs_dict` (`category_id`, `type`, `code`, `label`, `sort_order`, `is_active`) VALUES
(2, 'gender', 'male', '男', 1, 1),
(2, 'gender', 'female', '女', 2, 1);

-- 民族字典（category_id=2）
INSERT INTO `zs_dict` (`category_id`, `type`, `code`, `label`, `sort_order`, `is_active`) VALUES
(2, 'nation', 'han', '汉族', 1, 1),
(2, 'nation', 'miao', '苗族', 2, 1),
(2, 'nation', 'dong', '侗族', 3, 1),
(2, 'nation', 'buyi', '布依族', 4, 1),
(2, 'nation', 'shui', '水族', 5, 1),
(2, 'nation', 'yao', '瑶族', 6, 1),
(2, 'nation', 'zhuang', '壮族', 7, 1),
(2, 'nation', 'tujia', '土家族', 8, 1),
(2, 'nation', 'hui', '回族', 9, 1),
(2, 'nation', 'yi', '彝族', 10, 1),
(2, 'nation', 'gelao', '仡佬族', 11, 1),
(2, 'nation', 'bai', '白族', 12, 1),
(2, 'nation', 'other', '其他', 99, 1);

-- 户口性质字典（category_id=2）
INSERT INTO `zs_dict` (`category_id`, `type`, `code`, `label`, `sort_order`, `is_active`) VALUES
(2, 'household_type', 'agricultural', '农业户口', 1, 1),
(2, 'household_type', 'non_agricultural', '非农户口', 2, 1);

-- 监护人关系字典（category_id=2）
INSERT INTO `zs_dict` (`category_id`, `type`, `code`, `label`, `sort_order`, `is_active`) VALUES
(2, 'guardian_relation', 'father', '父亲', 1, 1),
(2, 'guardian_relation', 'mother', '母亲', 2, 1),
(2, 'guardian_relation', 'other', '其他', 3, 1);

-- 省份字典（category_id=2，贵州省及周边）
INSERT INTO `zs_dict` (`category_id`, `type`, `code`, `label`, `parent_code`, `sort_order`, `is_active`) VALUES
(2, 'province', '520000', '贵州省', NULL, 1, 1),
(2, 'province', '430000', '湖南省', NULL, 2, 1),
(2, 'province', '450000', '广西壮族自治区', NULL, 3, 1),
(2, 'province', '530000', '云南省', NULL, 4, 1);

-- 贵州省城市字典（category_id=2）
INSERT INTO `zs_dict` (`category_id`, `type`, `code`, `label`, `parent_code`, `sort_order`, `is_active`) VALUES
(2, 'city', '520100', '贵阳市', '520000', 1, 1),
(2, 'city', '520200', '六盘水市', '520000', 2, 1),
(2, 'city', '520300', '遵义市', '520000', 3, 1),
(2, 'city', '520400', '安顺市', '520000', 4, 1),
(2, 'city', '520500', '毕节市', '520000', 5, 1),
(2, 'city', '520600', '铜仁市', '520000', 6, 1),
(2, 'city', '522300', '黔西南布依族苗族自治州', '520000', 7, 1),
(2, 'city', '522600', '黔东南苗族侗族自治州', '520000', 8, 1),
(2, 'city', '522700', '黔南布依族苗族自治州', '520000', 9, 1);

-- 黔东南州区县字典（category_id=2）
INSERT INTO `zs_dict` (`category_id`, `type`, `code`, `label`, `parent_code`, `sort_order`, `is_active`) VALUES
(2, 'district', '522601', '凯里市', '522600', 1, 1),
(2, 'district', '522622', '黄平县', '522600', 2, 1),
(2, 'district', '522623', '施秉县', '522600', 3, 1),
(2, 'district', '522624', '三穗县', '522600', 4, 1),
(2, 'district', '522625', '镇远县', '522600', 5, 1),
(2, 'district', '522626', '岑巩县', '522600', 6, 1),
(2, 'district', '522627', '天柱县', '522600', 7, 1),
(2, 'district', '522628', '锦屏县', '522600', 8, 1),
(2, 'district', '522629', '剑河县', '522600', 9, 1),
(2, 'district', '522630', '台江县', '522600', 10, 1),
(2, 'district', '522631', '黎平县', '522600', 11, 1),
(2, 'district', '522632', '榕江县', '522600', 12, 1),
(2, 'district', '522633', '从江县', '522600', 13, 1),
(2, 'district', '522634', '雷山县', '522600', 14, 1),
(2, 'district', '522635', '麻江县', '522600', 15, 1),
(2, 'district', '522636', '丹寨县', '522600', 16, 1);

-- ==================== 查询示例 ====================

-- 查询成人高考的所有专业
-- SELECT * FROM zs_dict WHERE category_id = 1 AND type = 'major' AND is_active = 1 ORDER BY sort_order;

-- 查询成人高考的所有学习中心
-- SELECT * FROM zs_dict WHERE category_id = 1 AND type = 'learning_center' AND is_active = 1 ORDER BY sort_order;

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
--   CASE WHEN gender = 'male' THEN '男' ELSE '女' END AS gender_name,
--   COUNT(*) AS count
-- FROM zs_vocational34_enrollment
-- GROUP BY gender;
