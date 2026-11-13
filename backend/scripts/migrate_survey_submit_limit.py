"""
迁移脚本:给 oa_survey_survey 增加 submit_limit / submit_limit_period 字段
并给 oa_survey_answer 增加若干索引(SQL Server 版本)。

适用: 已存在 oa_survey_survey 表(不会重建),只追加字段。
依赖: pyodbc + 项目 init.config 配置

使用方式:
  python scripts/migrate_survey_submit_limit.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 字段默认值
DEFAULTS = {
    'submit_limit': 1,
    'submit_limit_period': 'once',
}


def main():
    import pyodbc
    from init.config import settings

    conn_str = (
        f"DRIVER={{{settings.DB_PARAMS['DRIVER'][1:-1]}}};"
        f"SERVER={settings.HOST};"
        f"DATABASE={settings.DATABASE};"
        f"UID={settings.USER};"
        f"PWD={settings.PASSWORD};"
        "TrustServerCertificate=yes;"
    )
    print(f"[migrate] 连接 SQL Server: {settings.HOST} / {settings.DATABASE}")

    sqls = [
        # 1) 加 submit_limit(默认 1)
        """IF NOT EXISTS (
            SELECT 1 FROM sys.columns
            WHERE object_id = OBJECT_ID(N'oa_survey_survey') AND name = 'submit_limit'
        )
        BEGIN
            ALTER TABLE [oa_survey_survey]
                ADD [submit_limit] INT NOT NULL
                CONSTRAINT [DF_oa_survey_survey_submit_limit] DEFAULT (1);
            PRINT '+ oa_survey_survey.submit_limit 已添加';
        END
        ELSE
            PRINT '- oa_survey_survey.submit_limit 已存在,跳过';""",

        # 2) 加 submit_limit_period(默认 'once',NVARCHAR 兼容中文)
        """IF NOT EXISTS (
            SELECT 1 FROM sys.columns
            WHERE object_id = OBJECT_ID(N'oa_survey_survey') AND name = 'submit_limit_period'
        )
        BEGIN
            ALTER TABLE [oa_survey_survey]
                ADD [submit_limit_period] NVARCHAR(16) NOT NULL
                CONSTRAINT [DF_oa_survey_survey_submit_limit_period] DEFAULT (N'once');
            PRINT '+ oa_survey_survey.submit_limit_period 已添加';
        END
        ELSE
            PRINT '- oa_survey_survey.submit_limit_period 已存在,跳过';""",

        # 3) 索引
        """IF NOT EXISTS (SELECT 1 FROM sys.indexes
            WHERE name = 'idx_answer_device' AND object_id = OBJECT_ID(N'oa_survey_answer'))
            CREATE NONCLUSTERED INDEX [idx_answer_device] ON [oa_survey_answer] ([device_id]); ELSE PRINT '- idx_answer_device 已存在';""",

        """IF NOT EXISTS (SELECT 1 FROM sys.indexes
            WHERE name = 'idx_answer_sid_wx' AND object_id = OBJECT_ID(N'oa_survey_answer'))
            CREATE NONCLUSTERED INDEX [idx_answer_sid_wx] ON [oa_survey_answer] ([sid], [wx_openid]); ELSE PRINT '- idx_answer_sid_wx 已存在';""",

        """IF NOT EXISTS (SELECT 1 FROM sys.indexes
            WHERE name = 'idx_answer_sid_device' AND object_id = OBJECT_ID(N'oa_survey_answer'))
            CREATE NONCLUSTERED INDEX [idx_answer_sid_device] ON [oa_survey_answer] ([sid], [device_id]); ELSE PRINT '- idx_answer_sid_device 已存在';""",

        """IF NOT EXISTS (SELECT 1 FROM sys.indexes
            WHERE name = 'idx_answer_sid_submit_time' AND object_id = OBJECT_ID(N'oa_survey_answer'))
            CREATE NONCLUSTERED INDEX [idx_answer_sid_submit_time] ON [oa_survey_answer] ([sid], [submit_time]); ELSE PRINT '- idx_answer_sid_submit_time 已存在';""",
    ]

    with pyodbc.connect(conn_str, autocommit=True) as conn:
        for i, sql in enumerate(sqls, 1):
            print(f"\n[migrate] [{i}/{len(sqls)}] 执行...")
            cursor = conn.cursor()
            cursor.execute(sql)
            # 拿 PRINT 输出
            while cursor.nextset():
                pass
            messages = [row[0] for row in cursor.messages] if cursor.messages else []
            for msg in messages:
                print(f"  {msg}")
            cursor.close()

    print("\n[migrate] 全部完成 ✓")
    print(f"\n新增字段默认值:")
    print(f"  submit_limit        = {DEFAULTS['submit_limit']}  (1 = 终身只能填1次)")
    print(f"  submit_limit_period = '{DEFAULTS['submit_limit_period']}'  (once = 终身周期)")
    print("\n如需开放某些问卷不限次:")
    print("  UPDATE [oa_survey_survey] SET [submit_limit] = 0 WHERE [sid] IN (...);")


if __name__ == "__main__":
    main()