"""API 路由汇总。"""

from fastapi import APIRouter

from app.api.routes import (
    auth,
    chat,
    documents,
    health,
    memories,
    sessions,
    settings,
    todos,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(chat.router)
api_router.include_router(documents.router)
api_router.include_router(sessions.router)
api_router.include_router(todos.router)
api_router.include_router(memories.router)
api_router.include_router(settings.router)
