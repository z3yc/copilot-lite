# RAG 原理与实现详解

> 本文结合 Copilot-Lite 项目的**真实代码**，从概念到实现讲透 **RAG（Retrieval-Augmented Generation，检索增强生成）**。
> 配套代码目录：`backend/app/rag/` · 相关文档：[架构图](../docs/architecture.md#3-rag-知识库流程)

---

## 1. 什么是 RAG？为什么需要它？

### 1.1 大模型的"知识困境"

大模型（LLM）的知识来自训练数据，存在三个硬伤：

| 问题 | 举例 |
|---|---|
| **知识有截止时间** | 不知道训练之后发生的事 |
| **不知道你的私有数据** | 你的工作笔记、公司文档、课件，模型从未见过 |
| **会一本正经地胡说** | 不知道答案时编造（幻觉，hallucination） |

### 1.2 RAG 的解决思路

**"先查资料，再回答"** —— 和人类查资料写报告一样：

```
用户提问
   │
   ▼
① 检索：从你的知识库里找出相关内容（Retrieval）
   │
   ▼
② 增强：把找出的内容拼进提示词（Augmentation）
   │
   ▼
③ 生成：LLM 基于"资料 + 问题"回答（Generation）
```

**好处**：
- 答案**基于你的真实数据**，可溯源、可解释；
- 知识库可随时更新，**不用重新训练模型**（成本极低）；
- 有效降低幻觉（模型被约束在给定资料内回答）。

> 面试一句话版：**RAG = 用检索把"模型不知道的知识"注入到生成上下文里。**

---

## 2. 本项目 RAG 的整体架构

```
┌──────────────────────── 预处理（离线，一次做） ────────────────────────┐
│                                                                       │
│  原始文档(MD/PDF/DOCX/代码/网页)                                       │
│    │  ① 解析（parsers/）                                              │
│    ▼                                                                  │
│  结构化章节（标题层级 + 文本 + 页码）                                    │
│    │  ② 分块（chunking.py）                                           │
│    ▼                                                                  │
│  文本分块（携带标题路径/页码元数据）                                      │
│    │  ③ 嵌入（embeddings.py：BGE 512维向量）                           │
│    ├───────────────────────────────►  PostgreSQL chunks 表（文本侧）   │
│    ▼                                                                  │
│  ④ 向量入库（vector_store.py：Qdrant 本地模式）                         │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘

┌──────────────────────── 检索+生成（在线，每次提问） ────────────────────┐
│                                                                       │
│  用户提问 "FastAPI 有哪些特点？"                                       │
│    │  ⑤ 混合检索（retriever.py）                                      │
│    ├── 向量检索：问题→向量→Qdrant 找语义相近的分块                      │
│    ├── BM25 检索：问题分词→PostgreSQL LIKE 找字面命中的分块              │
│    └── RRF 融合：两路结果按排名合并去重                                  │
│    │                                                                  │
│    ▼                                                                  │
│  相关分块（带来源：文档标题 > 章节 > 页码）                              │
│    │  ⑥ 上下文组装 + 系统提示                                          │
│    ▼                                                                  │
│  LLM 生成带引用的回答（orchestrator.py + kb_search 工具）               │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

**数据流一句话**：`原始文档 → 解析 → 分块 → 嵌入 → 双存储（PG 文本 + Qdrant 向量）→ 提问时混合检索 → 注入 LLM → 带引用回答`。

---

## 3. 预处理阶段：把知识变成可检索的"索引"

### 3.1 文档解析（`backend/app/rag/parsers/`）

不同格式需要不同的解析器，但输出统一结构（`ParsedDocument` + `Section`）：

```python
# parsers/base.py
@dataclass
class Section:
    heading: str | None   # 章节标题
    level: int            # 标题层级（1-6）
    content: str          # 正文
    page: int | None      # 页码（PDF）

@dataclass
class ParsedDocument:
    title: str
    source_type: str      # md / pdf / docx / code / web
    sections: list[Section]
```

| 解析器 | 策略 | 文件 |
|---|---|---|
| **Markdown** | 按 `#`~`######` 标题切分章节，保留标题层级 | `markdown_parser.py` |
| **PDF** | pypdf 按页提取文本，**追踪页码**（引用溯源用） | `pdf_parser.py` |
| **DOCX** | 按 Word 内置 Heading 样式切分 | `docx_parser.py` |
| **代码** | 按文件路径切分（每个文件一个章节） | `code_parser.py` |
| **网页** | BeautifulSoup 提取正文，剔除 script/style/nav | `web_parser.py` |

**设计要点**：解析器注册表（`register_parser`）——新增格式 = 写一个解析器 + 一行注册，与分块/检索完全解耦。

### 3.2 智能分块（`backend/app/rag/chunking.py`）

**为什么不能整篇喂给模型？**
- LLM 上下文窗口有限（如 8K/64K token），整本书放不下；
- 检索需要"精细命中"：问"第一章第一节"应返回那一节，而不是整本书。

**本项目分块策略（三层）**：

1. **标题层级锚定**：维护标题路径栈，每个块携带完整标题链
   ```
   块 meta: {"headings": ["第一章", "第一节"], "page": 3}
   ```
   → 回答时能精确引用"来自 fastapi_notes.md > 什么是 FastAPI 章节"

2. **段落聚合**：短章节整体成块；长章节按段落聚合到 `max_size=800` 字符

3. **重叠控制**：相邻块保留 `overlap=100` 字符重叠
   → 避免关键语义恰好被切断在块边界

> **面试追问：分块大小怎么定？**
> 没有绝对最优。块太小→上下文碎片化、检索噪声大；块太大→命中不精准、浪费 token。
> 800 字符 + 100 重叠是经验值，可配置（`chunk_document(max_size=..., overlap=...)`）。
> 进阶方案：按"语义边界"分块（如句向量相似度检测主题切换），本项目用标题层级近似实现了这一点。

### 3.3 嵌入（`backend/app/rag/embeddings.py`）

**什么是嵌入？** 把文本变成一组数字（向量），语义相近的文本向量距离近：

```
"苹果很好吃"  → [0.12, 0.87, ...]  ┐
"苹果营养丰富" → [0.15, 0.82, ...]  ┘ 距离近（语义相似）
"汽车跑得快"  → [0.91, 0.03, ...]  ← 距离远（语义无关）
```

**选型：为什么用 BGE-small-zh-v1.5 + fastembed？**

| 候选 | 问题 | 结论 |
|---|---|---|
| DeepSeek API | **官方没有 embedding 接口** | ❌ |
| OpenAI embedding | 要额外注册、付费、国内网络 | ⚠️ |
| **BGE + fastembed** | 无 | ✅ **本地免费、中文好、512 维** |

- **fastembed**：Qdrant 官方库，**ONNX 运行时 ~50MB**（对比 torch 方案 ~2GB），轻量离线；
- **BGE-small-zh-v1.5**：中文检索 benchmark 优秀，512 维，个人知识库精度足够；
- 首次使用自动下载模型（~100MB），国内走 `hf-mirror.com` 镜像（代码内 `setdefault`）。

**工程细节**：模型是同步推理，用 `run_in_executor` 放到线程池，**不阻塞 FastAPI 事件循环**。

### 3.4 双存储设计（为什么文本和向量分开存？）

| 存储 | 内容 | 用途 |
|---|---|---|
| **PostgreSQL `chunks` 表** | 分块文本 + 元数据 + `vector_id` | BM25 关键词检索、引用溯源、管理 |
| **Qdrant**（本地模式） | 512 维向量 + payload | 向量相似度检索（ANN） |

- 向量库擅长"找语义相近"，但不擅长"精确过滤/管理"；关系库正好相反——**各司其职**；
- `chunk.vector_id` 关联 Qdrant point，删除文档时两侧同步清理；
- Qdrant 本地模式（`qdrant_client.QdrantClient(path=...)`）**零 Docker 部署**，数据落 `backend/qdrant_data/`（已 gitignore）。

---

## 4. 检索阶段：混合检索（`backend/app/rag/retriever.py`）

### 4.1 为什么不能只用一种检索？

| 检索方式 | 强项 | 弱项 |
|---|---|---|
| **向量检索**（语义） | 理解"意思"：问"框架特点"能命中"性能高、自动文档" | 字面词不匹配时可能漏；对专有名词/ID/代码符号不敏感 |
| **BM25 关键词**（字面） | 精准命中："FastAPI"、"面试官常问" 这些词直接匹配 | 没有语义泛化，"框架"找不到"Web 框架" |

**真实场景**：问"面试官常问什么？" → BM25 精准命中"面试要点"章节；问"框架有什么特点？" → 向量检索命中"性能高"章节。**互补，缺一不可。**

### 4.2 三路合一：向量 + BM25 + RRF

```
向量检索 Top5 ──┐
               ├──► RRF 融合 ──► 精排 Top3 ──► 注入 LLM
BM25 检索 Top5 ─┘
```

**RRF（Reciprocal Rank Fusion，倒数排名融合）公式**：

```
score(块) = Σ 1 / (k + rank)
           k = 60（平滑常数）
```

**含义**：不看两路的分数绝对值（量纲不同没法直接比），只看**排名**——在两路中都排名靠前的块，融合分最高。无需调权重，鲁棒。

> **面试追问：为什么不用加权分数相加？**
> 向量分数（余弦相似度 0~1）和 BM25 分数（词频统计）**量纲完全不同**，加权需要调参数且不稳定；RRF 只看排名，天然无参、稳定。这是工业界常用的融合方案。

### 4.3 本项目的轻量 BM25（简化实现）

```python
# 查询词提取：英文单词整体 + 中文逐字
terms = ["FastAPI", "是", "什", "么"]

# OR 召回含任一查询词的块（避免 AND 过于严格）
stmt = select(Chunk).where(or_(*[Chunk.content.ilike(f"%{t}%") for t in terms]))

# 打分：命中词数 / 查询词数
score = hit_terms / len(terms)
```

**为什么是"轻量版"？** 标准 BM25 还要算词频（TF）、逆文档频率（IDF）、文档长度归一化。个人知识库（几十篇文档）用"命中词占比"精度足够，且实现简单可讲清。**大规模场景可无缝替换**为 PostgreSQL FTS / Elasticsearch / OpenSearch（接口不变）。

---

## 5. 生成阶段：带引用的回答

### 5.1 检索结果如何进入对话（`kb_search` 工具）

检索被封装成 **Agent 工具**（`backend/app/tools/kb_tool.py`），注册进工具注册表：

```python
@registry.register
async def kb_search(ctx, query: str, top_k: int = 3) -> str:
    results = await hybrid_search(db=ctx.session, query=query, ...)
    # 返回 JSON：{"来源": "fastapi_notes.md > 什么是 FastAPI", "内容": "..."}
```

Agent（编排器）在系统提示的引导下**自主决定**何时调用：

```
系统提示："当用户问题涉及知识库/文档/笔记时，必须先调用 kb_search，
          再基于检索结果回答，并注明来源"
```

### 5.2 完整调用链（一次 RAG 问答的真实流程）

```
用户: "FastAPI 有哪些核心特点？"
  │
  ▼
① Orchestrator 调 DeepSeek ──► 模型决定: 调用 kb_search({"query": "FastAPI 核心特点"})
  │
  ▼
② 执行 kb_search → 混合检索 → 返回带来源的片段（JSON）
  │
  ▼
③ 结果以 tool 消息回填 → 再次调 DeepSeek
  │
  ▼
④ 模型基于片段生成: "根据你的笔记（fastapi_notes.md > 什么是 FastAPI 章节）...
   1. 自动生成 OpenAPI 文档 2. 基于 Pydantic 校验 3. 原生异步支持"
```

### 5.3 引用溯源是怎么实现的？

**源头在分块阶段**：每个块都携带元数据（`headings` 标题路径 + `page` 页码）→ 检索时元数据跟着走 → 工具返回时带上 → 模型在回答中引用。

```
块元数据 ──► 检索结果 ──► 工具返回 ──► LLM 回答
{"headings": ["第一章","第一节"], "page": 3}
             → "来自 fastapi_notes.md > 第一章 > 第一节"
```

---

## 6. 代码地图（快速定位）

| 模块 | 文件 | 职责 |
|---|---|---|
| 解析器 | `backend/app/rag/parsers/` | 多格式 → 结构化章节 |
| 分块 | `backend/app/rag/chunking.py` | 章节 → 带元数据分块 |
| 嵌入 | `backend/app/rag/embeddings.py` | 文本 → 512 维向量 |
| 向量库 | `backend/app/rag/vector_store.py` | Qdrant 读写/过滤/删除 |
| 摄取流水线 | `backend/app/rag/pipeline.py` | 解析→分块→入库→嵌入→Qdrant |
| 混合检索 | `backend/app/rag/retriever.py` | 向量+BM25+RRF |
| 知识库工具 | `backend/app/tools/kb_tool.py` | Agent 可调用的检索入口 |
| 文档 API | `backend/app/api/routes/documents.py` | 上传/列表/删除 |
| 数据模型 | `backend/app/models/chunk.py` | chunks 表 |

---

## 7. 面试高频问题（含答案）

**Q1：为什么不直接用 LangChain 的 RAG 链路？**
→ 核心逻辑手写（解析/分块/检索/融合），才能讲清楚每个环节；设计模式（Tool 抽象、检索器抽象）借鉴了 LangChain，但实现自己写。面试可对比：LangChain 是"搭积木"，手写是"理解积木"。

**Q2：混合检索为什么优于纯向量检索？**
→ 专有名词/代码符号/ID 靠字面匹配（BM25），语义泛化靠向量；两路 RRF 融合互补，各自召回 Top5 融合后精排。

**Q3：分块大小怎么定？**
→ 800 字符 + 100 重叠是经验值，可配置；核心权衡是"检索精度 vs 上下文碎片化"；进阶用语义边界分块。

**Q4：嵌入模型为什么不用 DeepSeek？**
→ DeepSeek 官方没有 embedding API，需要自备；BGE-small-zh-v1.5 本地免费离线，512 维中文效果好。

**Q5：Qdrant 为什么能本地跑？（无 Docker）**
→ qdrant-client 的 `QdrantClient(path=...)` 是嵌入式本地模式，数据落磁盘，零服务器部署；云端可一行切换为 http 远程模式。

**Q6：如何降低幻觉？**
→ 系统提示约束"只基于检索内容回答"；回答带引用可追溯；检索不到时不编造（工具返回空 → 模型如实说"知识库中未找到"）。

**Q7：知识库更新了怎么办？**
→ 重新摄取（解析→分块→嵌入→覆盖写入）；删除文档时按 document_id 级联清理 Qdrant + PG，不会残留脏数据。

**Q8：性能瓶颈在哪？怎么优化？**
→ 瓶颈在嵌入（本地 CPU 推理）与 LLM 生成。优化：批量嵌入（batch_size）、摄取异步化（后台任务）、检索结果缓存；大规模时 Qdrant 换远程集群 + 嵌入换 API。

---

## 8. 扩展方向（本项目已留口子）

| 方向 | 说明 |
|---|---|
| **Rerank 精排** | RRF 融合后，用交叉编码器（如 bge-reranker）对 TopK 精排，进一步提准 |
| **Query 改写** | 检索前用 LLM 把问题改写成多个检索查询（HyDE / 多查询），提升召回 |
| **PDF 布局解析** | 引入 OCR/版面分析（如 PaddleOCR），处理扫描版 PDF |
| **增量摄取** | 文件变更监听，只重摄取变化的部分 |
| **多集合隔离** | 按用户/项目分 collection，配合权限控制 |

---

*本知识点由 Copilot-Lite 项目实践沉淀，代码可直接对照 `backend/app/rag/` 阅读。*
