# 📋 Copilot-Lite 项目工作计划（PLAN）

> 面向面试作品的**个人 AI 智能助理**项目 · 工作编排与待办清单
> 关联文档：[README](README.md)（项目说明） · [架构说明](README.md)（Mermaid 图）

---

## 1. 项目目标

> 基于 DeepSeek + 企业级 RAG + Agent 工具调用，打造个人专属 AI 助理，作为**后端/全栈初级岗**面试作品，证明学习能力与工程素养。

**验收红线（缺一不可）**：
- [x] 本地可跑通：后端 + 数据库 + CLI/Web
- [x] 能讲清楚架构：为什么这么设计（面试叙事）
- [ ] 云上可演示（P5）
- [x] 真实对话可用（DeepSeek Key 已配置，M1 全流程实测通过）

---

## 2. 进度总览

```
P0 地基     ██████████ 100% ✅
P1 Agent 核 ██████████ 100% ✅（真实对话已验证）
P2 知识库   ██████████ 100% ✅（M2 验收通过）
P3 双前端   ██████████ 100% ✅（M3 验收通过 + 功能增强）
P4 工程化   ██████████ 100% ✅（M4 本地验收通过）
P5 部署面试 ░░░░░░░░░░   0%（文档已就绪，云端待实测）
P6 收敛交付 █░░░░░░░░░  14%（R0 已完成，R1 见 P5；见 OPTIMIZATION_PLAN §13）
```

**Git 现状**：`develop` 基线后端 **337 用例 / 覆盖率 82.53%**、前端 **92 用例**、CLI **15 用例**（@ `5b5ce2f` J1 合并后）；CI/CD 由本机 Jenkins 承载（见 `docs/CICD_PLAN.md`）。
**范围基准**：本轮已收敛为 **R0-R7**（`OPTIMIZATION_PLAN.md` §13），冻结项见该文件 §11；需求准入规则见 `DEMO_SCRIPT.md`。

---

## 3. 已完成清单（勿重复劳动）

### P0 · 地基 ✅
- [x] FastAPI 项目骨架（uv 管理，Python 3.12，39 依赖）
- [x] 配置模块（pydantic-settings：RUN_MODE / DATABASE_URL / 预留 Redis/Qdrant）
- [x] 异步数据库层（SQLAlchemy 2.0 + async engine）
- [x] 核心 ORM 模型（User / ChatSession / Message / Todo / Document）
- [x] Alembic 迁移（首个迁移 `452777a89f5d`，PostgreSQL 已应用）
- [x] 本地 PostgreSQL 17 接入（开发与生产同构）
- [x] 健康检查 API + 2 个基础测试

### P1 · Agent 核心 ✅
- [x] DeepSeek LLM 客户端封装（兼容 OpenAI SDK，Function Calling）
- [x] 可插拔工具注册表（@tool 装饰器 + 签名自动生成 JSON Schema + 异常兜底）
- [x] Todo 工具集（create / list / complete / delete，对接 PostgreSQL）
- [x] 对话编排器（ReAct 循环 + 系统提示 + 历史窗口 + 最大轮数保护）
- [x] 聊天 API（POST /api/v1/chat：会话创建/续接、消息持久化）
- [x] 启动 seed 默认用户（P1 单用户模式）
- [x] CLI 客户端（typer + rich：`copilot chat` / `copilot ask`）
- [x] 测试套件 12 个用例（工具注册表 / ReAct / chat API 集成，独立测试库）
- [x] 多智能体扩展点预留（BaseAgent 抽象 + Agent-as-Tool 设计）

---

## 4. 待办工作清单

### 🔴 P2 · 知识库 RAG（已完成 ✅）

**前置决策（已敲定）**：
- [x] **嵌入模型选型**：本地 **BGE-small-zh-v1.5**（fastembed/ONNX，512维，免费离线，~50MB）；国内网络走 hf-mirror 镜像（代码内 setdefault）
- [x] **Qdrant 接入方式**：`qdrant-client` **本地模式**（磁盘持久化，零 Docker）；云端切 http 模式（代码已支持）

**任务分解**：
- [x] 文档解析 Pipeline
  - [x] 解析器抽象接口（ParsedDocument / Section 统一结构 + 注册表）
  - [x] Markdown 解析器（标题层级 → 分块锚点）
  - [x] PDF 解析器（pypdf，页码追踪）
  - [x] DOCX 解析器（python-docx，Heading 样式）
  - [x] 代码仓库解析器（按文件路径切分）
  - [x] 网页解析器（BeautifulSoup，正文提取）
- [x] 智能分块模块（标题路径栈 + 段落聚合 + 重叠控制 + 块级元数据）
- [x] 摄取流水线（uploaded → parsing → ready / failed，同步执行个人量级够用）
- [x] Qdrant collection 设计（payload：chunk_id / document_id / content / meta 标题路径+页码）
- [x] 混合检索：BM25（OR 召回+命中占比）+ 向量 + RRF 融合
- [x] 引用溯源（回答附文档标题/章节路径/页码）
- [x] 知识库工具注册：`kb_search`（复用 ToolRegistry）
- [x] 文档管理 API（上传 / 列表 / 详情 / 删除，级联清理）
- [x] 测试 19 用例（解析 / 分块 / 混合检索，伪嵌入不下载模型）
- [x] **M2 验收**：上传笔记 → CLI/API 提问 → 带引用回答（真实 BGE + DeepSeek）

