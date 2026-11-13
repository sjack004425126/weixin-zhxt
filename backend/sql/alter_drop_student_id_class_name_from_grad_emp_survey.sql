-- ============================================================
-- 从 zs_graduate_employment_survey 删除 student_id / class_name 字段
-- 模型已不再使用：student_id 与冗余的 class_name（班级可由 student_no
-- 在 zz_xs / zz_bj 反查，无需冗余存储）
-- 数据库：MSSQL（SQL Server）
-- 幂等：重复执行不会报错
-- ============================================================

-- 1) 删除可能存在的引用索引（按需）
-- 当前表上没有针对 student_id / class_name 的命名索引；如有自定义索引请先 DROP

-- 2) 删除字段（连同默认值约束/扩展属性自动随列移除）
IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.zs_graduate_employment_survey')
      AND name = N'student_id'
)
BEGIN
    -- 若存在默认值约束，先 drop（防御性写法）
    DECLARE @df_name1 sysname;
    SELECT @df_name1 = dc.name
      FROM sys.default_constraints dc
      JOIN sys.columns c ON dc.parent_object_id = c.object_id AND dc.parent_column_id = c.column_id
     WHERE dc.parent_object_id = OBJECT_ID(N'dbo.zs_graduate_employment_survey')
       AND c.name = N'student_id';
    IF @df_name1 IS NOT NULL
        EXEC('ALTER TABLE dbo.zs_graduate_employment_survey DROP CONSTRAINT ' + @df_name1);

    ALTER TABLE dbo.zs_graduate_employment_survey DROP COLUMN student_id;
END
GO

IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.zs_graduate_employment_survey')
      AND name = N'class_name'
)
BEGIN
    DECLARE @df_name2 sysname;
    SELECT @df_name2 = dc.name
      FROM sys.default_constraints dc
      JOIN sys.columns c ON dc.parent_object_id = c.object_id AND dc.parent_column_id = c.column_id
     WHERE dc.parent_object_id = OBJECT_ID(N'dbo.zs_graduate_employment_survey')
       AND c.name = N'class_name';
    IF @df_name2 IS NOT NULL
        EXEC('ALTER TABLE dbo.zs_graduate_employment_survey DROP CONSTRAINT ' + @df_name2);

    ALTER TABLE dbo.zs_graduate_employment_survey DROP COLUMN class_name;
END
GO
