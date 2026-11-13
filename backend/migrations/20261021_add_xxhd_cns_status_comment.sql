-- oa_xs_xxhd 补充 xs_cns_status 列注释
-- 创建日期: 2026-10-21
-- 用途: 标注学生是否已同意学习承诺书条款（0-未同意 1-已同意）
-- 说明: 列已存在于表中（历史遗留），本脚本仅补加注释，幂等。

IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.oa_xs_xxhd') AND name = 'xs_cns_status')
BEGIN
    -- 删除旧注释（若存在）后再添加，避免重复
    IF EXISTS (
        SELECT 1 FROM sys.extended_properties
        WHERE major_id = OBJECT_ID('dbo.oa_xs_xxhd')
          AND name = 'MS_Description'
          AND minor_id = (
              SELECT column_id FROM sys.columns
              WHERE object_id = OBJECT_ID('dbo.oa_xs_xxhd') AND name = 'xs_cns_status'
          )
    )
    BEGIN
        EXEC sp_updateextendedproperty 'MS_Description', '同意学习承诺书状态：0-未同意 1-已同意',
             'SCHEMA', 'dbo', 'TABLE', 'oa_xs_xxhd', 'COLUMN', 'xs_cns_status';
    END
    ELSE
    BEGIN
        EXEC sp_addextendedproperty 'MS_Description', '同意学习承诺书状态：0-未同意 1-已同意',
             'SCHEMA', 'dbo', 'TABLE', 'oa_xs_xxhd', 'COLUMN', 'xs_cns_status';
    END
END
GO

PRINT 'oa_xs_xxhd.xs_cns_status 注释更新完成！';
GO
