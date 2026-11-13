---
name: github-runner-deploy
description: Deploy any project to Ubuntu via GitHub private repo plus self-hosted Runner auto-deploy. Use when the user asks to push a project to GitHub, add auto-deploy on push to main, install or reuse a Runner on 172.16.100.102, write deploy.yml or deploy scripts, explain svc.sh/config.sh/.env/.credentials, fix CI exit 23/125/243, or set up a second project reusing the Runner program.
---

# GitHub 私有仓 + 自托管 Runner 自动部署

模型：`push 到 main` → 服务器 Runner 自动拉代码 → 后端重建容器 → 前端重建 dist。
内网机（出站经 `http://172.16.100.20:8118` 代理）专用，整机不走代理，只有 Runner 走。

## 架构一句话

```text
本地 push ──▶ GitHub(main) ──▶ Runner(checkout 到 _work/xxx/xxx)
  ├─ bash scripts/deploy-backend.sh    # rsync 代码 → docker 重建
  └─ bash scripts/deploy-frontend.sh   # npm ci + build → 覆盖静态目录
```

- `deploy.yml` 只决定"何时跑、跑哪台、调哪两个脚本"，本身不含构建逻辑。
- 前端是不是 Vue3、后端要不要编译，全由两个 `scripts/*.sh` 决定。

## Step 0 — 前置信息（先问清再动手）

| 项 | 说明 |
|---|---|
| 项目名/线上目录 | 如 `zhxt` → `/www/wwwroot/zhxt/{backend,frontend}` |
| 后端端口 | 须与反代一致（如 3088），不能随意改 |
| 前端类型 | Vue3/Vite(`dist`) / React(`build`) / 纯静态（免构建） |
| 外部服务 | DB/Redis/MinIO 是现成的还是 compose 内起 |
| 代理 | 出站代理地址（如 `172.16.100.20:8118`） |
| Runner 标签 | 每项目独立，如 `zhxt-prod`、`newproj-prod` |

## Step 1 — 本地仓库三件套

1. `.gitignore`（根）：`backend/.env`、`logs/`、`task_store/`、`exports/`、`export_temp/`、`node_modules/`、`frontend/dist/` 绝不进仓库。验证：`git status --short | grep ".env"` 只能看到 `.env.example`。
2. `.gitattributes`（根，防 Windows CRLF 到 Linux 报错）：
```text
*.sh text eol=lf
.github/workflows/*.yml text eol=lf
*.py text eol=lf
Dockerfile text eol=lf
```
3. `backend/.env.example`：真 `.env` 脱敏抄一份，新人照此建自己的 `.env`。

```bash
git init -b main
git add -A && git commit -m "init: 首版"
```

## Step 2 — GitHub 私有仓 + 推送（必走代理）

1. GitHub 建 **Private** 仓，不勾 README。
2. 本地关联推送（内网直连会被 reset，必须 export 代理，Windows Git Bash 用 `export` 不用 `set`）：

```bash
git remote add origin https://github.com/<owner>/<repo>.git
export https_proxy=http://172.16.100.20:8118 http_proxy=http://172.16.100.20:8118 HTTPS_PROXY=http://172.16.100.20:8118 HTTP_PROXY=http://172.16.100.20:8118
git push -u origin main
```

3. 加人：`Settings → Collaborators → Add people`，对方 `git clone` 即可。
4. 日常：开工 `git pull --rebase`，`git add + commit`，推前再 `pull --rebase` 一次再 `push`。

## Step 3 — Runner（程序共用，实例每项目一份）

目录里分两类文件，决定了"可复用、须隔离"：

- 程序（共用）：`bin/`、`externals/`、`run.sh`、`svc.sh`、`env.sh`。
- 身份（每项目独立）：`.credentials`、`.credentials_rsaparams`、`.runner`、`_work/`。
- 一个实例 `./config.sh --url .../某仓库` 写死，只能听一个仓库。

### 3.1 首个项目（完整安装）

```bash
apt update && apt install -y rsync curl
node -v || (curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && apt install -y nodejs)
mkdir -p /www/wwwroot/<proj> /opt/actions-runner-<proj>
chown -R ubuntu:ubuntu /www/wwwroot/<proj> /opt/actions-runner-<proj>
cd /opt/actions-runner-<proj>
export http_proxy=http://172.16.100.20:8118 https_proxy=http://172.16.100.20:8118
curl -o runner.tar.gz -L https://github.com/actions/runner/releases/download/v2.338.2/actions-runner-linux-x64-2.338.2.tar.gz
# 校验（去 Releases 页抄对应 hash）
echo "<hash>  runner.tar.gz" | shasum -a 256 -c
tar xzf ./runner.tar.gz
unset http_proxy https_proxy
```

