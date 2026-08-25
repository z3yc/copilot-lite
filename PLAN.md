# 📋 Copilot-Lite 项目工作计划（PLAN）

> 面向面试作品的**个人 AI 智能助理**项目 · 工作编排与待办清单
> 关联文档：[README](README.md)（项目说明） · [架构文档](docs/architecture.md)（Mermaid 图）

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
P3 双前端   ██████████ 100% ✅（M3 验收通过）
P4 工程化   ░░░░░░░░░░   0%
P5 部署面试 ░░░░░░░░░░   0%
```

**Git 现状**：25 个提交 · P3 完成（4 个提交）· 本地领先 origin 4 个

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

### 🟢 P4 · 工程化（约 1 周）

- [ ] Docker Compose 编排（backend + PostgreSQL + Qdrant + Redis + Nginx）
- [ ] 配置化收口（deploy/.env 模板 + 服务器规格自适应）
- [ ] 测试补全（覆盖率报告，关键路径 80%+）
- [ ] CI 流水线（提交触发 lint + test）
- [ ] **M4 验收**：`docker compose up` 一键启动

### 🔵 P5 · 部署 + 面试（约 2 周）

- [ ] 云服务器选购（2C4G 轻量，¥50/月内）与环境初始化
- [ ] 云端部署（Docker Compose + Nginx + HTTPS）
- [ ] README 完善（架构图 + 演示截图 + 配置说明）
- [ ] 面试问答文档（deep-dive 20 问：RAG/记忆/工具/架构取舍）
- [ ] 演示脚本排练（3 分钟 Demo 流程）
- [ ] **M5 验收**：云上可演示，故事线完整

---

## 5. 后续规划（Post-MVP，口子已留）

| 方向 | 说明 | 预留点 |
|---|---|---|
| 多智能体编排 | RouterAgent + 子 Agent 分工 | `BaseAgent` 协议 |
| 长期记忆 | 事实提取 → 向量化 → 召回注入 | ER 图 MEMORY_FACT |
| Agent-as-Tool | 子 Agent 注册为工具 | ToolRegistry 协议 |
| 流式增强 | SSE 已规划于 P3 | API 层包装 |
| LangGraph 可选 | 状态机复杂度上升时引入 | BaseAgent 迁移成本低 |

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
