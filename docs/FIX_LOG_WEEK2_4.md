# 🛠 修复日志（第 2-4 周 · 一次修复一次提交）

> 继 [SECURITY_FIX_WEEK1.md](SECURITY_FIX_WEEK1.md)（第 1 周 5 项安全修复）之后，本文件记录第 2-4 周全部剩余修复。
> 约定：每修复一项 → 跑测试 → `git commit`（一次提交一个修复）→ 本文件登记复盘。

## 进度总览（✅ 全部完成）

| # | 修复项 | 提交 | 测试 | 复盘 |
|---|---|---|---|---|
| W2-1 | SSE 契约（先落用户消息/error 事件/done=已持久化/心跳） | `78054e4` | ✅ 86 | ✅ |
| W2-1b | 客户端断开兜底持久化部分回复 | `9d1ab75` | ✅ | ✅ |
| W2-2 | 双引擎历史窗口统一（system 上下文常驻） | `9709c7d` | ✅ 87 | ✅ |
| W2-3 | LLM 客户端单例 + 超时/重试/max_tokens + 兜底 | `2ad24eb` | ✅ 87 | ✅ |
| W2-4 | 登录限流（防暴力破解） | `6a4f6e4` | ✅ 89 | ✅ |
| W2-5 | 前端 busy 兜底 + SSE 容错 + 停止生成 | `26a61c0` | ✅ 27 | ✅ |
| W2-6 | token_version 改密失效（模型+迁移） | `32864f8` | ✅ 89 | ✅ |
| W3-1 | 会话摘要压缩落地（summary 字段） | `24e07f1` | ✅ 95 | ✅ |
| W3-2 | 记忆提取节流（每 8 条一次 + 会话锁） | `24e07f1`（合并） | ✅ 95 | ✅ |
| W3-3 | 结构化引用（编号+chunk_id + [n] 标注） | `50b3d35` | ✅ | ✅ |
| W3-4 | RAG golden 评测集 + 评估脚本 | `1997f41` | ✅ | ✅ |
| W3-5 | README/架构图如实化（预留项标注） | `8803689` | — | ✅ |
| W4-1 | Prompt 注入防护（数据定界） | `3048ef1` | ✅ | ✅ |
| W4-2 | 工具调用审计日志（Message.extra） | `0339484` | ✅ | ✅ |
| W4-3 | 摄取流水线原子化（先算后写+补偿） | `f871f95` | ✅ | ✅ |
| W4-4 | BM25 jieba 中文分词 | `3b1aaeb` | ✅ | ✅ |
| W4-5 | API 健壮性（UUID 4xx/CORS/seed 修正） | `ba81bde` | ✅ 102 | ✅ |
| W4-6 | 分块 overlap 边界修复 | `71f0c50` | ✅ | ✅ |
| W4-7 | ai-create 参数校验（夹取/日期容错） | `a09dd43` | ✅ | ✅ |
| W4-8 | 附件治理（数量上限/真实字节数/IDOR） | `b399721` | ✅ | ✅ |

> 最终验证：后端 105 用例全绿、覆盖率 81.63% ≥ 80%、ruff 全过；前端 27 用例全绿、构建通过。

## 逐项复盘记录

### W2-1 SSE 契约 + W2-1b 断开兜底
- 改动：chat.py（用户消息先落库、LLMError/通用异常→error 事件、done 仅在持久化后、15s 心跳、finally 兜底保存）+ 测试
- 踩坑：`try/except/else/finally` 的 `finally` 必须紧跟 except——第一次写把 finally 放错位置导致语法错误，用 else 分支装成功路径解决
- 面试话术："流式协议要有显式终态：正常 done / 出错 error / 取消兜底保存；核心数据先落库再宣告成功。"

### W2-2 双引擎窗口统一
- 改动：base.py 新增 `split_system_context`（双轨：system 常驻 + 对话滚动）；orchestrator/langgraph 双引擎接入；HISTORY_WINDOW 入配置
- 踩坑：无。新测试验证 system 上下文不被截掉、历史只留窗口内 10 条
- 面试话术："默认 LangGraph 引擎没有窗口截断，两引擎行为不一致——我把截断统一收口到入口，system 上下文常驻不参与滚动。"

