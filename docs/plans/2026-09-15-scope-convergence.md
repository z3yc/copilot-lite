# R0 计划收敛 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 把三份计划文档从"77 条沉积待办"收敛为 R0–R7 交付路线 + 带重启条件的冻结清单，并新增作为需求准入过滤器的 3 分钟 Demo 剧本。

**Architecture:** 纯文档改造，**不写任何代码**。`develop` 为计划文档唯一权威版本，改动走 `docs/plan-scope-convergence` 分支 → 经批准合并 `develop`。设计依据：`docs/plans/2026-09-15-scope-convergence-design.md`（private-docs，已提交 `f5feb97`）。

**Tech Stack:** Markdown / git（`develop` + `private-docs` worktree）/ grep 校验。

**关键约束：**
- 本计划**只改文档，不改代码**；任何顺手改代码的行为都超出本批（AGENTS §2「一次只解决一个问题」）。
- 不新增功能开关、不新增配置（无代码改动）。
- 合并 / 推送需人工批准（AGENTS §11）——Task 9、Task 10 为此标注。

---

## 前置事实（执行者需知）

- 仓库：`C:/Users/asus/Documents/copilot-lite`（主 worktree，当前在 `develop`）
- 私有文档 worktree：`C:/Users/asus/Documents/copilot-lite-private`（`private-docs` 分支）
- `docs/` 被 `.gitignore` 忽略（"本地文档（仅本地保留，不推送远程）"），但 `docs/` 下已有文件**是已跟踪状态**；`private-docs` 上新增/修改 `docs/` 文件必须 `git add -f`。
- `OPTIMIZATION_PLAN.md` / `PLAN.md` 同时存在于 `develop` 与 `private-docs` 且**已分叉**（md5 `59a9ed4…` vs `6b1257a…`）——本批要消除这个双份。
- 当前未勾选项基线（执行 Task 8 前先记录）：

```bash
cd C:/Users/asus/Documents/copilot-lite
grep -c "^- \[ \]" OPTIMIZATION_PLAN.md ADMIN_PLAN.md PLAN.md
```

预期初始输出（2026-09-15 实测）：

```
OPTIMIZATION_PLAN.md:53
ADMIN_PLAN.md:17
PLAN.md:7
```

即 77 条（ADMIN_PLAN 的 17 条 = 功能 11 + §10 验收门槛 6；PLAN 的 7 条 = P5 功能 6 + 验收红线 1）。

---

### Task 1: 创建分支

**Files:**
- 无文件改动（仅 git 操作）

**Step 1: 确认工作区干净**

Run:
```bash
cd C:/Users/asus/Documents/copilot-lite
git status --short
```
Expected: 只有 `?? .workbuddy/`（本地未跟踪目录，忽略即可）；**不应有已修改的计划文档**。若有，先解决再继续。

**Step 2: 确认基线提交**

Run:
```bash
git log --oneline -1
```
Expected: `e406d95 chore(config): .gitignore 忽略 面试准备/——防 git add -A 把私有资料带进 develop/main`

**Step 3: 从 develop 切出分支**

Run:
```bash
git switch -c docs/plan-scope-convergence
git branch --show-current
```
Expected: `docs/plan-scope-convergence`

> 命名说明：AGENTS §11 只给了 `feat/` `fix/` 两种前缀；本批为纯文档，用 `docs/` 前缀（若维护者要求严格遵循，可改用 `chore/plan-scope-convergence`）。

---

### Task 2: 新增 `DEMO_SCRIPT.md`

**Files:**
- Create: `DEMO_SCRIPT.md`（`develop` 根目录）

**Step 1: 写入完整内容**

写入以下内容到 `DEMO_SCRIPT.md`（内容已定稿，直接落地）：

````markdown
# 3 分钟 Demo 剧本（Copilot-Lite）

> 用途：① 演示排练脚本；② **需求准入过滤器**。
> **准入规则**：任何新需求必须回答「进哪个镜头」或「能讲出什么数据」。两问答不出其一 → 进 `OPTIMIZATION_PLAN.md` §11 冻结清单，不排期。
> 更新时机：新增/删除镜头必须同步更新本文件与 `OPTIMIZATION_PLAN.md` §13 路线图。

---

## 0. 演示前置

| 项 | 要求 |
|---|---|
| 环境 | 云端 URL（HTTPS），演示账号已登录 |
| 预置数据 | Wiki 空间 1 个（≥ 20 页，含双链）、上传文档 3 篇、记忆 1 条、待办 1 条、持仓 1 支（R7 后） |
| 兜底 | 每个镜头预录 15s 录屏片段；网络/服务异常时直接放片段并口述 |
| 计时 | 6 镜头合计 ≤ 3 分钟（镜头 1/2/3 各 35s，镜头 4/5/6 各 25s） |