### 🟡 P3 · 双前端（约 2 周，与 P2 尾部可并行）

- [x] Chat API 增加 SSE 流式输出（POST /chat/stream：session→chunk→done；LLMClient.stream_chat 已封装）
- [x] Web UI 工程（React + Vite + TS，Vite proxy 代理 /api）
  - [x] 对话页（SSE 流式渲染 + Markdown 渲染）
  - [x] 知识库管理页（多文件上传/列表/状态/删除）
  - [x] 会话列表（新建/切换/删除）
- [x] CLI 完善（`copilot todo list/add/done/rm` 直接管理命令）
- [x] 配套：会话管理 API + Todo REST API（CLI 与前端共用）
- [x] **M3 验收**：Web 完整可用（localhost:5173 浏览器演示，22 测试全绿）

### ✨ 功能增强（P3 后追加，已记录于 docs/优化落地记录.md）

- [x] **Ant Design 重构**：专业组件库 UI（主题色可定制），业务代码 gzip 20KB
- [x] **知识库分类视图**：侧边栏分类导航（带数量）+ 分组展示 + `type` 参数过滤
- [x] **内容级搜索**：`/documents?q=` 标题+分块内容双匹配（防抖 300ms）
- [x] **暗色模式**：antd darkAlgorithm + CSS 变量，localStorage 记忆
- [x] **会话级附件**：对话上传仅本次会话可见（session_files 表），与知识库完全隔离
  - 附件文本注入对话上下文（每文件 1500 字符，最多 5 个），回答注明来源
- [x] 文档详情展开（分块内容 + 标题路径 + 失败原因）
- [x] **用户认证系统**：注册/登录/JWT + 数据按用户隔离 + 个人中心（可交互 4 Tab）
- [x] **完整待办工作区**：侧边栏待办 Tab、AI 快速添加、分类+标签、时间分组高亮、全字段编辑
- 当前测试：**后端 80 用例** + **前端 22 用例**（vitest：api SSE 解析 + 组件冒烟 + 401 回归）

### 🟢 P4 · 工程化（已完成 ✅）

- [x] 测试补全 + 覆盖率门槛：31 用例，**83%**（fail-under=80 强制）
- [x] CI 流水线：`.github/workflows/ci.yml`（后端 lint+test+coverage / 前端 typecheck+build+test）
- [x] 配置化收口：`deploy/.env.example` 完整模板（RUN_MODE/DATABASE/QDRANT/模型）
- [x] Docker Compose 预留：postgres+qdrant+redis+backend+web（`deploy/`，云端实测）
- [x] 一键启动脚本：`scripts/dev_start.ps1`（无 Docker 本地全服务启动）
- [x] **M4 验收**：一键脚本启动前后端 + 浏览器访问（本地版）；Docker 编排云端待实测（P5）

### 🔵 P5 · 部署 + 面试（约 2 周）

- [ ] 云服务器选购（2C4G 轻量，¥50/月内）与环境初始化
- [ ] 云端部署（Docker Compose + Nginx + HTTPS）实测通过，`/health/ready` 为 ok
- [ ] README 完善（架构图 + 演示截图 + 配置说明）
- [ ] 面试问答文档（deep-dive 20 问：RAG/记忆/工具/架构取舍）
- [ ] 演示脚本排练（`DEMO_SCRIPT.md` 6 镜头，3 分钟内一次过）
- [ ] **M5 验收**：云上可演示，故事线完整

### ⚪ P6 · 范围收敛与交付（进行中）

- [x] **R0** 计划收敛（本批交付）：三份计划改造 + 冻结清单（带重启条件）+ `DEMO_SCRIPT.md`
- [ ] **R2** Q1 trajectory 可观测
- [ ] **R3** M5 引用来源标注
- [ ] **R4** P-F1 MCP 地基 + `fund_tool`
- [ ] **R5** J3 评测门槛进 Jenkins + Q5 双引擎对照报告
- [ ] **R6** N2 质量看板（N2.1-N2.6 + N2.8）
- [ ] **R7** 基金自用闭环（P-F2/F3/F4,必做）

> 明细与预估见 `OPTIMIZATION_PLAN.md` §13；冻结与重启条件见同文件 §11。
> **进度以 `OPTIMIZATION_PLAN.md` §13 为准**；本页 P5/P6 为镜像视图，改动时先改 §13。

---

## 5. 后续规划（Post-MVP，三大增强）

### ✅ ① 长期记忆系统（已完成 0.9.0）

