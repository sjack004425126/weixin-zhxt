# ============================================================
# zhpt / backend  ——  Docker 镜像
#
# 基线：Debian bookworm slim + Python 3.11
# 关键点：
#   1) pyodbc 需要 unixODBC + Microsoft SQL Server ODBC 驱动
#      init/config.py 的 DB_PARAMS 写死了 '{ODBC Driver 17 for SQL Server}'，
#      Linux 官方包里**只有 18**，所以镜像里同时装 17 和 18，
#      连接串里的驱动名不用改（见下方 "ODBC 驱动" 段）。
#   2) opencv 换 headless 版（slim 里没有 X11/libGL，避免 "libGL.so.1 not found"）
#   3) gradio 已从运行期依赖中移除（2026-11 美颜改造）：
#      hivision/plugin/beauty/*.py 的 gradio import 已全部改为 __main__ 块内惰性引入，
#      `import hivision` 不再需要 gradio。
#   4) 非 root 运行（app 用户），入口脚本负责修正 bind mount 属主
#
# 两个构建阶段：
#   builder —— 装依赖（含 opencv headless 修复、ODBC 驱动校验、hivision 导入链校验）
#   runtime —— 最终镜像（生产用），代码烘进镜像，改代码要 rebuild
#
#   部署：docker compose up -d --build
#
# ⚠️ 2026-11-03 已删除 dev stage（详见文件末尾说明）。
# ============================================================

# ---------- 构建阶段 ----------
FROM python:3.11-slim-bookworm AS builder

# ⚠️ pip 必须走国内镜像。
#    实测直连 files.pythonhosted.org 只有 ~12 kB/s，构建极易 ReadTimeoutError。
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

# PIP_DEFAULT_TIMEOUT=180：大 wheel（opencv/onnxruntime）中断后留足重试时间
# PIP_RETRIES=10：容器网络抖动不必整体重跑构建
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_DEFAULT_TIMEOUT=180 \
    PIP_RETRIES=10

# 构建 pyodbc 需要 unixODBC 头文件（无 wheel 时回退源码编译）
ARG APT_MIRROR=mirrors.aliyun.com

RUN sed -i "s|deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        unixodbc-dev \
        unixodbc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# ⚠️ 依赖只有这一层。requirements.docker.txt 一旦变化，从这里往后的
#    pip install / COPY --from=builder 全部重跑。
#
#    为什么 pyodbc 不再单独装一层：
#    之前是「RUN 装 pyodbc」+「RUN 装 requirements」两条，
#    改任何一个包都会让 pyodbc 跟着重新编译（要 unixODBC 头文件，几十秒起）。
#    合并成一条后，pyodbc 也走 pip 的 wheel 解析，装完只需一次。
#    —— pyodbc 5.0.1 在 CPython 3.11 有官方预编译 wheel，Linux 上直接下载，
#       不触发编译；只有构建失败才会回退到源码编译，那时才需要 build-essential。
COPY requirements.docker.txt ./

# ⚠️ 这里必须做一次 cv2 修复，否则 import cv2 必崩：
#
#    mtcnn-runtime 的元数据是 `onnxruntime | opencv-python`（硬依赖非 headless 版），
#    pip 无法跳过。而 opencv-python 与 opencv-python-headless **共用同一个 cv2/ 目录**，
#    谁后装谁赢：
#        Installing collected packages: ... opencv-python-headless, opencv-python, ...
#    结果 cv2/ 被非 headless 版覆盖，slim 镜像没有 libGL →
#        ImportError: libGL.so.1: cannot open shared object file
#
#    修法：删掉 cv2/ 目录后用 --no-deps 强制重装 headless。
#    --no-deps 是关键，否则会把 opencv-python 又拉回来。
#    不能用 pip uninstall opencv-python：它会连带删除共享的 cv2/ 文件，
#    把已经装好的 headless 版一起弄坏。
#
# ⚠️ gradio 已不需要：hivision/plugin/beauty/whitening.py 与 grind_skin.py
#    的 gradio import 已改为 `if __name__ == "__main__"` 块内惰性引入，
#    运行期 `import hivision` 不再拉起 gradio（2026-11 美颜改造）。
RUN pip install --prefix=/install -r requirements.docker.txt \
    && rm -rf /install/lib/python3.11/site-packages/cv2 \
    && pip install --prefix=/install --no-deps --force-reinstall \
         opencv-python-headless==4.9.0.80 \
    && PYTHONPATH=/install/lib/python3.11/site-packages \
       python -c "import pyodbc, cv2, numpy, onnxruntime; print('deps ok | pyodbc', pyodbc.version, '| cv2', cv2.__version__)"


# ---------- 运行阶段 ----------
FROM python:3.11-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="zhpt-backend" \
      org.opencontainers.image.description="智校通学生综合管理平台 FastAPI 后端"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai \
    PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
    PIP_DEFAULT_TIMEOUT=180 \
    PIP_RETRIES=10

