# 跨平台陷阱速查（Windows 开发 → Linux 容器部署）

本文记录**在 Windows 上开发、在 Linux 容器里部署**时最容易踩、且报错信息最具误导性的几个坑。

每一节都包含：**症状 → 真实根因 → 修复**，并附可直接复制的代码。

---

## 一、ODBC 驱动名是连接串的一部分，跨平台不通用

### 症状

```
pyodbc.InterfaceError: ('IM002', '[IM002] [unixODBC][Driver Manager]
Data source name not found and no default driver specified (0) (SQLDriverConnect)')
```

### 真实根因

**这个报错极具误导性**。它字面意思是"数据源名找不到"，但绝大多数情况**不是驱动没装**，而是：

> **连接串里缺 `driver=` 参数**，unixODBC 不知道该用哪个驱动，于是报"找不到数据源"。

驱动名的平台差异：

| 平台 | 驱动名 | 说明 |
|---|---|---|
| Windows | `ODBC Driver 17 for SQL Server` | 微软官方 Windows 安装包 |
| Windows | `ODBC Driver 18 for SQL Server` | 新版，也支持 TLS 1.2+ |
| **Linux（官方包）** | **只有 `ODBC Driver 18 for SQL Server`** | Driver 17 **没有** Linux 版 |

所以：Windows 上能跑的连接串，**原样搬到 Linux 容器必然 IM002**。

还有一个坑：**Driver 18 默认开启 TLS 加密**，内网自签证书会连接失败，必须显式 `TrustServerCertificate=yes`。而这个参数 Driver 17 不认，传给它反而会失败。

### 验证方法（一眼定位）

```bash
# 容器里实际注册了哪些驱动
docker exec <容器名> python -c "import pyodbc; print(pyodbc.drivers())"
```

如果输出里有 `ODBC Driver 18 for SQL Server`，说明**驱动装好了**，问题一定在连接串。

### 修复：单一数据源 + 驱动名单独配置

**❌ 反模式：用两份连接串区分平台**

```yaml
# ❌ 危险！${...} 是 compose 插值，变量不存在时解析成空串，
#    而 environment 段优先级高于 env_file，会把正确值覆盖成空
DATABASE_URL: "${DATABASE_URL_DOCKER}"
```

这个写法有两个致命问题：

1. **目标机器的 `.env` 里如果没有该变量 → 插值成空串 → 连接串被清空**
   报错：`Could not parse SQLAlchemy URL from string ''`
2. 两份连接串要手工同步，改了一边忘了另一边 → 又是 IM002

**✅ 正确做法：连接串只有一份，驱动名独立配置，代码运行时套用**

`.env`（连接串**不带** driver）：

```bash
# 连接串主体，不含 driver（driver 是 ODBC 的一部分，跨平台不通用）
DATABASE_URL=mssql+pyodbc://user:pass@host:1433/DB?charset=GBK&autocommit=true

# 驱动名单独配置，各环境各填各的
DB_ODBC_DRIVER=ODBC Driver 17 for SQL Server
DB_ODBC_TRUST_SERVER_CERT=true
```

`docker-compose.yml`（**用字面量，不要用插值**）：

```yaml
    environment:
      # ⚠️ 必须用字面量。插值变量在目标机器的 .env 里不存在时会变成空串，
      #    且 environment 优先级高于 env_file → 正确值被空串覆盖
      DB_ODBC_DRIVER: "ODBC Driver 18 for SQL Server"
      DB_ODBC_TRUST_SERVER_CERT: "true"
```

`app/core/config.py`（运行时套用 + **自动探测**）：

```python
from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit, urlunsplit
from pydantic import model_validator


def _installed_odbc_drivers() -> list[str]:
    """列出本机 unixODBC 实际注册的驱动名。

    为什么要探测：Windows 装 Driver 17，Linux 只有 Driver 18。
    写死的驱动名在另一个平台上必然 IM002。
    """
    try:
        import pyodbc
        return [d for d in pyodbc.drivers() if d]
    except Exception:
        return []


def _pick_sqlserver_driver(installed: list[str]) -> str | None:
    """从已注册驱动里挑 SQL Server 驱动，优先版本新的。"""
    candidates = [d for d in installed if "SQL Server" in d]
    if not candidates:
        return None

    def version_of(name: str) -> int:
        for p in name.split():
            if p.isdigit():
                return int(p)
        return 0

    candidates.sort(key=lambda d: (-version_of(d), d))
    return candidates[0]


class Settings(BaseSettings):
    DATABASE_URL: str = ""
    DB_ODBC_DRIVER: str = ""
    DB_ODBC_TRUST_SERVER_CERT: bool = True

    @model_validator(mode="after")
    def _apply_odbc_driver(self):
        url = (self.DATABASE_URL or "").strip()
        if not url:
            raise ValueError(
                "DATABASE_URL 为空。\n"
                "  · 检查 .env 是否存在且包含 DATABASE_URL=...；\n"
                "  · 检查 compose 的 environment 段是否用 ${...} 插值覆盖了 DATABASE_URL。"
            )
        if not url.startswith("mssql+pyodbc"):
            return self

        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))

        installed = _installed_odbc_drivers()
        detected = _pick_sqlserver_driver(installed)
        configured = (self.DB_ODBC_DRIVER or "").strip()
        current = (query.get("driver") or "").strip()

        if installed:
            if configured and configured in installed:
                chosen = configured
            elif current and current in installed:
                chosen = current
            elif detected:
                chosen = detected
            else:
                chosen = current or configured
        else:
            chosen = configured or current

        if chosen:
            query["driver"] = chosen

        # TrustServerCertificate 只对 Driver 18 有意义，Driver 17 传了会失败
        if "18" in query.get("driver", ""):
            query["TrustServerCertificate"] = (
                "yes" if self.DB_ODBC_TRUST_SERVER_CERT else "no"
            )
        else:
            query.pop("TrustServerCertificate", None)

        self.DATABASE_URL = urlunsplit((
            parts.scheme, parts.netloc, parts.path,
            urlencode(query, quote_via=quote_plus), parts.fragment,
        ))
        return self
```

