---
name: docker-deploy-cn
description: Scaffold and operate Docker deployments for Python/FastAPI projects in China mainland network environments. Generates a multi-stage Dockerfile with Aliyun PyPI/APT mirrors, a production docker-compose.yml, and a dev override compose file, then handles build, switch, and startup. Use when the user asks to containerize a Python/FastAPI project, add or fix Dockerfile/compose files, configure domestic mirrors (pip/apt), create a dev-vs-production Docker workflow, or troubleshoot Docker build and startup failures.
---

# 国内网络环境下的 Python/FastAPI Docker 部署脚手架

生成一套**生产可直接用**的 Docker 文件，并给出可靠的构建/切换/启动流程。

## 何时使用

- 给 Python / FastAPI 项目加 Docker 化
- 需要在**国内网络**下构建镜像（pip/apt 走不通官方源）
- 需要区分生产镜像与开发镜像（热重载）
- 排查 `docker build` 失败、`ReadTimeoutError`、libGL 缺失、权限 denied

---

## 八条不可违背的原则

1. **国内源是硬性要求，不是可选项。** 直连 `files.pythonhosted.org` 实测仅 ~12 kB/s，一个 50MB wheel 会超时失败。
2. **多阶段构建 + 显式 `target`。** `runtime` 供生产，`dev` 供开发。Dockerfile 的**最后一个 stage 是 dev**，所以 compose 里**必须**显式写 `target: runtime`，否则生产会构建出 dev 镜像。
3. **dev 与 prod 用独立 image tag。** 生产 `xxx-backend:latest`，开发 `xxx-backend:dev`。共用 tag 会让 dev 构建把 latest 重新指向 dev 镜像，生产 `up -d`（漏 `--build`）就会误用 dev 镜像。
4. **生产降权到非 root。** `runtime` 结尾 `USER app`；`dev` 必须显式切回 `USER root`（bind mount 的文件属主是宿主 UID，非 root 会 Permission denied）。
5. **绝不能命名 `docker-compose.override.yml`。** 该文件会被 `docker compose` 自动加载，部署到服务器时会意外套上开发配置。
6. **共享基础设施独立 compose 项目，业务项目只「加入」网络，绝不自己再起一份。** Redis / MinIO / PostgreSQL 归基础设施 compose 统一管；每个业务容器**同时属于私有网络和共享网络**。详见 [network-topology.md](network-topology.md)。
7. **连接串与平台相关配置必须单一数据源。** 跨平台差异项（如 ODBC 驱动名）单独配置、由代码运行时套用，**绝不维护两份连接串**。详见 [cross-platform-traps.md](cross-platform-traps.md)。
8. **依赖版本要钉死，并在 Dockerfile 里做构建期自检。** 依赖漂移要在 **build 阶段**暴露，而不是部署后 500。详见 [cross-platform-traps.md](cross-platform-traps.md)。

---

## 工作流程

### Step 0 — 收集项目信息

先问清（或从代码推断）以下信息，不要凭空假设：

| 需确认项 | 说明 |
|---|---|
| 应用入口 | 如 `main:app`（FastAPI） |
| 宿主机端口 | 需与反向代理（OpenResty/Nginx）指向一致，**不能随意更改** |
| 依赖文件 | `requirements.docker.txt` / `pyproject.toml` |
| 系统依赖 | 是否有 pyodbc / OpenCV / 中文字体 / MS SQL Driver 等 |
| 持久化目录 | 数据库文件、日志、导出临时目录 |
| 外部服务 | DB/Redis/MinIO 是已存在的还是本 compose 内编排 |
| 是否含定时任务 | 决定 `--workers` 是否必须为 1 |
| **开发/生产平台差异** | Windows → Linux 的差异项（如 ODBC 驱动名），见 [cross-platform-traps.md](cross-platform-traps.md) |

### Step 1 — 生成 Dockerfile

复制 [Dockerfile.template.md](Dockerfile.template.md) 中的代码块到项目根目录，命名为 `Dockerfile`，替换占位符（清单见该文件顶部）。

必须保留的要点：

