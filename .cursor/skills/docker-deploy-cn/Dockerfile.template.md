# Dockerfile 模板

复制下面代码块内容到项目根目录，命名为 `Dockerfile`，并替换 `<...>` 占位符。

## 占位符替换清单

| 占位符 | 含义 | 示例 |
|---|---|---|
| `<项目名>` | OCI 镜像 title（镜像**名**由 compose 的 `image:` 决定） | `headphoto-backend` |
| `<项目描述>` | OCI label 描述 | `智校通 headphoto FastAPI 后端` |
| `<APP_PORT>` | 应用监听端口 | `3081` |
| `<APP_MODULE>` | FastAPI 入口模块 | `main` |
| `<APP_OBJECT>` | FastAPI 实例名 | `app` |
| `requirements.docker.txt` | 依赖文件名 | `requirements.txt` |

## 模板

```dockerfile
# ============================================================
# <项目名> —— Docker 镜像
#
# 基线：Debian bookworm slim + Python 3.11
# 关键点：
#   1) pyodbc 需要 unixODBC + Microsoft SQL Server ODBC 驱动 18
#   2) opencv 换 headless 版（slim 里没有 X11/libGL，避免 "libGL.so.1 not found"）
#   3) 应用内有 APScheduler + 内存任务队列 + Casbin SQLite → 必须单 worker
#
# 两个构建目标：
#   runtime（默认，生产）—— 代码烘进镜像，改代码要 rebuild（约十几秒）
#   dev     （开发）        —— 代码靠 bind mount 挂进来，改完只 restart（1 秒）
#
#   生产：docker compose up -d --build
#   开发：docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
# ============================================================

# ---------- 构建阶段 ----------
FROM python:3.11-slim-bookworm AS builder

# ⚠️ pip 必须走国内镜像。
#    实测直连 files.pythonhosted.org 只有 ~12 kB/s，opencv 的 49.6MB wheel
#    下载 20 分钟必然 ReadTimeoutError，构建直接失败（exit code: 2）。
#    PyPI 官方源对国内服务器不友好，这是硬性要求，不是可选项。
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

# PIP_DEFAULT_TIMEOUT=180：大 wheel（opencv 49.6MB）中断后留足重试时间
# PIP_RETRIES=10：容器网络抖动不必整体重跑构建
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_DEFAULT_TIMEOUT=180 \
    PIP_RETRIES=10

# 构建 pyodbc / lxml 等需要编译链
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
RUN pip install --prefix=/install -r requirements.docker.txt \
    && rm -rf /install/lib/python3.11/site-packages/cv2 \
    && pip install --prefix=/install --no-deps --force-reinstall \
         opencv-python-headless==4.9.0.80 \
    && PYTHONPATH=/install/lib/python3.11/site-packages \
       python -c "import pyodbc, cv2, numpy, onnxruntime; print('deps ok | pyodbc', pyodbc.version, '| cv2', cv2.__version__)"


# ---------- 运行阶段 ----------
FROM python:3.11-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="<项目名>" \
      org.opencontainers.image.description="<项目描述>"

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
#   fonts-wqy-microhei —— 证件照水印/文档中文渲染
#   tzdata            —— APScheduler 用 Asia/Shanghai
#
# 国内源：Debian 官方 695ms → 阿里云 103ms。
# 注意 deb822 格式（/etc/apt/sources.list.d/debian.sources），不是老式 sources.list。
# Microsoft ODBC 驱动**必须**走官方 packages.microsoft.com（校验签名，不可换）。
ARG APT_MIRROR=mirrors.aliyun.com

RUN sed -i "s|deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        tzdata \
        unixodbc \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 \
        fonts-wqy-microhei \
    && rm -rf /var/lib/apt/lists/*

# Microsoft SQL Server ODBC Driver 18
# ⚠️ 这一段只在项目**确实连 SQL Server** 时保留；不连就整段删掉。
RUN curl -fsSL https://packages.microsoft.com/config/debian/12/prod.list \
        -o /etc/apt/sources.list.d/mssql-release.list \
    && curl -fsSL https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb \
        -o /tmp/mssql.deb \
    && dpkg -i /tmp/mssql.deb \
    && rm -f /tmp/mssql.deb \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*

# 非 root 运行
RUN groupadd -r app && useradd -r -g app -d /app -s /sbin/nologin app

WORKDIR /app

# 从 builder 拷贝已装好的包
COPY --from=builder /install /usr/local

# 在 runtime 里再验一次 cv2：builder 阶段验过，但 runtime 的系统库不同
# （slim 基础镜像 + 这层装的 apt 包）。只有在这里能确认「最终镜像」可运行。
#
# ---------- 构建期校验：ODBC 驱动必须真的注册上 ----------
# ⚠️ 用 pyodbc.drivers() 作判据（应用实际用的就是它），而不是 odbcinst ——
#    两者偶尔不一致（odbcinst 配置在非默认路径时），但 pyodbc 是实际生效的那个。
#
# ⚠️ 这个校验必须放在 COPY --from=builder /install /usr/local **之后** ——
#    之前 pyodbc 还在 /install 里，import 不到，会误判失败。
#
# 校验失败就让 build 直接失败，避免"镜像构建通过、运行时才报 IM002"
# 这种最难排查的情况（IM002 只说驱动没找到，不说为什么）。
RUN python -c "import cv2, pyodbc, onnxruntime, numpy; \
    print('runtime ok | cv2', cv2.__version__, '| pyodbc', pyodbc.version)" \
    && python -c "import pyodbc; \
d=[x for x in pyodbc.drivers() if x]; \
print('registered ODBC drivers:', d); \
import sys; \
sys.exit(0) if any('SQL Server' in x for x in d) else (print('ERROR: no SQL Server ODBC driver registered -- msodbcsql18 install failed'), sys.exit(1))" \
    && python -c "\
import bcrypt; \
from passlib.context import CryptContext; \
print('runtime bcrypt:', bcrypt.__version__); \
c = CryptContext(schemes=['bcrypt'], deprecated='auto'); \
h = c.hash('smoke-test'); \
assert c.verify('smoke-test', h), 'bcrypt roundtrip failed'; \
print('runtime passlib+bcrypt roundtrip OK')"

# 项目代码：包含 app/、hivision/、muban/(Word 模板)、main.py
COPY --chown=app:app . /app

# 运行期需要写入的目录（与 docker-compose 的 volume 对应）
RUN mkdir -p /app/data /app/logs /app/export_temp /app/app/photo \
    && chown -R app:app /app/data /app/logs /app/export_temp /app/app/photo

USER app

EXPOSE <APP_PORT>

# 健康检查不依赖数据库，仅探进程存活（/health 不查 DB）
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:<APP_PORT>/health || exit 1

# 单 worker：应用内有定时任务 + 内存队列 + SQLite 锁，多 worker 会重复执行/互相覆盖
CMD ["gunicorn", "<APP_MODULE>:<APP_OBJECT>", \
     "--bind", "0.0.0.0:<APP_PORT>", \
     "--workers", "1", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--capture-output"]


# ============================================================
# ---------- 开发阶段 ----------
#
# 复用 runtime 的**全部依赖层**（OS 包 + 487MB Python 包），只是：
#   1) 不 COPY 项目代码（改用 bind mount 挂进来）
#   2) 换成 uvicorn --reload，改代码自动重启
#   3) 以 root 运行，避免宿主机文件 UID 与容器 app 用户不匹配导致 Permission denied
#
# ⚠️ 为什么依赖必须留在镜像里、不能改成"运行时 pip install"：
#    那 487MB 包要下载+编译，每次 restart 都重来一遍，几分钟起步；
#    而且 pip 装包要写 /usr/local，镜像只读层，改不动。
#    依赖是"不变的部分"，代码是"常变的部分" —— 只有代码适合挂载。
#
# 用法：docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
# ============================================================
FROM runtime AS dev

# ⚠️ 注意 PYTHONDONTWRITEBYTECODE 保持继承 runtime 的 =1（不写 .pyc）。
#    改代码挂载进来时，若允许写字节码，容器会在你 Windows 源码树里生成
#    __pycache__/*.pyc，污染宿主机且和 Windows 平台字节码混在一起。
#    代价只是容器每次启动多解析一遍源码（毫秒级），换来宿主机干净。
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai \
    PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
    PIP_DEFAULT_TIMEOUT=180 \
    PIP_RETRIES=10

# 开发期用 root：bind mount 进来的文件属主是宿主机 UID，
# 非 root 的 app 用户会 Permission denied（app/photo 要写文件）。
# 生产镜像（runtime）仍保持 USER app，不受影响。
#
# ⚠️ USER root 必须在下面任何写操作之前生效。
#    runtime 结尾是 USER app，dev 继承它 —— 若不先切回 root，
#    任何 pip install / mkdir 都会以 app 用户执行：
#        ERROR: Could not install packages due to an OSError:
#               [Errno 13] Permission denied: '/app/.local'
#    （pip 装不进 /usr/local 就回退到用户目录，而 /app 属主是 root）
USER root

# 开发期额外工具：watchfiles 让 --reload 用 polling 监听，
# 绕开 Docker Desktop on Windows 不传播 inotify 的问题
#
# ⚠️ 这里**不需要**再装 watchfiles：
#    `uvicorn[standard]==0.27.0` 本身就把 watchfiles 作为依赖装上了
#    （构建日志里的 "Successfully installed ... watchfiles-1.3.0 ..."），
#    且 builder 阶段以 root 装好后已通过
#    `COPY --from=builder /install /usr/local` 进入本镜像。
#    重复安装既无必要，又会以非 root 身份触发上面的 Permission denied。
RUN python -c "import watchfiles; print('watchfiles ok |', watchfiles.__version__)"

WORKDIR /app

# 只建目录，不放代码。代码由 compose 的 bind mount 覆盖进来。
# 挂载点必须存在，否则 docker 会在宿主机上创建同名空目录（很难排查）。
RUN mkdir -p /app/app/photo /app/data /app/logs /app/export_temp

EXPOSE <APP_PORT>

CMD ["uvicorn", "<APP_MODULE>:<APP_OBJECT>", \
     "--host", "0.0.0.0", \
     "--port", "<APP_PORT>", \
     "--reload", \
     "--reload-dir", "/app", \
     "--reload-exclude", "*.py[cod]", \
     "--reload-exclude", "data/*", \
     "--reload-exclude", "logs/*", \
     "--reload-exclude", "export_temp/*", \
     "--log-level", "info"]
```

