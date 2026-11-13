# weixin-zhxt 自动部署手册

> 模型：GitHub 私有仓 `main` 直推 + 102 自托管 Runner。
> push 到 `main` 即自动部署**后端**（重建容器，约 2–5 分钟）。
> `frontend/` 是微信小程序，**只进仓、不部署到 102**。

---

## 一、目录与约定（本项目实际值）

| 项 | 值 |
|---|---|
| 仓库 | `sjack004425126/weixin-zhxt`，分支 `main` |
| 后端线上目录 | `/www/wwwroot/weixin-zhxt/backend`（属主 `ubuntu:ubuntu`，uid/gid `1000:1000`） |
| 后端端口 | `3050`（容器内外一致，反代指向 `127.0.0.1:3050`，勿改） |
| 容器/镜像 | `weixin-zhxt-backend` / `weixin-zhxt-backend:latest`，compose 项目名 `weixin-zhxt` |
| Runner | 目录 `/opt/actions-runner-weixin-zhxt`，服务名 `actions.runner.sjack004425126-weixin-zhxt.weixin-zhxt-102`，标签 `weixin-zhxt-prod`，名称 `weixin-zhxt-102` |
| compose 命令 | 102 上只有 `docker-compose` 二进制，无 `docker compose` 插件，脚本已双兼容 |
| 出站代理 | `http://172.16.100.20:8118`（只 Runner 走，整机不走） |
| 生产 `.env` | 服务器手工维护 `/www/wwwroot/weixin-zhxt/backend/.env`，仓库里只有 `.env.example` |

## 二、日常协作

```bash
git pull --rebase      # 开工先拉
# …改代码…
git add -A && git commit -m "说明这次改了什么"
git pull --rebase && git push   # 推之前先拉
```

铁律：`backend/.env` 真密钥永不进仓；`frontend/project.private.config.json` 不进仓（已忽略）。

## 三、部署链路

```text
本地 push ──▶ GitHub(main) ──▶ Runner weixin-zhxt-102(checkout 到 _work)
  └─ bash scripts/deploy-backend.sh   # rsync → docker-compose up -d --build → curl /health
```

- `deploy.yml` 只有后端一个 job（无前端构建）。
- `deploy-backend.sh` 会：rsync（`--delete`，但跳过 `.env`/`logs`/`uploads`/`data` 等线上数据）、
  校验 `.env` 存在、重建容器、`curl 127.0.0.1:3050/health` 最多等 150 秒。
- `uploads/`、`data/` 是线上用户数据，脚本只 `mkdir` 不覆盖不删除。

回滚：Actions 找上一次成功的 run 点 **Re-run jobs**。

## 四、文件说明

| 文件 | 作用 |
|---|---|
| `.github/workflows/deploy.yml` | push 到 main 触发，`runs-on: [self-hosted, weixin-zhxt-prod]` |
| `scripts/deploy-backend.sh` | 同步后端代码 + 重建容器 + 健康检查 |
| `backend/.env.example` | 新人照此复制出自己的 `backend/.env` |

## 五、排错速查

| 现象 | 原因 | 解法 |
|---|---|---|
| 健康检查超时 | 构建失败或 DB/Redis 连不上 | 看 `DST/logs/deploy-*.log` + `docker logs weixin-zhxt-backend --tail 50` |
| `weixin-zhxt-backend/.env 缺失` | 服务器没放生产配置 | 管理员补 `/www/wwwroot/weixin-zhxt/backend/.env` 后重跑 |
| 容器 `Permission denied: /app/logs/xjxt.log` | bind 挂载属主不匹配 | 入口脚本已自动修正；检查 `APP_UID/GID=1000` |
| `git push` 被 reset | 没走代理 | 本仓已配 `http.proxy`，换网后检查 `git config --local --list \| grep proxy` |
| CRLF 报错 | Windows 换行 | 根 `.gitattributes` 强制 LF |
