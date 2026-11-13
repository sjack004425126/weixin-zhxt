-- ============================================================
-- 系统配置表 lw_config
-- 用于存储可动态配置的系统参数（如 VR URL 等）
-- ============================================================

-- 如果表不存在则创建
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[lw_config]') AND type in (N'U'))
BEGIN
    CREATE TABLE [dbo].[lw_config](
        [id] [int] IDENTITY(1,1) NOT NULL,
        [key] [nvarchar](100) NOT NULL,
        [value] [nvarchar](4000) NULL,              -- 配置值（支持较长内容如URL）
        [description] [nvarchar](500) NULL,        -- 配置描述说明
        [category] [nvarchar](50) NULL DEFAULT N'general',  -- 配置分类
        [is_enabled] [int] NOT NULL DEFAULT 1,     -- 是否启用：1=启用 0=禁用
        [sort_order] [int] NOT NULL DEFAULT 0,     -- 排序号
        [created_at] [datetime] NOT NULL DEFAULT GETDATE(),
        [updated_at] [datetime] NOT NULL DEFAULT GETDATE(),
        CONSTRAINT [PK_lw_config] PRIMARY KEY CLUSTERED ([id] ASC),
        CONSTRAINT [UQ_lw_config_key] UNIQUE ([key])
    );
    PRINT '✅ 表 [dbo].[lw_config] 创建成功';
END
GO

-- 初始化 VR URL 配置
IF NOT EXISTS (
    SELECT 1 FROM [dbo].[lw_config]
    WHERE [key] = 'vr_url'
)
BEGIN
    INSERT INTO [dbo].[lw_config] (
        [key], [value], [description], [category],
        [is_enabled], [sort_order], [created_at], [updated_at]
    )
    VALUES (
        'vr_url',
        'https://yh.bdbdigital.com/yihuaVideoPreview?id=2rbQF7',
        '智慧校园VR全景视频播放地址',
        'video',
        1,
        1,
        GETDATE(),
        GETDATE()
    );
    PRINT '✅ VR URL 配置初始化成功';
END
ELSE
BEGIN
    PRINT 'ℹ️ VR URL 配置已存在，跳过初始化';
END
GO

-- 查询验证
SELECT id, [key], [value], [description], category, is_enabled, sort_order, created_at, updated_at
FROM [dbo].[lw_config]
ORDER BY sort_order;