---

## 1. 镜头表

### 镜头 1（0:00–0:35）知识库问答：带引用、引用可点

- **讲什么**：混合检索（BM25 + 向量 + RRF 融合）→ Rerank 精排 → 引用溯源；Wiki 页面走双链邻居扩展。
- **展示什么**：在已同步的 Wiki 空间提问（如「XX 方法论在我笔记里的哪几页讲过」），流式回答 + `[1][2]` 引用；点击引用跳转到具体 Wiki 页面（或文档页码）。
- **预期现象**：回答下方引用条目显示「Wiki / 空间名 / 页面名」与「文档 / 文件名 / 第 N 页」两种来源类型；点击可跳转。
- **失败兜底**：若检索为空 → 讲"空结果不做幻觉生成，如实告知没找到"，并指向质量看板的空结果率指标（镜头 5）。

### 镜头 2（0:35–1:10）回答轨迹：多智能体不是黑盒

- **讲什么**：supervisor 单次路由 + 关键词兜底；路由失败回退单 agent 路径（可用性优先）。
- **展示什么**：展开「本次回答轨迹」：路由判定 → 选中哪个子 Agent（知识库 / 工具 / 通用）→ 调用了哪些工具 → 各步耗时。
- **预期现象**：轨迹面板可见路由决策、工具调用序列与耗时；同一问题换措辞后路由结果稳定。
- **失败兜底**：轨迹缺失时讲"没有 trajectory 的多智能体不可调试、不可评测"——这正是先做可观测再扩子 Agent 的理由。

### 镜头 3（1:10–1:45）实时数据走 MCP，不走 RAG

- **讲什么**：**精确数字不能靠语义检索**（净值/日期是精确值，进 RAG = 幻觉源）→ 走工具调用；MCP server 被 `fund_tool` 包一层，LLM 不直接见 server。
- **展示什么**：提问「我持仓的 XX 基金今天净值多少」→ 走 MCP → 返回净值 + 涨跌幅 + 净值日期。
- **预期现象**：回答含精确数字与日期；工具调用在镜头的轨迹面板中可见。
- **失败兜底**：MCP 超时 → 讲超时与脏数据防护（数值夹取、日期非法丢弃），展示降级文案。

### 镜头 4（1:45–2:10）危险操作人工确认（HITL）

- **讲什么**：工具层授权 = REST 层授权；副作用操作必须确认。
- **展示什么**：「记一下明天下午三点开会」→ 待办创建前弹出确认 → 确认后落库 → 待办列表可见。
- **预期现象**：确认条出现、确认后待办存在、拒绝则不落库。
- **失败兜底**：直接展示待办列表与 HITL 组件截图。

### 镜头 5（2:10–2:35）质量看板：把取舍变成数据

- **讲什么**：检索质量有 golden set 与阈值门槛（Recall@K / MRR / 空结果率 / 引用支撑率）；每次评测记录**配置指纹**（engine / model / prompt_version / embedding / top_k / rerank / wiki_expand），历史数字可比；双引擎（LangGraph vs 手写）对照 token / 延迟 / 准确率。
- **展示什么**：看板趋势折线 + 某次 run 的指标 + 两次 run 的配置指纹对比 + 失败样本下钻（哪条 query 没召回）。
- **预期现象**：指标带配置指纹；失败样本可定位到具体 query。
- **失败兜底**：看板不可用时展示 CI 历史上评测的阈值门槛通过记录与告警截图。

### 镜头 6（2:35–3:00）记忆与可溯源删除

- **讲什么**：长期记忆（提取 / 去重 / 召回 / 可视化管理）；**删除一律软删除**（`deleted_at`/`deleted_by` + 审计），列表与检索默认过滤，回收站可恢复。
- **展示什么**：我的记忆页（查看/编辑/删除）→ 回收站恢复一条已删对象 → 检索不再召回已删内容。
- **预期现象**：回收站可见被删对象并可恢复；恢复后检索能召回。
- **失败兜底**：展示审计记录（request_id / user_id / 资源 / 时间 / 结果）。

---

## 2. 快速自查（演示前 60 秒）

- [ ] 云端 URL 可达、健康检查 `/health/ready` 为 ok
- [ ] 预置数据齐全（Wiki 空间 / 文档 / 记忆 / 待办 / 持仓）
- [ ] 6 段录屏兜底片段可播放
- [ ] 每个镜头都能说出「问题 → 取舍 → 验证」三句话
````

**Step 2: 校对准入规则存在**

Run:
```bash
grep -n "准入规则" DEMO_SCRIPT.md
```
Expected: 输出包含 `准入规则`：任何新需求必须回答…（1 行）

