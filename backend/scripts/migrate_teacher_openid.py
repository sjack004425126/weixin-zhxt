"""
迁移脚本:给 oa_t（教师表）增加微信 openid 绑定字段

背景:
  教师端（开放教师 / 中职教师）新增"微信一键登录"（openid 登录）。
  首次仍需通过手机号快捷登录一次，后端会把 openid 写入 oa_t，
  之后即可直接用 openid 登录。

新增列:
  - t_wx_openid       NVARCHAR(200) NULL  微信 openid
  - t_wx_openid_hash  NVARCHAR(64)  NULL  openid 的 SHA256 哈希（隐私合规存储）

依赖: pyodbc + 项目 init.config 配置

使用方式:
  python scripts/migrate_teacher_openid.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


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
        # 1) 加 t_wx_openid
        """IF NOT EXISTS (
            SELECT 1 FROM sys.columns
            WHERE object_id = OBJECT_ID(N'oa_t') AND name = 't_wx_openid'
        )
        BEGIN
            ALTER TABLE [oa_t] ADD [t_wx_openid] NVARCHAR(200) NULL;
            PRINT '+ oa_t.t_wx_openid 已添加';
        END
        ELSE
            PRINT '- oa_t.t_wx_openid 已存在,跳过';""",

        # 2) 加 t_wx_openid_hash
        """IF NOT EXISTS (
            SELECT 1 FROM sys.columns
            WHERE object_id = OBJECT_ID(N'oa_t') AND name = 't_wx_openid_hash'
        )
        BEGIN
            ALTER TABLE [oa_t] ADD [t_wx_openid_hash] NVARCHAR(64) NULL;
            PRINT '+ oa_t.t_wx_openid_hash 已添加';
        END
        ELSE
            PRINT '- oa_t.t_wx_openid_hash 已存在,跳过';""",

        # 3) 唯一索引（同一 openid 只允许绑定一个教师）
        """IF NOT EXISTS (SELECT 1 FROM sys.indexes
            WHERE name = 'ux_oa_t_wx_openid' AND object_id = OBJECT_ID(N'oa_t'))
            CREATE UNIQUE NONCLUSTERED INDEX [ux_oa_t_wx_openid]
                ON [oa_t] ([t_wx_openid])
                WHERE [t_wx_openid] IS NOT NULL;
            ELSE PRINT '- ux_oa_t_wx_openid 已存在,跳过';""",
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
    print("\n说明:")
    print("  - 新字段默认为空，历史教师需先做一次「手机号快捷登录」才会写入 openid")
    print("  - 若已有重复 openid 数据，唯一索引创建会失败，请先清理重复值")


if __name__ == "__main__":
    main()
