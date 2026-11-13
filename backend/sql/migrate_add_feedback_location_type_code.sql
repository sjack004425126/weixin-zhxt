-- ============================================================
-- 反馈地点字典表新增 type_code 列（2026-09-28）
-- 适用：SQL Server 2014+ / 兼容老版本（不用 IF EXISTS / DROP IF EXISTS）
-- ============================================================

-- 1. 加 type_code 列（不存在则加；存在则跳过）
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('hp_feedback_location')
      AND name = 'type_code'
)
BEGIN
    ALTER TABLE hp_feedback_location ADD type_code NVARCHAR(32) NULL;
END
GO

-- 2. 加 type_code 索引（不存在则加）
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('hp_feedback_location')
      AND name = 'IX_hp_fbloc_type_code'
)
BEGIN
    CREATE INDEX IX_hp_fbloc_type_code ON hp_feedback_location(type_code);
END
GO

-- 3. 老节点回填：根据 level 推断 type_code（1=楼栋, 2=楼层, 3=房间）
--    已存在的节点没有 type_code，按它们当前的 level 给个合理值。
--    后续新节点由应用层（前端"新增地点"对话框）传入。
UPDATE hp_feedback_location
SET type_code = CASE level
    WHEN 1 THEN N'楼栋'
    WHEN 2 THEN N'楼层'
    WHEN 3 THEN N'房间号'
    ELSE N'地点'
END
WHERE type_code IS NULL OR type_code = '';
GO

-- 4. 验证
SELECT
    c.name AS column_name,
    TYPE_NAME(c.user_type_id) AS data_type,
    c.max_length,
    c.is_nullable
FROM sys.columns c
WHERE c.object_id = OBJECT_ID('hp_feedback_location')
  AND c.name IN ('id', 'parent_id', 'code', 'name', 'level', 'full_path', 'type_code', 'sort_order', 'is_active')
ORDER BY c.column_id;

SELECT type_code, COUNT(*) AS cnt
FROM hp_feedback_location
WHERE is_active = 1
GROUP BY type_code
ORDER BY type_code;
