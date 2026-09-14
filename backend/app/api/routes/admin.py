"""管理后台接口：鉴权骨架 + 用户管理（ADMIN_PLAN §4 / §9 N1.3）。

约定：
- 整组路由统一挂 ``require_admin``，非管理员一律 403；
- 所有写操作写审计（append-only），越权操作记 denied；
- 删除一律软删除（AGENTS §13/§14）；护栏：不能禁用/删除自己、不能动最后一个管理员；
- 只返回元数据与统计，不返回用户对话原文。
"""

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.core.audit import RESULT_DENIED, record_audit
from app.core.config import settings
from app.core.db import get_session
from app.core.eval_jobs import schedule_eval_run
from app.core.pagination import (
    DEFAULT_PAGE_SIZE,
    PageOut,
    normalize_page,
    page_offset,
)
from app.core.prompts import PROMPT_VERSION
from app.core.security import hash_password
from app.core.soft_delete import mark_deleted
from app.models import (
    AuditLog,
    Category,
    ChatSession,
    Chunk,
    Document,
    EvalRun,
    LLMSetting,
    User,
    WikiLink,
    WikiPage,
    WikiSpace,
)
from app.models.category import DEFAULT_CATEGORIES
from app.models.eval_run import STATUS_QUEUED
from app.models.user import STATUS_ACTIVE, STATUS_DISABLED

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


@router.get("/ping")
async def ping() -> dict:
    """连通性探针：验证管理后台鉴权骨架已生效。"""
    return {"ok": True}


# ---------------- 用户管理 ----------------


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(min_length=6, max_length=64)
    role: str = Field(default="user", pattern="^(user|admin)$")


class UserUpdateRequest(BaseModel):
    role: str | None = Field(default=None, pattern="^(user|admin)$")
    status: str | None = Field(default=None, pattern="^(active|disabled)$")
    password: str | None = Field(default=None, min_length=6, max_length=64)


class UserDeleteRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=255)


class UserSummary(BaseModel):
    id: str
    username: str
    role: str
    status: str
    has_key: bool
    deleted_at: datetime | None = None
    created_at: datetime | None = None


class UserDetail(UserSummary):
    session_count: int = 0
    document_count: int = 0
    last_active: datetime | None = None


def _summary(user: User, has_key: bool) -> UserSummary:
    return UserSummary(
        id=str(user.id),
        username=user.username,
        role=user.role,
        status=user.status,
        has_key=has_key,
        deleted_at=user.deleted_at,
        created_at=user.created_at,
    )


async def _get_user(
    db: AsyncSession, user_id: str, *, include_deleted: bool = False
) -> User:
    """按 id 取用户；畸形 id / 不存在 / 已软删（默认）统一 404，不泄露存在性。"""
    try:
        uid = uuid.UUID(str(user_id))
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="用户不存在") from None
    user = await db.get(User, uid)
    if user is None or (user.deleted_at is not None and not include_deleted):
        raise HTTPException(status_code=404, detail="用户不存在")
    return user


async def _key_user_ids(db: AsyncSession, ids: list[uuid.UUID]) -> set[uuid.UUID]:
    """批量返回已配置模型 Key 的用户 id 集合（避免列表 N+1）。"""
    if not ids:
        return set()
    rows = (await db.scalars(select(LLMSetting.user_id).where(LLMSetting.user_id.in_(ids)))).all()
    return set(rows)


async def _active_admin_count(db: AsyncSession) -> int:
    return (
        await db.scalar(
            select(func.count())
            .select_from(User)
            .where(
                User.role == "admin",
                User.status == STATUS_ACTIVE,
                User.deleted_at.is_(None),
            )
        )
        or 0
    )


async def _deny(
    db: AsyncSession,
    admin: User,
    *,
    action: str,
    resource_id: str,
    reason: str,
    status_code: int = 400,
) -> None:
    """记录越权/护栏拒绝审计后抛错（denied 也必须留痕）。"""
    await record_audit(
        db,
        action=action,
        user_id=admin.id,
        resource_type="user",
        resource_id=resource_id,
        result=RESULT_DENIED,
        meta={"reason": reason},
    )
    await db.commit()
    raise HTTPException(status_code=status_code, detail=reason)


