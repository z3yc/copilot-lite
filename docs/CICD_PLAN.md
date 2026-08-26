# Copilot-Lite 自动化 CI/CD 方案记录（Jenkins 自建）

> 状态：✅ 已确认 · 实施进行中（Phase 1 本机跑通 CI，Phase 2 待服务器）
> 关联文件：`Jenkinsfile` / `deploy/deploy_remote.sh` / `deploy/JENKINS_README.md`

---

## 1. 目标

为 Copilot-Lite 建立 **CI + CD 完整闭环**：

- **CI**：代码推送到 `main` 后自动执行 后端检查（ruff + pytest 覆盖率≥80%）→ 前端构建（类型检查 + vite build）→ 前端单测（vitest）→ 产物归档；
- **CD**：自动部署到云服务器（本期无服务器，**部署阶段写好但默认跳过**，配置参数后即启用）。

## 2. 需求确认记录（逐题确认结论）

| 维度 | 结论 | 备注 |
|---|---|---|
| 范围 | CI + CD 完整闭环 | 含失败回滚（服务器脚本内） |
| 流水线平台 | **自建 Jenkins** | 不用 GitHub Actions / Gitee Go |
| Jenkins 位置 | **本机 Windows**（Java 17 原生安装） | 不依赖 Docker Desktop（daemon 未运行） |
| 触发方式 | **轮询 Gitee**，每天一次（`H 9 * * *`，约 09:00） | 无需公网穿透；本机需保持开机；曾为每 2 分钟，按需改为每日 |
| 部署目标 | 尚无云服务器 → 本期跳过 | deploy 阶段为**后门**：配了参数才执行 |
| 结果通知 | **飞书应用私聊消息**（app_id/app_secret） | 成功/失败卡片（构建号/结果/分支/耗时），直接私聊用户 |
| 分支策略 | 监听 `main` push；支持手动"立即构建"任意分支 | |

### 技术事实（已核实）

- 后端测试全部 mock：SQLite（`sqlite+aiosqlite`）、假 LLM、假 Qdrant、禁用记忆抽取与 rerank —— CI 无需任何外部服务 / API key / 模型下载；
- 覆盖率门槛内置于 `backend/pyproject.toml`：`addopts = "--cov=app --cov-report=term-missing --cov-fail-under=80"`；
- 前端 `npm run build` = `tsc -b && vite build`（含类型检查）；`npm test` = `vitest run`；
- 生产部署编排：`deploy/docker-compose.yml`（postgres / qdrant / redis / backend / nginx），nginx 只读挂载 `../web/dist`；
- 仓库远程只有 Gitee（`https://gitee.com/zyc66x/copilot-lite.git`）；
- 本机环境：Java 17（Temurin）✅ / Node 22（nvm4w）✅ / uv ✅ / Git ✅ / OpenSSH ✅ / Docker CLI 有但 daemon 未运行；
- 后端 `requires-python = ">=3.12,<3.13"`，本机 Python 3.14 —— 由 `uv sync` 自动下载管理 Python 3.12，无需手工处理。

## 3. 整体架构

```
[Gitee 仓库] --每日轮询 09:00--> [Jenkins（本机 Windows / Java 17 / 服务自启）]
                                   │
                        Jenkinsfile 声明式流水线
                                   │
   ┌───────────────┬───────────────┬───────────────┬──────────────┐
   │ Checkout      │ Backend CI    │ Frontend CI   │ Archive      │
   │ git 拉 main   │ uv sync       │ npm ci        │ 归档 web/dist│
   │（Gitee 令牌） │ ruff check    │ npm run build │ + 测试报告    │
   │               │ pytest(≥80%)  │ npm test      │              │
   └───────────────┴───────────────┴───────────────┴──────┬───────┘
                                                          │
                                        [Deploy 阶段（后门）]
                         未配置参数 → 打印"跳过"（本期默认路径）
                         已配置 → SSH 上服务器执行 deploy_remote.sh：
                              git pull → 替换 web/dist → docker compose up -d --build
                              → /api/v1/health 健康检查 → 失败自动回滚
                                                          │
                                                   [飞书应用私聊通知]
                                              结果卡片（成功/失败/耗时）
```

## 4. 交付物清单

| 文件 | 职责 | 状态 |
|---|---|---|
| `Jenkinsfile` | 声明式流水线：Checkout / Backend CI / Frontend CI / Archive / Deploy（后门）+ 飞书通知 | 本期交付 |
| `deploy/deploy_remote.sh` | 服务器端部署：拉码 → 替换产物 → 重建容器 → 健康检查 → 失败回滚 | 本期交付（不执行） |
| `deploy/JENKINS_README.md` | 本机 Jenkins 安装 / 凭据配置 / 排障手册 | 本期交付 |
| `docs/CICD_PLAN.md` | 本方案记录 + 实施清单 | 本期交付 |

## 5. 凭据清单

| # | 凭据 | 用途 | 类型 | 存放 |
|---|---|---|---|---|
| 1 | **Gitee 私人访问令牌**（只读即可） | 轮询 + 拉取代码 | Username with password | Jenkins Credentials（id: `gitee-token`）✅ 已配置 |
| 2 | **飞书开放平台应用 app_id + app_secret** | 构建结果私聊通知（接收人 open_id 在 Jenkinsfile 的 `FEISHU_OPEN_ID`） | Secret text ×2 | Jenkins Credentials（id: `feishu-app-id` / `feishu-app-secret`）✅ 已配置 |
| 3 | **云服务器 IP + SSH 私钥**（Phase 2） | 自动部署 | SSH Username with private key | Jenkins Credentials（id: `deploy-ssh-key`） |

