# 调试与排障记录（Debugging Log）

> Copilot-Lite 开发过程中的问题排查实录，按主题分类。
> 每个条目：**现象 → 排查 → 根因 → 解决 → 经验**。
> 面试价值：真实问题 + 排查思路 + 工程化修复，比"我会 XX 技术"更有说服力。

---

## 一、环境与工具链

### 1. Gitee 推送认证失败（凭据地狱）
- **现象**：`git push` 反复 `Unauthorized`，凭据管理器里明明有 Gitee 凭据
- **排查**：
  1. `cmdkey /list` 发现两条旧 Gitee 凭据 → 删除后仍失败；
  2. Gitee API 验证令牌 → 用户发来的 32 位字符串**不是有效令牌**（401）；
  3. `git credential fill` 取回为空 → wincred helper 与 cmdkey 兼容问题；
  4. `git ls-remote` **内嵌凭据**成功（exit 0）→ 证明令牌有效，问题在凭据链路。
- **根因**：① 旧凭据失效未清理；② 执行环境（沙箱）无法派生凭据 helper 子进程，git 拿不到凭据。
- **解决**：内嵌凭据 URL 完成推送；用户侧清理凭据后重新生成令牌。
- **经验**：凭据问题先分两层排查——"令牌是否有效"（API 直测）与"git 是否取到"（ls-remote/credential fill）。

### 2. Windows PowerShell 的 curl 别名陷阱
- **现象**：`curl -X POST ...` 报 `找不到与参数名称"X"匹配的参数`
- **根因**：PowerShell 里 `curl` 是 `Invoke-WebRequest` 的别名，不支持 `-X/-F`
- **解决**：改用 `curl.exe`（真 curl）或 PowerShell 原生 `Invoke-RestMethod`
- **经验**：Windows 命令行工具命名冲突（`curl`/`curl.exe`、`python`/`py`）是高频坑。

### 3. PS 5.1 读取 UTF-8 脚本乱码
- **现象**：`.ps1` 脚本报 `字符串缺少终止符`，中文显示乱码
- **根因**：Windows PowerShell 5.1 默认按 **GBK** 读取无 BOM 的 UTF-8 文件
- **解决**：脚本输出改纯 ASCII；或换 PowerShell 7（`pwsh`）
- **经验**：跨版本脚本工具，纯 ASCII 输出最稳。

### 4. HuggingFace 模型下载失败（国内网络）
- **现象**：`ConnectTimeout` / `xet 协议 401`，BGE 模型下不下来
- **解决**：`HF_ENDPOINT=https://hf-mirror.com` 镜像 + `HF_HUB_DISABLE_XET=1` 禁用 xet；代码内 `os.environ.setdefault` 固化（用户显式配置优先）
- **经验**：国内 AI 开发的标配环境问题；setdefault 让镜像可覆盖。

### 5. Vite 只监听 IPv6
- **现象**：`http://127.0.0.1:5173` 连接失败，`http://localhost:5173` 正常
- **根因**：Vite 默认监听 `::1`（IPv6 localhost）
- **解决**：浏览器用 `localhost` 访问；无需改配置
- **经验**：localhost 与 127.0.0.1 在双栈系统上不等价。

---

## 二、后端与数据

### 6. `.env` 读不到（启动目录解耦）
- **现象**：`chat` 返回 503"未配置 DEEPSEEK_API_KEY"，但 `.env` 里明明有 key
- **排查**：进程命令行无异常；`/health` 正常 → 锁定配置加载
- **根因**：pydantic-settings 的 `env_file=".env"` 按**进程 cwd** 解析；从 `cli` 目录启动后端 → 找不到 `backend/.env`
- **解决**：`env_file` 改为基于文件位置绝对路径（`Path(__file__).parents[2] / ".env"`），与启动目录解耦
- **经验**：配置路径不要依赖 cwd——这是部署环境的经典坑。

### 7. API Key 误填 `.env.example`（泄露风险）
- **现象**：key 配了但读不到；搜索发现 key 在 `.env.example`
- **风险**：`.env.example` 会被 git 提交 → key 泄露到仓库
- **处理**：提取 key 迁移到 `.env`；还原示例文件；确认 key **未进入 git 历史**（`git status` 是未提交状态，及时拦截）
- **经验**：密钥类文件（`.env*`）gitignore 必须前置；发现误提交立即处理历史。

### 8. qdrant-client 1.19 API 变更
- **现象**：`AttributeError: 'QdrantClient' object has no attribute 'search'`
- **根因**：新版本 `search` 废弃，改为 `query_points`
- **解决**：改用 `query_points(collection_name, query=vector, limit=..., query_filter=...)`；`delete` 传参同理（`run_in_executor` 不支持 kwargs → lambda 包装）
- **经验**：SDK 大版本 API 变动是常态，`dir(client)` 探方法最直接。