**好处**：连接串只有一份，永远不会不同步；驱动名自动适配所在平台；`.env` 保持不变也能跑。

### 排查用诊断日志

启动时打印驱动列表和脱敏连接串，问题一眼可见：

```python
import re

def log_runtime_diagnostics(settings):
    try:
        import pyodbc
        drivers = [d for d in pyodbc.drivers() if d]
    except Exception as exc:
        drivers = []
        log.warning("读取 ODBC 驱动列表失败: %s", exc)

    log.info("已注册的 ODBC 驱动: %s", drivers or "(无)")
    if settings.DATABASE_URL.startswith("mssql+pyodbc"):
        masked = re.sub(r"://([^:]+):[^@]*@", r"://\1:***@", settings.DATABASE_URL)
        log.info("数据库连接串: %s", masked)
        if not drivers:
            log.error("容器内没有任何 ODBC 驱动 —— 镜像构建时驱动没装成功。")
```

### Dockerfile 里加构建期校验

**驱动没注册上就让 build 失败**，别拖到运行时才发现。用 `pyodbc.drivers()` 而不是 `odbcinst` 作判据（前者才是应用实际用的）。

⚠️ **校验必须放在 `COPY --from=builder /install /usr/local` 之后** —— 之前 pyodbc 还在 `/install` 里，`import` 不到，会误判失败。

```dockerfile
RUN python -c "import pyodbc; \
print('runtime ok | pyodbc', pyodbc.version); \
d=[x for x in pyodbc.drivers() if x]; \
print('registered ODBC drivers:', d); \
import sys; \
sys.exit(0) if any('SQL Server' in x for x in d) else (print('ERROR: no SQL Server ODBC driver registered'), sys.exit(1))"
```

---

## 二、passlib + bcrypt 版本冲突（登录接口 500）

### 症状

```
ValueError: password cannot be longer than 72 bytes, truncate manually if necessary (e.g. my_password[:72])
  File "passlib/handlers/bcrypt.py", line 655, in _calc_checksum
    hash = _bcrypt.hashpw(secret, config)
```

登录接口返回 **500 Internal Server Error**（不是 401），看起来像服务器坏了。

### 真实根因

**passlib 1.7.4 与 bcrypt >= 4.1 不兼容。**

机理：

1. passlib 加载 bcrypt 后端时会跑一次**自检**，自检里用了 **255 字节**的测试口令
2. bcrypt **4.x** 对超过 72 字节的口令**静默截断** → 自检通过 ✅
3. bcrypt **>= 4.1**（现在解析到 5.0.0）改成**直接抛异常** → 自检失败 ❌

实测（给 `bcrypt.hashpw` 打 spy 就能看到）：

```
hashpw called with password type= bytes len= 255 value= b'0123456789...'
ValueError: password cannot be longer than 72 bytes
```

**触发条件**：`requirements.txt` 里写 `passlib[bcrypt]==1.7.4` —— 方括号会让 pip 顺带装**最新**的 bcrypt（5.x），直接踩坑。

### 修复

**❌ 反模式**

```bash
passlib[bcrypt]==1.7.4     # ← 会顺带装 bcrypt 5.x，必踩坑
```

**✅ 正确做法：分开写并钉住版本**

```bash
passlib==1.7.4
bcrypt>=4.0.1,<4.1
```

### Dockerfile 里加构建期校验

```dockerfile
RUN python -c "\
import bcrypt; \
from passlib.context import CryptContext; \
print('bcrypt:', bcrypt.__version__); \
c = CryptContext(schemes=['bcrypt'], deprecated='auto'); \
h = c.hash('smoke-test'); \
assert c.verify('smoke-test', h), 'bcrypt roundtrip failed'; \
print('passlib+bcrypt roundtrip OK')"
```

> 注：日志里可能出现 `(trapped) error reading bcrypt version` 警告，**无害** —— passlib 只是读不到 `bcrypt.__about__`，不影响加解密。

