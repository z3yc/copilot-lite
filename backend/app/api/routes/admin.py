"""管理后台接口骨架：仅管理员可访问（ADMIN_PLAN §4 / AGENTS §6）。

约定：
- 整组路由统一挂 ``require_admin``，非管理员一律 403；
- 只读优先，写操作必须写审计；
- 后续 RBAC 接入时仅替换鉴权依赖，路由不变。
"""

from fastapi import APIRouter, Depends

from app.api.deps import require_admin

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


@router.get("/ping")
async def ping() -> dict:
    """连通性探针：验证管理后台鉴权骨架已生效。"""
    return {"ok": True}
