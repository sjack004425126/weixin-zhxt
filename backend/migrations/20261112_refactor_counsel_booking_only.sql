-- ============================================================
-- 心理咨询预约模块重构：纯预约制（去掉叫号/签到/排队）
--
-- 变更概要
-- --------
-- zz_counsel_schedule
--   删除 location           -> 地点下沉到号段级（每号段可不同）
--   删除 room_name         -> 同上
--   删除 checkin_code      -> 不再签到
--   删除 avg_minutes       -> 不再统计叫号耗时
--   删除 current_booking_id-> 不再叫号
--   counsel_date 改为可空  -> 日期以号段级 counsel_date 为准
--
-- zz_counsel_slot
--   新增 counsel_date      -> 号段级日期（控制排某天）
--   新增 location          -> 号段级诊疗地点
--   删除 booked_count      -> 冗余计数，改实时统计
--   category 收窄为 nvarchar(50)
--
-- zz_counsel_booking
--   删除 queue_seq / is_late / call_round
--   删除 sign_time / call_time / first_call_time / done_time / serve_seconds
--   room_name 扩到 nvarchar(100)（存诊疗地点）
--   category 收窄为 nvarchar(50)，phone_suffix 收窄为 nvarchar(4)
--   status 语义收敛为 booked / attended / cancelled
--   索引 ix_counsel_slot_queue -> ix_counsel_slot_seq
--
-- 执行顺序说明
--   slot.location 的存量回填依赖 schedule.location / schedule.room_name，
--   因此必须「先加 slot 新列并回填」再「删 schedule 旧列」。
--
-- 幂等：可重复执行
-- ============================================================


-- ============================================================
-- 步骤 1：zz_counsel_slot 新增 counsel_date
-- ============================================================
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.zz_counsel_slot') AND name = 'counsel_date')
BEGIN
    ALTER TABLE [dbo].[zz_counsel_slot] ADD [counsel_date] datetime NULL;
    RAISERROR(N'+ slot.counsel_date 已新增', 0, 1) WITH NOWAIT;
END
GO

-- 存量回填：号段日期取 start_time 的日期部分
UPDATE [dbo].[zz_counsel_slot]
SET [counsel_date] = CAST(CAST([start_time] AS date) AS datetime)
WHERE [counsel_date] IS NULL;
RAISERROR(N'+ slot.counsel_date 存量已回填', 0, 1) WITH NOWAIT;
GO


-- ============================================================
-- 步骤 2：zz_counsel_slot 新增 location
-- ============================================================
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.zz_counsel_slot') AND name = 'location')
BEGIN
    ALTER TABLE [dbo].[zz_counsel_slot] ADD [location] nvarchar(100) NULL;
    RAISERROR(N'+ slot.location 已新增', 0, 1) WITH NOWAIT;
END
GO

-- 存量回填：地点优先取该号段的预约快照，其次取同场次其他号段的地点
-- （schedule.location / room_name 可能已在历史迁移中删除，故不依赖它们）
UPDATE s
SET s.[location] = b.[loc]
FROM [dbo].[zz_counsel_slot] s
INNER JOIN (
    SELECT [slot_id] AS sid, MAX([room_name]) AS [loc]
    FROM [dbo].[zz_counsel_booking]
    WHERE [room_name] IS NOT NULL AND [room_name] <> ''
    GROUP BY [slot_id]
) b ON b.sid = s.[id]
WHERE s.[location] IS NULL;
RAISERROR(N'+ slot.location 存量已从预约快照回填', 0, 1) WITH NOWAIT;
GO