### 长期方案

passlib 1.7.4 已停止维护（最后发布 2020 年）。可选：

- 升级到 `pwdlib`（passlib 的活跃分支，兼容新 bcrypt）
- 或绕开 passlib，直接用 `bcrypt` 库

但**短期最稳的就是钉 `bcrypt<4.1`**。

---

## 三、compose 插值把环境变量变成空串

### 症状

```
sqlalchemy.exc.ArgumentError: Could not parse SQLAlchemy URL from string ''
```

连接串**变成空字符串**，而不是连不上。

### 真实根因

两条 compose 规则叠加：

1. `environment:` 段的优先级**高于** `env_file:`
2. `${VAR}` 是 compose **插值语法**，从**项目目录的 `.env`** 取值；变量不存在时**解析成空串**

所以这一行：

```yaml
environment:
  DATABASE_URL: "${DATABASE_URL_DOCKER}"   # 目标机器 .env 里没这个变量
```

会把 `.env` 里**本来正确**的 `DATABASE_URL` **覆盖成空串**。

### 规则

| 写法 | 语义 | 风险 |
|---|---|---|
| `KEY: "${VAR}"` | 插值，缺失时变空串 | ⚠️ 会覆盖 env_file |
| `KEY: "${VAR:?错误信息}"` | 缺失时**构建直接失败** | ✅ 推荐用于必填项 |
| `KEY: "${VAR:-默认值}"` | 缺失时用默认值 | ✅ 安全 |
| `KEY: 字面量` | 硬编码 | ✅ 最安全（值确定时首选） |

**凡是确定的值，就写字面量**，别用插值绕一圈。

### 防御性写法

代码里对空值显式报错，比让 SQLAlchemy 抛天书友好得多：

```python
if not url:
    raise ValueError("DATABASE_URL 为空。请检查 .env 与 compose 的 environment 段。")
```

---

## 四、部署前的同步检查（避免"本地改了、服务器没改"）

### 教训

真实事故：`config.py` 的修复逻辑**只存在于本地**，`requirements.docker.txt` 和 `.env` 却传上了服务器。
结果：服务器上连接串缺 `driver=` → IM002，而本地怎么测都正常。

**只传部分文件 = 比完全不传更危险**，因为会让人误以为"已经同步过了"。

### 上线前必须核对的文件清单

| 文件 | 改了哪些地方 |
|---|---|
| `app/core/config.py` | 连接串处理、驱动探测 |
| `app/main.py` | 启动流程、诊断日志 |
| `Dockerfile` | 构建期校验 |
| `requirements.docker.txt` | 依赖版本钉死 |
| `docker-compose.yml` | `environment` / `volumes` |
| `.env` | 连接串与密码（**注意别把 .env 打进镜像**） |

### 验证同步是否真的生效

```bash
# 1. 容器里的文件内容与本地一致？（关键！别只看文件存在）
docker exec <容器名> grep -c "_apply_odbc_driver" /app/app/core/config.py

# 2. 依赖版本与钉的一致？
docker exec <容器名> pip show bcrypt | grep Version

# 3. 驱动注册成功？
docker exec <容器名> python -c "import pyodbc; print(pyodbc.drivers())"

# 4. 环境变量真的传进去了吗？
docker exec <容器名> env | grep -E "DATABASE_URL|DB_ODBC"
```

### 更好的做法：让版本不匹配自己暴露

- **init git 并提交** —— 改动有记录，能 diff 出"服务器少了什么"
- Dockerfile 里加**构建期校验**（本文第一节、第二节）—— 依赖或环境不对时 build 就失败
- 启动时打印**诊断信息** —— 一眼看出驱动列表、连接串、依赖版本

---

## 五、SQLAlchemy 本身的小坑

### `SAWarning: No driver name specified`

```
SAWarning: No driver name specified; this is expected by PyODBC when using DSN-less connections
```

用了 DSN-less 连接（`mssql+pyodbc://user:pass@host/db`）时，**必须**在 query 里带 `driver=`。缺了就是 IM002。

### 密码里的特殊字符要 URL 编码

| 字符 | 编码 |
|---|---|
| `@` | `%40` |
| `/` | `%2F` |
| `:` | `%3A` |
| `#` | `%23` |

例：`DB_PASS=Qdndd@102505` → URL 里写 `Qdndd%40102505`。

### `autocommit` 会被抽走

`?autocommit=true` 不会出现在 ODBC 连接串里，而是被 SQLAlchemy 提取成 pyodbc 的 `autocommit` 参数 —— 这是正常行为。

### 校验生成结果

```python
from sqlalchemy.dialects.mssql.pyodbc import MSDialect_pyodbc
from sqlalchemy.engine import make_url

print(MSDialect_pyodbc().create_connect_args(make_url(url))[0][0])
```

输出就是真正交给 unixODBC 的字符串 —— **ODBC 串里必须能看到 `DRIVER={...}`**。
