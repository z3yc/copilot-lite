# 🛠 Copilot-Lite 优化落地计划（OPTIMIZATION_PLAN）

> 来源：项目全面分析（规范落差 + 性能 + RAG/Agent 深度 + UX）。
> 原则：**一个提交 = 一个问题**；修复带防回归测试；后端改动跑 `pytest`+`ruff`，前端改动跑 `npm test`+`npm run build`。
> 关联规范：[AGENTS.md](AGENTS.md)（§12 分层 / §14 契约 / §15 追踪 / §18 Prompt）。

## 进度总览

| 批次 | 主题 | 状态 |
|---|---|---|
| A | CLI 完整可用（双入口闭环） | ✅ 完成 |
| B | 契约与可观测性（对齐 AGENTS.md） | ✅ B1/B2/B4 完成，B3/B5 暂缓 |
| C | 性能与正确性 | ✅ C1/C2/C5 完成，C3/C4 暂缓 |
| D | RAG / Agent 能力深度 | ✅ D1/D2/D4 完成，D3/D5 暂缓 |
| E | 产品体验（前端 UX） | ✅ E1–E4 完成，E5 暂缓 |
| F | 模型配置页面化（新想法） | ✅ 完成 |

### 已完成（累计，均已入 develop）

| 提交粒度 | 内容 | 测试 |
|---|---|---|
| `fix(cli): 登录与鉴权注入` | `copilot login/logout/whoami` + 令牌持久化 + 401 友好提示 | CLI 15 用例 |
| `feat(core): request_id 全链路追踪` | 纯 ASGI 中间件 + contextvars + 日志过滤器（含 user_id） | +4 |
| `perf(api): 修复文档列表 N+1` | 分块数改为 GROUP BY 批量统计 | +1 |
| `feat(core): 结构化输出容错解析` | `parse_json`（围栏/噪声容错）+ `response_format` 接入三处解析点 | +7 |
| `feat(session): 重命名/搜索/导出Markdown` | 后端 PATCH + `?q=` + `/export`；前端搜索/重命名/导出 | 后端 +2 / 前端 +5 |
| `feat(health): 存活/就绪探针分层` | `/health/live` + `/health/ready`（探 DB/Qdrant，503 降级） | +5 |
| `feat(web): ErrorBoundary + 骨架屏` | 全局错误边界、知识库加载骨架屏 | 前端 +2 |
| `feat(rag): 文档去重 + 失败重试` | SHA-256 去重、`/documents/{id}/retry`、前端重试按钮 + 迁移 | +3 |
| `refactor(core): Prompt 集中管理` | 6 处迁移到 `core/prompts/` + `PROMPT_VERSION` | +4 |
| `feat(agent): 上下文 token 预算` | `HISTORY_MAX_TOKENS` 三件套 + 估算裁剪 | +4 |
| `feat(api): 统一响应结构 + 错误码` | `/api/v1` 信封 `{code,message,data}`、全局异常处理器、前端/CLI 适配 | +9 |
| `feat(api): 列表分页` | 文档/待办/会话 `page/page_size`（默认20/上限100），前端与 CLI 适配 | +4 |
| `feat(agent): Human-in-the-loop` | 危险工具挂起、`/chat/confirm`、SSE `pending` 事件、前端确认条 | +7 |

**当前基线**：后端 **171 用例 / 覆盖率 82.87%**、ruff 全过；前端 **37 用例**、build 零错误；CLI **15 用例**、ruff 全过。

---

## 批次 A · CLI 完整可用（双入口闭环）

- [x] **A1 CLI 登录与鉴权注入**
  - 问题：`cli/copilot_cli/main.py` 的 `_request()` 不带 `Authorization`，而 `/chat`、`/todos` 全走 `get_current_user` → CLI 所有命令 401。
  - 落地：`copilot_cli/auth.py`（令牌读写 `~/.copilot/credentials.json`，`COPILOT_TOKEN`/`COPILOT_CREDENTIALS` 环境变量覆盖）；`login`/`logout`/`whoami`；`_request` 自动注入 Bearer + 401 指引。
  - 验收：`copilot login` → `whoami` → `todo list` 全链路成功；未登录给出明确指引。

---

## 批次 B · 契约与可观测性

- [x] **B1 全链路 request_id 追踪**（§15）
  - 落地：`app/core/context.py`（ContextVar + 纯 ASGI 中间件，避免 BaseHTTPMiddleware 的 contextvar 不传播问题）；`main.py` 注入中间件 + 响应头回写；`logging.py` 过滤器；`deps.get_current_user` 写入 user_id。
  - 验收：响应含 `X-Request-ID`（支持透传）；日志行含 request_id/user_id。

