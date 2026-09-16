# 🛠 Copilot-Lite 优化与演进计划（OPTIMIZATION_PLAN）

> 定位：**作品展示 + 未来企业落地**。原则：留口优先、不过度设计、一个提交一个问题。
> 规范：[AGENTS.md](AGENTS.md)（§6 安全红线 / §12 分层 / §14 契约 / §15 追踪 / §18 Prompt）。
> 关联：`docs/知识库Wiki技术方案.md`、`docs/优化落地记录.md`、`面试准备/知识库架构选型-连接器化与混合租户.md`、`面试准备/FIX_LOG_WIKI_RAG_RUNTIME.md`。

---

## 1. 进度总览

| 批次 | 主题 | 状态 |
|---|---|---|
| A | CLI 完整可用（双入口闭环） | ✅ 完成 |
| B | 契约与可观测性（对齐 AGENTS.md） | ✅ B1/B2/B4 完成（B3/B5 ❄️ 冻结） |
| C | 性能与正确性 | ✅ C1/C2/C5 完成（C3/C4 ❄️ 冻结） |
| D | RAG / Agent 能力深度 | ✅ D1/D2/D4 完成（D3 并入 G-M2；D5 ❄️ 冻结） |
| E | 产品体验（前端 UX） | ✅ E1-E4 完成（E5 ❄️ 冻结） |
| F | 模型配置页面化 | ✅ 完成 |
| G | 本地 Wiki 知识库（Obsidian 接入） | ✅ G-M1/G-M1.5/G-M2 + G-P1–G-P3 + G-M3 完成（G-M4 ❄️ 冻结） |
| H | 连接器化收口（Obsidian → connectors） | ✅ 完成 |
| L | 软删除与审计（强制红线） | ✅ 完成（后端+回收站前端） |
| I | 企业化：租户与权限 | ❄️ 冻结（§11） |
| J | 可靠性与治理 | ✅ J1 完成；🟡 J3 → R5；J2/J4/J6/J7 ❄️ 冻结（J5 并入 L） |
| K | 连接器生态与直连能力 | ❄️ 冻结（§11） |
| M | 知识来源范围（RAG / Wiki 检索分流） | 🟡 M1/M5 完成；M2/M3/M4/M6 ❄️ 冻结 |
| N | 管理后台与质量看板 | 🟡 N0/N1 完成、N2 → R6；N2.7/N2.9/N3 ❄️ 冻结 |
| P | 基金盯盘 + MCP 接入 | 🟡 F1 → R4、F2-F4 → R7（**已排期**） |
| Q | Agent 形态与可观测 | 🟡 Q1 ✅ 完成（R2）、Q5 → R5；Q2/Q3/Q4 ❄️ 冻结 |
| Z | 暂缓项（B3/B5/C3/C4/D5/E5/L7） | ❄️ 冻结（§11） |

> ❄️ = 已冻结（不改代码、不排期）；**冻结项一律带重启条件**，见 §11 冻结清单与重启条件。
> 🟡 = 在范围内（已排期），行尾标注 `（见 §13 R<N>）`。
> ⏸ = 按需、不进路线图（等同冻结，不单列于 §11）。
> **进度事实来源：§13**。`PLAN.md` 的 P5/P6 与 `ADMIN_PLAN.md` 的 N2/N3 均为**镜像**；调整进度时先改 §13。

**当前基线**：后端 **394 用例 / 覆盖率 83.65%**、ruff 全过；前端 **125 用例**、build 零错误；CLI **15 用例**（沿用 `develop` 基线，R3 未改 CLI）。
（数据为 `fix/citation-jump-target` @ `1816bb7` 实测；R3 起点 `develop` @ `e772c7d` 为后端 380 / 83.39%、前端 107。）

---

## 2. 已完成（累计）

### 已入 `develop`

| 提交粒度 | 内容 | 测试 |
|---|---|---|
| `fix(cli)` 登录鉴权 | `copilot login/logout/whoami` + 令牌持久化 + 401 指引 | CLI +15 |
| `feat(core)` request_id 追踪 | 纯 ASGI 中间件 + contextvars + 日志过滤器（含 user_id） | +4 |
| `perf(api)` 文档列表 N+1 | 分块数改 GROUP BY 聚合 | +1 |
| `feat(core)` 结构化输出容错 | `parse_json` + `response_format` 接入三处解析点 | +7 |
| `feat(session)` 搜索/重命名/导出 | 后端 PATCH/`?q=`/`/export`；前端交互 | 后端 +2 / 前端 +5 |
| `feat(health)` 存活/就绪分层 | `/health/live` + `/health/ready`（探 DB/Qdrant） | +5 |
| `feat(web)` ErrorBoundary+骨架屏 | 全局错误边界、知识库加载骨架屏 | 前端 +2 |
| `feat(rag)` 文档去重+重试 | SHA-256 去重、`/documents/{id}/retry`、前端重试 | +3 |
| `refactor(core)` Prompt 集中 | 6 处迁 `core/prompts/` + `PROMPT_VERSION` | +4 |
| `feat(agent)` token 预算 | `HISTORY_MAX_TOKENS` + `estimate_tokens` 二次裁剪 | +4 |
| `feat(api)` 统一响应+错误码 | `/api/v1` 信封 + 全局异常处理器 + 前端/CLI 解包 | +9 |
| `feat(api)` 列表分页 | 文档/待办/会话 `page/page_size` + 前端/CLI 适配 | +4 |
| `feat(agent)` Human-in-the-loop | 危险工具挂起 + `/chat/confirm` + SSE pending + 前端确认条 | +7 |
| `feat(settings)` 模型配置页面化 | `llm_settings` 加密存储 + 按用户解析 + 设置页 + 连通测试 | +12 |
| `feat(wiki)` M1 导入与索引 | zip/本地路径导入、双链解析、增量同步、空间/页面/链接 API | +13 |
| `feat(wiki)` M1.5 管理 UI | Wiki 页签、空间/导入/同步、页面浏览、反向链接/出链 | 前端 +4 |
| `fix(wiki)` 时区 500 | `last_synced_at` 写 naive UTC（PG/asyncpg 兼容） | +1 |
| `fix(rag)` 嵌入离线缓存 | `EMBEDDING_CACHE_DIR` + `local_files_only` + 启动预热（51s→0.13s） | +2 |
| `refactor(connectors)` 连接器化 | `app/wiki` → `app/connectors/obsidian` + `SourceConnector` 抽象 | — |

