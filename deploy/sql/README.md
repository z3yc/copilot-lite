# 数据库初始化 SQL

> **由脚本生成，请勿手工修改** —— 改模型后重新生成即可（见文末）。
> 用途：一条命令把库建好（表结构 + Alembic 版本标记），不需要跑 Python / Alembic。

| 文件 | 方言 | 用途 |
|---|---|---|
| [`init_postgres.sql`](init_postgres.sql) | PostgreSQL | 本地 / Docker / 云端（本仓库统一使用 PG，不再支持 SQLite） |

## 导入

### PostgreSQL（宿主机）

```bash
createdb copilot                                        # 库不存在时先建
psql -U copilot -d copilot -f deploy/sql/init_postgres.sql
```

### PostgreSQL（Docker Compose 内的库）

```bash
cd deploy
docker compose exec -T postgres psql -U copilot -d copilot < sql/init_postgres.sql
```

> 容器启动命令本身会跑 `alembic upgrade head`；只有绕过容器、或要重建库时才需要手工导入。

## 特性

- **幂等**：所有 DDL（含索引）带 `IF NOT EXISTS`，可重复导入，已存在对象自动跳过；
- **不含业务数据**：只有表结构与 `alembic_version`（= 当前迁移 head）；业务数据由服务/接口产生
  （默认分类在用户注册时补齐，超级管理员由 `SUPER_ADMIN_*` 环境变量创建）；
- **Alembic 可接力**：版本号已写到 head，导入后跑 `alembic upgrade head` 是 no-op，不会重复建表。

## 重新生成（模型改动后）

```bash
cd backend
uv run python scripts/db_init_sql.py          # 重新生成
uv run python scripts/db_init_sql.py --check  # 校验产物与当前模型是否一致（不一致 exit 1）
```

生成器以 **ORM 元数据为单一源**（`app/models` 的 `Base.metadata`），与 `RUN_MODE=local` 的
`create_all` 同源；已实测与 Alembic 迁移链结果**等价**：

- PG：迁移链建库 vs SQL 导入建库，各自与 ORM 元数据 `compare_metadata` 差异均为 **0**；
- 已实测导入成功（18 表含 `alembic_version`），重复导入不报错；
- CI 在 `ruff` 之后跑 `--check`（防产物漂移），并在干净 PG 上跑一遍 `alembic upgrade head`。

> 为什么不用 `alembic upgrade head --sql` 生成：历史迁移中有 6 个用 `op.get_bind()` + `sa.inspect()`
> 做方言条件 DDL，离线模式（MockConnection）不支持 introspection，会中途报错并产出残缺 SQL。
