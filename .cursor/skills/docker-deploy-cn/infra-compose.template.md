# 共享基础设施 compose 模板（Redis / MinIO / PostgreSQL）

用于**多项目共用一套基础设施**的场景。这份 compose 是**独立的项目**（独立目录、独立 compose 项目名），所有业务项目通过外部网络加入。

## 目录位置

建议与业务项目**平级**，不要放进任何业务项目内部：

```
/www/wwwroot/
├── _shared/              ← 本模板部署到这里（项目名 shared）
│   ├── docker-compose.yml
│   └── .env
├── headphoto/backend/    ← 业务项目
└── zhpt-new/backend/     ← 业务项目
```

## 占位符替换清单

| 占位符 | 含义 | 示例 |
|---|---|---|
| `<共享项目名>` | compose 项目名，决定网络名前缀 | `shared` |
| `<网络名>` | 真实 Docker 网络名（业务项目要引用它） | `shared_default` |

---

## 模板

```yaml
# ============================================================
# 共享基础设施 —— Redis / MinIO / PostgreSQL
#
# 定位：**跨项目共用**的基础设施，独立于任何业务项目。
#   - 业务项目通过外部网络加入这里，用服务名 redis:6379 / minio:9000 / pgsql:5432
#     访问，不写死 IP。
#   - 任何业务项目都**不要**在自己的 compose 里再起一份 redis/minio/pgsql。
#
# 启动：
#   cd /www/wwwroot/_shared
#   docker compose up -d
#
# 常用：
#   docker compose ps
#   docker compose logs -f redis
#   docker compose down          # 停容器，保留数据卷
#   docker compose down -v       # ⚠️ 删数据卷，数据全丢，慎用！
# ============================================================

name: <共享项目名>

services:
  # ---------------------------------------------------------
  # Redis —— 缓存 / 短信验证码 / 会话 / 任务状态
  #
  # 稳定性三件套（缺一不可）：
  #   1. --requirepass   开启密码，防止内网任意主机连上来读写
  #   2. appendonly yes 开启 AOF，每次写入落盘，宕机不丢数据
  #   3. named volume   数据目录挂卷，容器重建不丢数据
  #
  # 为什么 Docker 跑 Redis 完全可以用于生产：
  #   官方镜像跑的就是官方编译的二进制，与源码安装**完全同源**，
  #   不存在额外封装。持久化由 Redis 自身的 RDB + AOF 保证，
  #   与部署方式无关。单机的量级下完全够用。
  #   真正需要哨兵/集群的是"单机扛不住的量"，多项目共用用不着。
  # ---------------------------------------------------------
  redis:
    image: redis:7.2-alpine
    container_name: <共享项目名>-redis
    restart: unless-stopped

    # ⚠️ 密码不要用含 @ : / # ? 等字符的值。
    #    这些字符是 Redis URI（redis://:密码@host:6379）里的分隔符，
    #    业务代码若哪天改用 URL 形式会解析出错。推荐纯字母数字。
    command:
      - redis-server
      - --requirepass
      - ${REDIS_PASSWORD:-Skh123456}
      - --appendonly
      - "yes"
      - --appendfsync
      - "everysec"
      # 内存上限：设为宿主机内存的 60% 左右，留足 OS 缓存。
      - --maxmemory
      - ${REDIS_MAXMEMORY:-512mb}
      - --maxmemory-policy
      - noeviction
      - --maxclients
      - "10000"
      # 慢查询日志：超过 10ms 记一笔，便于排查
      - --slowlog-log-slower-than
      - "10000"
      - --slowlog-max-len
      - "128"

    ports:
      # ⚠️ 端口暴露策略（按实际情况二选一）：
      #
      # ① 多台机器共用一个 Redis（安全性最高）
      #    只绑内网网卡，公网完全访问不到。
      #    ⚠️ 绑定的 IP 必须是本机真实存在的网卡地址，
      #       填错会导致容器起不来（"bind: cannot assign requested address"）。
      #       先查：ip -4 addr show | grep inet
      #    - "${REDIS_BIND_IP:-172.16.100.102}:6379:6379"
      #
      # ② 仅本机使用 / 靠共享网络访问（默认，兼容性最好）
      #    容器间走服务名 redis:6379，不经过宿主机端口。
      #    ⚠️ 若这台机器有公网 IP，务必确认 6379 没暴露到公网！
      #       防火墙：ufw deny 6379/tcp  或  安全组只放行内网段
      - "6379:6379"

    volumes:
      # AOF + RDB 落盘目录。⚠️ 绝不能用 `down -v` 删除。
      - redis-data:/data

    healthcheck:
      # 用密码 ping。redis-cli 的 -a 会打印警告，用 --no-auth-warning 抑制
      test: ["CMD-SHELL", "redis-cli -a \"$$REDIS_PASSWORD\" --no-auth-warning ping | grep -q PONG"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s

    environment:
      # 供 healthcheck 引用（$$ 转义后由容器内 shell 展开）
      REDIS_PASSWORD: "${REDIS_PASSWORD:-Skh123456}"

    logging:
      driver: "json-file"
      options:
        max-size: "20m"
        max-file: "5"

  # ---------------------------------------------------------
  # MinIO —— 对象存储（头像 / 附件 / 导入导出文件）
  #
  # ⚠️ 若目标主机上已经跑着 MinIO 且业务正常，**不要**在这里再起一个 ——
  #    两份数据会分叉。先确认当前用的是哪一套，再决定是否迁移。
  # ---------------------------------------------------------
  minio:
    image: minio/minio:RELEASE.2024-06-13T22-53-53Z
    container_name: <共享项目名>-minio
    restart: unless-stopped
    command: server /data --console-address ":9001"

    ports:
      - "9000:9000"   # S3 API
      - "9001:9001"   # 控制台

    environment:
      MINIO_ROOT_USER: "${MINIO_ROOT_USER:-sharedadmin}"
      MINIO_ROOT_PASSWORD: "${MINIO_ROOT_PASSWORD:-SharedMinio123456}"

    volumes:
      - minio-data:/data

    healthcheck:
      test: ["CMD-SHELL", "mc ready local || exit 1"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s

    logging:
      driver: "json-file"
      options:
        max-size: "20m"
        max-file: "5"

  # ---------------------------------------------------------
  # PostgreSQL —— 关系型主库
  #
  # ⚠️ 只在项目**确实使用 PostgreSQL** 时启用本服务。
  #    若主库是 SQL Server / MySQL 等裸机服务，删掉整个 postgres 段。
  #
  # 多项目共用一个 PostgreSQL 实例的隔离方式（与 Redis 不同）：
  #   - 每个项目一个 **database**（不是 schema）
  #   - 每个项目一个 **role**，权限只授予自己的 database
  #   初始化脚本见下方 init-db 挂载说明
  # ---------------------------------------------------------
  postgres:
    image: postgres:16-alpine
    container_name: <共享项目名>-postgres
    restart: unless-stopped

    environment:
      POSTGRES_USER: ${PG_SUPERUSER:-postgres}
      POSTGRES_PASSWORD: ${PG_SUPERUSER_PASSWORD:?必须设置 PG_SUPERUSER_PASSWORD}
      # ⚠️ 这里只创建**一个**初始库。其他项目的库需要手工创建，
      #    或挂 init 脚本（见 volumes 的 init-db 说明）。
      POSTGRES_DB: ${PG_INIT_DB:-postgres}

    ports:
      # ⚠️ 同 Redis：公网机器务必确认 5432 没暴露到公网
      - "5432:5432"

    volumes:
      # PGDATA 落在 named volume 里 —— 换 PGDATA 子目录会丢数据
      - pg-data:/var/lib/postgresql/data
      # 可选：初始化脚本。.sql 文件按文件名顺序执行，仅在数据为空时运行一次。
      #   ./initdb/01-create-dbs.sql 里写：
      #     CREATE DATABASE proj_a;
      #     CREATE DATABASE proj_b;
      #   ⚠️ 只在首次启动（数据卷为空）时执行；已有数据后不会再跑。
      # - ./initdb:/docker-entrypoint-initdb.d:ro

    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${PG_SUPERUSER:-postgres} -d ${PG_INIT_DB:-postgres}"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s

    # 共享实例的连接数上限，按机器规格调整
    command:
      - "postgres"
      - "-c"
      - "max_connections=${PG_MAX_CONNECTIONS:-200}"
      - "-c"
      - "shared_buffers=${PG_SHARED_BUFFERS:-256MB}"

    logging:
      driver: "json-file"
      options:
        max-size: "20m"
        max-file: "5"

volumes:
  redis-data:
    name: <共享项目名>-redis-data
  minio-data:
    name: <共享项目名>-minio-data
  pg-data:
    name: <共享项目名>-pg-data

networks:
  default:
    # ⚠️ 必须显式命名。业务项目要用 `external: true, name: <网络名>` 引用它。
    #    不写的话 compose 用 "<共享项目名>_default"，项目名一改网络名就变。
    name: <网络名>
```