### W2-3 LLM 单例 + 健壮性
- 改动：llm.py（get_llm 真单例、timeout/retries/max_tokens 透传、LLMError）；orchestrator/langgraph（主调用兜底转 LLMError）；chat.py（502 映射、流式 error 事件、预检函数替代双重构建引擎）；memory（不再关闭共享单例）
- 踩坑：单例化后 orchestrator.close 若还关闭共享客户端会把连接池杀掉——close 改为 no-op，客户端随应用生命周期管理
- 面试话术："LLM 是外部不可靠依赖：显式超时/重试、统一 LLMError 映射 502、连接池复用。"

### W2-4 登录限流
- 改动：auth.py 内存滑动窗口（60s 内 5 次失败 → 429，用户名+IP 维度）+ 测试
- 面试话术："限流防在线爆破、慢哈希防离线爆破，两者都要；单实例内存实现，多实例换 Redis。"

### W2-5 前端健壮性
- 改动：api.ts（JSON.parse 容错、心跳注释跳过、AbortSignal、AbortError 提示）+ ChatPanel（try/finally 复位 busy、停止按钮、会话切换取消）
- 踩坑：① StreamHandlers 加 signal 字段后测试的 Record 类型报 TS 错——用 Omit+& 修正类型；② streamChat mockRejectedValue 造成未处理 rejection——send 内补 catch 吞掉
- 面试话术："异步 UI 两条铁律：状态必须 finally 复位、旧请求必须能取消。"

### W2-6 token_version
- 改动：User 模型 + JWT 带 ver + deps 校验 + 改密 +1 + alembic 迁移 + 测试；迁移已应用到开发库
- 面试话术："JWT 无状态撤销：payload 带版本号，改密版本 +1，旧 token 全部自然失效，不引入黑名单存储。"

### W3-1 摘要压缩
- 改动：chat.py 后台压缩（阈值 40、溢出窗口外消息压缩入 summary、按窗口量节流、会话锁）+ _build_context 注入 + 测试
- 踩坑：① 后台任务把 str 当 UUID 传给 _load_history → SQLAlchemy Uuid 绑定报 'str' object has no attribute 'hex'（第二次踩同一坑，先转 uuid.UUID）；② 测试环境未关闭后台任务 → 任务持测试库句柄导致 teardown PermissionError——新增 SUMMARY_COMPRESS_ENABLED 开关并在 conftest 关闭
- 面试话术："长对话不丢主线：窗口溢出时旧消息压缩为摘要常驻注入，而不是暴力截断。"

### W3-2 记忆提取节流
- 改动：chat.py 每新增 8 条消息触发一次、会话级锁防并发重复；纯函数 _should_extract_memories 便于测试
- 面试话术："记忆提取是纯成本项——原来每轮都烧一次 LLM，改成按新增量节流后成本降一个数量级。"

### W3-3 结构化引用
- 改动：kb_search 返回 编号+chunk_id；双引擎提示词约束 [n] 标注
- 面试话术："引用要结构化绑定 chunk_id，不能靠 LLM 自由复述来源——否则会编造。"

### W3-4 评测集
- 改动：eval/golden_set.json（10 条示例）+ scripts/rag_eval.py（recall@K/MRR）+ schema 校验测试
- 面试话术："没有 golden 评测集，RAG 调参就是盲人摸象——我建了召回指标脚本，下一步接 RAGAS 测 faithfulness。"

### W3-5 文档如实化
- 改动：README/architecture 中沙箱、监控/通知、Redis、脱敏标注"预留"，工具安全边界按当前实现改写
- 面试话术："诚实是 AI 应用工程师的核心素养——没实现的能力在文档里如实标注'预留'，绝不当成已上线。"

