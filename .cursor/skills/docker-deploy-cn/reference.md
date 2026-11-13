# 参考文档

## 占位符总表

三个模板共用一套占位符。生成文件后**逐一全局替换**：

| 占位符 | 出现位置 | 说明 |
|---|---|---|
| `<项目名>` | compose `name:`、镜像名前缀 | 决定 compose 资源名前缀（网络、容器） |
| `<服务名>` | compose `services:` 的 key、`image:`、`container_name:` | **dev 文件里必须完全一致** |
| `<项目描述>` | Dockerfile `LABEL` | OCI 描述 |
| `<APP_PORT>` | Dockerfile `EXPOSE`/`CMD`/healthcheck、compose `ports`/`environment` | 应用监听端口，须与反代一致 |
| `<APP_MODULE>` | Dockerfile `CMD` | FastAPI 入口模块名 |
| `<APP_OBJECT>` | Dockerfile `CMD` | FastAPI 实例变量名 |
| `<相对目录>` | compose `volumes` | 需持久化/挂载的宿主机目录 |

替换命令（Linux，PowerShell 用 `Get-ChildItem -Recurse -File | ForEach-Object { ... }`）：

```bash
grep -rl '<APP_PORT>' . | xargs sed -i 's/<APP_PORT>/3081/g'
```

---

## 镜像瘦身

多阶段构建已经省掉了编译链，但还能进一步：

| 手段 | 做法 | 效果 |
|---|---|---|
| 清理 apt 缓存 | `rm -rf /var/lib/apt/lists/*` | 约 30-50MB |
| `PIP_NO_CACHE_DIR=1` | ENV 里设置 | 约 100-500MB（取决于包数） |
| `--no-compile` | `pip install --no-compile` | 省 .pyc，但**牺牲启动速度**，生产不建议 |
| `PYTHONDONTWRITEBYTECODE=1` | ENV 里设置 | 运行时不写 .pyc |
| 多阶段隔离 | builder 装编译链，runtime 不装 | 约 500MB-1GB |

查看各层占用：

```bash
docker history <镜像名> --no-trunc --format "table {{.Size}}\t{{.CreatedBy}}"
```

---

## 离线 / 内网构建

内网无法访问公网时：

**① pip 换内网源**

```bash
docker compose build --build-arg PIP_INDEX_URL=http://pypi.internal/simple
```

**② apt 换内网源**

```bash
docker compose build --build-arg APT_MIRROR=mirrors.internal
```

**③ 完全离线**：在有网机器上构建并导出：

```bash
docker build -t myapp:latest .
docker save myapp:latest -o myapp.tar
# 传到内网机器
docker load -i myapp.tar
docker compose up -d
```

**注意**：`docker save/load` 保留镜像 tag，但 `docker compose up -d --build` 会触发重建 —— 离线环境用 `docker compose up -d`（不带 `--build`）。

---

## Docker Hub 加速（拉基础镜像慢时）

```bash
# /etc/docker/daemon.json
{
  "registry-mirrors": [
    "https://<你的ID>.mirror.aliyuncs.com",
    "https://docker.m.daocloud.io"
  ]
}
```

```bash
systemctl daemon-reload && systemctl restart docker
```

⚠️ 加速源不稳定时，镜像拉取可能间歇性失败 —— 配合 `restart: unless-stopped` 使用，并保留回退到官方源的配置。

---

## compose 合并机制

`docker compose -f a.yml -f b.yml` 的合并规则：

| 字段 | 合并方式 |
|---|---|
| `image` | **后者覆盖前者**（标量） |
| `build.target` | **后者覆盖前者**（标量） |
| `build.args` | **按 key 合并** |
| `ports` / `volumes` / `environment` | **追加**（列表） |
| `container_name` | 后者覆盖前者 |
| `networks`（service 级） | **后者覆盖前者**（⚠️ 不是追加） |

**关键推论**：
- dev 文件里的 `image:` 和 `build.target:` 会**覆盖** base —— 这正是利用点
- dev 文件里**不要**写 `ports` / `volumes` 之外的无关项，否则会和 base 叠加
- dev 文件里**不要**写 `container_name` / `ports`，它们会自动继承 base
- ⚠️ **service 级 `networks` 是覆盖语义**：dev 文件一旦写了 `networks:`，就是**完整替换** base 的列表。
  如果 dev 需要共享网络，dev 文件必须把 `default` 和 `shared` **两个都写全**，
  否则 dev 容器会丢失共享网络成员资格 → 连不上 Redis/MinIO。
  若 dev 文件**完全不写** `networks:`，则整体继承 base（含 `shared`）。
