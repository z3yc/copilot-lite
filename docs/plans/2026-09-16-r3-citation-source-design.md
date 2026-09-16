# R3 · M5 引用来源标注（设计）

> 路线图位置：`OPTIMIZATION_PLAN.md` §13 R3（验收位置：`DEMO_SCRIPT.md` 镜头 1）。
> 上游需求原文：引用中明确区分「Wiki / 空间 / 页面」与「文档 / 页码」。
> 准入自检：进镜头 1（引用溯源演示）✅；不新增配置项；不动检索主干（M2/M3/M4 继续冻结）。

---

## 1. 目标与验收

1. 每条引用带**类型标签**：`Wiki / 空间名 / 页面名` 或 `文档 / 文件名 / 第 N 页`（无页码则 `文档 / 文件名`）。
2. **点击可跳**：Wiki 引用 → 切 Wiki 页签、必要时切空间、打开该页面；文档引用 → 切知识库页签、复位过滤、展开该文档详情。
3. 历史旧格式 `citations`（无类型字段）不崩，降级为纯文本、不可跳。
4. 不触碰检索主干；不新增配置项；不重建索引。

## 2. 架构决策

### 2.1 身份解析走**连接器 seam**（AGENTS §12）

AGENTS §12：知识来源统一走 `app/connectors/`，「检索 / 权限 / Agent **不感知具体来源**」。
Wiki 身份（`page_id` / `space_id` / 空间名）是 Obsidian 连接器的知识，**不得**在 `kb_tool` 里直查 `wiki_pages`。

```
kb_tool ──> connectors.registry.collect_source_meta(db, user_id, doc_ids)   # 泛型，无 wiki 知识
                     │ 遍历已注册连接器（默认实现返回 {}）
                     └─ ObsidianConnector.describe_sources()
                            └─ obsidian/service.describe_sources()
                               一条 WikiPage JOIN WikiSpace 查询
                               （user_id 过滤 + deleted_at IS NULL；document_id 复用现有索引）
kb_tool ──> app/rag/citations.py   # 纯函数：来源结构化 + 标签格式化（唯一展示口径）
```

- `SourceConnector` 新增**非抽象**默认方法 `describe_sources(db, user_id, document_ids) -> dict`（返回 `{}`）。
  未来 K2 解冻接入 S3/Confluence 时，只需实现该方法即自动获得同等引用体验，工具层零改动 → 这正是 seam 的价值。
- **不重建索引**：身份在查询期解析；存量 chunk 只有 `wiki_space/wiki_path/wiki_title` 快照，够做标签兜底。

### 2.2 为什么不在摄取期把 page_id 写进 chunk meta

- 存量 chunk 缺字段 → 必须重导/重建索引才能补齐（有成本、有停机面）；
- meta 是**快照**，页面重建/迁移后会过期 → 脏引用；
- 查询期 JOIN 命中率与正确性更高，且天然带 `user_id` + 软删除过滤（AGENTS §6.3/§13）。

### 2.3 为什么用 App 层显式状态做跳转（不用事件总线 / hash 路由）

- `App.tsx` 是页签式 SPA（无路由），目标面板靠 props 驱动最直观，vitest 可直接断言；
- 事件总线隐式、难追；hash 路由属 B5 相邻范围（已冻结），超 R3。

## 3. 契约

`Message.extra.citations[i]`：

```jsonc
{
  "index": 1,
  "chunk_id": "...",
  "document_id": "...",
  "snippet": "前 160 字",
  "source": "Wiki / 我的笔记 / 方法论",     // 带类型的展示标签（唯一展示口径）
  "source_kind": "wiki" | "document",
  "page": 3,                                 // 文档页码；Wiki/无页码为 null
  "wiki": {                                  // 仅 source_kind=wiki 且解析成功时出现
    "page_id": "...", "space_id": "...", "space_name": "我的笔记", "rel_path": "笔记/方法论.md"
  }
}
```

**与初版方案的一处收敛（已确认）**：去掉冗余 `source_label`，`source` 字段本身改为带类型的标签。
两个字段装同一字符串迟早分叉；`source` 仍在，老前端（`title`）与 CLI 展示不受影响。