UPDATE s
SET s.[location] = b.[loc]
FROM [dbo].[zz_counsel_slot] s
INNER JOIN (
    SELECT sl.[schedule_id] AS scid, MAX(sl2.[location]) AS [loc]
    FROM [dbo].[zz_counsel_slot] sl
    INNER JOIN [dbo].[zz_counsel_slot] sl2 ON sl2.[schedule_id] = sl.[schedule_id]
    WHERE sl2.[location] IS NOT NULL AND sl2.[location] <> ''
    GROUP BY sl.[schedule_id]
) b ON b.scid = s.[schedule_id]
WHERE s.[location] IS NULL;
RAISERROR(N'+ slot.location 存量已从同场次号段回填', 0, 1) WITH NOWAIT;
GO


-- ============================================================
-- 步骤 3：zz_counsel_schedule 删除旧列
-- ============================================================
IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.zz_counsel_schedule') AND name = 'location')
BEGIN
    ALTER TABLE [dbo].[zz_counsel_schedule] DROP COLUMN [location];
    RAISERROR(N'- schedule.location 已删除', 0, 1) WITH NOWAIT;
END
GO

IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.zz_counsel_schedule') AND name = 'room_name')
BEGIN
    ALTER TABLE [dbo].[zz_counsel_schedule] DROP COLUMN [room_name];
    RAISERROR(N'- schedule.room_name 已删除', 0, 1) WITH NOWAIT;
END
GO

IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.zz_counsel_schedule') AND name = 'checkin_code')
BEGIN
    ALTER TABLE [dbo].[zz_counsel_schedule] DROP COLUMN [checkin_code];
    RAISERROR(N'- schedule.checkin_code 已删除', 0, 1) WITH NOWAIT;
END
GO

IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.zz_counsel_schedule') AND name = 'avg_minutes')
BEGIN
    ALTER TABLE [dbo].[zz_counsel_schedule] DROP COLUMN [avg_minutes];
    RAISERROR(N'- schedule.avg_minutes 已删除', 0, 1) WITH NOWAIT;
END
GO

IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.zz_counsel_schedule') AND name = 'current_booking_id')
BEGIN
    ALTER TABLE [dbo].[zz_counsel_schedule] DROP COLUMN [current_booking_id];
    RAISERROR(N'- schedule.current_booking_id 已删除', 0, 1) WITH NOWAIT;
END
GO

-- counsel_date 改为可空
IF EXISTS (SELECT 1 FROM sys.columns
           WHERE object_id = OBJECT_ID('dbo.zz_counsel_schedule')
             AND name = 'counsel_date' AND is_nullable = 0)
BEGIN
    ALTER TABLE [dbo].[zz_counsel_schedule] ALTER COLUMN [counsel_date] datetime NULL;
    RAISERROR(N'+ schedule.counsel_date 已改为可空', 0, 1) WITH NOWAIT;
END
GO


-- ============================================================
-- 步骤 4：zz_counsel_slot 删除冗余列 + 收窄字段
-- ============================================================
IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.zz_counsel_slot') AND name = 'booked_count')
BEGIN
    ALTER TABLE [dbo].[zz_counsel_slot] DROP COLUMN [booked_count];
    RAISERROR(N'- slot.booked_count 已删除', 0, 1) WITH NOWAIT;
END
GO

IF EXISTS (SELECT 1 FROM sys.columns
           WHERE object_id = OBJECT_ID('dbo.zz_counsel_slot')
             AND name = 'category' AND max_length <> 100)
BEGIN
    ALTER TABLE [dbo].[zz_counsel_slot] ALTER COLUMN [category] nvarchar(50) NULL;
    RAISERROR(N'+ slot.category 已收窄为 nvarchar(50)', 0, 1) WITH NOWAIT;
END
GO


-- ============================================================
-- 步骤 5：删除依赖 queue_seq 的旧索引（必须在删 queue_seq 列之前）
-- ============================================================
IF EXISTS (SELECT 1 FROM sys.indexes
           WHERE name = 'ix_counsel_slot_queue'
             AND object_id = OBJECT_ID('dbo.zz_counsel_booking'))
