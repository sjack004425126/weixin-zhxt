-- ============================================================
-- 校园反馈系统(后勤模块) 建表 SQL - SQL Server 版
-- 适用:SQL Server 2012+
-- 字符集:NVARCHAR(支持中文/emoji)
-- ============================================================

-- ---------------- 工单主表 ----------------
IF OBJECT_ID(N'dbo.hp_feedback_ticket', N'U') IS NOT NULL
    DROP TABLE dbo.hp_feedback_ticket;
GO

CREATE TABLE dbo.hp_feedback_ticket (
    id                   INT             IDENTITY(1,1) NOT NULL,
    ticket_no            NVARCHAR(32)    NOT NULL CONSTRAINT DF_hp_ft_ticket_no DEFAULT (N''),
    category             NVARCHAR(20)    NOT NULL CONSTRAINT DF_hp_ft_category  DEFAULT (N''),
    item_type            NVARCHAR(30)    NULL,
    item_custom          NVARCHAR(50)    NULL,


    content              NVARCHAR(MAX)   NULL,
    location_text        NVARCHAR(200)   NULL,
    images               NVARCHAR(MAX)   NULL,
    urgency              NVARCHAR(10)    NOT NULL CONSTRAINT DF_hp_ft_urgency   DEFAULT (N'normal'),
    is_anonymous         TINYINT         NOT NULL CONSTRAINT DF_hp_ft_anon      DEFAULT (0),

    reporter_user_type   NVARCHAR(30)    NOT NULL CONSTRAINT DF_hp_ft_rut       DEFAULT (N''),
    reporter_id          NVARCHAR(50)    NOT NULL CONSTRAINT DF_hp_ft_rid       DEFAULT (N''),
    reporter_name        NVARCHAR(50)    NULL,
    reporter_phone       NVARCHAR(20)    NULL,
    reporter_dept        NVARCHAR(50)    NULL,

    status               NVARCHAR(20)    NOT NULL CONSTRAINT DF_hp_ft_status    DEFAULT (N'pending'),
    handle_remark        NVARCHAR(MAX)   NULL,
    handle_images        NVARCHAR(MAX)   NULL,
    handle_at            DATETIME        NULL,
    handler_name         NVARCHAR(50)    NULL,
    handler_phone        NVARCHAR(20)    NULL,
    sms_cpSubID          NVARCHAR(50)    NULL,
    reject_reason        NVARCHAR(500)   NULL,

    is_deleted           TINYINT         NOT NULL CONSTRAINT DF_hp_ft_isdel     DEFAULT (0),
    deleted_at           DATETIME        NULL,
    deleted_by           NVARCHAR(50)    NULL,

    created_at           DATETIME        NOT NULL CONSTRAINT DF_hp_ft_created   DEFAULT (GETDATE()),
    updated_at           DATETIME        NOT NULL CONSTRAINT DF_hp_ft_updated   DEFAULT (GETDATE()),

    CONSTRAINT PK_hp_feedback_ticket PRIMARY KEY CLUSTERED (id)
);
GO

CREATE INDEX idx_hp_ft_ticket_no       ON dbo.hp_feedback_ticket (ticket_no);
CREATE INDEX idx_hp_ft_status          ON dbo.hp_feedback_ticket (status);
CREATE INDEX idx_hp_ft_reporter        ON dbo.hp_feedback_ticket (reporter_user_type, reporter_id);
CREATE INDEX idx_hp_ft_reporter_phone  ON dbo.hp_feedback_ticket (reporter_phone);
CREATE INDEX idx_hp_ft_created_at      ON dbo.hp_feedback_ticket (created_at);
CREATE INDEX idx_hp_ft_category_status ON dbo.hp_feedback_ticket (category, status);
GO

-- 触发器:维护 updated_at
IF OBJECT_ID(N'dbo.trg_hp_feedback_ticket_updated', N'TR') IS NOT NULL
    DROP TRIGGER dbo.trg_hp_feedback_ticket_updated;
