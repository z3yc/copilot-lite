"""Todo（待办）工具集：展示可插拔工具的实际用法。

每个函数 = 一个 Agent 可调用的工具，通过 @registry.register 注册。
约定：第一个参数 ctx 由执行器注入；其余参数从签名自动生成 schema。
"""

import uuid
from datetime import date

from sqlalchemy import select

from app.models import Category, Todo
from app.tools.base import ToolContext, registry


async def _category_id_by_name(ctx: ToolContext, name: str | None) -> uuid.UUID | None:
    """按分类名查找 id（用户自己的分类）。"""
    if not name:
        return None
    cat = await ctx.session.scalar(
        select(Category).where(Category.user_id == ctx.user_id, Category.name == name)
    )
    return cat.id if cat else None


def _todo_out(t: Todo) -> dict:
    return {
        "id": str(t.id),
        "title": t.title,
        "status": t.status,
        "priority": t.priority,
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "category": t.category_id,
        "tags": list(t.tags or []),
    }


@registry.register
async def todo_list(ctx: ToolContext, status: str | None = None, category: str | None = None) -> list[dict]:
    """列出待办事项，可按状态（pending/done）或分类名（工作/生活/学习/其他）过滤。"""
    stmt = select(Todo).where(Todo.user_id == ctx.user_id).order_by(Todo.created_at.desc())
    if status:
        stmt = stmt.where(Todo.status == status)
    if category:
        cat_id = await _category_id_by_name(ctx, category)
        if cat_id is None:
            return []
        stmt = stmt.where(Todo.category_id == cat_id)
    rows = (await ctx.session.scalars(stmt)).all()
    return [_todo_out(t) for t in rows]


@registry.register
async def todo_create(
    ctx: ToolContext,
    title: str,
    priority: int = 3,
    due_date: str | None = None,
    category: str | None = None,
    tags: list[str] | None = None,
) -> dict:
    """创建待办，title 必填；priority 1-5（默认 3）；due_date 形如 2025-12-31；
    category 分类名（工作/生活/学习/其他）；tags 标签数组。"""
    todo = Todo(
        user_id=ctx.user_id,
        title=title,
        priority=max(1, min(5, priority)),
        due_date=date.fromisoformat(due_date) if due_date else None,
        category_id=await _category_id_by_name(ctx, category),
        tags=tags or [],
    )
    ctx.session.add(todo)
    await ctx.session.commit()
    await ctx.session.refresh(todo)
    return _todo_out(todo)


@registry.register
async def todo_update(
    ctx: ToolContext,
    todo_id: str,
    title: str | None = None,
    status: str | None = None,
    priority: int | None = None,
    due_date: str | None = None,
    category: str | None = None,
    tags: list[str] | None = None,
) -> dict:
    """编辑待办：按 id 修改任意字段（仅更新提供的字段）。"""
    todo = await ctx.session.get(Todo, uuid.UUID(todo_id))
    if todo is None:
        return {"error": f"待办 {todo_id} 不存在"}
    if title is not None:
        todo.title = title
    if status in ("pending", "done"):
        todo.status = status
    if priority is not None:
        todo.priority = max(1, min(5, priority))
    if due_date is not None:
        todo.due_date = date.fromisoformat(due_date) if due_date else None
    if category is not None:
        todo.category_id = await _category_id_by_name(ctx, category)
    if tags is not None:
        todo.tags = tags
    await ctx.session.commit()
    await ctx.session.refresh(todo)
    return _todo_out(todo)


@registry.register
async def todo_complete(ctx: ToolContext, todo_id: str) -> dict:
    """按 id 将待办标记为已完成。"""
    todo = await ctx.session.get(Todo, uuid.UUID(todo_id))
    if todo is None:
        return {"error": f"待办 {todo_id} 不存在"}
    todo.status = "done"
    await ctx.session.commit()
    return _todo_out(todo)


@registry.register
async def todo_delete(ctx: ToolContext, todo_id: str) -> dict:
    """按 id 删除一条待办事项。"""
    todo = await ctx.session.get(Todo, uuid.UUID(todo_id))
    if todo is None:
        return {"error": f"待办 {todo_id} 不存在"}
    await ctx.session.delete(todo)
    await ctx.session.commit()
    return {"deleted": todo_id}
