# Copilot-Lite 后端镜像
# 构建：docker build -f deploy/Dockerfile -t copilot-lite-backend .

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # 国内网络：uv 装依赖走清华 PyPI 镜像（用户显式配置可覆盖）
    UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple

WORKDIR /app

# 安装 uv（轻量包管理）
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 先复制依赖清单，利用缓存层
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev

# 复制应用代码
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./

EXPOSE 8000

# 启动（生产走 Alembic 迁移，见 deploy 文档）
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
