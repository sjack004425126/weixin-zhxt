-- ============================================
-- 宿舍管理模块 - MSSQL 数据库脚本
-- ============================================

-- 1. 楼栋表
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='zz_ss_ld' AND xtype='U')
CREATE TABLE zz_ss_ld (
    id INT IDENTITY(1,1) PRIMARY KEY,
    mc NVARCHAR(50) NOT NULL,           -- 楼栋名称（如：1号楼、男生宿舍A栋）
    bz NVARCHAR(200) NULL,              -- 备注
    px INT DEFAULT 0,                   -- 排序
    zt INT DEFAULT 1,                   -- 状态 1-启用 0-禁用
    cjsj DATETIME DEFAULT GETDATE(),    -- 创建时间
    gxsj DATETIME DEFAULT GETDATE()     -- 更新时间
);
GO

-- 2. 楼层表
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='zz_ss_lc' AND xtype='U')
CREATE TABLE zz_ss_lc (
    id INT IDENTITY(1,1) PRIMARY KEY,
    ld_id INT NOT NULL,                 -- 楼栋ID
    lc INT NOT NULL,                    -- 楼层号（如：1、2、3）
    bz NVARCHAR(200) NULL,              -- 备注
    zt INT DEFAULT 1,                   -- 状态 1-启用 0-禁用
    CONSTRAINT FK_zz_ss_lc_ld FOREIGN KEY (ld_id) REFERENCES zz_ss_ld(id)
);
GO

-- 3. 宿舍表
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='zz_ss_ss' AND xtype='U')
CREATE TABLE zz_ss_ss (
    id INT IDENTITY(1,1) PRIMARY KEY,
    lc_id INT NOT NULL,                 -- 楼层ID
    ssh NVARCHAR(20) NOT NULL,          -- 宿舍号（如：101、102）
    bz NVARCHAR(200) NULL,              -- 备注
    zt INT DEFAULT 1,                   -- 状态 1-启用 0-禁用
    CONSTRAINT FK_zz_ss_ss_lc FOREIGN KEY (lc_id) REFERENCES zz_ss_lc(id)
);
GO

-- 4. 床位表
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='zz_ss_cw' AND xtype='U')
CREATE TABLE zz_ss_cw (
    id INT IDENTITY(1,1) PRIMARY KEY,
    ss_id INT NOT NULL,                 -- 宿舍ID
    cwh NVARCHAR(10) NOT NULL,          -- 床位号（如：1、2、3、上铺A）
    zt INT DEFAULT 1,                   -- 状态 1-启用 0-禁用
    CONSTRAINT FK_zz_ss_cw_ss FOREIGN KEY (ss_id) REFERENCES zz_ss_ss(id)
);
GO

-- 5. 给学生表添加床位ID字段
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('zz_xs') AND name = 'cw_id')
BEGIN
    ALTER TABLE zz_xs ADD cw_id INT NULL;
END
GO

-- ============================================
-- 索引（提升查询性能）
-- ============================================
-- 楼层表：按楼栋查询
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_zz_ss_lc_ld_id')
    CREATE INDEX IX_zz_ss_lc_ld_id ON zz_ss_lc(ld_id);
GO

-- 宿舍表：按楼层查询
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_zz_ss_ss_lc_id')
    CREATE INDEX IX_zz_ss_ss_lc_id ON zz_ss_ss(lc_id);
GO

-- 床位表：按宿舍查询
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_zz_ss_cw_ss_id')
    CREATE INDEX IX_zz_ss_cw_ss_id ON zz_ss_cw(ss_id);
GO

-- 学生表：按床位查询
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_zz_xs_cw_id')
    CREATE INDEX IX_zz_xs_cw_id ON zz_xs(cw_id);
GO

-- ============================================
-- 常用统计视图
-- ============================================

-- 宿舍住宿情况视图（含楼栋、楼层、宿舍、床位、学生信息）
IF EXISTS (SELECT * FROM sys.views WHERE name = 'v_ss_zs_qk')
    DROP VIEW v_ss_zs_qk;
GO

CREATE VIEW v_ss_zs_qk AS
SELECT 
    ld.id AS ld_id, ld.mc AS ld_mc,
    lc.id AS lc_id, lc.lc AS lc_h,
    ss.id AS ss_id, ss.ssh,
    cw.id AS cw_id, cw.cwh,
    cw.zt AS cw_zt,
    xs.id AS xs_id, xs.xm AS xs_xm, xs.xh AS xs_xh,
    xs.bj_id, xs.xjzt,
    bj.mc AS bj_mc
FROM zz_ss_ld ld
JOIN zz_ss_lc lc ON lc.ld_id = ld.id
JOIN zz_ss_ss ss ON ss.lc_id = lc.id
JOIN zz_ss_cw cw ON cw.ss_id = ss.id
LEFT JOIN zz_xs xs ON xs.cw_id = cw.id
LEFT JOIN zz_bj bj ON bj.id = xs.bj_id
WHERE ld.zt = 1 AND lc.zt = 1 AND ss.zt = 1;
GO

-- ============================================
-- 示例数据（可选执行）
-- ============================================
/*
-- 插入楼栋
INSERT INTO zz_ss_ld (mc, bz, px) VALUES (N'1号楼', N'男生宿舍', 1);
INSERT INTO zz_ss_ld (mc, bz, px) VALUES (N'2号楼', N'女生宿舍', 2);

-- 插入楼层（1号楼，3层）
INSERT INTO zz_ss_lc (ld_id, lc) VALUES (1, 1);
INSERT INTO zz_ss_lc (ld_id, lc) VALUES (1, 2);
INSERT INTO zz_ss_lc (ld_id, lc) VALUES (1, 3);

-- 插入宿舍（1号楼1层，3间宿舍）
INSERT INTO zz_ss_ss (lc_id, ssh) VALUES (1, '101');
INSERT INTO zz_ss_ss (lc_id, ssh) VALUES (1, '102');
INSERT INTO zz_ss_ss (lc_id, ssh) VALUES (1, '103');

-- 插入床位（101宿舍6个床位，102宿舍4个床位 - 体现不同宿舍床位数不同）
INSERT INTO zz_ss_cw (ss_id, cwh) VALUES (1, '1');
INSERT INTO zz_ss_cw (ss_id, cwh) VALUES (1, '2');
INSERT INTO zz_ss_cw (ss_id, cwh) VALUES (1, '3');
INSERT INTO zz_ss_cw (ss_id, cwh) VALUES (1, '4');
INSERT INTO zz_ss_cw (ss_id, cwh) VALUES (1, '5');
INSERT INTO zz_ss_cw (ss_id, cwh) VALUES (1, '6');

INSERT INTO zz_ss_cw (ss_id, cwh) VALUES (2, '1');
INSERT INTO zz_ss_cw (ss_id, cwh) VALUES (2, '2');
INSERT INTO zz_ss_cw (ss_id, cwh) VALUES (2, '3');
INSERT INTO zz_ss_cw (ss_id, cwh) VALUES (2, '4');
*/