### 已完成的分支工作（`feat/wiki-import-files` → … → `fix/wiki-delete-safety`，均已合入 `develop`）

| 提交粒度 | 内容 | 测试 |
|---|---|---|
| `feat(rag)` M2 双链邻居扩展 | 命中页 1-hop 出/入链补充候选 + 精排（`WIKI_EXPAND_NEIGHBORS`，失败回退） | +4 |
| `feat(chat)` 结构化引用 | `kb_search`→上下文→`Message.extra.citations`；前端来源可点击 | +3 / 前端 +1 |
| `fix(agent)` Wiki 认知 | 提示词明示维基、路由关键词加 `wiki/维基`、`kb_search` 描述（`PROMPT_VERSION 1.1.0`） | +2 |
| `fix(rag)` 嵌入生成器 | 单条嵌入改 `next(iter(...))`（修复 `'generator' object is not subscriptable`） | +2 |
| `fix(agent)` LangGraph 流式 | 流式运行改用 `astream` 聚合（`ainvoke` 不产生 token 事件） | — |
| `fix(rag)` 重排缓存 | 离线优先 + 持久缓存 + 预热（1~2 分钟 → 2.5s） | +1 |
| `feat(wiki)` P1 导入入口 | 单/多文件 + 文件夹导入；支持 PDF/DOCX/TXT；`skipped` 反馈 | +3 / 前端 +1 |
| `feat(wiki)` P2 清洗与展示 | 排除模板目录（`WIKI_EXCLUDE_DIRS`）；去 `{{...}}`；`[[双链]]` 可跳转（`/resolve`） | +2 / 前端 +1 |
| `feat(wiki)` P3 单页重试 | `POST /wiki/pages/{id}/sync` + `document_status` + 前端按钮 | +1 / 前端 +1 |
| `fix(rag)` 文本编码/NUL | `decode_text()`（UTF-16/GBK 探测 + 去 NUL），修复 PG 分块入库 500 | +2 |
| `fix(wiki)` 删除安全护栏 | **仅删受管副本；local 空间只解除登记，绝不删用户文件** | +2 |
| `feat(wiki)` G-M3 图谱可视化 | `GET /wiki/graph`（空间/标签过滤、度数、节点上限截断）+ 前端力导向图（节点点击跳页） | 后端 +7 / 前端 +5 |

---

## 3. 批次 G · 本地 Wiki 知识库

- [x] **G-M1 导入与索引**：受管副本 + 本地路径/zip 导入 + `WikiParser` + 增量同步（rel_path 幂等 + hash 移动 + 级联删除）+ API。
- [x] **G-M1.5 管理 UI**：Wiki 页签、空间/导入/同步、页面树+搜索+分页、页面浏览、反向链接/出链。
- [x] **G-M2 双链检索增强 + 引用可点击**：1-hop 邻居扩展召回（可开关）；回答 `[n]` 来源落库并可点击。
- [x] **G-M2.5 导入体验 P1–P3**（用户反馈驱动）：单/多文件与文件夹导入、非 md（PDF/DOCX/TXT）索引与 `skipped`、模板目录排除与双链渲染、单页重新索引。
- [x] **G-M3 图谱可视化**：`GET /wiki/graph` + 前端 `react-force-graph-2d`（点击跳页、按空间/标签过滤、节点数上限）。
- ❄️ **G-M4 轻量本体（可选）**：类型化链接 `wiki_link.relation` + 按关系加权/着色；**不做完整本体**。

---

## 4. 批次 L · 软删除与审计（**强制红线，优先**）

> 驱动：删除空间误删用户本地目录事故（见 `docs/优化落地记录.md`）。
> 规范：AGENTS §6/§13/§14/§15 已更新——**所有删除一律软删除且可溯源，禁止物理删除业务/用户数据**。

- [x] **L1 模型与迁移**：业务表（documents / chat_sessions / messages / todos / session_files / memory_facts / wiki_spaces / wiki_pages）加 `deleted_at` + `deleted_by`（可选 `delete_reason`）；唯一约束改**部分唯一索引**（`WHERE deleted_at IS NULL`）。
- [x] **L2 查询/检索统一过滤**：列表、详情、统计、**向量 payload 与 BM25 召回**统一排除已删除；补"已删除不被召回"回归测试。
- [x] **L3 软删除服务**：`soft_delete()/restore()`；父子级联软删；删除写审计（request_id/user_id/资源/时间/结果）。
- [x] **L4 回收站**：`GET /trash`、`POST /trash/{type}/{id}/restore`、彻底删除（仅管理员/合规，需二次确认）；前端「回收站」入口。
- [x] **L5 文件与副本**：受管副本删除改为**移入回收目录**（可恢复）；**继续禁止触碰 local 外部真实目录**。
- [x] **L6 删除二次确认 + 前端回收站入口**：前端删除危险操作统一二次确认 + 文案说明影响范围。

---

## 5. 批次 I · 企业化：租户与权限（混合模式）

> 模型：`Tenant（隔离边界）→ Workspace（协作/知识空间）→ Membership(角色) → document.acl`。

