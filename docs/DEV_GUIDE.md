# 🧭 开发交接手册（DEV GUIDE）

> 给新开发窗口/新协作者的完整指引：**项目是什么、做到哪了、接下来干什么、怎么干**。
> 读完本文（约 5 分钟）即可开始后续功能开发。

---

## 1. 项目速览

**Copilot-Lite**：基于 DeepSeek 大模型 + 自研 Agent + RAG 知识库的**个人 AI 智能助理**（面试作品）。

| 项 | 说明 |
|---|---|
| 技术栈 | Python 3.12 / FastAPI / SQLAlchemy async / Qdrant（本地模式）/ React 18 + Vite + TS + Ant Design / DeepSeek API |
| 包管理 | **uv**（后端 `uv sync`）/ npm（前端） |
| 数据库 | 本地 PostgreSQL 17（`copilot` 库，用户 postgres/密码 root）；测试用独立 SQLite |
| 大模型 | DeepSeek（`backend/.env` 的 `DEEPSEEK_API_KEY`）；嵌入用本地 BGE-small-zh-v1.5（fastembed） |

## 2. 当前状态（重要）

| 项 | 状态 |
|---|---|
| **分支** | `feature/agent-enhancements`（三大增强①②③ 已完成；③ 在 `feature/langgraph-multiagent` 开发待审）· `main` 稳定 |
| 已完成 | P0-P4 全量 + 认证 + 个人中心 + 待办工作区 + **长期记忆（①）+ Rerank 重排（②）+ LangGraph 多 Agent（③）** |
| 待办 | 其他路线图项（Agent-as-Tool / Rerank 后置 Query 改写 / 云端部署实测，详见第 5 节） |
| 测试 | 75 用例全绿，覆盖率 81.48%（门槛 80%，`uv run pytest`） |
| 代码规范 | ruff 全绿（`uv run ruff check .`） |

## 3. 环境与启动

```bash
# 后端（终端 1）
cd backend
uv sync
uv run alembic upgrade head      # 数据库迁移
uv run uvicorn app.main:app --reload   # http://127.0.0.1:8000

# 前端（终端 2）
cd web
npm install
npm run dev                      # http://localhost:5173

# 测试与检查
cd backend
uv run pytest                    # 覆盖率 ≥80%
uv run ruff check .
```

**注意事项**：
- `.env` 在 `backend/.env`（gitignore 保护）；`DEEPSEEK_API_KEY` 已配置；
- BGE 模型自动下载（hf-mirror 镜像已在代码内 setdefault，无需手动配置）；
- Qdrant 本地模式数据在 `backend/qdrant_data/`（gitignore）；
- **Qdrant 客户端必须共享单例**（`get_qdrant_client`，本地模式同一目录只允许一个客户端实例——新增 collection 不要 new 客户端）。

## 4. 代码地图（快速定位）

```
backend/app/
├── main.py            # 入口 + lifespan（建表/seed 默认用户与分类）
├── core/              # config(settings)/db/llm(DeepSeek)/security(JWT)/logging/constants
├── agent/             # base.py(BaseAgent抽象) + orchestrator.py(手写ReAct，含run_stream流式) + langgraph_engine.py(多Agent引擎③)
├── rag/               # parsers(5格式)/chunking/embeddings(BGE)/vector_store(Qdrant)/retriever(混合检索)/pipeline(摄取)
├── memory/            # service.py(长期记忆：提取/存储/召回/编辑/删除)  ← ①已完成
├── tools/             # base.py(可插拔注册表) + todo_tool/kb_tool
├── api/routes/        # auth/chat(SSE)/sessions(含附件)/todos(含ai-create)/documents/memories
└── models/            # User/Category/ChatSession/Message/Todo/Document/Chunk/SessionFile/MemoryFact
web/src/
├── App.tsx            # 布局 + 认证门控 + 主题
├── api.ts             # 全部 API 封装 + token 管理 + SSE 流式解析
├── components/        # ChatPanel/SessionList/KbPanel/TodoPage/ProfilePage(含记忆管理)/LoginPage/DocCategoryNav
```

## 5. 待办任务（后续功能，按此顺序实施）

### ✅ ① 长期记忆 —— 已完成（勿重复）
见 `docs/CHANGELOG.md` 0.9.0 与 `backend/app/memory/service.py`。

### ✅ ② Rerank 重排 —— 已完成（勿重复）
见 `docs/CHANGELOG.md` 0.10.0、`backend/app/rag/reranker.py` 与 `retriever.py`（`hybrid_search` 末尾接入，`RAG_RERANK_ENABLED` 开关）。

### ✅ ③ LangGraph 多 Agent —— 已完成（勿重复）
见 `docs/CHANGELOG.md` 0.11.0 与 `backend/app/agent/langgraph_engine.py`（Supervisor 路由 + 3 子 Agent，`AGENT_ENGINE` 切换，SSE 接口不变）。

### 其他路线图项（下一步候选）
- Agent-as-Tool（子 Agent 注册为工具）
- Rerank 后置 Query 改写（HyDE）
- 云端部署实测（`deploy/DEPLOY.md`）

## 6. 工作约定（必须遵守）

1. **分支**：继续在 `feature/agent-enhancements` 开发；完成一部分可推送分支（**不要直接合并 main**，除非用户要求）；
2. **提交**：每个子功能独立提交，message 风格 `feat(rerank): ...` / `feat(multiagent): ...` / `fix(...)`；
3. **文档同步**：**每个功能完成后必须更新**：
   - `README.md`（核心特性加一条）
   - `docs/CHANGELOG.md`（新增版本号）
   - `PLAN.md`（标记完成 + 进度）
4. **质量门槛**：`uv run pytest` 覆盖率 ≥80%（不达标补测试）；`uv run ruff check .` 全绿；前端 `npm run build` 通过；
5. **测试隔离**：测试用独立 SQLite + 隔离 Qdrant 目录（conftest 已处理）；**不要**在测试中调用真实 LLM/嵌入模型（用 mock/Fake）。

## 7. 已知坑（避免踩）

| 坑 | 说明 |
|---|---|
| Qdrant 目录锁 | 本地模式同一目录只允许一个客户端 → 必须走 `get_qdrant_client()` 共享单例 |
| 配置路径 | `.env` 按文件位置解析（`Path(__file__).parents[2]`），启动目录无关 |
| Windows 控制台 | CLI/脚本输出纯 ASCII 或强制 UTF-8（GBK 会乱码） |
| 模型下载 | HF 走 hf-mirror + 禁用 xet（代码已 setdefault，勿改） |
| React StrictMode | 状态更新必须**不可变**（否则开发模式双调用会重复渲染） |

---

*交接人：主开发会话 · 交接时间：2026-08-25 · 有问题先读 PLAN.md / CHANGELOG.md / DEBUGGING.md*
