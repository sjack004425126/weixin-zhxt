/* ============================================================
   校园反馈 - 删除冗余地点列（强化版，2026-09-28 v2）
   生成背景：
     方案 C 落地：DB 只保留 location_text / location_dict_text / location_user_text，
     不再需要 location_text_fuzzy / location_parts。
   行为：
     1. 把 location_text_fuzzy 数据回填到 location_text（仅当 location_text 为空时）
     2. 删除 location_parts 列（含扩展属性）
     3. 删除 location_text_fuzzy 列 + 它上面所有相关索引
     4. 兜底：确保 location_dict_text / location_user_text 上有索引（独立 IO 优化）
   幂等：可重复执行；所有步骤独立 BEGIN/END，失败不影响其他步骤。
   ============================================================ */

SET NOCOUNT ON;
SET XACT_ABORT OFF;
GO

IF OBJECT_ID(N'dbo.hp_feedback_ticket', N'U') IS NULL
BEGIN
    PRINT N'[skip] dbo.hp_feedback_ticket 表不存在';
    RETURN;
END
GO

/* ============================================================
   1) 数据回填：location_text_fuzzy → location_text（仅空时）
   ============================================================ */
BEGIN TRY
    IF EXISTS (
        SELECT 1 FROM sys.columns
         WHERE object_id = OBJECT_ID(N'dbo.hp_feedback_ticket')
           AND name = N'location_text_fuzzy'
    )
    BEGIN
        UPDATE dbo.hp_feedback_ticket
           SET location_text = LTRIM(RTRIM(ISNULL(location_text_fuzzy, N'')))
         WHERE (location_text IS NULL OR LTRIM(RTRIM(location_text)) = N'')
           AND location_text_fuzzy IS NOT NULL
           AND LTRIM(RTRIM(location_text_fuzzy)) <> N'';
        PRINT N'[ok] step1: location_text_fuzzy -> location_text 回填完成';
    END
    ELSE
        PRINT N'[skip] step1: location_text_fuzzy 列不存在';
END TRY
BEGIN CATCH
    PRINT N'[warn] step1 失败: ' + ERROR_MESSAGE();
END CATCH
GO

/* ============================================================
   2) 删除 location_parts 列（含扩展属性）
   ============================================================ */
BEGIN TRY
    IF EXISTS (
        SELECT 1 FROM sys.columns
         WHERE object_id = OBJECT_ID(N'dbo.hp_feedback_ticket')
           AND name = N'location_parts'
    )
    BEGIN
        -- 先删扩展属性（如果存在）
        IF EXISTS (
            SELECT 1 FROM fn_listextendedproperty(
                N'MS_Description',
                N'SCHEMA', N'dbo',
                N'TABLE',  N'hp_feedback_ticket',
                N'COLUMN', N'location_parts')
        )
        BEGIN
            EXEC sp_updateextendedproperty
                N'MS_Description', NULL,
                N'SCHEMA', N'dbo',
                N'TABLE',  N'hp_feedback_ticket',
                N'COLUMN', N'location_parts';
            EXEC sp_dropextendedproperty
                N'MS_Description',
                N'SCHEMA', N'dbo',
                N'TABLE',  N'hp_feedback_ticket',
                N'COLUMN', N'location_parts';
        END

        ALTER TABLE dbo.hp_feedback_ticket DROP COLUMN location_parts;
        PRINT N'[ok] step2: location_parts 列已删除';
    END
    ELSE
        PRINT N'[skip] step2: location_parts 列不存在';
END TRY
BEGIN CATCH
    PRINT N'[warn] step2 失败: ' + ERROR_MESSAGE();
END CATCH
GO

/* ============================================================
   3) 删除 location_text_fuzzy 列 + 它上面所有相关索引
   ============================================================ */
