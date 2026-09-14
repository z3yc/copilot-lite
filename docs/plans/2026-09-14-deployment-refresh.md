# 部署方式刷新（Docker 自包含 + 一键脚本）实现计划

> **REQUIRED SUB-SKILL:** 用 `executing-plans` 按任务逐步执行本计划。

**Goal:** 让 Docker 部署自包含（前端进镜像），把部署收敛为服务器上一条 `bash deploy/deploy.sh`，Jenkins 只做 CI（Deploy 可选、默认关、复用同一脚本）。

**Architecture:** 新增多阶段 `deploy/Dockerfile.web`（node 构建 → nginx 托管）；`compose` 的 `web` 改为构建该镜像、去掉宿主机产物挂载；新增 `deploy/deploy.sh` 作为唯一部署入口（拉码 → 构建 → 起容器 → 健康检查 → 失败回滚）；删除 `deploy_remote.sh`；`Jenkinsfile` Deploy 改为 SSH 执行 `deploy.sh`。

**Tech Stack:** Docker / docker compose、Nginx、Node 20（构建期）、Jenkins（可选 CD）、Git。

**设计文档:** `docs/plans/2026-09-14-deployment-refresh-design.md`

---

## Task 1: 前端进镜像（Dockerfile.web + compose 改造）

**Files:**
- Create: `deploy/Dockerfile.web`
- Modify: `deploy/docker-compose.yml`（仅 `web` 服务）

**Step 1: 新建 `deploy/Dockerfile.web`**

```dockerfile
# Copilot-Lite 前端镜像（多阶段：Node 构建 → Nginx 托管）
# 构建：docker build -f deploy/Dockerfile.web -t copilot-lite-web .
# 上下文：仓库根（.dockerignore 已排除 node_modules / dist / .venv 等）

FROM node:20-alpine AS build
WORKDIR /web
# 国内源（构建容器不继承宿主代理）；可 --build-arg NPM_REGISTRY=... 覆盖
ARG NPM_REGISTRY=https://registry.npmmirror.com
# 先装依赖，利用缓存层
COPY web/package.json web/package-lock.json ./
RUN npm ci --registry="$NPM_REGISTRY"
# 再复制源码并构建（tsc 类型检查 + vite 打包）
COPY web/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /web/dist /usr/share/nginx/html
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
```

**Step 2: 改 `deploy/docker-compose.yml` 的 `web` 服务**

把：
```yaml
  web:
    image: nginx:1.27-alpine
    restart: unless-stopped
    volumes:
      - ../web/dist:/usr/share/nginx/html:ro
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
```
改为：
```yaml
  web:
    build:
      context: ..
      dockerfile: deploy/Dockerfile.web
    restart: unless-stopped
```
（`ports` / `depends_on` / `healthcheck` / `deploy` 保持不变。）

**Step 3: 验证构建**

Run:
```bash
docker compose -f deploy/docker-compose.yml build web
```
Expected: 构建成功，产出 `deploy-web` 镜像（`docker images | grep web` 可见）。

**Step 4: 验证全栈起来**

Run:
```bash
cd deploy && docker compose up -d --build
docker compose ps
curl -fsS -o /dev/null -w "%{http_code}\n" http://127.0.0.1/api/v1/health
curl -fsS -o /dev/null -w "%{http_code}\n" http://127.0.0.1/
```
Expected: 容器均 running/healthy；两个 `curl` 输出 `200`（首页由镜像内 nginx 提供，未挂宿主机 `web/dist`）。

**Step 5: 收尾**

Run: `cd deploy && docker compose down`（保留卷，验证用）。
Commit:
```bash
git add deploy/Dockerfile.web deploy/docker-compose.yml
git commit -m "feat(deploy): 前端进镜像——多阶段 Dockerfile.web，compose 不再依赖宿主机 web/dist"
```

---

## Task 2: 一键部署脚本 `deploy/deploy.sh`（替换 `deploy_remote.sh`）

**Files:**
- Create: `deploy/deploy.sh`
- Delete: `deploy/deploy_remote.sh`

**Step 1: 新建 `deploy/deploy.sh`**

```bash
#!/usr/bin/env bash
# ============================================================
# Copilot-Lite 一键部署（服务器上执行，唯一部署入口）
#
#   bash deploy/deploy.sh            # 部署最新 main：拉码 → 构建 → 起容器 → 健康检查
#   bash deploy/deploy.sh rollback   # 回滚到上一版代码并重建
#
# 前置：服务器已装 Docker + docker compose 插件；仓库克隆在 $APP_DIR，
#       且 deploy/.env 已配置（参考 deploy/.env.example）。
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

log "4/4 ✗ 健康检查失败，回滚到 $PREV_SHA"
git reset --hard "$PREV_SHA"
compose up -d --build
fail "部署失败并已回滚。日志：cd $COMPOSE_DIR && docker compose logs backend"
```

**Step 2: 赋可执行权限并删除旧脚本**

```bash
chmod +x deploy/deploy.sh
git rm deploy/deploy_remote.sh
```

**Step 3: 语法检查**

Run: `bash -n deploy/deploy.sh && echo OK`
Expected: `OK`（无输出错误）。

**Step 4: 提交**

```bash
git add deploy/deploy.sh
git commit -m "feat(deploy): 新增一键部署脚本 deploy.sh，退役 deploy_remote.sh

服务器只需 git pull + docker compose，不再上传 dist 产物；含 ff-only 拉码、
健康检查与失败自动回滚（reset --hard 上一版使回滚“粘住”）。"
```

---