- `ARG PIP_INDEX_URL` / `ARG APT_MIRROR` 提供**可覆盖的默认值**，内网离线时可切回官方源。
- **依赖只装一层**：`pip install` 合为一条 `RUN`，否则改任何一个包都会触发 pyodbc 等重编译。
- builder 装编译链，runtime 不装 —— 否则镜像白白变大。
- 若用 OpenCV：必须强制 `opencv-python-headless` 并删掉 `cv2/` 目录重装（原因见模板内注释）。
- runtime 阶段**再验一次 import**，因为 runtime 的系统库与 builder 不同。
- **关键依赖要做功能自检，而不只是 import 自检。** `import bcrypt` 成功不代表能用 —— passlib + bcrypt 版本不兼容时，import 全过，但登录接口 500。自检要跑通真实往返：

```dockerfile
# ⚠️ 校验必须在 COPY --from=builder /install /usr/local 之后
#    （之前 pyodbc 还在 /install 里，import 不到，会误判失败）
RUN python -c "import pyodbc; \
d=[x for x in pyodbc.drivers() if x]; \
print('registered ODBC drivers:', d); \
import sys; \
sys.exit(0) if any('SQL Server' in x for x in d) else (print('ERROR: no SQL Server ODBC driver registered'), sys.exit(1))" \
    && python -c "\
import bcrypt; \
from passlib.context import CryptContext; \
c = CryptContext(schemes=['bcrypt'], deprecated='auto'); \
h = c.hash('smoke-test'); \
assert c.verify('smoke-test', h), 'bcrypt roundtrip failed'; \
print('passlib+bcrypt roundtrip OK')"
```

这样依赖漂移或环境缺失会在 **build 阶段**失败，而不是部署完才暴露。

### Step 2 — 生成 docker-compose.yml

复制 [docker-compose.template.md](docker-compose.template.md) 中的代码块到项目根目录。

要点：

- 顶部写 `name: <项目名>` —— 否则 compose 默认拿**当前目录名**当项目名，部署目录一改名字就变。
- `build.target: runtime` 必写。
- `build.args.APT_MIRROR` 保留，方便内网离线时覆盖。
- `image` 用 `<服务名>:latest`（`<服务名>` 即 `services:` 下的 key）。
- `container_name` 用 `<服务名>`，与 `image` 同名便于 `docker logs <容器名>` 直接查。
- `env_file: [.env]` + `environment` 叠加，让改配置只需 `restart` 不必 rebuild。
- CPU 密集型应用（OpenCV/ONNX）**必须限制线程数**，否则会吃满宿主全部核心。
- `logging` 段设 `max-size` / `max-file`，否则日志轮转后查不到历史。

### Step 2.5 — 网络规划（多项目共用基础设施时）

**先读 [network-topology.md](network-topology.md)**，确认双层网络设计。

需要基础设施 compose 时，复制 [infra-compose.template.md](infra-compose.template.md) 到**独立目录**（与业务项目平级，如 `_shared/`），项目名与网络名按模板顶部占位符替换。

业务项目 compose 里接入：

```yaml
    networks:
      - default        # 本项目私有网络
      - shared         # 共享基础设施网络

networks:
  shared:
    external: true
    name: <共享网络名>
```

要点：

- `external: true` 表示「已存在，别创建」—— **基础设施必须先启动**，否则报 `network ... declared as external, but could not be found`。
- 业务代码连基础设施用**服务名**（`redis:6379`），不要写 IP。
- 多项目共用 Redis 靠 **`REDIS_DB` 逻辑库 + key 前缀**双重隔离；PostgreSQL 靠 **每项目一个 database + role**；MinIO 靠 **每项目一个 service account**。
- service 级别的 `networks` 在 compose 合并时是**覆盖**而非追加 —— dev 覆盖文件若写了 `networks`，必须把两个网络写全。

### Step 2.6 — 处理跨平台差异项（Windows 开发 → Linux 部署）

**如果项目用了 SQL Server / pyodbc，这一步不能跳过。** 详见 [cross-platform-traps.md](cross-platform-traps.md)。

核心规则：**单一数据源**。

