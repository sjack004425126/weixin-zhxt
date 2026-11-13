-- ========================================
-- 为 zz_xs 表添加信息核对相关字段 (MSSQL 版本)
-- ========================================

-- 1. 添加核对状态字段
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('zz_xs') AND name = 'xs_info_verify_status')
BEGIN
    ALTER TABLE zz_xs 
    ADD xs_info_verify_status NVARCHAR(20) NOT NULL CONSTRAINT DF_zz_xs_xs_info_verify_status DEFAULT 'pending';
    
    -- 添加注释（如果数据库支持）
    EXEC sp_addextendedproperty 
        @name = N'MS_Description', 
        @value = N'新生信息核对状态：pending-待核对 verified-已确认无误 modified-已修改提交', 
        @level0type = N'SCHEMA', @level0name = 'dbo', 
        @level1type = N'TABLE',  @level1name = 'zz_xs', 
        @level2type = N'COLUMN', @level2name = 'xs_info_verify_status';
END

-- 2. 添加核对记录JSON字段
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('zz_xs') AND name = 'xs_info_verify_record')
BEGIN
    ALTER TABLE zz_xs 
    ADD xs_info_verify_record NVARCHAR(MAX);
    
    -- 添加注释
    EXEC sp_addextendedproperty 
        @name = N'MS_Description', 
        @value = N'新生信息核对记录JSON，含原始值、修改值、历次提交历史', 
        @level0type = N'SCHEMA', @level0name = 'dbo', 
        @level1type = N'TABLE',  @level1name = 'zz_xs', 
        @level2type = N'COLUMN', @level2name = 'xs_info_verify_record';
END
-- ========================================
-- 创建索引（可选，提高查询效率）
-- ========================================
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('zz_xs') AND name = 'idx_zz_xs_verify_status')
BEGIN
    CREATE INDEX idx_zz_xs_verify_status ON zz_xs(xs_info_verify_status);
END

PRINT 'zz_xs 表字段添加完成！';

-- ========================================
-- 验证字段是否添加成功
-- ========================================
SELECT 
    c.name AS ColumnName,
    t.name AS DataType,
    c.max_length AS MaxLength,
    c.default_object_id AS HasDefault,
    c.is_nullable AS IsNullable,
    ep.value AS Description
FROM sys.columns c
INNER JOIN sys.types t ON c.user_type_id = t.user_type_id
LEFT JOIN sys.extended_properties ep ON ep.major_id = c.object_id AND ep.minor_id = c.column_id AND ep.name = 'MS_Description'
WHERE c.object_id = OBJECT_ID('zz_xs')
AND c.name IN ('xs_info_verify_status', 'xs_info_verify_record')
ORDER BY c.column_id;
