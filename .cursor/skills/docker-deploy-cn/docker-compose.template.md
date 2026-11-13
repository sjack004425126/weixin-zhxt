# docker-compose.yml 模板（生产）

复制下面代码块内容到项目根目录，命名为 `docker-compose.yml`，并替换 `<...>` 占位符。

## 占位符替换清单

| 占位符 | 含义 | 示例 |
|---|---|---|
| `<项目名>` | compose 项目名（决定网络/容器名前缀） | `headphoto` |
| `<服务名>` | 服务 key（**dev 覆盖文件里必须一致**） | `headphoto-backend` |
| `<APP_PORT>` | 宿主机→容器端口 | `3081` |
| `<相对目录>` | 需持久化/挂载的宿主机目录 | `data` |

## 模板

```yaml
# ============================================================
# <项目名> —— 一键起服务
#
#   docker compose up -d --build
#   docker compose logs -f <服务名>
#
# 注意：外部依赖（SQL Server / Redis / MinIO 等）若是**已有的外部服务**，
#       compose 里只编排应用自己。部署机必须能访问这些内网地址。
# ============================================================

# 项目名：决定 compose 资源名前缀（网络 <项目名>_default、容器 <服务名>-1 等）。
# ⚠️ 不写这一行的话，compose 默认拿**当前目录名**当项目名 ——
#    部署到 /www/wwwroot/xxx/backend 就会得到 "backend_default" 这种名字。
#    写死它，目录改名也不影响。
name: <项目名>

services:
  <服务名>:
    build:
      context: .
      dockerfile: Dockerfile
      # ⚠️ 必须显式指定 target: runtime
      #
      # Dockerfile 里的**最后一个 stage 是 dev**（FROM runtime AS dev），
      # 而 Docker 默认构建「最后一个 stage」。不写 target 时，
      # `docker compose up -d --build`（生产）实际构建的是 dev 镜像：
      #   - CMD 变成 uvicorn --reload（生产不该开热重载）
      #   - USER 变成 root（生产该用 app 用户降权）
      #
      # 开发时用 docker-compose.dev.yml 覆盖成 dev，它自己带 build.target: dev，
      # 两边不会打架。
      target: runtime
      args:
        # 国内源；内网离线或需回官方时：
        # docker compose build --build-arg APT_MIRROR=deb.debian.org
        APT_MIRROR: "mirrors.aliyun.com"
    image: <服务名>:latest
    container_name: <服务名>
    restart: unless-stopped

    ports:
      # 宿主机 <APP_PORT> → 容器 <APP_PORT>
      - "<APP_PORT>:<APP_PORT>"

    # 直接注入真实环境变量，优先级高于镜像内 .env
    # 好处：改配置只需 restart，不用重新 build
    env_file:
      - .env

    environment:
      # --- 运行环境 ---
      APP_ENV: "production"
      # DEBUG=true 才会开放 /docs。想先看接口文档就 true，正式上线改 false
      DEBUG: "${DEBUG:-true}"
      HOST: "0.0.0.0"
      PORT: "<APP_PORT>"
      TZ: "Asia/Shanghai"

      # --- 关键：ODBC 驱动名在 Linux 上与 Windows 不同 ---
      #
      # ⚠️ 这里必须用**字面量**，不要用 "${...}" 插值：
      #    插值变量在目标机器的 .env 里不存在时会**解析成空串**，
      #    而 environment 段优先级**高于** env_file，
      #    空串会把 .env 里正确的值**覆盖掉** →
      #        sqlalchemy.exc.ArgumentError:
      #        Could not parse SQLAlchemy URL from string ''
      #
      # Linux 官方包只提供 Driver 18（Windows 才有 Driver 17），
      # 驱动名由 app/core/config.py 在运行时套用到连接串上 ——
      # 连接串**只有一份**（在 .env 里，不含 driver 参数），
      # 不需要维护 DATABASE_URL / DATABASE_URL_DOCKER 两份。
      #
      # 详见 cross-platform-traps.md
      # ⚠️ 项目不用 SQL Server 就删掉这两行。
      DB_ODBC_DRIVER: "ODBC Driver 18 for SQL Server"
      # Driver 18 默认开启 TLS 加密，内网自签证书必须显式信任
      # （Driver 17 不认这个参数，代码里会按驱动名自动决定是否追加）
      DB_ODBC_TRUST_SERVER_CERT: "true"

      # --- 用 PostgreSQL 时启用（主机名是服务名，不是 IP）---
      # DATABASE_URL: "postgresql://<角色>:<密码>@pgsql:5432/<库名>"

      # --- 证件照抠图是 CPU 密集型（OpenCV + onnxruntime + MTCNN），
      # 不限制线程数会瞬间吃满宿主机全部核心导致整台机器变卡
      OMP_NUM_THREADS: "${OMP_NUM_THREADS:-4}"
      OPENBLAS_NUM_THREADS: "${OMP_NUM_THREADS:-4}"
      MKL_NUM_THREADS: "${OMP_NUM_THREADS:-4}"

    volumes:
      # ⚠️ <相对目录>/ 是权限模块的 SQLite(auth.sqlite)：用户、角色、菜单、Casbin 策略都在里面
      #    必须持久化，否则每次重建容器都会回到默认账号
      - ./<相对目录>:/app/<相对目录>
      # 应用日志 + 短信发送记录（会往 logs/sms_requests.log 追加）
      - ./logs:/app/logs
      # 导出临时文件
      - ./export_temp:/app/export_temp

    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://127.0.0.1:<APP_PORT>/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 40s

    logging:
      driver: "json-file"
      options:
        max-size: "20m"
        max-file: "5"

    networks:
      # 本项目私有网络（compose 自动创建 <项目名>_default）
      - default
      # 公共基础设施网络（infra/docker-compose.yml 创建的 shared_default）
      # 加入后，容器内可直接用 redis:6379 / minio:9000 访问，
      # 不再依赖 172.16.100.102 这类会变的 IP。
      #
      # ⚠️ external: true 表示"这个网络已存在，不要由我创建"。
      #    如果 infra 还没启动，业务容器会直接启动失败并报：
      #        network shared_default declared as external, but could not be found
      #    解决办法：先启动 infra 的 compose
      - shared

networks:
  shared:
    external: true
    name: shared_default

# ==========================================================================
# 说明：
# 1) 为什么 --workers 1（写在 Dockerfile 的 CMD 里）：
#    应用启动时会拉起 APScheduler 定时任务 + 内存任务队列 + 写 task_records.json，
#    权限库是 SQLite(WAL 单写)。多 worker 会导致
#      - 定时任务被重复执行 N 次
#      - 内存队列的任务状态互相覆盖
#      - Casbin/SQLite 写竞争
#    需要横向扩容时，拆成多个容器各自跑定时任务，或把定时任务抽出去单独跑。
#
# 2) 部署顺序（Redis/MinIO 是公用基础设施，先于业务项目启动）：
#      cd /www/wwwroot/_shared && docker compose up -d
#      cd /www/wwwroot/xxx/backend && docker compose up -d --build
# ==========================================================================
```

## 可裁剪的段落

| 段落 | 不需要时 |
|---|---|
| `DB_DRIVER` | 不连 SQL Server → 删除 |
| `networks.shared` + 顶层 `networks` | 无共用基础设施网络 → 删除 |
| `OMP_NUM_THREADS` 等 | 非 CPU 密集型 → 删除 |
| `healthcheck` | 不需要探活 → 删除 |
| `volumes` 中的某项 | 该目录无需持久化 → 删除 |

## 日志轮转建议

`json-file` 默认 `20m × 5 = 100MB`，高频访问日志会很快滚掉，历史查不到。生产建议改用 `local` 驱动：

```yaml
    logging:
      driver: "local"
      options:
        max-size: "50m"
        max-file: "10"
        compress: "true"    # 归档自动 gzip，约 10:1 压缩比
```
