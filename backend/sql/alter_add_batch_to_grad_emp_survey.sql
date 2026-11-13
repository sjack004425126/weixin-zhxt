-- ============================================================
-- 为 zs_graduate_employment_survey 增加 batch 字段
-- 用于记录提交时所属招生类别的当前批次（zs_category.batch）
-- 数据库：MSSQL
-- ============================================================

USE [OA]; -- TODO: 替换为实际数据库名
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.zs_graduate_employment_survey')
      AND name = 'batch'
)
BEGIN
    ALTER TABLE dbo.zs_graduate_employment_survey
        ADD batch INT NULL;
END
GO

-- 可选：为已有历史数据回填批次（按当前 zs_category.batch）
UPDATE s
   SET s.batch = c.batch
  FROM dbo.zs_graduate_employment_survey s
  CROSS APPLY (
      SELECT batch FROM dbo.zs_category WHERE code = 'graduate_employment_survey'
  ) c
 WHERE s.batch IS NULL;
GO

-- 索引（按批次过滤后台列表/统计）
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_zs_grad_emp_survey_batch'
      AND object_id = OBJECT_ID(N'dbo.zs_graduate_employment_survey')
)
BEGIN
    CREATE INDEX IX_zs_grad_emp_survey_batch
        ON dbo.zs_graduate_employment_survey(batch);
END
GO
