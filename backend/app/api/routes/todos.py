"""待办 REST 接口：供 CLI todo 子命令与前端直接管理。"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_session
from app.models import Todo, User

router = APIRouter(prefix="/todos", tags=["todos"])


class TodoOut(BaseModel):
    id: str
    title: str
    status: str
    priority: int
    due_date: str | None = None

    @classmethod
    def from_model(cls, t: Todo) -> "TodoOut":
        return cls(
            id=str(t.id),
            title=t.title,
            status=t.status,
            priority=t.priority,
            due_date=t.due_date.isoformat() if t.due_date else None,
        )


class TodoCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    priority: int = Field(default=3, ge=1, le=5)
    due_date: str | None = None


class TodoUpdate(BaseModel):
    status: str = Field(pattern="^(pending|done)$")


@router.get("", response_model=list[TodoOut])
async def list_todos(
    status: str | None = None,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[TodoOut]:
    stmt = select(Todo).where(Todo.user_id == user.id)
    if status:
        stmt = stmt.where(Todo.status == status)
    stmt = stmt.order_by(Todo.created_at.desc())
    todos = (await db.scalars(stmt)).all()
    return [TodoOut.from_model(t) for t in todos]


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
    )
    db.add(todo)
    await db.commit()
    await db.refresh(todo)
    return TodoOut.from_model(todo)


@router.patch("/{todo_id}", response_model=TodoOut)
async def update_todo(
    todo_id: str,
    req: TodoUpdate,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> TodoOut:
    todo = await db.get(Todo, uuid.UUID(todo_id))
    if todo is None or todo.user_id != user.id:
        raise HTTPException(status_code=404, detail="待办不存在")
    todo.status = req.status
    await db.commit()
    await db.refresh(todo)
    return TodoOut.from_model(todo)


@router.delete("/{todo_id}")
async def delete_todo(
    todo_id: str,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    todo = await db.get(Todo, uuid.UUID(todo_id))
    if todo is None or todo.user_id != user.id:
        raise HTTPException(status_code=404, detail="待办不存在")
    await db.delete(todo)
    await db.commit()
    return {"deleted": todo_id}
