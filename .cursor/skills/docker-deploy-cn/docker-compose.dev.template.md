# docker-compose.dev.yml 模板（开发）

复制下面代码块内容到项目根目录，命名为 `docker-compose.dev.yml`，并替换 `<...>` 占位符。

## 占位符替换清单

| 占位符 | 含义 | 示例 |
|---|---|---|
| `<服务名>` | 服务 key（**必须与 docker-compose.yml 里的 key 完全一致**） | `headphoto-backend` |
| `<APP_PORT>` | 应用端口 | `3081` |
| `<相对目录>` | 需挂载的源码目录 | `app` |

## 模板

```yaml
# ============================================================
# <项目名> —— 开发期覆盖配置
#
# ⚠️ 必须用显式 -f 指定，**绝不能**命名 docker-compose.override.yml
#    （那个名字会被 docker compose 自动加载，部署到服务器时会意外套上开发配置：
#     挂载代码、DEBUG 开着、APP_ENV=development。）
#
# 启动：
#   docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
#
# 改代码后：容器自动重载，**不用 restart**
# 改了 env 或装了新包：
#   docker compose -f docker-compose.yml -f docker-compose.dev.yml restart <服务名>
#
# ⚠️ 只隔离了**镜像 tag**，其余（容器名、端口）与生产完全一致 ——
#    反向代理（OpenResty/Nginx）指向 127.0.0.1:<APP_PORT>，端口不能动。
#    含义：开发和生产**不能同时跑**（容器名 + 端口都会冲突），
#    切换时先 down 再 up。
#
# 切回生产：
#   docker compose -f docker-compose.yml -f docker-compose.dev.yml down
#   docker compose up -d --build
# ============================================================

services:
  # 服务名必须与 docker-compose.yml 里的 key **完全一致**，
  # 否则 compose 认为是两个不同服务：base 里那个照常起（生产配置），
  # dev 这个另起一个（开发配置）—— 容器名和端口都会冲突。
  <服务名>:
    # ⚠️ 必须用**独立的 image tag**。
    #    base 里是 `<服务名>:latest`，如果 dev 也用同一个 tag，
    #    `up -d --build` 会把 latest 这个 tag **重新指向 dev 镜像**，
    #    生产镜像就变成 dangling（<none>）了。后果：
    #      - 之后生产 `docker compose up -d`（漏了 --build）会直接复用 dev 镜像
    #        → 生产跑起 uvicorn --reload + USER root + 代码挂载
    #      - 两种镜像无法并存，来回切换必须重建
    #    用 :dev 独立 tag 后，两个镜像并存、互不覆盖。
    image: <服务名>:dev
    # 用 dev stage：依赖与 runtime 完全一致，只是不烘代码 + 开 --reload
    build:
      target: dev

    environment:
      APP_ENV: "development"
      DEBUG: "true"

      # 开发期放开线程：宿主机核少，且不和生产服务抢资源
      OMP_NUM_THREADS: "${OMP_NUM_THREADS:-8}"
      OPENBLAS_NUM_THREADS: "${OMP_NUM_THREADS:-8}"
      MKL_NUM_THREADS: "${OMP_NUM_THREADS:-8}"

    volumes:
      # ---------- 代码挂载：核心 ----------
      # 挂源码目录 → /app，容器内路径与生产镜像完全一致，
      # 相对路径行为相同（Word 模板、模型文件等）。
      #
      # ⚠️ 只挂"代码目录"而非 . ：挂 . 会把宿主的 __pycache__、.venv、
      #    data/、logs/ 一起带进来。
      #    - data/ logs/ export_temp/ 已在基础配置里单独挂载，这里再挂会遮住它们
      #    - __pycache__ 里的 .pyc 是 Windows 平台编译的，Linux 读到会出错
      #    逐目录挂载虽然啰嗦，但边界清晰、没有意外污染。
      - ./<相对目录>:/app/<相对目录>
      # 其他需要挂载的源码目录同理逐个列出
      - ./main.py:/app/main.py
```

## 为什么 dev 不写 container_name 和 ports

| 项 | 原因 |
|---|---|
| 不写 `container_name` | 继承 base 的值 → 容器名冲突时能明确报错，而不是静默起第二个容器占用端口 |
| 不写 `ports` | 继承 base 的值 → 反向代理配置不用改，dev 环境同样能通过域名访问 |

**代价**：开发与生产**不能同时运行**。切换流程：

```bash
# prod → dev
docker compose down
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build

# dev → prod
docker compose -f docker-compose.yml -f docker-compose.dev.yml down
docker compose up -d --build
```

## 如果确实需要同时跑（牺牲反代一致性）

只有在**确认反代不指向开发端口**的前提下才这么做：

```yaml
    container_name: <服务名>-dev
    ports:
      - "<另一个端口>:<APP_PORT>"
```

这样两个容器可并存，但开发服务**不走反向代理**，只能直接访问 `http://localhost:<另一个端口>`。
