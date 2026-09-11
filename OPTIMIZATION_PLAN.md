# 🛠 Copilot-Lite 优化与演进计划（OPTIMIZATION_PLAN）

> 定位：**作品展示 + 未来企业落地**。原则：留口优先、不过度设计、一个提交一个问题。
> 规范：[AGENTS.md](AGENTS.md)（§12 分层 / §14 契约 / §15 追踪 / §18 Prompt / §6 安全）。
> 关联：`docs/知识库Wiki技术方案.md`、`docs/优化落地记录.md`、`面试准备/知识库架构选型-连接器化与混合租户.md`。

---

## 1. 进度总览

| 批次 | 主题 | 状态 |
|---|---|---|
| A | CLI 完整可用（双入口闭环） | ✅ 完成 |
| B | 契约与可观测性（对齐 AGENTS.md） | ✅ B1/B2/B4 完成（B3/B5 暂缓） |
| C | 性能与正确性 | ✅ C1/C2/C5 完成（C3/C4 暂缓） |
| D | RAG / Agent 能力深度 | ✅ D1/D2/D4 完成（D3 并入 G-M2；D5 暂缓） |
| E | 产品体验（前端 UX） | ✅ E1–E4 完成（E5 暂缓） |
| F | 模型配置页面化 | ✅ 完成 |
| G | 本地 Wiki 知识库（Obsidian 接入） | ✅ M1/M1.5 完成；M2/M3/M4 待做 |
| H | 连接器化收口（Obsidian → connectors） | ✅ 完成 |
| I | 企业化：租户与权限（混合模式） | ⬜ 待做（下一步） |
| J | 可靠性与治理（企业可运营） | ⬜ 待做 |
| K | 连接器生态与直连能力 | ⬜ 待做 |
| Z | 其他暂缓项（B3/B5/C3/C4/D5/E5） | ⏸ 暂缓 |

**当前基线**：后端 **201 用例 / 覆盖率 80.80%**、ruff 全过；前端 **42 用例**、build 零错误；CLI **15 用例**、ruff 全过。

---

## 2. 已完成（累计，均已入 `develop`）

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

---

## 3. 批次 G · 本地 Wiki 知识库（收尾）

> 方案：`docs/知识库Wiki技术方案.md`（v2）；选型：`面试准备/知识库Wiki技术选型与路线复盘.md`。

- [x] **G-M1 导入与索引**：受管副本 + 本地路径/zip 导入 + `WikiParser`（frontmatter/双链/嵌入/标签）+ 增量同步（rel_path 幂等 + hash 移动检测 + 级联删除）+ 空间/页面/链接 API。
- [x] **G-M1.5 管理 UI**：Wiki 页签、空间创建/删除、zip 上传、手动同步、页面树+搜索+分页、页面浏览、反向链接/出链面板。
- [ ] **G-M2 双链检索增强**（含原 D3）
  - 命中页 1-hop 邻居扩展召回（`WIKI_LINK_EXPANSION_ENABLED`/`WIKI_EXPAND_HOPS`，可开关 A/B）；
  - 引用溯源带 Wiki 路径，前端 `[n]` 可点击跳转到 chunk/页面；
  - 用 `scripts/rag_eval.py` 对比 recall@K / MRR。
- [ ] **G-M3 图谱可视化**
  - `GET /wiki/graph?space=&tag=&limit=` 返回 nodes/edges；
  - 前端 `react-force-graph-2d`（点击跳页、按空间/标签过滤、节点数上限）。
- [ ] **G-M4 轻量本体（可选）**：类型化链接 `wiki_link.relation`（约 8 个受控关系）+ 按关系加权/着色；**不做完整本体**。

---

## 4. 批次 I · 企业化：租户与权限（**混合模式**，下一步）

> 模型：`Tenant（隔离边界）→ Workspace（协作/知识空间）→ Membership(角色) → document.acl`。
> 演示模式默认单租户 + 默认 workspace，行为与现状一致（无感）。

- [ ] **I1 租户模型与迁移**：`tenants` / `workspaces` / `workspace_members`（role: owner/admin/member/viewer）；seed 默认租户+workspace。
- [ ] **I2 资源归属**：`documents` / `wiki_spaces` 增加 `tenant_id` / `workspace_id`；摄取时按当前上下文写入。
- [ ] **I3 文档级 ACL**：`documents.acl`（可访问 workspace/role/user 列表；默认继承 workspace）。
- [ ] **I4 检索过滤链（企业命门）**：向量 payload 过滤 + BM25 JOIN 过滤 + 引用链路，统一按 `tenant → 可访问 workspace → ACL`；补跨租户/跨 workspace 不可见回归测试。
- [ ] **I5 请求上下文**：从 JWT / 请求头解析 tenant/workspace（缺省回退默认，兼容 demo）。
- [ ] **I6 角色与前端**：workspace 切换器、成员管理、按角色隐藏危险操作（与 HITL 联动）。

