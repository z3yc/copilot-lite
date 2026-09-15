# 基金盯盘 + MCP 接入 设计文档（批次 P）

> 用途：批次 P 的落地方案（表结构 / 调度 / MCP 适配 / 播报口径 / 测试门槛）。
> 关联：`OPTIMIZATION_PLAN.md` §9（决策表 §9.1）、§10（批次 Q 多智能体）、同目录《Agent形态选型-单智能体与多智能体.md》。
> 记录时间：2026-09-15。状态：**已排期——F1 → R4、F2–F4 → R7**（见 `develop` 的 `OPTIMIZATION_PLAN.md` §13；本文件属 `private-docs` 分支）。

---

## 1. 背景与目标

| 项 | 内容 |
|---|---|
| 目标 | 让助手从「你问才答」变成「到点自己干活」——**Agent 主动性的第一片** |
| 附带目标 | 把 **MCP** 作为外部能力接入的标准接缝验证一遍（F1 就要验） |
| 形态 | **B 档**：交易日收盘后（默认 21:30）播报一次涨跌 + 收益；按 C 档（阈值告警）留接口 |
| 判据 | 面试演示 + 个人日用（不为企业规模过度设计） |

### 1.1 一句话原则

> **持仓 = 本机私密数据（手动录入）；行情 = 公开数据（走 MCP）；取数用代码，说话才用 LLM。**

### 1.2 做 / 不做

| 做 | 不做（留接缝） |
|---|---|
| 持仓 CRUD、收益计算、收盘后播报、站内通知、IM Webhook | 盘中轮询、阈值告警规则引擎、LLM 复盘报告 |
| MCP 行情接入（stdio）+ 领域工具（对话可查） | 用户级 MCP 配置（SSRF/凭据/隔离三重复杂度） |
| 调度复用 `jobs`（J1）状态机 | 节假日日历（改用 `nav_date` 数据驱动） |

### 1.3 为什么播报时间是 21:30（而非 15:30）

**A 股 15:00 收盘，但场外基金净值晚间才公布**（一般 20:00 起陆续出，QDII 更晚甚至 T+1）。
15:30 播报拿到的仍是昨日净值 —— 这是把「看起来对」和「真的对」区分开的关键一刻。

因此：`FUND_WATCH_TIME` 默认 **21:30**；播报**必须显示净值日期**，不假设是当天。

---

## 2. 架构与分层（遵循 AGENTS §12）

```
[对话路径]  LangGraph 多智能体（批次 Q 主干）
                  │  fund_tool（领域工具，白名单可控）
                  ▼
[定时路径]  scheduler(ticker) → jobs(J1) → fund_watch handler
                  │                        │
                  └────────────┬───────────┘
                               ▼
                   app/funds/service.py（持仓 / 收益 / 播报组装）
                               ▼
                   app/funds/quotes.py（归一化 · 校验 · 缓存）
                               ▼
                   app/mcp/client.py（stdio · initialize · tools/call）
                               ▼
                         MCP Server（基金行情）
```

| 层 | 新增模块 | 职责 |
|---|---|---|
| infra | `app/mcp/client.py`、`app/mcp/registry.py` | 拉起 stdio server、`tools/list`、`tools/call`、进程生命周期与重连 |
| infra(领域适配) | `app/funds/quotes.py` | 归一化为 `FundQuote`、数值校验、`(code, nav_date)` 缓存 |
| service | `app/funds/service.py` | 持仓 CRUD、收益计算、播报组装 |
| core | `app/core/scheduler.py` | ticker：扫 `schedules` → 建 `jobs` |
| tools | `app/tools/fund_tool.py` | 对话路径的领域工具（LLM 只见它，不见 MCP 原始 schema） |
| api | `app/api/routes/funds.py`、`app/api/routes/notifications.py` | 持仓 CRUD、手动触发播报、通知列表 |
| prompts | `app/core/prompts/fund.py` | 工具描述与播报模板（集中管理，AGENTS §18） |

**与批次 Q 的关系**：`fund_tool` 是一个普通工具，天然可纳入 Q2 的工具白名单；**定时路径不经过任何 Agent**（对应 Q0.3）。

---

## 3. 数据模型（4 张表，全部软删除）

