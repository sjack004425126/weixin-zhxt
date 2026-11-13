/* ============================================================
   校园反馈 - 工单表 location_text 列补齐（2026-09-28）
   生成背景：
     反馈工单模型 FeedbackTicket 重构后增加了
     location_text / location_text_fuzzy / location_parts 等列，
     但历史库里 hp_feedback_ticket 缺少 location_text 列，
     导致 /feedback/submit 触发 SELECT 全字段时报：
        42S22 列名 'location_text' 无效
   作用：
     给 hp_feedback_ticket 幂等补上 location_text（NVARCHAR(200)），
     与模型保持一致。脚本可重复执行。

   2026-09-28 修订：使用 dbo.sp_set_column_comment helper 保证 sp_addextendedproperty 幂等
     （已存在 MS_Description 时报 15233，需要走 sp_updateextendedproperty）。
   ============================================================ */

SET NOCOUNT ON;
GO

IF OBJECT_ID(N'dbo.hp_feedback_ticket', N'U') IS NULL
BEGIN
    PRINT N'⚠️  dbo.hp_feedback_ticket 表不存在，跳过（请先建表）';
    RETURN;
END
GO

/* 通用 helper：幂等写 MS_Description（已存在则更新，不存在则添加） */
IF OBJECT_ID(N'dbo.sp_set_column_comment', N'P') IS NULL
EXEC(N'
CREATE PROCEDURE dbo.sp_set_column_comment
    @schema_name SYSNAME,
    @table_name  SYSNAME,
    @column_name SYSNAME,
    @description NVARCHAR(4000)
AS
BEGIN
    SET NOCOUNT ON;
    IF EXISTS (
        SELECT 1 FROM fn_listextendedproperty(
            N''MS_Description'',
            N''SCHEMA'', @schema_name,
            N''TABLE'',  @table_name,
            N''COLUMN'', @column_name)
    )
    BEGIN
        EXEC sp_updateextendedproperty
            N''MS_Description'', @description,
            N''SCHEMA'', @schema_name,
            N''TABLE'',  @table_name,
            N''COLUMN'', @column_name;
    END
    ELSE
    BEGIN
        EXEC sp_addextendedproperty
            N''MS_Description'', @description,
            N''SCHEMA'', @schema_name,
            N''TABLE'',  @table_name,
            N''COLUMN'', @column_name;
    END
END
');
GO

/* 1) location_text */
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
     WHERE object_id = OBJECT_ID(N'dbo.hp_feedback_ticket')
       AND name = N'location_text'
)
BEGIN
    ALTER TABLE dbo.hp_feedback_ticket
        ADD location_text NVARCHAR(200) NULL;

    EXEC dbo.sp_set_column_comment
        N'dbo', N'hp_feedback_ticket', N'location_text',
        N'地点描述（兼容旧数据 / 自由输入）';

    PRINT N'✅ hp_feedback_ticket.location_text 列已添加';
END
ELSE
BEGIN
    PRINT N'ℹ️  hp_feedback_ticket.location_text 列已存在，跳过';
END
GO

/* 2) location_parts（防漏） */
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
     WHERE object_id = OBJECT_ID(N'dbo.hp_feedback_ticket')
       AND name = N'location_parts'
)
BEGIN
    ALTER TABLE dbo.hp_feedback_ticket
        ADD location_parts NVARCHAR(MAX) NULL;

    EXEC dbo.sp_set_column_comment
        N'dbo', N'hp_feedback_ticket', N'location_parts',
        N'JSON 数组：[{type, value}, ...] 任意地点类型组合（2026-09-27 重构）';

    PRINT N'✅ hp_feedback_ticket.location_parts 列已添加';
END
ELSE
BEGIN
    PRINT N'ℹ️  hp_feedback_ticket.location_parts 列已存在，跳过';
END
GO

/* 3) location_text_fuzzy（防漏） */
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
     WHERE object_id = OBJECT_ID(N'dbo.hp_feedback_ticket')
       AND name = N'location_text_fuzzy'
)
BEGIN
    ALTER TABLE dbo.hp_feedback_ticket
        ADD location_text_fuzzy NVARCHAR(255) NULL;

    CREATE INDEX IX_hp_fb_ticket_loc_fuzzy
        ON dbo.hp_feedback_ticket(location_text_fuzzy);

    EXEC dbo.sp_set_column_comment
        N'dbo', N'hp_feedback_ticket', N'location_text_fuzzy',
        N'地点自由文本/拼接显示（兼容旧字段，模糊搜索用）';

    PRINT N'✅ hp_feedback_ticket.location_text_fuzzy 列已添加（带索引）';
END
ELSE
BEGIN
    PRINT N'ℹ️  hp_feedback_ticket.location_text_fuzzy 列已存在，跳过';
END
GO

/* 4) repair_type_text（防漏） */
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
     WHERE object_id = OBJECT_ID(N'dbo.hp_feedback_ticket')
       AND name = N'repair_type_text'
)
BEGIN
    ALTER TABLE dbo.hp_feedback_ticket
        ADD repair_type_text NVARCHAR(64) NULL;

    CREATE INDEX IX_hp_fb_ticket_repair_type
        ON dbo.hp_feedback_ticket(repair_type_text);

    EXEC dbo.sp_set_column_comment
        N'dbo', N'hp_feedback_ticket', N'repair_type_text',
        N'维修类型自由文本（用户输入/字典选中，模糊搜索用）';

    PRINT N'✅ hp_feedback_ticket.repair_type_text 列已添加（带索引）';
END
ELSE
BEGIN
    PRINT N'ℹ️  hp_feedback_ticket.repair_type_text 列已存在，跳过';
END
GO


PRINT N'✅ hp_feedback_ticket 列补齐完成';
GO
