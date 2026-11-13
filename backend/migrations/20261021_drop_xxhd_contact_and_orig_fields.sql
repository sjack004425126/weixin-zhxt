-- oa_xs_xxhd 移除「联系信息」字段与原值快照字段
-- 创建日期: 2026-10-21
-- 用途: 精简核对表结构，删除不再使用的字段
--
-- 删除的列（新增后未被使用，全部为 NULL，无数据丢失）：
--   xs_dh / xs_dh_status        手机号码 + 核对状态
--   xs_zcdd / xs_zcdd_status     家庭住址 + 核对状态
--   orig_xs_xm / orig_xs_xb / orig_xs_sfzh / orig_xs_mz / orig_xs_dh / orig_xs_zcdd
--                                核对时原值快照（6 列）
--
-- 说明：本脚本幂等，列不存在时自动跳过。
-- 对应的后端模型 models.py 与控制器 student_info_verify.py 已同步移除对应定义。

-- 1. 手机号码
IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.oa_xs_xxhd') AND name = 'xs_dh')
BEGIN
    ALTER TABLE [dbo].[oa_xs_xxhd] DROP COLUMN [xs_dh];
END
GO

-- 2. 手机号码核对状态
IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.oa_xs_xxhd') AND name = 'xs_dh_status')
BEGIN
    ALTER TABLE [dbo].[oa_xs_xxhd] DROP COLUMN [xs_dh_status];
END
GO

-- 3. 家庭住址
IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.oa_xs_xxhd') AND name = 'xs_zcdd')
BEGIN
    ALTER TABLE [dbo].[oa_xs_xxhd] DROP COLUMN [xs_zcdd];
END
GO

-- 4. 家庭住址核对状态
IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.oa_xs_xxhd') AND name = 'xs_zcdd_status')
BEGIN
    ALTER TABLE [dbo].[oa_xs_xxhd] DROP COLUMN [xs_zcdd_status];
END
GO

-- 5-10. 原值快照字段
IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.oa_xs_xxhd') AND name = 'orig_xs_xm')
BEGIN
    ALTER TABLE [dbo].[oa_xs_xxhd] DROP COLUMN [orig_xs_xm];
END
GO

IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.oa_xs_xxhd') AND name = 'orig_xs_xb')
BEGIN
    ALTER TABLE [dbo].[oa_xs_xxhd] DROP COLUMN [orig_xs_xb];
END
GO

IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.oa_xs_xxhd') AND name = 'orig_xs_sfzh')
BEGIN
    ALTER TABLE [dbo].[oa_xs_xxhd] DROP COLUMN [orig_xs_sfzh];
END
GO

IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.oa_xs_xxhd') AND name = 'orig_xs_mz')
BEGIN
    ALTER TABLE [dbo].[oa_xs_xxhd] DROP COLUMN [orig_xs_mz];
END
GO

IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.oa_xs_xxhd') AND name = 'orig_xs_dh')
BEGIN
    ALTER TABLE [dbo].[oa_xs_xxhd] DROP COLUMN [orig_xs_dh];
END
GO

IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.oa_xs_xxhd') AND name = 'orig_xs_zcdd')
BEGIN
    ALTER TABLE [dbo].[oa_xs_xxhd] DROP COLUMN [orig_xs_zcdd];
END
GO

PRINT 'oa_xs_xxhd 字段精简完成！';
GO

-- 验证
SELECT c.name AS ColumnName, t.name AS DataType
FROM sys.columns c
INNER JOIN sys.types t ON c.user_type_id = t.user_type_id
WHERE c.object_id = OBJECT_ID('dbo.oa_xs_xxhd')
ORDER BY c.column_id;
GO