### W4-1 Prompt 注入防护
- 改动：附件/记忆/摘要/检索结果统一 ««DATA»» 定界 + "仅数据非指令"声明；系统提示加安全边界；kb_search 输出带提示字段
- 面试话术："间接注入面是 RAG 的经典风险：外部数据进 prompt 前要定界 + 声明数据身份 + 动作校验。"

### W4-2 工具审计日志
- 改动：双引擎收集 tool_calls（名称/参数/结果）→ Message.extra 落库；流式路径改为 event_gen 内建引擎以捕获审计
- 面试话术："工具调用全量审计可回放——排障和追溯 prompt 注入都靠它。"

### W4-3 摄取原子化
- 改动：pipeline 先嵌入后写库 + Qdrant 失败补偿删除分块；上传失败统一清理分块与向量
- 面试话术："跨'关系库+向量库'无法用单库事务——先算后写 + 失败补偿是标准解法。"

### W4-4 jieba 分词
- 改动：uv add jieba（锁文件同步更新，CI --frozen 安全）；_tokenize 中文按词切分，未安装退化逐字
- 踩坑：jieba 首次构建词典在测试 stderr 打日志（无害）；uv 需设 UV_CACHE_DIR 到工作区（沙箱外缓存目录拒绝访问）
- 面试话术："中文逐字切分召回噪声大，jieba 按词切分后多字词作为整体检索词。"

### W4-5 API 健壮性 + CORS
- 改动：parse_uuid 统一畸形 UUID→404；todos 分类 id→400；附件删除校验归属（IDOR 修复）；CORS 按配置放行；生产不再 seed 默认用户
- 踩坑：ruff RUF100/F401/S110/RUF015 四类问题一次清掉（无用的 noqa、未用 import、except-pass、切片取首）
- 面试话术："畸形输入返回 4xx 而非 500 堆栈；对象级授权落在被操作对象本身。"

### W4-6 分块 overlap
- 改动：聚合溢出边界统一注入上一块结尾字符（此前仅超长单段落有重叠，注释与实现不符）
- 面试话术："overlap 是为块边界语义连续——我 review 发现聚合边界实际零重叠，已统一注入。"

### W4-7 ai-create 校验
- 改动：priority 夹取 1-5、非法日期置 None（LLM 输出不可信，不再 500）
- 面试话术："LLM 输出永远当不可信输入：结构、类型、范围逐层校验，失败降级而非崩溃。"

### W4-8 附件治理
- 改动：单会话 20 个上限、bytes_size 真实字节数（模型+迁移）、数量/类型/大小三重校验
- 面试话术："字段语义要如实（size=真实字节数）；附件生命周期'只进不出'要设上限。"

## 整体复盘（第 2-4 周）

**时间账**：一次性完成（AI 助手代执行），21 次提交

| 问题 | 回答 |
|---|---|
| 最难的坑？ | ① SQLAlchemy Uuid 列比较不能传 str（两次踩到）；② 测试环境后台任务持库句柄导致 teardown 文件锁；③ 前端 StreamHandlers 加字段后测试类型报错 |
| 最值得讲的故事？ | "授权不对称"（REST 有校验工具没有）、"检索侧越权"（API 鉴权了语义检索没鉴权）、"文档宣称 vs 实现"（沙箱/摘要/确认机制三处如实化） |
| 工程方法沉淀？ | 先写会失败的测试（UUID 坑第一次跑就被测试抓住）；改动签名先 grep 全部调用点；后台任务必须可开关（测试环境关闭） |
| 给面试的新素材？ | 21 个"修复一个问题一次提交"的 commit 历史本身 = 工程习惯的可视化证据；FIX_LOG + SECURITY_FIX_WEEK1 两份复盘 = 可讲 20 分钟的"自审故事" |

---

> 关联文档：[INTERVIEW_AUDIT.md](INTERVIEW_AUDIT.md)（体检报告）· [SECURITY_FIX_WEEK1.md](SECURITY_FIX_WEEK1.md)（第 1 周）· [INTERVIEW_QA.md](INTERVIEW_QA.md)（面试问答）