---

## 5. 批次 J · 可靠性与治理（企业可运营）

- [ ] **J1 异步摄取/同步**：`jobs` 表 + 后台执行 + 进度查询 + 重试/死信；import/sync 不再阻塞 HTTP（大 vault）。先 asyncio，后换队列。
- [ ] **J2 可观测性**：OpenTelemetry 追踪（检索/LLM/工具 span）+ Prometheus 指标 + **按 tenant 的 token/成本统计**。
- [ ] **J3 评测进 CI**：`scripts/rag_eval.py` / `rag_eval_ragas.py` 接入流水线，设 recall@K / faithfulness 阈值门槛。
- [ ] **J4 审计日志**：工具调用 + 敏感操作（删除/权限变更/登录）审计表（request_id/user/tenant/action/result）。
- [ ] **J5 软删除与合规**：业务数据 `deleted_at`；提供彻底删除接口（GDPR 可删）。
- [ ] **J6 密钥与配置分级**：Secret Manager（Vault/K8s Secret）接入；公开/敏感/开关三类配置分离。
- [ ] **J7 基础设施可替换**：Redis（限流/预算/缓存，见 C3）、任务队列、Qdrant 集群、对象存储 S3。

---

## 6. 批次 K · 连接器生态与直连能力

> 定位：外部源始终是单一事实源；系统索引是可重建的派生数据。

- [ ] **K1 连接器管理与选择**：API/UI 列出可用连接器，按连接器创建空间（当前仅 obsidian）。
- [ ] **K2 新连接器**：S3/对象存储、Git 仓库、通用本地目录；后续 SharePoint / Confluence（企业常见）。
- [ ] **K3 直读工具（成本回退）**：`vault_list` / `vault_search(grep)` / `vault_read`——大文件/低频文件不必全文入索引，直接读。
- [ ] **K4 Obsidian 写回（可选）**：经 Obsidian Local REST API / MCP（编辑在 Obsidian，检索在平台，不自造编辑器）。
- [ ] **K5 增量与权限映射**：外部源增量游标 + ACL 拉取映射到 workspace/acl。

---

## 7. 暂缓批次（原分析项，按需再做）

- [ ] **B3 分层收口**：service 层抽离、`core` 去 FastAPI 依赖（`core/budget.py`）。
- [ ] **B5 OpenAPI → TS 类型自动生成**：`openapi-typescript` 替手写 `types.ts`。
- [ ] **C3 Redis 落地**：限流/每日预算从进程内存迁 Redis（带内存回退），支撑多实例（与 J7 合并做）。
- [ ] **C4 语义缓存（答案级）**：query 向量近邻命中复用答案（带 TTL）。
- [ ] **D5 BM25 升级**：PostgreSQL FTS（tsvector + GIN + ts_rank，jieba）替代 ILIKE 伪实现。
- [ ] **E5 用户反馈闭环**：回答 👍/👎 落库，驱动检索/生成评测。

---

## 8. 总路线图（建议顺序）

| 顺序 | 事项 | 价值 | 依赖/说明 |
|---|---|---|---|
| 1 | **G-M2 双链检索增强 + 引用可点击** | 作品亮点、RAG 深度 | 复用现有检索/评测 |
| 2 | **G-M3 图谱可视化** | 作品亮点、演示效果 | 新增 `react-force-graph-2d` |
| 3 | **J1 异步摄取/同步** | 可靠性、解锁大 vault | 当前 import/sync 同步阻塞 |
| 4 | **I1–I4 租户 + workspace + ACL** | 企业落地硬门槛 | 检索三路统一过滤 |
| 5 | **J2 可观测 + J3 评测进 CI** | 企业可运营/质量门槛 | 复用 request_id / golden set |
| 6 | **K 连接器生态 + 直读/MCP 写回** | 多来源、体验闭环 | 基于 H 的连接器接缝 |
| 7 | 暂缓项（B3/B5/C3/C4/D5/E5） | 按需 | C3 并入 J7 |

> 原则：**单体模块化 + 配置驱动 + 基础设施可替换**；不到压力点不拆微服务。每项仍遵循「一功能一分支 + 防回归测试 + 全绿 + 经批准后合并」。

---

## 9. 验收总门槛

- [x] 后端 `pytest` 全绿且覆盖率 ≥ 80%（**201 / 80.80%**）
- [x] 后端 `ruff check .` 全过
- [x] 前端 `npm test` 全绿（**42**）、`npm run build` 零错误
- [x] CLI `pytest` 全绿（**15**）、`ruff` 全过
- [ ] 每个新批次：分支开发 → 独立测试全绿 → **经批准**后合并
