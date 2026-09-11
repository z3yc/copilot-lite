"""待办 REST 接口：完整增删改查 + 分类 + 标签 + AI 快速创建。"""

import logging
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, parse_uuid
from app.core.budget import add_token_usage, check_token_budget
from app.core.config import settings
from app.core.db import get_session
from app.core.json_parse import parse_json_object
from app.core.llm import get_llm, get_usage_stats
from app.core.llm_settings import apply_user_llm_config
from app.core.pagination import (
    DEFAULT_PAGE_SIZE,
    PageOut,
    normalize_page,
    page_offset,
)
from app.core.prompts.todo import AI_PARSE_PROMPT
from app.core.rate_limit import SlidingWindowLimiter
from app.models import Category, Todo, User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/todos", tags=["todos"])

# AI 解析待办接口限流（纯 LLM 成本接口，比对话更紧）
ai_create_limiter = SlidingWindowLimiter(
    max_requests=settings.API_AI_CREATE_RATE_LIMIT,
    window_seconds=settings.API_CHAT_WINDOW_SECONDS,
)


async def require_ai_create_quota(user: User = Depends(get_current_user)) -> None:
    """AI 解析待办配额：窗口内超频返回 429。"""
    if not ai_create_limiter.allow(f"aiparse:{user.id}"):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")


class CategoryOut(BaseModel):
    id: uuid.UUID
    name: str
    color: str

    model_config = {"from_attributes": True}


class TodoOut(BaseModel):
    id: str
    title: str
    status: str
    priority: int
    due_date: str | None = None
    category_id: str | None = None
    category_name: str | None = None
    category_color: str | None = None
    tags: list[str] = []

    @classmethod
    def from_model(cls, t: Todo) -> "TodoOut":
        return cls(
            id=str(t.id),
            title=t.title,
            status=t.status,
            priority=t.priority,
            due_date=t.due_date.isoformat() if t.due_date else None,
            category_id=str(t.category_id) if t.category_id else None,
            tags=list(t.tags or []),
        )


class TodoCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    priority: int = Field(default=3, ge=1, le=5, description="优先级 1-5，1 最高、5 最低")
    due_date: str | None = None
    category_id: str | None = None
    tags: list[str] = Field(default_factory=list)


class TodoUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    status: str | None = Field(default=None, pattern="^(pending|done)$")
    priority: int | None = Field(default=None, ge=1, le=5, description="优先级 1-5，1 最高、5 最低")
    due_date: str | None = None
    category_id: str | None = None
    tags: list[str] | None = None


async def _attach_category(db: AsyncSession, out: TodoOut, user_id) -> TodoOut:
    """补充分类名称与颜色。"""
    if out.category_id:
        cat = await db.get(Category, uuid.UUID(out.category_id))
        if cat and cat.user_id == user_id:
            out.category_name = cat.name
            out.category_color = cat.color
    return out


@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[CategoryOut]:
    """当前用户的分类列表。"""
    stmt = select(Category).where(Category.user_id == user.id).order_by(Category.sort_order)
    cats = (await db.scalars(stmt)).all()
    return [CategoryOut.model_validate(c) for c in cats]


@router.get("", response_model=PageOut[TodoOut])
async def list_todos(
    status: str | None = None,
    category_id: str | None = None,
    tag: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> PageOut[TodoOut]:
    """待办列表（分页）；支持按状态 / 分类 / 标签过滤。"""
    stmt = select(Todo).where(Todo.user_id == user.id)
    if status:
        stmt = stmt.where(Todo.status == status)
    if category_id:
        try:
            cat_id = uuid.UUID(category_id)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="无效的分类 id") from None
        stmt = stmt.where(Todo.category_id == cat_id)
    stmt = stmt.order_by(Todo.created_at.desc())

    page, page_size = normalize_page(page, page_size)
    if tag:
        # 标签为 JSON 数组，跨库过滤不便：内存过滤后手动分页（个人量级足够）
        all_todos = (await db.scalars(stmt)).all()
        filtered = [t for t in all_todos if tag in (t.tags or [])]
        total = len(filtered)
        offset, limit = page_offset(page, page_size)
        page_items = filtered[offset : offset + limit]
    else:
        total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        offset, limit = page_offset(page, page_size)
        page_items = (await db.scalars(stmt.limit(limit).offset(offset))).all()

    items = [await _attach_category(db, TodoOut.from_model(t), user.id) for t in page_items]
    return PageOut(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=TodoOut)
