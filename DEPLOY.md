# zhxt 双人协作 + 自动部署手册

> 模型：GitHub 私有仓 `main` 直推 + Ubuntu 服务器自托管 Runner。
> push 到 `main` 即自动部署（后端重建容器、前端重建 dist），约 2–5 分钟生效。

---

## 一、建 GitHub 私有仓并首次推送（任选一人在电脑上做一次）

1. 到 GitHub 新建仓库：**Private**，名字如 `zhxt`，不要勾选 README/`.gitignore`（本地已有）。
2. 本地仓库已初始化好（`main` 分支、首个 commit 已提交），只需关联并推送：

```bash
cd E:\MyPrj\zhxt
git remote add origin https://github.com/<你的组织或用户名>/zhxt.git
git push -u origin main
```

3. 把第二个人加为 collaborator：仓库页 **Settings → Collaborators → Add people**，
   对方接受邀请后：

```bash
git clone https://github.com/<你的组织或用户名>/zhxt.git
```

## 二、日常协作（两人都直推 main）

```bash
git pull --rebase      # 开工先拉
# …改代码…
git add -A && git commit -m "说明这次改了什么"
git pull --rebase && git push   # 推之前先拉，避免冲突
```

冲突时 Git 会标出 `<<<<<<<`，两人商量保留哪边，改完 `git add -A && git rebase --continue`。

**铁律：**
- `backend/.env`（真密钥）永远不进仓库，每人本地各维护一份，服务器上那份不动。
- 生产前端地址：`frontend/.env.production` 保持 `VITE_API_BASE_URL=`（空），
  本地联调走 `frontend/.env`（`localhost:3088`），互不干扰。
- 两个人不要同时改同一个文件且都不拉取，推前必 `git pull --rebase`。

## 三、服务器装自托管 Runner（在 172.16.100.102 上做一次）

前置：服务器能访问 github.com（只需出站 443，内网机一般可经网关出去；
若完全不能上外网，此方案不可用，改用下面的方案 B）。

```bash
# 1. 装依赖：docker / node 20 / rsync
sudo apt update && sudo apt install -y rsync curl
node -v || (curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install -y nodejs)

# 2. 建目录并给 ubuntu 用户写权限（Runner 以 ubuntu 身份跑）
sudo mkdir -p /www/wwwroot/zhxt /opt/actions-runner
sudo chown -R ubuntu:ubuntu /www/wwwroot/zhxt /opt/actions-runner

# 3. 下载 Runner（版本号去 github.com/actions/runner/releases 对照，示例 2.321.0）
cd /opt/actions-runner
curl -o runner.tar.gz -L https://github.com/actions/runner/releases/download/v2.321.0/actions-runner-linux-x64-2.321.0.tar.gz
tar xzf runner.tar.gz

# 4. 注册（token 去 GitHub 仓库页 Settings → Actions → Runners → New self-hosted runner 复制）
./config.sh --url https://github.com/<你的组织或用户名>/zhxt --token <刚才复制的TOKEN> --labels zhxt-prod --name zhxt-prod-102

# 5. 装成系统服务并启动
sudo ./svc.sh install ubuntu
sudo ./svc.sh start
./run.sh --check --labels zhxt-prod   # 应显示监听成功
```

GitHub 仓库页 **Settings → Actions → Runners** 看到 `zhxt-prod-102` 变绿即成功。
以后 `git push` 到 main，Actions 页能看到 `deploy-prod` 自动跑，
日志里有"后端部署完成 / 前端部署完成"即上线成功。

回滚：Actions 找上一次成功的 run 点 **Re-run jobs** 即可回到上一版。

## 四、方案 B（备选：服务器不能访问外网时）

服务器上每 5 分钟自动拉取：

```bash
# 服务器：先把线上目录变成 git 仓库（保留 .env！）
cd /www/wwwroot/zhxt/backend && git init -b main 2>/dev/null; git remote add origin https://github.com/<组织>/zhxt.git 2>/dev/null
git fetch origin && git checkout -f origin/main -- app main.py requirements.txt Dockerfile docker-compose.yml
```

或写个 cron 脚本定时 `git pull + docker compose up -d --build + 前端构建`。
需要时我再帮你写这个脚本。

## 五、文件说明

| 文件 | 作用 |
|---|---|
| `.github/workflows/deploy.yml` | push 到 main 自动触发部署 |
| `scripts/deploy-backend.sh` | 同步后端代码（跳过 `.env`/日志/数据）+ 重建容器 |
| `scripts/deploy-frontend.sh` | `npm ci + build`，校验无硬编码 IP 后覆盖发布目录 |
| `backend/.env.example` | 新人照此复制出自己的 `backend/.env` |
