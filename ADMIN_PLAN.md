# 🛠 Copilot-Lite 管理后台与质量看板计划（ADMIN_PLAN）

> 定位：**作品集/演示为主（可看、可讲），架构为未来企业多租户留接缝**。
> 原则：只读优先、一次一个改动、企业能力"留口不实现"。
> 关联：[AGENTS.md](AGENTS.md)、[OPTIMIZATION_PLAN.md](OPTIMIZATION_PLAN.md)（批次 I/J3/M/L/F）、`docs/知识库Wiki技术方案.md`。
> 状态：**已设计，待排期**。

---

## 1. 目标与边界

| 项 | 结论 |
|---|---|
| 主要用途 | 作品集/面试演示：**用户 + 用量 + 质量看板**，亮点是"质量趋势" |
| 次要目标 | 为多租户企业交付**留接缝**（不实现租户功能） |
| 架构 | **C 混合**：后台自研页负责治理/审计/质量看板；系统级指标 P3 交 Grafana |
| 不做 | 自研 BI、完整租户/成员管理、推理机、对话原文浏览（默认不开放） |

---

## 2. 指标定义与口径（先定口径，否则看板无意义）

### 2.1 检索质量（离线，golden set）
| 指标 | 口径 |
|---|---|
| Recall@K | 命中（expected 出现在前 K）的查询数 / 总查询数 |
| MRR | mean(1 / 命中排名)，未命中记 0 |
| nDCG@K | 分级相关性折损累计增益（需 `relevance` 字段，缺省按命中=1） |
| Hit@K | 至少命中一条的查询占比（≈Recall@K，保留用于分布） |
| 空结果率 | 检索返回 0 条的比例（暴露"查不到"） |
| 按来源切片 | 按 `source_scope`（all / docs / wiki）分别出数 |

### 2.2 生成质量（离线，RAGAS + 自定义）
| 指标 | 口径 |
|---|---|
| Faithfulness | 答案是否忠实于检索内容（RAGAS） |
| AnswerRelevancy | 答案与问题相关度（RAGAS） |
| 引用支撑率 | 答案中的 `[n]` 被判定"确由第 n 条支撑"的比例 |
| **拒答率（负面）** | 对"知识库中不存在"的问题正确拒答的比例 |
| 幻觉标记数 | judge 判定的无支撑断言条数 |

### 2.3 Wiki 图谱（确定性，可对账）
| 指标 | 口径 |
|---|---|
| 双链解析正确率 | 正确解析链接数 / vault 实际 `[[...]]` 数 |
| 悬空链接率 | `target_page_id is null` 的比例 |
| 反向链接对账 | DB backlink 与 vault 反查的一致性 |
| sync 四态 | added / updated / moved / deleted / failed |

### 2.4 治理/运营
| 指标 | 口径 |
|---|---|
| 每用户 | 请求数、token 进出、**成本**、错误率、预算余额、最后活跃、是否配 Key |
| 每模型 | 延迟 p50/p95、错误码、**并发信号量饱和度**、上游 429/5xx |
| 任务 | 队列深度、失败/死信、最后同步时间、单任务耗时 |

> ⚠️ **F1 说明**：排序任务不套 F1（需二值标签）。F1 仅用于"是/否"判定（链接解析对错、意图路由）。

### 2.5 指标可比性（强制）
每次评测必须记录 **配置指纹**：
`{engine, model, prompt_version, embedding_model, top_k, rerank, query_rewrite, wiki_expand}` + **golden set 版本号**。
否则历史数字不可比。

---

## 3. 数据模型（含企业接缝）

> 所有新表预留 **nullable `tenant_id` / `workspace_id`**（默认租户），查询一律带该过滤——以后切多租户不改查询语义。

