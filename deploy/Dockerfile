# Copilot-Lite 后端镜像
# 构建：docker build -f deploy/Dockerfile -t copilot-lite-backend .

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # 国内网络：uv 装依赖走清华 PyPI 镜像（用户显式配置可覆盖）
    UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple \
    # 非 root 运行：HOME 指向 app 用户目录（uv 运行时缓存可写）
    HOME=/home/app

WORKDIR /app

# 安装 uv（固定版本 tag，构建可复现；避免 latest 漂移）
COPY --from=ghcr.io/astral-sh/uv:0.11.14 /uv /uvx /bin/

# 先复制依赖清单，利用缓存层（README 为 hatchling 构建本地包所需）
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN uv sync --frozen --no-dev

# 复制应用代码
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./

# 非 root 用户运行；/models 目录预创建并授权
# （命名卷首次挂载会继承镜像内目录的属主，保证 app 用户可写模型缓存）
RUN useradd -m -u 1000 app \
    && mkdir -p /models \
    # 注意：HOME=/home/app 在 useradd 之前，uv sync（root）已在 /home/app/.cache/uv
    # 建了属于 root 的缓存目录；必须一并 chown，否则 app 用户跑 `uv run` 报 Permission denied
    && chown -R app:app /app /models /home/app
USER app

EXPOSE 8000

# 启动（生产走 Alembic 迁移，见 deploy 文档）
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