版本太旧（如 2.321）注册会 `404`，必须用 Releases 页最新版（当前 2.338.2）。

### 3.2 后续项目（复用包，不重下）

```bash
mkdir -p /opt/actions-runner-<new> /www/wwwroot/<new>
tar xzf /opt/actions-runner-<old>/actions-runner-linux-x64-2.338.2.tar.gz -C /opt/actions-runner-<new>
cp /opt/actions-runner-<old>/.env /opt/actions-runner-<new>/.env
chown -R ubuntu:ubuntu /opt/actions-runner-<new> /www/wwwroot/<new>
```

### 3.3 Runner 专属代理（只 Runner 走，整机不走）

`/opt/actions-runner-<proj>/.env`（`run.sh`/服务启动时自动加载）：

```bash
http_proxy=http://172.16.100.20:8118
https_proxy=http://172.16.100.20:8118
HTTP_PROXY=http://172.16.100.20:8118
HTTPS_PROXY=http://172.16.100.20:8118
no_proxy=localhost,127.0.0.1,::1,172.16.0.0/16,172.18.0.0/16,192.168.0.0/16,10.0.0.0/8
NO_PROXY=localhost,127.0.0.1,::1,172.16.0.0/16,172.18.0.0/16,192.168.0.0/16,10.0.0.0/8
```

不要设 `git config --global http.proxy`，那会污染整机所有 git。

### 3.4 注册（TOKEN 一次性，凭证长期）

```bash
cd /opt/actions-runner-<proj>
export http_proxy=http://172.16.100.20:8118 https_proxy=http://172.16.100.20:8118
# TOKEN 去仓库页 Settings → Actions → Runners → New self-hosted runner 复制（1小时有效，去掉网页带的 Copied! 后缀）
sudo -u ubuntu ./config.sh --url https://github.com/<owner>/<repo> --token <纯TOKEN> --labels <proj>-prod --name <proj>-102
unset http_proxy https_proxy
```

- `--token` 只换长期身份，换完作废，写入 `.credentials` + `.runner` + `.credentials_rsaparams`。
- 以后重启/断电**不用重跑**，`svc.sh start` 读 `.credentials` 自连。只在 `config.sh remove` 或 GitHub 删 Runner 后才重配。
- `--name` 必须全机唯一（决定 systemd 服务名），`--labels` 必须与 `deploy.yml` 的 `runs-on` 对应。

### 3.5 svc.sh（包里自带不用新建）

解压即有：`config.sh run.sh svc.sh runsvc.sh`。`run.sh` 前台调试用，`svc.sh` 装 systemd 服务（开机自启后台常驻），`runsvc.sh` 是内部调用。

```bash
cd /opt/actions-runner-<proj>
sudo ./svc.sh install ubuntu   # 生成 actions.runner.<owner>-<repo>.<name>.service
sudo ./svc.sh start
sudo ./svc.sh status           # active + Connected to GitHub 即成功
systemctl list-units 'actions.runner.*' --no-pager  # 多项目各一个服务互不冲突
```

常用：`status/stop/start/restart`，`uninstall` 只删服务不删目录。

## Step 4 — 部署文件（每项目三份抄模板改三处）

```
.github/workflows/deploy.yml   # runs-on: [self-hosted, <proj>-prod]
scripts/deploy-backend.sh       # DST=/www/wwwroot/<proj>/backend
scripts/deploy-frontend.sh      # DST=/www/wwwroot/<proj>/frontend
```

改三处：两个 `DST` + 一个 `labels`。`deploy.yml` 模板：

```yaml
name: deploy-prod
on:
  push: { branches: [main] }
  workflow_dispatch: {}
jobs:
  deploy:
    runs-on: [self-hosted, <proj>-prod]
    steps:
      - uses: actions/checkout@v4
      - name: 后端部署
        run: bash scripts/deploy-backend.sh
      - name: 前端构建发布
        run: bash scripts/deploy-frontend.sh
```

### deploy-backend.sh 要点

```bash
SRC="$GITHUB_WORKSPACE/backend"; DST="/www/wwwroot/<proj>/backend"
rsync -a --delete --exclude='.env' --exclude='__pycache__/' --exclude='logs/' \
  --exclude='*.log' --exclude='task_store/' --exclude='exports/' --exclude='export_temp/' "$SRC/" "$DST/"
mkdir -p "$DST/logs" "$DST/task_store" "$DST/exports" "$DST/export_temp"
chmod -R a+rwX "$DST/logs" "$DST/task_store" "$DST/exports" "$DST/export_temp"
cd "$DST"
# 兼容老机器：优先 docker compose 插件缺失回落 docker-compose 二进制否则 exit 125
if docker compose version >/dev/null 2>&1; then DOCKER_COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then DOCKER_COMPOSE="docker-compose"
else echo "no compose"; exit 125; fi
DEPLOY_LOG="$DST/logs/deploy-$(date +%Y%m%d-%H%M%S).log"
$DOCKER_COMPOSE up -d --build 2>&1 | tee "$DEPLOY_LOG"   # 代码烘进镜像必须 --build
$DOCKER_COMPOSE ps
for i in $(seq 1 30); do curl -fsS -m 5 http://127.0.0.1:<port>/health && break; sleep 5; done
```

