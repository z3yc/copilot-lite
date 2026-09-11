# 🔒 第 1 周安全修复清单（5 项 · 可复盘）

> **用途**：执行并记录 [INTERVIEW_AUDIT.md](INTERVIEW_AUDIT.md) 第六节"第 1 周：安全修复（🔴 全清）"的 5 项修复，每项附代码级改法、验证清单与复盘模板。
> **使用方法**：
> 1. 动手前先跑一次基线测试（见下方"动手前"），确认全绿；
> 2. 按顺序执行 1→5，每完成一项：改代码 → 跑验证 → 勾选状态 → 填复盘；
> 3. 每完成一项单独提交一次 git（提交信息模板见文末）；
> 4. 全部完成后填"整体复盘"。
>
> 状态标记：⬜ 未开始 · 🔄 进行中 · ✅ 已完成

---

## 总进度

| # | 修复项 | 严重度 | 工作量 | 状态 | 复盘 |
|---|---|---|---|---|---|
| 1 | 检索层用户隔离（RAG + 记忆） | 🔴 严重 | 小 | ✅ | ✅ |
| 2 | SECRET_KEY 启动校验 + 模板补项 | 🔴 严重 | 小 | ✅ | ✅ |
| 3 | 前端 XSS：DOMPurify 消毒 | 🟠 高 | 小 | ✅ | ✅ |
| 4 | 上传文件名消毒 + 大小/类型限制 | 🟠 高 | 小 | ✅ | ✅ |
| 5 | 工具层归属校验（todo_update/complete/delete） | 🟠 高 | 小 | ✅ | ✅ |

> ✅ 全部完成于 2026-08-27（AI 助手代执行 + 全量测试验证）。测试结果：后端 85 用例全绿、覆盖率 81.21% ≥ 80%、ruff 通过；前端 22 用例全绿、构建通过。

---

## 动手前：基线确认

```powershell
# 后端：全部用例必须绿（当前 80 用例，覆盖率门槛 80%）
cd C:\Users\asus\Documents\copilot-lite\backend
uv run pytest

# 前端：测试 + 类型检查/构建
cd C:\Users\asus\Documents\copilot-lite\web
npm test
npm run build
```

基线结果记录：`pytest ____ passed · npm test ____ passed · build ✅/❌`

---

## 修复 1：检索层用户隔离（RAG + 记忆）🔴

**根因**（详见体检报告 2.1/2.2）：Qdrant 全局单集合，chunk payload 没有 `user_id`；`_bm25_search` 全表查不 JOIN documents；`hybrid_search`/`recall`/`_is_duplicate` 从不按用户过滤。多用户部署下 A 会召回 B 的文档与私人记忆。

**涉及文件**：`backend/app/rag/pipeline.py`、`vector_store.py`、`retriever.py`、`tools/kb_tool.py`、`memory/service.py` + 测试

### 改动步骤

**① `pipeline.py:67-79` — 写向量时 payload 加 user_id**

```python
points = [
    (
        row.id,
        vector,
        {
            "chunk_id": str(row.id),
            "document_id": str(document.id),
            "user_id": str(document.user_id),   # ← 新增
            "content": row.content,
            "meta": row.meta,
        },
    )
    for row, vector in zip(chunk_rows, vectors, strict=True)
]
```

**② `vector_store.py:83-110` — search() 支持 user_id 过滤（与 document_id 可组合）**

```python
async def search(
    self, vector: list[float], top_k: int,
    document_id: str | None = None, user_id: str | None = None,   # ← 新增参数
) -> list[SearchHit]:
    must = []
    if document_id:
        must.append(qm.FieldCondition(key="document_id", match=qm.MatchValue(value=document_id)))
    if user_id:
        must.append(qm.FieldCondition(key="user_id", match=qm.MatchValue(value=str(user_id))))
    qfilter = qm.Filter(must=must) if must else None
    # 下面 query_points 的 query_filter=qfilter 不变
```

**③ `retriever.py:51-79` — BM25 按用户过滤（JOIN documents 表）**