# 运行时系统依赖：
#   unixodbc          —— pyodbc 运行时
#   libglib2.0-0 等   —— opencv-python-headless
#   fonts-wqy-microhei —— 报告/中文渲染
#   tzdata            —— APScheduler 用 Asia/Shanghai
#
# 国内源：Debian 官方源慢，阿里云快。注意 deb822 格式
# （/etc/apt/sources.list.d/debian.sources），不是老式 sources.list。
# Microsoft ODBC 驱动**必须**走官方 packages.microsoft.com（校验签名，不可换）。
ARG APT_MIRROR=mirrors.aliyun.com

RUN sed -i "s|deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        tzdata \
        unixodbc \
        odbcinst \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 \
        fonts-wqy-microhei \
    && rm -rf /var/lib/apt/lists/*

# Microsoft SQL Server ODBC 驱动
#
# ⚠️ 这里装 **17 和 18 两个版本**，原因：
#    init/config.py 的 DB_PARAMS 写死了 'DRIVER': '{ODBC Driver 17 for SQL Server}'，
#    而 Linux 官方包**只有 18**。如果只装 18，连接串里写 17 → IM002。
#    两个都装，连接串**一个字都不用改**，Windows 开发 / Linux 容器行为一致。
#    （packages.microsoft.com 的 debian/12 源里 msodbcsql17 和 msodbcsql18 都有）
#
# 这一步失败（网络不通/源挂）会让 build 直接失败 —— 这是好事，
# 因为如果这里静默跳过，容器能构建成功，但运行时报：
#     pyodbc.InterfaceError: ('IM002', '[IM002] [unixODBC][Driver Manager]
#     Data source name not found and no default driver specified')
# 那个报错只说"驱动没找到"，不会告诉你是镜像构建阶段就没装上，
# 排查起来非常绕。所以在下面紧接着做一次**构建期校验**。
RUN curl -fsSL https://packages.microsoft.com/config/debian/12/prod.list \
        -o /etc/apt/sources.list.d/mssql-release.list \
    && curl -fsSL https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb \
        -o /tmp/mssql.deb \
    && dpkg -i /tmp/mssql.deb \
    && rm -f /tmp/mssql.deb \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql17 msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*

# 非 root 运行
#
# ⚠️ UID/GID 必须与宿主机目录属主一致（默认 1001:1001）：
#    部署目录 /www/wwwroot/zhpt/backend 及其 logs/ uploads/ data/ 在宿主机上
#    属主是 uid=1001（宝塔建的站点用户）。如果容器里用别的 uid
#    （例如系统默认的 999），bind mount 进来的目录就写不进去：
#        PermissionError: [Errno 13] Permission denied: '/app/logs/xjxt.log'
#    而且这个错发生在 main.py 里 RotatingFileHandler 初始化时 →
#    worker 直接起不来，日志里只有一行 PermissionError，很难联想到是 uid 不匹配。
#
#    ARG 化，方便以后换部署用户（不用改 Dockerfile 本体）。
ARG APP_UID=1001
ARG APP_GID=1001

RUN groupadd -g ${APP_GID} app && useradd -u ${APP_UID} -g app -d /app -s /sbin/nologin app

WORKDIR /app

# 从 builder 拷贝已装好的包
COPY --from=builder /install /usr/local

# ---------- 构建期校验（必须在 COPY --from=builder 之后）----------
# ⚠️ 校验必须在 pyodbc 装好之后才能跑（COPY --from=builder /install /usr/local 之前
#    pyodbc 在 /install 里，import 不到）。
#
# 1) ODBC 驱动必须真的注册上：用 **pyodbc.drivers()** 作为权威判据
#    （应用真正用的就是它），而不是 odbcinst —— 两者偶尔会不一致。
#    校验失败就让 build 直接失败：否则会出现"镜像构建通过、运行时才报
#    IM002"这种最难排查的情况（IM002 只说驱动没找到，不说为什么）。
#
# 2) bcrypt 往返自检：import bcrypt 成功不代表能用 ——
#    passlib 1.7.4 + bcrypt>=4.1 时 import 全过，但登录接口 500。
#    必须跑通真实往返。
#
# 3) hivision 导入链自检：**必须放在 COPY 项目代码之后**（见下方第 8 步）。
#    hivision 是项目内的本地包（backend/hivision/），不是 pip 包，
#    提前校验必然 ModuleNotFoundError。
RUN python -c "import pyodbc; \
print('runtime ok | pyodbc', pyodbc.version); \
d=[x for x in pyodbc.drivers() if x]; \
print('registered ODBC drivers:', d); \
import sys; \
sys.exit(0) if any('SQL Server' in x for x in d) else (print('ERROR: no SQL Server ODBC driver registered -- msodbcsql17/18 install failed'), sys.exit(1))" \
    && python -c "import cv2, numpy, onnxruntime; \
print('runtime ok | cv2', cv2.__version__, '| numpy', numpy.__version__, '| onnx', onnxruntime.__version__)" \
    && python -c "\
import bcrypt; \
from passlib.context import CryptContext; \
print('runtime bcrypt:', bcrypt.__version__); \
c = CryptContext(schemes=['bcrypt'], deprecated='auto'); \
h = c.hash('smoke-test'); \
assert c.verify('smoke-test', h), 'bcrypt roundtrip failed'; \
print('runtime passlib+bcrypt roundtrip OK')"