**类型判定优先级**

1. 连接器身份（`source_kind=wiki` + `wiki` 导航对象）；
2. chunk meta 的 `wiki_space`/`wiki_title`（页面行已软删/重建 → 标签仍正确，**无** `wiki` 对象 → 不可跳）；
3. 否则 `source_kind=document`，标签 `文档 / {document_title} / 第 N 页`。

**LLM 可见口径同步**：`kb_search` 回给模型的「来源」字符串用同一标签（模型复述来源不再裸标题），带回归用例锁住。

## 4. 兜底与安全

| 场景 | 行为 |
|---|---|
| 旧格式 citation（无 `source_kind`） | 显示 `source` 纯文本，不可跳 |
| Wiki 页已软删 / 已重建 | 标签正确，不提供跳转 |
| document_id 已删 / 无权 | 跳后面板按既有 404 兜底提示；不泄露资源存在性（AGENTS §6.4） |
| 跨用户 | JOIN 强制 `user_id` 过滤；构造"检索命中 A 文档但页面行属 B"的脏数据回归（AGENTS §6.3） |
| 无引用 | 不渲染来源区（现状不变） |
| 连接器抛错 | `collect_source_meta` 捕获并记 WARNING，退回 meta 兜底（**增强不能拖垮主链路**，AGENTS §10） |

## 5. 改动清单

**后端**

| 文件 | 改动 |
|---|---|
| `app/connectors/base.py` | `SourceConnector.describe_sources` 默认实现（返回 `{}`） |
| `app/connectors/registry.py` | `collect_source_meta(db, user_id, document_ids)`（遍历 + 容错） |
| `app/connectors/obsidian/connector.py` | 转调 service |
| `app/connectors/obsidian/service.py` | `describe_sources`：单条 JOIN 查询 |
| `app/rag/citations.py`（新） | `build_source_label` / `build_citation`（纯函数，无来源知识） |
| `app/tools/kb_tool.py` | 一次 `collect_source_meta` + 用 `citations.py` 构造；LLM 可见「来源」同口径 |

**前端**

| 文件 | 改动 |
|---|---|
| `types.ts` | `Citation` 增 `source_kind` / `page` / `wiki` |
| `ChatPanel.tsx` | `onOpenCitation` prop；标签渲染；可跳才可点（a11y 保持 role/tabIndex/aria-label） |
| `App.tsx` | `openTarget` 状态 + 页签切换 + 传 `openTarget`/`onOpened` |
| `WikiPanel.tsx` | 消费 `openTarget`（必要时切空间）→ `openPage` → `onOpened` |
| `KbPanel.tsx` | 消费 `openTarget`（复位搜索/分类）→ 列表就绪后 `toggleDetail` → `onOpened` |

**文档**：本设计 + `2026-09-16-r3-citation-source.md`（实施计划）+ `docs/优化落地记录.md` R3 小节。

## 6. 测试与验收

- 后端：`test_kb_tool.py` 断言更新（新「来源」口径）；新增 `test_citation_sources.py`（wiki 标签+导航字段 / 文档页码 / meta 兜底 / 软删页面不导航 / 跨用户不泄露 / 连接器抛错回退）。
- 前端：`ChatPanel.test.tsx`（新格式渲染 + 回调 + 旧格式兼容）；`WikiPanel.test.tsx` / `KbPanel.test.tsx`（`openTarget` 一次性消费）。
- 命令：`pytest`（≥80% 覆盖率）、`ruff check .`、`npm test`、`npm run build`。

## 7. 风险

| 风险 | 处置 |
|---|---|
| 契约字段新增导致前端旧数据渲染异常 | `source_kind` 可选；无则走纯文本分支；专门留旧格式用例 |
| 额外 JOIN 增加检索延迟 | 单次批量查询、`document_id` 已有索引；结果为空则零成本 |
| 跨面板跳转出现"打开了但看不到" | `onOpened` 一次性消费 + 目标不在列表时面板主动复位过滤后再展开 |
| prompt 口径变化影响模型行为 | 工具描述未变，仅返回数据标签变化；`test_kb_tool` 断言锁住，不改 `PROMPT_VERSION`（无模板变更） |
