# 智慧平台（zhpt）基础设施手册

> 本文档是 `project_dev_spec_v1.2.md` 的**项目侧实参对照**。规范文档讲方法论（用占位符），本文档落具体值（桶名/账号/密钥位置/nginx 配置/命名约定）。
>
> **维护原则**：基础设施变更（换桶、轮换账号、改 nginx）后**必须同步更新本文档**，并在 §9 演进记录里追加一条。

---

## 1. 基础设施清单

| 资源 | 地址 / 标识 | 网段 / 备注 |
|---|---|---|
| 后端服务（开发） | `172.16.14.216:3050` | 开发机 Windows 10 |
| 后端服务（生产） | `<待补>` | 由运维填写 |
| MinIO 集群 | `172.16.100.102:9000`（API）/ `:9001`（控制台） | 内网，不直接对外暴露 |
| MinIO Region | `guizhou` | 桶元数据中携带 |
| Redis | `172.16.100.102:6379`，DB=0，密码见 `.env` | 与 MinIO 同主机 |
| SQLite | `backend/<dbfile>.db` 本地文件 | 单机部署阶段 |

> 实际机密值（AK/SK/密码）只放在各环境 `.env` 文件，**永远不要写进本手册**。本手册只标注"密钥放在哪个 env 变量"。

---

## 2. MinIO 桶清单

### 2.1 在用桶

| 桶名 | 用途 | 可见性 | 访问入口 | 状态 |
|---|---|---|---|---|
| `guizhou-zhpt-prod-private` | 业务私有数据：学生头像、招生简章扫描件、3+4 报名材料、就业推荐配图、招生上传图（`zs/*`）等 | 全私有 | 后端业务代理（带 HMAC 签名，5 分钟有效） | **当前生产桶**（2026-05-11 P3 cutover 完成） |
| `guizhou-zhpt-prod-public` | 公共静态资源：首页背景 `zbm.png`、默认头像、答题图标、品牌素材；目录约定 `static/<sub>/<name>` | 匿名 readonly | 生产经 nginx `/static/*` 直发（含 `secure_link`）；开发/兜底经 FastAPI `/static/*` 路由 | **当前生产桶** |
| `headphoto` | **遗留桶**——P3 之前所有业务数据所在的桶 | 全私有 | 已无在线读路径，仅留作迁移兜底快照 | **待删除**（计划稳定 30 天后由运维 `mc rb`） |

### 2.2 桶目录约定

**公共桶 `guizhou-zhpt-prod-public`**

```
static/
  images/          # 首页/通用插图（如 zbm.png）
  icons/           # 业务图标（如答题、报名等）
  brand/           # 校徽 / 品牌素材
```

**私有桶 `guizhou-zhpt-prod-private`**

```
<sfzh>.jpg                  # 学生头像（身份证号为文件名，根目录）
zs/<uuid>.<ext>             # 3+4 招生上传图
brochure/vocational/<n>.jpg # 中职招生简章（n 为有序数字）
brochure/open/<n>.jpg       # 开大招生简章
brochure/adult/<n>.jpg      # 成人高考招生简章
jytj/<timestamp>.jpg        # 就业推荐文章配图
```

> 命名规则与「§5 命名规范」一致：不出现中文、空格、大写；扩展名小写。

---

## 3. MinIO 账号

| 账号 | 类型 | 用途 | 持有方 | 密钥位置 |
|---|---|---|---|---|
| `flysky` | Root | 仅运维通过 `mc` 做迁移、建桶、policy 维护 | 运维 | 运维本地 `mc alias` |
| `ZXU2KINV0UJ2D9CTW65H` | Service Account | 应用读写两个生产桶 | 后端应用 | `backend/.env` 的 `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` |

### 3.1 Service Account IAM Policy

