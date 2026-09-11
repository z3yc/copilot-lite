# 🛠 Copilot-Lite 优化落地计划（OPTIMIZATION_PLAN）

> 来源：项目全面分析（规范落差 + 性能 + RAG/Agent 深度 + UX）。
> 原则：**一个提交 = 一个问题**；修复带防回归测试；后端改动跑 `pytest`+`ruff`，前端改动跑 `npm test`+`npm run build`。
> 关联规范：[AGENTS.md](AGENTS.md)（§12 分层 / §14 契约 / §15 追踪 / §18 Prompt）。

## 进度总览

| 批次 | 主题 | 状态 |
|---|---|---|
| A | CLI 完整可用（双入口闭环） | ✅ 完成 |
| B | 契约与可观测性（对齐 AGENTS.md） | 🟡 进行中（B1 完成） |
| C | 性能与正确性 | 🟡 进行中（C1 完成） |
| D | RAG / Agent 能力深度 | 🟡 进行中（D1 完成） |
| E | 产品体验（前端 UX） | 🟡 进行中（E2/E3 完成） |

### 本轮已落地（可提交）

| 提交粒度 | 内容 | 测试 |
|---|---|---|
| `fix(cli): 登录与鉴权注入` | `copilot login/logout/whoami` + 令牌持久化 + 401 友好提示 | CLI 12 用例（新增） |
| `feat(core): request_id 全链路追踪` | 纯 ASGI 中间件 + contextvars + 日志过滤器（含 user_id） | 4 用例（新增） |
| `perf(api): 修复文档列表 N+1` | 分块数改为 GROUP BY 批量统计 | 1 用例（含查询数断言） |
| `feat(core): 结构化输出容错解析` | `parse_json`（围栏/噪声容错）+ `response_format` 接入三处解析点 | 7 用例（新增） |
| `feat(session): 重命名/搜索/导出Markdown` | 后端 PATCH + `?q=` + `/export`；前端搜索/重命名/导出 | 后端 2 + 前端 5 用例 |

**当前基线**：后端 **135 用例 / 覆盖率 82.99%**、ruff 全过；前端 **32 用例**、build 零错误；CLI **12 用例**、ruff 全过。

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

- [ ] **B2 统一响应结构 + 错误码分层**（§14）
  - 问题：路由返回裸对象 / `HTTPException(detail=...)`，无 `{code,message,data}`、无 1xxx/2xxx/3xxx。
  - 落地：业务异常基类 + 全局异常处理器；错误码枚举；前端 api 层适配解包。
  - 验收：所有错误响应结构一致；前端行为不回归。
  - ⚠️ 影响面大（全路由 + 前端），建议单独批次并保留兼容。

- [ ] **B3 分层收口：service 层 + core 去框架依赖**（§12）
  - 问题：`api` 直接调 `agent`/`rag`；`core/budget.py` 直接 `import HTTPException`。
  - 落地：核心业务抽到 `app/service/*`；`core` 只抛领域异常，由 `api` 映射 HTTP。

- [ ] **B4 Prompt 集中管理 + 版本**（§18）
  - 问题：6 个文件硬编码 prompt，无 `core/prompts/`、无 jinja2、无版本。
  - 落地：迁移到 `app/core/prompts/*`，加版本常量；注入定界声明保持。
  - 注：当前 venv 无 jinja2；若坚持模板渲染需先加依赖（`uv add jinja2`）。

- [ ] **B5 OpenAPI → TS 类型自动生成**（§14）
  - 落地：脚本导出 openapi.json + `openapi-typescript`；保留手写别名层。
  - 验收：`npm run gen:types` 可复现；build 通过。

---

## 批次 C · 性能与正确性

- [x] **C1 修复文档列表 N+1 查询**（§13/§20）
  - 落地：`_chunk_counts()` 一次 GROUP BY 聚合回填。
  - 验收：列表查询数从 N+1 降到常数，测试含 SQL 语句数断言。

- [ ] **C2 摄取流水线幂等 + 去重 + 重试**
  - 问题：重复上传产生双份向量；失败无重试入口；同步阻塞 HTTP。
  - 落地：内容 SHA-256 去重（同用户同哈希直接返回已有文档）；`retry` 接口；后台任务化 + 状态机。
  - 需新增 `documents.content_hash` 列 + Alembic 迁移。

- [ ] **C3 Redis 落地（限流 / 预算），带内存回退**
  - 落地：抽象存储接口，优先 Redis（`REDIS_URL`），不可用回退内存；测试用内存后端。
  - 需 `redis` 依赖 + 可选服务。

- [ ] **C4 语义缓存（答案级）**
  - 落地：query 向量近邻命中即复用答案（带 TTL），命中率日志。

- [ ] **C5 健康检查分层 + 依赖探活**
  - 落地：`/health/live` 与 `/health/ready`（探 DB / Qdrant）。

---

## 批次 D · RAG / Agent 能力深度

- [x] **D1 结构化输出 + 容错解析**
  - 落地：`app/core/json_parse.py`；`LLMClient.chat(response_format=...)`；查询改写/记忆提取/待办解析接入；Supervisor 路由 JSON 优先 + 正则兜底。
  - 验收：```json 围栏、前后噪声、非法 JSON 均正确降级。

- [ ] **D2 Human-in-the-loop 工具确认**
  - 落地：`Tool.requires_confirmation` 标记；挂起 + 确认事件；`/chat/confirm`；前端确认弹窗。
  - ⚠️ 跨两引擎 + SSE，工作量较大，建议单独批次。

- [ ] **D3 结构化引用可点击**
  - 落地：前端 [n] 渲染为可跳转到 chunk 的链接。

- [ ] **D4 上下文 token 预算**（替代纯条数窗口）

- [ ] **D5 BM25 升级（PostgreSQL FTS）**

---

## 批次 E · 产品体验（前端 UX）

- [ ] **E1 列表分页**（§14：`page`/`page_size` 默认 20、最大 100）
- [x] **E2 会话重命名 / 搜索**（后端 + 前端）
- [x] **E3 会话导出 Markdown**（后端 `/export` + 前端下载）
- [ ] **E4 前端健壮性**：ErrorBoundary、骨架屏（AbortController / finally / SSE try-catch 已完成）
- [ ] **E5 用户反馈闭环**：回答 👍/👎 落库，驱动评测

---

## 验收总门槛

- [x] 后端 `pytest` 全绿且覆盖率 ≥ 80%（135 / 82.99%）
- [x] 后端 `ruff check .` 全过
- [x] 前端 `npm test` 全绿（32）、`npm run build` 零错误
- [x] CLI `pytest` 全绿（12）、`ruff` 全过
- [ ] 剩余批次按上表继续推进