- 顶层 `networks:`（网络定义）同样是覆盖：dev 文件若声明了顶层 `networks:`，base 的定义会被替换。

验证合并结果：

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml config
```

**必查项**：`image`、`build.target`、`ports`、`container_name`、`networks`。

---

## 日志与持久化

### 日志查询

```bash
docker compose logs -f --timestamps <服务名>      # 实时跟随
docker compose logs --tail=200 <服务名>          # 最近 200 行
docker logs --since 1h <容器名>                  # 最近 1 小时
docker logs --since "2026-10-29T09:00:00" <容器名>
docker logs --until 30m <容器名>
docker compose logs <服务名> > /tmp/app.log 2>&1  # 导出离线分析
```

### 双通道日志

FastAPI 应用常有两套日志出口：

| 通道 | 配置方式 | 位置 |
|---|---|---|
| stdout | `logging.StreamHandler(sys.stdout)` | `docker compose logs` |
| 文件 | `logging.FileHandler(settings.LOG_DIR / "app.log")` | 宿主机 `./logs/app.log`（需 bind mount） |

**stdout 通道**受 Docker 轮转限制（`max-size` × `max-file`），会丢历史。
**文件通道**只要 bind mount 了就不受轮转影响，且跨容器重建仍在。

建议生产两者都开：stdout 供实时查看，文件供历史追溯。

---

## 常见排错详解

### `docker compose up` 报端口占用

```
Bind for 0.0.0.0:3081 failed: port is already allocated
```

```bash
# 查是谁占的
docker ps --filter publish=3081
ss -lntp | grep 3081
```

### 容器起不来，日志为空

```bash
docker compose ps -a           # 看状态和退出码
docker compose logs --tail=100 <服务名>
docker inspect <容器名> --format '{{.State.ExitCode}} {{.State.Error}}'
```

### 修改 env 后不生效

`environment` 变化需要**重建容器**，`restart` 不够：

```bash
docker compose up -d --force-recreate
```

### 改了代码但生产没更新

生产镜像把代码烘进去了，必须 rebuild：

```bash
docker compose up -d --build
```

### build 缓存没命中导致反复全量重建

```bash
docker compose build --no-cache
docker builder prune -f          # 清理构建缓存
```

### SQLite 在 bind mount 上报 locked

WAL 模式对文件锁有要求，bind mount 到不同文件系统（尤其 Windows/macOS）会失效。生产应把数据库放在容器内卷或宿主机原生 Linux 路径上。

### 连接串相关（跨平台 / compose 插值）

**详细说明见 [cross-platform-traps.md](cross-platform-traps.md)**，这里只列速查：

| 报错 | 真实原因 |
|---|---|
| `Could not parse SQLAlchemy URL from string ''` | compose `${...}` 插值成空串，覆盖了 `env_file` 的正确值 |
| `IM002: Data source name not found` | 连接串缺 `driver=` 参数（**不是**驱动没装） |
| `SAWarning: No driver name specified` | 同上，DSN-less 连接必须带 `driver=` |

快速判断驱动是否真的装了：

```bash
docker exec <容器名> python -c "import pyodbc; print(pyodbc.drivers())"
```

### 登录接口 500（passlib / bcrypt）

```
ValueError: password cannot be longer than 72 bytes, truncate manually if necessary
```

passlib 1.7.4 与 bcrypt ≥ 4.1 不兼容。解法：`bcrypt>=4.0.1,<4.1`，且**不要**写 `passlib[bcrypt]`。

### 应用导入即崩（容器一直 Up 但服务不可用）

容器状态 `Up (healthy)` 不代表应用正常 —— 常见于 **import 阶段就抛异常**：

```
[7] [ERROR] Exception in worker process
  File "/app/app/core/db.py", line 11, in <module>
    engine = create_engine(settings.DATABASE_URL)
