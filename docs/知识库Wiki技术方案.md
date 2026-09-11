# Copilot-Lite 本地知识库接入 Wiki —— 技术方案（v2 收敛版）

> 目标：把本地 Obsidian Wiki（Markdown 双链笔记）导入现有 RAG 知识库，实现**索引检索 + 双链图谱 + 图谱可视化 + 检索增强**。
> 关联：[OPTIMIZATION_PLAN.md](../OPTIMIZATION_PLAN.md)、[AGENTS.md](../AGENTS.md)。
> 状态：**决策已锁定（v2）**，可按里程碑开分支落地。

---

## 1. 已确认的决策（v2）

| # | 决策项 | 结论 | 对方案的影响 |
|---|---|---|---|
| D1 | Wiki 来源 | **手动导入 Obsidian vault** | 需"导入通道"：本地路径 / 上传 zip；后端持有受管副本 |
| D2 | 读写权限 | **只读** | 不写回文件；页面只做浏览，不内建编辑器 |
| D3 | 同步方式 | **手动 + 定时** | `/wiki/sync` 手动触发 + 定时任务重扫受管副本 |
| D4 | 部署 | **兼顾后续云端** | 不能依赖"后端直读用户本机目录"；云端走 zip 上传通道 |
| D5 | 图谱可视化 | **需要** | `/wiki/graph` + 前端图谱页；渲染用 **`react-force-graph-2d`**（现成库） |
| D6 | 隔离 | **可选（默认按用户，支持共享空间）** | `wiki_space.owner_id` 可空 = 共享空间 |

> 关键推论：既然要"手动导入 + 云端"，就把 **vault 的"受管副本"落在后端存储**（`data/wiki/{scope}/{space}/`），
> 同步永远针对受管副本——本地托管时副本可由服务器路径导入，云端时由 zip 上传解压而来。**同一套同步逻辑两种形态通用。**

---

## 2. 总体架构

```
┌────────────────────────────── Web UI ──────────────────────────────┐
│  📚 知识库  │  🕸️ Wiki：页面树 / 页面浏览 / 反向链接 / 标签 / 图谱    │
└───────────────▲──────────────────────────────────────▲─────────────┘
                │ REST(/wiki/*)                         │ kb_search/wiki_*
┌───────────────┴──────────────────────────────────────┴─────────────┐
│ API  wiki.py（导入/同步/列表/详情/搜索/图谱）                        │
├─────────────────────────────────────────────────────────────────────┤
│ service  WikiService：导入→解压/落地受管副本→扫描→diff→摄取→链接图   │
├──────────────┬──────────────┬──────────── ──┬──────────────────────┤
│ 导入器        │ WikiParser    │ links.py      │ 摄取 pipeline（复用） │
│ path / zip    │ md+frontmatter│ 正/反向链接    │ parse→chunk→embed     │
│ (git 可选)    │ +[[双链]]+标签 │ +可选关系类型  │ →chunks+Qdrant        │
├──────────────┴──────────────┴───────────────┴──────────────────────┤
│ 存储：PostgreSQL(wiki_space/wiki_page/wiki_link) + documents/chunks  │
│        Qdrant（复用）  ·  受管副本：backend/data/wiki/...（只读扫描） │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 3. 导入与同步（含云端）

### 3.1 导入通道
| 通道 | 适用 | 落地 |
|---|---|---|
| **本地路径** | 自托管 / 本地部署（后端可访问） | 填服务器目录 → 复制/软链到受管副本（或直接登记只读根） |
| **上传 zip** | **云端通用**（用户本机 Obsidian vault 打包上传） | 解压到 `data/wiki/{scope}/{space}/`（限大小/条目数，防 zip 炸弹） |
| （可选）Git 仓库 | 进阶 | 仅允许白名单 host，防 SSRF；本期不做 |

> Obsidian vault 本质就是含 `.md` 的目录，导入即"复制/解压 + 登记空间"。

### 3.2 同步流程（幂等）
```
POST /wiki/spaces/{space}/sync
  1. 扫描受管副本 *.md → {rel_path: (mtime,size,sha256)}（排除 .obsidian/ 附件目录）
  2. 与 wiki_page diff：
       新增 → 解析→摄取→建 page
       修改 → 重解析→(删旧 chunks+向量)→重摄取→更新
       移动(内容 hash 相同, rel_path 变) → 仅更新 rel_path，不重嵌
       删除 → 级联清理 page/chunks/向量/link
  3. 重建该空间 wiki_link（全量或按变更页）
  4. 返回 {added, updated, moved, deleted, failed}