授权范围：仅 `guizhou-zhpt-prod-private` + `guizhou-zhpt-prod-public` 两个桶的对象读写 + 列举。**不**包含 `s3:CreateBucket / s3:DeleteBucket` 等管理动作。

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": [
        "arn:aws:s3:::guizhou-zhpt-prod-private/*",
        "arn:aws:s3:::guizhou-zhpt-prod-public/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::guizhou-zhpt-prod-private",
        "arn:aws:s3:::guizhou-zhpt-prod-public"
      ]
    }
  ]
}
```

### 3.2 密钥轮换流程

1. 运维 `mc admin user svcacct add zhpt flysky --name "zhpt-app-vN+1"` 生成新 AK/SK
2. 把新 AK/SK 写入 `.env`，**先注释保留旧的**
3. 重启后端，验证业务正常
4. 验证稳定 24h 后，`mc admin user svcacct rm zhpt <旧AK>` 销毁旧账号
5. 在本手册 §9 追加一条轮换记录

---

## 4. 访问路径与鉴权

### 4.1 公共桶访问

| 入口 | 路径示例 | 使用场景 | 鉴权 |
|---|---|---|---|
| nginx 直发 | `https://<domain>/static/images/zbm.png?st=<md5>&e=<unix>` | 生产环境对外 | `secure_link_md5` 防盗链 |
| FastAPI 兜底代理 | `http://<backend>/static/images/zbm.png` | 开发环境 / nginx 故障兜底 | 无（公共桶本就匿名只读） |

实现位置：`@/backend/controllers/static_proxy.py`

### 4.2 私有桶访问

| 入口 | 路径示例 | 鉴权 |
|---|---|---|
| 学生头像 | `/photo/get_headphoto/{sfzh}?t=<ts>&s=<hmac>` | HMAC(SHA256, 密钥, sfzh+ts)，5 分钟有效 |
| 招生上传图 | `/photo/zs_image/{filename}` | 当前未签名（**待加固**） |
| 招生简章图 | `/brochure/image/{path}?t=<ts>&s=<hmac>` | 同上 |
| 就业推荐配图 | `/job/image/{filename}?t=<ts>&s=<hmac>` | 同上 |

实现位置：`@/backend/controllers/photo_upload.py`、`@/backend/controllers/brochure.py`、`@/backend/controllers/job_recommend.py`

---

## 5. 命名规范（项目实参）

### 5.1 MinIO 桶名

模板：`<org>-<project>-<env>-<purpose>`
落地：`guizhou-zhpt-prod-private` / `guizhou-zhpt-prod-public`

- `<org>` = `guizhou`
- `<project>` = `zhpt`
- `<env>` ∈ `dev` / `test` / `prod`
- `<purpose>` ∈ `public` / `private`

### 5.2 对象 Key

- 头像：身份证号 + `.jpg`（如 `522633197902185418.jpg`），不带前缀目录
- 业务图：按业务前缀目录组织（见 §2.2）
- 临时文件：`tmp/<uuid>.<ext>`，由清理任务周期回收

### 5.3 Redis 键

模板：`zhpt:<module>:<identifier>`，例如 `zhpt:verify_code:13800000000`、`zhpt:login_verify_code:13800000000`、`zhpt:user:token:<user_id>`

### 5.4 数据库表

下划线小写复数 / 单数视历史而定（旧表保留原名）；新表统一下划线复数。

### 5.5 后端路由 prefix

- 私有图代理：`/photo/*`、`/brochure/*`、`/job/*`
- 公共图代理：`/static/*`
- 管理类：`/admin/*`
- 业务功能：按模块名，如 `/login`、`/photo`、`/brochure`、`/exam`

---

## 6. 密钥与 Token 清单

> 所有密钥实际值在 `backend/.env`（开发） / 运维环境变量（生产）。本表只列**键名 + 用途 + 是否需要轮换**。

| 环境变量 | 用途 | 轮换周期 | 影响范围 |
|---|---|---|---|
| `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | MinIO service account 凭据 | 半年 | 全部图片读写 |
| `STATIC_LINK_SECRET` | nginx `secure_link_md5` + 后端业务图 HMAC 签名共享密钥 | 半年 | 公共桶防盗链 + 私有桶签名 |
| `REDIS_PASSWORD` | Redis 鉴权 | 半年 | 缓存、验证码 |
| `<JWT_SECRET>` 或同等 | 用户登录 Token 签名（若使用 JWT） | 半年 | 全站登录态 |
| `HIKVISION_APP_KEY` / `HIKVISION_APP_SECRET` | 海康威视开放平台 API | 跟随海康策略 | 视频/抓拍 |
| 短信平台 `cpKey`（`backend/utils/sms.py` 内常量） | MAS 短信平台鉴权 | 跟随平台策略 | 验证码 / 业务通知 |
| `BROCHURE_SECRET_KEY`（`backend/controllers/brochure.py` 内常量） | 招生简章图片签名 | 半年 | 招生简章访问 |

> **改进建议**：当前 `cpKey`、`BROCHURE_SECRET_KEY` 还硬编码在源码里，应迁移到 `.env` 统一管理。

### Token 体系

| Token 类型 | 载体 | 生命周期 | 携带身份 |
|---|---|---|---|
| 登录 Token | Header `Authorization: Bearer <token>` 或 业务自定义 | 业务侧约定 | 用户类型（开放学生/老师、中职学生/老师）+ user_id |
| 图片访问签名 | URL Query `?t=&s=`（或 `?st=&e=`） | 5 分钟 | 仅锁定 URI，不绑定用户（由调用前的登录态校验补足） |
| 验证码 | Redis `zhpt:verify_code:<phone>` | 5 分钟 | 仅锁定手机号 |

---

## 7. 生产 nginx 配置（参考）

```nginx
# /etc/nginx/sites-enabled/zhpt.conf
upstream minio_upstream {
    server 172.16.100.102:9000;
    keepalive 32;
}

