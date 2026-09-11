# FIX_LOG —— Wiki / RAG 运行时问题复盘

> 用途：面试复盘。每个问题按「现象 → 定位 → 根因 → 修复 → 防回归 → 面试话术 → 通用教训」记录。
> 背景：项目具备完整 Fake 测试（121+ 用例），但这些 bug **只在真实运行**（PostgreSQL + 真实 fastembed + LangGraph 默认引擎）才暴露。
> 记录时间：2026-09-11。

---

## 0. 一句话总览

| # | 现象 | 根因（一句话） | 修复（一句话） |
|---|---|---|---|
| 1 | `kb_search` 报 `'generator' object is not subscriptable` | fastembed `embed()` 返回**生成器**，代码却用 `[0]` 下标 | 改 `next(iter(...))` |
| 2 | 对话只有 `session` + 空 `done`，回答没内容 | LangGraph 子 Agent 用 `ainvoke`，**不产生流式事件** | 流式运行改 `astream` 聚合 |
| 3 | 每次请求联网加载重排模型（1~2 分钟） | 重排模型加载**未设缓存目录/未离线优先** | `local_files_only` + 持久缓存 + 预热 |
| 4 | 同步 Wiki 报 500（时区错误） | naive 时间列写入 aware datetime | 写库前去掉 tzinfo |

---

## 1. 单条嵌入对生成器取下标

- **现象**：知识库问答报 `'generator' object is not subscriptable`；记忆召回/去重也失败（都走单条嵌入）。批量摄取却正常。
- **定位**：报错出现在查询向量阶段 → 看 `app/rag/embeddings.py`，单条路径 `model.embed([text])[0]`；批量路径是 `[x for x in model.embed(texts)]`（迭代，正常）。
- **根因**：fastembed 的 `TextEmbedding.embed()` 返回**迭代器/生成器**，不能下标访问。**同一 API 两种消费方式，只有一条写错**。
- **修复**：
  ```python
  vec = next(iter(model.embed([text])))   # 生成器取首个
  ```
- **防回归**：加"返回生成器的假模型"测试（单条 + 批量），模拟 fastembed 行为；真实环境验证 `dim=512`。
- **面试话术**："我的单测用 Fake 嵌入，掩盖了真实 SDK 的一个行为差异——`embed()` 返回生成器。**教训：Fake 要模仿接口'形状'（返回类型/惰性），不只是返回值。**"
- **通用教训**：第三方库的**返回类型（生成器 vs 列表）**也要在 Fake 里还原；"批量对、单条错"往往就是消费方式不一致。

---

## 2. LangGraph 流式输出为空

- **现象**：前端 SSE 只收到 `session` 与空 `done`，回答没内容；日志显示模型其实被调用了 3 次（Supervisor + 工具轮 + 最终回答）。
- **定位**：默认引擎 `langgraph`，`run_stream` 只转发 `on_chat_model_stream` 事件；而子 Agent 节点内是 `bound.ainvoke(...)`——**非流式调用不产生 stream 事件**，所以没有任何 token 可转发。
- **根因**：**流式输出依赖"模型调用本身是流式"**；`ainvoke` 与 `astream_events` 语义不匹配。
- **修复**：节点在**流式运行**时改用 `astream` 聚合成 `AIMessageChunk`（保留 tool_calls），非流式运行仍用 `ainvoke`：
  ```python
  if self._streaming:
      full = None
      async for chunk in bound.astream(messages):
          full = chunk if full is None else full + chunk
      resp = full
  else:
      resp = await bound.ainvoke(messages)
  ```
  （`_streaming` 由 `run_stream` 置 True；避免测试 Fake 在"工具轮空内容"时 `astream` 报 `No generation chunks`。）
- **防回归**：保留"真实图 + `astream_events` 流式产出"测试；新增非流式路径兼容。
- **面试话术**："流式不是'前端的事'——**模型调用必须真的是流式**（`astream`），否则事件总线收不到 token。我做双引擎时踩到'行为不一致'：手写引擎流式对，LangGraph 用的是非流式调用。"
- **通用教训**：接框架时，先确认"**事件从哪来**"（模型流 vs 节点返回）；`ainvoke`/`astream`/`astream_events` 三者语义要对齐。

---

## 3. 重排模型每次请求联网加载

- **现象**：日志里 `hf-mirror` 反复拉取 `bge-reranker-base`（第一次 1~2 分钟）；请求长时间无输出。
- **定位**：`app/rag/reranker.py` 的 `_load()` 直接 `TextCrossEncoder(model_name=...)`，没有 `cache_dir`、没有离线优先；且与嵌入模型一样默认落 `%TEMP%`。加上网络到 HF 源不稳 → 反复校验/重下。
- **根因**：**模型缓存位置 + 加载策略**（联网校验 vs 本地缓存）没做对；默认缓存目录易被清理。
- **修复**：
  1. `cache_dir=settings.EMBEDDING_CACHE_DIR`（持久卷 `./data/models`）；
  2. **离线优先**：先 `local_files_only=True`，未命中才联网下载；
  3. 线程锁防并发重复加载；启动**后台预热**（`app/main.py`）；
  4. 把已下载的 2.1GB 重排缓存从 `%TEMP%` 移到持久目录（避免再下）。
- **防回归**：测试断言 `TextCrossEncoder` 收到 `cache_dir` 且 `local_files_only=True`。
- **面试话术**："本地模型推理的成本陷阱在**加载**而非推理：默认缓存落 `%TEMP%` + 每次联网校验，会让'本地免费'变成'每次 1 分钟'。我的做法是**持久缓存 + 离线优先 + 启动预热**。"
- **通用教训**：本地模型三件套——**持久缓存目录、离线优先加载、启动预热**；否则延迟会伪装成"功能坏了"。

---

## 4. 时间列写入带时区时间（500）

- **现象**：同步 Wiki 返回 500；日志 `asyncpg DataError: can't subtract offset-naive and offset-aware datetimes`。
- **根因**：列是 `TIMESTAMP WITHOUT TIME ZONE`（naive），代码写入 `datetime.now(UTC)`（aware）。**SQLite 两种都收，PostgreSQL 直接拒绝**。
- **修复**：写库前 `.replace(tzinfo=None)`；测试断言 `tzinfo is None`。
- **面试话术**："**SQLite 能过、PostgreSQL 报错**是经典陷阱——测试库与生产库的严格程度不同。时间字段要么统一 aware 列（`timestamptz`），要么统一 naive 写入。"
- **通用教训**：**测试库尽量与生产同构**；时间语义（naive/aware）要在模型层统一。

---

## 5. 横向总结（为什么"测试全绿却线上崩"）

1. **Fake 不还原真实行为**：返回类型（生成器）、流式语义、时区严格性。
2. **测试用 SQLite，生产 PostgreSQL**：时区、级联、并发语义不同。
3. **网络依赖未隔离**：模型下载源不稳 → 先改成"缓存优先/离线优先"，再谈功能。
4. **多实现并存**：手写引擎与 LangGraph 行为不一致，**只测默认那个不够**。

**对策**：真实依赖**冒烟测试**（本地 PG + 真实模型各跑一条）；Fake 贴近接口形状；关键行为加"运行时探针"（启动预热/健康检查）。
