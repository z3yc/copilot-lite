# 数据库初始化 SQL 与「SQLite 跑不动迁移链」复盘

> 日期：2026-09-15 ｜ 代码分支：`develop` ｜ 本文：`private-docs`
> 起因：为「其他开发者在本地一键部署」准备建库手段 —— 不跑 Python / Alembic，导入 SQL 即可建库。

---

## 1. 改动文件

| 文件 | 作用 |
|---|---|
| `backend/scripts/db_init_sql.py` | 生成器：以 ORM 元数据为单一源导出 DDL；`--dialect` / `--out` / `--check` |
| `deploy/sql/init_postgres.sql`、`init_sqlite.sql` | 产物：各 394 行 / 17 张表 / 63 条 DDL |
| `deploy/sql/README.md` | 导入说明（含 Docker 内 psql、无 sqlite3 时用 Python 标准库） |
| `backend/tests/test_db_init_sql.py` | 8 个回归用例（表覆盖、缺分号、部分唯一索引、head、真实导入幂等） |
| `.github/workflows/ci.yml`、`Jenkinsfile` | CI 在 `ruff` 之后加 `db_init_sql.py --check`，防模型改了忘生成 |
| `scripts/dev_start.ps1` | 按 `RUN_MODE` 决定是否跑 `alembic upgrade head`（local 模式跳过） |

---

## 2. 原理

### 2.1 核心发现：迁移链在 SQLite 上跑不完

实测（可复现）：

```bash
cd backend && rm -f tmp_mig.db
DATABASE_URL="sqlite+aiosqlite:///./tmp_mig.db" uv run alembic upgrade head
```

结果：跑到第 4 个迁移 `Running upgrade d73001c3fa47 -> 1473b855e26a` 后抛异常：

```
NotImplementedError: No support for ALTER of constraints in SQLite dialect.
Please refer to the batch mode feature which allows for SQLite migrations
using a copy-and-move strategy.
```

落点：`alembic/versions/1473b855e26a_add_categories_table_and_todo_category_.py:43`
→ `op.create_foreign_key(None, "todos", "categories", ["category_id"], ["id"], ondelete="SET NULL")`
（SQLite 的 `ALTER TABLE` 不能 ADD CONSTRAINT；Alembic 的 batch 模式才能 copy-and-move）

**由此确立的几条判断**：

1. 不装 PostgreSQL 的本地开发**不可能**用迁移建表 → `RUN_MODE=local` 的
   `Base.metadata.create_all` **不是"图方便"，而是唯一可行路径**（原设计判断被反向验证）；
2. 代价是 `create_all` 只建缺失表、**不 ALTER 已有表** → 改 ORM 模型必须删库重建
   （已写进 `DEVELOPMENT.md` §2.4，列为"新人第一大坑"）；
3. 想验证迁移脚本，必须 PG + `RUN_MODE=cloud`（迁移链实际只在 PG 上被验证过，
   SQLite 是二等公民 —— 本地开发够用，但不能当作迁移的验收环境）；
4. 因此 `init_sqlite.sql` 是本地**唯一可用**的建表 SQL（迁移链在 SQLite 上产不出来）。

### 2.2 为什么不手写 SQL、也不用 `alembic upgrade head --sql`

| 方案 | 为什么不选 |
|---|---|
| 手写 `init.sql` | 17 张表 / 66 个索引 / 软删除部分唯一索引（`postgresql_where=deleted_at IS NULL`），与模型双份维护必然漂移 |
| `alembic upgrade head --sql` | 6 个历史迁移用 `op.get_bind()` + `sa.inspect()` 做**方言条件 DDL**；离线模式的 MockConnection 不支持 introspection → `NoInspectionAvailable`，中途报错并只产出 271 行残片 |
| **采用：元数据导出** | `CreateTable(t, if_not_exists=True)` + `CreateIndex(i, if_not_exists=True)` 编译成 DDL —— 与 `create_all` **同源**，模型即唯一 schema 源 |

### 2.3 幂等 + 与 Alembic「接力」