**Step 3: 提交**

```bash
git add DEMO_SCRIPT.md
git commit -m "docs(plan): 新增 3 分钟 Demo 剧本——兼作需求准入过滤器

- 6 镜头剧本（引用/轨迹/MCP/HITL/质量看板/软删除）与失败兜底
- 准入规则：新需求必须能回答进哪个镜头或讲出什么数据，否则进冻结清单
- 目的：防待办再次无序沉积（本轮沉积的直接成因之一）"
```

---

### Task 3: `OPTIMIZATION_PLAN.md` —— 批次表状态改冻结

**Files:**
- Modify: `OPTIMIZATION_PLAN.md`（§1 进度总览表，约 12–31 行）

**Step 1: 替换进度总览表**

将 §1 「进度总览」表整体替换为下表（保留 `A`–`H`、`L` 的 ✅ 状态，其余改 ❄️ 并指向冻结清单）：

```markdown
| 批次 | 主题 | 状态 |
|---|---|---|
| A | CLI 完整可用（双入口闭环） | ✅ 完成 |
| B | 契约与可观测性（对齐 AGENTS.md） | ✅ B1/B2/B4 完成（B3/B5 ❄️ 冻结） |
| C | 性能与正确性 | ✅ C1/C2/C5 完成（C3/C4 ❄️ 冻结） |
| D | RAG / Agent 能力深度 | ✅ D1/D2/D4 完成（D5 ❄️ 冻结） |
| E | 产品体验（前端 UX） | ✅ E1–E4 完成（E5 ❄️ 冻结） |
| F | 模型配置页面化 | ✅ 完成 |
| G | 本地 Wiki 知识库（Obsidian 接入） | ✅ M1/M1.5/M2 + P1–P3 + M3 完成（M4 ❄️ 冻结） |
| H | 连接器化收口（Obsidian → connectors） | ✅ 完成 |
| L | 软删除与审计（强制红线） | ✅ 完成（后端+回收站前端） |
| I | 企业化：租户与权限 | ❄️ 冻结（§11） |
| J | 可靠性与治理 | 🟡 J1/J3 在范围内（J3 → R5）；J2/J4/J6/J7 ❄️ 冻结 |
| K | 连接器生态与直连能力 | ❄️ 冻结（§11） |
| M | 知识来源范围（RAG / Wiki 检索分流） | 🟡 M1 完成、M5 → R3；M2/M3/M4/M6 ❄️ 冻结 |
| N | 管理后台与质量看板 | 🟡 N0/N1 完成、P2 → R6；N2.7/N2.9/N3 ❄️ 冻结 |
| P | 基金盯盘 + MCP 接入 | 🟡 F1 → R4、F2–F4 → R7（**已排期**） |
| Q | Agent 形态与可观测 | 🟡 Q1 → R2、Q5 → R5；Q2/Q3/Q4 ❄️ 冻结 |
| Z | 暂缓项（B3/B5/C3/C4/D5/E5/L7） | ❄️ 冻结（§11） |
```

> 注意：原表中 `J` 的 `J5 并入 L`、`D3 并入 G-M2` 等已完成合并关系在 §6/§8 章节内保留，不在总览表重复。

**Step 2: 在表下方补一行指向**

紧接表格后插入：

```markdown
> ❄️ = 已冻结（不改代码、不排期）。**冻结项一律带重启条件**，见 §11 冻结清单与重启条件。
> 当前交付路线（R0–R7）见 §13。
```

**Step 3: 校验**

```bash
grep -n "❄️" OPTIMIZATION_PLAN.md | head -20
```
Expected: ≥ 10 行含 ❄️，且含 `§11`、`§13` 指向行。

**Step 4: 提交**

```bash
git add OPTIMIZATION_PLAN.md
git commit -m "docs(plan): 批次总览改冻结态——区分在范围与已冻结

- 企业化/伪替换/无场景批次（I/J2/J4/J6/J7/K/M2-4/M6/N2.7/2.9/N3/Q2-4/Z）统一标 ❄️ 并指向冻结清单
- 在范围批次显式标注去向（J3→R5、M5→R3、P→R4/R7、Q1→R2、Q5→R5、N-P2→R6）
- 消除 ADMIN_PLAN §7「只留缝不实现」与 OPTIMIZATION_PLAN 要求「实现 I1-I6」的自相矛盾"
```

---

### Task 4: `OPTIMIZATION_PLAN.md` —— 新增 §11 冻结清单与重启条件

**Files:**
- Modify: `OPTIMIZATION_PLAN.md`（在现有 `## 11. 暂缓批次（按需）` 处**整体替换**该章节）

