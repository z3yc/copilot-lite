# 🛠 修复日志：RAGAS 评测 + Query 改写增强 + AGENTS.md

> 主题：RAGAS 生成质量评测接入 · Query 改写多路召回 · 开发规范 AGENTS.md
> 约定：每完成一项 → 跑测试 → `git commit`（一次提交一个改动）→ 更新本文件复盘记录
> 位置说明：与既有日志同体系，维护在仓库外目录（C:\Users\asus\Documents\面试准备\）；仓库内 commit message 为第二份记录。

## 进度总览

| # | 改动项 | 提交 | 测试 | 复盘 |
|---|---|---|---|---|
| R1 | RAGAS 接入（依赖 + rag_eval_ragas.py + golden 参考答案 + schema 测试） | `d548026` | ✅ | ✅ |
| Q1 | Query 改写多路召回（rewriter + 跨查询 RRF + kb_search 接入 + 开关） | `a5c7f43` | ✅ | ✅ |
| D1 | AGENTS.md 开发规范（11 节，含安全红线与自查清单） | `6145329` | — | ✅ |

## 逐项复盘记录

### R1 RAGAS 接入（`d548026`）
- **改动**：`uv add ragas`（0.3.1）+ `langchain-google-vertexai`（解决导入依赖）；新增 `scripts/rag_eval_ragas.py`——golden 集问题 → 混合检索上下文 → DeepSeek 生成答案 → ragas 三指标打分（Faithfulness / ContextRelevance / ResponseRelevancy），fastembed 封装 `LocalEmbeddings` 适配 langchain；golden 集 10 条全部补 `ground_truth` 参考答案；schema 测试校验
- **踩坑（重要）**：① ragas 0.3.1 与 langchain-community 1.x 存在兼容缺口——`ragas.llms.base` 无条件导入已被移除的 `langchain_community.chat_models.vertexai` 模块，即使装了 langchain-google-vertexai 也救不了（它装的是新包路径）——最终在脚本顶部注册**占位模块**到 `sys.modules` 绕开（本项目不使用 VertexAI，占位安全）；② 指标名是 `ContextRelevance`（0.3 改名，不是 0.2 的 ContextRelevancy）
- **测试**：golden schema 测试 3 例通过；脚本 py_compile + ruff 通过（CI 内不跑真评测——需 API Key 与已摄取数据）
- **面试话术**："生成质量我用 RAGAS 三指标闭环：faithfulness 测幻觉、context relevance 测检索、response relevancy 测切题——DeepSeek 当 judge，本地 fastembed 供指标计算，golden 集带参考答案。"

### Q1 Query 改写多路召回（`a5c7f43`）
- **改动**：新增 `app/rag/query_rewriter.py`（LLM 生成 N 个改写：同义/补全上下文/拆子问题，失败静默回退原查询）；`retriever.multi_query_search`（每查询独立混合检索 → 跨查询 RRF 融合）；`kb_search` 按 `RAG_QUERY_REWRITE_ENABLED` 开关接入；conftest 默认关闭（防测试触发真实 LLM）
- **原理**：multi-query 补"用户问法 vs 文档写法"的表达鸿沟——口语化问题单查询召回有限，多个改写各自命中不同文档，RRF 融合后覆盖面显著提升；改写是**锦上添花**，任何失败都回退单查询，绝不让主链路挂掉
- **踩坑**：kb_tool 测试用 monkeypatch 替换 `kb_module.hybrid_search`，但改写开启时走的是 `multi_query_search`（内部引用 retriever 模块自己的 hybrid_search）——测试会穿透到真实嵌入下载模型。解法：conftest autouse 关闭改写开关（与 rerank 同模式）
- **测试**：新增 test_query_rewriter.py 4 例（改写返回/失败回退/跨查询融合/kb_search 开关链路）；kb_tool 既有测试不受影响
- **面试话术**："检索质量的三个杠杆我已实现两个：混合检索+重排、查询改写多路召回（第三个是评测闭环）——改写失败自动回退原查询，增强功能永远不让主链路挂掉。"

### D1 AGENTS.md（`6145329`）
- **改动**：仓库根新增 AGENTS.md（11 节）：项目概览/开发流程/提交规范/后端与前端代码规范/安全红线 7 条/配置三件套/测试规范/记录复盘/LLM 工程规范/提交前自查清单
- **定位**：把整个体检+修复周期沉淀的经验写成可执行的约定——AI 编码代理与协作者的统一规范；优先级：安全红线 > 测试门槛 > 规范 > 个人习惯
- **面试话术**："我把安全自审的经验固化成了 AGENTS.md——安全红线（隔离穿透检索、工具层授权=REST、上传三件套）违反即阻塞，配合覆盖率门槛与一次提交一个改动，让规范可执行而不是停留在口头。"

## 整体复盘

**时间账**：3 项改动 · 3 次提交

| 问题 | 回答 |
|---|---|
| 最难的坑？ | ragas 0.3.1 × langchain-community 1.x 的 vertexai 导入缺口——社区已知不兼容，占位模块绕开是最小侵入解（仅在评测脚本内，不进业务代码） |
| 方法论沉淀？ | "增强功能失败回退"模式第三次出现（改写→原查询、记忆提取→静默、摘要压缩→不阻塞）——它应该成为本项目的通用原则，已写入 AGENTS.md §10 |
| 给面试的新素材？ | 检索质量三杠杆全部落地：混合检索+重排（已有）、Query 改写多路召回（本轮）、评测闭环（RAGAS + recall@K 双脚本）——"你怎么证明检索有效"从答不上变成完整答案 |

---

> 关联日志：SECURITY_FIX_WEEK1.md（第 1 周安全修复）· FIX_LOG_WEEK2_4.md（第 2-4 周修复）· FIX_LOG_CACHE_LIMIT.md（缓存/限流增强）