- 所有 DDL 带 `IF NOT EXISTS`（含索引）→ 可重复导入，已存在对象跳过；
- 末尾写入 `alembic_version = <当前 head>`（`ScriptDirectory.get_heads()` 取，多 head 直接报错退出）
  → 导入后 `alembic upgrade head` 是 **no-op**，SQL 初始化与迁移两条路能无缝接力；
- 不含任何业务数据（默认分类在注册时补齐、超管由 `SUPER_ADMIN_*` 环境变量创建）。

---

## 3. 踩坑记录

| # | 坑 | 现象 / 处理 |
|---|---|---|
| 1 | **`compile()` 生成的 DDL 不带分号** | 整个文件粘连成一条坏语句，psql 第 390 行"语法错误 在 CREATE 或附近"，**首次导入即失败**；修：`_ddl()` 统一 strip + 补 `;`，并加回归断言 `")\nCREATE" not in sql` |
| 2 | Windows GBK 控制台打 emoji | `UnicodeEncodeError: 'gbk' codec can't encode '\u2705'` 直接崩；改 `[OK]` / `[FAIL]` |
| 3 | git 检出 CRLF 是否影响 `--check` | 实测不会：`Path.read_text()` 归一化换行，CRLF 工作区下 `--check` 仍 exit 0 |
| 4 | **PowerShell 5.1 按 GBK 解析无 BOM 的 `.ps1`** | 往 `dev_start.ps1` 加中文提示后，脚本直接语法崩（`字符串缺少终止符`）；改回英文，并用 `[Parser]::ParseFile` 做语法校验。**结论：仓内 .ps1 一律只写 ASCII** |
| 5 | `sqlalchemy.sql.dialect` 不存在 | `Dialect` 在 `sqlalchemy.engine`（2.0） |

---

## 4. 测试结果（证据）

| 验证项 | 结果 |
|---|---|
| **等价性（硬证据）** | 临时 PG 库 A 跑完 17 个迁移、库 B 导入 `init_postgres.sql`，各自与元数据 `compare_metadata` 差异 **均为 0** |
| 导入幂等（PG） | 导入 2 次均 exit 0（第 2 次全部"已存在，跳过"）；18 张表（17 业务 + `alembic_version`） |
| 导入幂等（SQLite） | 导入 2 次均通过：18 张表 / 66 个索引 / `alembic_version = e7f8a9b0c1d2` |
| 迁移接力 | 在 SQL 导入建的库上跑 `alembic upgrade head` → 无 `Running upgrade`，no-op ✅ |
| 回归测试 | `pytest` 345 passed，覆盖率 **82.53%**（门槛 80）；`ruff` 全过 |
| CI 步骤 | 本地等价命令 `uv run python scripts/db_init_sql.py --check` → `[OK]` exit 0 |
| `dev_start.ps1` | PowerShell Parser 语法校验通过（全 ASCII） |

> 临时库 `copilot_check_mig` / `copilot_check_sql` 验证后已 drop，无残留。

---

## 5. 面试一句话话术

- **讲设计**："初始化 SQL 我不手写，而是从 ORM 元数据自动导出——schema 只能有一个源，手写必然漂移。我还把 `--check` 挂进 CI，改了模型忘了重新生成就会红。"
- **讲发现**："顺手验证出一个既有事实：我们的 Alembic 迁移链在 SQLite 上跑不完——第 4 个迁移给 todos 加外键，SQLite 不支持 `ALTER ... ADD CONSTRAINT`。所以本地用 `create_all` 不是偷懒，是唯一可行路径；代价是改模型要删库，我把这条写进了开发者文档。"
- **讲验证**："我没停在'能导入'：临时 PG 库上分别用迁移链和 SQL 建库，两边跟元数据 `compare_metadata` 差异都是 0，才敢下'等价'的结论。"
- **讲细节**："`compile()` 出来的 DDL 不带分号，我实测导入时整份文件被当成一条语句报语法错误，所以补了分号并写了回归测试；另外 Windows 的 PowerShell 5.1 会按 GBK 解析无 BOM 的 `.ps1`，中文提示会让脚本直接语法崩，仓内脚本因此全用 ASCII。"
- **可延伸**："这套思路就是'把 schema 当代码的单一源来生成一切下游产物'——迁移、初始化 SQL、文档里的 DDL 都从模型导出，人只维护模型。"