- ❄️ **I1 租户模型与迁移**：`tenants` / `workspaces` / `workspace_members`（owner/admin/member/viewer）；seed 默认租户+workspace。
- ❄️ **I2 资源归属**：`documents` / `wiki_spaces` 增加 `tenant_id` / `workspace_id`；摄取时写入。
- ❄️ **I3 文档级 ACL**：`documents.acl`（可访问 workspace/role/user；默认继承 workspace）。
- ❄️ **I4 检索过滤链（企业命门）**：向量 payload + BM25 JOIN + 引用链路统一按 `tenant → 可访问 workspace → ACL`；跨租户/跨 workspace 不可见回归测试。
- ❄️ **I5 请求上下文**：从 JWT/请求头解析 tenant/workspace（缺省回退默认，兼容 demo）。
- ❄️ **I6 角色与前端**：workspace 切换器、成员管理、按角色隐藏危险操作（与 HITL 联动）。

---

## 6. 批次 J · 可靠性与治理

- [x] **J1 异步摄取/同步**：`jobs` 表 + 后台执行 + 进度查询 + 重试/死信；import/sync 不再阻塞 HTTP。
      _实现：`app/core/jobs.py` 通用状态机（handler 注册表 + 限并发/超时 + 自动重试→dead）+ `Job` 模型与迁移
      + `/jobs` 列表/详情/重试（按 `user_id` 隔离）+ Wiki 导入/同步接入（`JOBS_ENABLED` 开→202+job_id，关→内联回退旧行为）
      + 前端轮询进度（可取消）。_
- ❄️ **J2 可观测性**：OpenTelemetry（检索/LLM/工具 span）+ 指标 + 按 tenant 的 token/成本统计。
- 🟡 **J3 评测进 CI**：`rag_eval.py` / `rag_eval_ragas.py` 阈值门槛。（见 §13 R5）
- ❄️ **J4 审计日志**：与 L3 联动，统一审计表（敏感操作）。
- ❄️ **J6 密钥与配置分级**：Secret Manager 接入。
- ❄️ **J7 基础设施可替换**：Redis（C3）、任务队列、Qdrant 集群、S3。
- [x] **J5 软删除与合规** → 已提升为 **批次 L**（更严格：全部软删除+可溯源）。

---

## 7. 批次 K · 连接器生态与直连能力

- ❄️ **K1 连接器管理与选择**：API/UI 列出可用连接器，按连接器创建空间。
- ❄️ **K2 新连接器**：S3/对象存储、Git、通用本地目录；后续 SharePoint / Confluence。
- ❄️ **K3 直读工具（成本回退）**：`vault_list` / `vault_search(grep)` / `vault_read`。
- ❄️ **K4 Obsidian 写回（可选）**：Local REST API / MCP。
- ❄️ **K5 增量与权限映射**：外部源增量游标 + ACL 映射。

---

## 8. 批次 M · 知识来源范围（RAG / Wiki 检索分流）—— M1/M5 完成；M2–M4/M6 已冻结（§11）

> **决策（本会话讨论锁定）**：采用**方案 C**——不拆两个工具，保持**统一索引 + 单一 `kb_search`**，用可选 `scope` 表达范围，默认全库，收窄为空时自动回退。
> 背景：Wiki 页面已与上传文档同走 `documents/chunks/Qdrant` 一条摄取/检索链路，差异在**增强策略**（Wiki 有双链邻居扩展/图谱）而非检索主干，故拆工具只会增加路由犯错面。
> 现状：`document.source_type` **已写入** Qdrant payload（M1 已完成，向量与 BM25 双路读取）；原文「未写入」的描述已过时，保留于此仅为沿革记录。

- [x] **M1 来源元数据入检索层**：`document.source_type` 写入 Qdrant payload（与 BM25 的 Document JOIN 对齐），使 scope 过滤在**向量 + BM25 同一条过滤链**生效；需一次性重建/回填索引。
      _已完成（实测 `rag/pipeline.py` 写 payload `source_type`，`rag/retriever.py` 向量/BM25 双路读取；对应 ADMIN_PLAN §9 N0.4 已勾选）。_
- ❄️ **M2 `kb_search` 增加可选 `scope`**：枚举 `all | docs | wiki`，**默认 all**；仅当用户**显式表达**范围（“只在我的 wiki 里”/“根据我上传的文档”）才收窄；无法判断一律 all。
- ❄️ **M3 空结果自动回退**：收窄检索为空时**自动放宽到 all**，并如实告知用户已放宽范围——杜绝“猜错范围即漏答”。
- ❄️ **M4 策略随 scope 联动**：`scope=wiki` 强制开双链邻居扩展；`scope=docs` 关闭该扩展（将现有 `WIKI_LINK_EXPANSION_ENABLED` 从全局开关细化为按 scope）。
- 🟡 **M5 引用来源标注**：引用中明确区分 `Wiki/空间/页面` 与 `文档/页码`（方案 A 的补强，**可独立先做**，不依赖 M1）。**✅ 已完成（R3）**：`app/rag/citations.py` 统一标签口径 + `SourceConnector.describe_sources` 连接器身份 seam + 前端 `openTarget` 跨面板跳转。
- ❄️ **M6（可选）UI 知识范围选择器**：聊天框“知识范围”下拉或 `@wiki` 提及，提供零 LLM 猜测的确定性入口（方案 D，作为 scope 的上层输入）。

---

## 9. 批次 P · 基金盯盘 + MCP 接入（Agent 主动性第一落地）

