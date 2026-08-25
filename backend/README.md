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

> **数据库策略**：默认 SQLite（零依赖，克隆即跑）；推荐配置 `.env` 指向本地 PostgreSQL
> （`postgresql+asyncpg://...`），与生产环境同构。表结构统一由 Alembic 迁移管理。
