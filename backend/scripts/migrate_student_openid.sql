-- ============================================================
-- 迁移：学生表增加微信 openid 绑定字段（自检 + 补齐）
--
-- 背景：
--   开放学生（oa_xs）与中职学生（zz_xs）的"微信一键登录"依赖
--   xs_wx_openid / xs_wx_openid_hash 两列。
--   本脚本幂等：已存在则跳过，缺失则补齐。
--
-- 数据库：SQL Server
-- ============================================================

USE [你的数据库名]  -- ← 改成实际库名
GO

-- ------------------------------------------------------------
-- 1) 开放学生表 oa_xs
-- ------------------------------------------------------------
IF OBJECT_ID(N'dbo.oa_xs', N'U') IS NOT NULL
BEGIN
    IF NOT EXISTS (SELECT 1 FROM sys.columns
                   WHERE object_id = OBJECT_ID(N'dbo.oa_xs')
                     AND name = 'xs_wx_openid')
    BEGIN
        ALTER TABLE dbo.oa_xs ADD xs_wx_openid NVARCHAR(50) NULL;
        PRINT '+ oa_xs.xs_wx_openid 已添加';
    END
    ELSE
        PRINT '- oa_xs.xs_wx_openid 已存在，跳过';

    IF NOT EXISTS (SELECT 1 FROM sys.columns
                   WHERE object_id = OBJECT_ID(N'dbo.oa_xs')
                     AND name = 'xs_wx_openid_hash')
    BEGIN
        ALTER TABLE dbo.oa_xs ADD xs_wx_openid_hash NVARCHAR(64) NULL;
        PRINT '+ oa_xs.xs_wx_openid_hash 已添加';
    END
    ELSE
        PRINT '- oa_xs.xs_wx_openid_hash 已存在，跳过';
END
ELSE
    PRINT '! 表 dbo.oa_xs 不存在，跳过';
GO

-- ------------------------------------------------------------
-- 2) 中职学生表 zz_xs
-- ------------------------------------------------------------
IF OBJECT_ID(N'dbo.zz_xs', N'U') IS NOT NULL
BEGIN
    IF NOT EXISTS (SELECT 1 FROM sys.columns
                   WHERE object_id = OBJECT_ID(N'dbo.zz_xs')
                     AND name = 'xs_wx_openid')
    BEGIN
        ALTER TABLE dbo.zz_xs ADD xs_wx_openid NVARCHAR(200) NULL;
        PRINT '+ zz_xs.xs_wx_openid 已添加';
    END
    ELSE
        PRINT '- zz_xs.xs_wx_openid 已存在，跳过';

    IF NOT EXISTS (SELECT 1 FROM sys.columns
                   WHERE object_id = OBJECT_ID(N'dbo.zz_xs')
                     AND name = 'xs_wx_openid_hash')
    BEGIN
        ALTER TABLE dbo.zz_xs ADD xs_wx_openid_hash NVARCHAR(64) NULL;
        PRINT '+ zz_xs.xs_wx_openid_hash 已添加';
    END
    ELSE
        PRINT '- zz_xs.xs_wx_openid_hash 已存在，跳过';
END
ELSE
    PRINT '! 表 dbo.zz_xs 不存在，跳过';
GO

-- ------------------------------------------------------------
-- 3) 唯一索引（过滤索引，只约束非空值）
-- ------------------------------------------------------------
IF OBJECT_ID(N'dbo.oa_xs', N'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE object_id = OBJECT_ID(N'dbo.oa_xs')
                     AND name = N'ux_oa_xs_wx_openid')
BEGIN
    CREATE UNIQUE NONCLUSTERED INDEX ux_oa_xs_wx_openid
        ON dbo.oa_xs (xs_wx_openid)
        WHERE xs_wx_openid IS NOT NULL;
    PRINT '+ ux_oa_xs_wx_openid 已创建';
END
GO

IF OBJECT_ID(N'dbo.zz_xs', N'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE object_id = OBJECT_ID(N'dbo.zz_xs')
                     AND name = N'ux_zz_xs_wx_openid')
BEGIN
    CREATE UNIQUE NONCLUSTERED INDEX ux_zz_xs_wx_openid
        ON dbo.zz_xs (xs_wx_openid)
        WHERE xs_wx_openid IS NOT NULL;
    PRINT '+ ux_zz_xs_wx_openid 已创建';
END
GO

-- ------------------------------------------------------------
-- 4) 验证
-- ------------------------------------------------------------
SELECT
    OBJECT_NAME(object_id) AS table_name,
    name                  AS column_name,
    type_name(user_type_id) AS data_type,
    max_length            AS max_length
FROM sys.columns
WHERE name IN ('xs_wx_openid', 'xs_wx_openid_hash')
  AND OBJECT_NAME(object_id) IN ('oa_xs', 'zz_xs')
ORDER BY table_name, column_name;
GO

-- ------------------------------------------------------------
-- 5) 重复值检查（有结果需人工清理，否则唯一索引会失败）
-- ------------------------------------------------------------
SELECT 'oa_xs' AS src, xs_wx_openid, COUNT(*) AS cnt
FROM dbo.oa_xs
WHERE xs_wx_openid IS NOT NULL AND LTRIM(RTRIM(xs_wx_openid)) <> ''
GROUP BY xs_wx_openid HAVING COUNT(*) > 1
UNION ALL
SELECT 'zz_xs', xs_wx_openid, COUNT(*)
FROM dbo.zz_xs
WHERE xs_wx_openid IS NOT NULL AND LTRIM(RTRIM(xs_wx_openid)) <> ''
GROUP BY xs_wx_openid HAVING COUNT(*) > 1;
GO
