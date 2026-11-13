-- ============================================================
-- 反馈字典重构迁移脚本（SQL Server 版本，2026-09-27）
-- 目标：
--   1. feedback_dict: 合并 item -> repair_type（按 label 去重）
--   2. feedback_location: 加 type_code 列（兼容旧的 parent_id/level/full_path）
--   3. feedback_ticket: 加 location_parts 列
-- ============================================================

-- ============== 1. 合并 item -> repair_type ==============
-- 1.1 把 item 中不重复的 label 复制到 repair_type（仅当 repair_type 中不存在该 label 时）
-- code 列长度 32，截断 MD5 串保证不超长
INSERT INTO hp_feedback_dict (category, code, label, sort_order, is_active, is_custom, feedback_type, created_at, updated_at)
SELECT
  'repair_type' AS category,
  LEFT('mig_' + CONVERT(VARCHAR(64), HASHBYTES('MD5', label), 2), 32) AS code,
  label,
  MIN(sort_order),
  1,
  0,
  'both',
  GETDATE(),
  GETDATE()
FROM hp_feedback_dict
WHERE category = 'item' AND is_active = 1
GROUP BY label
HAVING NOT EXISTS (
  SELECT 1 FROM hp_feedback_dict t
  WHERE t.category = 'repair_type' AND t.label = hp_feedback_dict.label
);

-- 1.2 软删除 item 记录
UPDATE hp_feedback_dict SET is_active = 0, updated_at = GETDATE() WHERE category = 'item';

-- ============== 2. feedback_location 加 type_code 列 ==============
IF NOT EXISTS (
  SELECT 1 FROM sys.columns
  WHERE object_id = OBJECT_ID('hp_feedback_location') AND name = 'type_code'
)
BEGIN
  ALTER TABLE hp_feedback_location ADD type_code NVARCHAR(64) NULL;
  -- 简单索引
  IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('hp_feedback_location') AND name = 'ix_feedback_location_type_active')
    CREATE INDEX ix_feedback_location_type_active ON hp_feedback_location (type_code, is_active, sort_order);
END
GO

-- 2.1 level/full_path/parent_id 允许 NULL（兼容历史）
IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('hp_feedback_location') AND name = 'level' AND is_nullable = 0)
  ALTER TABLE hp_feedback_location ALTER COLUMN level INT NULL;
IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('hp_feedback_location') AND name = 'full_path' AND is_nullable = 0)
  ALTER TABLE hp_feedback_location ALTER COLUMN full_path NVARCHAR(255) NULL;
IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('hp_feedback_location') AND name = 'parent_id' AND is_nullable = 0)
  ALTER TABLE hp_feedback_location ALTER COLUMN parent_id INT NULL;
GO

-- 2.2 历史三级数据回填 type_code（level=1→楼栋 / 2→楼层 / 3→房间号）
UPDATE hp_feedback_location
SET type_code = CASE level
  WHEN 1 THEN N'楼栋'
  WHEN 2 THEN N'楼层'
  WHEN 3 THEN N'房间号'
  ELSE N'类型' + ISNULL(CONVERT(NVARCHAR(10), level), '')
END
WHERE type_code IS NULL OR type_code = '';
GO

-- ============== 3. feedback_ticket 加 location_parts 列 ==============
IF NOT EXISTS (
  SELECT 1 FROM sys.columns
  WHERE object_id = OBJECT_ID('hp_feedback_ticket') AND name = 'location_parts'
)
BEGIN
  ALTER TABLE hp_feedback_ticket ADD location_parts NVARCHAR(MAX) NULL;
END
GO

-- 3.1 老数据回填：把 location_text_fuzzy 整段塞进 location_parts（type=未知）
UPDATE hp_feedback_ticket
SET location_parts = '[{"type":"未知","value":"' + ISNULL(location_text_fuzzy, '') + '"}]'
WHERE (location_parts IS NULL OR location_parts = '')
  AND ISNULL(location_text_fuzzy, '') <> '';
GO

-- ============== 验证 ==============
SELECT 'feedback_dict 统计' AS info;
SELECT category, COUNT(*) AS cnt FROM hp_feedback_dict WHERE is_active = 1 GROUP BY category;

SELECT 'feedback_location 类型分布' AS info;
SELECT ISNULL(type_code, '(空)') AS type_code, COUNT(*) AS cnt
FROM hp_feedback_location WHERE is_active = 1 GROUP BY type_code;

SELECT 'feedback_ticket location_parts 填充率' AS info;
SELECT
  COUNT(*) AS total,
  SUM(CASE WHEN location_parts IS NOT NULL AND location_parts <> '' THEN 1 ELSE 0 END) AS filled
FROM hp_feedback_ticket WHERE is_deleted = 0;
GO
