-- 留宿申请表
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='zz_ss_ls' AND xtype='U')
CREATE TABLE zz_ss_ls (
    id INT IDENTITY(1,1) PRIMARY KEY,
    xs_id INT NOT NULL,
    xs_xm NVARCHAR(50),
    xs_xh NVARCHAR(50),
    bj_id INT,
    bj_mc NVARCHAR(50),
    ld_id INT,
    ld_mc NVARCHAR(50),
    ss_id INT,
    ss_ssh NVARCHAR(20),
    cw_id INT,
    cw_cwh NVARCHAR(10),
    ls_type NVARCHAR(20) DEFAULT 'weekend',
    ls_reason NVARCHAR(500),
    start_date DATETIME NOT NULL,
    end_date DATETIME NOT NULL,
    status INT DEFAULT 0,
    approve_by NVARCHAR(50),
    approve_time DATETIME,
    approve_remark NVARCHAR(200),
    cjsj DATETIME DEFAULT GETDATE(),
    gxsj DATETIME DEFAULT GETDATE()
);
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_zz_ss_ls_xs_id')
    CREATE INDEX IX_zz_ss_ls_xs_id ON zz_ss_ls(xs_id);
GO
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_zz_ss_ls_bj_id')
    CREATE INDEX IX_zz_ss_ls_bj_id ON zz_ss_ls(bj_id);
GO
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_zz_ss_ls_status')
    CREATE INDEX IX_zz_ss_ls_status ON zz_ss_ls(status);
GO
