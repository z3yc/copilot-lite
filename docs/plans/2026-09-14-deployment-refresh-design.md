# 部署方式刷新设计（Docker 自包含 + 一键脚本）

- 日期：2026-09-14
- 状态：已确认（brainstorming 通过）
- 关联：AGENTS §11/§19、`deploy/DEPLOY.md`、`Jenkinsfile`、`GIT_WORKFLOW.md`
- 方向：选项 **D = A（Docker 自包含）+ B（收敛为一键脚本，Jenkins 只做 CI）**

## 1. 背景与问题

当前存在两条半重叠的部署链路：

| 链路 | 入口 | 行为 |
|---|---|---|
| Docker（单机 compose） | 服务器 `deploy/` | 起 postgres/qdrant/redis/backend/web；web=nginx 挂**宿主机 `../web/dist`**；仅 80，443 需手工开注释 |
| 服务器（Jenkins 驱动） | 本机 Jenkins | 轮询 Gitee `*/main` → 后端 CI + 前端 build/test → 归档 → SSH 上传 `dist.new` → `deploy_remote.sh`（拉码 + 原子替换 dist + `compose up -d --build` + 健康检查 + 回滚） |

痛点：
1. **Docker 不自包含**：前端不进镜像，web 容器绑宿主 `web/dist` → 服务器必须装 Node 并 `npm run build`，或依赖 CI 上传产物；`docker compose up -d --build` 单命令跑不起来。
2. **职责重叠**：`deploy_remote.sh` 既拉码、替换产物，又 `compose up --build`，与纯 Docker 部署重复。
3. **触发分支不一致**：Jenkins 只轮询 `main`，而 CI 已覆盖 `develop`。
4. **Redis 预留着但后端未实际使用**（内存限流/预算），占 128M（2C4G 偏紧）——本轮不动，仅文档标注。
5. **HTTPS 靠手工注释**——本轮不自动化，仅随镜像化调整文档操作方式。

## 2. 目标 / 非目标

**目标**
- Docker **自包含**：前端进镜像；服务器只需 Docker + git，无需 Node/`web/dist`。
- 部署**收敛为一条命令**：`bash deploy/deploy.sh`（拉码 → 构建 → 起容器 → 健康检查 → 失败回滚）。
- **Jenkins 只做 CI**；Deploy 阶段改为可选、默认关闭、复用同一 `deploy.sh`（不再上传产物）。

**非目标（本轮不做）**
- 自动 HTTPS / 证书签发与续期（保持手工，更新文档操作步骤）。
- 移除 Redis、多环境/多租户、监控告警。

## 3. 方案

### 3.1 前端进镜像（P1：独立多阶段 `deploy/Dockerfile.web`）
```dockerfile
FROM node:20-alpine AS build
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build                 # = tsc -b && vite build

FROM nginx:1.27-alpine
COPY --from=build /web/dist /usr/share/nginx/html
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
```
- 构建上下文 = 仓库根（复用既有 `.dockerignore` 排除 `web/node_modules`、`web/dist`、`.venv` 等）。
- 前端无构建期 env 依赖（已确认无 `import.meta.env`）。

### 3.2 `deploy/docker-compose.yml`
- `web` 服务：`image: nginx` + 挂 `../web/dist`、`./nginx.conf` → 改为
  `build: { context: .., dockerfile: deploy/Dockerfile.web }`；移除两个占位挂载（配置与产物均在镜像内）。
- 其余服务（postgres/qdrant/redis/backend、卷、健康检查、仅暴露 80）**不变**。

### 3.3 `deploy/deploy.sh`（服务器唯一部署入口）
`set -euo pipefail`，流程：
1. 记录 `PREV_SHA=$(git rev-parse HEAD)`
2. `git fetch origin main && git merge --ff-only origin/main`（分叉即中止，不强覆服务器本地改动）
3. `docker compose up -d --build`
4. 健康检查轮询 `http://127.0.0.1/api/v1/health`（≤120s）
5. 失败：`git checkout "$PREV_SHA"` + `docker compose up -d --build` 回滚，退出非 0
- 子命令 `bash deploy/deploy.sh rollback`：回滚到上一版代码并重建。

