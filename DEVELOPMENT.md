# 本地开发环境指南

> 面向**其他开发者**：从 clone 到能改代码、能跑测试，约 10 分钟。
> 跨平台（Windows / macOS / Linux），需要本地 **PostgreSQL**（本仓库只用 PG，不用 SQLite/MySQL），**不需要 Docker**。
>
> - 云端部署（2C4G 服务器 + HTTPS + 回滚）→ [`deploy/DEPLOY.md`](deploy/DEPLOY.md)
> - Docker 全栈跑法（不装 Python/Node，最接近生产形态）→ 本文[附录 A](#附录-adocker-全栈可选)
> - 分支 / 提交 / CR 规范 → [`AGENTS.md`](AGENTS.md)、[`GIT_WORKFLOW.md`](GIT_WORKFLOW.md)

---

## 0. TL;DR（复制即用）

```bash
git clone https://gitee.com/zyc66x/copilot-lite.git && cd copilot-lite

# 终端 1：后端 → http://127.0.0.1:8000/docs
cd backend && uv sync && uv run uvicorn app.main:app --reload

# 终端 2：前端 → http://localhost:5173
cd web && npm ci && npm run dev
```

**只要本机有 PostgreSQL 就能跑**：PG + 嵌入式 Qdrant + 本地嵌入模型，不需要 Docker；
首次建库 `createdb copilot`（或导入初始化 SQL，见 [§2.3](#23-数据库只支持-postgresql)）；
本地模式建表由代码自动完成，**不需要跑 `alembic upgrade head`**（原因见 [§2.4](#24-建表与迁移新人第一大坑)）。

> 首次启动会在后台下载模型（嵌入 ~50–100MB + 重排 ~1.1GB），不阻塞服务；想跳过见 [§6](#6-模型下载与缓存)。
>
> Windows 也可一键：`powershell -ExecutionPolicy Bypass -File scripts\dev_start.ps1`
> （装依赖 → 建表 → 起前后端 → 开浏览器；仅 Windows，其他平台用上面手动命令）。

---

## 1. 前置环境

| 依赖 | 要求 | 说明 |
|---|---|---|
| Python | **3.12.x（严格）** | `backend/pyproject.toml` 为 `requires-python = ">=3.12,<3.13"`；3.13+ 会被拒 |
| [uv](https://docs.astral.sh/uv/) | 较新版本 | 依赖与环境管理；`uv sync` 会自动准备 3.12 解释器 |
| Node.js | **≥ 20**（CI 基准 20） | 前端构建与测试 |
| Git | — | — |
| **PostgreSQL** | **17.x（必需）** | 本地 / 测试 / 生产统一 PG（不再支持 SQLite）；`createdb copilot` |
| Docker | 可选 | 仅[附录 A](#附录-adocker-全栈可选)需要 |

**不需要**：Qdrant 服务、Redis —— 本地都有零依赖替代（见 [§2.3](#23-数据库只支持-postgresql)）。

```bash
uv --version && node -v && git --version   # Docker 可选：docker --version
```

> ⚠️ 若本机已有 `backend/.venv` 但解释器不是 3.12（例如 3.14），`uv sync` 会因版本不匹配失败。
> 处理：删掉那个 venv 再同步 ——
> Windows `Remove-Item -Recurse -Force backend\.venv` / macOS·Linux `rm -rf backend/.venv`，
> 或显式指定 `uv sync --python 3.12`。

---

## 2. 后端

### 2.1 启动

```bash
cd backend
uv sync                               # 安装依赖（首次会下载 3.12 解释器 + 依赖）
uv run uvicorn app.main:app --reload  # 热重载，端口 8000
```

Windows 上也可用封装脚本（**强制 venv + 端口占用检查 + 启动自证**）：

```powershell
# 仓库根目录：自动用 backend\.venv\Scripts\python.exe 启动，打印解释器路径与 kb_tool.py 时间
powershell -ExecutionPolicy Bypass -File scripts\dev_backend.ps1
powershell -ExecutionPolicy Bypass -File scripts\dev_backend.ps1 -NoReload   # 关热重载（排查/压测）
powershell -ExecutionPolicy Bypass -File scripts\dev_backend.ps1 -Port 8001
```

> 踩过的坑：直接用系统 Python（`WindowsApps\...\python.exe -m uvicorn`）且不带 `--reload`
> 启动，会导致「**改了代码完全没生效**」，排查半天才发现在跑旧代码/错解释器。
> 自查方法：进程启动时间必须**晚于**所改文件的 mtime；端口被占用时先杀进程再重启。

验证：

```bash
curl http://127.0.0.1:8000/api/v1/health        # → {"status":"ok",...}
curl http://127.0.0.1:8000/api/v1/health/ready  # 就绪探针（连 DB/向量库）
```

接口文档：<http://127.0.0.1:8000/docs>

### 2.2 配置文件（可以跳过）

后端只读 **`backend/.env`**（`app/core/config.py` 的 `env_file` 指向它）——
**不是** `deploy/.env`（那是 Docker Compose 专用的）。

```bash
cd backend && cp .env.example .env   # 按需修改；不建也能跑
```

不建 `.env` 时的默认值（对开发足够）：

| 配置 | 默认值 | 说明 |
|---|---|---|
| `RUN_MODE` | `local` | 本地模式：自动建表，允许使用内置开发 `SECRET_KEY` |
| `DATABASE_URL` | `postgresql+asyncpg://postgres:root@localhost:5432/copilot` | **非 PG 方言会在启动自检被直接拒绝**（`config.py`） |
| `SECRET_KEY` | 内置开发值 | **仅 `local` 可用**；`RUN_MODE=cloud` 时不改会拒绝启动（安全自检） |
| `DEEPSEEK_API_KEY` | 空 | 不影响启动：普通用户在前端各自配置模型（见 [§5](#5-首次使用注册--配模型--问答)） |
| `SUPER_ADMIN_USERNAME` / `SUPER_ADMIN_PASSWORD` | `demo` / 空 | 密码非空才会在启动时创建/提升超管（`role=admin`），见 [§5](#5-首次使用注册--配模型--问答) |

`.env` 已被 gitignore，`.env.example` 是入库模板。

### 2.3 数据库只支持 PostgreSQL

本仓库**统一 PostgreSQL**（本地 / 测试 / 生产同构），不引入 SQLite / MySQL ——
`config.py` 的启动自检会拒绍非 `postgresql://` 的 `DATABASE_URL`。

```bash
createdb copilot   # 首次建库；或用初始化 SQL（见下）
# DATABASE_URL 默认已指向 postgresql+asyncpg://postgres:root@localhost:5432/copilot
```

若用户名/口令不同，改 `backend/.env` 的 `DATABASE_URL`（两份 `.env.example` 都有模板）。

> ⚠️ 测试库不用手工建：`conftest.py` 会自动创建 `copilot_test`（可用 `TEST_DATABASE_URL` 覆盖）。

**向量库仍零依赖**：`QDRANT_URL` 保持默认 `http://localhost:6333` 时，代码走**嵌入式 Qdrant**
（`QDRANT_PATH=./qdrant_data`，文件模式，无需安装 Qdrant 服务）；
只有设成别的地址（如 `http://qdrant:6333`）才连远程服务。

> ⚠️ 嵌入式 Qdrant 是文件锁模式：**同一份 `qdrant_data/` 不能被两个后端进程同时打开**。
> 需要多实例/多 worker 时，用 Docker 起 Qdrant 并配置 `QDRANT_URL`。

> 💡 想直接建库（不跑 ORM/迁移）：仓库已备好幂等初始化 SQL（PostgreSQL）——
> 见 [`deploy/sql/README.md`](deploy/sql/README.md)。

### 2.4 建表与迁移（新人第一大坑）

| 模式 | 建表方式 |
|---|---|
| `RUN_MODE=local`（开发默认） | 启动时 `Base.metadata.create_all`（`app/main.py`）→ **不需要 `alembic upgrade head`** |
| `RUN_MODE=cloud`（Docker / 云端） | `alembic upgrade head`（backend 容器启动命令已自动执行） |

**后果**：改了 `app/models/` 里的 ORM 模型，本地**不会自动生效** ——
`create_all` 只补缺失的表，**不会 ALTER 已有表**。处理：

- 最快：`dropdb copilot && createdb copilot`，重启后端（数据会丢，仅开发库）；
- 保留数据：手工 `ALTER TABLE`，或把 `RUN_MODE=cloud` 临时打开让启动走 `alembic upgrade head`；
- **若你这次改动写了 Alembic 迁移**（`backend/alembic/versions/`）：用**独立空库**验证，例如
  `createdb copilot_mig && DATABASE_URL=postgresql+asyncpg://postgres:root@localhost:5432/copilot_mig uv run alembic upgrade head`
  （不要在已被 `create_all` 建过表的开发库上直接跑迁移，会因表已存在而失败），见 [§7](#7-开发闭环提交前必须全绿)。

### 2.5 建议关掉的后台任务

开发时这些后台任务会消耗 token 或干扰调试，按需写进 `backend/.env`：

```
MEMORY_EXTRACT_ENABLED=false    # 会话结束后台提取长期记忆
SUMMARY_COMPRESS_ENABLED=false  # 长对话摘要压缩
EMBEDDING_PREWARM=false         # 启动即预热嵌入/重排模型
```

---

## 3. 前端

```bash
cd web
npm ci         # 按 package-lock.json 安装（与 CI 一致；首次约 1–2 分钟）
npm run dev    # http://localhost:5173
```

- `vite.config.ts` 已把 `/api` 代理到 `http://127.0.0.1:8000` → **本地无需配置 CORS**；
- 后端没起时页面能打开，但接口会报错（先起后端）；
- 换端口：`npm run dev -- --port 5174`，此时要同步后端 `CORS_ORIGINS`（默认只放行 5173）。

---

## 4. CLI（可选）

```bash
cd cli && uv sync
uv run copilot login --register    # 登录（--register 顺带注册）；凭据存 ~/.copilot/credentials.json
uv run copilot chat                # 交互式对话
uv run copilot ask "今天有什么待办"
uv run copilot todo list           # 待办：list / add / done / rm
uv run copilot logout
```

- 后端地址默认 `http://127.0.0.1:8000`，用环境变量 `COPILOT_API_URL` 覆盖；
- 令牌优先级：`COPILOT_TOKEN` 环境变量 > 凭据文件（`COPILOT_CREDENTIALS` 可改路径）。

---

## 5. 首次使用（注册 → 配模型 → 问答）

1. 打开 <http://localhost:5173> → **注册**（用户名 2–64 位，仅字母/数字/下划线；密码 ≥6 位）→ 登录；
2. **配置自己的模型 Key**：首次进入会有引导，之后可在「个人中心 → 模型设置」修改
   （Base URL / 模型 / API Key / 温度 / max_tokens）。Key 加密入库，接口只回掩码；
   > 环境变量 `DEEPSEEK_API_KEY` **只作为超级管理员账号的兜底**，普通用户不配置就调不通模型；
3. 上传一篇 Markdown / PDF 到知识库 → 等状态 `ready` → 提问并核对引用来源。

> 🔑 **超级管理员（demo）**：在 `backend/.env` 设置 `SUPER_ADMIN_USERNAME=demo` 与
> `SUPER_ADMIN_PASSWORD=<非空密码>` 后，后端启动时会自动创建（或提升同名账号为）
> `role=admin` 的超管，默认用户名 `demo`；**未配置密码则不创建**。超管是唯一能走环境变量
> `DEEPSEEK_API_KEY` 兜底调用模型的账号（普通用户须自配 Key），也可访问管理后台 `/admin`；
> 登录入口与普通用户相同（用户名 `demo` + 你设置的密码）。

---

## 6. 模型下载与缓存

首次启动会在**后台**预热模型（不阻塞服务；失败只记 WARNING，延迟到首次使用时重试）：

| 模型 | 体积 | 缓存位置 |
|---|---|---|
| 嵌入（fastembed BGE） | ~50–100MB | `backend/data/models`（`EMBEDDING_CACHE_DIR`） |
| 重排（bge-reranker-base） | ~1.1GB | 同上；仅 `RAG_RERANK_ENABLED=true` 时预热 |

- 代码内置 hf-mirror 镜像（用 `os.environ.setdefault`，**你自己的 `HF_ENDPOINT` 优先**）；
- 省流量 / 离线开发：`.env` 设 `RAG_RERANK_ENABLED=false`（跳过 1.1GB，检索退化为无精排的混合检索）
  或 `EMBEDDING_PREWARM=false`（延后到实际用到时再下）；
- `backend/data/` 已 gitignore，不会污染仓库。

---

## 7. 开发闭环（提交前必须全绿）

| 命令 | 内容 | 门槛 |
|---|---|---|
| `cd backend && uv run pytest` | 后端测试 | **覆盖率 < 80% 直接失败**（`--cov-fail-under=80` 写在 `pyproject.toml`） |
| `cd backend && uv run ruff check .` | 后端规范 | 必须全过（line-length=100） |
| `cd web && npm test` | 前端单测（vitest） | 全过 |
| `cd web && npm run build` | `tsc -b` 类型检查 + 构建 | 零类型错误 |

- **测试不触网、不下载模型，但需要一个真实 PostgreSQL**：`backend/tests/conftest.py` 会把
  `DATABASE_URL` 指向 `TEST_DATABASE_URL`（默认 `.../copilot_test`，**库不存在会自动创建**），
  每个用例前 `TRUNCATE` 全部表，并关闭全部后台任务（记忆提取 / 摘要压缩 / 预热等），
  LLM / 嵌入 / 重排全用 Fake；
- 新增 `asyncio.create_task` 类后台逻辑**必须**配 `settings` 开关，并在 conftest 中默认关闭（`AGENTS.md` §8）；
- 验证 **Alembic 迁移**：在独立空库上跑（`createdb copilot_mig` + 临时 `DATABASE_URL`），
  `uv run alembic upgrade head` 再看 `downgrade`；CI 已自动做这一步（干净 PG 上从零迁移）；
- 检索参数调优用 `backend/scripts/rag_eval.py`（recall@K / MRR），
  生成质量用 `backend/scripts/rag_eval_ragas.py`，golden 集在 `backend/eval/golden_set.json`。

---

## 8. 改代码须知

- **后端分层**：`api`（路由：只做参数校验 + 调 service）→ `service` → `core` → `infra`；
  禁止反向依赖，`core` 不引 FastAPI，跨模块只走对方 service（见 `AGENTS.md` §12）；
- **新增配置项要三件套**：`app/core/config.py` 字段 + `deploy/.env.example` + `backend/.env.example`，
  安全类配置加启动校验（§7）；
- **新增工具**：写一个函数 + 在 `ToolRegistry` 注册一行；副作用操作必须校验归属（§6）；
- **前端**：业务组件放对应页面目录、通用组件放 `components/common`；
  渲染 LLM 输出只能走 `web/src/utils/markdown.ts` 的 `renderMarkdown()`（内部已 `DOMPurify.sanitize`）；
- **删除一律软删除**（`deleted_at` / `deleted_by`），检索与列表默认过滤（§13）；
- 提交信息 / 分支命名见 `AGENTS.md` §3、§11，流程见 `GIT_WORKFLOW.md`；
  **禁止直接 push `main` / `develop`**，一律 PR + CI 全绿。

---

## 9. 常见问题

| 现象 | 原因 | 解决 |
|---|---|---|
| `uv sync` 报 Python 版本不匹配 | 已有 `backend/.venv` 是别的版本 | 删掉 `backend/.venv` 重新 `uv sync`，或 `uv sync --python 3.12` |
| `:8000` / `:5173` 被占用 | 上次进程没关干净 | Windows `netstat -ano \| findstr :8000`；mac/Linux `lsof -i:8000`（5173 同理） |
| 改了模型但表结构没变 | local 模式 `create_all` 不会 ALTER 已有表 | 见 [§2.4](#24-建表与迁移新人第一大坑)：删库重建 / 手工 ALTER / 用 PG 走迁移 |
| 向量检索报文件锁 / 数据不更新 | 嵌入式 Qdrant 被第二个进程占用 | 只留一个后端进程，或改用 Docker Qdrant 并设 `QDRANT_URL` |
| 模型下载慢或卡住 | 首次要下 ~1.1GB | 见 [§6](#6-模型下载与缓存)；可临时 `HF_ENDPOINT` 换镜像 |
| 对话报模型相关错误 | 该账号没配模型 Key | 个人中心 → 模型设置（[§5](#5-首次使用注册--配模型--问答)） |
| 前端接口 404 / 跨域 | 后端不在 8000，或改了前端端口 | 后端跑在 8000，或同步改 `vite.config.ts` 代理与 `CORS_ORIGINS` |
| `dev_start.ps1` 执行失败 | 该脚本仅 Windows | mac/Linux 用 [§0](#0-tldr复制即用) 手动命令；Windows 需 `-ExecutionPolicy Bypass` |
| Windows 下 `docker compose up` 报挂载错误 | base 文件的 certbot 挂载是 Linux 专用 | 叠加 `deploy/docker-compose.windows.yml`（[附录 A](#附录-adocker-全栈可选)） |
| pytest 覆盖率不达标 | 新增代码没测试 | 补用例；确无必要的分支加 `# pragma: no cover`（需理由） |

---

## 10. 停止与清理

| 目标 | 操作 |
|---|---|
| 停服务 | 各终端 `Ctrl+C` |
| 清本地业务数据 | `dropdb copilot && createdb copilot`（重启后自动重建空表） |
| 一键重建表结构 | 导入初始化 SQL：`psql -U postgres -d copilot -f deploy/sql/init_postgres.sql`（幂等，见 [`deploy/sql/README.md`](deploy/sql/README.md)） |
| 清向量数据 | `rm -rf backend/qdrant_data`（根目录 `qdrant_data/` 同理，取决于你在哪启动后端） |
| 清模型缓存 | `rm -rf backend/data/models`（下次启动重新下载） |
| Docker 全栈 | `cd deploy && docker compose down` —— **别加 `-v`**，会连数据卷与模型卷一起删 |

> Windows 把 `rm -rf` / `rm` 换成 `Remove-Item -Recurse -Force` / `Remove-Item`。

---

## 附录 A：Docker 全栈（可选）

**适用**：不想装 Python / Node，或想验证接近生产的形态
（PostgreSQL + Qdrant 服务 + Redis + Nginx）。
**不适用**：日常改代码 —— 改完要重建镜像，比 `--reload` 慢得多。

```bash
cd deploy
cp .env.example .env      # 模板是 RUN_MODE=cloud
```

`.env` 必填项（缺任一项 compose 直接拒绝启动）：

| 变量 | 说明 |
|---|---|
| `POSTGRES_PASSWORD` | 强口令，且必须与 `DATABASE_URL` 里的口令一致 |
| `SECRET_KEY` | 强随机值，生成：`python -c "import secrets;print(secrets.token_urlsafe(48))"`；**cloud 模式沿用默认值会拒绝启动** |
| `QDRANT_API_KEY` | 强随机值（compose 中 Qdrant 开启了认证） |
| `REDIS_PASSWORD` | 强口令，且必须与 `REDIS_URL` 一致 |

```bash
docker compose up -d --build     # 首次构建 3–8 分钟（uv sync + npm ci）
docker compose ps                # 期望全部 running / healthy
curl http://localhost/api/v1/health
```

浏览器：<http://localhost/>

- 建表由 backend 容器启动命令里的 `alembic upgrade head` 完成；
- **不要用 `deploy/deploy.sh`**：那是云端脚本（会在服务器上 `git pull` `main` 并重建、带回滚）；
- 停止：`docker compose down`（**别加 `-v`**，会删掉 `pgdata` / `qdrantdata` / `models` 卷，模型要重下）。

### 🪟 Windows：必须叠加 windows 补丁（本机实测）

`deploy/docker-compose.yml` 的 web 服务挂载了 Linux 专用 certbot webroot `/var/www/certbot`，
Windows 上无法创建（实测 `docker run -v /var/www/certbot:/x alpine ls /x`
→ `ls: X:/: No such file or directory`），直接 `docker compose up` 会失败。

仓库已备好补丁 `deploy/docker-compose.windows.yml`，**显式叠加**即可
（它不会被自动加载，因此不影响 Linux / 云端）：

```bash
cd deploy
docker compose -f docker-compose.yml -f docker-compose.windows.yml up -d --build
```

补丁做两件事：移除 certbot 挂载（本地不走 ACME）；把发布端口 80 改为 8080
（规避 http.sys / IIS 占用）。

- 访问 <http://localhost:8080/>（`curl http://localhost:8080/api/v1/health`）；
- 停止同样要带两个 `-f`：
  `docker compose -f docker-compose.yml -f docker-compose.windows.yml down`；
- 补丁里 **`!override` 是必需的**：compose 对 list 字段是**追加**语义 —— 实测写 `volumes: []`
  清不掉硬编码挂载，`ports` 会变成 80 与 8080 **同时发布**；该标签需
  Docker Compose ≥ 2.24（`docker compose version` 查看）；
- 本地不需要 HTTPS，去掉该挂载不影响功能（nginx 只在 `/.well-known/acme-challenge/`
  请求时读它；HTTPS 流程见 `deploy/DEPLOY.md`）。

---

## 附录 B：相关文档

| 文档 | 内容 |
|---|---|
| [`README.md`](README.md) | 项目简介 / 功能 / 架构 |
| [`deploy/DEPLOY.md`](deploy/DEPLOY.md) | 云端部署（服务器初始化 + HTTPS + 回滚 + 上线自检清单） |
| [`AGENTS.md`](AGENTS.md) | 开发规范（分层 / 安全红线 / 配置三件套 / 测试 / 提交 / CR） |
| [`GIT_WORKFLOW.md`](GIT_WORKFLOW.md) | 分支模型与双远端（GitHub 全量 / Gitee 精简） |
| [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md) | 演示剧本与演示前自检 |
| [`PLAN.md`](PLAN.md) | 路线图与进度 |
| [`OPTIMIZATION_PLAN.md`](OPTIMIZATION_PLAN.md) | 优化批次与验收标准 |
