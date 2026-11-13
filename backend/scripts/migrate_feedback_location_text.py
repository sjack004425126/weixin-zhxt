"""
反馈工单存储结构迁移脚本（2026-09-27）

改造目标：hp_feedback_ticket 表新增纯文本列，不再依赖字典 id 做精确匹配。

新增列：
  - location_text_fuzzy  NVARCHAR(255)  地点自由文本（LIKE 模糊搜索用）
  - repair_type_text     NVARCHAR(64)   维修类型自由文本（LIKE 模糊搜索用）

回填逻辑：
  - location_text_fuzzy ← COALESCE(TRIM(location_full_path), TRIM(location_text))
  - repair_type_text    ← TRIM(repair_type_label)

默认 DRY-RUN：只打印 SQL / 影响行数，不改任何数据。
加 --apply 真正执行：
    python scripts/migrate_feedback_location_text.py --apply

使用前：
  - 先在测试环境验证
  - 生产环境执行前备份数据
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# 添加 backend 根目录到 sys.path，以便 import init.database_optimized / models.models
_backend_root = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(_backend_root))

from init.database_optimized import db_manager
from init.config import get_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    # 强制 UTF-8，避免 Windows 控制台 GBK 编码报错
    stream=__import__("sys").stdout,
)
# 把 root logger handler 的编码强制设为 utf-8（Windows + Python 3.6+）
import sys as _sys
for _h in logging.getLogger().handlers:
    try:
        _h.stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass
_sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
logger = logging.getLogger("migrate_feedback_location")


# ============================================================
# SQL Server DDL
# ============================================================

SQL_ADD_COLS = """
-- 1. 新增列（IF NOT EXISTS 语义在 SQL Server 通过 IF NOT EXISTS(...) 检查实现）
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('hp_feedback_ticket')
      AND name = 'location_text_fuzzy'
)
BEGIN
    ALTER TABLE hp_feedback_ticket ADD location_text_fuzzy NVARCHAR(255) NULL;
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('hp_feedback_ticket')
      AND name = 'repair_type_text'
)
BEGIN
    ALTER TABLE hp_feedback_ticket ADD repair_type_text NVARCHAR(64) NULL;
END;
"""

SQL_BACKFILL = """
-- 回填已有数据
-- 优先使用 location_full_path（字典快照路径），回退到 location_text（用户自由文本）
UPDATE hp_feedback_ticket
SET location_text_fuzzy = RTRIM(LTRIM(
    COALESCE(NULLIF(RTRIM(LTRIM(location_full_path)), ''), NULLIF(RTRIM(LTRIM(location_text)), ''))
));

UPDATE hp_feedback_ticket
SET repair_type_text = RTRIM(LTRIM(repair_type_label))
WHERE repair_type_label IS NOT NULL;
"""

SQL_REPORT = """
SELECT
    'location_text_fuzzy' AS col_name,
    COUNT(*) AS total_rows,
    SUM(CASE WHEN location_text_fuzzy IS NULL THEN 1 ELSE 0 END) AS null_count,
    SUM(CASE WHEN location_text_fuzzy IS NOT NULL THEN 1 ELSE 0 END) AS filled_count
FROM hp_feedback_ticket
UNION ALL
SELECT
    'repair_type_text',
    COUNT(*),
    SUM(CASE WHEN repair_type_text IS NULL THEN 1 ELSE 0 END),
    SUM(CASE WHEN repair_type_text IS NOT NULL THEN 1 ELSE 0 END)
