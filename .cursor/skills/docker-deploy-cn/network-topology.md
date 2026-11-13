# 网络拓扑设计：双层网络

> 多项目共用一套基础设施时的网络规划依据。**这是架构决策，不是配置细节** ——
> 每次新增项目、或有人建议"简化成一份 compose"时，回到本文档核对。

---

## 1. 拓扑总览

```
┌──────────────────────────────────────────────────────┐
│  基础设施层（全局唯一，所有项目共用）                  │
│  compose 项目名：shared                              │
│  网络：shared_default                                │
│                                                      │
│   shared-redis    shared-minio    shared-postgres   │
└───────────────┬──────────────────┬──────────────────┘
                │                  │
     ┌──────────┘                  └──────────┐
     │                                        │
┌────┴─────────────────────┐   ┌────────────┴───────────┐
│ 业务层（每项目一个，默认隔离）│   │ 业务层                  │
│ 网络：<项目名>_default      │   │ 网络：<项目名2>_default  │
│                            │   │                         │
│  ┌──────────────────────┐  │   │  ┌───────────────────┐  │
│  │ <项目名>-backend      │  │   │  │ <项目名2>-backend │  │
│  │ + default            │  │   │  │ + default         │  │
│  │ + shared             │  │   │  │ + shared          │  │
│  └──────────────────────┘  │   │  └───────────────────┘  │
└────────────────────────────┘   └─────────────────────────┘
```

**每个业务容器同时属于两个网络。**

---

## 2. 核心原则

> **「需要被共享的」放共享网络，「需要被隔离的」放私有网络。**

这正是 Kubernetes 的 `namespace` + `NetworkPolicy`（默认拒绝、显式放行）的等价物。

| 层 | 归属 | 成员 | 访问方式 |
|---|---|---|---|
| 共享网络 | 基础设施 compose | redis / minio / postgres | 业务容器用**服务名**（`redis:6379`） |
| 私有网络 | 各业务 compose | 本项目全部服务 | 内部互调用**服务名** |
| host 网络 | 反向代理 | nginx | 通过 `127.0.0.1:<端口>` 访问所有项目 |

---

## 3. 为什么不能全塞进一个网络

这是最容易被推翻的决策点，所以先说清楚代价：

| 问题 | 具体代价 |
|---|---|
| **DNS 污染** | 每个容器都能解析到所有容器的名字。项目一多，A 项目的容器能"看见"B 项目的容器，极易误连 |
| **隔离性丢失** | 业务容器之间互相可达。一个项目的配置写错，就能访问到别的项目的数据 |
| **服务名冲突** | 两个项目都有 `backend` 服务时，DNS 里 `backend` 到底指谁？必须用 `项目名-服务名` 这种全限定名，很丑且易错 |
| **无法网络级隔离** | 共享一个网络后，任何容器能访问任何端口，做不了端口级的进出限制 |
| **compose 归属** | 一个网络只能属于一个 compose 项目。跨项目共享必须显式声明 `external: true`，且引入启动顺序依赖 |

**反过来，共享层为什么该独立**：

- Redis / PostgreSQL / MinIO 天然是「多租户单实例」，属于共享层
- 业务容器只该看到 `redis` / `minio` / `pgsql` 这几个服务名，**看不到别的项目的内部服务**
- **加新项目时不用改 infra** —— 业务项目加入 `shared_default` 即可

---

## 4. 跨项目共享的三个机制

### 4.1 `external: true` 的语义

业务项目 compose：

```yaml
services:
  <服务名>:
    networks:
      - default
      - shared

networks:
  shared:
    external: true
    name: shared_default
```

| 字段 | 作用 |
|---|---|
| `external: true` | **「这个网络已存在，不要由我创建」** |
| `name: shared_default` | 真正要引用的 Docker 网络名 |

**创建者与销毁者**：

| 操作 | 谁负责 |
|---|---|
| 创建 `shared_default` | 基础设施 compose（`docker compose up` 时） |
| 销毁 `shared_default` | 基础设施 compose（`docker compose down` 时） |
| 业务项目 `down` | **不会**删掉 `external` 网络 ✅ |

**启动顺序是硬约束**：

```bash
# ① 先起基础设施（创建 shared_default）
cd /www/wwwroot/_shared && docker compose up -d

# ② 再起业务项目
cd /www/wwwroot/<项目>/backend && docker compose up -d --build
```

顺序反了会报：

```
network shared_default declared as external, but could not be found
```

### 4.2 服务名必须全局唯一（同一网络内）

Docker 的内嵌 DNS 在**每个网络内是独立作用域**。两个容器在同一个网络里时：