| 做法 | 是否推荐 |
|---|---|
| `.env` 写一份连接串（不含 `driver`），驱动名单独配置，代码运行时套用 | ✅ **推荐** |
| `.env` 写两份连接串（`DATABASE_URL` + `DATABASE_URL_DOCKER`），compose 用 `${...}` 插值切换 | ❌ 变量缺失时插值成空串，且要手工同步 |
| compose 里直接写死完整连接串 | ⚠️ 值确定时可以，但密码会进版本库 |

`.env`（连接串**不带** driver）：

```bash
DATABASE_URL=mssql+pyodbc://user:pass@host:1433/DB?charset=GBK&autocommit=true
DB_ODBC_DRIVER=ODBC Driver 17 for SQL Server   # Windows 本地
DB_ODBC_TRUST_SERVER_CERT=true
```

`docker-compose.yml`（**字面量**，不用插值）：

```yaml
    environment:
      DB_ODBC_DRIVER: "ODBC Driver 18 for SQL Server"   # Linux 官方包只有 18
      DB_ODBC_TRUST_SERVER_CERT: "true"
```

代码里用 `model_validator` 在运行时套用驱动名，并且**自动探测本机实际注册的驱动**（配置与实际不符时以实际为准），这样 `.env` 即使没同步也不会挂。

### Step 3 — 生成 docker-compose.dev.yml

复制 [docker-compose.dev.template.md](docker-compose.dev.template.md) 中的代码块到项目根目录。

要点：

- `image: <服务名>:dev`（独立 tag）
- `build.target: dev`
- **不写** `container_name`、**不写** `ports` —— 与生产保持一致，端口反代才能复用；代价是 dev/prod 不能同时跑。
- 代码用 **bind mount 逐目录**挂载，不整个挂 `.`（避免 `__pycache__`、`.venv`、数据目录污染）。

### Step 4 — 验证

```bash
# 合并后的配置是否正确（重点看 image / target / ports / container_name）
docker compose config
docker compose -f docker-compose.yml -f docker-compose.dev.yml config
```

### Step 5 — 构建与启动

**启动顺序（用了共享基础设施时不可颠倒）**：

```bash
# ① 先起基础设施（创建共享网络）
cd /www/wwwroot/_shared && docker compose up -d

# ② 再起业务项目
cd <项目目录> && docker compose up -d --build
```

**生产**

```bash
cd <项目目录>
docker compose up -d --build
docker compose logs -f <服务名>
```

**开发**

```bash
cd <项目目录>
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f <服务名>
```

---

## 切换流程（dev ⇄ prod）

容器名和端口两者相同，**不能同时跑**。切换必须先 `down`：

```bash
# prod → dev
docker compose down
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build

# dev → prod
docker compose -f docker-compose.yml -f docker-compose.dev.yml down
docker compose up -d --build
```

`docker compose down` 只删容器和 compose 创建的网络，**不删镜像、不删命名卷**。bind mount 的数据目录更不受影响。

---

## 国内源速查

| 用途 | 默认值（阿里云） | 备选 |
|---|---|---|
| PyPI | `https://mirrors.aliyun.com/pypi/simple/` | `https://pypi.tuna.tsinghua.edu.cn/simple` / `https://mirrors.cloud.tencent.com/pypi/simple` / `https://repo.huaweicloud.com/repository/pypi/simple` |
| APT (Debian/Ubuntu) | `mirrors.aliyun.com` | `mirrors.tuna.tsinghua.edu.cn` / `mirrors.ustc.edu.cn` / `mirrors.huaweicloud.com` |
| Docker Hub | `https://<id>.mirror.aliyuncs.com` | `https://docker.m.daocloud.io` / `https://dockerproxy.com` |
| npm | `https://registry.npmmirror.com` | `https://mirrors.cloud.tencent.com/npm/` |

**换 APT 源的关键细节**：Debian 12+ 用 **deb822** 格式，路径是 `/etc/apt/sources.list.d/debian.sources`；老版本用 `/etc/apt/sources.list`。改错文件会导致源没换成功。

```bash
# Debian 12+ (bookworm) / Ubuntu 24.04
sed -i "s|deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources
# Ubuntu 22.04 及以前 / Debian 11 及以前
sed -i "s|deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list
```