### 9. 工具返回字符串被二次 JSON 序列化
- **现象**：`kb_search` 返回的 JSON 字符串被再包一层 → 模型看到 `'"[...]"'`
- **根因**：`registry.execute` 统一 `json.dumps(result)`，字符串也被转义
- **解决**：`isinstance(result, str)` 时原样返回
- **经验**：**这是覆盖率测试抓出的真实 bug**——写测试不是凑数字。

### 10. BM25 多词 AND 过严
- **现象**：检索"FastAPI 是什么"返回空
- **根因**：查询词用 AND 连接，要求块同时含所有词（含单字"是/什/么"）
- **解决**：改 **OR 召回** + 命中词数占比打分（更接近 BM25 语义）
- **经验**：中文分词粒度（逐字）与检索逻辑要配套设计。

### 11. Pydantic 响应模型类型序列化
- **现象**：上传文档 500：`id` 期望 str 收到 UUID
- **解决**：`DocumentOut.id` 用 `uuid.UUID` 类型（Pydantic 自动序列化），`created_at` 用 `datetime`
- **经验**：`model_validate` ORM 对象时，字段类型要与 DB 类型一致。

### 12. pytest Windows 文件句柄占用
- **现象**：teardown 删除 `test_copilot.db` 报 `PermissionError: WinError 32`
- **根因**：模块级 async engine 未 dispose，SQLite 文件被占用
- **解决**：autouse fixture 中 `await engine.dispose()` 后再删；测试前也清理残留（防污染）
- **经验**：Windows 上 SQLite 测试的句柄管理 + 测试间隔离。

### 13. Python bytes 字面量不能含中文
- **现象**：`SyntaxError: bytes can only contain ASCII literal characters`
- **解决**：测试内容用 `str`，调用处 `.encode()`
- **经验**：`b"..."` 只接受 ASCII。

---

## 三、前端与 UI

### 14. 知识库分类筛选不生效
- **现象**：侧边栏选"PDF"，主区仍显示全部文件
- **排查**：前端切分类只改状态；后端 `/documents` **根本没有 type 参数**
- **解决**：后端加 `source_type` 过滤 + 前端 `fetchDocs(q, type)` 携带分类；上传/删除/刷新统一走 `loadDocs` 保持条件
- **经验**：**前端状态与后端查询条件必须一一对应**——UI 改动前先确认接口能力。

### 15. 对话出现两个 AI 头像
- **现象**：发送消息后出现两个机器人头像
- **根因**：消息列表已追加 assistant 消息（带头像），`busy` 状态又渲染独立 typing 气泡（也带头像）
- **解决**：删除独立 typing 气泡，光标 `▍` 并入生成中的消息气泡
- **经验**：加载态与数据流要复用同一渲染通道，避免"双份 UI"。

### 16. 非真流式（一次性生成）
- **现象**：回复"突然冒出来"而非逐字生成
- **根因**：编排器完整执行后按 40 字符分片下发
- **解决**：`Orchestrator.run_stream()` 用模型流式接口逐 token 转发；利用 DeepSeek"工具轮 content 为空"的行为约定兼容工具调用
- **经验**：SSE 传输层 ≠ 真流式，流式要从模型层做起。

### 17. CLI emoji 渲染崩溃
- **现象**：`UnicodeEncodeError: 'gbk' codec can't encode character '\u2705'`
- **解决**：CLI 启动时 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`
- **经验**：Windows GBK 控制台 vs UTF-8 输出的经典冲突。

### 18. 流式回复内容重复（StrictMode 双调用 + 可变更新）
- **现象**：AI 回复出现大量重复的字段/片段（开发模式下）
- **排查**：后端接口直接 curl 输出正常 → 锁定前端渲染；定位到 `onChunk` 的 `setMessages` updater
- **根因**：updater 内 `last.content += chunk` **直接修改了 state 数组中的对象**
  （`[...prev]` 是浅拷贝，最后一条消息仍是引用）；React 18 `<StrictMode>`
  在开发模式会**双调用 updater** → 同一 chunk 被追加两次 → 内容重复
- **解决**：改为**不可变更新** `next[lastIdx] = { ...last, content: last.content + chunk }`；
  `onError` 分支同步修复
- **经验**：**React 状态更新必须不可变**——StrictMode 双调用是"照妖镜"，
  能暴露所有 mutate 的 updater；生产构建不触发，但这是真实隐患

---

## 四、排障方法论（面试总结）

1. **分层定位**：先确认"环境问题"还是"代码问题"（如 #1 令牌 vs 凭据链路、#6 启动目录）
2. **用接口实测**：`ls-remote`/`curl` 直测绕过中间层，快速二分
3. **最小复现**：测试用例即复现脚本（#9/#10 都是测试先暴露）
4. **测试防回归**：每个修复补一条测试（覆盖率从 72% → 81% 的过程中抓出多个真 bug）
5. **文档沉淀**：每个坑记录现象/根因/解决（本文档），面试直接可讲

---

*共 18 条排障记录 · 覆盖环境/后端/前端三类 · 与 docs/CHANGELOG.md 互为补充*