```python
async def _bm25_search(db: AsyncSession, query: str, top_k: int, user_id=None) -> list[SearchHit]:
    from sqlalchemy import or_
    from app.models import Document          # ← 新增 import

    terms = _tokenize(query)
    if not terms:
        return []

    conditions = [Chunk.content.ilike(f"%{term}%") for term in terms[:12]]
    stmt = select(Chunk)
    if user_id:                              # ← 新增：按用户过滤
        stmt = stmt.join(Document, Chunk.document_id == Document.id).where(
            Document.user_id == user_id
        )
    stmt = stmt.where(or_(*conditions)).limit(top_k * 5)
    rows = (await db.scalars(stmt)).all()
    # 后续打分逻辑不变
```

**④ `retriever.py:134-166` — hybrid_search 增加 user_id 参数并透传两路**

```python
async def hybrid_search(
    db, query, embeddings, vector_store,
    top_k=settings.RAG_TOP_K, candidate_k=..., rerank_top_n=...,
    document_id: str | None = None,
    user_id=None,                            # ← 新增参数
    reranker: Reranker | None = None,
):
    qvec = (await embeddings.embed([query]))[0]
    vector_hits = await vector_store.search(qvec, top_k, document_id=document_id, user_id=user_id)  # ← 透传
    keyword_hits = await _bm25_search(db, query, top_k, user_id=user_id)                             # ← 透传
    ...
```

**⑤ `tools/kb_tool.py:17-23` — 从 ctx 取用户并强制传入**

```python
results = await hybrid_search(
    db=ctx.session, query=query,
    embeddings=get_embedding_service(), vector_store=get_vector_store(),
    top_k=top_k,
    user_id=ctx.user_id,                     # ← 新增（这是修漏洞的关键一行）
)
```

**⑥ `memory/service.py` — 召回与去重按用户过滤**

```python
# _is_duplicate：签名加 user_id，调用处同步改
async def _is_duplicate(self, fact: str, user_id) -> bool:
    try:
        vec = (await self.embeddings.embed([fact]))[0]
        hits = await self.vector_store.search(vec, top_k=1, user_id=str(user_id))  # ← 过滤
        return bool(hits and hits[0].score >= DEDUP_THRESHOLD)
    except Exception:
        return False

# extract_from_session 内调用处（约 92 行）：
#   if await self._is_duplicate(fact):        ← 旧
#   if await self._is_duplicate(fact, user_id):  ← 新

# recall（约 150 行）：
hits = await self.vector_store.search(vec, top_k=top_k, user_id=str(user_id))      # ← 过滤
```

### ⚠️ 边界与坑

1. **旧数据迁移**：本地 `backend/qdrant_data/` 里已入库的 chunk 点没有 `user_id` 字段 → 修复后过滤检索将查不到它们。个人量级最省事：**在 Web 知识库页删除旧文档并重新上传**（重新摄取）。记忆集合的 payload 本来就带 user_id，无需迁移。
2. **测试兼容**：`test_retriever.py` 按位置传参调用 `hybrid_search`，新参数放 keyword-only 尾部不破坏现有用例；但测试里手工构造的 payload 没带 user_id——不传 user_id 时行为不变，仍会通过。
3. `ctx.user_id` 是 `uuid.UUID` 类型，`str(user_id)` 统一转字符串再进 Qdrant filter（Qdrant 要求字符串）。

### 新增测试（防回归，必做）

- `backend/tests/test_retriever.py` 加一例：**用户 A 和用户 B 各一篇文档**，A 查询时传 `user_id=A`，断言结果只含 A 的分块；不传 user_id 时（单用户模式）仍能召回全部。
- `backend/tests/test_memory.py` 加一例：A/B 各存一条相似记忆，A 的 `_is_duplicate(A同类事实, A)` 返回 True（和自己的比），B 的相似事实不影响 A；`recall(query, A)` 不返回 B 的记忆。

### 验证清单

```powershell
cd C:\Users\asus\Documents\copilot-lite\backend
uv run pytest              # 80+2 用例全绿，覆盖率 ≥80%
uv run ruff check .
```

手工验证（Web）：注册两个账号 → A 上传"我的旅行计划.md"、B 上传"我的理财记录.md" → A 提问"我的旅行计划里写了什么" → 回答只能引用 A 的文档，绝不出现 B 的内容（可故意让 B 的文档含敏感词测试）。

### 状态与复盘

