/* ============================================================
   电表充值 - 新建表 zz_dianbiao_meters (2026-10-20)

   背景：
     chongzhi 项目里有一份 meters 表（290 条数据），是"管家婆"系统同步过来的
     电表（电表充值场景）。需要把结构 + 数据迁移到 zhpt-new，便于小程序内
     做"输入电表名 → 完全匹配 → 展示电表充值二维码"。

   设计：
     - 表名：zz_dianbiao_meters（与 zhpt-new 中"zz_" 前缀保持一致；
            实际场景是中职宿舍电表，挂在"中职"业务域下）
     - 字段与 chongzhi.backend.app.models.meter.Meter 完全一致；
            仅 raw 字段由 JSON 改为 NVARCHAR(MAX)（SQL Server JSON 兼容写法）
     - 索引：device_id/sn 唯一索引、house_id/estate_name+house_name 普通索引
     - 二维码文件已存在于 MinIO 私有桶
            guizhou-zhpt-prod-private 的 /dianbiao/<sn>.png 路径下，
            数据迁移不需要搬运文件。

   幂等：脚本可重复执行。
   适用于 SQL Server。
   ============================================================ */
SET NOCOUNT ON;
GO

IF OBJECT_ID(N'dbo.zz_dianbiao_meters', N'U') IS NOT NULL
BEGIN
    PRINT N'ℹ️  dbo.zz_dianbiao_meters 表已存在，跳过建表';
END
ELSE
BEGIN
    CREATE TABLE dbo.zz_dianbiao_meters (
        id               INT             IDENTITY(1,1) NOT NULL,
        device_id        INT             NOT NULL,
        sn               NVARCHAR(64)    NOT NULL,
        mac              NVARCHAR(64)    NULL,
        house_id         INT             NOT NULL,

        estate_name      NVARCHAR(128)   NULL,
        building         NVARCHAR(64)    NULL,
        house_name       NVARCHAR(64)     NULL,
        full_name        NVARCHAR(255)   NULL,
        tenant_name      NVARCHAR(64)    NULL,
        status           NVARCHAR(32)    NULL,

        resident_count   INT             NOT NULL DEFAULT 0,

        price            NVARCHAR(16)    NULL,
        basic_price      NVARCHAR(16)    NULL,
        du               NVARCHAR(32)    NULL,
        total            NVARCHAR(32)    NULL,
        total_money      NVARCHAR(32)    NULL,
        total_recharge   INT             NULL,

        online_status    INT             NULL,
        is_disabled      INT             NULL,
        recharge_disabled INT            NULL,
        expired_at       DATETIME        NULL,
        month_limit      NVARCHAR(32)    NULL,
        month_recharge   NVARCHAR(32)    NULL,
        qrcode           NVARCHAR(255)   NULL,

        raw              NVARCHAR(MAX)   NULL,
        remote_synced_at DATETIME        NULL,

        created_at       DATETIME        NOT NULL DEFAULT GETDATE(),
        updated_at       DATETIME        NOT NULL DEFAULT GETDATE(),

        CONSTRAINT PK_zz_dianbiao_meters PRIMARY KEY CLUSTERED (id)
    );

    -- 唯一索引：sn / device_id
    CREATE UNIQUE INDEX IX_zz_dianbiao_meters_sn
        ON dbo.zz_dianbiao_meters(sn);
    CREATE UNIQUE INDEX IX_zz_dianbiao_meters_device
        ON dbo.zz_dianbiao_meters(device_id);

    -- 普通索引：house_id、estate_name + house_name 复合索引
    CREATE INDEX IX_zz_dianbiao_meters_house_id
        ON dbo.zz_dianbiao_meters(house_id);
    CREATE INDEX IX_zz_dianbiao_meters_estate_house
        ON dbo.zz_dianbiao_meters(estate_name, house_name);
    CREATE INDEX IX_zz_dianbiao_meters_house_name
        ON dbo.zz_dianbiao_meters(house_name);

    PRINT N'✅ 已创建 dbo.zz_dianbiao_meters 表';
END
GO

/* ============================================================
   新增功能开关：code = 'dianbiao'
   说明：电表充值入口的总开关，与现有 photo / feedback 等保持同一套机制。
   ============================================================ */
IF NOT EXISTS (
    SELECT 1 FROM dbo.lw_feature_switch WHERE code = 'dianbiao'
)
BEGIN
    INSERT INTO dbo.lw_feature_switch
        (code, name, is_enabled, sort_order, remark, tip_message, created_at, updated_at)
    VALUES
        ('dianbiao', N'电表充值', 1, 50,
         N'学生输入电表名称（house_name）查询电表并展示充值二维码。关闭后首页对应入口不再可用。',
         N'电表充值功能已关闭，请联系管理员开启',
         GETDATE(), GETDATE());

    PRINT N'✅ 已新增功能开关 code=dianbiao';
END
ELSE
BEGIN
    UPDATE dbo.lw_feature_switch
    SET name        = N'电表充值',
        sort_order  = 50,
        remark      = N'学生输入电表名称（house_name）查询电表并展示充值二维码。关闭后首页对应入口不再可用。',
        tip_message = N'电表充值功能已关闭，请联系管理员开启',
        updated_at  = GETDATE()
    WHERE code = 'dianbiao';

    PRINT N'ℹ️  功能开关 code=dianbiao 已存在，已刷新配置';
END
GO