async def create_todo(
    req: TodoCreate,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> TodoOut:
    todo = Todo(
        user_id=user.id,
        title=req.title,
        priority=req.priority,
        due_date=date.fromisoformat(req.due_date) if req.due_date else None,
        category_id=uuid.UUID(req.category_id) if req.category_id else None,
        tags=req.tags,
    )
    db.add(todo)
    await db.commit()
    await db.refresh(todo)
    return await _attach_category(db, TodoOut.from_model(todo), user.id)


@router.patch("/{todo_id}", response_model=TodoOut)
async def update_todo(
    todo_id: str,
    req: TodoUpdate,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> TodoOut:
    """全字段编辑（仅更新传入的字段）。"""
    todo = await db.get(Todo, parse_uuid(todo_id))
    if todo is None or todo.user_id != user.id:
        raise HTTPException(status_code=404, detail="待办不存在")

    if req.title is not None:
        todo.title = req.title
    if req.status is not None:
        todo.status = req.status
    if req.priority is not None:
        todo.priority = req.priority
    if req.due_date is not None:
        todo.due_date = date.fromisoformat(req.due_date) if req.due_date else None
    if req.category_id is not None:
        todo.category_id = uuid.UUID(req.category_id) if req.category_id else None
    if req.tags is not None:
        todo.tags = req.tags

    await db.commit()
    await db.refresh(todo)
    return await _attach_category(db, TodoOut.from_model(todo), user.id)


@router.delete("/{todo_id}")
async def delete_todo(
    todo_id: str,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    todo = await db.get(Todo, parse_uuid(todo_id))
    if todo is None or todo.user_id != user.id:
        raise HTTPException(status_code=404, detail="待办不存在")
    await db.delete(todo)
    await db.commit()
    return {"deleted": todo_id}


# ---------------- AI 快速创建 ----------------


class AiCreateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)


@router.post("/ai-create", response_model=TodoOut)
async def ai_create_todo(
    req: AiCreateRequest,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    _quota: None = Depends(require_ai_create_quota),
) -> TodoOut:
    """AI 快速创建：自然语言 → LLM 结构化解析 → 创建待办。

    解析失败时降级为"整句作为标题"，保证功能可用。
    """
    check_token_budget(user.id)
    await apply_user_llm_config(db, user.id)
    tokens_before = get_usage_stats().get("total_tokens", 0)
    try:
        llm = get_llm()
        result = await llm.chat(
            [
                {"role": "system", "content": AI_PARSE_PROMPT},
                {"role": "user", "content": req.text},
            ],
            response_format={"type": "json_object"},
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        # 本轮 LLM 用量计入每日预算（LLM 客户端为单例，不在此关闭）
        add_token_usage(user.id, get_usage_stats().get("total_tokens", 0) - tokens_before)

    # 容错解析：围栏/前后噪声/非法 JSON 均降级为空对象（整句作为标题）
    parsed = parse_json_object(result.content)

    # 分类名 → id
    category_id = None
    cat_name = parsed.get("category")
    if cat_name:
        cat = await db.scalar(
            select(Category).where(Category.user_id == user.id, Category.name == cat_name)
        )
        category_id = str(cat.id) if cat else None

    # LLM 输出不可信：优先级夹取 1-5，日期非法置 None（不再 500）
    try:
        priority = int(parsed.get("priority") or 3)
    except (TypeError, ValueError):
        priority = 3
    priority = max(1, min(5, priority))

    due_date = None
    raw_date = parsed.get("due_date")
    if raw_date:
        try:
            due_date = date.fromisoformat(str(raw_date))
        except ValueError:
            due_date = None

    todo = Todo(
        user_id=user.id,
        title=str(parsed.get("title") or req.text).strip()[:255],
        priority=priority,
        due_date=due_date,
        category_id=uuid.UUID(category_id) if category_id else None,
        tags=[str(t) for t in (parsed.get("tags") or [])][:10],
    )
    db.add(todo)
    await db.commit()
    await db.refresh(todo)
    return await _attach_category(db, TodoOut.from_model(todo), user.id)