| 表 | 关键字段 | 说明 |
|---|---|---|
| `fund_positions` | `id, user_id, code, name, shares, cost_nav, source, note, created_at, updated_at, deleted_at, deleted_by` | 部分唯一索引 `(user_id, code) WHERE deleted_at IS NULL` |
| `fund_quotes` | `id, code, nav_date, nav, change_pct, fetched_at`，唯一 `(code, nav_date)` | **公开行情缓存，无 user_id**（多用户共享） |
| `schedules` | `id, user_id, kind, time_of_day, enabled, last_run_at, next_run_at, created_at, deleted_at, deleted_by` | 用户级「每天几点播报」 |
| `notifications` | `id, user_id, kind, title, body, read_at, channel_status(JSON), created_at, deleted_at, deleted_by` | 站内通知（可追溯、可软删） |

### 3.1 两个硬约束

1. **金额与份额一律 `Numeric(18,4)` + `Decimal`，禁 `float`** —— 浮点误差会滚成「少算 0.01 元」，财务数据不能这么干。
2. **软删除 + 可恢复**（AGENTS §13）：列表/统计默认 `deleted_at IS NULL`；新增表迁移带 `inspect` 守卫，可回滚。

### 3.2 迁移

`add_fund_tables`（新 revision）：四张表 + 索引（`user_id`、`code`、`next_run_at`、`created_at`），部分唯一索引按方言处理（PostgreSQL 原生；SQLite 用 `WHERE deleted_at IS NULL` 的 partial index）。

---

## 4. 调度（`schedules` + ticker）

```
ticker（SCHEDULER_ENABLED=true；测试默认关，AGENTS §8）
  每 SCHEDULER_TICK_SECONDS(60) 秒：
    1) UPDATE schedules
         SET last_run_at = now, next_run_at = <下一次到点>
       WHERE next_run_at <= now AND enabled AND deleted_at IS NULL
       RETURNING id                      ← 原子抢占，多实例安全
    2) 对每个被抢占的 schedule：
         job = jobs.submit_job(kind="fund_watch", user_id, payload={"schedule_id": ...})
         jobs.schedule_job(job.id)       ← 复用 J1：重试 → dead、超时、/jobs 可查
```

| 设计点 | 决定 |
|---|---|
| 下次时间 | 只按 `time_of_day` 推（今天没到→今天；已过→明天），**不查节假日** |
| 幂等 | 原子 UPDATE 保证一次 tick 对同一 schedule 只建一个 job |
| 触发/执行解耦 | ticker 只建作业；失败重试、死信、进度全归 J1 —— 「昨天为什么没播报」只查 `jobs` 一张表 |
| 可开关 | `SCHEDULER_ENABLED` / `SCHEDULER_TICK_SECONDS`，测试环境默认关 |
| 超时 | ticker 单轮有超时；job 级超时用 J1 的 `JOBS_TIMEOUT_SECONDS` |

**留口**：企业化时加容器 cron 调 `POST /internal/tick` 即可，ticker 代码原样复用。

---

## 5. MCP 接入

### 5.1 配置（管理员级，`.env`）

```jsonc
// MCP_SERVERS
[
  {
    "name": "fund-quotes",
    "command": "python",
    "args": ["-m", "some_fund_mcp_server"],
    "env": { "FUND_API_KEY": "***" },   // 高敏：加密存储/日志脱敏
    "tool": "get_fund_nav",             // 显式指定工具名，不猜
    "adapter": "fund_nav_v1"            // 归一化适配器注册表键
  }
]
```

### 5.2 生命周期

| 场景 | 行为 |
|---|---|
| 首次调用 | 懒启动（拉起 stdio 子进程 + `initialize` + 缓存 `tools/list`） |
| 复用 | 进程常驻，不随请求启停 |
| 调用失败 / 子进程退出 | 该次失败返回可读错误；**下次调用自动重连** |
| 总开关关闭 | 领域工具返回「未配置行情源」，**降级不炸** |

### 5.3 外部数据一律视为不可信（AGENTS §6.6）

| 字段 | 校验 | 不通过时 |
|---|---|---|
| `nav` | `Decimal`，`0 < nav < 1e6` | 丢弃该条 + `logger.warning` |
| `change_pct` | 夹取到 `[-100, 100]`；非数值 → `None` | 置 `None` |
| `nav_date` | 可解析为日期 | 丢弃该条 |
| 未返回的代码 | —— | 如实标注「未取到」，**不编造** |

**只取结构化字段**：server 返回的文本内容仅作数据，绝不作为指令；`tool description` 截断至 200 字符并只允许白名单 server。

