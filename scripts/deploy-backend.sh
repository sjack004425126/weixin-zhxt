#!/bin/bash
# ============================================================
# weixin-zhxt 后端自动部署（微信小程序项目）
#
#   触发：push 到 main → Runner(checkout 到 _work) → 本脚本
#   目标：DST=/www/wwwroot/weixin-zhxt/backend，端口 3050
#
# 与通用模板的两处差异（本项目特有）：
#   1) 没有前端构建发布步骤 —— frontend 是微信小程序，只进仓，
#      不部署到 102（见 .github/workflows/deploy.yml）。
#   2) rsync 额外排除 uploads/ 和 data/ —— 这两个是线上用户数据，
#      --delete 绝不能碰它们；缺失时只 mkdir，不从仓库覆盖。
# ============================================================
set -e

SRC="$GITHUB_WORKSPACE/backend"
DST="/www/wwwroot/weixin-zhxt/backend"
PORT="3050"
CONTAINER="weixin-zhxt-backend"

echo ">>> [1/5] 同步代码 $SRC -> $DST"
mkdir -p "$DST"
rsync -a --delete \
  --exclude='.env' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='logs/' \
  --exclude='*.log' \
  --exclude='uploads/' \
  --exclude='data/' \
  --exclude='task_store/' \
  --exclude='exports/' \
  --exclude='export_temp/' \
  --exclude='.venv/' --exclude='venv/' \
  "$SRC/" "$DST/"
mkdir -p "$DST/logs" "$DST/uploads" "$DST/data"
chmod -R a+rwX "$DST/logs" "$DST/uploads" "$DST/data"

echo ">>> [2/5] 选择 compose 命令"
# 102 上只有 docker-compose 二进制，无 docker compose 插件，双兼容
if docker compose version >/dev/null 2>&1; then DOCKER_COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then DOCKER_COMPOSE="docker-compose"
else echo "ERROR: no compose found"; exit 125; fi
echo "使用: $DOCKER_COMPOSE"

# 生产 .env 由管理员在服务器上手工维护，仓库里永远没有；
# 缺失则直接失败，绝不用默认配置启动（保护生产库）。
if [ ! -f "$DST/.env" ]; then
  echo "ERROR: $DST/.env 缺失，停止部署。请先在服务器上建好 .env 再重跑。"
  exit 1
fi

echo ">>> [3/5] 重建容器（代码烘进镜像，必须 --build）"
cd "$DST"
DEPLOY_LOG="$DST/logs/deploy-$(date +%Y%m%d-%H%M%S).log"
$DOCKER_COMPOSE up -d --build 2>&1 | tee "$DEPLOY_LOG"
$DOCKER_COMPOSE ps | tee -a "$DEPLOY_LOG"

echo ">>> [4/5] 健康检查 http://127.0.0.1:$PORT/health"
for i in $(seq 1 30); do
  if curl -fsS -m 5 "http://127.0.0.1:$PORT/health" | tee -a "$DEPLOY_LOG"; then
    echo
    echo ">>> 健康检查通过"
    break
  fi
  echo "等待容器启动 ($i/30)..."
  sleep 5
  if [ "$i" = "30" ]; then
    echo "ERROR: 健康检查超时，最后 60 行构建日志："
    tail -n 60 "$DEPLOY_LOG"
    echo "---- 容器日志 ----"
    docker logs "$CONTAINER" --tail 50 || true
    exit 1
  fi
done

echo ">>> [5/5] 后端部署完成"
