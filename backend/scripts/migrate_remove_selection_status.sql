-- ============================================================
-- 迁移：社团课选课表 zz_st_course_selection
-- 1) 删除 status 字段（不再使用软删除）
-- 2) 删除所有 status=0 的历史"退选"记录
-- 3) 增加唯一约束：同一学生在同一学期不能重复选同一门课
-- 4) 增加索引
-- 数据库：SQL Server
-- ============================================================

-- 1) 删除历史退选记录（status=0）
DELETE FROM zz_st_course_selection WHERE status = 0;

-- 2) 删除 status 字段（如果存在）
IF EXISTS (SELECT 1 FROM sys.columns
           WHERE object_id = OBJECT_ID(N'dbo.zz_st_course_selection')
             AND name = 'status')
BEGIN
    ALTER TABLE dbo.zz_st_course_selection DROP COLUMN status;
END

-- 3) 清理可能的重复记录后加唯一约束
-- 保留每个 (student_id, course_id, year, semester) 最早的一条
;DELETE FROM dbo.zz_st_course_selection
WHERE id IN (
    SELECT id FROM (
        SELECT
            id,
            ROW_NUMBER() OVER (
                PARTITION BY student_id, course_id, year, semester
                ORDER BY id ASC
            ) AS rn
        FROM dbo.zz_st_course_selection
    ) t
    WHERE rn > 1
);

-- 4) 增加唯一约束（防止同学生重复选同一门课）
IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE object_id = OBJECT_ID(N'dbo.zz_st_course_selection')
                 AND name = N'uk_student_course_term')
BEGIN
    ALTER TABLE dbo.zz_st_course_selection
        ADD CONSTRAINT uk_student_course_term UNIQUE (student_id, course_id, year, semester);
END

-- 5) 增加索引（如果不存在）
IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE object_id = OBJECT_ID(N'dbo.zz_st_course_selection')
                 AND name = N'idx_course_term')
BEGIN
    CREATE INDEX idx_course_term ON dbo.zz_st_course_selection (course_id, year, semester);
END

IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE object_id = OBJECT_ID(N'dbo.zz_st_course_selection')
                 AND name = N'idx_student_term')
BEGIN
    CREATE INDEX idx_student_term ON dbo.zz_st_course_selection (student_id, year, semester);
END

-- ============================================================
-- 完成后请同步清除 Redis 中的旧缓存：
-- redis-cli --scan --pattern "st_course:selected:*" | xargs redis-cli DEL
-- ============================================================