> 定位：让助手从「你问才答」变成「到点自己干活」——**Agent 主动性（A）的第一片**，
> 同时把 **MCP** 作为外部能力接入的标准接缝验证一遍。
> 一句话原则：**持仓 = 本机私密数据（手动录入）；行情 = 公开数据（走 MCP）；取数用代码，说话才用 LLM。**
> 关联：`docs/plans/2026-09-15-fund-watch-mcp-design.md`（设计文档，属 `private-docs` 分支）。

### 9.1 已锁定的设计决策（讨论定稿）

| # | 决策 | 理由 |
|---|---|---|
| P0.1 | 形态 **B 档**：交易日收盘后（默认 21:30，可配）播报一次涨跌 + 收益；按 C 档（阈值告警）留接口 | **A 股 15:00 收盘，但场外基金净值晚间才公布**——「15:30 播报」拿到的还是昨日数据 |
| P0.2 | 持仓 **手动录入**，表留 `source(manual/mcp/ocr)` 接缝 | 财务数据最敏感 → 不出本机；自动化瓶颈在「每天跑」而非「录一次」 |
| P0.3 | 行情走 **`ToolRegistry`（工具）**，**不进 RAG** | 净值是精确数字，语义检索数字 = 幻觉源 |
| P0.4 | MCP **全局共享 + 本地 stdio**（管理员 `.env` 配置） | 行情公开且同源；避开用户级配置带来的 SSRF/凭据/隔离三重复杂度 |
| P0.5 | MCP 工具**不直接透传给 LLM**，包一层领域工具（`fund_tool`） | server 会停更、字段各异；换 server 只改适配器，prompt 不变 |
| P0.6 | 调度**复用 J1 `jobs` 状态机**（`schedules` 表 + ticker 建作业） | 触发与执行解耦，重试/死信/排障统一在一张表 |
| P0.7 | 播报**先不接 LLM**（Jinja2 模板渲染），留 `FUND_REPORT_LLM` 接缝 | 省 token、可对账、可精确断言 |
| P0.8 | 产出：**站内落 `notifications`（必做）+ IM Webhook（可选）** | 站内可追溯/可软删；webhook 一个 URL 换真提醒体验 |
| P0.9 | **不引节假日日历**：`nav_date` 未前进即视为「无新数据」 | 日历会过期；数据驱动更稳（且不必假设是当天） |

### 9.2 分期（每期独立可交付、可验收）

- 🟡 **P-F1 MCP 地基**：`app/mcp/`（stdio client + server 注册表 + 适配器注册表）+ `app/funds/quotes.py`（归一化/校验/缓存）+ `fund_tool`（对话查单支基金净值）。（见 §13 R4）
      _最早验证 MCP server 选型：不合适就换，不返工。_
- 🟡 **P-F2 持仓**：`fund_positions` 表 + 迁移 + CRUD API + 前端录入 + 收益计算（`Decimal`，含 `prev_nav` 缺失/除零边界）。（见 §13 R7）
- 🟡 **P-F3 调度闭环**：`schedules` 表 + `core/scheduler.py` ticker（原子抢占 + 幂等 + 可开关）+ `fund_watch` job handler + 站内 `notifications`。（见 §13 R7）
- 🟡 **P-F4 提醒体验**：IM Webhook 推送（URL 脱敏 + 超时 + 失败不回滚站内）+ 通知中心前端（列表/已读/删除）。（见 §13 R7）

### 9.3 关键实现约束

- **MCP 返回视为不可信**（AGENTS §6.6/§18）：数值夹取（`nav∈(0,1e6)`、`change_pct∈[-100,100]`）、`nav_date` 解析失败丢弃、只取结构化字段；server 白名单 + tool description 截断；
- **密钥脱敏**（AGENTS §6.1/§6.8）：MCP `env` 中的 Key、飞书 webhook URL（含 token）**日志一律脱敏**；
- **软删除**（AGENTS §13）：持仓/调度/通知全 `deleted_at/deleted_by`，列表默认过滤；部分唯一索引 `(user_id, code) WHERE deleted_at IS NULL`；
- **后台任务可开关**（AGENTS §8）：`SCHEDULER_ENABLED` 测试默认关；ticker 与 MCP 调用均设超时（AGENTS §17）；
- **金额/份额一律 `Numeric(18,4)` + `Decimal`，禁用 `float`**；
- 手动触发 `POST /funds/report/run`：便于当场验证配置与演示（无需等到半夜）。

### 9.4 新增配置（三件套）

`MCP_ENABLED` · `MCP_SERVERS` · `MCP_CALL_TIMEOUT_SECONDS` · `FUND_QUOTE_CACHE_MINUTES` · `SCHEDULER_ENABLED` · `SCHEDULER_TICK_SECONDS` · `FUND_WATCH_TIME` · `FUND_REPORT_LLM` · `FUND_WEBHOOK_URL`

### 9.5 验收门槛

- [ ] 后端 `pytest` 全绿且覆盖率 ≥80%、`ruff` 全过；前端 `npm test` + `build` 零错误；
- [ ] 跨用户隔离回归（A 看不到 B 的持仓/通知/调度）；软删除可恢复且列表/统计已过滤；
- [ ] MCP 适配层用 Fake client 测（不联网）；脏数据（负净值/日期非法/超范围）逐条丢弃并留日志；
- [ ] webhook 失败**不影响站内记录**；日志无明文密钥（含 webhook token）；
- [ ] 调度：到点触发 / 未到点不触发 / 开关关闭不跑 / 重复 tick 不重复执行（幂等）各有回归用例。

---

## 10. 批次 Q · Agent 形态与可观测（多智能体主干）

> 定位：把 Agent 从「问答机器人」推向「个人助手」。**形态定稿：多智能体为主干**；
> 可观测与多智能体**同时做**——多智能体没有 trajectory 就不可调试、不可评测，
> 先上形态不补可观测 = 自己把自己变成黑盒。
> 关联：同目录《Agent 形态选型-单智能体与多智能体.md》（`private-docs` 分支，含正反论点与面试话术）。