**Step 1: 用冻结清单替换原「暂缓批次」章节**

原章节（约 265–274 行，`## 11. 暂缓批次（按需）` 及其下 7 个 `- [ ]` 条目）整体替换为：

````markdown
## 11. ❄️ 冻结清单与重启条件

> 冻结 ≠ 删除。**每条必须带重启条件**，否则半年后会被重新当成待办挖出来——这正是本轮范围沉积的成因（见 `docs/plans/2026-09-15-scope-convergence-design.md` §1）。
> 冻结项一律**不改代码、不排期、不承接部分实现**。
> 重新激活流程：满足重启条件 → 先写设计文档 → 纳入路线图 → 再开工。

| 项 | 冻结理由 | 重启条件 |
|---|---|---|
| **I1–I6** 多租户 / workspace / ACL | 单用户不可演示、不可验证；半成品 ACL 是真实泄露面 | 真实出现第二个用户，或面试岗位明确要求讲多租户 |
| **J2** OTel + Grafana + 告警 | `request_id` + `/health/ready` + 审计已够个人量级 | 出现真实排障需求（线上事故查不动），或岗位明确要求可观测体系 |
| **J4** 审计统一表 | L3 + `/admin/audit` 已覆盖敏感操作 | 企业合规要求 |
| **J6** Secret Manager | 单机 `.env` + Fernet 加密已足够 | 企业落地 / 合规要求 |
| **J7 / C3** Redis、任务队列、S3、Qdrant 集群 | `jobs` 表 + 单体已够；"基础设施可替换"是架构原则，不是待办 | 出现可量化瓶颈（队列深度/延迟有数据支撑） |
| **K1** 连接器管理界面 | K2 前置，无多来源可管 | K2 解冻 |
| **K2** 新连接器（S3/Git/通用目录/SharePoint/Confluence） | **无真实数据源 = 无内容可检索** | 出现真实数据源（如实习/工作环境有 Confluence） |
| **K3** 直读工具（`vault_list`/`grep`/`read`） | Obsidian 已导入索引；Demo 的工具调用示例由 `fund_tool` 承担 | 自用时真实出现"要 grep 未索引内容"的需求 |
| **K4** Obsidian 写回 | 读路径未跑满，写回增加对外部系统的副作用面 | 自用中真实出现回写需求，且评估过副作用风险 |
| **K5** 增量游标 + ACL 映射 | 依赖 I 与 K2 | I + K2 解冻 |
| **M2/M3/M4** `kb_search` scope 分流 | 未进任何镜头；当前未出现"查错来源"的真实痛点 | 自用时反复出现检索范围混淆 |
| **M6** UI 知识范围选择器 | 依赖 M2 | M2 解冻 |
| **N2.7** Wiki 图谱对账 | 不在镜头 5；确定性指标可后补 | R6 出数顺利且需要 Wiki 质量故事 |
| **N2.9** A/B lift（rerank/query-rewrite/双链） | 单用户样本量不足，结论不可信 | 有足够评测样本量（≥ 200 query） |
| **N3.1 / N3.2** OTel+Grafana / 多租户 | 同 J2 / I | 同 J2 / I |
| **Q2** 工具白名单与渐进披露 | 当前工具数少，全量注入未爆 | 工具数 > 15，或 prompt 明显膨胀 |
| **Q3** Task 实体（跨轮任务状态机） | 无跨轮跟进场景；成本中型 | 自用中真实出现"跨轮跟进/可恢复任务"需求 |
| **Q4** supervisor 深化 | 现有单次路由 + 关键词兜底已够 | 路由判错成为高频问题（有 trajectory 数据支撑） |
| **B3** 分层收口（service 层抽离） | 纯重构，无新故事，风险高 | 需要大规模协作或模块数翻倍时 |
| **B5** OpenAPI → TS 类型自动生成 | 手写类型量级小，收益低 | 接口数翻倍 |
| **C4** 语义缓存（答案级） | 个人量级无命中率，且有缓存错答案的正确性风险 | 请求量支撑命中率（有数据） |
| **D5** BM25 → PostgreSQL FTS | 现有 BM25 在百篇量级够用，纯替换无收益 | 现有实现被证明是瓶颈（检索延迟数据） |
| **E5** 用户反馈闭环 | 单用户无标注价值 | 多用户 |
| **G-M4** 轻量本体（类型化链接） | 图谱可视化已够，本体属学术级玩具 | 真实出现关系推理需求 |
| **L7** 用户注销 / 账号软删除 | 单用户无注销场景（`ADMIN_PLAN` N0.6/N1.3 已覆盖管理员侧软删） | 多用户上线 |

