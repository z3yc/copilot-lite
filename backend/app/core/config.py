"""应用配置：基于 pydantic-settings，支持 .env 与环境变量覆盖。

优先级：环境变量 > .env 文件 > 代码默认值。
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- 应用基础 ----
    APP_NAME: str = "copilot-lite"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # 运行模式：local（本地开发，SQLite 零依赖）/ cloud（云端，PostgreSQL）
    RUN_MODE: str = "local"

    # ---- 存储 ----
    # 本地默认 SQLite；云端设置为 PostgreSQL，例如：
    # postgresql+asyncpg://user:pass@localhost:5432/copilot
    DATABASE_URL: str = "sqlite+aiosqlite:///./copilot.db"

    # ---- 日志 ----
    LOG_LEVEL: str = "INFO"

    # ---- 大模型（DeepSeek，兼容 OpenAI SDK）----
    DEEPSEEK_API_KEY: str = ""  # 从 .env 读取，必填
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    # Agent 循环参数
    AGENT_MAX_TURNS: int = 5  # ReAct 循环最大轮数

    # ---- 预留（后续里程碑启用）----
    REDIS_URL: str = "redis://localhost:6379/0"
    QDRANT_URL: str = "http://localhost:6333"


@lru_cache
def get_settings() -> Settings:
    """缓存配置实例，避免每次导入重复解析。"""
    return Settings()


settings = get_settings()
