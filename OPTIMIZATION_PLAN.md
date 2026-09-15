# 🛠 Copilot-Lite 优化与演进计划（OPTIMIZATION_PLAN）

> 定位：**作品展示 + 未来企业落地**。原则：留口优先、不过度设计、一个提交一个问题。
> 规范：[AGENTS.md](AGENTS.md)（§6 安全红线 / §12 分层 / §14 契约 / §15 追踪 / §18 Prompt）。
> 关联：`docs/知识库Wiki技术方案.md`、`docs/优化落地记录.md`、`面试准备/知识库架构选型-连接器化与混合租户.md`、`面试准备/FIX_LOG_WIKI_RAG_RUNTIME.md`。

---

## 1. 进度总览

| 批次 | 主题 | 状态 |
|---|---|---|
| A | CLI 完整可用（双入口闭环） | ✅ 完成 |
| B | 契约与可观测性（对齐 AGENTS.md） | ✅ B1/B2/B4 完成（B3/B5 暂缓） |
| C | 性能与正确性 | ✅ C1/C2/C5 完成（C3/C4 暂缓） |
| D | RAG / Agent 能力深度 | ✅ D1/D2/D4 完成（D3 并入 G-M2、已完成；D5 暂缓） |
| E | 产品体验（前端 UX） | ✅ E1–E4 完成（E5 暂缓） |
| F | 模型配置页面化 | ✅ 完成 |
| G | 本地 Wiki 知识库（Obsidian 接入） | ✅ M1/M1.5/M2 + 导入体验 P1–P3 + **M3 图谱可视化** 完成；M4 待做 |
| H | 连接器化收口（Obsidian → connectors） | ✅ 完成 |
| **L** | **软删除与审计（强制红线）** | ✅ 完成（后端+回收站前端） |
| I | 企业化：租户与权限（混合模式） | ⬜ 待做 |
| J | 可靠性与治理（企业可运营） | 🟡 **J1 完成**；J2–J7 待做（J5 并入 L） |
| K | 连接器生态与直连能力 | ⬜ 待做 |
| M | 知识来源范围（RAG / Wiki 检索分流） | ⏸ 已设计（方案 C），待排期 |
| N | 管理后台与质量看板（作品集为主，企业留口） | ⏸ 已设计，见 [ADMIN_PLAN.md](ADMIN_PLAN.md) |
| Z | 其他暂缓项（B3/B5/C3/C4/D5/E5/L7） | ⏸ 暂缓 |

**当前基线**：后端 **246 用例 / 覆盖率 80.04%**、ruff 全过；前端 **75 用例**、build 零错误；CLI **15 用例**、ruff 全过。
（后端/前端为分支 `feat/wiki-graph` 上的数据；CLI 沿用 `develop` 基线。）

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

### 在分支上完成，**待批准合并**（`feat/wiki-import-files` → `...` → `fix/wiki-delete-safety`）

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
- [ ] **G-M4 轻量本体（可选）**：类型化链接 `wiki_link.relation` + 按关系加权/着色；**不做完整本体**。

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

- [ ] **I1 租户模型与迁移**：`tenants` / `workspaces` / `workspace_members`（owner/admin/member/viewer）；seed 默认租户+workspace。
- [ ] **I2 资源归属**：`documents` / `wiki_spaces` 增加 `tenant_id` / `workspace_id`；摄取时写入。
- [ ] **I3 文档级 ACL**：`documents.acl`（可访问 workspace/role/user；默认继承 workspace）。
- [ ] **I4 检索过滤链（企业命门）**：向量 payload + BM25 JOIN + 引用链路统一按 `tenant → 可访问 workspace → ACL`；跨租户/跨 workspace 不可见回归测试。
- [ ] **I5 请求上下文**：从 JWT/请求头解析 tenant/workspace（缺省回退默认，兼容 demo）。
- [ ] **I6 角色与前端**：workspace 切换器、成员管理、按角色隐藏危险操作（与 HITL 联动）。

---

## 6. 批次 J · 可靠性与治理