upstream zhpt_backend {
    server 127.0.0.1:3050;
    keepalive 32;
}

server {
    listen 443 ssl http2;
    server_name <prod-domain>;

    # ssl_certificate / ssl_certificate_key ...

    # 1) 公共静态资源：nginx 直发 MinIO 公共桶
    location /static/ {
        # 防盗链
        secure_link $arg_st,$arg_e;
        secure_link_md5 "$secure_link_expires$uri $http_user_agent <STATIC_LINK_SECRET>";
        if ($secure_link = "")  { return 403; }
        if ($secure_link = "0") { return 410; }

        proxy_pass http://minio_upstream/guizhou-zhpt-prod-public/static/;
        proxy_set_header Host $host;
        proxy_hide_header x-amz-id-2;
        proxy_hide_header x-amz-request-id;
        proxy_hide_header x-amz-meta-server-side-encryption;
        proxy_intercept_errors on;
        error_page 403 = @static_fallback;
        error_page 404 = @static_fallback;

        expires 7d;
        add_header Cache-Control "public, immutable";
    }

    # 1b) nginx 直发失败时降级到后端
    location @static_fallback {
        proxy_pass http://zhpt_backend;
    }

    # 1c) 私有桶预签名对象：nginx 直发 MinIO 私有桶
    #     前端拿到的是 Sig V4 预签名 URL（?X-Amz-...），由 MinIO 端验签
    #     注意：proxy_pass 必须保留 query string（S3 验签需要）
    location /object/ {
        proxy_pass http://minio_upstream/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        # 保留 query string（MinIO SigV4 验签依赖 ?X-Amz-* 参数）
        proxy_set_header X-Accel-Redirect off;
        proxy_hide_header x-amz-id-2;
        proxy_hide_header x-amz-request-id;
        proxy_hide_header x-amz-meta-server-side-encryption;
        # 启用 HTTP Range，让小程序 <image> / 音频能流式播放
        proxy_set_header Range $http_range;
        proxy_pass_request_headers on;
        proxy_buffering off;
        proxy_read_timeout 60s;

        # 大对象支持
        client_max_body_size 50m;

        expires 5m;
        add_header Cache-Control "private, max-age=300";
    }

    # 2) 业务接口
    location / {
        proxy_pass http://zhpt_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }
}
```

**说明**

- `<STATIC_LINK_SECRET>` 在 nginx 配置里只能写明文；将该文件权限设为 `640 root:nginx`，禁止应用账号读取。
- 此 secret 必须与 `backend/.env` 的 `STATIC_LINK_SECRET` **保持一致**——前端从后端拿到带 `?st=&e=` 的 URL 后，由 nginx 验证。
- 业务私有图（`/object/<bucket>/<key>?X-Amz-...`）由 **nginx 直发 MinIO**，MinIO 端用 SigV4 验签；FastAPI 的 `/object/{path:path}` 路由仅作为 HMAC 老签名的兼容通道，新代码生成的 SigV4 URL 应走 nginx → MinIO 这条链路。
- `proxy_pass http://minio_upstream/;` 末尾的 `/` 关键：nginx 会把 `/object/guizhou-zhpt-prod-private/...` 中的 `/object/` 剥掉，把剩余路径 `/guizhou-zhpt-prod-private/...` 转给 MinIO。

---

## 8. 后台管理白名单

`backend/utils/feedback_admin_whitelist.py`（举例，按当前实现）：通过手机号白名单控制后台菜单可见性。修改后**需重启后端生效**。

> 改动白名单视同变更生产配置，须经审批，并在 §9 留底。

---

## 8.1 容器部署故障排查

### 8.1.1 启动即崩：`PermissionError: ... '/app/logs/xjxt.log'`

**现象**：容器反复重启（`Worker failed to boot`），日志只有一行：

```
PermissionError: [Errno 13] Permission denied: '/app/logs/xjxt.log'
  at main.py RotatingFileHandler(...)
```

**根因**：`/app/logs` `/app/uploads` `/app/data` 是宿主机目录 **bind mount** 进来的。镜像里的 `chown` 只对**镜像层内**目录有效，bind mount 会**覆盖**镜像层 —— 挂载点上属主仍是宿主机的。非 root 的 `app` 用户（uid 1001）属主不匹配就写不进去。

**两种解法**（二选一，勿叠加）：

| 方案 | 做法 | 适用 |
|---|---|---|
| **A. 入口脚本自动修正**（推荐） | `docker-entrypoint.sh` 以 root 进入 → `chown` 挂载目录 → `setpriv` 降权回 app 执行 CMD | 常规部署 |
| **B. 宿主机手工改属主** | `chown -R 1001:1001 /www/wwwroot/zhpt/backend/{logs,uploads,data}` | 宿主机属主不能动时 |

**方案 A 的前提**：`docker-entrypoint.sh` **必须存在于构建上下文目录**（`/www/wwwroot/zhpt/backend/docker-entrypoint.sh`）。缺失时 `docker compose build` 直接失败：

```
failed to calculate checksum ... "/docker-entrypoint.sh": not found
```

同步文件时**务必带上它**（`deploy1.sh` 已包含）。

**降级开关**：宿主机目录属主必须保持原样时，设 `FIX_MOUNT_OWNER=0` 跳过自动修正 —— 应用侧已有兜底（日志写不了就只输出 stdout，不再崩溃）。

### 8.1.2 应用层兜底

`backend/utils/log_setup.py` 提供容错封装：

- `ensure_log_dir()` — 真实写探针文件验证可写性
- `safe_file_handler()` — 主动 `os.open` 探测后才建 handler，失败返回 `None`
- `safe_append_line()` — 旁路日志写失败静默返回 `False`

即：**日志写不了只会降级为 stdout 输出，绝不会让 worker 启动失败**。

---

## 9. 演进记录

| 日期 | 变更 | 操作人 | 备注 |
|---|---|---|---|
| 2026-05-11 | P1：拆分公共桶 `guizhou-zhpt-prod-public`，迁移首页/图标类静态资源；后端新增 `/static/*` 兜底代理 | — | 见 `@/docs/image-access-refactor.md` |
| 2026-05-11 | P2：修复 `/static/*` 路由不存在 → 修正 prefix；解决跨网段访问 `Provisional headers` 卡顿 | — | — |
| 2026-05-11 | P3：业务私有数据从 `headphoto` 迁移到 `guizhou-zhpt-prod-private`，10744 对象 `mc diff` 一致后切桶；后端切换 service account（`flysky` → `ZXU2KINV0UJ2D9CTW65H`） | — | 见 `@/backend/scripts/p3_bucket_migration.md` |
| 2026-11-03 | 修复容器日志权限崩溃：新增 `docker-entrypoint.sh`（自动修正 bind mount 属主）+ `utils/log_setup.py`（应用层容错兜底） | — | 见 §8.1 |

---

## 10. 待办与改进建议

- [ ] 把硬编码在源码的 `BROCHURE_SECRET_KEY`、SMS `cpKey` 迁移到 `.env`
- [ ] 给 `/photo/zs_image/{filename}` 加签名校验（当前裸露）
- [ ] 老桶 `headphoto` 在 P3 cutover 稳定 30 天后执行 `mc rb --force` 删除（计划日期：2026-06-10）
- [ ] 把 service account AK/SK 的轮换接入运维 SOP，加到半年度安全检查
- [ ] 生产 nginx 配置纳入 IaC（如 Ansible / Pulumi），避免手改丢失
- [ ] `INFRA_PLAYBOOK.md` 每次基础设施变更后**必须** PR 同步更新
- [ ] **构建上下文文件的同步检查**：`docker-entrypoint.sh` 是 Dockerfile 的 `COPY` 源，
      缺失时 build 直接失败（`not found`）。新增任何被 Dockerfile `COPY` 的文件时，
      必须同步更新 `_deploy/deploy1.sh` 的备份/拷贝列表。
