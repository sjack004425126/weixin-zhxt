"""把 chongzhi.db 里的 meters 表数据迁移到 zhpt-new.zz_dianbiao_meters（MSSQL）。

两种使用方式：
1. 离线模式：python migrate_dianbiao.py --sql-only
   → 只在 migrations/20261020_migrate_zz_dianbiao_meters.sql 里生成
     "DELETE + 分批 INSERT" 的 SQL 片段，交给运维在 SSMS 里执行。

2. 在线模式（默认）：python migrate_dianbiao.py
   → 通过 settings.py / .env 里 SQL Server URI 直接 INSERT 到目标库。
     走 SQLAlchemy core 做 executemany，每批 200 条。

注意：
- 需 pip install sqlalchemy pyodbc（或 pymssql）
- 在线模式只读 chongzhi.db → 不带 raw 中可能的 datetime 字符串，直接构造
  ISO 字符串给 SQL Server。

依赖：
- 本机/网络能联通目标 SQL Server
- chongzhi 路径（CHI_DB_PATH）与 zhpt-new 路径（--target-env）
"""
import argparse
import os
import sys
from pathlib import Path

# 默认 chongzhi.db 路径
DEFAULT_CHONGZHI_DB = Path(r'E:\MyPrj\chongzhi\backend\data\chongzhi.db')
DEFAULT_OUT_SQL = Path(__file__).resolve().parent.parent / 'migrations' / '20261020_migrate_zz_dianbiao_meters.sql'


COLUMNS = [
    'id', 'device_id', 'sn', 'mac', 'house_id',
    'estate_name', 'building', 'house_name', 'full_name',
    'tenant_name', 'status', 'resident_count',
    'price', 'basic_price', 'du', 'total', 'total_money', 'total_recharge',
    'online_status', 'is_disabled', 'recharge_disabled', 'expired_at',
    'month_limit', 'month_recharge', 'qrcode',
    'raw', 'remote_synced_at',
    'created_at', 'updated_at',
]
INT_COLS = {'id', 'device_id', 'house_id', 'resident_count',
            'online_status', 'is_disabled', 'recharge_disabled', 'total_recharge'}
DT_COLS = {'expired_at', 'remote_synced_at', 'created_at', 'updated_at'}
JSON_COLS = {'raw'}


def fmt_dt(v):
    if v is None or v == '':
        return None
    s = str(v).strip()
    if not s:
        return None
    if '.' in s:
        s = s.split('.', 1)[0]
    return s  # 'YYYY-MM-DD HH:MM:SS'


def fmt_int(v):
    if v is None or v == '':
        return None
    try:
        return int(v)
    except Exception:
        return None


def fmt_str(v):
    if v is None:
        return None
    return str(v)


def fmt_json(v):
    if v is None or v == '':
        return None
    return str(v)


def read_rows(chongzhi_db: Path):
    """从 chongzhi.db 读出所有行，转成 dict（key 在 COLUMNS 里）。"""
    import sqlite3
    if not chongzhi_db.exists():
        raise FileNotFoundError(f'找不到 chongzhi.db: {chongzhi_db}')
    conn = sqlite3.connect(str(chongzhi_db))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute('SELECT * FROM meters ORDER BY id')
    rows_raw = cur.fetchall()
    conn.close()

    rows = []
    for r in rows_raw:
        rd = dict(r)
        out = {}
        for c in COLUMNS:
            v = rd.get(c)
            if c in INT_COLS:
                out[c] = fmt_int(v)
            elif c in DT_COLS:
                out[c] = fmt_dt(v)
            elif c in JSON_COLS:
                out[c] = fmt_json(v)
            else:
                out[c] = fmt_str(v)
        rows.append(out)
    return rows