GO
CREATE TRIGGER dbo.trg_hp_feedback_ticket_updated
ON dbo.hp_feedback_ticket
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE t SET updated_at = GETDATE()
    FROM dbo.hp_feedback_ticket t
    INNER JOIN inserted i ON t.id = i.id;
END;
GO


-- ---------------- 工单时间线 ----------------
IF OBJECT_ID(N'dbo.hp_feedback_timeline', N'U') IS NOT NULL
    DROP TABLE dbo.hp_feedback_timeline;
GO

CREATE TABLE dbo.hp_feedback_timeline (
    id              INT             IDENTITY(1,1) NOT NULL,
    ticket_id       INT             NOT NULL,
    action          NVARCHAR(20)    NOT NULL CONSTRAINT DF_hp_fl_action  DEFAULT (N''),
    operator_name   NVARCHAR(50)    NULL,
    operator_phone  NVARCHAR(20)    NULL,
    remark          NVARCHAR(MAX)   NULL,
    created_at      DATETIME        NOT NULL CONSTRAINT DF_hp_fl_created DEFAULT (GETDATE()),

    CONSTRAINT PK_hp_feedback_timeline PRIMARY KEY CLUSTERED (id)
);
GO

CREATE INDEX idx_hp_fl_ticket_id  ON dbo.hp_feedback_timeline (ticket_id);
CREATE INDEX idx_hp_fl_created_at ON dbo.hp_feedback_timeline (created_at);
GO


-- ---------------- 字段说明(扩展属性) ----------------
EXEC sp_addextendedproperty 'MS_Description', N'校园反馈工单表(后勤)', 'SCHEMA', 'dbo', 'TABLE', 'hp_feedback_ticket';
EXEC sp_addextendedproperty 'MS_Description', N'工单号 FByyyymmddHHMMSSxxxx', 'SCHEMA','dbo','TABLE','hp_feedback_ticket','COLUMN','ticket_no';
EXEC sp_addextendedproperty 'MS_Description', N'repair维修 / suggestion意见建议', 'SCHEMA','dbo','TABLE','hp_feedback_ticket','COLUMN','category';
EXEC sp_addextendedproperty 'MS_Description', N'紧急程度 normal/urgent', 'SCHEMA','dbo','TABLE','hp_feedback_ticket','COLUMN','urgency';
EXEC sp_addextendedproperty 'MS_Description', N'是否匿名 0否 1是(仅建议类)', 'SCHEMA','dbo','TABLE','hp_feedback_ticket','COLUMN','is_anonymous';
EXEC sp_addextendedproperty 'MS_Description', N'open_student/vocational_student/open_teacher/vocational_teacher', 'SCHEMA','dbo','TABLE','hp_feedback_ticket','COLUMN','reporter_user_type';
EXEC sp_addextendedproperty 'MS_Description', N'pending/processing/done/rejected/cancelled', 'SCHEMA','dbo','TABLE','hp_feedback_ticket','COLUMN','status';
EXEC sp_addextendedproperty 'MS_Description', N'JSON数组,反馈附图相对路径', 'SCHEMA','dbo','TABLE','hp_feedback_ticket','COLUMN','images';
EXEC sp_addextendedproperty 'MS_Description', N'JSON数组,整改后照片', 'SCHEMA','dbo','TABLE','hp_feedback_ticket','COLUMN','handle_images';
EXEC sp_addextendedproperty 'MS_Description', N'办结通知短信任务ID(关联 sms_log)', 'SCHEMA','dbo','TABLE','hp_feedback_ticket','COLUMN','sms_cpSubID';

EXEC sp_addextendedproperty 'MS_Description', N'校园反馈时间线(后勤)', 'SCHEMA', 'dbo', 'TABLE', 'hp_feedback_timeline';
EXEC sp_addextendedproperty 'MS_Description', N'submit/process/done/reject/cancel/comment', 'SCHEMA','dbo','TABLE','hp_feedback_timeline','COLUMN','action';
GO