- 状态：✅ 已完成
- 📝 复盘记录（实际执行）：
  - 实际改动：5 个文件（pipeline.py / vector_store.py / retriever.py / kb_tool.py / memory/service.py）+ 2 个测试文件新增隔离用例
  - 遇到的坑/卡点：**SQLAlchemy Uuid 类型比较不能传 str**——`Document.user_id == "uuid字符串"` 在绑定参数时抛 `AttributeError: 'str' object has no attribute 'hex'`，必须先 `uuid.UUID(str(user_id))` 转换。新测试正好抓住了这个坑。
  - 学到的新知识：Qdrant 本地模式支持 payload 过滤（`Filter(must=[FieldCondition(...)])`），多条件可组合；向量检索的隔离必须在**写入（payload 带 user_id）和查询（filter）两端**同时做。
  - 面试一句话话术："我发现语义检索层的隔离漏洞并修复了——payload 带 user_id，向量和 BM25 两路都强制过滤，还补了跨用户测试。"

---

## 修复 2：SECRET_KEY 启动校验 + 模板补项 🔴

**根因**（详见体检报告 2.3）：代码默认值 `"dev-secret-change-me-in-production"` 是公开的；`deploy/.env.example` 模板漏了 SECRET_KEY 项，照模板部署就用默认值 → 可伪造任意用户 JWT。

**涉及文件**：`backend/app/core/config.py`、`deploy/.env.example`、`backend/.env`、`deploy/.env`

### 改动步骤

**① `config.py` — 云模式禁止默认密钥（pydantic 校验器）**

在 `Settings` 类内加：

```python
from pydantic import model_validator

# 类内新增：
@model_validator(mode="after")
def _reject_default_secret(self):
    if self.RUN_MODE == "cloud" and self.SECRET_KEY == "dev-secret-change-me-in-production":
        raise ValueError(
            "生产模式禁止使用默认 SECRET_KEY，请在 .env 中设置强随机值"
        )
    return self
```

> 只拦 `cloud` 模式：本地开发（local）保持零配置可用，测试也不会被破坏。

**② `deploy/.env.example` — 补上 SECRET_KEY 模板项**

```ini
# JWT 签名密钥（生产必填，强随机值；生成命令见下行）
SECRET_KEY=
# 生成命令：python -c "import secrets;print(secrets.token_urlsafe(48))"
```

**③ 生成本地强密钥并写入两个 .env**（把 <生成值> 替换为实际输出）

```powershell
python -c "import secrets;print(secrets.token_urlsafe(48))"
# 把输出追加到 backend\.env 和 deploy\.env（若已有 SECRET_KEY 行则替换）：
Add-Content backend\.env "SECRET_KEY=<生成值>"
Add-Content deploy\.env  "SECRET_KEY=<生成值>"
```

### ⚠️ 边界与坑

1. **换密钥的副作用**：SECRET_KEY 变更后，之前签发的 token 全部失效 → 所有已登录用户需重新登录（个人项目无影响）。
2. `.env` 文件被 gitignore 保护，确认 `git ls-files | findstr .env` 只列出 `.env.example`。
3. 测试环境 RUN_MODE 默认 local，校验器不触发，不会破坏 pytest。

### 验证清单

```powershell
cd C:\Users\asus\Documents\copilot-lite\backend
uv run pytest                            # 全绿（local 模式不受影响）

# 手动验证校验器真的会拦（临时命令，测完删掉环境变量）：
$env:RUN_MODE="cloud"; uv run python -c "from app.core.config import settings"   # 应报错
Remove-Item Env:RUN_MODE                                                          # 恢复
```

### 状态与复盘

- 状态：✅ 已完成
- 📝 复盘记录（实际执行）：
  - 实际改动：config.py（model_validator 启动自检）+ deploy/.env.example（补 SECRET_KEY 模板项）+ 两个 .env 写入 64 位强随机密钥
  - 遇到的坑/卡点：写入 .env 时注意编码——PowerShell Set-Content 可能引入 UTF-8 BOM 影响第一行配置解析（本次检查无 BOM，安全）
  - 学到的新知识：pydantic `@model_validator(mode="after")` 是"配置自检"的标准位置——比文档提醒更可靠，因为**校验在启动时强制生效**
  - 面试一句话话术："我加了启动自检：云模式检测到默认 JWT 密钥直接拒绝启动——配置模板漏一项就可能把后门带上生产，校验比文档提醒更可靠。"

---

## 修复 3：前端 XSS —— DOMPurify 消毒 🟠

