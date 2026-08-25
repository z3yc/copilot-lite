# Copilot-Lite Backend

Copilot-Lite 后端服务（FastAPI）。

## 本地开发

```bash
# 安装依赖（Python 3.12）
uv sync

# 启动开发服务器（自动重载）
uv run uvicorn app.main:app --reload

# 运行测试
uv run pytest

# 数据库迁移
uv run alembic revision --autogenerate -m "描述"
uv run alembic upgrade head
```

- API 文档：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/api/v1/health

> 开发模式默认使用 SQLite（零依赖）；生产/云端通过 `DATABASE_URL` 配置切换 PostgreSQL。