> 安全：令牌只读、存 Jenkins 凭据，绝不写入代码库 / Jenkinsfile。

## 6. 实施清单（Checklist）

### Phase 1 —— 本机跑通 CI（✅ 已完成，2026-08-26 实测通过）

- [x] 1. 安装 Jenkins 2.516.3（war + Java 17，端口 8080；JENKINS_HOME 在项目内 `.jenkins-home/`，已 gitignore）
- [x] 2. Jenkins 初始化：解锁 → 创建管理员（admin）→ 安装建议插件（Pipeline / Git / Credentials Binding 等）
- [x] 3. 配置凭据：`gitee-token`（Gitee 私人令牌）、`feishu-app-id` + `feishu-app-secret`（飞书应用，私聊通知）
- [x] 4. 新建 Pipeline Job `copilot-lite`：SCM 指向仓库根 `Jenkinsfile`（凭据 `gitee-token`，分支 `*/main`）
- [x] 5. 提交 `Jenkinsfile` 到 main，手动构建验证全绿（构建 #1 SUCCESS，2.2 min）
- [x] 6. 轮询触发器生效（初为 `H/2 * * * *`，后按需改为每日 `H 9 * * *`）：push 后自动构建（构建 #2 由轮询自动触发）
- [x] 7. 飞书通知验证通过：私聊消息送达（`code:0`，消息内容含构建号/结果/分支/耗时）
- [x] 8. 回归检查：后端 ruff 全绿 + pytest 80 用例（覆盖率 81%+）、前端 build + vitest 22 用例全绿、`web/dist` 归档可见

> ⚠️ 踩坑记录（详见 `deploy/JENKINS_README.md` 排障表）：① Job 名含中文导致 bat 步骤挂死（须用 ASCII 名）；② Jenkinsfile 中文/emoji 字面量在 GBK 环境损坏导致飞书 payload 非法（消息保持纯 ASCII）；③ Jenkins 2.5xx API POST 需要 form body；④ API 认证须用 API Token（登录密码无效）。

### Phase 2 —— 接入自动部署（服务器到位后，约 30 分钟）

- [ ] 1. 服务器按 `deploy/DEPLOY.md` 初始化（Docker + 克隆仓库到 `/opt/copilot-lite`）
- [ ] 2. 生成 SSH 密钥对：公钥放服务器 `~/.ssh/authorized_keys`，私钥存 Jenkins（`deploy-ssh-key`）
- [ ] 3. Job 参数：`DEPLOY_ENABLED=true`，`DEPLOY_SERVER=user@服务器IP`
- [ ] 4. 端到端验证：push → CI 通过 → 自动部署 → 健康检查通过 → 飞书收到部署成功通知
- [ ] 5. 演练回滚：手动执行 `bash deploy_remote.sh rollback` 验证

## 7. 决策记录（ADR 摘要）

| 决策 | 选择 | 理由 |
|---|---|---|
| 平台 | 自建 Jenkins | 用户明确要求；自托管是面试加分项；不依赖第三方免费额度 |
| Jenkins 载体 | 本机 Windows + Java 原生 | Docker daemon 未运行；Java 17 已就绪；原生更省内存 |
| 触发 | 轮询 Gitee（每日 `H 9 * * *`） | 本机在 NAT 后无法收 WebHook；轮询零成本、可靠 |
| 部署产物策略 | 前端在 Jenkins 构建后上传；后端在服务器 docker build | 2C4G 服务器跑 vite build 易 OOM；服务器构建后端可复用清华镜像与缓存 |
| 通知 | 飞书开放平台应用（私聊消息） | 用户提供 app_id/app_secret；直接私聊用户，无需群机器人；实现只需 curl |
| Job 命名 | ASCII（`copilot-lite`） | 中文 Job 名 → 工作区路径含非 ASCII → Windows bat 步骤挂死（实测踩坑） |
| 回滚 | `deploy_remote.sh` 保留 `.prev` 产物 + 健康检查失败自动恢复 | 轻量、无额外组件 |

## 8. 风险与注意

| 风险 | 影响 | 缓解 |
|---|---|---|
| 本机需开机 | 关机期间 Gitee 提交不触发构建 | 轮询固有约束，可接受；Jenkins 装为服务开机自启 |
| 轮询延迟 | 每日仅触发一次，push 后最长 ~24h 才构建 | 需要更快反馈时调 `pollSCM`（如 `H/30 * * * *`）或改 WebHook |
| Windows 构建 vs Linux 生产环境差异 | 后端行为可能不一致 | 部署以服务器 `docker compose` 为准；前端产物 + 测试已覆盖大部分风险 |
| Jenkins Windows 服务 PATH 不含用户级目录 | uv/node 找不到 | Jenkinsfile 已显式补齐 PATH（见文件头注释） |
| Gitee 令牌泄露 | 仓库被恶意操作 | 只读令牌 + 存凭据 + 不明文入库 |
| `web/dist.new` 上传中断 | 部署产物不完整 | deploy_remote.sh 校验 `index.html` 存在后才原子替换 |