| 表 | 关键字段 |
|---|---|
| `users`（改造） | 增加**软删除** `deleted_at / deleted_by / delete_reason` + `status`(active/disabled)；`username` 唯一约束改**部分唯一索引**（`WHERE deleted_at IS NULL`）（承接 L7） |
| `audit_logs` | request_id, user_id, action, resource_type, resource_id, result, meta(json), created_at (+tenant/workspace) |
| `usage_daily` | user_id, day, requests, tokens_in, tokens_out, cost, errors (+tenant) |
| `golden_datasets` | name, version, description, created_by, created_at (+tenant) |
| `golden_items` | dataset_id, query, expected_doc_title, must_contain(json), ground_truth, **source_scope**, **query_type**(single/multi/negative), tags |
| `eval_runs` | dataset_id, status(queued/running/done/failed), trigger(manual/ci), config_fingerprint(json), metrics(json), source_scope, total/passed, progress, error, started_at, finished_at, created_by |
| `eval_items` | run_id, query, expected, hit, rank, retrieved(json), judge(json), query_type, source |

> `audit_logs` 可复用/统一 L3 的审计落点；`eval_runs` 承担"作业状态机"（见 §6）。

---

## 4. 后端 API（`/admin`，只读优先）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/admin/overview` | KPI 汇总（用户/请求/token/成本/错误率/最新评测分） |
| POST | `/admin/users` | 新建用户（用户名/密码/角色，复用注册的默认分类初始化） |
| GET | `/admin/users` | 列表（搜索/筛选/分页） |
| GET | `/admin/users/{id}` | 详情（用量/成本/会话/文档/Key 状态/最后活跃） |
| PATCH | `/admin/users/{id}` | 改角色 / 启停 / 重置密码 / 配额预算（**写 + 审计**） |
| DELETE | `/admin/users/{id}` | **软删除**（返回 `{deleted, soft: true}`） |
| POST | `/admin/users/{id}/restore` | 恢复被软删用户 |
| POST | `/admin/users/{id}/force-logout` | 强制下线（`token_version+1`） |
| GET | `/admin/usage` | 用量/成本时间序列（range） |
| GET | `/admin/knowledge` | 文档/Wiki 空间、chunk 数、sync 统计、失败 |
| GET | `/admin/audit` | 审计查询（按 action/user/request_id 过滤） |
| GET | `/admin/eval/datasets` · POST | golden 数据集管理（版本） |
| POST | `/admin/eval/runs` | **页面触发评测**（建作业，返回 run_id） |
| GET | `/admin/eval/runs` · `/{id}` | 运行历史 / 详情（状态/进度/指标） |
| GET | `/admin/eval/runs/{id}/items` | 明细与**失败样本下钻** |
| GET | `/admin/health` | 复用 `/health/ready` + 队列/资源 |

### 4.1 用户管理细则（CRUD）
- **增**：admin 建号可直接设角色；复用注册逻辑（默认分类/初始化）。
- **查**：列表 + 详情（用量/成本/会话数/文档数/Key 是否配置/最后活跃）。
- **改**：角色、启用/禁用、重置密码、每用户配额/预算；**任何改密/禁用/软删都 `token_version+1`**，旧 token 立即失效。
- **删（软删除）**：`deleted_at/deleted_by/delete_reason`；软删后禁止登录，列表/统计/检索统一过滤，数据保留可恢复（AGENTS §13/§14）。
- **恢复**：`POST .../restore` 清空 `deleted_at`。
- **唯一约束**：`username` 改**部分唯一索引**（`WHERE deleted_at IS NULL`），允许删号后重用用户名。
- **护栏**：不能删除/禁用自己；不能删除/降级**最后一个管理员**；删除二次确认 + `delete_reason`；全部写操作写审计。
- **物理删除**：仅合规（GDPR）且写审计，管理后台**不提供**。

**鉴权**：`require_admin`（现按 `User.role=="admin"`）；接口与依赖设计成日后可替换为 `require_permission("admin.read")`（批次 I）。

---

## 5. 前端页面（演示优先）

