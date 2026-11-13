"""
反馈工本存储结构迁移脚本（item_type → repair_type_text）

改造目标：
  把旧的 item_type 字段通过字典表 hp_feedback_dict 反查为中文 label，
  填充到 repair_type_text。

填充策略：
  仅翻译：hp_feedback_dict WHERE category='item' AND code=item_type 能查到 label 的行
  跳过条件：
    - 'custom'（"其他" 兏底项，不跳翻译会覆盖 item_custom 原意）
    - 字典里不存在的 code（保留原状以利排查）
    - item_type 为空
  其他情况一律跳过，不动。

为什么跳过 custom：
  字典里 custom → "其他" 是「兏底下拉项」。
  用户选中 custom 后通常还会填 item_custom（具体描述）。
  如果跳 custom 跳"其他"，会覆盖 item_custom 信息、丢失用户原意。

默认 DRY-RUN：只打印 SQL / 影响行数，不改任何数据。
加 --apply 真正执行：
    python scripts/migrate_feedback_item_to_repair_type_text.py --apply

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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    # 强制 UTF-8，避免 Windows 控制台 GBK 编码报错
    stream=__import__("sys").stdout,
)
for _h in logging.getLogger().handlers:
    try:
        _h.stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass
_sys = __import__("sys")
_sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

logger = logging.getLogger("migrate_item_to_repair_type_text")


# ============================================================
# SQL Server 回填 SQL
# ============================================================

# 仅"字典能查到 label 且非 custom"的工单才回填
SQL_BACKFILL = """
UPDATE t
SET t.repair_type_text = RTRIM(LTRIM(d.label))
FROM hp_feedback_ticket t
INNER JOIN hp_feedback_dict d
    ON  d.category = 'item'
    AND d.code     = t.item_type
    AND d.is_active = 1
WHERE (t.item_type IS NOT NULL AND t.item_type <> '' AND t.item_type <> 'custom')
  AND d.label IS NOT NULL AND LTRIM(RTRIM(d.label)) <> ''
  AND (t.repair_type_text IS NULL OR t.repair_type_text = '')
"""

# 报告：按"能否被字典翻译"统计
SQL_REPORT_BY_SOURCE = """
SELECT
    bucket,
    COUNT(*) AS total,
    SUM(CASE WHEN repair_type_text IS NOT NULL AND LTRIM(RTRIM(repair_type_text)) <> '' THEN 1 ELSE 0 END) AS filled
