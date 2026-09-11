"""用户模型配置的读取与应用。

- `resolve_user_llm_config`：读取并解密用户配置（无配置返回 None）；
- `apply_user_llm_config`：写入请求上下文，使 `get_llm()` 与辅助 LLM 调用
  （查询改写/记忆提取/摘要）自动使用用户配置；None 时回退环境变量。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_secret
from app.core.llm import LLMConfig, set_llm_config
from app.models import LLMSetting


async def get_user_setting(db: AsyncSession, user_id) -> LLMSetting | None:
    """读取当前用户的模型配置记录。"""
    return await db.scalar(select(LLMSetting).where(LLMSetting.user_id == user_id))


async def resolve_user_llm_config(db: AsyncSession, user_id) -> LLMConfig | None:
    """解析用户模型配置；未配置 / 解密失败返回 None（回退环境变量）。"""
    row = await get_user_setting(db, user_id)
    if row is None or not row.api_key_encrypted:
        return None
    api_key = decrypt_secret(row.api_key_encrypted)
    if not api_key:
        return None
    return LLMConfig(
        api_key=api_key,
        base_url=row.base_url,
        model=row.model,
        temperature=row.temperature,
        max_tokens=row.max_tokens,
    )


async def apply_user_llm_config(db: AsyncSession, user_id) -> None:
    """把用户模型配置写入请求上下文（None = 回退环境变量）。"""
    set_llm_config(await resolve_user_llm_config(db, user_id))