async def _guard_last_admin(
    db: AsyncSession, admin: User, target: User, action: str
) -> None:
    """目标为唯一活跃管理员时禁止降级/禁用/删除（防锁死后台）。"""
    if target.role != "admin":
        return
    if await _active_admin_count(db) <= 1:
        await _deny(
            db,
            admin,
            action=action,
            resource_id=str(target.id),
            reason="不能操作最后一个管理员",
        )


@router.get("/users", response_model=PageOut[UserSummary])
async def list_users(
    q: str | None = None,
    role: str | None = None,
    status: str | None = None,
    include_deleted: bool = False,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> PageOut[UserSummary]:
    """用户列表（搜索/筛选/分页）；默认不含已软删用户。"""
    stmt = select(User)
    if not include_deleted:
        stmt = stmt.where(User.deleted_at.is_(None))
    if q and q.strip():
        stmt = stmt.where(User.username.ilike(f"%{q.strip()}%"))
    if role:
        stmt = stmt.where(User.role == role)
    if status:
        stmt = stmt.where(User.status == status)
    stmt = stmt.order_by(User.created_at.desc())

    page, page_size = normalize_page(page, page_size)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    offset, limit = page_offset(page, page_size)
    users = (await db.scalars(stmt.limit(limit).offset(offset))).all()
    key_ids = await _key_user_ids(db, [u.id for u in users])
    return PageOut(
        items=[_summary(u, u.id in key_ids) for u in users],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/users", response_model=UserSummary)
async def create_user(
    req: UserCreateRequest,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> UserSummary:
    """新建用户（复用注册的默认分类初始化）；活跃用户名重复 409。"""
    exists = await db.scalar(
        select(User.id).where(User.username == req.username, User.deleted_at.is_(None))
    )
    if exists is not None:
        raise HTTPException(status_code=409, detail="用户名已存在")

    user = User(
        username=req.username,
        password_hash=hash_password(req.password),
        role=req.role,
        status=STATUS_ACTIVE,
    )
    db.add(user)
    await db.flush()
    for c in DEFAULT_CATEGORIES:
        db.add(Category(user_id=user.id, **c))
    await record_audit(
        db,
        action="user.create",
        user_id=admin.id,
        resource_type="user",
        resource_id=str(user.id),
        meta={"username": user.username, "role": user.role},
    )
    await db.commit()
    await db.refresh(user)
    return _summary(user, False)


@router.get("/users/{user_id}", response_model=UserDetail)
async def get_user(
    user_id: str,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> UserDetail:
    """用户详情：统计会话/文档数、是否配置 Key、最后活跃（仅元数据）。"""
    user = await _get_user(db, user_id)
    session_count = (
        await db.scalar(
            select(func.count())
            .select_from(ChatSession)
            .where(ChatSession.user_id == user.id, ChatSession.deleted_at.is_(None))
        )
        or 0
    )
    document_count = (
        await db.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.user_id == user.id, Document.deleted_at.is_(None))
        )
        or 0
    )
    has_key = (
        await db.scalar(
            select(func.count())
            .select_from(LLMSetting)
            .where(LLMSetting.user_id == user.id)
        )
        or 0
    ) > 0
    last_active = await db.scalar(
        select(func.max(ChatSession.updated_at)).where(
            ChatSession.user_id == user.id, ChatSession.deleted_at.is_(None)
        )
    )
    summary = _summary(user, has_key)
    return UserDetail(
        **summary.model_dump(),
        session_count=session_count,
        document_count=document_count,
        last_active=last_active,
    )


@router.patch("/users/{user_id}", response_model=UserDetail)
async def update_user(
    user_id: str,
    req: UserUpdateRequest,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> UserDetail:
    """改角色 / 启停 / 重置密码；安全相关变更 token_version+1，全部写审计。"""
    user = await _get_user(db, user_id)
    changed = False

    if req.role is not None and req.role != user.role:
        if user.role == "admin":
            await _guard_last_admin(db, admin, user, "user.role_change")
        user.role = req.role
        await record_audit(
            db,
            action="user.role_change",
            user_id=admin.id,
            resource_type="user",
            resource_id=str(user.id),
            meta={"from": "admin" if req.role == "user" else "user", "to": req.role},
        )
        changed = True

    if req.status is not None and req.status != user.status:
        if user.id == admin.id:
            await _deny(
                db, admin,
                action="user.disable" if req.status == STATUS_DISABLED else "user.enable",
                resource_id=str(user.id),
                reason="不能禁用自己",
            )
        if req.status == STATUS_DISABLED:
            await _guard_last_admin(db, admin, user, "user.disable")
        user.status = req.status
        user.token_version += 1  # 禁用/启用均使旧 token 失效
        await record_audit(
            db,
            action="user.disable" if req.status == STATUS_DISABLED else "user.enable",
            user_id=admin.id,
            resource_type="user",
            resource_id=str(user.id),
        )
        changed = True

    if req.password is not None:
        user.password_hash = hash_password(req.password)
        user.token_version += 1
        await record_audit(
            db,
            action="user.password_reset",
            user_id=admin.id,
            resource_type="user",
            resource_id=str(user.id),
        )
        changed = True

    if changed:
        await db.commit()
        await db.refresh(user)
    return await get_user(str(user.id), db=db, admin=admin)


class UserActionResult(BaseModel):
    id: str
    soft: bool = True
    message: str = "ok"


class UserDeleteResult(BaseModel):
    """删除响应（对齐 ADMIN_PLAN §4/§14：`{deleted, soft: true}`）。"""

    deleted: str
    soft: bool = True


@router.delete("/users/{user_id}", response_model=UserDeleteResult)
async def delete_user(
    user_id: str,
    req: UserDeleteRequest | None = None,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> UserDeleteResult:
    """软删除用户（不物理删除）；返回 {id, soft: true}。"""
    user = await _get_user(db, user_id)
    if user.id == admin.id:
        await _deny(
            db, admin,
            action="user.soft_delete",
            resource_id=str(user.id),
            reason="不能删除自己",
        )
    await _guard_last_admin(db, admin, user, "user.soft_delete")

    reason = req.reason if req else None
    mark_deleted(user, admin.id)
    user.delete_reason = reason
    user.token_version += 1  # 旧 token 立即失效
    await record_audit(
        db,
        action="user.soft_delete",
        user_id=admin.id,
        resource_type="user",
        resource_id=str(user.id),
        meta={"reason": reason},
    )
    await db.commit()
    return UserDeleteResult(deleted=str(user.id), soft=True)


@router.post("/users/{user_id}/restore", response_model=UserActionResult)
async def restore_user(
    user_id: str,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> UserActionResult:
    """恢复被软删用户；若活跃用户名被占用则 409。"""
    user = await _get_user(db, user_id, include_deleted=True)
    if user.deleted_at is None:
        return UserActionResult(id=str(user.id), soft=False, message="用户未被删除")
    busy = await db.scalar(
        select(User.id).where(
            User.username == user.username,
            User.deleted_at.is_(None),
            User.id != user.id,
        )
    )
    if busy is not None:
        raise HTTPException(status_code=409, detail="该用户名已被占用，无法恢复")
    user.deleted_at = None
    user.deleted_by = None
    user.delete_reason = None
    await record_audit(
        db,
        action="user.restore",
        user_id=admin.id,
        resource_type="user",
        resource_id=str(user.id),
    )
    await db.commit()
    return UserActionResult(id=str(user.id), soft=True, message="已恢复")


@router.post("/users/{user_id}/force-logout", response_model=UserActionResult)
async def force_logout_user(
    user_id: str,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> UserActionResult:
    """强制下线：token_version+1，该用户全部旧 token 立即失效。"""
    user = await _get_user(db, user_id)
    user.token_version += 1
    await record_audit(
        db,
        action="user.force_logout",
        user_id=admin.id,
        resource_type="user",
        resource_id=str(user.id),
    )
    await db.commit()
    return UserActionResult(id=str(user.id), soft=False, message="已强制下线")


# ---------------- 审计查询（N1.6） ----------------


class AuditItem(BaseModel):
    id: str
    request_id: str | None = None
    user_id: str | None = None
    action: str
    resource_type: str | None = None
    resource_id: str | None = None
    result: str
    meta: dict = Field(default_factory=dict)
    created_at: datetime | None = None


@router.get("/audit", response_model=PageOut[AuditItem])
async def list_audit(
    action: str | None = None,
    user_id: str | None = None,
    request_id: str | None = None,
    result: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> PageOut[AuditItem]:
    """审计日志查询（按 action / user / request_id / result 过滤，分页）。"""
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if request_id:
        stmt = stmt.where(AuditLog.request_id == request_id)
    if result:
        stmt = stmt.where(AuditLog.result == result)
    if user_id:
        try:
            uid = uuid.UUID(str(user_id))
        except (ValueError, TypeError):
            return PageOut(items=[], total=0, page=1, page_size=page_size)
        stmt = stmt.where(AuditLog.user_id == uid)
    stmt = stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())

    page, page_size = normalize_page(page, page_size)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    offset, limit = page_offset(page, page_size)
    rows = (await db.scalars(stmt.limit(limit).offset(offset))).all()
    return PageOut(
        items=[
            AuditItem(
                id=str(r.id),
                request_id=r.request_id,
                user_id=str(r.user_id) if r.user_id else None,
                action=r.action,
                resource_type=r.resource_type,
                resource_id=r.resource_id,
                result=r.result,
                meta=r.meta or {},
                created_at=r.created_at,
            )
            for r in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


# ---------------- 知识库概览（N1.5） ----------------


class SourceStat(BaseModel):
    source_type: str
    documents: int = 0
    chunks: int = 0


class WikiSpaceStat(BaseModel):
    id: str
    name: str
    owner_id: str | None = None
    page_count: int = 0
    last_synced_at: datetime | None = None


class KnowledgeOut(BaseModel):
    documents_total: int
    chunks_total: int
    failed_documents: int
    by_source: list[SourceStat]
    wiki_spaces: int
    wiki_pages: int
    wiki_dangling_links: int
    spaces: list[WikiSpaceStat]


@router.get("/knowledge", response_model=KnowledgeOut)
async def knowledge_overview(
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> KnowledgeOut:
    """知识库概览：文档/chunk 总量、按来源切片、失败数、Wiki 空间与悬空链接。

    注：Wiki“sync 四态”（added/updated/moved/deleted）为同步过程的瞬时计数，
    当前未持久化，待 sync 统计落库后补充（N2.7 图谱对账）。
    """
    documents_total = (
        await db.scalar(
            select(func.count()).select_from(Document).where(Document.deleted_at.is_(None))
        )
        or 0
    )
    chunks_total = (
        await db.scalar(
            select(func.count()).select_from(Chunk).where(Chunk.deleted_at.is_(None))
        )
        or 0
    )
    failed_documents = (
        await db.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.deleted_at.is_(None), Document.status == "failed")
        )
        or 0
    )

    doc_rows = (
        await db.execute(
            select(Document.source_type, func.count())
            .where(Document.deleted_at.is_(None))
            .group_by(Document.source_type)
        )
    ).all()
    chunk_rows = (
        await db.execute(
            select(Document.source_type, func.count())
            .select_from(Chunk)
            .join(Document, Chunk.document_id == Document.id)
            .where(Chunk.deleted_at.is_(None), Document.deleted_at.is_(None))
            .group_by(Document.source_type)
        )
    ).all()
    by_source: dict[str, SourceStat] = {}
    for source_type, count in doc_rows:
        by_source[source_type] = SourceStat(source_type=source_type, documents=count)
    for source_type, count in chunk_rows:
        entry = by_source.setdefault(source_type, SourceStat(source_type=source_type))
        entry.chunks = count

    wiki_spaces = (
        await db.scalar(
            select(func.count()).select_from(WikiSpace).where(WikiSpace.deleted_at.is_(None))
        )
        or 0
    )
    wiki_pages = (
        await db.scalar(
            select(func.count()).select_from(WikiPage).where(WikiPage.deleted_at.is_(None))
        )
        or 0
    )
    wiki_dangling = (
        await db.scalar(
            select(func.count())
            .select_from(WikiLink)
            .where(WikiLink.target_page_id.is_(None))
        )
        or 0
    )
    space_rows = (
        await db.execute(
            select(WikiSpace, func.count(WikiPage.id))
            .outerjoin(
                WikiPage,
                and_(WikiPage.space_id == WikiSpace.id, WikiPage.deleted_at.is_(None)),
            )
            .where(WikiSpace.deleted_at.is_(None))
            .group_by(WikiSpace.id)
            .order_by(WikiSpace.created_at.desc())
            .limit(50)
        )
    ).all()

    return KnowledgeOut(
        documents_total=documents_total,
        chunks_total=chunks_total,
        failed_documents=failed_documents,
        by_source=sorted(by_source.values(), key=lambda s: s.source_type),
        wiki_spaces=wiki_spaces,
        wiki_pages=wiki_pages,
        wiki_dangling_links=wiki_dangling,
        spaces=[
            WikiSpaceStat(
                id=str(space.id),
                name=space.name,
                owner_id=str(space.owner_id) if space.owner_id else None,
                page_count=page_count,
                last_synced_at=space.last_synced_at,
            )
            for space, page_count in space_rows
        ],
    )


# ---------------- 评测作业接口（N1.7，机制见 §6 / N0.5） ----------------


class EvalRunCreateRequest(BaseModel):
    dataset_id: uuid.UUID | None = None
    source_scope: str = Field(default="all", pattern="^(all|docs|wiki)$")
    trigger: str = Field(default="manual", pattern="^(manual|ci)$")


class EvalRunOut(BaseModel):
    id: str
    dataset_id: str | None = None
    status: str
    trigger: str
    source_scope: str
    config_fingerprint: dict = Field(default_factory=dict)
    metrics: dict = Field(default_factory=dict)
    total: int = 0
    passed: int = 0
    progress: int = 0
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None


def _config_fingerprint() -> dict:
    """当前评测配置指纹（指标可比性，ADMIN_PLAN §2.5）。"""
    from app.rag.embeddings import DEFAULT_MODEL as _EMBED_MODEL

    return {
        "engine": settings.AGENT_ENGINE,
        "model": settings.DEEPSEEK_MODEL,
        "prompt_version": PROMPT_VERSION,
        "embedding_model": _EMBED_MODEL,
        "top_k": settings.RAG_TOP_K,
        "rerank": settings.RAG_RERANK_ENABLED,
        "query_rewrite": settings.RAG_QUERY_REWRITE_ENABLED,
        "wiki_expand": settings.WIKI_LINK_EXPANSION_ENABLED,
    }


def _eval_out(run: EvalRun) -> EvalRunOut:
    return EvalRunOut(
        id=str(run.id),
        dataset_id=str(run.dataset_id) if run.dataset_id else None,
        status=run.status,
        trigger=run.trigger,
        source_scope=run.source_scope,
        config_fingerprint=run.config_fingerprint or {},
        metrics=run.metrics or {},
        total=run.total,
        passed=run.passed,
        progress=run.progress,
        error=run.error,
        started_at=run.started_at,
        finished_at=run.finished_at,
        created_at=run.created_at,
    )


async def _get_eval_run(db: AsyncSession, run_id: str) -> EvalRun:
    try:
        rid = uuid.UUID(str(run_id))
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="评测作业不存在") from None
    run = await db.get(EvalRun, rid)
    if run is None:
        raise HTTPException(status_code=404, detail="评测作业不存在")
    return run


@router.post("/eval/runs", response_model=EvalRunOut)
async def create_eval_run(
    req: EvalRunCreateRequest,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> EvalRunOut:
    """页面触发评测：建 queued 作业并调度后台 worker（不阻塞 HTTP）。"""
    run = EvalRun(
        dataset_id=req.dataset_id,
        status=STATUS_QUEUED,
        trigger=req.trigger,
        source_scope=req.source_scope,
        config_fingerprint=_config_fingerprint(),
        created_by=admin.id,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    await record_audit(
        db,
        action="eval.run_create",
        user_id=admin.id,
        resource_type="eval_run",
        resource_id=str(run.id),
        meta={"source_scope": req.source_scope, "trigger": req.trigger},
    )
    await db.commit()
    await schedule_eval_run(run.id)
    return _eval_out(run)


@router.get("/eval/runs", response_model=PageOut[EvalRunOut])
async def list_eval_runs(
    status: str | None = None,
    source_scope: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> PageOut[EvalRunOut]:
    """评测运行历史（可按状态/来源切片过滤，分页）。"""
    stmt = select(EvalRun)
    if status:
        stmt = stmt.where(EvalRun.status == status)
    if source_scope:
        stmt = stmt.where(EvalRun.source_scope == source_scope)
    stmt = stmt.order_by(EvalRun.created_at.desc())

    page, page_size = normalize_page(page, page_size)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    offset, limit = page_offset(page, page_size)
    runs = (await db.scalars(stmt.limit(limit).offset(offset))).all()
    return PageOut(
        items=[_eval_out(r) for r in runs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/eval/runs/{run_id}", response_model=EvalRunOut)
async def get_eval_run(
    run_id: str,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> EvalRunOut:
    """评测作业详情（状态/进度/指标），供前端轮询。"""
    run = await _get_eval_run(db, run_id)
    return _eval_out(run)