**接缝不删**（`ADMIN_PLAN` §7「只留缝」是正确的，继续保留）：
`tenant_id`/`workspace_id` nullable 列 · `require_admin → RBAC` 替换点 · `audit_logs` append-only · `config_fingerprint` 维度。
````

**Step 2: 校验章节与条目数**

```bash
grep -n "^## 11" OPTIMIZATION_PLAN.md
grep -c "^| \*\*" OPTIMIZATION_PLAN.md
```
Expected: 第一行为 `## 11. ❄️ 冻结清单与重启条件`；第二个数字 ≥ 24（冻结条目数）。

**Step 3: 确认旧章节的复选框已被移除**

```bash
grep -n "暂缓批次" OPTIMIZATION_PLAN.md
```
Expected: 无输出（该章节标题已不存在）。

**Step 4: 提交**

```bash
git add OPTIMIZATION_PLAN.md
git commit -m "docs(plan): 暂缓批次升级为冻结清单——每条带重启条件

- 原'暂缓批次'只有 7 条且无理由，其余冻结项散落各处，导致半年后被重新当待办
- 冻结清单覆盖 24 组条目：I/J2-7/K/N2.7-2.9/N3/Q2-4/B3-B5/C4/D5/E5/G-M4/L7
- 明确接缝不删（tenant/workspace nullable、RBAC 替换点、audit append-only、配置指纹）"
```

---

### Task 5: `OPTIMIZATION_PLAN.md` —— §12 清理与 §13 路线图重写

**Files:**
- Modify: `OPTIMIZATION_PLAN.md`（`## 12. 待合并与推送` 尾部、`## 13. 总路线图`、`## 14. 验收总门槛`）

**Step 1: 清理 §12 重复条目**

删除重复的推送行，即把：

```markdown
- [ ] **推送**：GitHub + Gitee 的 `develop` / `main`（J1 合并后新增待推）。
- [ ] **推送**：GitHub + Gitee 的 `develop` / `main`。
```

替换为单条（保留 private-docs 那条不变）：

```markdown
- [ ] **推送**：GitHub + Gitee 的 `develop` / `main`（J1 合并后新增待推）。
```

**Step 2: 重写 §13 总路线图**

`## 13. 总路线图（建议顺序）` 整节替换为：

```markdown
## 13. 总路线图（R0–R7）

> 定稿依据：`docs/plans/2026-09-15-scope-convergence-design.md`（目标 C：面试优先 + 兼顾自用）。
> 准入规则：新需求必须能回答"进哪个镜头"（见 `DEMO_SCRIPT.md`）或"讲出什么数据"，否则进 §11 冻结清单。

| 批次 | 事项 | 预估 | 验收位置 |
|---|---|---|---|
| **R0** | 计划收敛（本文件改造 + `DEMO_SCRIPT.md` + 清理双份分叉） | 0.5 天 | 本批 |
| **R1** | **P5 云上可演示**：服务器 + Compose/Nginx/HTTPS 实测 + README 截图 + 面试问答 + Demo 排练 | ~1 周 | 镜头 1–6 可跑通 |
| **R2** | **Q1 trajectory**：全量落 `Message.extra` + 前端可见（`AGENT_TRACE_ENABLED`） | ~3 天 | 镜头 2 |
| **R3** | **M5 引用来源标注**：区分 `Wiki/空间/页面` 与 `文档/页码` | ~2 天 | 镜头 1 |
| **R4** | **P-F1 MCP 地基**：`app/mcp/` + `funds/quotes.py` + `fund_tool` | ~1 周 | 镜头 3 |
| **R5** | **评测闭环**：J3 进 Jenkins 门槛 + Q5 双引擎对照报告（共用 `rag_eval`） | ~3 天 | 镜头 5 |
| **R6** | **N2 质量看板**：N2.1–N2.6 + N2.8 | ~1.5 周 | 镜头 5 |
| **R7** | **基金自用闭环（必做）**：P-F2 持仓 → P-F3 调度 → P-F4 通知 | ~1.5 周 | 自用价值 |

- [ ] **R1** 云上可演示（P5）：服务器选购与环境初始化、Compose+Nginx+HTTPS 实测、README 截图、面试问答 20 问、Demo 排练
- [ ] **R2** Q1 trajectory 落库与前端展示
- [ ] **R3** M5 引用来源标注
- [ ] **R4** P-F1 MCP 地基与 `fund_tool`
- [ ] **R5** J3 评测门槛进 Jenkins + Q5 双引擎对照报告
- [ ] **R6** N2.1–N2.6、N2.8 质量看板
- [ ] **R7** P-F2 持仓 → P-F3 调度 → P-F4 通知（必做）

> **排序逻辑**：R1 先上线（把交付悬崖前置消化，之后每次改动即刻可演示）→ R2/R3 便宜且立刻改善 Demo → R4 新子系统放在有真环境可验之后 → R5/R6 产数据资产 → R7 兑现自用。
> **实施计划粒度**：R1–R7 各自开工时另写计划（`docs/plans/YYYY-MM-DD-<批次>-<主题>.md`），**不超前写**——R4 需先定 MCP server 选型，R6 依赖 R5 产出的评测执行器。
> **每批门槛**：见 §14。
```