- [x] **B2 统一响应结构 + 错误码分层**（§14）
  - 落地：`app/core/errors.py`（AppError + 1xxx/2xxx/3xxx 映射）+ `app/core/envelope.py`（纯 ASGI 中间件，仅 `/api/v1` 2xx JSON 包壳，不影响 SSE/下载/OpenAPI）+ main.py 全局异常处理器（HTTPException/校验错误/未捕获异常）；前端 `request()` 解包、CLI `_request` 解包。
  - 验收：成功/错误结构一致；SSE、导出 Markdown、/openapi.json、根路径均不被包装。

- [ ] **B3 分层收口：service 层 + core 去框架依赖**（§12）
  - 问题：`api` 直接调 `agent`/`rag`；`core/budget.py` 直接 `import HTTPException`。
  - 落地：核心业务抽到 `app/service/*`；`core` 只抛领域异常，由 `api` 映射 HTTP。

- [x] **B4 Prompt 集中管理 + 版本**（§18）
  - 落地：迁移到 `app/core/prompts/*`（agent/chat/memory/rag/todo）+ `PROMPT_VERSION`；业务模块只引用。
  - 注：当前以 Python 常量集中管理（未引入 jinja2 运行时依赖）。

- [ ] **B5 OpenAPI → TS 类型自动生成**（§14）
  - 落地：脚本导出 openapi.json + `openapi-typescript`；保留手写别名层。
  - 验收：`npm run gen:types` 可复现；build 通过。

---

## 批次 C · 性能与正确性

- [x] **C1 修复文档列表 N+1 查询**（§13/§20）
  - 落地：`_chunk_counts()` 一次 GROUP BY 聚合回填。
  - 验收：列表查询数从 N+1 降到常数，测试含 SQL 语句数断言。

- [x] **C2 摄取流水线幂等 + 去重 + 重试**
  - 落地：`documents.content_hash`（SHA-256）同用户同内容复用已就绪文档；`POST /documents/{id}/retry` 复用原件重试；Alembic `d5a1c7e9f2b3`；前端 failed 文档重试按钮。

- [ ] **C3 Redis 落地（限流 / 预算），带内存回退**
  - 落地：抽象存储接口，优先 Redis（`REDIS_URL`），不可用回退内存；测试用内存后端。
  - 需 `redis` 依赖 + 可选服务。

- [ ] **C4 语义缓存（答案级）**
  - 落地：query 向量近邻命中即复用答案（带 TTL），命中率日志。

- [x] **C5 健康检查分层 + 依赖探活**
  - 落地：`/health/live` 与 `/health/ready`（探 DB / Qdrant，503 降级）；compose 健康检查改用 ready。

---

## 批次 D · RAG / Agent 能力深度