BEGIN
    DROP INDEX [ix_counsel_slot_queue] ON [dbo].[zz_counsel_booking];
    RAISERROR(N'- 旧索引 ix_counsel_slot_queue 已删除', 0, 1) WITH NOWAIT;
END
GO


-- ============================================================
-- 步骤 6：zz_counsel_booking 删除叫号相关列
-- ============================================================
IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.zz_counsel_booking') AND name = 'queue_seq')
BEGIN
    ALTER TABLE [dbo].[zz_counsel_booking] DROP COLUMN [queue_seq];
    RAISERROR(N'- booking.queue_seq 已删除', 0, 1) WITH NOWAIT;
END
GO

IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.zz_counsel_booking') AND name = 'is_late')
BEGIN
    ALTER TABLE [dbo].[zz_counsel_booking] DROP COLUMN [is_late];
    RAISERROR(N'- booking.is_late 已删除', 0, 1) WITH NOWAIT;
END
GO

IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.zz_counsel_booking') AND name = 'call_round')
BEGIN
    ALTER TABLE [dbo].[zz_counsel_booking] DROP COLUMN [call_round];
    RAISERROR(N'- booking.call_round 已删除', 0, 1) WITH NOWAIT;
END
GO

IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.zz_counsel_booking') AND name = 'sign_time')
BEGIN
    ALTER TABLE [dbo].[zz_counsel_booking] DROP COLUMN [sign_time];
    RAISERROR(N'- booking.sign_time 已删除', 0, 1) WITH NOWAIT;
END
GO

IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.zz_counsel_booking') AND name = 'call_time')
BEGIN
    ALTER TABLE [dbo].[zz_counsel_booking] DROP COLUMN [call_time];
    RAISERROR(N'- booking.call_time 已删除', 0, 1) WITH NOWAIT;
END
GO

IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.zz_counsel_booking') AND name = 'first_call_time')
BEGIN
    ALTER TABLE [dbo].[zz_counsel_booking] DROP COLUMN [first_call_time];
    RAISERROR(N'- booking.first_call_time 已删除', 0, 1) WITH NOWAIT;
END
GO

IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.zz_counsel_booking') AND name = 'done_time')
BEGIN
    ALTER TABLE [dbo].[zz_counsel_booking] DROP COLUMN [done_time];
    RAISERROR(N'- booking.done_time 已删除', 0, 1) WITH NOWAIT;
END
GO

IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.zz_counsel_booking') AND name = 'serve_seconds')
BEGIN
    ALTER TABLE [dbo].[zz_counsel_booking] DROP COLUMN [serve_seconds];
    RAISERROR(N'- booking.serve_seconds 已删除', 0, 1) WITH NOWAIT;
END
GO


-- ============================================================
-- 步骤 7：状态收敛 + 字段长度调整
-- ============================================================
-- 场次：calling（旧的叫号中）-> published（可预约）；draft/published/finished 保持
UPDATE [dbo].[zz_counsel_schedule]
SET [status] = 'published'
WHERE [status] = 'calling';
RAISERROR(N'+ schedule 状态 calling 已收敛为 published', 0, 1) WITH NOWAIT;
GO

-- 号段：closed 保持；其它保持
UPDATE [dbo].[zz_counsel_booking]
SET [status] = 'attended'
WHERE [status] IN ('signed', 'calling', 'done', 'missed');
RAISERROR(N'+ booking 存量状态已收敛为 booked/attended/cancelled', 0, 1) WITH NOWAIT;
GO

IF EXISTS (SELECT 1 FROM sys.columns
           WHERE object_id = OBJECT_ID('dbo.zz_counsel_booking')
             AND name = 'category' AND max_length <> 100)
BEGIN
    ALTER TABLE [dbo].[zz_counsel_booking] ALTER COLUMN [category] nvarchar(50) NULL;
    RAISERROR(N'+ booking.category 已收窄为 nvarchar(50)', 0, 1) WITH NOWAIT;
END
GO