# 项目代码：包含 common/ controllers/ services/ hivision/ init/ models/ utils/ main.py
COPY --chown=app:app . /app

# ---------- 构建期校验（第二轮）：本地包导入链 ----------
# ⚠️ 必须在 COPY 代码之后跑：hivision 是**项目内的本地包**（backend/hivision/），
#    不是 pip 包。放在前面的校验里必然 ModuleNotFoundError。
#
#    这一步验证的是「cv2 / onnxruntime / mtcnnruntime 能不能真的撑起
#    `import hivision`」——hivision 是项目内的本地包，缺任何一环，
#    证件照链路在运行时才炸。
RUN python -c "\
import hivision; \
from hivision.plugin.beauty.handler import beauty_face; \
from hivision.plugin.beauty.whitening import make_whitening; \
from hivision.creator.choose_handler import choose_handler; \
print('runtime hivision import chain OK')"

# 运行期需要写入的目录（与 docker-compose 的 volume 对应）
RUN mkdir -p /app/logs /app/uploads /app/data \
    && chown -R ${APP_UID}:${APP_GID} /app/logs /app/uploads /app/data

# ---------- 入口脚本：修正 bind mount 的属主 ----------
# ⚠️ 上面那句 chown 只对**镜像层内**的目录有效；
#    bind mount 进来的目录会**覆盖**镜像层，挂载点上属主仍是宿主机的。
#    宿主机属主 uid 与容器内 APP_UID 不一致时，
#    非 root 的 app 用户就写不进去 → worker 启动即崩：
#        PermissionError: [Errno 13] Permission denied: '/app/logs/xjxt.log'
#
#    所以入口脚本以 root 进入 → 修正挂载目录属主 → 再降权回 app 执行 CMD。
#    setpriv 来自 util-linux（debian slim 已内置）。
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# 入口脚本需要 root 来 chown；脚本内部会自行降权到 app。
USER root

# ⚠️ 这里**不**设 APP_UID / APP_GID —— 由 docker-entrypoint.sh 从容器内
#    app 用户的实际 uid/gid 推导，避免「chown 用的 uid」和「进程跑的 uid」
#    两处定义不一致（那正是 2026-11-03 readonly database 的根因）。
#    需要覆盖时用 compose 的 environment 传，且必须与镜像内 app 的 uid 一致。
ENV FIX_MOUNT_OWNER="${FIX_MOUNT_OWNER:-1}"

EXPOSE 3050

# 健康检查不依赖数据库，仅探进程存活（/health 不查 DB）
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:3050/health || exit 1

# ⚠️ 单 worker：
#    应用内用 SQLAlchemy QueuePool + pyodbc，4 个 worker 会各自建 30 条连接池
#    （pool_size=30, max_overflow=50），对 SQL Server 压力过大；
#    且腾讯云短信回调的 IP 白名单校验依赖 X-Forwarded-For，
#    多 worker 会出现并发写同一张 sms_log 表。
#    原 gunicorn 命令用 4 workers，这里保守降到 1，扩容请拆多容器。
#
# 端口 3050 与应用自身配置一致（init/config.py 的 AppConfig.PORT = 3050），
# 反向代理指向 127.0.0.1:3050，容器内必须监听 3050。
CMD ["docker-entrypoint.sh", "gunicorn", "main:app", \
     "--bind", "0.0.0.0:3050", \
     "--workers", "1", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--keep-alive", "2", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--capture-output"]


# ============================================================
# ⚠️ 这里**不再有 dev stage**（2026-11-03 移除）
#
#    之前有 `FROM runtime AS dev`：不 COPY 代码、bind mount 源码进来、
#    用 uvicorn --reload 热重载、以 root 运行。
#
#    移除原因：
#      1) 生产服务器上**一直误跑着 dev 镜像** —— 旧容器
#         `headphoto-backend` 的 Cmd 是 `uvicorn --reload`、User=root，
#         而不是 runtime 的 `gunicorn` + entrypoint 降权。
#         生产跑热重载本身就是错的。
#      2) dev stage 用 `USER root`，所以**掩盖了** bind mount 属主
#         不匹配的问题 —— root 能写任何目录，权限错误永远不会暴露。
#         切到 runtime（非 root + entrypoint）后立刻暴露成
#         `attempt to write a readonly database`。
#      3) 开发机（Windows）直接跑本地 Python 即可，不必起容器。
#
#    如需临时热重载调试，用 runtime 镜像 + 手动改 CMD，不要恢复 dev stage：
#        docker run --rm -v $(pwd):/app -p 3050:3050 #            -e FASTAPI_ENV=development --entrypoint uvicorn #            zhpt-backend:latest main:app --reload --host 0.0.0.0 --port 3050
# ============================================================
