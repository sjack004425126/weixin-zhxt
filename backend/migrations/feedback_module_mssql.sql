/* ============================================================
   校园反馈模块 - 新增表 & 种子数据（MSSQL）
   生成时间：2026-05-12
   说明：
     1. 3 张新表：hp_staff / hp_feedback_dict / hp_feedback_admin
     2. 字典种子：5 个场景 + 11 个物品类型
     3. 管理员种子：从原 feedback_admin_whitelist.py 同步
        ⚠ 管理员表 user_ref_id 写的是手机号占位，
          请在导入后用真实业务主键替换
          （或重启后端，启动时的 ensure_super_admin_seeds 会自动匹配 5 张用户表回填）
     4. 工作人员表（hp_staff）按要求留空，自行录入
   ============================================================ */

SET NOCOUNT ON;
GO

/* ============================================================
   1. 工作人员表
   ============================================================ */
IF OBJECT_ID(N'dbo.hp_staff', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.hp_staff (
        id           INT             IDENTITY(1,1) NOT NULL PRIMARY KEY,
        name         NVARCHAR(64)    NOT NULL,
        phone        VARCHAR(11)     NOT NULL,
        department   NVARCHAR(64)    NULL,
        position     NVARCHAR(64)    NULL,
        id_card      VARCHAR(18)     NULL,
        status       VARCHAR(8)      NOT NULL CONSTRAINT DF_hp_staff_status   DEFAULT ('active'),
        note         NVARCHAR(255)   NULL,
        created_at   DATETIME        NOT NULL CONSTRAINT DF_hp_staff_created  DEFAULT (GETDATE()),
        updated_at   DATETIME        NOT NULL CONSTRAINT DF_hp_staff_updated  DEFAULT (GETDATE())
    );

    CREATE INDEX IX_hp_staff_name   ON dbo.hp_staff(name);
    CREATE INDEX IX_hp_staff_phone  ON dbo.hp_staff(phone);
    CREATE INDEX IX_hp_staff_status ON dbo.hp_staff(status);

    EXEC sp_addextendedproperty 'MS_Description', N'工作人员（保洁/维修/保卫/食堂等非教师非学生岗位）',
         'SCHEMA', 'dbo', 'TABLE', 'hp_staff';
END
GO


/* ============================================================
   2. 反馈字典表
   ============================================================ */
IF OBJECT_ID(N'dbo.hp_feedback_dict', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.hp_feedback_dict (
        id             INT             IDENTITY(1,1) NOT NULL PRIMARY KEY,
        category       VARCHAR(16)     NOT NULL,        -- scene / item
        code           VARCHAR(32)     NOT NULL,        -- 业务编码：canteen/meal/...
        label          NVARCHAR(32)    NOT NULL,        -- 展示文案
        icon           VARCHAR(64)     NULL,
        sort_order     INT             NOT NULL CONSTRAINT DF_hp_fbdict_sort     DEFAULT (0),
        is_active      BIT             NOT NULL CONSTRAINT DF_hp_fbdict_active   DEFAULT (1),
        is_custom      BIT             NOT NULL CONSTRAINT DF_hp_fbdict_custom   DEFAULT (0),
        feedback_type  VARCHAR(16)     NOT NULL CONSTRAINT DF_hp_fbdict_ftype    DEFAULT ('both'),  -- repair / suggestion / both
        created_at     DATETIME        NOT NULL CONSTRAINT DF_hp_fbdict_created  DEFAULT (GETDATE()),
        updated_at     DATETIME        NOT NULL CONSTRAINT DF_hp_fbdict_updated  DEFAULT (GETDATE()),
        CONSTRAINT uq_feedback_dict_cat_code UNIQUE (category, code)
    );

    CREATE INDEX IX_hp_fbdict_category  ON dbo.hp_feedback_dict(category);
    CREATE INDEX IX_hp_fbdict_active    ON dbo.hp_feedback_dict(is_active);
    CREATE INDEX IX_hp_fbdict_sort      ON dbo.hp_feedback_dict(sort_order);
    CREATE INDEX ix_feedback_dict_cat_active_order
            ON dbo.hp_feedback_dict(category, is_active, sort_order);
END
GO


/* ============================================================
   3. 反馈管理员表
   ============================================================ */
IF OBJECT_ID(N'dbo.hp_feedback_admin', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.hp_feedback_admin (
        id              INT             IDENTITY(1,1) NOT NULL PRIMARY KEY,
        user_type       VARCHAR(20)     NOT NULL,          -- staff/open_teacher/vocational_teacher/open_student/vocational_student
        user_ref_id     VARCHAR(50)     NOT NULL,          -- 对应用户表主键（字符串形式）
        phone_snapshot  VARCHAR(11)     NOT NULL,          -- 冗余手机号
        name_snapshot   NVARCHAR(64)    NULL,              -- 冗余姓名
        role            VARCHAR(16)     NOT NULL CONSTRAINT DF_hp_fbadmin_role     DEFAULT ('handler'),  -- super/manager/handler/viewer
        department      NVARCHAR(64)    NULL,
        scope_codes     VARCHAR(255)    NULL,              -- handler 限定字典 code，逗号分隔
        is_active       BIT             NOT NULL CONSTRAINT DF_hp_fbadmin_active   DEFAULT (1),
        created_by      INT             NULL,
        created_at      DATETIME        NOT NULL CONSTRAINT DF_hp_fbadmin_created  DEFAULT (GETDATE()),
        updated_at      DATETIME        NOT NULL CONSTRAINT DF_hp_fbadmin_updated  DEFAULT (GETDATE()),
        note            NVARCHAR(255)   NULL,
        CONSTRAINT uq_feedback_admin_user UNIQUE (user_type, user_ref_id)
    );

    CREATE INDEX IX_hp_fbadmin_phone   ON dbo.hp_feedback_admin(phone_snapshot);
    CREATE INDEX IX_hp_fbadmin_active  ON dbo.hp_feedback_admin(is_active);
    CREATE INDEX ix_feedback_admin_phone_active
            ON dbo.hp_feedback_admin(phone_snapshot, is_active);
END
GO


/* ============================================================
   4. 字典种子数据（与 services/feedback_init.py 中 _SCENE_SEEDS / _ITEM_SEEDS 完全对齐）
      仅在表为空时插入
   ============================================================ */
IF NOT EXISTS (SELECT 1 FROM dbo.hp_feedback_dict)
BEGIN
    INSERT INTO dbo.hp_feedback_dict (category, code, label, sort_order, is_custom, feedback_type) VALUES
    -- 场景
    ('scene',  'canteen',     N'食堂',          10,  0, 'both'),
    ('scene',  'shop',        N'超市',          20,  0, 'both'),
    ('scene',  'classroom',   N'教室',          30,  0, 'both'),
    ('scene',  'dorm',        N'宿舍',          40,  0, 'both'),
    ('scene',  'building',    N'其他建筑',      50,  0, 'both'),
    ('scene',  'custom',      N'其他',          999, 1, 'both'),
    -- 物品类型 / 维修类
    ('item',   'water_power', N'水电',          10,  0, 'repair'),
    ('item',   'desk',        N'桌椅板凳',      20,  0, 'repair'),
    ('item',   'banbantong',  N'班班通',        30,  0, 'repair'),
    ('item',   'training_eq', N'实训设备',      40,  0, 'repair'),
    ('item',   'facility',    N'校园设施',      50,  0, 'repair'),
    -- 物品类型 / 意见建议类
    ('item',   'meal',        N'饭菜质量',      100, 0, 'suggestion'),
    ('item',   'price',       N'价格',          110, 0, 'suggestion'),
    ('item',   'guoqi',       N'过期、三无产品', 120, 0, 'suggestion'),
    ('item',   'service',     N'服务态度',      130, 0, 'suggestion'),
    ('item',   'safety',      N'安全卫生',      140, 0, 'suggestion'),
    -- 物品类型 / 兜底
    ('item',   'custom',      N'其他',          999, 1, 'both');
END
GO


/* ============================================================
   5. 管理员种子（从 feedback_admin_whitelist.py 转录）
      ⚠ user_ref_id 临时填为手机号，目的是先把记录建出来；
        后端启动时 ensure_super_admin_seeds 会自动按手机号匹配 5 张用户表，
        把 user_type / user_ref_id 更新为真实业务主键。
      ⚠ 如果你想立即生效（不重启），请在执行本脚本前先打开下面的"立即解析"段，
        或重启后端让保底种子自动跑。
   ============================================================ */
IF NOT EXISTS (SELECT 1 FROM dbo.hp_feedback_admin WHERE role = 'super' AND is_active = 1)
BEGIN
    INSERT INTO dbo.hp_feedback_admin
        (user_type, user_ref_id, phone_snapshot, name_snapshot, role, department, is_active, note)
    VALUES
        ('pending', '15885828255', '15885828255', N'杨帆',     'super', N'分管校长',       1, N'seeded from whitelist'),
        ('pending', '18785112572', '18785112572', N'龙安发',   'super', N'后勤总负责人',   1, N'seeded from whitelist'),
        ('pending', '15286608119', '15286608119', N'杨昌坤',   'super', N'后勤总负责人',   1, N'seeded from whitelist'),
        ('pending', '15685905915', '15685905915', N'王正坊',   'super', N'后勤总负责人',   1, N'seeded from whitelist'),
        ('pending', '13885576813', '13885576813', N'粟多铭',   'super', N'维修组',         1, N'seeded from whitelist'),
        ('pending', '19082738316', '19082738316', N'吴师傅',   'super', N'维修组',         1, N'seeded from whitelist'),
        ('pending', '18984619084', '18984619084', N'石开华',   'super', N'开发者',         1, N'seeded from whitelist'),
        ('pending', '15121438850', '15121438850', N'杨仁伟',   'super', N'开发者',         1, N'seeded from whitelist');
END
GO


/* ============================================================
   6.（可选）立即把 user_type / user_ref_id 解析为真实业务主键
       —— 如果你不想重启后端，可以执行这一段。
       —— 注意：教师表统一登记为 open_teacher，因为后端 resolve_user 中
          open_teacher / vocational_teacher 都查 oa_t 表。
   ============================================================ */
-- 优先级 1：工作人员
UPDATE a
   SET a.user_type   = 'staff',
       a.user_ref_id = CONVERT(VARCHAR(50), s.id)
  FROM dbo.hp_feedback_admin a
  JOIN dbo.hp_staff s
    ON s.phone = a.phone_snapshot AND s.status = 'active'
 WHERE a.user_type = 'pending';

-- 优先级 2：教师
UPDATE a
   SET a.user_type   = 'open_teacher',
       a.user_ref_id = CONVERT(VARCHAR(50), t.t_id)
  FROM dbo.hp_feedback_admin a
  JOIN dbo.oa_t t
    ON t.t_dh = a.phone_snapshot
 WHERE a.user_type = 'pending';

-- 优先级 3：开放学生
UPDATE a
   SET a.user_type   = 'open_student',
       a.user_ref_id = CONVERT(VARCHAR(50), x.xs_id)
  FROM dbo.hp_feedback_admin a
  JOIN dbo.oa_xs x
    ON x.xs_dh = a.phone_snapshot
 WHERE a.user_type = 'pending';

-- 优先级 4：中职学生
UPDATE a
   SET a.user_type   = 'vocational_student',
       a.user_ref_id = CONVERT(VARCHAR(50), zx.id)
  FROM dbo.hp_feedback_admin a
  JOIN dbo.zz_xs zx
    ON zx.xsdh = a.phone_snapshot
 WHERE a.user_type = 'pending';

-- 未匹配的留作 pending 状态，登录时无法被识别为管理员；
-- 录入 hp_staff 后再次重启或重跑上面这 4 段 UPDATE 即可激活。
GO


PRINT N'✅ 校园反馈模块表 & 种子数据创建完成';
PRINT N'   - hp_staff           （工作人员，留空，自行录入）';
PRINT N'   - hp_feedback_dict   （17 条字典数据已插入）';
PRINT N'   - hp_feedback_admin  （8 条管理员种子，user_ref_id 已尝试解析）';
GO

/* ============================================================
   7. 新增 can_view_suggestion 字段（存量表升级）
      如果表已存在但缺少该字段，执行此段补充。
   ============================================================ */
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
     WHERE object_id = OBJECT_ID(N'dbo.hp_feedback_admin')
       AND name = N'can_view_suggestion'
)
BEGIN
    ALTER TABLE dbo.hp_feedback_admin
        ADD can_view_suggestion BIT NOT NULL
            CONSTRAINT DF_hp_fbadmin_can_view_suggestion DEFAULT (0);

    EXEC sp_addextendedproperty
        'MS_Description',
        N'是否允许查看"意见建议"类工单，默认 0(False)；manager/super 角色不受此字段限制，始终可见',
        'SCHEMA', 'dbo', 'TABLE', 'hp_feedback_admin', 'COLUMN', 'can_view_suggestion';

    PRINT N'✅ hp_feedback_admin.can_view_suggestion 字段已添加';
END
ELSE
BEGIN
    PRINT N'ℹ️  hp_feedback_admin.can_view_suggestion 字段已存在，跳过';
END
GO