### 10.1 已锁定的设计决策

| # | 决策 | 理由 |
|---|---|---|
| Q0.1 | 形态：**多智能体**（supervisor + 专项子 Agent）为主干 | 目标=面试演示 + 个人日用；判据不是"理论最优" |
| Q0.2 | 引擎归属：**LangGraph 升为主干**（U1-a）；手写 `Orchestrator` 降为**对照/回退**，功能冻结 | 骨架现成、接口层平权（HITL/引用/流式都有），改造低于新建 |
| Q0.3 | 确定性任务**不进 Agent**：走 `jobs`（J1）+ 领域工具 | 省 token、可对账、可断言（与批次 P 的 P0.3/P0.5/P0.7 同哲学） |
| Q0.4 | 子 Agent 仅在**"上下文会被中间产物撑爆"**时引入（深度研究、长文写作） | 不为好看而拆（其余皆是工具调用） |
| Q0.5 | supervisor **先单次路由 + 失败回退**，不做自由回环 | 防不确定循环；可测试、可回归 |
| Q0.6 | `tools_agent` 从 `None`（**全量工具**）改为**显式白名单** | MCP 接入后工具膨胀，全量节点 prompt 最先爆 |
| Q0.7 | **trajectory 全量落库**：plan → 路由 → 节点 → 工具 → 结果（复用 `Message.extra`） | 多智能体不可观测 = 不可调试/不可评测 |
| Q0.8 | 双引擎**对照评测**（同一批 golden 问题：token / 延迟 / 准确率） | 把"取舍"变成数据——也是最好的演示资产 |
| Q0.9 | 引入 **Task 实体**（跨轮任务状态：可恢复、可中断、可跟进） | 没有 Task，"多智能体分配工作"无从落地 |

### 10.2 分期（每期独立可交付、可验收）

- ✅ **Q1 可观测地基**：trajectory 结构定义 + 落 `Message.extra` + 前端可见（先能看清）。（R2 已完成，见 §13）
- ❄️ **Q2 工具白名单与渐进披露**：`tools_agent` 显式白名单；按意图分批披露工具（为 MCP 铺路）。
- ❄️ **Q3 Task 实体**：任务状态机（跨轮/可恢复/可中断）+ API + 前端；"分配工作"的载体。
- ❄️ **Q4 supervisor 深化**：单次路由 + 失败回退 + 路由落 trajectory + **路由回归用例**（关键词兜底仍生效）。
- 🟡 **Q5 双引擎对照评测**：脚本 + 报告（token/延迟/准确率）；作为"何时退回单智能体"的数据依据。（见 §13 R5）
- ⏸ **子 Agent 扩展（深度研究 / 长文写作）**：按需，不在本期。

### 10.3 关键实现约束

- **双引擎契约**（AGENTS §2）：LangGraph 升主干后，手写引擎转为**回归基线**——两套测试都要跑，防“主干改造把对照实现跑坏”；
- **新增能力优先“做成工具”**：两引擎共享 `ToolRegistry`，加工具成本 ≈ 0（只有改引擎本身才是 2×）；
- **脱敏**（AGENTS §15）：trajectory 禁落密钥；对话原文按现有日志口径处理，不新增泄露面；
- **可开关**（AGENTS §8）：`AGENT_TRACE_ENABLED` 等新增开关测试环境默认关；
- **失败回退优先可用性**（AGENTS §10）：路由失败→回退单 agent 路径，绝不让用户拿到空回复；
- 改 `langgraph_engine` 时**同步检查 `tools_agent: None` 全量注入**是否已收敛。

### 10.4 新增配置（三件套，待细化）

`AGENT_TRACE_ENABLED` · `AGENT_ROUTE_FALLBACK` · `TASK_ENABLED`

### 10.5 验收门槛

> R2 完成时逐条核对：以下 3 条属本轮范围（已达成）；另 3 条分属 Q2/Q4/Q5，不在本轮。

- [x] **trajectory 可回放**：给定一条消息能复原路由 / 节点 / 工具 / 结果；（R2：`tests/test_trajectory_api.py::test_chat_persists_trajectory`）
- [ ] **路由回归**：路由判错用例能被测试捕获，关键词兜底仍生效；→ **属 Q4（❄️ 冻结，不在 R2 范围）**；R2 已顺带补「关键词兜底」回归（轨迹如实标注 `source=keyword`）
- [ ] **白名单生效**：未挂白名单的新工具不会被注入 `tools_agent`；→ **属 Q2（❄️ 冻结）**
- [ ] **对照报告产出**：两引擎 token / 延迟 / 准确率三项数据可比；→ **Q5 → R5**
- [x] 后端 `pytest` 全绿且覆盖率 ≥80%、`ruff` 全过；前端 `npm test` + `build` 零错误；（R2 实测：后端 370 / 82.81%、ruff 全过、前端 102、build 零错误）
- [x] trajectory 与日志中无密钥。（R2：敏感 key 值替换 `***`，覆盖驼峰 key 与工具结果，4 个回归用例）

---

## 11. ❄️ 冻结清单与重启条件

> 冻结 ≠ 删除。**每条必须带重启条件**，否则半年后会被重新当成待办挖出来——这正是本轮范围沉积的成因（见 `docs/plans/2026-09-15-scope-convergence-design.md` §1，属 `private-docs` 分支）。
> 冻结项一律**不改代码、不排期、不承接部分实现**。
> 重新激活流程：满足重启条件 → 先写设计文档 → 纳入路线图 → 再开工。