### 3.4 退役 `deploy/deploy_remote.sh`
由 `deploy.sh` 取代（删除），避免两套真相源。

### 3.5 `Jenkinsfile`
- Deploy 阶段：移除 `mkdir dist.new` 与 `scp` 上传；改为 `ssh … "bash /opt/copilot-lite/deploy/deploy.sh"`；仍由参数 `DEPLOY_ENABLED`/`DEPLOY_SERVER` 控制，**默认关闭**。
- Checkout + Backend CI + Frontend CI + Archive + 飞书通知**保留**（Archive 仅留档，便于排查）。

### 3.6 文档同步
- `deploy/DEPLOY.md`：删除「服务器装 Node 构建前端」「`dist.new` 上传」步骤；部署改为 `bash deploy/deploy.sh` 一条命令；TLS 步骤改为「改 `deploy/nginx.conf` 后重建 web 镜像」。
- `deploy/JENKINS_README.md`：Deploy 阶段描述改为「SSH 执行 `deploy.sh`（默认关）」。
- `README.md`：部署相关一句话同步（如需）。

## 4. 时序

```
开发者 push → Gitee
  ├─ GitHub Actions（main/develop 的 PR/push）→ 后端 lint+test、前端 build+test
  └─ Jenkins 轮询 Gitee main → 同上 CI →（可选）SSH 执行 deploy.sh

服务器：bash deploy/deploy.sh
  → git fetch/ff-only → docker compose up -d --build → health → ✅ 或 回滚
```

## 5. 错误处理与回滚

| 失败点 | 处理 |
|---|---|
| 远端分叉 / 本地有改动 | `merge --ff-only` 失败即中止（不 reset --hard） |
| 镜像构建失败 | 退出非 0；不重启旧容器（`up --build` 失败不替换运行中容器） |
| 健康检查失败/超时 | `git reset --hard PREV_SHA` + 重建，退出非 0（部署机为 deploy-only，无本地改动；重置使回滚“粘住”，不会被下次部署自动覆盖） |
| 手工回滚 | `bash deploy/deploy.sh rollback` |

## 6. 安全

- 密钥仍在 `deploy/.env`（gitignore，不入库、不进镜像）。
- 后端镜像非 root（`USER app`）；web 用官方 nginx 镜像。
- 仅对外暴露 80（443 按需）；backend/postgres/qdrant/redis 仅内网。
- `.dockerignore` 保证 `web/node_modules`、`backend/.venv`、私有目录不进构建上下文。

## 7. 验证计划

- `docker compose -f deploy/docker-compose.yml build web`（本机 Docker 29.7.2 可用）
- `docker compose up -d` 全栈 → `curl 127.0.0.1/api/v1/health` 与 `/` 均 200
- `bash -n deploy/deploy.sh` 语法检查
- 后端 `pytest` + `ruff`、前端 `vitest` + `build` 回归（无代码改动，应全绿）

## 8. 风险与回退

- web 镜像首次构建需联网 `npm ci`（服务器需可达 npm 源）。
- TLS 配置 baked 进镜像，启用/修改需重建 web 镜像（文档注明）。
- 回退：全部为仓库文件改动，`git revert`/切回上一提交即可恢复旧部署方式。

## 9. 验收标准

1. 服务器只需 Docker：`git pull` + `bash deploy/deploy.sh` 一条命令起全栈，无需 Node/`web/dist`。
2. `web` 镜像内含前端产物与 nginx 配置，无宿主机产物依赖。
3. Jenkins Deploy 默认关闭，且仅调用 `deploy.sh`（不传产物）。
4. `deploy_remote.sh` 已移除，部署逻辑单一。
5. 文档与实现一致；回归测试全绿。