**Step 3: 校验未完成项已归属**

```bash
grep -n "^- \[ \]" OPTIMIZATION_PLAN.md
```
Expected: 仅剩 R1–R7 的 7 条 + §12 的推送条目（3 条）+ §14 验收门槛条目；**不应再出现 I/K/M2-M6/N2.7/Q2-Q4/Z 批次的功能条目**。

**Step 4: 提交**

```bash
git add OPTIMIZATION_PLAN.md
git commit -m "docs(plan): 路线图重写为 R0-R7 并清理重复记录

- §13 由 11 项建议顺序改为 R0-R7 交付路线，含预估与验收镜头对应
- 明确 R1-R7 实施计划不超前写（R4 需先定 MCP server 选型，R6 依赖 R5 执行器）
- §12 删除重复的推送条目（陈旧记录）"
```

---

### Task 6: `PLAN.md` —— 加 P6、细化 P5、同步基线

**Files:**
- Modify: `PLAN.md`（§2 进度总览约 20–29 行；§4 `🔵 P5 · 部署 + 面试` 约 118–125 行）

**Step 2 之前先做 Step 1。**

**Step 1: 进度总览加 P6 并同步基线**

在 §2 进度总览代码块中，`P5 部署面试` 行之后追加一行：

```
P6 收敛交付 ░░░░░░░░░░   0%（R0 计划收敛进行中，见 OPTIMIZATION_PLAN §13）
```

并把 §2 末尾的「**Git 现状**」段整体替换为：

```markdown
**Git 现状**：`develop` 基线后端 **337 用例 / 覆盖率 82.53%**、前端 **92 用例**、CLI **15 用例**（@ `5b5ce2f` J1 合并后）；CI/CD 由本机 Jenkins 承载（见 `docs/CICD_PLAN.md`）。
**范围基准**：本轮已收敛为 **R0–R7**（`OPTIMIZATION_PLAN.md` §13），冻结项见该文件 §11；需求准入规则见 `DEMO_SCRIPT.md`。
```

**Step 2: 细化 P5 为 R1 子项**

将 `### 🔵 P5 · 部署 + 面试（约 2 周）` 章节下的复选框替换为：

```markdown
- [ ] 云服务器选购（2C4G 轻量，¥50/月内）与环境初始化
- [ ] 云端部署（Docker Compose + Nginx + HTTPS）实测通过，`/health/ready` 为 ok
- [ ] README 完善（架构图 + 演示截图 + 配置说明）
- [ ] 面试问答文档（deep-dive 20 问：RAG/记忆/工具/架构取舍）
- [ ] 演示脚本排练（`DEMO_SCRIPT.md` 6 镜头，3 分钟内一次过）
- [ ] **M5 验收**：云上可演示，故事线完整
```

**Step 3: 在 P5 章节后追加 P6 章节**

```markdown
### ⚪ P6 · 范围收敛与交付（进行中）

- [ ] **R0** 计划收敛：三份计划改造 + 冻结清单（带重启条件）+ `DEMO_SCRIPT.md`
- [ ] **R2** Q1 trajectory 可观测
- [ ] **R3** M5 引用来源标注
- [ ] **R4** P-F1 MCP 地基 + `fund_tool`
- [ ] **R5** J3 评测门槛进 Jenkins + Q5 双引擎对照报告
- [ ] **R6** N2 质量看板（N2.1–N2.6 + N2.8）
- [ ] **R7** 基金自用闭环（P-F2/F3/F4，必做）

> 明细与预估见 `OPTIMIZATION_PLAN.md` §13；冻结与重启条件见同文件 §11。
```

**Step 4: 校验**

```bash
grep -n "P6 收敛交付\|R0-R7\|R0–R7" PLAN.md
grep -c "^- \[ \]" PLAN.md
```
Expected: 第一组输出含 `P6 收敛交付` 与 `R0-R7`（或 `R0–R7`）；本文件未完成项由 7 升至 **14**（P5 功能 6 + P6 共 7 + 验收红线 1）。

**Step 5: 提交**