```
- **幂等主键**：`rel_path`（而非 content_hash）。
- 复用现有：内容去重、`/documents/{id}/retry`、分页、统一响应信封、后台任务调度。
- 定时：`WIKI_SCAN_INTERVAL_MINUTES`（0=仅手动），后台任务可开关（§8）。

---

## 4. 数据模型（新增）

### 4.1 `wiki_space`
| 字段 | 说明 |
|---|---|
| id, name, owner_id (FK users, **nullable=共享**), source_type (`local`/`upload`), root_path, last_synced_at, created_at | |

### 4.2 `wiki_page`
| 字段 | 说明 |
|---|---|
| id, user_id, space_id, rel_path, title, slug, document_id (FK documents), content_hash, mtime, size | 唯一约束 `(space_id, rel_path)` |

### 4.3 `wiki_link`
| 字段 | 说明 |
|---|---|
| id, user_id, space_id, source_page_id, target_slug, target_page_id(nullable=悬空), alias, kind(`link`/`embed`/`tag`), **relation**(nullable, 轻量本体用，见 §7) | |

> `documents.source_type` 新增 `wiki`；`chunks.meta` 增 `wiki_space/wiki_path/wiki_title`。

---

## 5. 解析与分块

- `WikiParser(DocumentParser)`（`app/rag/parsers/wiki_parser.py`，一行注册）：
  - frontmatter（title/tags/aliases）→ 元数据；
  - `[[目标]]`/`[[目标|别名]]`/`[[目标#标题]]` → 链接；`![[...]]` → embed；`#标签` → tag；
  - 代码块内 `[[ ]]` 不误判；正文原样保留供检索。
- 分块复用 `chunk_document`，meta 注入 wiki 字段。

---

## 6. 链接图 + 图谱可视化

- **反向链接**：`wiki_link` 按 `target_page_id` 反查 → 页面详情"被谁引用"。
- **图谱 API**：`GET /wiki/graph?space=&limit=&tag=` 返回 `{nodes:[{id,title,space,degree,tag}], edges:[{source,target,kind,relation}]}`。
- **前端可视化**：**`react-force-graph-2d`**（现成库，内部即 d3-force 布局 + Canvas 渲染，避免引入 three.js）；节点点击跳页面、按标签/空间过滤、限制节点数（默认 ≤300，超出提示）。
- **入库范围**：图谱为正式功能（非可选）。先做 2D 力导向；后续如需 3D，改用 `react-force-graph` 全家桶（API 一致）。

---

## 7. 检索增强（链接图驱动）

```
混合检索 TopN → 取命中页 1-hop 出链/入链页 → 各取 Top1 块
 → 合并去重 → 交叉编码器 Rerank → 注入
```
- 开关 `WIKI_LINK_EXPANSION_ENABLED`、`WIKI_EXPAND_HOPS=1`。
- 引用溯源：`[n] Wiki/空间/页面 > 标题路径`，前端可点击跳转（与未来 D3 合并）。
- 若启用轻量本体（§8）：扩展可**按关系类型加权**（如 `depends_on`/`part_of` 优先于 `related_to`）。

---

## 8. 轻量本体 vs 知识图谱 vs 双链（评估结论）

### 8.1 三个概念的区别
| 维度 | Wiki 双链（文档图） | 知识图谱（KG） | 本体（Ontology） |
|---|---|---|---|
| 节点/边 | 页面 / 链接（无类型） | 实体 / **类型化关系**（三元组，如 `青木 —准备→ 后端面试`） | **概念/关系/公理**（schema，如"准备"是"动作"的子类） |
| 层次 | 实例（instance） | 实例（结构化） | **模式（schema/model）** |
| 产生方式 | 人工写 `[[ ]]` | LLM/规则抽取（NER+关系） | 领域专家设计 |
| 形式化程度 | 非形式 | 半形式（可图查询） | 形式（RDFS/OWL，可推理） |
| 推理能力 | 无 | 有限（多跳遍历） | 强（分类/传递/逆/基数约束） |
| 维护成本 | 低 | 中 | **高** |
| 典型收益 | 导航、上下文扩展、反向链接 | 结构化/多跳问答、实体消歧 | 术语统一、一致性校验、可推理 |
| 存储 | 普通表/图 | 图库或三元组表 | 本体文件 + 推理机（GraphDB/OWL） |

一句话：**双链是"实例级的文档图"；知识图谱是"实例级的实体关系图"；本体是"定义前两者如何组织的模式/词典"**。三者不是替代关系，而是"实例 ↔ 模式"。

### 8.2 对本项目有没有必要？
- **完整本体（OWL/SPARQL/推理机）→ 没有必要**。它会带来 schema 设计、抽取映射、推理引擎、维护与评估成本，收益集中在"强约束/强推理"的领域（医疗、法律、供应链）。个人助理知识库达不到这个收益拐点，属于过度设计（违背项目"不为未来过度设计"原则）。
- **轻量本体（受控关系词表 + 实体类型）→ 可选、且有性价比**。定义 ~8 个关系（`instance_of / part_of / depends_on / derived_from / related_to / authored_by / references / contradicts`）+ 少量实体类型（`Concept/Project/Person/Tool/Note`），用 LLM 给**已存在的双链**打关系类型，写入 `wiki_link.relation`。
  - 收益：图谱边有语义（可视化更清晰）、多跳检索可按关系加权、支持"这个概念属于哪个项目"这类结构化问法。
  - 成本：一次批量 LLM 抽取（可复用 `response_format` 结构化输出 + `parse_json`）+ 一张可选表，远低于完整本体。
- **推荐路线**：M2 先用**无类型双链图**跑通；M4 若确有需求，再加"轻量本体（类型化链接）"。完整本体仅作为面试可讲的"知道边界、不盲目上"。

### 8.3 若做轻量本体的设计（M4+ 备选）
- 存储：`wiki_link.relation`（枚举字符串）+ 可选 `wiki_entity`（实体消歧）。
- 抽取：摄取时对每页的链接批量调用 LLM，输出 `[{source_title, target_title, relation}]`（结构化输出 + 容错解析 + 失败保留无类型边）。
- 使用：图谱按 relation 着色/过滤；检索扩展按 relation 权重排序；不做推理机（把"推理"限制为多跳遍历）。

---

## 9. API 设计（统一 `{code,message,data}` 信封）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/wiki/spaces` | 创建空间（name、source_type、path 或 zip） |
| POST | `/wiki/spaces/{id}/import` | 上传 zip 导入（云端） |
| POST | `/wiki/spaces/{id}/sync` | 扫描同步，返回统计 |
| GET | `/wiki/spaces` | 空间列表（页面数/最后同步） |
| GET | `/wiki/pages?space=&q=&tag=&page=&page_size=` | 页面列表/搜索（分页） |
| GET | `/wiki/pages/{id}` | 详情（正文 + frontmatter + 出链/反向链接） |
| GET | `/wiki/graph?space=&tag=&limit=` | 图谱数据 |
| GET | `/wiki/search?q=&space=` | 仅搜 Wiki（复用 hybrid_search + source 过滤） |

**Agent 工具**：扩展 `kb_search(source="wiki")`；新增 `wiki_read(page)` / `wiki_backlinks(page)`（只读，无需确认）。

---

## 10. 前端

- 「📚 知识库」下新增 **🕸️ Wiki**：
  - 空间管理（导入/同步/删除）+ 同步统计；
  - 页面树/列表 + 搜索 + 标签筛选；
  - 页面浏览：Markdown 渲染（**复用 `ChatPanel.renderMarkdown` + DOMPurify**）、`[[双链]]` 可点击跳转、右侧"反向链接"面板；
  - **图谱页**：力导向图（节点点击跳转、按空间/标签过滤、限制节点数）。
- 渲染安全：Wiki 正文与 LLM 输出同等对待，唯一消毒入口（§6 防存储型 XSS）。

---

## 11. 安全与规范（§6/§12/§13/§7）

| 项 | 落地 |
|---|---|
| 路径沙箱 | `Path(root).resolve()` 必须 `is_relative_to(受管根)`；拒绝 `..`/绝对路径/软链逃逸；默认只读 |
| zip 导入 | 限大小/条目数/解压后总大小（防 zip 炸弹）；拒绝路径穿越条目 |
| 用户隔离 | `space.owner_id` 绑定；`kb_search` 复用既有 `user_id` 过滤；共享空间需显式配置 |
| LLM 不可信 | Wiki 内容进 prompt 走既有定界 + "仅数据非指令"声明 |
| 分层 | 新增 `app/wiki/`（解析/链接/扫描/导入）+ `app/service/wiki_service.py`；api 只校验参数 |
| 配置三件套 | `WIKI_ENABLED / WIKI_STORAGE_ROOT / WIKI_SCAN_INTERVAL_MINUTES / WIKI_LINK_EXPANSION_ENABLED / WIKI_EXPAND_HOPS` + 两份 .env.example |
| 迁移 | `wiki_space/wiki_page/wiki_link` 建索引；级联删除；大表 DDL 评估锁表 |

---

## 12. 里程碑（按依赖排序）

| 里程碑 | 内容 | 预估 | 可演示 |
|---|---|---|---|
| **M1 导入与索引** | 受管副本 + 本地路径/zip 导入 + WikiParser + 增量同步 + 分类"Wiki" | 4–6 天 | 导入 Obsidian vault → 对话检索到 Wiki 内容 |
| **M2 双链与检索增强** | 链接图 + 反向链接 + 邻居扩展召回 + 引用带 Wiki 路径 | 3–5 天 | 引用下钻；跨页问题召回提升 |
| **M3 图谱可视化** | `/wiki/graph` + 力导向图页面 | 2–3 天 | 知识图谱演示 |
| **M4 轻量本体（可选）** | 类型化链接（relation）+ 按关系加权检索/着色 | 3–4 天 | "按关系多跳"演示 |
| M5（远期） | 云端 zip 通道加固 / 共享空间权限 | 按需 | 多用户 |

> 全程"一功能一分支 + 防回归测试 + 全绿验证"，从 `develop` 切 `feat/wiki-*`。

---

## 13. 风险与对策

| 风险 | 对策 |
|---|---|
| 云端无法读本地目录 | 受管副本 + zip 上传通道（v2 已内建） |
| zip 炸弹/路径穿越 | 解压前校验条目与总大小、拒绝 `..` 与绝对路径 |
| 大 vault 同步慢 | 后台任务 + 进度 + 批量嵌入 + 只重嵌变更页 |
| 重命名导致重复 | 同 hash 视为"移动"，只更新 rel_path |
| 同名页/别名歧义 | space 内 slug 唯一；歧义链接记入列表不静默 |
| 图谱节点爆炸 | 默认限制节点数 + 按空间/标签过滤 |
| 轻量本体成本 | 只对"已存在的双链"打关系类型，失败降级为无类型边 |

---

## 14. 已定选型与下一步（可开工）

**已确认**：
1. 受管存储根目录：`backend/data/wiki/`（可挂载卷）✅
2. 图谱库：**`react-force-graph-2d`**（现成库，不自研；2D 包不引入 three.js）✅

建议先做 **M1 `feat/wiki-import`**：导入通道（本地路径 / zip）+ 受管副本 + `WikiParser` + 增量同步 + 分类“Wiki”。

> 完整本体不做；若你倾向“结构化问答”，M4 走**轻量本体（类型化链接）**路线。