- 服务名 `backend` 在 `shared_default` 里只能有**一个**
- 业务项目的 `backend` 在自己的 `<项目名>_default` 里，与共享网络无关 ✅

**所以规则是**：往共享网络里加的服务，服务名要带项目/用途前缀（`redis`、`minio`、`pgsql` 都符合）。不要往共享网络里塞业务服务。

**DNS 解析的是「服务名」，不是 `container_name`**：

```yaml
services:
  redis:
    container_name: shared-redis    # 容器名
#     ↑ 服务名是 redis
```

业务代码连 `redis:6379` → 解析到 `shared-redis` 容器 ✅ 正确。

### 4.3 同一容器加入两个网络

一个服务可以加入多个网络：

```yaml
    networks:
      - default        # 自己的私有域
      - shared         # 共享域
```

容器会拿到**两个 IP**（`eth0`、`eth1`），且在**两个域里都能做 DNS 解析**：

| 域里能解析到 | 在哪个网络 |
|---|---|
| `redis` / `minio` / `pgsql` | `shared` |
| 本项目其他服务名 | `default` |

**注意**：service 级别的 `networks` 在 compose 合并时是**覆盖**而非追加。所以 dev 覆盖文件如果写了 `networks`，就是**完整替换** base 的列表 —— dev 文件必须把两个都写全。

---

## 5. 反向代理（host 网络）的特例

大多数反向代理容器跑在 host 网络：

```yaml
    network_mode: host
```

**两个后果**：

1. **host 网络与 bridge 网络互斥** —— 不能既 `network_mode: host` 又写 `networks:`。host 模式的容器**看不到任何 bridge 网络的 DNS**。
2. nginx 解析**域名形式**的 upstream 时，用的是 `resolver` 指令指向的 DNS，**不是** Docker 内嵌 DNS（`127.0.0.11`）。

**因此反代必须通过宿主机端口访问业务容器**：

```nginx
upstream <项目名>_backend {
    server 127.0.0.1:<APP_PORT>;
}
```

**这反而简化了方案** —— nginx 天然通过宿主机端口访问所有项目，**不需要加入任何业务网络**。host 网络在这里不是缺陷，而是特性：**它就是那个跨所有项目的总线**。

> 如果确实想让 nginx 用容器名反代，需要同时满足三个条件：
> ① 放弃 host 网络改用 bridge ② `resolver` 改成 `127.0.0.11` ③ nginx 加入所有相关网络或业务侧发布端口。
> 三条全做到才能改，通常不值得。

---

## 6. 端口暴露策略

共享基础设施的端口暴露有三种模式，按场景选：

| 模式 | 配置 | 适用 |
|---|---|---|
| **只走网络**（最安全） | 不写 `ports` | 业务容器与基础设施**同机**时 |
| 绑内网网卡 | `"172.16.x.x:6379:6379"` | 多机共用，机器有公网 IP 时必选 |
| 全网卡 | `"6379:6379"` | 默认，兼容性最好，但**公网机器要确认防火墙** |

⚠️ 绑内网网卡时，**IP 必须是本机真实存在的地址**，否则容器起不来：

```
bind: cannot assign requested address
```

先查：`ip -4 addr show | grep inet`

---

## 7. 决策速查

| 场景 | 做法 |
|---|---|
| 新增业务项目 | 加 `networks: [default, shared]`，给它新的 `REDIS_DB` / database / bucket |
| 业务需要连基础设施 | 用**服务名**（`redis`），不要写 IP |
| 基础设施服务名冲突 | 加前缀，或不要往共享网络加业务服务 |
| 反代访问业务 | 业务容器发布端口到宿主机，反代用 `127.0.0.1:<端口>` |
| 想让反代用容器名 | 见 §5 的三个前提，通常不值得 |
| 基础设施要下线 | 先停所有业务项目，再 `docker compose down`（**不要加 `-v`**） |

---

## 8. 明确禁止的做法

| ❌ 禁止 | 原因 |
|---|---|
| 业务项目在自己 compose 里再起一份 Redis/MinIO/PostgreSQL | 两份数据分叉，故障时无法判断哪份是权威 |
| 把所有容器塞进一个网络 | DNS 污染 + 服务名冲突 + 无法隔离（见 §3） |
| 业务项目 `down` 时删共享网络 | `external: true` 保护了它，但手写 `docker network rm` 会破坏其他项目 |
| `docker compose down -v` 跑在基础设施上 | **数据卷被删，数据全丢** |
| 在共享网络里放业务服务 | 污染共享域，且服务名易与其他项目冲突 |
| 密码用含 `@ : / # ?` 的字符 | Redis URI 分隔符，改用 URL 形式时会解析出错 |