**根因**（详见体检报告 2.4）：`marked.parse` 默认放行原始 HTML，`dangerouslySetInnerHTML` 直接渲染——知识库/附件里的 `<img onerror=...>` 会在浏览器执行，与 token 存 localStorage 叠加成账号接管链。

**涉及文件**：`web/package.json`、`web/src/components/ChatPanel.tsx`

### 改动步骤

**① 安装依赖**

```powershell
cd C:\Users\asus\Documents\copilot-lite\web
npm install dompurify
```

**② `ChatPanel.tsx` — 渲染前消毒**

```tsx
// 文件顶部 import 区新增：
import DOMPurify from "dompurify";

// renderMarkdown 改为：
function renderMarkdown(text: string): string {
  try {
    const html = marked.parse(text, { async: false }) as string;
    return DOMPurify.sanitize(html);          // ← 关键一行
  } catch {
    return text;
  }
}
```

（第 201 行的 `dangerouslySetInnerHTML={{ __html: renderMarkdown(m.content) }}` 不动——消毒已发生在 renderMarkdown 内部。）

### ⚠️ 边界与坑

1. DOMPurify 默认白名单会**剥掉 `<script>`、`onerror` 等危险内容**，但保留安全标签（链接、代码块、表格），Markdown 正常样式不受影响。
2. dompurify v3 自带 TypeScript 类型，无需额外 @types。
3. 若想更彻底，可配合 marked 的 renderer 关闭原始 HTML——DOMPurify 已够用，不重复做。

### 验证清单

```powershell
cd C:\Users\asus\Documents\copilot-lite\web
npm test                    # 组件冒烟测试全绿
npm run build               # 类型检查 + 构建通过
```

手工验证（浏览器）：发送一条消息 `测试 <img src=x onerror=alert(1)> <script>alert(2)</script>` → 页面**无弹窗**，F12 查看渲染结果中危险标签已被移除。

### 状态与复盘

- 状态：✅ 已完成
- 📝 复盘记录（实际执行）：
  - 实际改动：package.json（+dompurify）+ ChatPanel.tsx（import + sanitize 一行）
  - 遇到的坑/卡点：无。dompurify v3 自带 TS 类型，`DOMPurify.sanitize(marked.parse(...))` 一行完成
  - 学到的新知识：marked 只负责"MD → HTML"，**不负责安全**；消毒是渲染层的独立职责（DOMPurify 白名单过滤危险标签/事件属性）
  - 面试一句话话术："LLM 输出会复述用户上传的内容，所以我把模型回答当不可信输入处理——渲染前 DOMPurify 消毒，堵住了'知识库恶意文档 → 存储型 XSS'的链路。"

---

## 修复 4：上传文件名消毒 + 大小/类型限制 🟠

**根因**（详见体检报告 2.5/2.6）：`file.read()` 无上限（内存 DoS）；客户端文件名直接拼 Path（绝对路径/`../` 可逃逸写任意路径）；未知扩展名默认按 markdown 解析（二进制垃圾入库）。

**涉及文件**：`backend/app/api/routes/documents.py`、`backend/app/api/routes/sessions.py` + 测试

### 改动步骤

**① `documents.py` — 大小限制 + 扩展名白名单 + 文件名消毒**

```python
# 文件顶部常量区新增：
MAX_UPLOAD_BYTES = 50 * 1024 * 1024   # 50MB

# upload_document 内，原 `content = await file.read()` 改为：
content = await file.read(MAX_UPLOAD_BYTES + 1)
if len(content) > MAX_UPLOAD_BYTES:
    raise HTTPException(status_code=413, detail=f"文件超过 {MAX_UPLOAD_BYTES // 1024 // 1024}MB 上限")

# 扩展名白名单（未知类型拒绝，而不是默认当 md 解析）：
ext = Path(file.filename or "").suffix.lower()
if ext not in _EXT_MAP:
    raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext or '未知'}")

# 保存原件处（约 92 行）——文件名消毒：
safe_name = Path(file.filename).name if file.filename else "unnamed"
if not safe_name or safe_name in {".", ".."}:
    safe_name = "unnamed"
(save_dir / safe_name).write_bytes(content)   # 只取纯文件名，杜绝路径穿越
```

**② `sessions.py` — 附件同样加限制**

