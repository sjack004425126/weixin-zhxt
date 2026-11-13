-- ============================================================
-- 校园反馈系统(后勤模块) 建表 SQL
-- 数据库:MySQL 5.7+ / MariaDB 10.3+
-- 字符集:utf8mb4
-- ============================================================

-- 工单主表
DROP TABLE IF EXISTS `hp_feedback_ticket`;
CREATE TABLE `hp_feedback_ticket` (
  `id`                  INT             NOT NULL AUTO_INCREMENT COMMENT '主键',
  `ticket_no`           VARCHAR(32)     NOT NULL DEFAULT '' COMMENT '工单号 FByyyymmddHHMMSSxxxx',
  `category`            VARCHAR(20)     NOT NULL DEFAULT '' COMMENT '分类:repair维修 / suggestion意见建议',
  `item_type`           VARCHAR(30)              DEFAULT NULL COMMENT '物品/对象类型',
  `item_custom`         VARCHAR(50)              DEFAULT NULL COMMENT '自定义对象',
  `content`             TEXT                     COMMENT '详细描述',
  `location_text`       VARCHAR(200)             DEFAULT NULL COMMENT '位置/地点描述',
  `images`              TEXT                     COMMENT '反馈附图(JSON数组,相对路径)',
  `urgency`             VARCHAR(10)     NOT NULL DEFAULT 'normal' COMMENT '紧急程度:normal/urgent',
  `is_anonymous`        TINYINT(1)      NOT NULL DEFAULT 0 COMMENT '是否匿名 0否 1是(仅建议类可用)',

  `reporter_user_type`  VARCHAR(30)     NOT NULL DEFAULT '' COMMENT '反馈人类型:open_student/vocational_student/open_teacher/vocational_teacher',
  `reporter_id`         VARCHAR(50)     NOT NULL DEFAULT '' COMMENT '学号或工号',
  `reporter_name`       VARCHAR(50)              DEFAULT NULL COMMENT '反馈人姓名',
  `reporter_phone`      VARCHAR(20)              DEFAULT NULL COMMENT '反馈人电话(用于办结短信)',
  `reporter_dept`       VARCHAR(50)              DEFAULT NULL COMMENT '班级/部门',

  `status`              VARCHAR(20)     NOT NULL DEFAULT 'pending' COMMENT '状态:pending/processing/done/rejected/cancelled',
  `handle_remark`       TEXT                     COMMENT '处理意见',
  `handle_images`       TEXT                     COMMENT '整改照片(JSON数组)',
  `handle_at`           DATETIME                 DEFAULT NULL COMMENT '办结时间',
  `handler_name`        VARCHAR(50)              DEFAULT NULL COMMENT '处理人姓名',
  `handler_phone`       VARCHAR(20)              DEFAULT NULL COMMENT '处理人手机',
  `sms_cpSubID`         VARCHAR(50)              DEFAULT NULL COMMENT '办结通知短信任务ID(关联 sms_log)',
  `reject_reason`       VARCHAR(500)             DEFAULT NULL COMMENT '驳回原因',

  `is_deleted`          TINYINT(1)      NOT NULL DEFAULT 0 COMMENT '软删除:0未删 1已删',
  `deleted_at`          DATETIME                 DEFAULT NULL COMMENT '删除时间',
  `deleted_by`          VARCHAR(50)              DEFAULT NULL COMMENT '删除操作人',

  `created_at`          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at`          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

  PRIMARY KEY (`id`),
  KEY `idx_ticket_no`        (`ticket_no`),
  KEY `idx_status`           (`status`),
  KEY `idx_reporter`         (`reporter_user_type`, `reporter_id`),
  KEY `idx_reporter_phone`   (`reporter_phone`),
  KEY `idx_created_at`       (`created_at`),
  KEY `idx_category_status`  (`category`, `status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='校园反馈工单表(后勤)';


-- 工单时间线/操作日志
DROP TABLE IF EXISTS `hp_feedback_timeline`;
CREATE TABLE `hp_feedback_timeline` (
  `id`              INT          NOT NULL AUTO_INCREMENT COMMENT '主键',
  `ticket_id`       INT          NOT NULL COMMENT '工单ID',
  `action`          VARCHAR(20)  NOT NULL DEFAULT '' COMMENT '动作:submit/process/done/reject/cancel/comment',
  `operator_name`   VARCHAR(50)           DEFAULT NULL COMMENT '操作人姓名',
  `operator_phone`  VARCHAR(20)           DEFAULT NULL COMMENT '操作人手机',
  `remark`          TEXT                  COMMENT '备注/说明',
  `created_at`      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  KEY `idx_ticket_id`  (`ticket_id`),
  KEY `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='校园反馈时间线(后勤)';