| 项 | 冻结理由 | 重启条件 |
|---|---|---|
| **I1-I6** 多租户 / workspace / ACL | 单用户不可演示、不可验证；半成品 ACL 是真实泄露面 | 真实出现第二个用户，或面试岗位明确要求讲多租户 |
| **J2** OTel + Grafana + 告警 | `request_id` + `/health/ready` + 审计已够个人量级 | 出现真实排障需求（线上事故查不动），或岗位明确要求可观测体系 |
| **J4** 审计统一表 | L3 + `/admin/audit` 已覆盖敏感操作 | 企业合规要求 |
| **J6** Secret Manager | 单机 `.env` + Fernet 加密已足够 | 企业落地 / 合规要求 |
| **J7 / C3** Redis、任务队列、S3、Qdrant 集群 | `jobs` 表 + 单体已够；"基础设施可替换"是架构原则，不是待办 | 出现可量化瓶颈（队列深度/延迟有数据支撑） |
| **K1** 连接器管理界面 | K2 前置，无多来源可管 | K2 解冻 |
| **K2** 新连接器（S3/Git/通用目录/SharePoint/Confluence） | **无真实数据源 = 无内容可检索** | 出现真实数据源（如实习/工作环境有 Confluence） |
| **K3** 直读工具（`vault_list`/`grep`/`read`） | Obsidian 已导入索引；Demo 的工具调用示例由 `fund_tool` 承担 | 自用时真实出现"要 grep 未索引内容"的需求 |
| **K4** Obsidian 写回 | 读路径未跑满，写回增加对外部系统的副作用面 | 自用中真实出现回写需求，且评估过副作用风险 |
| **K5** 增量游标 + ACL 映射 | 依赖 I 与 K2 | I + K2 解冻 |
| **M2/M3/M4** `kb_search` scope 分流 | 未进任何镜头；当前未出现"查错来源"的真实痛点 | 自用时反复出现检索范围混淆 |
| **M6** UI 知识范围选择器 | 依赖 M2 | M2 解冻 |
| **N2.7** Wiki 图谱对账 | 不在镜头 5；确定性指标可后补 | R6 出数顺利且需要 Wiki 质量故事 |
| **N2.9** A/B lift（rerank/query-rewrite/双链） | 单用户样本量不足，结论不可信 | 有足够评测样本量（≥ 200 query） |
| **N3.1 / N3.2** OTel+Grafana / 多租户 | 同 J2 / I | 同 J2 / I |
| **Q2** 工具白名单与渐进披露 | 当前工具数少，全量注入未爆 | 工具数 > 15，或 prompt 明显膨胀 |
| **Q3** Task 实体（跨轮任务状态机） | 无跨轮跟进场景；成本中型 | 自用中真实出现"跨轮跟进/可恢复任务"需求 |
| **Q4** supervisor 深化 | 现有单次路由 + 关键词兜底已够 | 路由判错成为高频问题（有 trajectory 数据支撑） |
| **B3** 分层收口（service 层抽离） | 纯重构，无新故事，风险高 | 需要大规模协作或模块数翻倍时 |
| **B5** OpenAPI → TS 类型自动生成 | 手写类型量级小，收益低 | 接口数翻倍 |
| **C4** 语义缓存（答案级） | 个人量级无命中率，且有缓存错答案的正确性风险 | 请求量支撑命中率（有数据） |
| **D5** BM25 → PostgreSQL FTS | 现有 BM25 在百篇量级够用，纯替换无收益 | 现有实现被证明是瓶颈（检索延迟数据） |
| **E5** 用户反馈闭环 | 单用户无标注价值 | 多用户 |
| **G-M4** 轻量本体（类型化链接） | 图谱可视化已够，本体属学术级玩具 | 真实出现关系推理需求 |
| **L7** 用户注销 / 账号软删除 | 单用户无注销场景（`ADMIN_PLAN` N0.6/N1.3 已覆盖管理员侧软删） | 多用户上线 |

**接缝不删**（`ADMIN_PLAN` §7「只留缝」是正确的，继续保留）：
`tenant_id`/`workspace_id` nullable 列 · `require_admin → RBAC` 替换点 · `audit_logs` append-only · `config_fingerprint` 维度。

---

## 12. 待合并与推送（**需批准**）

> 按约定：合并 / 推送前需维护者确认。

- [x] **合并 `feat/jobs-async-ingest`**（J1 异步摄取/同步：jobs 表 + 状态机 + Wiki 接入 + 前端轮询）→ `develop`（`5b5ce2f`）；`main` 待发布时合并。
- [x] **合并修复分支**：`fix/wiki-delete-safety`（tip，含 M2 + 引用 + 认知修复 + 嵌入/LangGraph/重排修复 + P1–P3 + 编码修复 + 删除护栏）→ `develop`——**已完成**（分支已删除，早前合并，此行属陈旧记录）。
- [x] **合并 `feat/agent-trajectory`**（R2 / Q1 trajectory：`TrajectoryRecorder` + 双引擎同形状接线 + `Message.extra.trajectory` + SSE `done` 增量字段 + 前端轨迹面板 + `AGENT_TRACE_ENABLED` 三件套）→ `develop`（合并提交 `a430ecc`；已过逐任务评审、全分支评审与真实模型实测）；分支已删除。
  - ⚠️ **一次性例外（维护者 2026-09-15 批准）**：本次**本地 `--no-ff` 合并后直推 `develop`**，未走 PR/MR。原因：当时 AGENTS §11「禁止直接 push `develop`」与 `GIT_WORKFLOW.md`「代码：正常推两个远端」**互相矛盾**。→ **已解决（同日）**：AGENTS §11 合并规则改为「`develop`/`main` 推送需维护者明确批准；是否走 PR/MR 由维护者按改动规模决定（CI 全量检查仍为合并前置条件）」，与 `GIT_WORKFLOW.md` 取齐。
    - ⚠️ 遗留风险：`AGENTS.md` 被 `.gitignore` 忽略（本机文件），该规则**不进版本库、仅本机生效**。建议后续把分支/合并规则搬进受版本管理的 `GIT_WORKFLOW.md`，AGENTS 只留指针。
  - 合并前发现 `github/develop` 领先本地/Gitee **1 个提交**（`20353db` 部署/开发文档补超管说明），已先 `--ff-only` 并入再合并，避免非快进被拒。
  - 合并后的树上复跑实测：后端 370 / 82.81%、`ruff` 全过；前端 102、`build` 零错误。