IF EXISTS (SELECT 1 FROM sys.columns
           WHERE object_id = OBJECT_ID('dbo.zz_counsel_booking')
             AND name = 'phone_suffix' AND max_length <> 8)
BEGIN
    ALTER TABLE [dbo].[zz_counsel_booking] ALTER COLUMN [phone_suffix] nvarchar(4) NULL;
    RAISERROR(N'+ booking.phone_suffix 已收窄为 nvarchar(4)', 0, 1) WITH NOWAIT;
END
GO

IF EXISTS (SELECT 1 FROM sys.columns
           WHERE object_id = OBJECT_ID('dbo.zz_counsel_booking')
             AND name = 'room_name' AND max_length <> 200)
BEGIN
    ALTER TABLE [dbo].[zz_counsel_booking] ALTER COLUMN [room_name] nvarchar(100) NULL;
    RAISERROR(N'+ booking.room_name 已扩为 nvarchar(100)', 0, 1) WITH NOWAIT;
END
GO


-- ============================================================
-- 步骤 8：索引调整
-- ============================================================
IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = 'ix_counsel_slot_seq'
                 AND object_id = OBJECT_ID('dbo.zz_counsel_booking'))
BEGIN
    CREATE NONCLUSTERED INDEX [ix_counsel_slot_seq]
        ON [dbo].[zz_counsel_booking] ([slot_id], [status], [slot_seq]);
    RAISERROR(N'+ 索引 ix_counsel_slot_seq 已创建', 0, 1) WITH NOWAIT;
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = 'ix_counsel_schedule_date'
                 AND object_id = OBJECT_ID('dbo.zz_counsel_schedule'))
BEGIN
    CREATE NONCLUSTERED INDEX [ix_counsel_schedule_date]
        ON [dbo].[zz_counsel_schedule] ([counsel_date], [id]);
    RAISERROR(N'+ 索引 ix_counsel_schedule_date 已创建', 0, 1) WITH NOWAIT;
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = 'ix_counsel_slot_date'
                 AND object_id = OBJECT_ID('dbo.zz_counsel_slot'))
BEGIN
    CREATE NONCLUSTERED INDEX [ix_counsel_slot_date]
        ON [dbo].[zz_counsel_slot] ([schedule_id], [counsel_date], [sort_order]);
    RAISERROR(N'+ 索引 ix_counsel_slot_date 已创建', 0, 1) WITH NOWAIT;
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = 'ix_counsel_booking_xh'
                 AND object_id = OBJECT_ID('dbo.zz_counsel_booking'))
BEGIN
    CREATE NONCLUSTERED INDEX [ix_counsel_booking_xh]
        ON [dbo].[zz_counsel_booking] ([xh], [book_time] DESC);
    RAISERROR(N'+ 索引 ix_counsel_booking_xh 已创建', 0, 1) WITH NOWAIT;
END
GO


-- ============================================================
-- 步骤 9：验证
-- ============================================================
SELECT
    t.name AS table_name,
    c.name AS column_name,
    ty.name AS data_type,
    c.max_length,
    c.is_nullable
FROM sys.columns c
JOIN sys.tables t ON t.object_id = c.object_id
JOIN sys.types ty ON c.user_type_id = ty.user_type_id
WHERE t.name IN ('zz_counsel_schedule', 'zz_counsel_slot', 'zz_counsel_booking')
ORDER BY t.name, c.column_id;

SELECT
    OBJECT_NAME(object_id) AS table_name,
    name AS index_name,
    is_unique,
    filter_definition
FROM sys.indexes
WHERE object_id IN (
    OBJECT_ID('dbo.zz_counsel_schedule'),
    OBJECT_ID('dbo.zz_counsel_slot'),
    OBJECT_ID('dbo.zz_counsel_booking')
)
AND name IS NOT NULL
ORDER BY table_name, index_name;

RAISERROR(N'心理咨询预约模块重构完成！', 0, 1) WITH NOWAIT;
GO
