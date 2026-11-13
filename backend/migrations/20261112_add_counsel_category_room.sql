-- ============================================================
-- 心理咨询叫号系统：按「心语工作坊·心理医生极简叫号系统」原型重构
-- 新增字段：
--   zz_counsel_schedule.room_name    诊室名称
--   zz_counsel_slot.category         咨询项目类别
--   zz_counsel_booking.category      咨询项目类别快照
--   zz_counsel_booking.phone_suffix  手机后4位（个人核对）
--   zz_counsel_booking.room_name     诊室快照
-- 幂等：可重复执行
-- ============================================================

-- 1) 场次：诊室
IF NOT EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id = OBJECT_ID('dbo.zz_counsel_schedule') AND name = 'room_name')
BEGIN
    ALTER TABLE [dbo].[zz_counsel_schedule] ADD [room_name] NVARCHAR(50) NULL;
    PRINT '+ zz_counsel_schedule.room_name 已添加';
END
ELSE
    PRINT '- zz_counsel_schedule.room_name 已存在，跳过';
GO

-- 2) 时段：咨询项目类别
IF NOT EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id = OBJECT_ID('dbo.zz_counsel_slot') AND name = 'category')
BEGIN
    ALTER TABLE [dbo].[zz_counsel_slot] ADD [category] NVARCHAR(50) NULL;
    PRINT '+ zz_counsel_slot.category 已添加';
END
ELSE
    PRINT '- zz_counsel_slot.category 已存在，跳过';
GO

-- 3) 号单：咨询项目 / 手机尾号 / 诊室
IF NOT EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id = OBJECT_ID('dbo.zz_counsel_booking') AND name = 'category')
BEGIN
    ALTER TABLE [dbo].[zz_counsel_booking] ADD [category] NVARCHAR(50) NULL;
    PRINT '+ zz_counsel_booking.category 已添加';
END
ELSE
    PRINT '- zz_counsel_booking.category 已存在，跳过';
GO

IF NOT EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id = OBJECT_ID('dbo.zz_counsel_booking') AND name = 'phone_suffix')
BEGIN
    ALTER TABLE [dbo].[zz_counsel_booking] ADD [phone_suffix] NVARCHAR(4) NULL;
    PRINT '+ zz_counsel_booking.phone_suffix 已添加';
END
ELSE
    PRINT '- zz_counsel_booking.phone_suffix 已存在，跳过';
GO

IF NOT EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id = OBJECT_ID('dbo.zz_counsel_booking') AND name = 'room_name')
BEGIN
    ALTER TABLE [dbo].[zz_counsel_booking] ADD [room_name] NVARCHAR(50) NULL;
    PRINT '+ zz_counsel_booking.room_name 已添加';
END
ELSE
    PRINT '- zz_counsel_booking.room_name 已存在，跳过';
GO

PRINT '心理咨询叫号系统字段扩展完成！'
GO