- Python 无编译但 `Dockerfile COPY . /app` 把代码烘进镜像，只拷文件不重建=旧代码，必须 `--build`。`requirements.txt` 不变时 pip 层 `CACHED` 只要几秒。
- `chmod a+rwX` 双保险：bind 挂载盖掉镜像内 `chown`，宿主属主 ubuntu vs 容器内 app(uid 999) 否则 `Permission denied: /app/logs/app.log`。
- 日志落盘 `$DST/logs/deploy-*.log`，失败 `tail 60` 即定位。

### deploy-frontend.sh 要点

```bash
SRC="$GITHUB_WORKSPACE/frontend"; DST="/www/wwwroot/<proj>/frontend"
cd "$SRC"
export NODE_OPTIONS="--max-old-space-size=3072"
export NPM_CONFIG_CACHE="${RUNNER_TEMP:-/tmp}/npm-cache-$$"  # 默认 /www/server/nodejs/cache 是 root 的会 EACCES 243
mkdir -p "$NPM_CONFIG_CACHE"
npm ci --no-audit --no-fund --registry=https://registry.npmmirror.com || npm ci --no-audit --no-fund
npm run build            # 即 package.json "build": "vite build"，Vue3/React/静态页按此替换
grep -rq "<开发IP>" dist/ && { echo "dist 含开发 IP"; exit 1; }  # 防 .env.production 写错
rm -rf "$DST/assets" "$DST/index.html"
cp -r "$SRC/dist/assets" "$DST/assets"; cp "$SRC/dist/index.html" "$DST/"
```

- 服务端不知道 Vue3：只是执行 `npm run build` 再 `cp dist/* $DST/`。React 把 `dist` 换 `build`，纯静态删构建直接 `cp`。`$DST` 即 OpenResty `root` 对外 serving。
- 构建日志落 `/tmp/frontend-deploy-*.log`。

## 缓存行为

- Runner `_work/<repo>/<repo>/.git` 常驻：首次全量 clone之后每次 `fetch + checkout` 只传差异。`ls -ld .git`（很老）vs `ls -lt frontend/src`（最新）即证据。
- `checkout` 默认 `git clean`，上次 `dist/` 不污染下次。
- `npm ci` 每次清空重装（按 lock 精确版，可复现慢 1~2 分钟故意换可靠）；后端 `rsync --delete` + 镜像层缓存（依赖不变只重跑 COPY 层）。

## 验证

```bash
curl -s http://127.0.0.1:<port>/api/v1/<probe> | head -c 500
curl -sk https://<域名>/api/v1/<probe> | head -c 500
docker logs <容器> --tail 30
ls -lt /www/wwwroot/<proj>/frontend/ | head
```

GitHub `Actions → deploy-prod` 绿即上线，前端 `Ctrl+F5` 硬刷。

## 排错速查

| 现象 | 原因 | 解法 |
|---|---|---|
| 注册 `POST .../runner-registration 404` | 包太旧(2.321)接口下线 | 换 2.338.2+重解压 |
| `Request headers must contain ASCII` | Token 粘了 `Copied!` | 只留纯 Token，重配 |
| `shasum FAILED` | 半截包（没走代理慢速中断） | 删包挂代理重下到 OK 再解 |
| CI `exit 23` | Runner(ubuntu)写不进线上目录 | `chown -R ubuntu:ubuntu /www/wwwroot/<proj>` |
| CI `exit 125` | 只有 `docker-compose` 无 `docker compose` 插件 | 脚本兼容两者 |
| 前端 `exit 243 EACCES` | npm 缓存 `/www/server/nodejs/cache` 属 root | 缓存改 `RUNNER_TEMP` |
| 容器 `Permission denied: /app/logs/app.log` | bind 盖掉镜像权限 | 镜像+脚本双 `chmod a+rwX` |
| 推了线上仍 `Not Found` | 容器没重建/构建失败 | 看 `logs/deploy-*.log` + `docker logs` |
| `git push` 被 reset | 没走代理 | export 四个代理变量再推 |
| CRLF 报错 | Windows 换行 | `.gitattributes` 强制 LF |
