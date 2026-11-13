-- ============================================================
-- 教师头像字段迁移脚本 (MSSQL / SQL Server)
-- 文件: e:\MyPrj\zhxt\zhpt-new\backend\migrations\20260912_add_teacher_headphoto.sql
-- 执行: sqlcmd -S <server> -d <dbname> -i 20260912_add_teacher_headphoto.sql
-- 或在 SSMS 中打开执行
-- ============================================================
-- 说明：使用 INFORMATION_SCHEMA.COLUMNS 视图代替 sys.columns，
--      避免不同版本 ODBC 驱动解析 object_id 列名的兼容问题。
--      该视图是 SQL-92 标准，所有 MSSQL 版本都支持。
-- ============================================================

-- 1. 幂等添加字段
IF EXISTS (
    SELECT 1
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'dbo'
      AND TABLE_NAME   = 'oa_t'
      AND COLUMN_NAME  = 'headphoto'
)
BEGIN
    PRINT '[SKIP] dbo.oa_t.headphoto 字段已存在，跳过添加';
END
ELSE
BEGIN
    ALTER TABLE dbo.oa_t ADD headphoto INT NOT NULL DEFAULT 0;
    PRINT '[OK] dbo.oa_t.headphoto 字段已添加';
END
GO

-- 2. 添加字段说明（MSSQL 用存储过程）
-- 注意：MSSQL 要求 DECLARE 在批处理最前面，所以这里不能用 IF EXISTS 包 DECLARE
DECLARE @colid INT = (
    SELECT c.column_id
    FROM sys.columns c
    WHERE c.object_id = OBJECT_ID('dbo.oa_t')
      AND c.name = 'headphoto'
);

IF @colid IS NOT NULL
   AND NOT EXISTS (
       SELECT 1
       FROM sys.extended_properties
       WHERE major_id = OBJECT_ID('dbo.oa_t')
         AND minor_id = @colid
         AND class = 1
         AND name = 'MS_Description'
   )
BEGIN
    EXEC sp_addextendedproperty
        @name = N'MS_Description',
        @value = N'是否有照片 0-无 1-有',
        @level0type = N'SCHEMA', @level0name = N'dbo',
        @level1type = N'TABLE',  @level1name = N'oa_t',
        @level2type = N'COLUMN', @level2name = N'headphoto';
    PRINT '[OK] 字段说明已添加';
END
ELSE
BEGIN
    PRINT '[SKIP] 字段说明已存在或字段不存在，跳过';
END
GO

PRINT '==== headphoto 字段迁移完成 ====';
GO
