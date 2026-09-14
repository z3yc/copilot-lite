#!/usr/bin/env bash
# ============================================================
# Copilot-Lite 一键部署（在服务器上执行，唯一部署入口）
#
#   bash deploy/deploy.sh            # 部署最新 main：拉码 → 构建 → 起容器 → 健康检查
#   bash deploy/deploy.sh rollback   # 回滚到上一版代码并重建
#
# 前置：服务器已装 Docker + docker compose 插件；仓库克隆在 $APP_DIR（默认
#       /opt/copilot-lite），且 deploy/.env 已配置（参考 deploy/.env.example）。
# 说明：前端已进镜像（deploy/Dockerfile.web），无需宿主机 Node / web/dist。
# ============================================================
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/copilot-lite}"
BRANCH="${BRANCH:-main}"
COMPOSE_DIR="$APP_DIR/deploy"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1/api/v1/health}"
WAIT_SECONDS="${WAIT_SECONDS:-120}"

log()  { echo "[deploy $(date '+%F %T')] $*"; }
fail() { log "✗ $*"; exit 1; }
compose() { ( cd "$COMPOSE_DIR" && docker compose "$@" ); }

cd "$APP_DIR" || fail "目录不存在：$APP_DIR"

# ---------- 回滚模式 ----------
if [[ "${1:-}" == "rollback" ]]; then
  git rev-parse --verify --quiet HEAD~1 >/dev/null || fail "没有可回滚的上一版"
  log "回滚代码：$(git rev-parse --short HEAD) → $(git rev-parse --short HEAD~1)"
  git checkout "$BRANCH"
  git reset --hard HEAD~1
  compose up -d --build
  log "✅ 回滚完成"
  exit 0
fi

# ---------- 常规部署 ----------
command -v docker >/dev/null 2>&1 || fail "未安装 docker"
docker compose version >/dev/null 2>&1 || fail "未安装 docker compose 插件"
[[ -f "$COMPOSE_DIR/.env" ]] || fail "$COMPOSE_DIR/.env 缺失（参考 .env.example）"

PREV_SHA="$(git rev-parse HEAD)"

log "1/4 拉取最新代码（$BRANCH，仅快进合并，绝不强覆服务器本地改动）"
# 若处于 detached HEAD（历史回滚留下的状态），先切回分支
if ! git symbolic-ref -q HEAD >/dev/null; then
  git checkout "$BRANCH" || fail "无法切回分支 $BRANCH（存在本地改动？请人工处理）"
fi
git fetch origin "$BRANCH"
git merge --ff-only "origin/$BRANCH" \
  || fail "远端与本地分叉，拒绝强拉。请人工处理：git status / git log HEAD..origin/$BRANCH"

log "2/4 构建并启动容器（数据库迁移由 backend 启动命令自动执行）"
compose up -d --build

log "3/4 健康检查（最多 ${WAIT_SECONDS}s）"
deadline=$(( $(date +%s) + WAIT_SECONDS ))
while (( $(date +%s) < deadline )); do
  if curl -fsS --max-time 5 "$HEALTH_URL" >/dev/null 2>&1; then
    log "✅ 部署成功：$HEALTH_URL"
    exit 0
  fi
  sleep 5
done

# 健康检查失败：回滚代码并重建（部署机为 deploy-only，无本地改动）
log "4/4 ✗ 健康检查失败，回滚到 $PREV_SHA"
git reset --hard "$PREV_SHA"
compose up -d --build
fail "部署失败并已回滚。日志：cd $COMPOSE_DIR && docker compose logs backend"
