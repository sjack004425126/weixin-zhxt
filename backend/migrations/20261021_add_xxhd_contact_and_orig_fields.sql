-- 新生信息核对表 oa_xs_xxhd 扩展字段
-- 创建日期: 2026-10-21
-- 用途: 支持「联系信息」「学籍信息」分组核对 + 原值快照

-- 1. 手机号码
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.oa_xs_xxhd') AND name = 'xs_dh')
BEGIN
    ALTER TABLE [dbo].[oa_xs_xxhd] ADD [xs_dh] varchar(15) COLLATE Chinese_PRC_CI_AS NULL;
    EXEC sp_addextendedproperty 'MS_Description', '手机号码', 'SCHEMA', 'dbo', 'TABLE', 'oa_xs_xxhd', 'COLUMN', 'xs_dh';
END
GO

-- 2. 手机号码核对状态
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.oa_xs_xxhd') AND name = 'xs_dh_status')
BEGIN
    ALTER TABLE [dbo].[oa_xs_xxhd] ADD [xs_dh_status] int NULL;
    EXEC sp_addextendedproperty 'MS_Description', '手机号码核对状态：0-有误已修正 1-无误', 'SCHEMA', 'dbo', 'TABLE', 'oa_xs_xxhd', 'COLUMN', 'xs_dh_status';
END
GO

-- 3. 家庭住址
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.oa_xs_xxhd') AND name = 'xs_zcdd')
BEGIN
    ALTER TABLE [dbo].[oa_xs_xxhd] ADD [xs_zcdd] varchar(50) COLLATE Chinese_PRC_CI_AS NULL;
    EXEC sp_addextendedproperty 'MS_Description', '家庭住址', 'SCHEMA', 'dbo', 'TABLE', 'oa_xs_xxhd', 'COLUMN', 'xs_zcdd';
END
GO

-- 4. 家庭住址核对状态
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.oa_xs_xxhd') AND name = 'xs_zcdd_status')
BEGIN
    ALTER TABLE [dbo].[oa_xs_xxhd] ADD [xs_zcdd_status] int NULL;
    EXEC sp_addextendedproperty 'MS_Description', '家庭住址核对状态：0-有误已修正 1-无误', 'SCHEMA', 'dbo', 'TABLE', 'oa_xs_xxhd', 'COLUMN', 'xs_zcdd_status';
END
GO

-- 5. 原值快照字段
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.oa_xs_xxhd') AND name = 'orig_xs_xm')
BEGIN
    ALTER TABLE [dbo].[oa_xs_xxhd] ADD [orig_xs_xm] varchar(20) COLLATE Chinese_PRC_CI_AS NULL;
    EXEC sp_addextendedproperty 'MS_Description', '核对时姓名原值', 'SCHEMA', 'dbo', 'TABLE', 'oa_xs_xxhd', 'COLUMN', 'orig_xs_xm';
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.oa_xs_xxhd') AND name = 'orig_xs_xb')
BEGIN
    ALTER TABLE [dbo].[oa_xs_xxhd] ADD [orig_xs_xb] varchar(1) COLLATE Chinese_PRC_CI_AS NULL;
    EXEC sp_addextendedproperty 'MS_Description', '核对时性别原值', 'SCHEMA', 'dbo', 'TABLE', 'oa_xs_xxhd', 'COLUMN', 'orig_xs_xb';
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.oa_xs_xxhd') AND name = 'orig_xs_sfzh')
BEGIN
    ALTER TABLE [dbo].[oa_xs_xxhd] ADD [orig_xs_sfzh] varchar(20) COLLATE Chinese_PRC_CI_AS NULL;
    EXEC sp_addextendedproperty 'MS_Description', '核对时身份证号原值', 'SCHEMA', 'dbo', 'TABLE', 'oa_xs_xxhd', 'COLUMN', 'orig_xs_sfzh';
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.oa_xs_xxhd') AND name = 'orig_xs_mz')
BEGIN
    ALTER TABLE [dbo].[oa_xs_xxhd] ADD [orig_xs_mz] varchar(20) COLLATE Chinese_PRC_CI_AS NULL;
    EXEC sp_addextendedproperty 'MS_Description', '核对时民族原值', 'SCHEMA', 'dbo', 'TABLE', 'oa_xs_xxhd', 'COLUMN', 'orig_xs_mz';
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.oa_xs_xxhd') AND name = 'orig_xs_dh')
BEGIN
    ALTER TABLE [dbo].[oa_xs_xxhd] ADD [orig_xs_dh] varchar(15) COLLATE Chinese_PRC_CI_AS NULL;
    EXEC sp_addextendedproperty 'MS_Description', '核对时手机号码原值', 'SCHEMA', 'dbo', 'TABLE', 'oa_xs_xxhd', 'COLUMN', 'orig_xs_dh';
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.oa_xs_xxhd') AND name = 'orig_xs_zcdd')
BEGIN
    ALTER TABLE [dbo].[oa_xs_xxhd] ADD [orig_xs_zcdd] varchar(50) COLLATE Chinese_PRC_CI_AS NULL;
    EXEC sp_addextendedproperty 'MS_Description', '核对时家庭住址原值', 'SCHEMA', 'dbo', 'TABLE', 'oa_xs_xxhd', 'COLUMN', 'orig_xs_zcdd';
END
GO

PRINT 'oa_xs_xxhd 扩展字段添加完成！';
GO

-- 验证
SELECT c.name AS ColumnName, t.name AS DataType
FROM sys.columns c
INNER JOIN sys.types t ON c.user_type_id = t.user_type_id
WHERE c.object_id = OBJECT_ID('dbo.oa_xs_xxhd')
  AND c.name IN ('xs_dh','xs_dh_status','xs_zcdd','xs_zcdd_status',
                 'orig_xs_xm','orig_xs_xb','orig_xs_sfzh','orig_xs_mz','orig_xs_dh','orig_xs_zcdd')
ORDER BY c.column_id;
GO