## Task 3: `Jenkinsfile` — Deploy 改为 SSH 执行 `deploy.sh`

**Files:**
- Modify: `Jenkinsfile`（Deploy 阶段 + 顶部注释）

**Step 1: 替换 Deploy 阶段 steps 中的三条 `bat`**

把：
```groovy
// 1) 服务器上准备产物接收目录
bat "ssh -i \"%SSH_KEY%\" -o StrictHostKeyChecking=accept-new ${params.DEPLOY_SERVER} \"mkdir -p /opt/copilot-lite/web/dist.new\""
// 2) 上传前端产物
bat "scp -i \"%SSH_KEY%\" -o StrictHostKeyChecking=accept-new -r web\\dist\\* ${params.DEPLOY_SERVER}:/opt/copilot-lite/web/dist.new/"
// 3) 远端执行部署脚本（拉码 + 重建容器 + 健康检查 + 失败回滚）
bat "ssh -i \"%SSH_KEY%\" -o StrictHostKeyChecking=accept-new ${params.DEPLOY_SERVER} \"bash /opt/copilot-lite/deploy/deploy_remote.sh\""
```
改为：
```groovy
// 服务器上执行一键部署（拉码 + 构建镜像 + 重建容器 + 健康检查 + 失败回滚）
// 不再上传任何产物：前端已进镜像（deploy/Dockerfile.web）
bat "ssh -i \"%SSH_KEY%\" -o StrictHostKeyChecking=accept-new ${params.DEPLOY_SERVER} \"bash /opt/copilot-lite/deploy/deploy.sh\""
```

**Step 2: 更新顶部注释**

把 Deploy 相关说明中的「上传前端产物 / deploy_remote.sh」改为「SSH 执行 `deploy.sh`」。

**Step 3: 验证（无本地 Jenkins 时的人工核验）**

Run:
```bash
grep -n "deploy" Jenkinsfile
```
Expected: 不再出现 `dist.new` / `deploy_remote.sh` / `scp`；出现 `deploy/deploy.sh`。

**Step 4: 提交**

```bash
git add Jenkinsfile
git commit -m "ci(jenkins): Deploy 阶段改为 SSH 执行 deploy.sh——不再上传前端产物"
```

---

## Task 4: 文档同步（DEPLOY.md / JENKINS_README.md / README.md）

**Files:**
- Modify: `deploy/DEPLOY.md`
- Modify: `deploy/JENKINS_README.md`
- Modify: `README.md`（如仍描述旧流程）

**Step 1: `DEPLOY.md`**
- 删除「3.3 构建前端静态资源（服务器装 Node + `npm run build`）」整节。
- 把「3.4 一键启动」改为：
  ```bash
  cd /opt/copilot-lite && bash deploy/deploy.sh
  ```
  并说明：脚本 = 拉码(ff-only) → `docker compose up -d --build` → 健康检查 → 失败回滚；前端已进镜像，无需 Node。
- 「3.6 启用 HTTPS」：把「改 compose 挂载 + 放开 nginx 注释」改为「编辑 `deploy/nginx.conf` 的 443 段与 80 跳转 → `docker compose up -d --build web`（配置已进镜像，需重建）」。
- 「常见问题」/「上线自检清单」中涉 `deploy_remote.sh`、`dist.new` 的措辞同步替换。

**Step 2: `JENKINS_README.md`**
- Deploy/Phase 2 描述改为「SSH 执行 `/opt/copilot-lite/deploy/deploy.sh`（默认关闭）」，删除产物上传相关步骤。

**Step 3: 验证文档不再提旧流程**

Run:
```bash
grep -rn "dist.new\|deploy_remote.sh\|npm run build" deploy/DEPLOY.md deploy/JENKINS_README.md
```
Expected: 无输出（除 `npm run build` 若在 CI 段落中属正常——按实际保留）。

**Step 4: 提交**

```bash
git add deploy/DEPLOY.md deploy/JENKINS_README.md README.md
git commit -m "docs(deploy): 部署文档同步一键脚本——删除产物上传/服务器构建前端步骤"
```

---

## Task 5: 全量回归与收尾

**Step 1: 后端 + 前端回归**

Run:
```bash
cd backend && .venv/Scripts/ruff.exe check . && .venv/Scripts/python.exe -m pytest -q
cd ../web && npm test && npm run build
```
Expected: ruff 通过；pytest 全过且覆盖率 ≥80%；vitest 全过；`tsc -b` + `vite build` 零错误。

**Step 2: 合成验证（本机 Docker）**

Run:
```bash
cd deploy && docker compose up -d --build && sleep 8
curl -fsS -o /dev/null -w "health=%{http_code}\n" http://127.0.0.1/api/v1/health
curl -fsS -o /dev/null -w "web=%{http_code}\n" http://127.0.0.1/
docker compose down
```
Expected: `health=200`、`web=200`。

**Step 3: 汇总提交**（若前几步已分别提交，则此步仅核对 `git log`）

Run: `git log --oneline -6`
Expected: 见 Task 1–4 的 4 个提交（或按仓库习惯合并为更少提交，但每次一个改动）。

---

## 验收标准（对应设计 §9）

1. `bash deploy/deploy.sh` 一条命令在服务器起全栈；无需 Node / `web/dist`。
2. `web` 镜像内含前端产物与 nginx 配置。
3. `Jenkinsfile` Deploy 默认关闭且只调用 `deploy.sh`；无 `dist.new` / `scp`。
4. `deploy_remote.sh` 已删除。
5. 文档与实现一致；后端/前端回归全绿。