---

## `.env` 模板

```bash
# ---------- Redis ----------
# ⚠️ 密码建议只用字母数字，不要含 @ : / # ?
#    这些字符是 Redis URI 的分隔符，业务代码改用 redis:// URL 形式时会解析出错。
#    当前代码若用分参数形式（host= / password=）则不受影响。
REDIS_PASSWORD=Skh123456

# 内存上限。按宿主机实际内存的 60% 左右设置。查内存：free -h
REDIS_MAXMEMORY=512mb

# ---------- MinIO ----------
# Root 账号，仅用于运维建桶/改 policy。
# 业务代码**不要**用 root，应该用 Service Account（每个项目一个 AK/SK）。
MINIO_ROOT_USER=sharedadmin
MINIO_ROOT_PASSWORD=SharedMinio123456

# ---------- PostgreSQL ----------
PG_SUPERUSER=postgres
PG_SUPERUSER_PASSWORD=<强密码>
PG_INIT_DB=postgres
PG_MAX_CONNECTIONS=200
PG_SHARED_BUFFERS=256MB
```

---

## 业务项目如何接入

业务项目 `docker-compose.yml` 末尾：

```yaml
    networks:
      - default        # 本项目私有网络
      - shared         # 共享基础设施网络

networks:
  shared:
    external: true
    name: <网络名>
```

