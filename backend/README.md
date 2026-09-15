# Copilot-Lite Backend

Copilot-Lite 后端服务（FastAPI）。

## 本地开发

```bash
# 安装依赖（Python 3.12）
uv sync

# 数据库迁移（首次：创建数据库并建表）
#   createdb copilot            # 本地 PostgreSQL 已运行时
#   cp .env.example .env        # 配置 DATABASE_URL
uv run alembic upgrade head

# 启动开发服务器（自动重载）
uv run uvicorn app.main:app --reload

# 运行测试
uv run pytest
```

- API 文档：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/api/v1/health

> **数据库策略**：本地 / 测试 / 生产统一 **PostgreSQL**（不再支持 SQLite）。
> 先 `createdb copilot`（默认连接 `postgresql+asyncpg://postgres:root@localhost:5432/copilot`）；
> 表结构由 `create_all`（`RUN_MODE=local`）或 Alembic 迁移（`cloud`）管理。