- [x] **J1 异步摄取/同步**：`jobs` 表 + 后台执行 + 进度查询 + 重试/死信；import/sync 不再阻塞 HTTP。
      _实现：`app/core/jobs.py` 通用状态机（handler 注册表 + 限并发/超时 + 自动重试→dead）+ `Job` 模型与迁移
      + `/jobs` 列表/详情/重试（按 `user_id` 隔离）+ Wiki 导入/同步接入（`JOBS_ENABLED` 开→202+job_id，关→内联回退旧行为）
      + 前端轮询进度（可取消）。_
- [ ] **J2 可观测性**：OpenTelemetry（检索/LLM/工具 span）+ 指标 + 按 tenant 的 token/成本统计。
- [ ] **J3 评测进 CI**：`rag_eval.py` / `rag_eval_ragas.py` 阈值门槛。
- [ ] **J4 审计日志**：与 L3 联动，统一审计表（敏感操作）。
- [ ] **J6 密钥与配置分级**：Secret Manager 接入。
- [ ] **J7 基础设施可替换**：Redis（C3）、任务队列、Qdrant 集群、S3。
- [x] **J5 软删除与合规** → 已提升为 **批次 L**（更严格：全部软删除+可溯源）。

---

## 7. 批次 K · 连接器生态与直连能力

- [ ] **K1 连接器管理与选择**：API/UI 列出可用连接器，按连接器创建空间。
- [ ] **K2 新连接器**：S3/对象存储、Git、通用本地目录；后续 SharePoint / Confluence。
- [ ] **K3 直读工具（成本回退）**：`vault_list` / `vault_search(grep)` / `vault_read`。
- [ ] **K4 Obsidian 写回（可选）**：Local REST API / MCP。
- [ ] **K5 增量与权限映射**：外部源增量游标 + ACL 映射。

---

## 8. 批次 M · 知识来源范围（RAG / Wiki 检索分流）—— 已设计，待排期

> **决策（本会话讨论锁定）**：采用**方案 C**——不拆两个工具，保持**统一索引 + 单一 `kb_search`**，用可选 `scope` 表达范围，默认全库，收窄为空时自动回退。
> 背景：Wiki 页面已与上传文档同走 `documents/chunks/Qdrant` 一条摄取/检索链路，差异在**增强策略**（Wiki 有双链邻居扩展/图谱）而非检索主干，故拆工具只会增加路由犯错面。
> 现状缺口：`document.source_type` **未写入 Qdrant payload**（payload 仅有 `document_id/chunk_id/user_id/meta/deleted`），故当前无法做**检索级**来源过滤。

- [x] **M1 来源元数据入检索层**：`document.source_type` 写入 Qdrant payload（与 BM25 的 Document JOIN 对齐），使 scope 过滤在**向量 + BM25 同一条过滤链**生效；需一次性重建/回填索引。
      _已完成（实测 `rag/pipeline.py` 写 payload `source_type`，`rag/retriever.py` 向量/BM25 双路读取；对应 ADMIN_PLAN §9 N0.4 已勾选）。_
- [ ] **M2 `kb_search` 增加可选 `scope`**：枚举 `all | docs | wiki`，**默认 all**；仅当用户**显式表达**范围（“只在我的 wiki 里”/“根据我上传的文档”）才收窄；无法判断一律 all。
- [ ] **M3 空结果自动回退**：收窄检索为空时**自动放宽到 all**，并如实告知用户已放宽范围——杜绝“猜错范围即漏答”。
- [ ] **M4 策略随 scope 联动**：`scope=wiki` 强制开双链邻居扩展；`scope=docs` 关闭该扩展（将现有 `WIKI_LINK_EXPANSION_ENABLED` 从全局开关细化为按 scope）。
- [ ] **M5 引用来源标注**：引用中明确区分 `Wiki/空间/页面` 与 `文档/页码`（方案 A 的补强，**可独立先做**，不依赖 M1）。
- [ ] **M6（可选）UI 知识范围选择器**：聊天框“知识范围”下拉或 `@wiki` 提及，提供零 LLM 猜测的确定性入口（方案 D，作为 scope 的上层输入）。