def write_sql_only(rows, out_sql: Path):
    """生成 MSSQL 风格的 DELETE + 分批 INSERT 文件。"""
    import datetime as _dt
    out_lines = []
    out_lines.append('-- ============================================================')
    out_lines.append('-- 从 chongzhi.db 迁移 meters 表数据 -> zhpt-new.zz_dianbiao_meters')
    out_lines.append(f'-- 生成时间: {_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    out_lines.append(f'-- 行数: {len(rows)}')
    out_lines.append('-- ============================================================')
    out_lines.append('-- 幂等性：先 DELETE 再 INSERT；若要保留 zhpt-new 已有数据，请注释掉 DELETE')
    out_lines.append('IF OBJECT_ID(N\'dbo.zz_dianbiao_meters\', N\'U\') IS NULL')
    out_lines.append('BEGIN')
    out_lines.append('    PRINT N\'请先执行 migrations/20261020_add_zz_dianbiao_meters.sql 建表\';')
    out_lines.append('    RETURN;')
    out_lines.append('END')
    out_lines.append('GO')
    out_lines.append('DELETE FROM dbo.zz_dianbiao_meters;')
    out_lines.append('GO')
    out_lines.append('')

    # 显式插入 id（IDENTITY 列），必须开 IDENTITY_INSERT；
    # SQL Server 要求 IDENTITY_INSERT 在一个会话/事务内保持，因此 BEGIN TRAN 包住整段；
    # 任何一个批次失败都 ROLLBACK 恢复。
    out_lines.append('-- 必须开 IDENTITY_INSERT，否则显式插入 id 会报 544：')
    out_lines.append('--   当 IDENTITY_INSERT 设置为 OFF 时，不能为表 \'zz_dianbiao_meters\' 中的标识列插入显式值')
    out_lines.append('SET XACT_ABORT ON;')
    out_lines.append('BEGIN TRY')
    out_lines.append('    BEGIN TRAN;')
    out_lines.append('    SET IDENTITY_INSERT dbo.zz_dianbiao_meters ON;')
    out_lines.append('')

    BATCH = 100
    for batch_idx in range(0, len(rows), BATCH):
        batch = rows[batch_idx:batch_idx + BATCH]
        col_list = ', '.join(COLUMNS)
        out_lines.append(f'    INSERT INTO dbo.zz_dianbiao_meters ({col_list}) VALUES')
        vals = []
        for r in batch:
            parts = []
            for c in COLUMNS:
                v = r.get(c)
                if v is None:
                    parts.append('NULL')
                elif c in INT_COLS:
                    parts.append(str(v))
                elif c in DT_COLS:
                    parts.append(f"'{v}'")
                else:
                    # 字符串字段，转义单引号
                    s = str(v).replace("'", "''")
                    parts.append(f"'{s}'")
            vals.append('        (' + ', '.join(parts) + ')')
        out_lines.append(',\n'.join(vals) + ';')
        out_lines.append('')

    out_lines.append('    SET IDENTITY_INSERT dbo.zz_dianbiao_meters OFF;')
    out_lines.append('    COMMIT TRAN;')
    out_lines.append('    PRINT N\'✅ zz_dianbiao_meters 数据迁移完成: \' + CAST(@@ROWCOUNT AS NVARCHAR(10)) + N\' 行\';')
    out_lines.append('END TRY')
    out_lines.append('BEGIN CATCH')
    out_lines.append('    IF @@TRANCOUNT > 0 ROLLBACK TRAN;')
    out_lines.append('    SET IDENTITY_INSERT dbo.zz_dianbiao_meters OFF;')
    out_lines.append('    DECLARE @msg NVARCHAR(4000) = ERROR_MESSAGE();')
    out_lines.append('    RAISERROR(@msg, 16, 1);')
    out_lines.append('END CATCH')
    out_lines.append('GO')

    out_sql.parent.mkdir(parents=True, exist_ok=True)
    out_sql.write_text('\n'.join(out_lines), encoding='utf-8')
    print(f'[sql-only] 已生成: {out_sql}  ({len(rows)} 行)')


def write_to_mssql(rows):
    """直连 SQL Server 写入。"""
    # 把 backend 加到 sys.path 以读取 settings
    here = Path(__file__).resolve()
    backend_root = here.parent.parent
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    from init.config import get_config
    from init.database_optimized import db_manager

    config_name = os.getenv('FASTAPI_ENV', 'production')
    cfg = get_config(config_name)
    engine = db_manager.init_db(config_name)
    print(f'[online] 连接 SQL Server: {str(engine.url).split("@")[-1]}')

    insert_sql = (
        f"INSERT INTO dbo.zz_dianbiao_meters ({', '.join(COLUMNS)}) "
        f"VALUES ({', '.join(['?']*len(COLUMNS))})"
    )

    BATCH = 200
    with engine.begin() as conn:
        conn.exec_driver_sql("DELETE FROM dbo.zz_dianbiao_meters")
        # MSSQL IDENTITY 列必须开 IDENTITY_INSERT 才能显式插入 id
        conn.exec_driver_sql("SET IDENTITY_INSERT dbo.zz_dianbiao_meters ON")
        for batch_idx in range(0, len(rows), BATCH):
            batch = rows[batch_idx:batch_idx + BATCH]
            payload = [tuple(r.get(c) for c in COLUMNS) for r in batch]
            conn.exec_driver_sql(insert_sql, payload)
        conn.exec_driver_sql("SET IDENTITY_INSERT dbo.zz_dianbiao_meters OFF")
    print(f'[online] 写入完成: {len(rows)} 行')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default=str(DEFAULT_CHONGZHI_DB), help='chongzhi.db 路径')
    parser.add_argument('--sql-only', action='store_true', help='只生成 SQL 文件，不写库')
    parser.add_argument('--out', default=str(DEFAULT_OUT_SQL), help='SQL 文件输出路径')
    args = parser.parse_args()

    rows = read_rows(Path(args.db))
    print(f'读取到 {len(rows)} 行')

    if args.sql_only:
        write_sql_only(rows, Path(args.out))
    else:
        write_to_mssql(rows)


if __name__ == '__main__':
    main()
