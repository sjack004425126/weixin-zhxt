-- =====================================================================
-- 迁移:问卷提交次数限制(SQL Server 2016+)
-- 适用: 已有 oa_survey_survey / oa_survey_answer 表的库
-- 操作: 给 oa_survey_survey 加 2 个字段 + 给 oa_survey_answer 加 4 个索引
-- 用法: sqlcmd / SSMS 直接执行,字段/索引已存在会自动跳过
-- =====================================================================

-- 1) 问卷主表: 次数限制字段
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'oa_survey_survey')
      AND name = 'submit_limit'
)
BEGIN
    ALTER TABLE [oa_survey_survey]
        ADD [submit_limit] INT NOT NULL
        CONSTRAINT [DF_oa_survey_survey_submit_limit] DEFAULT (1);
    PRINT '+ oa_survey_survey.submit_limit 已添加';
END
ELSE
BEGIN
    PRINT '- oa_survey_survey.submit_limit 已存在,跳过';
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'oa_survey_survey')
      AND name = 'submit_limit_period'
)
BEGIN
    ALTER TABLE [oa_survey_survey]
        ADD [submit_limit_period] NVARCHAR(16) NOT NULL
        CONSTRAINT [DF_oa_survey_survey_submit_limit_period] DEFAULT (N'once');
    PRINT '+ oa_survey_survey.submit_limit_period 已添加';
END
ELSE
BEGIN
    PRINT '- oa_survey_survey.submit_limit_period 已存在,跳过';
END
GO

-- 2) 答卷表: 联合索引(用于次数校验查询)
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_answer_device' AND object_id = OBJECT_ID(N'oa_survey_answer'))
BEGIN
    CREATE NONCLUSTERED INDEX [idx_answer_device] ON [oa_survey_answer] ([device_id]);
    PRINT '+ idx_answer_device 已创建';
END
ELSE
BEGIN
    PRINT '- idx_answer_device 已存在,跳过';
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_answer_sid_wx' AND object_id = OBJECT_ID(N'oa_survey_answer'))
BEGIN
    CREATE NONCLUSTERED INDEX [idx_answer_sid_wx] ON [oa_survey_answer] ([sid], [wx_openid]);
    PRINT '+ idx_answer_sid_wx 已创建';
END
ELSE
BEGIN
    PRINT '- idx_answer_sid_wx 已存在,跳过';
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_answer_sid_device' AND object_id = OBJECT_ID(N'oa_survey_answer'))
BEGIN
    CREATE NONCLUSTERED INDEX [idx_answer_sid_device] ON [oa_survey_answer] ([sid], [device_id]);
    PRINT '+ idx_answer_sid_device 已创建';
END
ELSE
BEGIN
    PRINT '- idx_answer_sid_device 已存在,跳过';
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_answer_sid_submit_time' AND object_id = OBJECT_ID(N'oa_survey_answer'))
BEGIN
    CREATE NONCLUSTERED INDEX [idx_answer_sid_submit_time] ON [oa_survey_answer] ([sid], [submit_time]);
    PRINT '+ idx_answer_sid_submit_time 已创建';
END
ELSE
BEGIN
    PRINT '- idx_answer_sid_submit_time 已存在,跳过';
END
GO

-- 3) 回填:给所有现有问卷默认值(1/once),无需手动更新
--    如需某些问卷不限次,手动执行:
--    UPDATE [oa_survey_survey] SET [submit_limit] = 0 WHERE [sid] IN (...);
--    UPDATE [oa_survey_survey] SET [submit_limit] = 5, [submit_limit_period] = N'day' WHERE [sid] IN (...);

PRINT '迁移完成';