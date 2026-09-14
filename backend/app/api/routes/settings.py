"""模型配置接口：按用户配置 LLM 的 API Key / Base URL / 模型等（页面化配置）。

- GET    /settings/llm       读取当前配置（Key 仅掩码）
- PUT    /settings/llm       保存配置（Key 加密入库）
- DELETE /settings/llm       恢复默认（回退环境变量）
- POST   /settings/llm/test  用给定/已存配置做一次真实连通性测试
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.crypto import decrypt_secret, encrypt_secret, mask_secret
from app.core.db import get_session
from app.core.llm import LLMConfig, build_llm
from app.core.llm_settings import (
    admin_env_config,
    get_user_setting,
    resolve_effective_llm_config,
    resolve_user_llm_config,
)
from app.models import LLMSetting, User
from app.models.llm_setting import DEFAULT_BASE_URL, DEFAULT_MODEL

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/settings", tags=["settings"])


def _validate_url(value: str) -> str:
    value = value.strip()
    if not value.startswith(("http://", "https://")):
        raise ValueError("Base URL 必须以 http:// 或 https:// 开头")
    return value.rstrip("/")


class LLMSettingsIn(BaseModel):
    base_url: str = Field(min_length=1, max_length=255)
    model: str = Field(min_length=1, max_length=128)
    # None = 不修改已存 Key；"" = 清除 Key；非空 = 更新
    api_key: str | None = Field(default=None, max_length=512)
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=2048, ge=1, le=32768)

    _check_url = field_validator("base_url")(_validate_url)


class LLMSettingsOut(BaseModel):
    base_url: str
    model: str
    temperature: float
    max_tokens: int
    api_key_set: bool
    api_key_preview: str
    source: str  # user / env / none


class LLMModelsOut(BaseModel):
    models: list[str]
    current: str
    source: str  # user / env


class LLMTestIn(BaseModel):
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    api_key: str | None = None
    max_tokens: int = Field(default=16, ge=1, le=512)

    _check_url = field_validator("base_url")(_validate_url)


class LLMModelsIn(BaseModel):
    """配置页拉模型列表：用表单中尚未保存的 Base URL / Key。"""

    base_url: str = DEFAULT_BASE_URL
    api_key: str | None = Field(default=None, max_length=512)

    _check_url = field_validator("base_url")(_validate_url)


@router.get("/llm", response_model=LLMSettingsOut)
async def get_llm_settings(
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> LLMSettingsOut:
    """读取当前生效的模型配置（用户配置优先，否则环境变量）。"""
    row = await get_user_setting(db, user.id)
    if row is not None and row.api_key_encrypted:
        preview = mask_secret(decrypt_secret(row.api_key_encrypted))
        return LLMSettingsOut(
            base_url=row.base_url,
            model=row.model,
            temperature=row.temperature,
            max_tokens=row.max_tokens,
            api_key_set=True,
            api_key_preview=preview,
            source="user",
        )
    env = admin_env_config(user)
    if env is not None:
        # 管理员：Key 用 env，但允许已存记录的 model/温度/tokens 覆盖
        return LLMSettingsOut(
            base_url=env.base_url,
            model=row.model if row is not None and row.model else env.model,
            temperature=row.temperature if row is not None else 0.7,
            max_tokens=row.max_tokens if row is not None else (env.max_tokens or 2048),
            api_key_set=True,
            api_key_preview=mask_secret(env.api_key),
            source="env",
        )
    return LLMSettingsOut(
        base_url=DEFAULT_BASE_URL,
        model=DEFAULT_MODEL,
        temperature=0.7,
        max_tokens=2048,
        api_key_set=False,
        api_key_preview="",
        source="none",
    )


@router.get("/llm/models", response_model=LLMModelsOut)
async def list_llm_models(
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> LLMModelsOut:
    """按当前用户配置的 API Key / Base URL 拉取可用模型列表。

    用户配置优先，否则回退环境变量；均未配置时返回 400（前端引导去配置）。
    上游不提供 /models 时返回 502，前端回退为当前模型。
    """
    user_config = await resolve_user_llm_config(db, user.id)
    config = await resolve_effective_llm_config(db, user.id, user)
    if config is None:
        raise HTTPException(
            status_code=400,
            detail="未配置 API Key，请先在「个人主页 → 模型设置」中配置",
        )

    client = build_llm(config)
    try:
        models = await client.list_models()
    except Exception as exc:  # 上游网关差异需回显给用户
        logger.warning("获取模型列表失败: %s", exc)
        raise HTTPException(
            status_code=502, detail=f"获取模型列表失败：{str(exc)[:200]}"
        ) from exc
    return LLMModelsOut(
        models=models,
        current=config.model,
        source="user" if user_config is not None else "env",
    )


@router.post("/llm/models", response_model=LLMModelsOut)
async def list_llm_models_with_key(
    req: LLMModelsIn,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> LLMModelsOut:
    """按配置页中**尚未保存**的 Base URL / Key 拉取模型列表。

    解决“模型名要先填才能保存、但模型名应从列表选”的死循环：
    - 传了 api_key → 用表单里的 Key/URL 直接拉取（**不落库**，Key 走请求体不入 URL/日志）；
    - 未传 → 回退已存用户配置 / 管理员 env。
    """
    api_key = (req.api_key or "").strip()
    if api_key:
        config = LLMConfig(
            api_key=api_key,
            base_url=req.base_url,
            model=DEFAULT_MODEL,
            temperature=0.0,
            max_tokens=1,
        )
        source = "user"
    else:
        user_config = await resolve_user_llm_config(db, user.id)
        config = await resolve_effective_llm_config(db, user.id, user)
        if config is None:
            raise HTTPException(
                status_code=400,
                detail="未配置 API Key，请先在「个人主页 → 模型设置」中配置",
            )
        source = "user" if user_config is not None else "env"

    client = build_llm(config)
    try:
        models = await client.list_models()
    except Exception as exc:  # 上游网关差异需回显给用户
        logger.warning("获取模型列表失败: %s", exc)
        raise HTTPException(
            status_code=502, detail=f"获取模型列表失败：{str(exc)[:200]}"
        ) from exc
    return LLMModelsOut(models=models, current=config.model, source=source)


@router.put("/llm", response_model=LLMSettingsOut)
async def save_llm_settings(
    req: LLMSettingsIn,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> LLMSettingsOut:
    """保存用户模型配置（Key 加密存储，不回传明文）。"""
    row = await get_user_setting(db, user.id)
    if row is None:
        row = LLMSetting(user_id=user.id)
        db.add(row)

    row.base_url = req.base_url
    row.model = req.model
    row.temperature = req.temperature
    row.max_tokens = req.max_tokens
    if req.api_key is not None:
        key = req.api_key.strip()
        row.api_key_encrypted = encrypt_secret(key) if key else None

    await db.commit()
    await db.refresh(row)

    has_key = bool(row.api_key_encrypted)
    preview = mask_secret(decrypt_secret(row.api_key_encrypted)) if has_key else ""
    return LLMSettingsOut(
        base_url=row.base_url,
        model=row.model,
        temperature=row.temperature,
        max_tokens=row.max_tokens,
        api_key_set=has_key,
        api_key_preview=preview,
        source="user" if has_key else ("env" if admin_env_config(user) else "none"),
    )


@router.delete("/llm")
async def delete_llm_settings(
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """删除用户配置，恢复环境变量默认。"""
    row = await get_user_setting(db, user.id)
    if row is not None:
        await db.delete(row)
        await db.commit()
    return {"ok": True, "message": "已恢复默认模型配置"}


@router.post("/llm/test")
async def test_llm_settings(
    req: LLMTestIn,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """用给定（或已存/环境）配置发起一次最小请求，验证连通性。"""
    api_key = (req.api_key or "").strip()
    if api_key:
        config = LLMConfig(
            api_key=api_key,
            base_url=req.base_url,
            model=req.model,
            temperature=0.0,
            max_tokens=req.max_tokens,
        )
    else:
        config = await resolve_effective_llm_config(db, user.id, user)
        if config is None:
            raise HTTPException(status_code=400, detail="未提供 API Key，且无可用的已存/环境配置")
        config = LLMConfig(
            api_key=config.api_key,
            base_url=config.base_url,
            model=config.model,
            temperature=0.0,
            max_tokens=req.max_tokens,
        )

    client = build_llm(config)
    try:
        result = await client.chat([{"role": "user", "content": "ping"}])
    except Exception as exc:  # noqa: BLE001  测试连通性需回显错误
        logger.warning("模型连通性测试失败: %s", exc)
        return {"ok": False, "message": f"连接失败：{str(exc)[:200]}"}
    return {"ok": True, "message": "连接成功", "reply": (result.content or "")[:60]}