```python
# 常量区新增：
MAX_UPLOAD_BYTES = 10 * 1024 * 1024   # 附件 10MB
_ALLOWED_EXTS = _MD_EXTS | _CODE_EXTS | {".pdf", ".docx"}

# upload_session_file 内：
content = await file.read(MAX_UPLOAD_BYTES + 1)
if len(content) > MAX_UPLOAD_BYTES:
    raise HTTPException(status_code=413, detail=f"文件超过 {MAX_UPLOAD_BYTES // 1024 // 1024}MB 上限")
ext = Path(file.filename or "").suffix.lower()
if ext not in _ALLOWED_EXTS:
    raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext or '未知'}")
```

### ⚠️ 边界与坑

1. `file.read(n)` 只读前 n 字节——超大文件不会再整读进内存。
2. `Path("C:\\evil\\x.txt").name` → `x.txt`、`Path("..\\x.txt").name` → `x.txt`，消毒后用 `.name` 即可；`_EXT_MAP` 里 `.doc` 映射 docx 但 python-docx 实际解析不了老格式 .doc，属历史遗留，可顺手把 `.doc` 从映射里删掉或保留（不影响本项）。
3. 测试上传的 `笔记.md` 在白名单内，现有用例不受影响。
4. 数据库 `title` 字段保留原始文件名（仅展示用途，不进路径），无需消毒。

### 新增测试（防回归）

- `test_session_files.py` 加一例：上传 `.exe` 文件 → 400。
- 文档上传超限（构造 >50MB 太慢，可先用小上限 monkeypatch 验证 413 分支）。

### 验证清单

```powershell
cd C:\Users\asus\Documents\copilot-lite\backend
uv run pytest
uv run ruff check .
```

手工验证（用 curl 或 Web）：① 上传一个 60MB 文件 → 413；② 文件名填 `..\..\evil.md` 上传 → 检查 `backend/data/<doc_id>/` 下保存的是 `evil.md`，且 `data/` 目录外**没有**新文件。

### 状态与复盘

- 状态：✅ 已完成
- 📝 复盘记录（实际执行）：
  - 实际改动：documents.py（50MB 上限 + 扩展名白名单 + 文件名取 basename）+ sessions.py（10MB 上限 + 附件白名单）+ 2 个 400 拒绝测试
  - 遇到的坑/卡点：`_detect_source_type` 原来"未知扩展名默认 md"要改为返回 None 由调用方拒绝——**必须先改调用点再改函数**，否则 source_type=None 直接进数据库报错
  - 学到的新知识：`file.read(n)` 支持"只读前 n 字节"，超限判断 `read(MAX+1)` 比读完整文件再判断更省内存；`Path("C:\\x\\evil.md").name` 和 `Path("..\\evil.md").name` 都只返回 `evil.md`
  - 面试一句话话术："上传安全我做了三道闸：读前限长（防内存 DoS）、扩展名白名单（防垃圾入库）、文件名取 basename（防路径穿越）——'入口设防'永远比'事后截断'可靠。"

---

## 修复 5：工具层归属校验（todo_update/complete/delete）🟠

**根因**（详见体检报告 2.7）：REST 接口有归属校验，但 LLM 可调用的**同名工具没有**——配上 prompt 注入即可越权改/删他人待办。授权必须与 REST 同标准。

**涉及文件**：`backend/app/tools/todo_tool.py` + 测试

### 改动步骤

`todo_tool.py` 三个函数统一加归属判断（工具层约定：返回 error 字符串而不是抛 HTTP 异常，让 ReAct 循环继续）：

```python
# todo_update（约 89-90 行）：
todo = await ctx.session.get(Todo, uuid.UUID(todo_id))
if todo is None or todo.user_id != ctx.user_id:      # ← 加 user_id 判断
    return {"error": f"待办 {todo_id} 不存在或无权限"}

# todo_complete（约 112-113 行）：
todo = await ctx.session.get(Todo, uuid.UUID(todo_id))
if todo is None or todo.user_id != ctx.user_id:      # ← 同上
    return {"error": f"待办 {todo_id} 不存在或无权限"}

# todo_delete（约 123-124 行）：
todo = await ctx.session.get(Todo, uuid.UUID(todo_id))
if todo is None or todo.user_id != ctx.user_id:      # ← 同上
    return {"error": f"待办 {todo_id} 不存在或无权限"}
```

> `todo_list` 和 `_category_id_by_name` 已有 user_id 过滤，不动。

### ⚠️ 边界与坑

