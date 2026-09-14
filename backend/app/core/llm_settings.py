"""用户模型配置的读取与应用。

- `resolve_user_llm_config`：读取并解密用户配置（无配置返回 None）；
- `admin_env_config`：**仅超级管理员**可用的 env Key 兜底（普通用户 None，禁止白嫖）；
- `apply_user_llm_config`：把"用户自配优先 → 管理员 env 兜底 → 否则 None"写入请求上下文，
  使 `get_llm()` 与辅助 LLM 调用（查询改写/记忆提取/摘要）读取到当前请求的有效配置。
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_secret
from app.core.llm import LLMConfig, env_llm_config, set_llm_config
from app.models import LLMSetting, User


async def get_user_setting(db: AsyncSession, user_id) -> LLMSetting | None:
    """读取当前用户的模型配置记录。"""
    return await db.scalar(select(LLMSetting).where(LLMSetting.user_id == user_id))


async def resolve_user_llm_config(db: AsyncSession, user_id) -> LLMConfig | None:
    """解析用户模型配置；未配置 / 解密失败返回 None。"""
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


def admin_env_config(user: User | None) -> LLMConfig | None:
    """环境变量 Key 的兜底配置：**只有超级管理员**（role=admin）可用。

    普通注册用户即使部署方在环境里配了 Key，也不得使用（禁止白嫖）。
    """
    if user is not None and getattr(user, "role", "") == "admin":
        return env_llm_config()
    return None


def _as_uuid(value) -> uuid.UUID | None:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


async def _load_user(db: AsyncSession, user_id, user: User | None = None) -> User | None:
    if user is not None:
        return user
    uid = _as_uuid(user_id)
    return await db.get(User, uid) if uid else None


async def resolve_effective_llm_config(
    db: AsyncSession, user_id, user: User | None = None
) -> LLMConfig | None:
    """当前用户真正生效的模型配置。

    - 有个人 Key → 用个人配置；
    - 否则若为超级管理员 → 用 env Key 兜底，并允许用已存记录覆盖
      `model / temperature / max_tokens`（保留 env 的 Key 与 Base URL）；
    - 其他 → None（前端引导去配置）。
    """
    config = await resolve_user_llm_config(db, user_id)
    if config is not None:
        return config
    owner = await _load_user(db, user_id, user)
    env = admin_env_config(owner)
    if env is None or owner is None:
        return env
    row = await get_user_setting(db, owner.id)
    if row is not None and row.model:
        return LLMConfig(
            api_key=env.api_key,
            base_url=env.base_url,
            model=row.model,
            temperature=row.temperature,
            max_tokens=row.max_tokens,
        )
    return env


async def apply_user_llm_config(db: AsyncSession, user_id) -> None:
    """写入当前请求的有效模型配置（用户自配优先，管理员可 env 兜底，其余 None）。"""
    set_llm_config(await resolve_effective_llm_config(db, user_id))