- [x] **合并修复分支 `fix/stream-truncation`**（真实使用暴露的流式三修，`8d79c11..dd7e493`，共 **8** 个提交）→ `develop`（合并提交 `ed78b4d`；已过逐任务评审、全分支评审、残留修复复审与真机 21.15s 静默复验）；分支已删除。
  - ⚠️ **一次性例外（第二次，维护者 2026-09-15 批准）**：同样**本地 `--no-ff` 合并后直推 `develop`**，未走 PR/MR。此矛盾已于同日取齐（见 R2 条目：AGENTS §11 措辞已改）——**此后直推 `develop` 属规则内行为，前提是维护者明确批准**。
  1. **心跳不再截断回答**（`743cdae`/`41d0880`）：旧实现用 `asyncio.wait_for(anext(gen), timeout=_HEARTBEAT_SECONDS)` 取下一分片，超时会**取消**被包裹的 `anext`、把异步生成器就地终止；流循环随后把 `StopAsyncIteration` 当正常结束 → 落库并发 `done`，表现为「回答被静默截断却显示成功」，且 `citations`/`trajectory` 一并丢失（它们只在 `run_stream` 收尾代码里拷贝）。改为把 `anext` 挂成 Task、跨心跳超时复用，并在断开时显式取消悬挂的分片任务。
  2. **工具轮独白不再当作回答**（`6c74471`/`0e52eca`）：双引擎按「模型轮」缓冲，只有该轮**无** `tool_calls` 才把缓冲文本作为回答产出；`tool_calls` 字段缺失时 fail-closed（按工具轮丢弃并 WARNING）。旧假设「工具轮 content 为空、纯文本轮 tool_calls 为空，二者互斥」被真实模型打破（实测落库正文 = `"I'll check your todo list for you.你的待办列表如下：…"`）。另：工具轮耗尽 `max_turns` 时用节点收尾文本兜底，不再给空回复。
  3. **新会话首条消息不再自杀**（`19c12a8`）：`onSessionCreated={setSessionId}` 让 `sessionId` 从 `null` 变为新 id，触发了依赖 `[initialMessages, sessionId]` 的 effect，把刚发起的请求 abort 掉。
  - 测试结果（合并后的树上复跑）：后端 **380 / 83.39%**、`ruff` 全过；前端 **107 / 19 文件**、`npm run build` 零错误。
  - 残留修复轮（`21abe5d`/`dd7e493`，均为全分支评审提出、用户授权后修）：收尾先取消并**等待**生产者再动 db（消除共享 `AsyncSession` 竞态，断开与静默上限两路径共用）；会话切换导致的中止不再往里刚清空的列表写错误气泡。
  - 真实模型端到端（运行中的服务，LangGraph 引擎）：Q1 `帮我看一下我的待办列表`（路由 tools→`todo_list`）与 Q2 `帮我看看wiki里有什么`（路由 kb→`kb_search`，启动后 19.4s 静默、期间发 1 次心跳、仍完整返回）均无英文独白，落库 `extra` 含 `tool_calls` + `trajectory`（Q2 另有 `citations`），流式拼接 == 落库 `content`，事件序列 `session,chunk,done` 无 `error`。
  - 真实模型端到端（运行中的服务，LangGraph 引擎）：Q1 `帮我看一下我的待办列表`（路由 tools→`todo_list`）与 Q2 `帮我看看wiki里有什么`（路由 kb→`kb_search`，启动后 19.4s 静默、期间发 1 次心跳、仍完整返回）均无英文独白，落库 `extra` 含 `tool_calls` + `trajectory`（Q2 另有 `citations`），流式拼接 == 落库 `content`，事件序列 `session,chunk,done` 无 `error`。
  - 合并后**控制者独立复验**：同一慢路径自然静默 **21.15s**（>15s 心跳阀值，心跳已发）而答案仍完整 1121 字、无英文独白、`extra` 三键齐全、流式与落库逐字节相等（1121==1121）。
- [x] **推送**：R2 与流式三修合并后 `develop` 已推 GitHub + Gitee；`main` 待发布时合并（§13 R1）。
- [ ] **合并 `feat/rag-citation-source`**（R3 / M5 引用来源标注：`app/rag/citations.py` + `SourceConnector.describe_sources` + Obsidian 身份解析 + `kb_search` 接线 + 前端标签/跳转，共 6 个提交 `0f76e0e..b813b79`）→ `develop`——**待维护者批准**。
  - 验收：后端 393 / 83.60%、`ruff` 全过；前端 112 / 19 文件、`build` 零错误（分支 tip 实测）。
  - 未做：真实模型端到端 + 浏览器点击跳转的目视复验（需运行服务与预置 Wiki 数据），已列入合并前人工复验清单。