BEGIN TRY
    IF EXISTS (
        SELECT 1 FROM sys.columns
         WHERE object_id = OBJECT_ID(N'dbo.hp_feedback_ticket')
           AND name = N'location_text_fuzzy'
    )
    BEGIN
        -- 3.1 删扩展属性
        IF EXISTS (
            SELECT 1 FROM fn_listextendedproperty(
                N'MS_Description',
                N'SCHEMA', N'dbo',
                N'TABLE',  N'hp_feedback_ticket',
                N'COLUMN', N'location_text_fuzzy')
        )
        BEGIN
            EXEC sp_updateextendedproperty
                N'MS_Description', NULL,
                N'SCHEMA', N'dbo',
                N'TABLE',  N'hp_feedback_ticket',
                N'COLUMN', N'location_text_fuzzy';
            EXEC sp_dropextendedproperty
                N'MS_Description',
                N'SCHEMA', N'dbo',
                N'TABLE',  N'hp_feedback_ticket',
                N'COLUMN', N'location_text_fuzzy';
        END

        -- 3.2 删所有可能存在的索引（按名字枚举最稳妥）
        DECLARE @idx_name SYSNAME;
        DECLARE cur CURSOR LOCAL FAST_FORWARD FOR
            SELECT i.name
              FROM sys.indexes i
             WHERE i.object_id = OBJECT_ID(N'dbo.hp_feedback_ticket')
               AND i.is_hypothetical = 0
               AND i.name IS NOT NULL
               AND EXISTS (
                   SELECT 1 FROM sys.index_columns ic
                    WHERE ic.object_id = i.object_id
                      AND ic.index_id  = i.index_id
                      AND ic.column_id = (
                          SELECT column_id FROM sys.columns
                           WHERE object_id = OBJECT_ID(N'dbo.hp_feedback_ticket')
                             AND name = N'location_text_fuzzy'
                      )
               );
        OPEN cur;
        FETCH NEXT FROM cur INTO @idx_name;
        WHILE @@FETCH_STATUS = 0
        BEGIN
            BEGIN TRY
                -- 必须先在 NVARCHAR 变量里拼接好整条 SQL，再交给 sp_executesql 执行。
                -- 不能直接 EXEC(N'... ' + QUOTENAME(...) + ...')，因为 EXEC(N'...') 内部是
                -- 字符串字面量，函数调用不允许出现在字面量拼接里（报 102 "QUOTENAME 附近语法错误"）。
                DECLARE @drop_sql NVARCHAR(MAX) =
                    N'DROP INDEX ' + QUOTENAME(@idx_name) + N' ON dbo.hp_feedback_ticket';
                EXEC sp_executesql @drop_sql;
                PRINT N'[ok] step3.2: 索引 ' + @idx_name + N' 已删除';
            END TRY
            BEGIN CATCH
                PRINT N'[warn] step3.2: 索引 ' + @idx_name + N' 删除失败: ' + ERROR_MESSAGE();
            END CATCH
            FETCH NEXT FROM cur INTO @idx_name;
        END
        CLOSE cur;
        DEALLOCATE cur;

        -- 3.3 删列
        ALTER TABLE dbo.hp_feedback_ticket DROP COLUMN location_text_fuzzy;
        PRINT N'[ok] step3.3: location_text_fuzzy 列已删除';
    END
    ELSE
        PRINT N'[skip] step3: location_text_fuzzy 列不存在';
END TRY
BEGIN CATCH
    PRINT N'[warn] step3 失败: ' + ERROR_MESSAGE();
END CATCH
GO

/* ============================================================
   4) 兜底：确保新方案 C 列上有索引
   ============================================================ */
BEGIN TRY
    IF NOT EXISTS (
        SELECT 1 FROM sys.indexes
         WHERE object_id = OBJECT_ID(N'dbo.hp_feedback_ticket')
           AND name = N'IX_hp_fb_ticket_loc_dict'
    )
    BEGIN
        IF EXISTS (
            SELECT 1 FROM sys.columns
             WHERE object_id = OBJECT_ID(N'dbo.hp_feedback_ticket')
               AND name = N'location_dict_text'
        )
        BEGIN
            CREATE INDEX IX_hp_fb_ticket_loc_dict
                ON dbo.hp_feedback_ticket(location_dict_text);
            PRINT N'[ok] step4.1: IX_hp_fb_ticket_loc_dict 索引已创建';
        END
    END
    ELSE
        PRINT N'[skip] step4.1: IX_hp_fb_ticket_loc_dict 已存在';
END TRY
BEGIN CATCH
    PRINT N'[warn] step4.1 失败: ' + ERROR_MESSAGE();
END CATCH
GO

BEGIN TRY
    IF NOT EXISTS (
        SELECT 1 FROM sys.indexes
         WHERE object_id = OBJECT_ID(N'dbo.hp_feedback_ticket')
           AND name = N'IX_hp_fb_ticket_loc_user'
    )
    BEGIN
        IF EXISTS (
            SELECT 1 FROM sys.columns
             WHERE object_id = OBJECT_ID(N'dbo.hp_feedback_ticket')
               AND name = N'location_user_text'
        )
        BEGIN
            CREATE INDEX IX_hp_fb_ticket_loc_user
                ON dbo.hp_feedback_ticket(location_user_text);
            PRINT N'[ok] step4.2: IX_hp_fb_ticket_loc_user 索引已创建';
        END
    END
    ELSE
        PRINT N'[skip] step4.2: IX_hp_fb_ticket_loc_user 已存在';
END TRY
BEGIN CATCH
    PRINT N'[warn] step4.2 失败: ' + ERROR_MESSAGE();
END CATCH
GO

PRINT N'========================================';
PRINT N'✅ hp_feedback_ticket 方案 C 清理完成';
PRINT N'   - DROP: location_parts, location_text_fuzzy';
PRINT N'   - INDEX: location_dict_text, location_user_text';
PRINT N'========================================';
GO
