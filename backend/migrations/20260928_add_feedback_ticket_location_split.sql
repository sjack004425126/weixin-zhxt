/* ============================================================
   校园反馈 - location_dict_text / location_user_text 列补齐（2026-09-28）
   生成背景：
     方案 C：双列独立存储地点信息（一次性解决，不再返回单列拼接）。
     - location_dict_text：仅 chip 拼接（字典原值序列），"|"分隔
     - location_user_text：仅用户备注（自由文本）
     - location_text     ：合并展示串（"|"段 + " · " + 备注），给详情/列表展示用
   作用：
     给 hp_feedback_ticket 幂等补上 location_dict_text / location_user_text 两列，
     并为 location_dict_text 建索引（token 精确匹配），为 location_user_text 建索引（LIKE 用）。
     脚本可重复执行。
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

/* 1) location_dict_text：列表段（"|"分隔的字典原值序列） */
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
     WHERE object_id = OBJECT_ID(N'dbo.hp_feedback_ticket')
       AND name = N'location_dict_text'
)
BEGIN
    ALTER TABLE dbo.hp_feedback_ticket
        ADD location_dict_text NVARCHAR(500) NULL;

    -- 索引：方便 token 精确匹配（WHERE '|'+dict+'|' LIKE '%|kw|%'）
    CREATE INDEX IX_hp_fb_ticket_loc_dict
        ON dbo.hp_feedback_ticket(location_dict_text);

    EXEC dbo.sp_set_column_comment
        N'dbo', N'hp_feedback_ticket', N'location_dict_text',
        N'地点-列表段：仅来自字典 chip 拼接，"|"分隔，例如 "10楼|宿舍楼A|102教室讲台"';

    PRINT N'✅ hp_feedback_ticket.location_dict_text 列已添加（带索引）';
END
ELSE
BEGIN
    PRINT N'ℹ️  hp_feedback_ticket.location_dict_text 列已存在，跳过';
END
GO

/* 2) location_user_text：备注段（用户自由文本，无分隔符约束） */
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
     WHERE object_id = OBJECT_ID(N'dbo.hp_feedback_ticket')
       AND name = N'location_user_text'
)
BEGIN
    ALTER TABLE dbo.hp_feedback_ticket
        ADD location_user_text NVARCHAR(500) NULL;

    -- 索引：方便单列 LIKE '%kw%'
    CREATE INDEX IX_hp_fb_ticket_loc_user
        ON dbo.hp_feedback_ticket(location_user_text);

    EXEC dbo.sp_set_column_comment
        N'dbo', N'hp_feedback_ticket', N'location_user_text',
        N'地点-备注段：仅用户手写（textarea），自由文本，可空';

    PRINT N'✅ hp_feedback_ticket.location_user_text 列已添加（带索引）';
END
ELSE
BEGIN
    PRINT N'ℹ️  hp_feedback_ticket.location_user_text 列已存在，跳过';
END
GO

/* 3) location_text 已有则不动，仅同步扩展说明 */
IF EXISTS (
    SELECT 1 FROM sys.columns
     WHERE object_id = OBJECT_ID(N'dbo.hp_feedback_ticket')
       AND name = N'location_text'
)
BEGIN
    EXEC dbo.sp_set_column_comment
        N'dbo', N'hp_feedback_ticket', N'location_text',
        N'地点-展示合并串：list 段 + " · " + 备注段，给详情/列表展示用，不参与搜索';
    PRINT N'ℹ️  hp_feedback_ticket.location_text 列说明已更新';
END
GO

PRINT N'✅ hp_feedback_ticket 双列拆分字段补齐完成';
GO
