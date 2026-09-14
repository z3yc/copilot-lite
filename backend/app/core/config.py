"""应用配置：基于 pydantic-settings，支持 .env 与环境变量覆盖。

优先级：环境变量 > .env 文件 > 代码默认值。

.env 路径固定为 backend/.env（基于本文件位置解析），
与进程启动目录解耦——无论在哪个目录启动后端都能读到配置。
"""

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py → parents[0]=core, [1]=app, [2]=backend
_BACKEND_DIR = Path(__file__).resolve().parents[2]

# 代码内置的弱默认密钥（仅限本地开发；云模式启动时校验拦截）
_DEFAULT_SECRET_KEY = "dev-secret-change-me-in-production"


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
    SECRET_KEY: str = _DEFAULT_SECRET_KEY

    # CORS 允许来源（本地开发默认前端地址；云端按部署域名配置）
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # ---- 存储 ----
    # 本地默认 SQLite；云端设置为 PostgreSQL，例如：
    # postgresql+asyncpg://user:pass@localhost:5432/copilot
    DATABASE_URL: str = "sqlite+aiosqlite:///./copilot.db"

    # ---- 日志 ----
    LOG_LEVEL: str = "INFO"

    # ---- 大模型（DeepSeek，兼容 OpenAI SDK）----
    DEEPSEEK_API_KEY: str = ""  # 可选：默认全员不可用；仅超级管理员可作兜底（见 SUPER_ADMIN）
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"
    # 超级管理员（可选）：显式配置非空密码才会在启动时种子该账号（role=admin）。
    # 该账号未自配 Key 时可用 DEEPSEEK_API_KEY 兜底；其他注册用户一律必须自配（禁白嫖）。
    SUPER_ADMIN_USERNAME: str = "demo"
    SUPER_ADMIN_PASSWORD: str = ""
    # LLM 调用健壮性（显式配置，不依赖 SDK 默认值）
    LLM_TIMEOUT_SECONDS: float = 60.0  # 单次请求超时
    LLM_MAX_RETRIES: int = 2  # SDK 层重试次数
    LLM_MAX_TOKENS: int = 2048  # 单次回复 token 上限（成本控制）
    # LLM 并发上限（进程内信号量；防止多 SSE 同时打爆 API 限额与账单）
    LLM_MAX_CONCURRENCY: int = 3
    # 每用户每日 token 预算（0=不限，仅统计；开启后超限返回 429）
    LLM_DAILY_TOKEN_BUDGET: int = 0
    # 流式请求是否请求 usage 统计（stream_options.include_usage；
    # 个别兼容网关不支持时可关闭）
    LLM_TRACK_STREAM_USAGE: bool = True
    # API 限流（滑动窗口，按用户维度；个人量级内存实现）
    API_CHAT_RATE_LIMIT: int = 30  # 对话接口：窗口内最大请求数
    API_CHAT_WINDOW_SECONDS: float = 60.0
    API_AI_CREATE_RATE_LIMIT: int = 10  # AI 解析待办接口（更紧：纯 LLM 成本）

    # Agent 循环参数
    AGENT_MAX_TURNS: int = 5  # ReAct 循环最大轮数
    # 上下文窗口：注入 LLM 的最近对话消息条数（system 上下文不占窗口）
    HISTORY_WINDOW: int = 20
    # 滚动历史 token 预算（0=不限）：在条数窗口之上再按估算 token 裁剪，
    # 防止长消息（工具结果/长文）在条数内仍撑爆上下文与成本
    HISTORY_MAX_TOKENS: int = 4000
    # Agent 引擎：langgraph（多 Agent 路由，默认）/ handwritten（手写 ReAct，可对比）
    AGENT_ENGINE: str = "langgraph"

    # ---- 预留（后续里程碑启用）----
    REDIS_URL: str = "redis://localhost:6379/0"

    # ---- 知识库（P2）----
    # Qdrant 本地模式（磁盘持久化，无需服务器）；云端可切换为 http(s) 地址
    QDRANT_PATH: str = "./qdrant_data"
    QDRANT_URL: str = "http://localhost:6333"
    # Qdrant 远程模式 API Key（云端部署必配；本地模式忽略）
    QDRANT_API_KEY: str = ""
    # 检索参数
    RAG_TOP_K: int = 5  # 向量/BM25 各自召回数
    RAG_RERANK_CANDIDATE_K: int = 10  # RRF 融合后进入精排的候选数
    RAG_RERANK_TOP_N: int = 3  # 精排后最终注入 LLM 的前 N 条
    RAG_RERANK_ENABLED: bool = True  # Rerank 精排开关（可对比效果）
    # 查询向量缓存条数（单条 query 嵌入的 lru_cache 上限）
    EMBED_QUERY_CACHE_SIZE: int = 512
    # Rerank 结果缓存条数（(query, passages) → 分数）
    RERANK_CACHE_SIZE: int = 128
    # 查询改写（multi-query 召回）：LLM 生成多个检索表述后跨查询 RRF 融合
    RAG_QUERY_REWRITE_ENABLED: bool = True
    RAG_QUERY_REWRITE_VARIANTS: int = 2  # 除原问题外的改写数量

    # ---- 嵌入模型缓存 ----
    # fastembed 模型缓存目录（默认落 %TEMP% 易被清理 → 每次加载都联网重下，很慢）
    # 固定到持久卷（如挂载 data/ 卷），下载一次后长期复用
    EMBEDDING_CACHE_DIR: str = "./data/models"
    # 启动时后台预热嵌入模型（首次会下载约 50MB；测试环境关闭）
    EMBEDDING_PREWARM: bool = True

    # 长期记忆
    MEMORY_TOP_K: int = 5  # 每次召回记忆条数
    MEMORY_EXTRACT_ENABLED: bool = True  # 会话结束后台提取开关（测试环境关闭）
    # 会话摘要后台压缩开关（测试环境关闭，避免后台任务占用测试库句柄）
    SUMMARY_COMPRESS_ENABLED: bool = True

    # ---- Wiki 本地知识库（Obsidian 导入）----
    WIKI_ENABLED: bool = True
    # 受管副本根目录（本地路径导入需位于此目录下；zip 导入解压到此）
    WIKI_STORAGE_ROOT: str = "./data/wiki"
    # 定时同步间隔（分钟；0=仅手动触发）
    WIKI_SCAN_INTERVAL_MINUTES: int = 0
    # 检索时是否用双链邻居扩展召回（可开关对比效果）
    WIKI_LINK_EXPANSION_ENABLED: bool = True
    WIKI_EXPAND_HOPS: int = 1  # 邻居扩展跳数（保留接口，当前实现 1 跳）
    WIKI_EXPAND_NEIGHBORS: int = 2  # 链接邻居最多补充的候选块数
    WIKI_GRAPH_MAX_NODES: int = 300  # 图谱接口单次返回节点数上限（超出按度数截断）
    # 导入安全上限（防 zip 炸弹）
    WIKI_MAX_ARCHIVE_BYTES: int = 200 * 1024 * 1024  # 压缩包大小上限 200MB
    WIKI_MAX_EXTRACT_BYTES: int = 500 * 1024 * 1024  # 解压后总大小上限 500MB
    WIKI_MAX_FILES: int = 5000  # 单次导入文件数上限
    # 是否把 vault 内非 Markdown（PDF/DOCX/TXT）也索引进 Wiki 空间
    WIKI_INCLUDE_NON_MD: bool = True
    # 扫描时额外排除的目录名（逗号分隔；默认排除模板目录，减噪声）
    WIKI_EXCLUDE_DIRS: str = "templates,模板,.templates,_templates"
    # 是否允许 local 空间使用**绝对文件夹路径**直接扫描：
    # 本地/自托管建议 true；云端多用户部署建议 false（仅允许受管目录/zip）
    WIKI_ALLOW_LOCAL_PATH: bool = True

    # ---- 管理后台 / 评测作业（ADMIN_PLAN）----
    # 管理后台开关：关闭后 /admin 一律 404；仅管理员（role=admin）可访问
    ADMIN_ENABLED: bool = True
    # 页面触发评测的后台作业开关（后台任务，测试环境默认关闭，AGENTS §8）
    EVAL_JOB_ENABLED: bool = False
    # 评测作业并发上限（评测跑真实嵌入 / LLM judge，必须限并发）
    EVAL_JOB_CONCURRENCY: int = 1

    @model_validator(mode="after")
    def _reject_default_secret(self) -> "Settings":
        """安全自检：云模式禁止使用代码内置的默认 JWT 密钥。

        防止部署时照抄 .env.example 漏配 SECRET_KEY——
        默认密钥公开在仓库中，等于认证后门。
        """
        if self.RUN_MODE == "cloud" and self.SECRET_KEY == _DEFAULT_SECRET_KEY:
            raise ValueError(
                "生产模式禁止使用默认 SECRET_KEY，请在 .env 中设置为强随机值"
                '（生成命令：python -c "import secrets;print(secrets.token_urlsafe(48))"）'
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """缓存配置实例，避免每次导入重复解析。"""
    return Settings()


settings = get_settings()
