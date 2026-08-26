"""应用配置：基于 pydantic-settings，支持 .env 与环境变量覆盖。

优先级：环境变量 > .env 文件 > 代码默认值。

.env 路径固定为 backend/.env（基于本文件位置解析），
与进程启动目录解耦——无论在哪个目录启动后端都能读到配置。
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py → parents[0]=core, [1]=app, [2]=backend
_BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- 应用基础 ----
    APP_NAME: str = "copilot-lite"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # 运行模式：local（本地开发，SQLite 零依赖）/ cloud（云端，PostgreSQL）
    RUN_MODE: str = "local"

    # JWT 签名密钥（生产必须通过 .env 覆盖为强随机值）
    SECRET_KEY: str = "dev-secret-change-me-in-production"

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
    # Agent 引擎：langgraph（多 Agent 路由，默认）/ handwritten（手写 ReAct，可对比）
    AGENT_ENGINE: str = "langgraph"

    # ---- 预留（后续里程碑启用）----
    REDIS_URL: str = "redis://localhost:6379/0"

    # ---- 知识库（P2）----
    # Qdrant 本地模式（磁盘持久化，无需服务器）；云端可切换为 http(s) 地址
    QDRANT_PATH: str = "./qdrant_data"
    QDRANT_URL: str = "http://localhost:6333"
    # 检索参数
    RAG_TOP_K: int = 5  # 向量/BM25 各自召回数
    RAG_RERANK_CANDIDATE_K: int = 10  # RRF 融合后进入精排的候选数
    RAG_RERANK_TOP_N: int = 3  # 精排后最终注入 LLM 的前 N 条
    RAG_RERANK_ENABLED: bool = True  # Rerank 精排开关（可对比效果）

    # 长期记忆
    MEMORY_TOP_K: int = 5  # 每次召回记忆条数
    MEMORY_EXTRACT_ENABLED: bool = True  # 会话结束后台提取开关（测试环境关闭）


@lru_cache
def get_settings() -> Settings:
    """缓存配置实例，避免每次导入重复解析。"""
    return Settings()


settings = get_settings()
