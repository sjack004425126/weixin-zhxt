"""
从远程服务器爬取学生照片并上传到MinIO
- 读取 oa_xs 表中 headphoto=1 的学生
- 根据学号拼接图片URL下载
- 以身份证号.jpg命名存入MinIO的headphoto桶
"""
import os
import sys
import time
import urllib.parse
import requests
from io import BytesIO
from minio import Minio
from minio.error import S3Error
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# 加载环境变量
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# ========== 配置 ==========
# 数据库
DB_HOST = os.getenv('DB_HOST', '172.16.100.101')
DB_PORT = os.getenv('DB_PORT', '1433')
DB_USER = os.getenv('DB_USER', 'zhxt')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'Skh@1234')
DB_DATABASE = os.getenv('DB_DATABASE', 'OA')

# MinIO
MINIO_HOST = os.getenv('MINIO_HOST', '172.16.100.102:9000')
MINIO_ACCESS_KEY = os.getenv('MINIO_ACCESS_KEY', '9zHT3JykwM66M9FBTFkC')
MINIO_SECRET_KEY = os.getenv('MINIO_SECRET_KEY', '3o5DXbxSbUbB9rnRNkQ4CDnwHuiqlnT64H64iUjJ')
MINIO_BUCKET = 'headphoto'

# 图片源地址模板
PHOTO_URL_TEMPLATE = 'http://172.16.100.101/static/kdxs_ks_zp/{xh}.jpg?t={ts}'

# 请求超时（秒）
REQUEST_TIMEOUT = 15
# ========== 配置结束 ==========


def get_db_engine():
    DB_PARAMS = {
        'DRIVER': os.getenv('DB_DRIVER', '{ODBC Driver 17 for SQL Server}'),
        'SERVER': f'{DB_HOST},{DB_PORT}',
        'DATABASE': DB_DATABASE,
        'UID': DB_USER,
        'PWD': DB_PASSWORD,
        'TrustServerCertificate': 'yes'
    }
    conn_str = ';'.join(f"{k}={v}" for k, v in DB_PARAMS.items())
    uri = f"mssql+pyodbc:///?odbc_connect={urllib.parse.quote_plus(conn_str)}"
    return create_engine(uri, pool_pre_ping=True)


def get_minio_client():
    return Minio(
        MINIO_HOST,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False
    )


def main():
    print("=" * 60)
    print("  开放教育学生照片爬取 -> MinIO")
    print("=" * 60)

    # 1. 连接数据库
    print("\n[1/3] 连接数据库...")
    engine = get_db_engine()
    Session = sessionmaker(bind=engine)
    session = Session()
    print(f"  数据库连接成功: {DB_HOST}:{DB_PORT}/{DB_DATABASE}")

    # 2. 连接MinIO
    print("[2/3] 连接MinIO...")
    minio_client = get_minio_client()
    if not minio_client.bucket_exists(MINIO_BUCKET):
        minio_client.make_bucket(MINIO_BUCKET)
        print(f"  创建桶: {MINIO_BUCKET}")
    print(f"  MinIO连接成功: {MINIO_HOST}/{MINIO_BUCKET}")

    # 3. 查询学生
    print("[3/3] 查询 headphoto=1 的学生...")
    result = session.execute(
        text("SELECT xs_id, xs_xh, xs_sfzh, xs_xm FROM oa_xs WHERE headphoto = 1 AND xs_sfzh IS NOT NULL AND xs_xh IS NOT NULL")
    )
    students = result.fetchall()
    total = len(students)
    print(f"  共找到 {total} 个有照片的学生\n")

    if total == 0:
        print("没有需要处理的学生，退出。")
        session.close()
        return

    success_count = 0
    skip_count = 0
    fail_count = 0
    start_time = time.time()

    for idx, row in enumerate(students, 1):
        xs_id, xh, sfzh, xm = row
        sfzh = sfzh.strip() if sfzh else ''
        xh = xh.strip() if xh else ''
        xm = xm.strip() if xm else ''

        prefix = f"[{idx}/{total}]"

        if not sfzh or not xh:
            print(f"{prefix} 跳过 {xm}(ID:{xs_id}) - 学号或身份证号为空")
            skip_count += 1
            continue

        # 检查MinIO是否已存在
        file_name = f"{sfzh}.jpg"
        try:
            minio_client.stat_object(MINIO_BUCKET, file_name)
            print(f"{prefix} 跳过 {xm}({xh}) - MinIO已存在 {file_name}")
            skip_count += 1
            continue
        except S3Error:
            pass  # 不存在，继续下载

        # 下载图片
        url = PHOTO_URL_TEMPLATE.format(xh=xh, ts=int(time.time()))
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                print(f"{prefix} 失败 {xm}({xh}) - HTTP {resp.status_code}")
                fail_count += 1
                continue

            content_type = resp.headers.get('Content-Type', '')
            if 'image' not in content_type and len(resp.content) < 1000:
                print(f"{prefix} 失败 {xm}({xh}) - 返回非图片内容 (Content-Type: {content_type}, Size: {len(resp.content)})")
                fail_count += 1
                continue

            photo_bytes = resp.content

        except requests.exceptions.RequestException as e:
            print(f"{prefix} 失败 {xm}({xh}) - 下载异常: {e}")
            fail_count += 1
            continue

        # 上传到MinIO
        try:
            minio_client.put_object(
                MINIO_BUCKET,
                file_name,
                BytesIO(photo_bytes),
                length=len(photo_bytes),
                content_type='image/jpeg'
            )
            print(f"{prefix} 成功 {xm}({xh}) -> {file_name} ({len(photo_bytes)} bytes)")
            success_count += 1
        except Exception as e:
            print(f"{prefix} 失败 {xm}({xh}) - 上传MinIO异常: {e}")
            fail_count += 1

    elapsed = time.time() - start_time
    session.close()

    print("\n" + "=" * 60)
    print(f"  处理完成! 耗时: {elapsed:.1f}秒")
    print(f"  总计: {total} | 成功: {success_count} | 跳过: {skip_count} | 失败: {fail_count}")
    print("=" * 60)


if __name__ == '__main__':
    main()