| 页面 | 内容 | 优先级 |
|---|---|---|
| 概览 | KPI 卡片 + 趋势图 + 最新评测综合分 | P1 |
| 用户与用量 | 用户表（用量/成本/Key 状态/状态）、曲线、限流/预算 | P1 |
| 知识库与任务 | 文档/Wiki 空间、sync 四态、失败/重试 | P1 |
| 审计日志 | 删除/恢复/权限/登录/HITL，按 request_id 串链路 | P1 |
| 质量看板 | 评测历史 + **per-source 切片** + 趋势 + baseline 对比 + 失败下钻 | **P2（卖点）** |
| 系统健康 | health/ready、队列、模型缓存 | P1/P3 |

> 管理后台入口**仅管理员可见**（前端按 `role` 隐藏 + 后端强制鉴权）。

---

## 6. 页面触发评测：作业机制（关键）

页面点"运行评测"不能阻塞 HTTP：
```
POST /admin/eval/runs → 建 eval_runs(status=queued) → 返回 run_id
后台 worker（可开关）→ status=running、写 progress → 执行检索/生成/打分
  → 写 eval_items → status=done/failed + metrics
前端轮询 GET /admin/eval/runs/{id} 看进度与结果
```
要求（对齐 AGENTS §8/§17）：
- **可开关**：`EVAL_JOB_ENABLED`（测试环境默认关闭，避免持测试库句柄）；
- **并发上限 + 超时**：评测跑真实嵌入/LLM judge，必须限并发、可取消；
- **失败可重试**：run 级 failed + error 落库；
- **优先复用 J1**（若先做了 `jobs` 表则复用；否则用 eval_runs 自带状态机）。

---

## 7. 企业留口清单（只留缝）

1. `tenant_id` / `workspace_id` nullable 列（users/documents/wiki_spaces/eval_runs/audit_logs/usage_daily）。
2. `require_admin` → 日后可替换为 RBAC 权限点。
3. `audit_logs` append-only，天然可租户切片。
4. `config_fingerprint` 预留 tenant/workspace 维度。
5. **不实现**：租户切换器、成员管理、跨租户看板（批次 I）。

---

## 8. 安全与审计红线

- 管理员默认**只看元数据，不看用户对话原文**；如需查看须单独权限 + 留痕 + 脱敏（AGENTS §15）。
- **管理员自身操作也入审计**（否则后台是后门）。
- 破坏性操作（停用/清死信/重跑）二次确认。
- 密钥/密文永不回显；日志不含对话原文、密钥、文件内容。
- 用户**软删除/禁用写审计**；禁止删除/禁用自己、禁止删最后一个管理员。
- 新配置项三件套齐全（§7）。

---

## 9. 分阶段清单

### N0 · 地基与接缝（前置）
- [x] **N0.1** `require_admin` 依赖 + `/admin` 路由骨架（未授权 403）。
- [x] **N0.2** `audit_logs` 统一审计表与写入口（复用 L3 审计）。
- [x] **N0.3** 配置三件套：`ADMIN_ENABLED`、`EVAL_JOB_ENABLED`（测试默认关）、`EVAL_JOB_CONCURRENCY`。
- [x] **N0.4** 依赖【批次 M1】：`source_type` 写入 Qdrant payload（per-source 切片前置）。
- [x] **N0.5** 作业机制（`eval_runs` 状态机 + 可开关后台 worker）。
- [x] **N0.6** `users` 增加软删除字段 + `status` + `username` 部分唯一索引迁移（承接 L7）。