[1] [ERROR] Reason: Worker failed to boot.
```

gunicorn master 会反复拉起 worker、每次都崩。排查：

```bash
docker compose logs --tail=100 <服务名> | grep -A15 "Exception in worker"
```

---

## 迁移到新项目时的检查清单

### 跨平台 / 依赖一致性检查（Windows 开发 → Linux 部署）

- [ ] `.env` 里**只有一份** `DATABASE_URL`，且**不含 `driver=` 参数**
- [ ] 驱动名单独配置（如 `DB_ODBC_DRIVER`），compose 里用**字面量**而非 `${...}` 插值
- [ ] 代码里有 `model_validator` 在运行时套用驱动名，且会**自动探测**本机实际注册的驱动
- [ ] 连接串为空时**显式报错**，而不是让 SQLAlchemy 抛 `Could not parse SQLAlchemy URL from string ''`
- [ ] `requirements.docker.txt` 里 **passlib 与 bcrypt 分开写**，bcrypt 钉 `<4.1`
- [ ] Dockerfile 里有 **ODBC 驱动校验**（build 阶段失败，而非运行时）
- [ ] Dockerfile 里有 **passlib+bcrypt 往返自检**（不只是 import）
- [ ] 启动日志会打印**已注册驱动列表 + 脱敏连接串**

### 部署同步检查（避免"本地改了、服务器没改"）

只传部分文件比完全不传更危险 —— 会让人误以为"已经同步过了"。

| 文件 | 常改内容 |
|---|---|
| `app/core/config.py` | 连接串处理、驱动探测 |
| `app/main.py` | 启动流程、诊断日志 |
| `Dockerfile` | 构建期校验 |
| `requirements.docker.txt` | 依赖版本钉死 |
| `docker-compose.yml` | `environment` / `volumes` |
| `.env` | 连接串与密码（**别打进镜像**） |

上传后**逐个核对内容**（不是只看文件存在）：

```bash
docker exec <容器名> grep -c "_apply_odbc_driver" /app/app/core/config.py
docker exec <容器名> pip show bcrypt | grep Version
docker exec <容器名> python -c "import pyodbc; print(pyodbc.drivers())"
docker exec <容器名> env | grep -E "DATABASE_URL|DB_ODBC"
```

**更好的做法**：init git 并提交，改动有记录能 diff 出"服务器少了什么"。

- [ ] `Dockerfile` 三个占位符已替换（`<APP_PORT>` / `<APP_MODULE>` / `<APP_OBJECT>`）
- [ ] `requirements.docker.txt` 依赖文件名正确
- [ ] 不需要的段落已删除（MS SQL 驱动 / OpenCV / 中文字体 / 外部网络）
- [ ] `docker-compose.yml` 的 `name:` 已设为项目名（不要留默认值）
- [ ] `build.target: runtime` 已写
- [ ] `image` / `container_name` 已改成本项目名
- [ ] 端口与反向代理配置一致
- [ ] `docker-compose.dev.yml` 的服务 key 与 base **完全一致**
- [ ] `docker-compose.dev.yml` 的 `image` 是 `:dev`，`build.target` 是 `dev`
- [ ] `docker-compose.dev.yml` 未写 `container_name` / `ports`
- [ ] 代码目录挂载路径逐个列出，未整个挂 `.`
- [ ] `docker compose config` 与合并后的 `config` 均通过
- [ ] `docker compose build` 成功
- [ ] `docker compose up -d` 后 `curl http://127.0.0.1:<APP_PORT>/health` 返回正常

### 共享基础设施相关（多项目共用时）

- [ ] 基础设施 compose 放在**独立目录**（与业务项目平级），不在任何业务项目内部
- [ ] 基础设施 compose 顶部有 `name: <共享项目名>`
- [ ] 基础设施 compose 顶层 `networks.default.name` **显式命名**（业务项目要引用它）
- [ ] Redis 配了 `--requirepass` + `appendonly yes` + named volume 三件套
- [ ] Redis/MinIO/PostgreSQL 都用 **named volume**，不是 bind mount
- [ ] PostgreSQL 的 `POSTGRES_PASSWORD` 用 `${VAR:?}` 强制必填（不设默认值，避免误用弱密码）
- [ ] 业务项目 compose 有 `networks: [default, shared]` + 顶层 `external: true` 定义
- [ ] 业务代码用**服务名**（`redis`）而非 IP 连接基础设施
- [ ] 本项目的 `REDIS_DB` / PostgreSQL database / MinIO bucket 与其他项目**不重复**
- [ ] Redis key 前缀带项目标识（如 `zhpt:`）
- [ ] 启动顺序：先基础设施，后业务项目
- [ ] 已确认基础设施**不会**被 `docker compose down -v` 删除卷

### 网络检查命令

```bash
# 看容器实际加入了哪些网络
docker inspect <容器名> --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}'

# 看网络成员
docker network inspect shared_default --format '{{range .Containers}}{{.Name}} {{end}}'

# 验证服务名解析（在业务容器内）
docker exec <业务容器> getent hosts redis
docker exec <业务容器> redis-cli -h redis -a '<密码>' --no-auth-warning ping
```