### 5.4 缓存

按 `(code, nav_date)` 落 `fund_quotes`，`FUND_QUOTE_CACHE_MINUTES`(60) 内的最新记录直接复用 —— 多用户同一天同一支基金只调一次 MCP。

---

## 6. 领域工具（对话路径）

```python
# app/tools/fund_tool.py（示意）
@registry.register
async def fund_query(ctx: ToolContext, codes: list[str] | None = None) -> str:
    """查询本人持仓基金的最新净值与收益；codes 为空则查全部持仓。"""
```

| 约束 | 说明 |
|---|---|
| 归属 | 只读写 `ctx.user_id` 的数据（AGENTS §6.3/§6.4） |
| 写操作 | 增删改持仓走 HITL（`requires_confirmation=True`），与现有 `todo_delete` 同款 |
| 描述 | 明确写出「数据来自第三方、可能延迟」，避免 LLM 把过期净值说成实时 |
| 白名单 | 可被纳入批次 Q 的 `AGENT_TOOLS` 白名单；**不暴露 MCP 原始工具名** |

---

## 7. 播报与推送（`fund_watch` handler，全程无 LLM）

```
1. 取有效持仓（user_id 过滤，deleted_at IS NULL）
2. 拉行情：先查 fund_quotes 缓存 → 缺的调 MCP
3. 算账（Decimal）：
     市值     = Σ shares × nav
     成本     = Σ shares × cost_nav
     收益     = 市值 − 成本
     收益率   = 收益 / 成本          （成本为 0 → 不计算，显示「—」）
     当日盈亏 = Σ shares × (nav − prev_nav)   （无 prev_nav → 「—」）
4. 渲染文案：Jinja2 模板（AGENTS §18 禁字符串拼接）
5. 落 notifications（站内，必做，事务内）
6. 推 Webhook（可选）：失败不回滚站内记录，只写 channel_status
```

### 7.1 模板样例

```jinja
【基金日报 · {{ report_date }}】
{% for p in items %}
· {{ p.name }}（{{ p.code }}）净值 {{ p.nav }}（{{ p.nav_date }}）{{ p.change_pct }}%
{% endfor %}
总市值 {{ total_value }} 元｜收益 {{ total_pnl }} 元（{{ total_pct }}）
{% if stale %}⚠️ 部分基金未取到当日净值，已用最新可得数据并标注日期{% endif %}
```

### 7.2 三个决定

1. **先不接 LLM 写文案** —— 模板渲染省 token、可对账、可精确断言；留 `FUND_REPORT_LLM=false` 接缝。
2. **无新净值照发**，标题如实标「（无新净值，最新为 X 月 X 日）」—— 静默会让人以为系统挂了。
3. **手动触发** `POST /funds/report/run` → 立刻建同款 job：随时验证配置，演示不必等到半夜。

### 7.3 Webhook 安全

| 项 | 措施 |
|---|---|
| URL 来源 | **管理员 env**（非用户输入 → 无 SSRF 面） |
| 密钥 | 飞书 webhook URL **自带 token**：日志只打 host，不打路径与 token |
| 超时 | 5s，失败由 job 层重试 |
| 失败语义 | **站内记录必须已落库**；webhook 失败不回滚（可用性优先，AGENTS §10） |

---

## 8. 错误处理与降级

| 场景 | 行为 |
|---|---|
| MCP 总开关关 / 未配置 | 工具返回可读提示；播报标记「未配置行情源」，不建 job |
| MCP 调用超时/崩溃 | 该次失败 → J1 重试 → 耗尽置 `dead`（`/jobs` 可查、可重试） |
| 脏数据 | 逐条丢弃并告警；其余基金正常播报 |
| 无持仓 | 不建 job（或落一条「未录入持仓」提示，配置决定） |
| 全部未取到净值 | 仍落站内通知，标题如实说明（不静默） |

---

## 9. 安全红线对照（AGENTS §6）

| 红线 | 本设计对应 |
|---|---|
| 用户隔离穿透检索/召回（§6.3） | 持仓、通知、调度全带 `user_id`；工具只碰 `ctx.user_id`；跨用户回归用例 |
| 工具授权 = REST 授权（§6.4） | `fund_tool` 写操作走 HITL + 归属校验，返回「不存在或无权限」 |
| 密钥永不入库/不打印（§6.1/§6.8） | MCP `env` Key、webhook URL 脱敏；新增密钥项进 `.env.example` |
| 外部数据视为不可信（§6.6） | §5.3 校验表 |
| 破坏性操作区分受管/外部（§6.10） | 本批次不引入任何删除外部路径的逻辑 |
| 删除一律软删除（§6.11/§13） | 三张业务表 `deleted_at/deleted_by`，列表默认过滤，可恢复 |