| 环节 | 设计 | 状态 |
|---|---|---|
| 提取 | 会话结束后台 LLM 批量抽取事实/偏好（结构化 JSON，偏好/事实/背景） | ✅ |
| 存储 | `memory_facts` 表 + Qdrant `copilot_memories` 集合 | ✅ |
| 去重 | 向量相似度 > 0.92 判定同事实跳过 | ✅ |
| 召回（混合） | 对话按问题检索注入（等价于会话开始 + 话题切换补充） | ✅ |
| 可视化管理 | 个人中心"🧠 我的记忆"：**查看 / 编辑 / 删除** | ✅ |
| API | `GET /memories`、`PATCH /memories/{id}`、`DELETE /memories/{id}` | ✅ |
| 附带修复 | Qdrant 客户端共享单例（目录锁冲突） | ✅ |

### ✅ ② Rerank 重排（已完成 0.10.0）

| 环节 | 设计 | 状态 |
|---|---|---|
| 模型 | 本地 **bge-reranker-base**（fastembed，复用 hf-mirror 配置） | ✅ |
| 流程 | 混合检索（BM25+向量+RRF）→ TopK → Rerank 精排 → 前 N 注入 | ✅ |
| 配置 | `RAG_RERANK_ENABLED` 开关（可对比效果） | ✅ |
| 实现 | `backend/app/rag/reranker.py` + `retriever.hybrid_search` 末尾接入（线程池异步） | ✅ |
| 测试 | 8 用例（Fake 重排器：链路接入/开关关闭/排序截断），共 60 用例，覆盖率 80.69% | ✅ |

### ✅ ③ LangGraph 多 Agent（已完成 0.11.0）

```
START → Supervisor（LLM 意图判断）→ 条件路由
  ├─ 🧠 知识库 Agent（RAG 检索 + 引用回答）
  ├─ 🛠️ 工具 Agent（复用现有 ToolRegistry）
  └─ 💬 通用 Agent（日常对话）
→ 汇总 → END
```

| 环节 | 设计 | 状态 |
|---|---|---|
| 依赖 | `langgraph` + `langchain-openai`（DeepSeek 兼容 OpenAI） | ✅ |
| 引擎接入 | **并存模式**：LangGraph（默认）+ 手写 Orchestrator（配置 `AGENT_ENGINE` 切换） | ✅ |
| 工具复用 | 现有 ToolRegistry 适配为 LangGraph 工具（bind_tools，执行仍走 registry） | ✅ |
| 流式 | `graph.astream_events` 过滤叶子节点输出，SSE 接口不变 | ✅ |
| 实现 | `backend/app/agent/langgraph_engine.py`（StateGraph + Supervisor JSON 路由 + 关键词兜底） | ✅ |
| 测试 | 15 用例（图结构/路由/工具/兜底/最大轮数/流式/引擎切换/API），共 75 用例，覆盖率 81.48% | ✅ |

### 实施顺序与预估

| 顺序 | 方向 | 预估工作量 |
|---|---|---|
| 1️⃣ | 长期记忆（后端 + 前端管理页） | ✅ 已完成 0.9.0 |
| 2️⃣ | Rerank（检索链路增强） | ✅ 已完成 0.10.0 |
| 3️⃣ | LangGraph 多 Agent（图 + 引擎切换 + 测试） | ✅ 已完成 0.11.0 |

### 关键风险预案

- LangGraph 与手写引擎边界清晰（配置切换互不干扰）
- bge-reranker 下载 → 复用 hf-mirror + 禁用 xet
- 记忆提取成本 → 会话结束批量一次，可控
- 测试策略 → 记忆提取 mock LLM、rerank mock、LangGraph 图测试

---

## 6. 关键依赖与前置条件

| 依赖 | 状态 | 说明 / 行动 |
|---|---|---|
| DeepSeek API Key | ✅ 已配置 | 位于 `backend/.env`（gitignore 保护）；M1 真实对话实测通过 |
| 嵌入模型 | ✅ BGE-small-zh-v1.5 | fastembed 本地推理（512 维），hf-mirror 镜像自动配置 |
| Qdrant | ✅ 本地模式 | `backend/qdrant_data/`（gitignore 保护）；云端切 http 模式 |
| Docker | ❌ 未安装 | P2 用 Qdrant 本地模式绕开；P4 需安装或改用脚本部署 |
| PostgreSQL 17 | ✅ 已就绪 | 本地 `copilot` 库运行中 |
| 前端基础 | ⚠️ 偏弱 | P3 前 2 周开始 React 基础自学（并行不阻塞） |

---

## 7. 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| 嵌入模型选型拖延 | P2 阻塞 | 本周决策，默认走 BGE 本地方案 |
| Qdrant 本地模式性能 | 大数据量检索慢 | 个人知识库量级（百篇内）无影响；云端切独立实例 |
| 公司文档隐私 | 数据泄露 | 云端只放脱敏示例；敏感数据本地模式 |
| 前端工期超支 | P3 挤压 | 界面"够用且好看"，重点投入后端 |
| API Key 成本 | 演示费用 | DeepSeek 按量付费，个人量级每月几元 |

---

## 8. 使用说明

- **每完成一项**：勾选 `[x]` 并提交一次（`feat(rag): xxx` 风格）
- **每阶段结束**：更新进度总览 + 里程碑验证
- **计划变更**：先改本文件，再动代码（保持文档与代码同步）

> 设计原则：**不为未来过度设计，但为未来留好接口**。