- [ ] **合并 `fix/citation-jump-target`**（R3.1 + R3.2 修复：人工核验发现的四类问题——跳转落点不依赖列表、wiki 不降级为文档、同轮多次检索编号累加、正文 `[n]` 可点，四个提交 `14d7aa2..1816bb7`）→ **先合入 `feat/rag-citation-source`**（缺陷属 R3 引入、R3 尚未合并），再随 R3 一并进 `develop`——**待维护者批准**。
  - 验收：后端 394 / 83.65%、`ruff` 全过；前端 125 / 20 文件、`build` 零错误（分支 tip 实测）。
  - 回归用例：wiki 缺 `page_id` 必须不可点（`utils/citation.test.ts`）、目标不在列表仍能打开详情（`KbPanel.test.tsx`）、同轮两次 `kb_search` 编号连续且累加（`test_kb_tool.py`）、正文 `[n]` 可点且无对应引用不做死链（`ChatPanel.test.tsx`）。
  - 已知边界：历史消息 citations 已落库不重算（旧消息需重新提问才有效）。
- [ ] **推送 `private-docs`**：含本轮累积记录（`docs/优化落地记录.md` R2 / R2.1 / R3 / R3.1 / R3.2 节、`docs/plans/` 两份 R3 设计与实施计划、R2 实施计划与预检修订、`面试准备/2026-09-15-流式截断与独白泄漏复盘.md`、`面试准备/2026-09-16-引用溯源与跳转复盘.md`）——**待维护者确认**（按 §11 只推 GitHub）。


---

## 13. 总路线图（R0-R7）

> 定稿依据：`docs/plans/2026-09-15-scope-convergence-design.md`（目标 C：面试优先 + 兼顾自用）（属 `private-docs` 分支）。
> 准入规则：新需求必须能回答"进哪个镜头"（见 `DEMO_SCRIPT.md`）或"讲出什么数据",否则进 §11 冻结清单。

**执行顺序（2026-09-15 调整：R1 挪到最后）**：R2 → R3 → R4 → R5 → R6 → R7 → **R1**（云上演示）。

| 序 | 批次 | 事项 | 预估 | 验收位置 |
|---|---|---|---|---|
| 0 | **R0** | 计划收敛（本文件改造 + `DEMO_SCRIPT.md` + 清理双份分叉） | 0.5 天 | ✅ 本批 |
| 1 | **R2** | **Q1 trajectory**：全量落 `Message.extra` + 前端可见（`AGENT_TRACE_ENABLED`） | ~1 小时（同日完成） | 镜头 2 |
| 2 | **R3** | **M5 引用来源标注**：区分 `Wiki/空间/页面` 与 `文档/页码` | ~2 天（同日完成） | ✅ 镜头 1 |
| 3 | **R4** | **P-F1 MCP 地基**：`app/mcp/` + `funds/quotes.py` + `fund_tool` | ~1 周 | 镜头 3 |
| 4 | **R5** | **评测闭环**：J3 进 Jenkins 门槛 + Q5 双引擎对照报告（共用 `rag_eval`） | ~3 天 | 镜头 5 |
| 5 | **R6** | **N2 质量看板**：N2.1-N2.6 + N2.8 | ~1.5 周 | 镜头 5 |
| 6 | **R7** | **基金自用闭环（必做）**：P-F2 持仓 → P-F3 调度 → P-F4 通知 | ~1.5 周 | 自用价值 |
| 7 | **R1** | **P5 云上可演示（最后）**：服务器 + Compose/Nginx/HTTPS 实测 + README 截图 + 面试问答 + Demo 排练 | ~1 周 | 镜头 1-6 可跑通 |

- [x] **R0** 计划收敛（本批交付）：三份计划改造 + 冻结清单（带重启条件）+ `DEMO_SCRIPT.md`
- [x] **R2** Q1 trajectory 落库与前端展示
- [x] **R3** M5 引用来源标注（`feat/rag-citation-source`：标签纯函数 + 连接器身份 seam + 前端跳转；后端 393 / 83.60%、前端 112 / build 零错误）
- [ ] **R4** P-F1 MCP 地基与 `fund_tool`
- [ ] **R5** J3 评测门槛进 Jenkins + Q5 双引擎对照报告
- [ ] **R6** N2.1-N2.6、N2.8 质量看板
- [ ] **R7** P-F2 持仓 → P-F3 调度 → P-F4 通知（必做）
- [ ] **R1** 云上可演示（P5）：服务器选购与环境初始化、Compose+Nginx+HTTPS 实测、README 截图、面试问答 20 问、Demo 排练

> **排序逻辑（2026-09-15 调整）**：先做**不依赖真环境**的能力（R2 轨迹最便宜且立刻改善可讲性 → R3 引用 → R4 MCP 新子系统 → R5 数据资产 → R6 看板 → R7 自用闭环），**R1 云上演示放最后**一次性完成部署与排练。
> **代价（已知并接受）**：R2–R7 开发期**没有线上环境**，各能力无法即时在真环境验证与截图；`DEMO_SCRIPT.md` 的 6 镜头要到最后才能完整排练。若中途需要线上验证，可临时提前 R1（其余批次不阻塞它）。
> **实施计划粒度**：R1-R7 各自开工时另写计划（`docs/plans/YYYY-MM-DD-<批次>-<主题>.md`），**不超前写**——R4 需先定 MCP server 选型，R6 依赖 R5 产出的评测执行器。
> **每批门槛**：见 §14。

---

## 14. 验收总门槛

> 本清单为**验收快照**（@ `1816bb7` R3.2 分支 tip 实测；上一快照 @ `af9ed5f` R2 分支 tip），数字随基线推进可能滞后；`develop` 基线见 §1。

- [x] 后端 `pytest` 全绿且覆盖率 ≥ 80%（**394 / 83.65%**）
- [x] 后端 `ruff check .` 全过
- [x] 前端 `npm test` 全绿（**125**）、`npm run build` 零错误
- [x] CLI `pytest` 全绿（**15**）、`ruff` 全过
- [x] 删除操作全量软删除（`deleted_at`/`deleted_by`）且列表/检索已过滤（批次 L：已完成）
