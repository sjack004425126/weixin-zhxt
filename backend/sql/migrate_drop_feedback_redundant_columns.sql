-- ============================================================
-- 反馈工单废弃列清理 DDL（2026-09-27）
-- 适用于：SQL Server 2016 SP1+ / SSMS / sqlcmd
-- 特点：纯 DDL，无 cursor、无 EXEC 拼接，兼容性最好
-- ============================================================

-- ===================== 1. 删索引（按实际查到的索引名） =====================
-- 注意：当前 SQL Server 不支持 DROP INDEX IF EXISTS，所以重复执行遇到"不存在"请忽略。
DROP INDEX IX_hp_fbticket_location ON hp_feedback_ticket;
DROP INDEX IX_hp_fbticket_repair_type ON hp_feedback_ticket;
GO

-- 兼容其它历史命名（已删过的会报"不存在"，忽略即可）
DROP INDEX idx_hp_feedback_ticket_location_id ON hp_feedback_ticket;
DROP INDEX ix_hp_feedback_ticket_location_id ON hp_feedback_ticket;
DROP INDEX hp_feedback_ticket_location_id_idx ON hp_feedback_ticket;
DROP INDEX idx_hp_feedback_ticket_repair_type_code ON hp_feedback_ticket;
DROP INDEX ix_hp_feedback_ticket_repair_type_code ON hp_feedback_ticket;
DROP INDEX hp_feedback_ticket_repair_type_code_idx ON hp_feedback_ticket;
GO

-- ===================== 2. 删列（逐条独立，可重入） =====================
-- 之前已部分执行过的列不会再报"不存在"以外的新错误。
-- 一条 GO 一条，按需手动注释已删的。
-- 有 DEFAULT 约束的列需要先 DROP CONSTRAINT 再 DROP COLUMN。

-- ---------- repair_type_code ----------
-- DEFAULT 约束已不存在（已删除），直接删列即可
ALTER TABLE hp_feedback_ticket DROP COLUMN repair_type_code;
GO

-- ---------- repair_type_label ----------
-- repair_type_label 上无 DEFAULT 约束（已确认），直接删列即可
ALTER TABLE hp_feedback_ticket DROP COLUMN repair_type_label;
GO

-- ---------- scene / scene_custom ----------
-- scene 上的索引（如有）
DROP INDEX IX_hp_fbticket_scene ON hp_feedback_ticket;
DROP INDEX ix_hp_feedback_ticket_scene ON hp_feedback_ticket;
DROP INDEX idx_hp_feedback_ticket_scene ON hp_feedback_ticket;
GO
-- 先删可能的 DEFAULT 约束
ALTER TABLE hp_feedback_ticket DROP CONSTRAINT DF_hp_fbticket_scene;
GO
ALTER TABLE hp_feedback_ticket DROP COLUMN scene;
GO
ALTER TABLE hp_feedback_ticket DROP COLUMN scene_custom;
GO

-- ===================== 3. 验证 =====================
SELECT
    c.name AS column_name,
    TYPE_NAME(c.user_type_id) AS data_type,
    c.max_length,
    c.is_nullable
FROM sys.columns c
WHERE c.object_id = OBJECT_ID('hp_feedback_ticket')
ORDER BY c.column_id;
