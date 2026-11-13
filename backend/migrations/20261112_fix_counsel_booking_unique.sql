-- ============================================================
-- 修复 uq_counsel_slot_xh 唯一约束
--
-- 问题：
--   原约束 UniqueConstraint('slot_id','xh') 不含 status，
--   导致「已取消(cancelled)」的预约仍然占用唯一键，
--   学生取消预约后无法再次预约同一时段（报 2627 重复键）。
--   同时老师手动添加的预约 xh 为空串 ''，多条之间也会互相冲突。
--
-- 方案：
--   删除旧约束，改为 filtered unique index，
--   仅对「未取消 + 真实学号」的记录生效：
--     WHERE status <> 'cancelled' AND xh <> ''
--   幂等：可重复执行
-- ============================================================

-- 1) 删除旧的 UNIQUE 约束（若存在）
--    注意：这里用 RAISERROR 而非 PRINT，保证 ELSE 分支不是空块，
--    在不解析 PRINT 的客户端（如 pyodbc）下也能整段执行。
IF EXISTS (SELECT 1 FROM sys.key_constraints
           WHERE name = 'uq_counsel_slot_xh' AND parent_object_id = OBJECT_ID('dbo.zz_counsel_booking'))
BEGIN
    ALTER TABLE [dbo].[zz_counsel_booking] DROP CONSTRAINT [uq_counsel_slot_xh];
    RAISERROR(N'+ 旧约束 uq_counsel_slot_xh 已删除', 0, 1) WITH NOWAIT;
END
ELSE
    RAISERROR(N'- 旧约束 uq_counsel_slot_xh 不存在，跳过', 0, 1) WITH NOWAIT;
GO

-- 2) 清理历史脏数据：同一 (slot_id, xh) 只保留一条未取消记录，其余标记为 cancelled
--    防止建索引时因历史重复导致失败
--    注意：SQL Server 的 UPDATE 目标表不能带别名，SET 后的列名也不能带表名前缀，
--    因此这里用自连接 + 别名 t 的写法。
UPDATE t
SET status = 'cancelled'
FROM [dbo].[zz_counsel_booking] t
INNER JOIN (
    SELECT slot_id, xh, MIN(id) AS keep_id
    FROM [dbo].[zz_counsel_booking]
    WHERE status <> 'cancelled' AND xh <> ''
    GROUP BY slot_id, xh
) k
    ON t.slot_id = k.slot_id
   AND t.xh = k.xh
WHERE t.status <> 'cancelled'
  AND t.xh <> ''
  AND t.id <> k.keep_id;
RAISERROR(N'历史重复预约已清理', 0, 1) WITH NOWAIT;
GO

-- 3) 创建 filtered unique index
IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = 'uq_counsel_slot_xh_active'
                 AND object_id = OBJECT_ID('dbo.zz_counsel_booking'))
BEGIN
    CREATE UNIQUE INDEX [uq_counsel_slot_xh_active]
        ON [dbo].[zz_counsel_booking] ([slot_id], [xh])
        WHERE [status] <> 'cancelled' AND [xh] <> '';
    RAISERROR(N'+ filtered unique index uq_counsel_slot_xh_active 已创建', 0, 1) WITH NOWAIT;
END
ELSE
    RAISERROR(N'- filtered unique index uq_counsel_slot_xh_active 已存在，跳过', 0, 1) WITH NOWAIT;
GO

-- 4) 验证
SELECT
    i.name AS index_name,
    i.is_unique,
    i.filter_definition
FROM sys.indexes i
WHERE i.object_id = OBJECT_ID('dbo.zz_counsel_booking')
  AND i.name IN ('uq_counsel_slot_xh_active');

RAISERROR(N'心理咨询预约唯一约束修复完成！', 0, 1) WITH NOWAIT;
GO