```bash
git add PLAN.md
git commit -m "docs(plan): 新增 P6 收敛交付并同步基线——消除计划与实际的偏差

- 进度总览与 OPTIMIZATION_PLAN 基线对齐（337 用例/82.53%、前端 92）
- P5 细化为可验收子项（云端 ready、README 截图、面试问答、Demo 排练）
- 新增 P6 章节承载 R0-R7，避免交付项散落在优化计划里"
```

---

### Task 7: `ADMIN_PLAN.md` —— 状态更新与 N2 收敛

**Files:**
- Modify: `ADMIN_PLAN.md`（第 6 行「状态」行；§9 `### P2 · 质量看板（卖点）`；`### P3 · 可观测与多租户`）

**Step 1: 更新状态行**

将第 6 行：

```markdown
> 状态：**已设计，待排期**。
```

替换为：

```markdown
> 状态：**N0/N1 已完成；N2 已排入 R6（见 `OPTIMIZATION_PLAN.md` §13）**；N2.7/N2.9/N3 已冻结（同文件 §11）。
```

**Step 2: P2 章节收敛**

将 `### P2 · 质量看板（卖点）` 下 N2.1–N2.9 的复选框替换为：

```markdown
- [ ] **N2.1** golden 数据集管理/版本（表 + 上传/复制）。
- [ ] **N2.2** 评测执行器：复用 `rag_eval.py` / `rag_eval_ragas.py` 逻辑，写 `eval_runs`/`eval_items` + 配置指纹。
- [ ] **N2.3** `GET /admin/eval/runs/{id}/items` 明细 + 失败下钻。
- [ ] **N2.4** 指标：Recall/MRR/nDCG/Hit/空结果率 + Faithfulness/Relevancy/**引用支撑率**/**拒答率**。
- [ ] **N2.5** **per-source 切片**（wiki/docs）。
- [ ] **N2.6** 趋势 + **baseline 对比**（配置指纹 + 数据集版本）。
- [ ] **N2.8** 前端质量看板（图表库：`recharts`）。
- ❄️ **N2.7** Wiki 图谱对账、**N2.9** A/B 开关 lift → 已移入 `OPTIMIZATION_PLAN.md` §11 冻结清单。
```

**Step 3: P3 章节标记冻结**

将 `### P3 · 可观测与多租户` 下两条复选框替换为：

```markdown
- ❄️ **N3.1** OTel + Grafana + 告警（J2）、**N3.2** 多租户/workspace/角色（批次 I）→ 已移入 `OPTIMIZATION_PLAN.md` §11 冻结清单。
```

**Step 4: 校验**

```bash
grep -n "已排入 R6" ADMIN_PLAN.md
grep -c "^- \[ \]" ADMIN_PLAN.md
```
Expected: 输出含 `已排入 R6`；未完成项由 17 降至 **13**（其中功能项由 11 降至 7：N2.1–N2.6、N2.8）。

**Step 5: 提交**

```bash
git add ADMIN_PLAN.md
git commit -m "docs(plan): N2 收敛为最小可交付并标注 N3 冻结

- 状态由'待排期'改为'N2 已排入 R6'，消除计划与实际进度的偏差
- N2.7/N2.9/N3 移入冻结清单，未完成项 17 → 13（功能项 11 → 7）
- 图表库沿用已定选型 recharts（不引重型依赖）"
```

---

### Task 8: 未勾选项归属核对（验证任务）

**Files:**
- 无文件改动（产出核对结论，附在 Task 9 的提交说明或 PR 描述中）

**Step 1: 导出全部未勾选项**

Run:
```bash
cd C:/Users/asus/Documents/copilot-lite
grep -n "^- \[ \]" OPTIMIZATION_PLAN.md ADMIN_PLAN.md PLAN.md > /tmp/unchecked.txt
wc -l /tmp/unchecked.txt
```
Expected: 总数由 **77** 降至 **≤ 45**（其中功能项 ≤ 20）。

**Step 2: 逐条标注归属**

对 `/tmp/unchecked.txt` 每一行标注归属，取值只能是：`R1`–`R7` / `§11 冻结` / `§12 推送` / `§14 验收门槛`。

**Step 3: 判定**

Expected: **0 条"无归属"**。若存在无归属项，回到 Task 3–7 修正文档（不改代码）。

**Step 4: 交叉引用核对**

```bash
grep -n "scope-convergence-design\|2026-09-15-fund-watch-mcp-design\|DEMO_SCRIPT" OPTIMIZATION_PLAN.md PLAN.md ADMIN_PLAN.md
```
Expected: 每个引用路径真实存在（`DEMO_SCRIPT.md` 在 `develop` 根目录；两个设计文档在 `private-docs` 的 `docs/plans/`）。逐一 `ls` 验证，**不留下悬空引用**。

---

### Task 9: 自查、提交与合并申请（**需人工批准**）