FROM hp_feedback_ticket;
"""


def _run_sql_block(conn, sql: str, dry_run: bool):
    """执行多语句 SQL 块（每条单独 execute，因为 SQL Server 不支持多语句字符串直接 exec）。"""
    # 去掉注释和空行，逐条提取
    statements = []
    for line in sql.split("\n"):
        line = line.strip()
        if not line or line.startswith("--"):
            continue
        statements.append(line)

    combined = " ".join(statements)
    # 按分号分割（保留末尾分号）
    for stmt in combined.split(";"):
        stmt = stmt.strip()
        if not stmt:
            continue
        if not stmt.endswith(";"):
            stmt += ";"
        if dry_run:
            logger.info("[DRY-RUN] Would execute: %s", stmt[:120])
        else:
            try:
                conn.execute(conn.connection.commit() or None)  # flush
                conn.execute(conn.connection.connection, stmt)
                conn.connection.commit()
                logger.info("    ✓ executed: %s", stmt[:100])
            except Exception as e:
                logger.error("    ✗ failed: %s  → %s", stmt[:100], e)
                raise


def _safe_execute(conn, sql: str, dry_run: bool, desc: str):
    """安全执行一条 SQL。"""
    if dry_run:
        logger.info("[DRY-RUN] %s: %s", desc, sql.strip()[:120])
        return None
    try:
        from sqlalchemy import text
        result = conn.execute(text(sql))
        conn.commit()
        rows = result.fetchall() if result.returns_rows else None
        logger.info("    ✓ %s → %s row(s) affected/fetched", desc, result.rowcount if result.rowcount >= 0 else (len(rows) if rows else 0))
        return rows
    except Exception as e:
        logger.error("    ✗ %s failed: %s", desc, e)
        raise


def main():
    parser = argparse.ArgumentParser(description="迁移反馈工单存储结构（DRY-RUN 模式默认）")
    parser.add_argument("--apply", action="store_true", help="真正执行迁移（不加则仅 DRY-RUN）")
    parser.add_argument("--env", default="production", help="环境配置名（default=production）")
    args = parser.parse_args()

    dry_run = not args.apply

    if dry_run:
        logger.warning("⚠  DRY-RUN 模式：不会修改任何数据。加 --apply 真正执行。")

    # 初始化数据库连接
    try:
        db_manager.init_db(args.env)
        logger.info("数据库连接初始化成功（env=%s）", args.env)
    except Exception as e:
        logger.error("数据库连接初始化失败: %s", e)
        sys.exit(1)

    session = db_manager.get_session()

    try:
        conn = session.connection()

        from sqlalchemy import text

        # 0. 现状报告
        logger.info("=" * 60)
        logger.info("【Step 0】现状报告")
        try:
            rows = conn.execute(text("SELECT COUNT(*) AS total FROM hp_feedback_ticket")).fetchone()
            logger.info("  当前工单总数: %s", rows[0] if rows else "?")
        except Exception as e:
            logger.warning("  无法读取总数（表可能不存在）: %s", e)

        # 检查列是否已存在
        def _column_exists(name: str) -> bool:
            try:
                rs = conn.execute(text(
                    "SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('hp_feedback_ticket') AND name = :n"
                ), {"n": name}).fetchone()
                return bool(rs)
            except Exception:
                return False

        loc_exists = _column_exists("location_text_fuzzy")
        typ_exists = _column_exists("repair_type_text")
        logger.info("  location_text_fuzzy 列存在: %s", loc_exists)
        logger.info("  repair_type_text    列存在: %s", typ_exists)

        if loc_exists and typ_exists:
            null_loc = conn.execute(text(
                "SELECT COUNT(*) FROM hp_feedback_ticket WHERE location_text_fuzzy IS NULL"
            )).fetchone()
            null_typ = conn.execute(text(
                "SELECT COUNT(*) FROM hp_feedback_ticket WHERE repair_type_text IS NULL"
            )).fetchone()
            has_loc = conn.execute(text(
                "SELECT COUNT(*) FROM hp_feedback_ticket WHERE location_text_fuzzy IS NOT NULL"
            )).fetchone()
            has_typ = conn.execute(text(
                "SELECT COUNT(*) FROM hp_feedback_ticket WHERE repair_type_text IS NOT NULL"
            )).fetchone()
            logger.info("  location_text_fuzzy: NULL=%s / NOT NULL=%s", null_loc[0], has_loc[0])
            logger.info("  repair_type_text:    NULL=%s / NOT NULL=%s", null_typ[0], has_typ[0])

        # 1. 新增列
        logger.info("=" * 60)
        logger.info("【Step 1】新增列（IF NOT EXISTS，幂等）")
        if dry_run:
            logger.info("[DRY-RUN] IF NOT EXISTS 检查 + ALTER TABLE ...")
            logger.info("  → ADD location_text_fuzzy NVARCHAR(255) NULL")
            logger.info("  → ADD repair_type_text NVARCHAR(64) NULL")
        else:
            # SQL Server：逐条 ALTER TABLE
            add_stmts = [
                ("check_add_location_text_fuzzy",
                 "IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('hp_feedback_ticket') AND name = 'location_text_fuzzy') "
                 "ALTER TABLE hp_feedback_ticket ADD location_text_fuzzy NVARCHAR(255) NULL;"),
                ("check_add_repair_type_text",
                 "IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('hp_feedback_ticket') AND name = 'repair_type_text') "
                 "ALTER TABLE hp_feedback_ticket ADD repair_type_text NVARCHAR(64) NULL;"),
            ]
            for desc, sql in add_stmts:
                _safe_execute(conn, sql, dry_run, desc)

        # 2. 回填数据
        logger.info("=" * 60)
        logger.info("【Step 2】回填已有数据")
        logger.info("  location_text_fuzzy ← COALESCE(location_full_path, location_text)")
        logger.info("  repair_type_text    ← repair_type_label")
        _safe_execute(conn,
            "UPDATE hp_feedback_ticket SET location_text_fuzzy = RTRIM(LTRIM("
            "COALESCE(NULLIF(RTRIM(LTRIM(location_full_path)), ''), NULLIF(RTRIM(LTRIM(location_text)), ''))"
            "))",
            dry_run, "backfill location_text_fuzzy")
        _safe_execute(conn,
            "UPDATE hp_feedback_ticket SET repair_type_text = RTRIM(LTRIM(repair_type_label)) "
            "WHERE repair_type_label IS NOT NULL",
            dry_run, "backfill repair_type_text")

        # 3. 最终报告
        logger.info("=" * 60)
        logger.info("【Step 3】执行后状态")
        if dry_run:
            logger.info("  [DRY-RUN] 跳过验证")
        else:
            try:
                rows = conn.execute(text("SELECT COUNT(*) AS total FROM hp_feedback_ticket")).fetchone()
                null_loc2 = conn.execute(text(
                    "SELECT COUNT(*) FROM hp_feedback_ticket WHERE location_text_fuzzy IS NULL"
                )).fetchone()
                null_typ2 = conn.execute(text(
                    "SELECT COUNT(*) FROM hp_feedback_ticket WHERE repair_type_text IS NULL"
                )).fetchone()
                logger.info("  总数: %s  |  location_text_fuzzy NULL: %s  |  repair_type_text NULL: %s",
                             rows[0], null_loc2[0], null_typ2[0])
            except Exception as e:
                logger.warning("  最终状态读取失败: %s", e)

        logger.info("=" * 60)
        if dry_run:
            logger.warning("⚠ DRY-RUN 完成，未修改数据。加 --apply 执行真实迁移。")
        else:
            logger.info("✅ 迁移完成。后续改动参考：")
            logger.info("  - zhpt-new/controllers/feedback.py  提交时写入新列")
            logger.info("  - headphoto/.../feedback_ticket_controller.py  筛选/排序/导出改用新列")

    finally:
        session.close()


if __name__ == "__main__":
    main()