FROM (
    SELECT
        t.id,
        t.item_type,
        t.repair_type_text,
        CASE
            WHEN t.item_type IS NULL OR LTRIM(RTRIM(t.item_type)) = '' THEN 'no_item_type'
            WHEN t.item_type = 'custom' THEN 'is_custom'
            WHEN d.label IS NOT NULL AND LTRIM(RTRIM(d.label)) <> '' THEN 'dict_translated'
            ELSE 'no_dict_match'
        END AS bucket
    FROM hp_feedback_ticket t
    LEFT JOIN hp_feedback_dict d
        ON  d.category = 'item'
        AND d.code     = t.item_type
        AND d.is_active = 1
) s
GROUP BY bucket
ORDER BY bucket;
"""


def _safe_execute(conn, sql: str, dry_run: bool, desc: str):
    """执行单条 SQL；DRY-RUN 只打印。"""
    if dry_run:
        logger.info("[DRY-RUN] %s: %s", desc, " ".join(sql.split()))
        return None
    try:
        from sqlalchemy import text
        result = conn.execute(text(sql))
        conn.commit()
        rows = result.fetchall() if result.returns_rows else None
        n = result.rowcount if (result.rowcount is not None and result.rowcount >= 0) else (len(rows) if rows else 0)
        logger.info("    ✓ %s → rowcount=%s", desc, n)
        return rows
    except Exception as e:
        logger.error("    ✗ %s failed: %s", desc, e)
        raise


def main():
    parser = argparse.ArgumentParser(description="把 item_type 查字典填到 repair_type_text（DRY-RUN 默认）")
    parser.add_argument("--apply", action="store_true", help="真正执行（不加则 DRY-RUN）")
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
        from sqlalchemy import text
        conn = session.connection()

        # 0. 现状报告
        logger.info("=" * 60)
        logger.info("【Step 0】现状报告")
        try:
            total = conn.execute(text("SELECT COUNT(*) FROM hp_feedback_ticket")).fetchone()[0]
            # 仅统计"字典能翻译 + 非 custom"的行
            need_fill = conn.execute(text(
                "SELECT COUNT(*) FROM hp_feedback_ticket t "
                "INNER JOIN hp_feedback_dict d "
                "    ON d.category = 'item' AND d.code = t.item_type AND d.is_active = 1 "
                "WHERE (t.item_type IS NOT NULL AND t.item_type <> '' AND t.item_type <> 'custom') "
                "AND d.label IS NOT NULL AND LTRIM(RTRIM(d.label)) <> '' "
                "AND (t.repair_type_text IS NULL OR t.repair_type_text = '')"
            )).fetchone()[0]
            # custom 工单数（将跳过翻译）
            custom_n = conn.execute(text(
                "SELECT COUNT(*) FROM hp_feedback_ticket WHERE item_type = 'custom'"
            )).fetchone()[0]
            # 不被翻译（custom / 字典缺失）行数
            no_match = conn.execute(text(
                "SELECT COUNT(*) FROM hp_feedback_ticket t "
                "LEFT JOIN hp_feedback_dict d "
                "    ON d.category = 'item' AND d.code = t.item_type AND d.is_active = 1 "
                "WHERE (t.item_type IS NOT NULL AND t.item_type <> '' AND t.item_type <> 'custom') "
                "AND (d.label IS NULL OR LTRIM(RTRIM(d.label)) = '')"
            )).fetchone()[0]
            already = conn.execute(text(
                "SELECT COUNT(*) FROM hp_feedback_ticket "
                "WHERE repair_type_text IS NOT NULL AND repair_type_text <> ''"
            )).fetchone()[0]
            logger.info("  工单总数:        %s", total)
            logger.info("  将被字典翻译的行数: %s", need_fill)
            logger.info("  custom 工单数（跳过翻译）: %s", custom_n)
            logger.info("  字典缺失行数:     %s", no_match)
            logger.info("  repair_type_text 已有值行数: %s", already)

            # 字典里 item 类别有多少
            dict_n = conn.execute(text(
                "SELECT COUNT(*) FROM hp_feedback_dict WHERE category = 'item' AND is_active = 1"
            )).fetchone()[0]
            logger.info("  hp_feedback_dict (item 类别) 启用项数: %s", dict_n)
        except Exception as e:
            logger.error("  读取现状失败: %s", e)
            raise

        # 1. 预览：将影响的行（最多 30 条）打印出来人工核对
        logger.info("=" * 60)
        logger.info("【Step 1】预览（最多 30 条）：仅显示「字典能翻译 + 非 custom」的样本")
        try:
            preview_rows = conn.execute(text("""
                SELECT TOP 30
                    t.id,
                    t.item_type,
                    t.item_custom,
                    t.repair_type_text AS old_text,
                    RTRIM(LTRIM(d.label)) AS new_text
                FROM hp_feedback_ticket t
                INNER JOIN hp_feedback_dict d
                    ON  d.category = 'item'
                    AND d.code     = t.item_type
                    AND d.is_active = 1
                WHERE (t.item_type IS NOT NULL AND t.item_type <> '' AND t.item_type <> 'custom')
                  AND d.label IS NOT NULL AND LTRIM(RTRIM(d.label)) <> ''
                  AND (t.repair_type_text IS NULL OR t.repair_type_text = '')
                ORDER BY t.id
            """)).fetchall()
            for r in preview_rows:
                logger.info("  id=%-5s item_type=%-15s item_custom=%-15s old=%-15s → new=%s",
                            r[0], repr(r[1]), repr(r[2]), repr(r[3]), repr(r[4]))
            if len(preview_rows) == 30:
                logger.info("  ... 仅显示前 30 条样本，实际共 %s 条将受影响", need_fill)
        except Exception as e:
            logger.warning("  预览失败（继续）: %s", e)

        # 2. 执行回填
        logger.info("=" * 60)
        logger.info("【Step 2】执行回填")
        _safe_execute(conn, SQL_BACKFILL, dry_run, "backfill repair_type_text from item_type (via dict)")

        # 3. 执行后报告
        logger.info("=" * 60)
        logger.info("【Step 3】执行后状态")
        if dry_run:
            logger.info("  [DRY-RUN] 跳过验证。加 --apply 执行真实迁移。")
        else:
            try:
                # 按来源分布（最终全表）
                logger.info("  全表按 bucket 分布：")
                for r in conn.execute(text(SQL_REPORT_BY_SOURCE)).fetchall():
                    logger.info("    %-22s total=%s  其中已填 repair_type_text=%s", r[0], r[1], r[2])
            except Exception as e:
                logger.warning("  最终状态读取失败: %s", e)

        logger.info("=" * 60)
        if dry_run:
            logger.warning("⚠ DRY-RUN 完成，未修改数据。加 --apply 执行真实迁移。")
        else:
            logger.info("✅ 回填完成。后续：")
            logger.info("  - 可 DROP COLUMN item_type / item_custom（视业务决定是否一并删除）")
            logger.info("  - 本次脚本只处理数据，不删字段")

    finally:
        session.close()


if __name__ == "__main__":
    main()