---

## 9. 暂缓批次（按需）

- [ ] **B3 分层收口**：service 层抽离、`core` 去 FastAPI 依赖。
- [ ] **B5 OpenAPI → TS 类型自动生成**。
- [ ] **C3 Redis 落地**（并入 J7）。
- [ ] **C4 语义缓存（答案级）**。
- [ ] **D5 BM25 升级 PostgreSQL FTS**。
- [ ] **E5 用户反馈闭环**。
- [ ] **L7 用户注销/账号软删除**（承接批次 L）：账号注销/自助删除统一走**软删除**（`deleted_at` / `deleted_by` / 可选 `delete_reason`）+ **审计留痕**（request_id/user_id/资源/时间/结果）；注销后禁止登录、列表与检索按用户隔离过滤，数据默认可恢复；彻底删除仅限合规（GDPR）且写审计。**后续排期时一并做。**

---

## 10. 待合并与推送（**需批准**）

> 按约定：合并 / 推送前需维护者确认。

- [ ] **合并 `feat/jobs-async-ingest`**（J1 异步摄取/同步：jobs 表 + 状态机 + Wiki 接入 + 前端轮询）→ `develop` → `main`。
- [ ] **合并修复分支**：`fix/wiki-delete-safety`（tip，含 M2 + 引用 + 认知修复 + 嵌入/LangGraph/重排修复 + P1–P3 + 编码修复 + 删除护栏）→ `develop` → `main`。
- [ ] **推送**：GitHub + Gitee 的 `develop` / `main`。
- [ ] **推送 `private-docs`**：含本轮记录（`docs/优化落地记录.md`、`FIX_LOG_*`）。

---

## 11. 总路线图（建议顺序）

| 顺序 | 事项 | 价值 | 依赖/说明 |
|---|---|---|---|
| 0 | **合并待批准分支 + 推送**（§10） | 消除已知 bug/数据风险 | 需批准 |
| 1 | **批次 L 软删除与审计** | 数据安全红线、可溯源 | 事故驱动，优先 |
| 2 | **G-M3 图谱可视化** | 作品亮点、演示效果 | `react-force-graph-2d` |
| 3 | **J1 异步摄取/同步** | 可靠性、解锁大 vault | ✅ 已完成（`feat/jobs-async-ingest`） |
| 4 | **I1–I4 租户 + workspace + ACL** | 企业落地硬门槛 | 检索三路统一过滤 |
| 5 | **J2 可观测 + J3 评测进 CI** | 企业可运营/质量门槛 | 复用 request_id / golden set |
| 6 | **K 连接器生态 + 直读/MCP 写回** | 多来源、体验闭环 | 基于 H 的接缝 |
| 7 | **批次 M 知识来源范围（scope）** | 多来源精准检索、为 I4 ACL 铺路 | 默认 all + 空回退；需 payload 回填索引；M5 可先做 |
| 8 | **批次 N 管理后台与质量看板** | 作品集亮点 + 企业治理留口 | 见 [ADMIN_PLAN.md](ADMIN_PLAN.md)；依赖 M1 |
| 9 | 暂缓项（B3/B5/C3/C4/D5/E5） | 按需 | C3 并入 J7 |

> 原则：**单体模块化 + 配置驱动 + 基础设施可替换**；每项遵循「一功能一分支 + 防回归测试 + 全绿 + 经批准后合并」。

---

## 12. 验收总门槛

- [x] 后端 `pytest` 全绿且覆盖率 ≥ 80%（**221 / 80.10%**）
- [x] 后端 `ruff check .` 全过
- [x] 前端 `npm test` 全绿（**47**）、`npm run build` 零错误
- [x] CLI `pytest` 全绿（**15**）、`ruff` 全过
- [ ] 删除操作全量软删除（`deleted_at/deleted_by`）且列表/检索已过滤（批次 L）
