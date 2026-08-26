#!/usr/bin/env bash
# ============================================================
# Copilot-Lite 远端部署脚本（在云服务器上执行）
#
# 职责：拉取最新代码 → 原子替换前端产物 → 重建容器 → 健康检查 → 失败自动回滚
#
# 用法（由 Jenkins Deploy 阶段调用，也可手动执行）：
#   bash deploy_remote.sh              # 部署最新 main
#   bash deploy_remote.sh rollback     # 回滚前端产物到上一版
#
# 前置：服务器已按 deploy/DEPLOY.md 初始化
#       （Docker + 克隆仓库到 /opt/copilot-lite，deploy/.env 已配置）
# 约定：
#   web/dist.new   —— CI 上传的新前端产物（本脚本校验后原子替换为 web/dist）
#   web/dist.prev  —— 上一版产物备份（回滚/失败恢复用）
# ============================================================
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/copilot-lite}"
DIST_DIR="$APP_DIR/web/dist"
DIST_NEW="$APP_DIR/web/dist.new"
DIST_PREV="$APP_DIR/web/dist.prev"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1/api/v1/health}"

log()  { echo "[deploy $(date '+%F %T')] $*"; }
fail() { log "✗ $*"; exit 1; }

# ---------- 回滚模式 ----------
if [[ "${1:-}" == "rollback" ]]; then
  [[ -d "$DIST_PREV" ]] || fail "没有可回滚的上一版本（$DIST_PREV 不存在）"
  log "回滚前端产物：dist.prev → dist"
  rm -rf "$DIST_DIR"
  mv "$DIST_PREV" "$DIST_DIR"
  log "重建 web 容器（nginx 只读挂载 dist，重建即生效）"
  ( cd "$APP_DIR/deploy" && docker compose up -d --build web )
  log "✅ 回滚完成"
  exit 0
fi

# ---------- 常规部署 ----------
cd "$APP_DIR" || fail "目录不存在：$APP_DIR"

log "1/5 拉取最新代码（main）"
git fetch origin main
git reset --hard origin/main

log "2/5 校验前端产物"
[[ -d "$DIST_NEW" ]] || fail "未找到 $DIST_NEW —— 请先由 CI 上传 web/dist 到该路径"
[[ -f "$DIST_NEW/index.html" ]] || fail "$DIST_NEW/index.html 缺失，产物不完整，中止部署"

log "3/5 原子替换前端产物（保留 .prev 用于回滚）"
rm -rf "$DIST_PREV"
[[ -d "$DIST_DIR" ]] && mv "$DIST_DIR" "$DIST_PREV"
mv "$DIST_NEW" "$DIST_DIR"

log "4/5 重建并启动容器（数据库迁移由 backend 启动命令自动执行）"
( cd "$APP_DIR/deploy" && docker compose up -d --build )

log "5/5 健康检查（最多等待 120s）"
for i in $(seq 1 24); do
  if curl -fsS --max-time 5 "$HEALTH_URL" >/dev/null 2>&1; then
    log "✅ 健康检查通过：$HEALTH_URL"
    exit 0
  fi
  sleep 5
done

log "✗ 健康检查失败，自动回滚到上一版本"
rm -rf "$DIST_DIR"
[[ -d "$DIST_PREV" ]] && mv "$DIST_PREV" "$DIST_DIR"
( cd "$APP_DIR/deploy" && docker compose up -d --build web )
fail "部署失败并已回滚，请查看日志：docker compose -f $APP_DIR/deploy/docker-compose.yml logs backend"