1. `ctx.user_id`（`uuid.UUID`）与 `Todo.user_id`（数据库 UUID 列）直接 `!=` 比较即可。
2. 错误文案用"不存在**或无权限**"，与 REST 层"越权返回 404"的策略一致——**不泄露资源是否存在**。

### 新增测试（防回归）

`backend/tests/test_tools.py` 加一例：用户 A 建待办 → 用 `ToolContext(user_id=B)` 调 `todo_update/complete/delete` → 断言返回 error 且待办原样未变。

### 验证清单

```powershell
cd C:\Users\asus\Documents\copilot-lite\backend
uv run pytest
uv run ruff check .
```

手工验证（CLI 或对话）：A 登录建待办，B 登录让 AI"完成待办 <A的id>" → 应回复"不存在或无权限"，A 的待办未被改动。

### 状态与复盘

- 状态：✅ 已完成
- 📝 复盘记录（实际执行）：
  - 实际改动：todo_tool.py 三个函数加 `todo.user_id != ctx.user_id` 判断 + 1 个跨用户测试（改/完成/删除三连拒绝断言）
  - 遇到的坑/卡点：无。工具层返回 error 字符串（让 ReAct 循环继续）而非 HTTP 异常——与 REST 层策略不同但目标一致
  - 学到的新知识：**授权不对称**的教训——REST 有校验、LLM 工具没有，就是第二个未设防的入口；Agent 工具的授权必须与 API 同标准
  - 面试一句话话术："我修了一个授权不对称：REST 有归属校验、LLM 工具没有——Agent 工具是绕过人工的第二个入口，授权标准必须和 API 完全一致。"

---

## 提交建议（每完成一项提交一次，风格与 PLAN 约定一致）

```powershell
git add -A
git commit -m "fix(security): 检索层用户隔离（payload user_id + BM25/向量过滤 + 跨用户测试）"
git commit -m "fix(security): 云模式拒绝默认 SECRET_KEY，模板补项"
git commit -m "fix(security): 前端 DOMPurify 消毒修复存储型 XSS"
git commit -m "fix(security): 上传限长/白名单/文件名消毒防路径穿越与 DoS"
git commit -m "fix(security): 工具层归属校验对齐 REST 授权"
```

---

## 整体复盘（5 项全部完成 ✅ 2026-08-27）

**时间账**：计划 1 周（小工作量 × 5），实际 —— 一次性完成（AI 助手代执行 + 全量测试验证）

| 问题 | 回答 |
|---|---|
| 哪一项比预期难？卡在哪？ | 修复 1 的 BM25 过滤：SQLAlchemy `Uuid` 列比较传了字符串 → `AttributeError: 'str' object has no attribute 'hex'`，必须 `uuid.UUID(str(user_id))` 转换。新测试第一跑就暴露了它 |
| 哪一项比预期简单？ | 修复 3（DOMPurify 一行解决）与修复 5（三个函数各加一个判断） |
| 修改中破坏了什么测试？怎么发现的？ | 只有一处：test_memory.py 里 monkeypatch 的 `_no_dup(self, fact)` 签名与新 `_is_duplicate(self, fact, user_id)` 不匹配，改代码时同步更新了测试 |
| 下次做类似安全修复能更快的方法？ | ① 先写"会失败的测试"再改代码（这次新测试直接抓住了 UUID 坑）；② 改动函数签名时先全局 grep 所有调用点与测试 monkeypatch |
| 这 5 项修复给面试新增了什么素材？ | 一个完整的"安全自审 → 修复 → 防回归测试"故事，含一个真实的技术坑（UUID 类型）和一个设计教训（检索层隔离/授权不对称） |

**给面试的总结话术**（背熟）：

> "项目后期我做了一次安全自审，发现并修复了五类问题：检索层跨用户隔离（最隐蔽，它不在 API 层而在语义检索链路）、默认 JWT 密钥、存储型 XSS、上传路径穿越与内存 DoS、工具层授权不对称。每一项我都补了防回归测试。这件事让我意识到：**数据隔离要穿透到召回链路，安全校验要落在每一个入口，而 Agent 工具是必须和 REST 同标准鉴权的第二入口。**"

---

> 关联文档：[INTERVIEW_AUDIT.md](INTERVIEW_AUDIT.md)（体检报告）· [INTERVIEW_QA.md](INTERVIEW_QA.md)（面试问答）· 后续周次计划见体检报告第六节