**Step 1: 全量自查**

```bash
cd C:/Users/asus/Documents/copilot-lite
git log --oneline develop..HEAD
git diff --stat develop...HEAD
```
Expected: 5–6 个 `docs(plan)` 提交；**改动仅限 4 个 .md 文件**（`DEMO_SCRIPT.md` 新增 + 三份计划文档），无任何 `.py` / `.ts` / 配置改动。

**Step 2: 确认无代码/私有资料混入**

```bash
git diff --name-only develop...HEAD
```
Expected: 仅 `DEMO_SCRIPT.md`、`PLAN.md`、`OPTIMIZATION_PLAN.md`、`ADMIN_PLAN.md`；**不得出现 `面试准备/`、`docs/`、`.env*`、`AGENTS.md`**（AGENTS §6.1 / §11）。

**Step 3: 按 §7 规范确认无配置与迁移影响**

Run:
```bash
git diff develop...HEAD --stat | grep -E "config.py|\.env\.example|alembic" || echo "无代码/配置/迁移改动 ✅"
```
Expected: `无代码/配置/迁移改动 ✅`

**Step 4: 申请合并（需批准，AGENTS §11）**

向维护者（用户）出示 Step 1–3 输出，申请：

```bash
# 经批准后执行
git switch develop
git merge --no-ff docs/plan-scope-convergence -m "merge: 计划收敛——冻结清单带重启条件 + R0-R7 路线 + Demo 剧本准入过滤器"
```

**Step 5: 提交后不推送**

推送需再次批准（AGENTS §11）。**不要**在此步 `git push`。

---

### Task 10: `private-docs` 分支整理（**需人工批准**）

**Files:**
- Delete: `PLAN.md`、`OPTIMIZATION_PLAN.md`（`private-docs` 分支副本）
- Modify: `docs/plans/2026-09-15-fund-watch-mcp-design.md`（状态行）

**Step 1: 确认分叉现状（留存证据）**

```bash
cd C:/Users/asus/Documents/copilot-lite
git show develop:OPTIMIZATION_PLAN.md | md5sum
git show private-docs:OPTIMIZATION_PLAN.md | md5sum
```
Expected: 两个 md5 **不同**（当前为 `59a9ed4…` vs `6b1257a…`），证明删副本的必要性。

**Step 2: 删除重复副本并更新批次 P 文档状态**

```bash
cd C:/Users/asus/Documents/copilot-lite-private
git rm PLAN.md OPTIMIZATION_PLAN.md
# 修改 docs/plans/2026-09-15-fund-watch-mcp-design.md 状态行：
#   「状态：**设计已定，待排期实现**。」→「状态：**已排期——F1 → R4、F2–F4 → R7**（见 `OPTIMIZATION_PLAN.md` §13）。」
git add -f docs/plans/2026-09-15-fund-watch-mcp-design.md
git commit -m "docs(plan): 计划文档权威版本统一为 develop——删除分叉副本

- PLAN/OPTIMIZATION_PLAN 在 develop 与 private-docs 各存一份且 md5 已不同，导致勾选不同步（本轮沉积的成因）
- private-docs 只承载 docs/ 与 面试准备/；计划文档以 develop 为唯一权威
- 批次 P 设计文档状态更新为已排期（F1→R4、F2-F4→R7）"
```

**Step 3: 确认工作区无私有资料误入 develop**

```bash
cd C:/Users/asus/Documents/copilot-lite
git log --oneline -1 -- 面试准备/ ; echo "（应为空：面试准备/ 从未进入 develop）"
```
Expected: 无输出。

**Step 4: 申请推送（需批准）**

`private-docs` 推送 GitHub 需批准（AGENTS §11），且**不得**推 Gitee（`scripts/git-hooks/pre-push` 守卫）。

---

## 完成标准（R0 结束判据）

- [ ] `DEMO_SCRIPT.md` 已落地，含 6 镜头与准入规则
- [ ] `OPTIMIZATION_PLAN.md` 含 §11 冻结清单（≥ 24 条，每条带重启条件）与 §13 R0–R7 路线
- [ ] `PLAN.md` 含 P6 章节，基线与 `develop` 实际一致（337 用例 / 82.53%）
- [ ] `ADMIN_PLAN.md` 状态更新，未完成项 17 → 13（功能项 11 → 7：N2.1–N2.6、N2.8）
- [ ] Task 8 归属核对：**0 条"无归属"**，无悬空引用
- [ ] 未勾选功能项 **77 → ≤ 20**
- [ ] `docs/plan-scope-convergence` 分支仅含 4 个 .md 改动，无代码/配置/问卷改动
- [ ] 合并与推送均经维护者批准后执行