---

## 10. 配置清单（三件套：`config.py` + `deploy/.env.example` + `backend/.env.example`）

| 配置 | 默认 | 说明 |
|---|---|---|
| `MCP_ENABLED` | `false` | MCP 总开关 |
| `MCP_SERVERS` | `[]` | server 配置（JSON） |
| `MCP_CALL_TIMEOUT_SECONDS` | `10` | 单次调用超时 |
| `FUND_QUOTE_CACHE_MINUTES` | `60` | 行情缓存窗口 |
| `SCHEDULER_ENABLED` | `true`（测试关） | ticker 开关 |
| `SCHEDULER_TICK_SECONDS` | `60` | tick 间隔 |
| `FUND_WATCH_TIME` | `21:30` | 每日播报时间 |
| `FUND_REPORT_LLM` | `false` | 是否用 LLM 写文案（留口） |
| `FUND_WEBHOOK_URL` | `""` | IM Webhook（空=不推） |

---

## 11. 测试口径

| 层 | 用例 |
|---|---|
| 调度 | 到点触发 / 未到点不触发 / 开关关闭不跑 / 重复 tick 幂等（不重复建 job） |
| 收益计算 | 正常 / 无持仓 / 缺净值 / `prev_nav` 缺失 / 成本为 0（除零）/ `Decimal` 精度 |
| MCP 适配 | **Fake client 不联网**；脏数据（负净值、日期非法、超范围）逐条丢弃并告警 |
| 播报 | 站内必落库；webhook 失败**不影响**站内；脱敏断言（日志无 token） |
| 安全 | 跨用户隔离回归（看不到他人持仓/通知/调度）；软删除后可恢复且列表已过滤 |
| 前端 | 持仓录入表单、通知中心（列表/已读/删除）组件测试 |
| 全量 | 后端 `pytest` ≥80% + `ruff`；前端 `npm test` + `build` |

---

## 12. 分期与验收

| 期 | 交付 | 验收 |
|---|---|---|
| **F1** | MCP client + 适配层 + `fund_tool`（对话查净值） | 用一个真实 server 跑通「问基金净值」；脏数据用例全绿 |
| **F2** | 持仓表 + CRUD + 前端录入 + 收益计算 | 跨用户隔离回归；收益计算边界用例全绿 |
| **F3** | `schedules` + ticker + `fund_watch` + 站内通知 | 幂等用例全绿；手动触发可在界面上看到结果 |
| **F4** | Webhook + 通知中心前端 | webhook 失败不影响站内；日志脱敏断言通过 |

**F1 是「最便宜的失败点」**：若选到的 MCP server 不可用/字段对不上，只改适配器或换 server，不返工后续三期。

---

## 13. 风险与留口

| 风险 | 对策 |
|---|---|
| MCP server 停更 / 字段变更 | 适配器注册表解耦；领域工具 schema 稳定；换 server 只改适配层 |
| 净值公布时间漂移（QDII 更晚） | 数据驱动：`nav_date` 未前进即标「无新净值」；不假设当天 |
| 多实例重复播报 | DB 原子抢占（`UPDATE ... RETURNING`） |
| 用户以为「实时」（实际延迟） | 播报与工具描述均标注净值日期与数据来源 |
| 将来要「盘中告警」（C 档） | 接缝已留：`schedules` 支持多 kind；规则引擎作为新 handler 接入 |

---

## 14. 与批次 Q（多智能体）的接口

| 批次 Q 决策 | 本设计的配合 |
|---|---|
| Q0.3 确定性任务不进 Agent | `fund_watch` 走 `jobs`，**不经 LLM** |
| Q0.6 `tools_agent` 改显式白名单 | `fund_tool` 按需挂白名单，不会被全量注入 |
| Q0.7 trajectory 全量落库 | 对话路径的 `fund_tool` 调用进 trajectory；定时路径只在 `jobs` 留痕 |
| Q0.8 双引擎对照评测 | `fund_tool` 两引擎共享，无需重复实现 |