---

## 常见坑速查

| 现象 | 原因 | 解法 |
|---|---|---|
| **构建卡在 `ReadTimeoutError`** | pip 走官方源太慢 | 加 `PIP_INDEX_URL` 指向国内镜像 |
| **`IM002: Data source name not found`** | 连接串**缺 `driver=`**（≠ 驱动没装！） | 补 driver 参数；Linux 只有 Driver 18；见 [cross-platform-traps.md](cross-platform-traps.md) |
| **`Could not parse SQLAlchemy URL from string ''`** | compose `${...}` 插值成空串，覆盖了 env_file | 别用插值；用字面量或 `${VAR:?}`；见 [cross-platform-traps.md](cross-platform-traps.md) |
| **登录接口 500 `password cannot be longer than 72 bytes`** | passlib 1.7.4 与 bcrypt≥4.1 不兼容 | 钉 `bcrypt>=4.0.1,<4.1`，别写 `passlib[bcrypt]`；见 [cross-platform-traps.md](cross-platform-traps.md) |
| **本地正常、服务器报同一个错** | 改动只同步了部分文件 | 逐个核对关键文件内容，别只看文件是否存在 |
| `ImportError: libGL.so.1` | 装了非 headless 版 OpenCV | 删 `cv2/` 后 `--no-deps --force-reinstall opencv-python-headless` |
| `Permission denied: '/app/.local'` | dev 继承了 `USER app` 却要写 `/usr/local` | dev stage 显式 `USER root` |
| 生产跑起 `--reload` | Dockerfile 最后 stage 是 dev，compose 没写 `target` | compose 写 `target: runtime` |
| 生产用了 dev 镜像 | dev 与 prod 共用 image tag | dev 用独立 tag（`:dev`） |
| 改一行代码要等几分钟重建 | 依赖层被连带重跑 | 依赖合并成一条 `RUN`；dev 用 bind mount |
| 宿主机器瞬间变卡 | OpenCV/ONNX 吃满全部核心 | 限制 `OMP_NUM_THREADS` 等 |
| 容器起不来，日志无输出 | 进程秒退 | `docker compose logs --tail=100 <服务名>` 看 stderr |
| `network ... declared as external, but could not be found` | 共享网络还没创建 | 先启动基础设施的 compose |
| 容器连不上 redis/minio | 用了 IP 而非服务名，或没加入共享网络 | `docker inspect <容器> --format '{{.NetworkSettings.Networks}}'` 确认 |
| DNS 解析到别的项目 | 所有容器塞进了同一个网络 | 拆成「私有 + 共享」双层网络 |
| 共享网络里服务名冲突 | 两个项目都叫 `backend` | 共享层服务名加前缀，业务服务留在私有网络 |
| 基础设施数据全丢 | 跑了 `docker compose down -v` | 卷被删了，只能从备份恢复；平时只用 `down` |

---

## 日志查询

```bash
docker compose logs -f --timestamps <服务名>      # 实时跟随
docker compose logs --tail=200 <服务名>          # 最近 200 行
docker logs --since 1h <容器名>                  # 最近 1 小时
docker logs --since "2026-10-29T09:00:00" <容器名>
docker compose logs <服务名> > /tmp/app.log 2>&1  # 导出离线分析
```

---

## 模板与参考

- [Dockerfile.template.md](Dockerfile.template.md) — 多阶段构建，含国内源、OpenCV 修复、非 root、健康检查
- [docker-compose.template.md](docker-compose.template.md) — 生产编排
- [docker-compose.dev.template.md](docker-compose.dev.template.md) — 开发覆盖
- [infra-compose.template.md](infra-compose.template.md) — 共享基础设施（Redis / MinIO / PostgreSQL）
- [network-topology.md](network-topology.md) — 双层网络设计依据（**架构决策文档**）
- [cross-platform-traps.md](cross-platform-traps.md) — **Windows→Linux 跨平台陷阱**（ODBC 驱动名 / bcrypt 版本 / compose 插值空串 / 部署同步检查）
- [reference.md](reference.md) — 占位符替换清单、镜像瘦身、离线构建、更多排错