- [x] **D1 结构化输出 + 容错解析**
  - 落地：`app/core/json_parse.py`；`LLMClient.chat(response_format=...)`；查询改写/记忆提取/待办解析接入；Supervisor 路由 JSON 优先 + 正则兜底。
  - 验收：```json 围栏、前后噪声、非法 JSON 均正确降级。

- [x] **D2 Human-in-the-loop 工具确认**
  - 落地：`Tool.requires_confirmation` + `@registry.register(requires_confirmation=True)`；`todo_delete` 标记；两引擎遇危险工具挂起并返回确认提示；`Message.extra` 持久化 `pending_confirmation`；`POST /chat/confirm` 执行/取消；SSE `pending` 事件 + 前端确认条。
  - 验收：未确认不执行副作用；确认后执行并落库结果；取消不改数据。

- [ ] **D3 结构化引用可点击**
  - 落地：前端 [n] 渲染为可跳转到 chunk 的链接。

- [ ] **D4 上下文 token 预算**（替代纯条数窗口） — ✅ 已完成（`HISTORY_MAX_TOKENS` + `estimate_tokens` 二次裁剪）

- [ ] **D5 BM25 升级（PostgreSQL FTS）**

---

## 批次 E · 产品体验（前端 UX）

- [x] **E1 列表分页**（§14：`page`/`page_size` 默认 20、最大 100）——文档/待办/会话，前端与 CLI 自动解包 `items`
- [x] **E2 会话重命名 / 搜索**（后端 + 前端）
- [x] **E3 会话导出 Markdown**（后端 `/export` + 前端下载）
- [x] **E4 前端健壮性**：ErrorBoundary、骨架屏（AbortController / finally / SSE try-catch 已完成）
- [ ] **E5 用户反馈闭环**：回答 👍/👎 落库，驱动评测

---

## 验收总门槛

- [x] 后端 `pytest` 全绿且覆盖率 ≥ 80%（**171 / 82.87%**）
- [x] 后端 `ruff check .` 全过
- [x] 前端 `npm test` 全绿（**37**）、`npm run build` 零错误
- [x] CLI `pytest` 全绿（**15**）、`ruff` 全过

---

## 未来计划（暂缓批次，待后续完成）

> 以下已分析、有明确落地路径，但暂缓执行（非当前优先级）。需要时按原方案逐个开分支落地。

- [ ] **B3 分层收口**：service 层抽离、`core` 去 FastAPI 依赖（`core/budget.py` 直接 import HTTPException）
- [ ] **B5 OpenAPI → TS 类型自动生成**：脚本导出 openapi.json + `openapi-typescript`，替手写 `types.ts`
- [ ] **C3 Redis 落地**：限流/每日预算从进程内存迁到 Redis（带内存回退），支持多实例
- [ ] **C4 语义缓存（答案级）**：query 向量近邻命中即复用答案（带 TTL）
- [ ] **D3 结构化引用可点击**：前端 [n] 渲染为可跳转到对应 chunk 原文的链接
- [ ] **D5 BM25 升级**：PostgreSQL FTS（tsvector + GIN + ts_rank，jieba 分词）替代 ILIKE 伪实现
- [ ] **E5 用户反馈闭环**：回答 👍/👎 落库，驱动检索/生成评测

---

## 批次 F · 模型配置页面化（✨ 新想法，进行中）

> 目标：不用改 `.env`、重启服务，直接在 Web 页面配置模型——API Key、Base URL、模型名、温度、最大 tokens 等，按用户生效，未配置时回退环境变量。

- [x] **F1 配置存储与加密**
  - 已落地：`llm_settings` 表（user_id 唯一）+ Alembic `f1a2b3c4d5e6`；`core/crypto.py` Fernet（密钥派生自 SECRET_KEY）加密 API Key。
- [x] **F2 按用户解析模型配置**
  - 已落地：`LLMConfig` + contextvar；`get_llm()` 与 LangGraph `_get_langchain_llm()` 用户配置优先、环境变量回退；chat/ai-create 入口写入上下文，后台任务（记忆/摘要）自动继承。
- [x] **F3 配置 API**
  - 已落地：`GET/PUT/DELETE /settings/llm` + `POST /settings/llm/test`（真实连通性测试）；Key 掩码回显、URL 校验。
- [x] **F4 前端设置页**
  - 已落地：个人中心新增“⚙️ 模型设置”Tab（Base URL/模型/API Key/温度/max_tokens + 测试连接/保存/恢复默认）。
- [x] **F5 安全与测试**
  - 已落地：Key 加密存储（不回传明文、日志不打印）、跨用户隔离、未配置回退环境变量；后端 +12 用例（加密/掩码/隔离/回退/连通性）。

> 安全红线说明（§6）：密钥仅加密存于本人记录，接口不回传明文、日志不打印；`.env` 仍为默认，不破坏现有部署。

---

## 批次 G · 本地 Wiki 知识库（Obsidian 接入）

> 方案：`docs/知识库Wiki技术方案.md`（v2）；选型复盘：`面试准备/知识库Wiki技术选型与路线复盘.md`。

- [x] **M1 导入与索引**（`feat/wiki-import`，提交 `3f835b5`）
  - 受管副本 `WIKI_STORAGE_ROOT`；导入通道：**本地路径（受管根下）+ zip 上传**（zip 炸弹/路径穿越防护）。
  - `WikiParser`：frontmatter / `[[双链]]` / `![[嵌入]]` / `#标签`，注册进现有解析器表。
  - 增量同步：`rel_path` 幂等 + 内容 hash 识别“移动” + 变更页重嵌 + 删除级联；重建双链图。
  - API：空间 CRUD / zip 导入 / 同步 / 页面列表（分页）/ 页面详情（正文+出链+反向链接）。
  - 配置三件套：`WIKI_ENABLED / WIKI_STORAGE_ROOT / WIKI_SCAN_INTERVAL_MINUTES / WIKI_LINK_EXPANSION_ENABLED / WIKI_EXPAND_HOPS / WIKI_MAX_*`。
  - 测试：+13（语法 / zip 安全 / 导入同步 / 链接图 / 移动检测 / 隔离）。
- [x] **M1.5 Wiki 管理 UI**（`feat/wiki-ui`，提交 `c788b27`，**未合并**）：空间创建/删除、zip 导入、手动同步、页面树+搜索、页面浏览、反向链接/出链面板；前端 +4 用例。
- [ ] **M2 双链检索增强**：邻居扩展召回 + 引用带 Wiki 路径
- [ ] **M3 图谱可视化**：`/wiki/graph` + `react-force-graph-2d`
- [ ] **M4 轻量本体（可选）**：类型化链接（`wiki_link.relation`）+ 按关系加权/着色

**M1 后基线**：后端 **197 用例 / 覆盖率 80.55%**、ruff 全过；前端 **41 用例**、build 零错误；CLI **15 用例**。
