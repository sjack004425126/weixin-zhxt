/* ============================================================
   校园反馈 - 地点类型排序字段（2026-09-29）

   背景：
     原方案 C 把"地点类型"用 type_code 字符串扁平化存在 hp_feedback_location 里。
     /location/types 接口以"该 type_code 下所有 value 项的最小 sort_order"作为"类型排序"。
     这导致类型整体排序无法独立调整（必须改 value 项的 sort_order），管理页无法
     直接修改"地点类型"的排序字段。

   方案：
     新建独立表 hp_feedback_location_type 存储 (type_code, sort_order)：
     - type_code  : PK，业务主键
     - sort_order : 排序，越小越靠前
     - created_at / updated_at : 维护字段

   兼容：
     首次执行：把所有现有 type_code 同步进新表（用现有"最小 sort_order"做初始值）
   ============================================================ */

SET NOCOUNT ON;
GO

IF OBJECT_ID(N'dbo.hp_feedback_location_type', N'U') IS NOT NULL
BEGIN
    PRINT N'ℹ️  dbo.hp_feedback_location_type 表已存在，跳过';
    RETURN;
END
GO

CREATE TABLE dbo.hp_feedback_location_type (
    type_code   NVARCHAR(64)  NOT NULL,
    sort_order  INT           NOT NULL DEFAULT 0,
    created_at  DATETIME      NOT NULL DEFAULT GETDATE(),
    updated_at  DATETIME      NOT NULL DEFAULT GETDATE(),
    CONSTRAINT PK_hp_fb_loc_type PRIMARY KEY CLUSTERED (type_code)
);
GO

CREATE INDEX IX_hp_fb_loc_type_sort
    ON dbo.hp_feedback_location_type(sort_order, type_code);
GO

EXEC dbo.sp_set_column_comment
    N'dbo', N'hp_feedback_location_type', N'type_code',
    N'地点类型编码（与 hp_feedback_location.type_code 对应）';
EXEC dbo.sp_set_column_comment
    N'dbo', N'hp_feedback_location_type', N'sort_order',
    N'类型排序：越小越靠前；用于工单筛选弹窗左侧分组顺序';
GO

/* 初始化：把现有 type_code 全部同步进新表，sort_order 取该 type 下所有 value 的最小 sort_order */
IF OBJECT_ID(N'dbo.hp_feedback_location', N'U') IS NOT NULL
BEGIN
    ;WITH src AS (
        SELECT type_code, MIN(ISNULL(sort_order, 0)) AS min_sort
          FROM dbo.hp_feedback_location
         WHERE type_code IS NOT NULL AND type_code <> ''
         GROUP BY type_code
    )
    INSERT INTO dbo.hp_feedback_location_type (type_code, sort_order)
    SELECT type_code, min_sort FROM src;

    PRINT N'✅ 已从 hp_feedback_location 同步 ' + CAST(@@ROWCOUNT AS NVARCHAR(10)) + N' 个 type_code';
END
GO

PRINT N'✅ hp_feedback_location_type 表已创建';
GO
