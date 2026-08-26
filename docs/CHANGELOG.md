# Changelog · 变更记录

> Copilot-Lite 项目演进记录。格式：[语义化版本](https://semver.org/lang/zh-CN/) + 里程碑说明。

---

## [0.10.1] · 2026-08-25 · 修复：工具参数类型容错（Agent 改待办优先级失败）

### 🐛 修复
- **根因（两层叠加）**：
  1. `_build_parameters` 不识别 Optional 联合类型——`_TYPE_MAP.get(int | None)` 查不到，
     `todo_update` 的 `priority: int | None` 在 schema 中被声明为 **`"string"`**，
     误导 LLM 传字符串 `"5"`；
  2. 执行器不做类型容错，字符串 `"5"` 直接进 `min(5, "5")` 抛 TypeError，
     且异常发生在 **commit 之前** → 数据库未更新 → 优先级始终显示旧值；
- **修复**：① schema 生成支持联合类型剥壳（`int|None`→integer、`list[str]|None`→array）；
  ② `registry.execute` 按 schema 类型对参数强制转换（`"5"`→5、数组字符串→`json.loads`），
  转换失败返回友好错误不中断对话；
- 测试：新增 4 用例（字符串优先级更新且**断言数据库真实落库** / 字符串数组 /
  非法参数不改数据 / schema 类型映射），共 64 用例，覆盖率 80.28%。

---

## [0.10.0] · 2026-08-25 · Rerank 重排（检索链路增强）

### ✨ 新增
- **Rerank 精排**：混合检索（BM25+向量+RRF）后接入 **bge-reranker-base** 交叉编码器
  二次精排，补齐"检索 → 重排 → 生成"链路（`backend/app/rag/reranker.py`）；
- **链路设计**：向量/BM25 各自召回（`RAG_TOP_K`）→ RRF 融合出候选
  （`RAG_RERANK_CANDIDATE_K`）→ 精排取前 N 注入 LLM（`RAG_RERANK_TOP_N`）；
- **配置开关**：`RAG_RERANK_ENABLED`（默认开）——关闭时行为与旧版完全一致，
  可 A/B 对比精排效果；
- **异步封装**：同步 ONNX 推理走线程池不阻塞事件循环；模型懒加载 + hf-mirror 镜像复用
  （fastembed 0.8 类名 `TextCrossEncoder`，高版本同能力入口为 `TextReranking`）；
- 测试：新增 8 用例（排序截断/空与单候选短路/单例懒加载/链路接入/开关关闭），
  共 **60 用例**，覆盖率 **80.69%**（Fake 重排器，不下载模型）。

---

## [0.9.0] · 2026-08-25 · 长期记忆系统

### ✨ 新增
- **自动提取**：会话结束后台 LLM 批量抽取用户事实/偏好（结构化 JSON，
  分类：偏好/事实/背景；`MEMORY_EXTRACT_ENABLED` 开关）；
- **向量记忆**：`memory_facts` 表 + Qdrant `copilot_memories` 集合，
  向量相似度去重（同事实不重复累积）；
- **混合召回**：对话按当前问题自动注入相关记忆（等价于"会话开始 + 话题切换补充"）；
- **可视化管理**：`GET/PATCH/DELETE /memories` + 个人中心"🧠 我的记忆"页
  （查看 / 编辑内容与分类 / 删除）；
- **fix(qdrant)**：Qdrant 客户端共享单例——本地模式同一目录只允许一个客户端
  实例，多 collection（文档/记忆）必须共享 client（修复潜在生产崩溃）；
- 测试：52 用例（提取/降级/召回/编辑/删除/API），覆盖率 80.34%。

---

## [0.8.0] · 2026-08-25 · 完整待办工作区

### ✨ 新增
- **侧边栏"📋 待办"独立工作区**（Todoist 风格）：
  - 左侧导航：今天/本周/未来/已过期/无日期分组 + 分类列表（带计数）；
  - **时间高亮**：过期红 / 今天橙 / 本周黄；
- **AI 快速添加**：`POST /todos/ai-create` 自然语言 → DeepSeek 结构化解析
  （时间/分类/标签），失败自动降级为整句标题；
- **分类系统**：Category 表（预留自定义）+ 默认 4 类（工作/生活/学习/其他），
  注册与启动时自动 seed；
- **标签**：自由标签（JSON 数组），支持按标签过滤；
- **全字段编辑**：`PATCH /todos/{id}`（标题/状态/优先级/日期/分类/标签）；
- **Agent 工具升级**：todo_create 支持分类/标签、新增 todo_update、
  todo_list 分类过滤；
- 测试：46 用例（分类/CRUD/AI 解析与降级/工具），覆盖率 80.54%。

---

## [0.7.0] · 2026-08-25 · 用户认证与数据隔离

### ✨ 新增
- **注册 / 登录接口**：`POST /auth/register`、`POST /auth/login`、`GET /auth/me`；
- **JWT 无状态认证**：HS256 签名，24 小时有效（`core/security.py`）；
- **PBKDF2 密码哈希**：标准库实现（盐 + 10 万次迭代），常量时间比较防时序攻击；
- **数据按用户隔离**：会话 / 待办 / 文档全部归属当前用户，越权访问返回 404；
- **前端登录页**：登录/注册切换、token localStorage 管理、请求自动携带
  Authorization、401 自动回登录页、侧边栏退出按钮；
- 认证测试：未认证 401 / 注册 409 冲突 / 错误密码 401（37 用例，覆盖率 80.63%）。

---

## [0.6.0] · 2026-08-25 · 会话附件 + UI 全面增强

### ✨ 新增：会话级附件（对话上传的文件仅本次会话可见）
- **产品逻辑变更**：对话中上传的文件不再自动进入知识库，改为**会话附件**
  （`session_files` 表），仅本次对话可见，提问时注入上下文；
- 数据模型：`SessionFile`（session_id + 提取文本，截断 20K 字符存储），迁移 `d73001c3fa47`；
- 后端接口：`POST /sessions`（预创建）、附件上传/列表/删除；
- 上下文注入：chat 时附件作为 system 消息注入（每文件 1500 字符，最多 5 个），
  回答注明来源文件；
- 与知识库（documents/chunks/向量）**完全隔离**——附件不产生任何检索数据；
- 前端：输入栏 📎 上传 → Tag 展示 → 可删除 → 切换会话自动加载。

### ✨ 新增：知识库分类视图与搜索
- 侧边栏分类导航（全部/笔记/PDF/Word/代码/网页，带数量徽标）；
- 后端 `/documents` 支持 `type` 与 `q` 参数（**内容级搜索**：标题 + 分块内容双匹配）；
- 主区分组展示 + 分类 Tag + 防抖搜索（300ms）。

### ✨ 新增：暗色模式
- antd `darkAlgorithm` + CSS 变量双主题；侧边栏一键切换；`localStorage` 记忆偏好。

### 🎨 UI 重构：Ant Design
- 全面引入 antd 组件库（Layout/List/Card/Collapse/Tag/Upload/Popconfirm…）；
- 主题色 `#4f6ef7`，业务代码 gzip 仅 20KB（manualChunks 拆包）。

### 🐛 修复
- 知识库分类筛选不生效（后端缺 `source_type` 过滤参数）；
- 工具返回字符串被二次 JSON 序列化；
- Windows 控制台 GBK 无法渲染 emoji（CLI 强制 UTF-8）；
- 配置 `.env` 路径与启动目录解耦（基于文件位置解析）。

---

## [0.5.0] · 2026-08-25 · 工程化（P4）

### ✨ 新增
- **CI 流水线**：`.github/workflows/ci.yml`（后端 ruff+pytest+覆盖率≥80% / 前端 tsc+构建）；
- **一键启动**：`scripts/dev_start.ps1`（装依赖→迁移→起前后端→开浏览器）；
- **部署编排（预留）**：`deploy/`——Docker Compose（pg+qdrant+redis+backend+web）、
  Dockerfile、Nginx（SSE 关缓冲）、`.env.example`、`DEPLOY.md`；
- **测试增强**：覆盖率 72%→83%，新增解析器/流水线/kb_search 工具测试；
- 覆盖率门槛：`fail-under=80`（未达标 CI 直接失败）。

---

## [0.4.0] · 2026-08-25 · 双前端（P3）

### ✨ 新增
- **SSE 流式对话**：`POST /chat/stream`（session→chunk→done 事件）；
- **会话管理 API**：列表 / 历史消息 / 删除；
- **Todo REST API**：CLI 与前端共用；
- **CLI 子命令**：`copilot todo list/add/done/rm`；
- **Web 前端**：React + Vite + TS（对话流式渲染、会话列表、知识库管理）。

---

## [0.3.0] · 2026-08-25 · 知识库 RAG（P2）

### ✨ 新增
- 多格式解析器：MD（标题层级）/ PDF（页码）/ DOCX / 代码 / 网页；
- 智能分块：标题路径栈 + 段落聚合 + 重叠控制；
- 嵌入：fastembed + BGE-small-zh-v1.5（512 维，本地离线，hf-mirror 镜像）；
- 向量库：Qdrant **本地模式**（无 Docker），数据落 `backend/qdrant_data/`；
- 摄取流水线：解析→分块→chunks 表→嵌入→Qdrant→状态回写；
- **混合检索**：BM25 + 向量 + RRF 融合；
- 知识库工具 `kb_search`（Agent 可调用）+ **引用溯源**（文档>章节>页码）；
- 文档管理 API：上传（自动摄取）/ 列表 / 详情 / 删除（级联清理）。

---

## [0.2.0] · 2026-08-25 · Agent 核心（P1）

### ✨ 新增
- DeepSeek LLM 客户端（Function Calling）；
- **可插拔工具注册表**（`@tool` 装饰器 + 签名自动生成 JSON Schema）；
- Todo 工具集（create/list/complete/delete）；
- **ReAct 编排器**（系统提示 + 历史窗口 + 最大轮数保护）；
- 聊天 API + CLI（`copilot chat` / `copilot ask`）；
- 多智能体扩展点：`BaseAgent` 抽象 + Agent-as-Tool 设计。

---

## [0.1.0] · 2026-08-25 · 项目地基（P0）

### ✨ 新增
- FastAPI 异步骨架（uv 管理，Python 3.12）；
- 配置模块（pydantic-settings，本地 SQLite / PostgreSQL 双支持）；
- 核心 ORM（User / ChatSession / Message / Todo / Document）+ Alembic 迁移；
- 本地 PostgreSQL 接入（开发与生产同构）。