业务项目 `.env` 用**服务名**而非 IP：

```
REDIS_ENABLED=true
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=<与共享 .env 一致>

MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=<项目自己的 service account AK>
MINIO_SECRET_KEY=<项目自己的 service account SK>

DATABASE_URL=postgresql://<项目角色>:<密码>@pgsql:5432/<项目库名>
```

---

## 多项目隔离机制

| 资源 | 隔离方式 | 说明 |
|---|---|---|
| Redis | **`REDIS_DB` 逻辑库**（0/1/2...）+ **key 前缀** | 两项都要做。DB 隔离 keyspace，前缀防止逻辑串味 |
| PostgreSQL | **每项目一个 database** + **每项目一个 role** | role 只授予自己 database 的权限 |
| MinIO | **每项目一个 service account** + **bucket 前缀** | 不用 root；bucket 按项目划分 |

**Redis key 前缀规范**：`<项目缩写>:<模块>:<标识>`，如 `zhpt:sms_code:<手机号>`。

---

## 启动顺序（不可颠倒）

```bash
# ① 先起基础设施
cd /www/wwwroot/_shared && docker compose up -d

# ② 再起业务项目
cd /www/wwwroot/<项目>/backend && docker compose up -d --build
```

`external: true` 的网络必须**已存在**，否则业务容器启动失败：

```
network shared_default declared as external, but could not be found
```

---

## 运维速查

```bash
cd /www/wwwroot/_shared

docker compose ps                       # 状态
docker compose logs -f redis            # 日志
docker compose restart redis            # 重启
docker compose down                     # 停容器，保留数据卷
docker compose down -v                  # ⚠️ 删数据卷，数据全丢

# Redis 备份
docker exec shared-redis redis-cli -a '<密码>' --no-auth-warning BGSAVE
docker cp shared-redis:/data/dump.rdb ./backup/redis-$(date +%F).rdb

# PostgreSQL 备份
docker exec shared-postgres pg_dump -U postgres <库名> > ./backup/db-$(date +%F).sql

# MinIO 同步（mc mirror）
mc alias set target http://127.0.0.1:9000 <AK> <SK>
mc mirror target/<bucket> ./backup/<bucket> --overwrite
```

---

## 监控阈值

| 指标 | 检查命令 | 告警阈值 |
|---|---|---|
| Redis 内存 | `redis-cli INFO memory \| grep used_memory_human` | > 80% maxmemory |
| Redis 连接数 | `redis-cli INFO clients \| grep connected_clients` | > 500 |
| Redis 拒绝连接 | `redis-cli INFO stats \| grep rejected_connections` | > 0（maxclients 打满） |
| PostgreSQL 连接数 | `psql -c "SELECT count(*) FROM pg_stat_activity;"` | > 80% max_connections |
| 磁盘 | `df -h` | > 80% |
