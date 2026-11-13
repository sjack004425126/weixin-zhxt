-- ============================================================
-- 迁移：教师表 oa_t 增加微信 openid 绑定字段
--
-- 背景：
--   教师端（开放教师 / 中职教师）新增"微信一键登录"（openid 登录）。
--   首次仍需通过「手机号快捷登录」一次，后端会把 openid 写入 oa_t，
--   之后即可直接用 openid 登录。
--
-- 新增列：
--   t_wx_openid       NVARCHAR(200) NULL  微信 openid
--   t_wx_openid_hash  NVARCHAR(64)  NULL  openid 的 SHA256 哈希（隐私合规存储）
--
-- 数据库：SQL Server
-- 执行方式：SSMS / Azure Data Studio 中打开本文件直接运行（可重复执行，幂等）
-- ============================================================

USE [你的数据库名]  -- ← 改成实际库名，例如 USE [zhpt]
GO

-- ------------------------------------------------------------
-- 0) 前置检查：确认目标表存在
-- ------------------------------------------------------------
IF OBJECT_ID(N'dbo.oa_t', N'U') IS NULL
BEGIN
    PRINT '✗ 错误：找不到表 dbo.oa_t，请确认数据库名/表名后重试';
    RETURN;
END
GO

-- ------------------------------------------------------------
-- 1) 新增列 t_wx_openid
-- ------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id = OBJECT_ID(N'dbo.oa_t')
                 AND name = 't_wx_openid')
BEGIN
    ALTER TABLE dbo.oa_t ADD t_wx_openid NVARCHAR(200) NULL;
    PRINT '+ oa_t.t_wx_openid 已添加';
END
ELSE
    PRINT '- oa_t.t_wx_openid 已存在，跳过';
GO

-- ------------------------------------------------------------
-- 2) 新增列 t_wx_openid_hash
-- ------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id = OBJECT_ID(N'dbo.oa_t')
                 AND name = 't_wx_openid_hash')
BEGIN
    ALTER TABLE dbo.oa_t ADD t_wx_openid_hash NVARCHAR(64) NULL;
    PRINT '+ oa_t.t_wx_openid_hash 已添加';
END
ELSE
    PRINT '- oa_t.t_wx_openid_hash 已存在，跳过';
GO

-- ------------------------------------------------------------
-- 3) 唯一索引：同一 openid 只允许绑定一个教师
--    ⚠️ 若下面报表存在重复值，索引创建会失败，请先清理
-- ------------------------------------------------------------
-- 【检查重复 openid】（有结果则需要人工处理）
SELECT t_wx_openid, COUNT(*) AS cnt
FROM dbo.oa_t
WHERE t_wx_openid IS NOT NULL AND LTRIM(RTRIM(t_wx_openid)) <> ''
GROUP BY t_wx_openid
HAVING COUNT(*) > 1;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE object_id = OBJECT_ID(N'dbo.oa_t')
                 AND name = N'ux_oa_t_wx_openid')
BEGIN
    -- 过滤索引：只对非空值建唯一约束，避免历史 NULL 行互相冲突
    CREATE UNIQUE NONCLUSTERED INDEX ux_oa_t_wx_openid
        ON dbo.oa_t (t_wx_openid)
        WHERE t_wx_openid IS NOT NULL;
    PRINT '+ ux_oa_t_wx_openid 唯一索引已创建';
END
ELSE
    PRINT '- ux_oa_t_wx_openid 已存在，跳过';
GO

-- ------------------------------------------------------------
-- 4) 验证结果
-- ------------------------------------------------------------
SELECT
    't_wx_openid' AS col_name,
    COUNT(*)                                              AS total_rows,
    SUM(CASE WHEN t_wx_openid IS NULL THEN 1 ELSE 0 END) AS null_count,
    SUM(CASE WHEN t_wx_openid IS NOT NULL THEN 1 ELSE 0 END) AS filled_count
FROM dbo.oa_t
UNION ALL
SELECT
    't_wx_openid_hash',
    COUNT(*),
    SUM(CASE WHEN t_wx_openid_hash IS NULL THEN 1 ELSE 0 END),
    SUM(CASE WHEN t_wx_openid_hash IS NOT NULL THEN 1 ELSE 0 END)
FROM dbo.oa_t;
GO

-- ============================================================
-- 5) 顺带自检：学生端 openid 字段是否已存在
--    （开放学生表是 oa_xs，中职学生表是 zz_xs）
-- ============================================================
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

-- ============================================================
-- 说明
-- ------------------------------------------------------------
-- 1) 新字段默认为空，历史教师需要先做一次「手机号快捷登录」才会写入 openid。
-- 2) openid 与 hash 由后端自动维护，前端无需传。
-- 3) 中职教师与开放教师共用 oa_t 表，同一微信在两端只能绑定一个教师身份。
-- 4) 绑定规则：字段为空才写；已被他人占用时踢掉旧绑定再写入。
-- ============================================================
