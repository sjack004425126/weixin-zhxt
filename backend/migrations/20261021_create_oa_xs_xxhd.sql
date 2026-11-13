-- 新生信息核对表 oa_xs_xxhd 迁移脚本
-- 创建日期: 2026-10-21

-- 如果表已存在，先删除（注意：会丢失数据，请谨慎操作）
-- DROP TABLE IF EXISTS [dbo].[oa_xs_xxhd];

-- 创建新生信息核对表
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[oa_xs_xxhd]') AND type in (N'U'))
BEGIN
    CREATE TABLE [dbo].[oa_xs_xxhd] (
        [id] int IDENTITY(1,1) NOT NULL,
        [xs_xh] varchar(20) COLLATE Chinese_PRC_CI_AS NULL,
        [xs_xm] varchar(20) COLLATE Chinese_PRC_CI_AS NULL,
        [xs_xb] varchar(1) COLLATE Chinese_PRC_CI_AS NULL,
        [xs_mz] varchar(20) COLLATE Chinese_PRC_CI_AS NULL,
        [xs_sfzh] varchar(20) COLLATE Chinese_PRC_CI_AS NULL,
        [xs_bj_id] int NULL,
        [xs_bzr_id] int NULL,
        [addtime] datetime NULL,
        [xs_xm_status] int NULL,
        [xs_xb_status] int NULL,
        [xs_sfzh_status] int NULL,
        [xs_mz_status] int NULL,
        CONSTRAINT [PK_oa_xs_xxhd] PRIMARY KEY CLUSTERED ([id])
        WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON)
        ON [PRIMARY]
    )
    ON [PRIMARY]
    
    -- 添加注释
    EXEC sp_addextendedproperty 'MS_Description', '新生信息核对表', 'SCHEMA', 'dbo', 'TABLE', 'oa_xs_xxhd';
    EXEC sp_addextendedproperty 'MS_Description', '自增主键ID', 'SCHEMA', 'dbo', 'TABLE', 'oa_xs_xxhd', 'COLUMN', 'id';
    EXEC sp_addextendedproperty 'MS_Description', '学号', 'SCHEMA', 'dbo', 'TABLE', 'oa_xs_xxhd', 'COLUMN', 'xs_xh';
    EXEC sp_addextendedproperty 'MS_Description', '姓名', 'SCHEMA', 'dbo', 'TABLE', 'oa_xs_xxhd', 'COLUMN', 'xs_xm';
    EXEC sp_addextendedproperty 'MS_Description', '性别', 'SCHEMA', 'dbo', 'TABLE', 'oa_xs_xxhd', 'COLUMN', 'xs_xb';
    EXEC sp_addextendedproperty 'MS_Description', '民族', 'SCHEMA', 'dbo', 'TABLE', 'oa_xs_xxhd', 'COLUMN', 'xs_mz';
    EXEC sp_addextendedproperty 'MS_Description', '身份证号', 'SCHEMA', 'dbo', 'TABLE', 'oa_xs_xxhd', 'COLUMN', 'xs_sfzh';
    EXEC sp_addextendedproperty 'MS_Description', '班级ID', 'SCHEMA', 'dbo', 'TABLE', 'oa_xs_xxhd', 'COLUMN', 'xs_bj_id';
    EXEC sp_addextendedproperty 'MS_Description', '班主任ID', 'SCHEMA', 'dbo', 'TABLE', 'oa_xs_xxhd', 'COLUMN', 'xs_bzr_id';
    EXEC sp_addextendedproperty 'MS_Description', '添加时间', 'SCHEMA', 'dbo', 'TABLE', 'oa_xs_xxhd', 'COLUMN', 'addtime';
    EXEC sp_addextendedproperty 'MS_Description', '姓名核对状态：0-有误已修正 1-无误', 'SCHEMA', 'dbo', 'TABLE', 'oa_xs_xxhd', 'COLUMN', 'xs_xm_status';
    EXEC sp_addextendedproperty 'MS_Description', '性别核对状态：0-有误已修正 1-无误', 'SCHEMA', 'dbo', 'TABLE', 'oa_xs_xxhd', 'COLUMN', 'xs_xb_status';
    EXEC sp_addextendedproperty 'MS_Description', '身份证号核对状态：0-有误已修正 1-无误', 'SCHEMA', 'dbo', 'TABLE', 'oa_xs_xxhd', 'COLUMN', 'xs_sfzh_status';
    EXEC sp_addextendedproperty 'MS_Description', '民族核对状态：0-有误已修正 1-无误', 'SCHEMA', 'dbo', 'TABLE', 'oa_xs_xxhd', 'COLUMN', 'xs_mz_status';
    
    -- 添加索引
    CREATE INDEX [IX_oa_xs_xxhd_xs_xh] ON [dbo].[oa_xs_xxhd] ([xs_xh]);
    
    PRINT '表 oa_xs_xxhd 创建成功';
END
ELSE
BEGIN
    PRINT '表 oa_xs_xxhd 已存在，跳过创建';
END
GO

-- 设置锁升级
ALTER TABLE [dbo].[oa_xs_xxhd] SET (LOCK_ESCALATION = TABLE);
GO