### P1 · 治理/审计/概览 + 用户管理 + 评测触发骨架
- [ ] **N1.1** `usage_daily` 聚合表 + 采集/rollup。
- [ ] **N1.2** `GET /admin/overview`（KPI）。
- [ ] **N1.3** `/admin/users` 全套 CRUD：增 / 查 / 改（角色·启停·重置密码·配额）/ **软删除** / 恢复 / 强制下线（写操作审计 + 护栏）。
- [ ] **N1.3b** 前端用户管理页（列表 / 详情 / 编辑 / 软删二次确认 + 恢复入口）。
- [ ] **N1.4** `GET /admin/usage` 时间序列。
- [ ] **N1.5** `GET /admin/knowledge`（sync 四态/失败）。
- [ ] **N1.6** `GET /admin/audit` 查询。
- [ ] **N1.7** `POST /admin/eval/runs` + `GET .../runs`、`.../{id}`（状态/进度）。
- [ ] **N1.8** 前端：管理后台入口（仅 admin）+ 概览/用户/知识库/审计页。
- [ ] **N1.9** 管理员操作审计 + 用户数据默认脱敏。

### P2 · 质量看板（卖点）
- [ ] **N2.1** golden 数据集管理/版本（表 + 上传/复制）。
- [ ] **N2.2** 评测执行器：复用 `rag_eval.py` / `rag_eval_ragas.py` 逻辑，写 `eval_runs`/`eval_items` + 配置指纹。
- [ ] **N2.3** `GET /admin/eval/runs/{id}/items` 明细 + 失败下钻。
- [ ] **N2.4** 指标：Recall/MRR/nDCG/Hit/空结果率 + Faithfulness/Relevancy/**引用支撑率**/**拒答率**。
- [ ] **N2.5** **per-source 切片**（wiki/docs）。
- [ ] **N2.6** 趋势 + **baseline 对比**（配置指纹 + 数据集版本）。
- [ ] **N2.7** Wiki 图谱对账（解析正确率/悬空率/backlink parity）。
- [ ] **N2.8** 前端质量看板（图表库选型见 §12）。
- [ ] **N2.9**（可选）A/B 开关 lift：rerank / query-rewrite / 双链扩展。

### P3 · 可观测与多租户
- [ ] **N3.1** OTel + Grafana + 告警（J2）。
- [ ] **N3.2** 多租户/workspace/角色（批次 I，与 N0 接缝对接）。

---

## 10. 验收门槛（每阶段）
- [ ] 后端 `pytest` 全绿且覆盖率 ≥80%、`ruff` 全过；前端 `npm test` + `build` 零错误。
- [ ] admin 接口**非管理员 403**（回归用例）；管理员写操作**必写审计**。
- [ ] 新配置三件套齐全；后台任务可开关且测试默认关闭。
- [ ] 无密钥/对话原文进入日志或接口响应。
- [ ] 用户**软删除可恢复**；软删后无法登录，且列表/统计/检索已过滤；不能删最后一个管理员。
- [ ] 指标带配置指纹，历史可比。

---

## 11. 依赖与风险
| 依赖 | 说明 |
|---|---|
| 批次 M1 | `source_type` 入 payload → per-source 切片 |
| 批次 L | 审计表/软删除（N0.2 复用） |
| 批次 L7 | 账号软删除（N0.6 / N1.3 承接） |
| 批次 J1 | `jobs` 表（可选，N0.5 可自带状态机） |
| 批次 I | 多租户（P3），接缝在 N0 |

| 风险 | 对策 |
|---|---|
| 评测费钱（LLM judge） | 默认小样本/离线跑，`limit` + 并发上限；judge 可关 |
| 长任务阻塞 | 后台 worker + 进度轮询 + 超时 |
| 指标不可比 | 配置指纹 + 数据集版本强制 |
| 后台越权看数据 | 默认元数据 + 权限 + 留痕 |
| 范围膨胀 | 严格按 P1/P2/P3；企业能力只留缝 |

---

## 12. 已定技术选型（默认，不再单列待定）
- **图表库**：`recharts`（体积小、够用；不引重型 charts 包）。
- **作业机制**：先用 `eval_runs` 自带状态机（不提前引 `jobs` 表）；J1 落地后再迁移。
- **评测结果存储**：DB 表（`eval_runs` / `eval_items`），便于趋势与下钻。
- **后台入口**：独立 `/admin` 路由（与个人主页解耦，利于日后权限收口）。
