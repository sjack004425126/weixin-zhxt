-- ============================================================
-- 报名查询码功能 - SQL Server 数据库变更脚本
-- 为4个报名表添加 query_code（8位查询码）和 query_code_expire（过期时间）字段
-- 执行环境：SQL Server
-- ============================================================

-- 1. 成人高等教育预报名表 zs_adult_enrollment
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('zs_adult_enrollment') AND name = 'query_code')
BEGIN
    ALTER TABLE zs_adult_enrollment ADD query_code VARCHAR(20) NULL;
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('zs_adult_enrollment') AND name = 'query_code_expire')
BEGIN
    ALTER TABLE zs_adult_enrollment ADD query_code_expire DATETIME NULL;
END
GO

-- 创建唯一索引（排除NULL值）
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_zs_adult_enrollment_query_code' AND object_id = OBJECT_ID('zs_adult_enrollment'))
BEGIN
    CREATE UNIQUE NONCLUSTERED INDEX IX_zs_adult_enrollment_query_code
    ON zs_adult_enrollment(query_code)
    WHERE query_code IS NOT NULL;
END
GO


-- 2. 3+4中本贯通报名表 zs_vocational34_enrollment
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('zs_vocational34_enrollment') AND name = 'query_code')
BEGIN
    ALTER TABLE zs_vocational34_enrollment ADD query_code VARCHAR(20) NULL;
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('zs_vocational34_enrollment') AND name = 'query_code_expire')
BEGIN
    ALTER TABLE zs_vocational34_enrollment ADD query_code_expire DATETIME NULL;
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_zs_vocational34_enrollment_query_code' AND object_id = OBJECT_ID('zs_vocational34_enrollment'))
BEGIN
    CREATE UNIQUE NONCLUSTERED INDEX IX_zs_vocational34_enrollment_query_code
    ON zs_vocational34_enrollment(query_code)
    WHERE query_code IS NOT NULL;
END
GO


-- 3. 毕业生就业调查表 zs_graduate_employment_survey
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('zs_graduate_employment_survey') AND name = 'query_code')
BEGIN
    ALTER TABLE zs_graduate_employment_survey ADD query_code VARCHAR(20) NULL;
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('zs_graduate_employment_survey') AND name = 'query_code_expire')
BEGIN
    ALTER TABLE zs_graduate_employment_survey ADD query_code_expire DATETIME NULL;
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_zs_graduate_employment_survey_query_code' AND object_id = OBJECT_ID('zs_graduate_employment_survey'))
BEGIN
    CREATE UNIQUE NONCLUSTERED INDEX IX_zs_graduate_employment_survey_query_code
    ON zs_graduate_employment_survey(query_code)
    WHERE query_code IS NOT NULL;
END
GO


-- 4. 中职报名学生表 zz_bmxs
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('zz_bmxs') AND name = 'query_code')
BEGIN
    ALTER TABLE zz_bmxs ADD query_code VARCHAR(20) NULL;
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('zz_bmxs') AND name = 'query_code_expire')
BEGIN
    ALTER TABLE zz_bmxs ADD query_code_expire DATETIME NULL;
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_zz_bmxs_query_code' AND object_id = OBJECT_ID('zz_bmxs'))
BEGIN
    CREATE UNIQUE NONCLUSTERED INDEX IX_zz_bmxs_query_code
    ON zz_bmxs(query_code)
    WHERE query_code IS NOT NULL;
END
GO


-- ============================================================
-- 验证执行结果
-- ============================================================
SELECT 'zs_adult_enrollment' AS table_name, name AS column_name, TYPE_NAME(system_type_id) AS data_type
FROM sys.columns WHERE object_id = OBJECT_ID('zs_adult_enrollment') AND name IN ('query_code', 'query_code_expire')
UNION ALL
SELECT 'zs_vocational34_enrollment', name, TYPE_NAME(system_type_id)
FROM sys.columns WHERE object_id = OBJECT_ID('zs_vocational34_enrollment') AND name IN ('query_code', 'query_code_expire')
UNION ALL
SELECT 'zs_graduate_employment_survey', name, TYPE_NAME(system_type_id)
FROM sys.columns WHERE object_id = OBJECT_ID('zs_graduate_employment_survey') AND name IN ('query_code', 'query_code_expire')
UNION ALL
SELECT 'zz_bmxs', name, TYPE_NAME(system_type_id)
FROM sys.columns WHERE object_id = OBJECT_ID('zz_bmxs') AND name IN ('query_code', 'query_code_expire');
GO


-- ============================================================
-- 5. 开放新生缴费订单表 wxxs_xf_payinfo
-- ============================================================
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('wxxs_xf_payinfo') AND name = 'query_code')
BEGIN
    ALTER TABLE wxxs_xf_payinfo ADD query_code VARCHAR(20) NULL;
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('wxxs_xf_payinfo') AND name = 'query_code_expire')
BEGIN
    ALTER TABLE wxxs_xf_payinfo ADD query_code_expire DATETIME NULL;
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_wxxs_xf_payinfo_query_code' AND object_id = OBJECT_ID('wxxs_xf_payinfo'))
BEGIN
    CREATE UNIQUE NONCLUSTERED INDEX IX_wxxs_xf_payinfo_query_code
    ON wxxs_xf_payinfo(query_code)
    WHERE query_code IS NOT NULL;
END
GO
