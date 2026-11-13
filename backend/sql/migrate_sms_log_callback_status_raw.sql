-- ============================================================
-- sms_log.callback_status 扩容：varchar(100) -> nvarchar(1000)
-- 2026-11-01
--
-- 背景：
--   callback_status 原先存腾讯云回执的解析态（'SUCCESS' / 'FAIL'），
--   现改为直接存**腾讯云回调的原始 JSON 报文**（不解析、不改写）。
--   原 varchar(100) 装不下原始报文（典型报文约 220~235 字符），
--   故扩为 nvarchar(1000)。
--
--   说明：callback_desc 保持原逻辑不变（仍存解析后的可读描述）。
--
-- 兼容：SQL Server 2014+ / 老版本（不用 IF EXISTS / DROP IF EXISTS）
-- ============================================================

-- 1. 扩列（nvarchar 需先转成大字段类型才能改宽度）
IF COL_LENGTH('sms_log', 'callback_status') IS NOT NULL
BEGIN
    -- 先转 text（大字段），再转回 nvarchar(1000)
    ALTER TABLE sms_log ALTER COLUMN callback_status NVARCHAR(1000) NULL;
END
GO

-- 2. 验证列定义
SELECT
    c.name AS column_name,
    TYPE_NAME(c.user_type_id) AS data_type,
    c.max_length AS max_length_bytes,
    c.is_nullable
FROM sys.columns c
WHERE c.object_id = OBJECT_ID('sms_log')
  AND c.name IN ('id', 'cpSubID', 'status_desc', 'callback_status', 'callback_desc')
ORDER BY c.column_id;
GO