## 可裁剪的段落

| 段落 | 不需要时 |
|---|---|
| MS SQL Server ODBC Driver 18 | 项目不连 SQL Server → 整段删除 |
| `build-essential` / `unixodbc-dev` | 依赖全为纯 wheel → 可从 builder 删掉 |
| `libglib2.0-0` 等 opencv 运行库 | 不用 OpenCV → 删除 |
| `fonts-wqy-microhei` | 无中文渲染需求 → 删除 |
| cv2 修复段 | 不用 OpenCV → 删除 |
| `HEALTHCHECK` | 编排层已有 healthcheck → 可删 |
| `pyodbc` 导入校验 | 不连 SQL Server → 从校验语句里删掉 |
| bcrypt 往返自检 | 不用 passlib/bcrypt → 从校验语句里删掉 |
| ODBC 驱动校验 | 不连 SQL Server → 整条 `python -c` 删掉 |

---

## ⚠️ 依赖钉版本的硬性要求

**`requirements.docker.txt` 里涉及密码哈希的依赖必须分开写并钉死版本**：

```bash
# ❌ 错误：方括号会让 pip 顺带装最新的 bcrypt(5.x)，与 passlib 1.7.4 不兼容
passlib[bcrypt]==1.7.4

# ✅ 正确：分开写，显式钉 bcrypt <4.1
passlib==1.7.4
bcrypt>=4.0.1,<4.1
```

原因：passlib 1.7.4 加载 bcrypt 后端时会跑一次自检，自检用了 **255 字节**的测试口令。
bcrypt **4.x** 对超 72 字节的口令**静默截断** → 自检通过；
bcrypt **≥4.1**（现在解析到 5.0.0）改成**直接抛异常** →
`ValueError: password cannot be longer than 72 bytes` → 登录接口 500。

详见 [cross-platform-traps.md](cross-platform-traps.md)。
