"""
清理 /private/hq/feedback/ 路径下的孤儿对象。

判定规则:
  - DB 表 feedback_ticket.image_keys 中存在 → 保留
  - 不在 DB 中的全部视为孤儿 → 列出待删

默认 DRY-RUN：只列出对象 / 大小 / 数量，不删任何东西。
要真正删除，加 --apply：
    python scripts/cleanup_feedback_orphans.py --apply

【数据源】
  - MinIO:    bucket = guizhou-zhpt-prod-private
              prefix = private/hq/feedback/
  - SQL Server: DatabaseConfig 默认 OA (zhpt 数据库)
               表 hp_feedback_ticket.images / handle_images 字段为 JSON 数组字符串

【使用前必读】
- 跑 --apply 前必须先在测试环境验证
- 脚本内置 DRY-RUN：第一次不加 --apply 只看打印
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# 让脚本可以直接 `python scripts/cleanup_feedback_orphans.py` 跑
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# .env 自动加载由 utils.minio_client 负责，这里只显式 load 一次确保 DB 配置也拿到
try:
    from dotenv import load_dotenv
    load_dotenv(BACKEND_DIR / ".env", override=False)
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cleanup_orphans")


def list_all_keys_in_minio(client, bucket: str, prefix: str) -> list[str]:
    keys: list[str] = []
    for obj in client.list_objects(bucket, prefix=prefix, recursive=True):
        keys.append(obj.object_name)
    return keys


def collect_db_keys() -> set[str]:
    """从 hp_feedback_ticket 表里聚合所有 image key（用户提交图 + 整改后图）。"""
    try:
        import pyodbc
    except ImportError:
        logger.error("pyodbc 未安装,无法查 DB。pip install pyodbc")
        sys.exit(2)

    from init.config import get_database_config
    cfg = get_database_config()
    conn = pyodbc.connect(cfg.DB_CONN_STR, timeout=15)
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = 'hp_feedback_ticket'
              AND COLUMN_NAME IN ('images', 'handle_images')
        """)
        cols = [r[0] for r in cur.fetchall()]
        if not cols:
            logger.warning("hp_feedback_ticket 表未找到 images/handle_images 列,视为 DB 无关联")
            return set()
        union = " UNION ALL ".join(
            f"SELECT CAST([{c}] AS NVARCHAR(MAX)) FROM hp_feedback_ticket WHERE [{c}] IS NOT NULL"
            for c in cols
        )
        cur.execute(union)
        bag: set[str] = set()
        for (raw,) in cur.fetchall():
            if not raw:
                continue
            txt = raw if isinstance(raw, str) else raw.decode("utf-8", "ignore")
            try:
                arr = json.loads(txt)
            except Exception:
                # 容错: 可能是 "a.jpg,b.jpg" 这种格式
                arr = [x.strip() for x in txt.replace("[", "").replace("]", "").replace('"', "").split(",") if x.strip()]
            if isinstance(arr, list):
                for k in arr:
                    if isinstance(k, str):
                        bag.add(k.lstrip("/"))
        return bag
    finally:
        conn.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真实删除（默认 DRY-RUN）")
    ap.add_argument("--prefix", default="private/hq/feedback/")
    args = ap.parse_args()

    from utils.minio_client import gateway
    if not gateway.available:
        logger.error("MinIO 网关不可用,检查 .env")
        return 2

    logger.info("列出 MinIO 对象 prefix=%s", args.prefix)
    minio_keys = list_all_keys_in_minio(gateway.client, gateway.bucket_private, args.prefix)
    logger.info("MinIO 共有 %d 个对象", len(minio_keys))

    logger.info("查询 DB 中已引用的 image key ...")
    db_keys = collect_db_keys()
    logger.info("DB 引用了 %d 个 key", len(db_keys))

    # 比较
    referenced = [k for k in minio_keys if k in db_keys]
    orphans = [k for k in minio_keys if k not in db_keys]
    logger.info("引用数 %d, 孤儿数 %d", len(referenced), len(orphans))

    if orphans:
        sample = orphans[:10]
        logger.info("孤儿样本(前 10):")
        for k in sample:
            logger.info("  - %s", k)

    if not args.apply:
        logger.info("【DRY-RUN】未执行删除。要真实删除请加 --apply")
        return 0

    if not orphans:
        logger.info("没有孤儿对象,无需清理")
        return 0

    # 二次确认
    confirm = input(f"确认删除 {len(orphans)} 个孤儿对象? 输入 yes 继续: ").strip()
    if confirm != "yes":
        logger.info("已取消")
        return 0

    ok = 0
    for k in orphans:
        if gateway.delete_object(gateway.bucket_private, k):
            ok += 1
    logger.info("删除完成: 成功 %d / 总数 %d", ok, len(orphans))
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)