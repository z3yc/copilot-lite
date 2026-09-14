"""管理后台用户管理测试（ADMIN_PLAN §4.1 / §9 N1.3）。

覆盖：列表分页、创建（默认分类/重名/软删后重用）、改角色、启停、
软删除+恢复、强制下线、护栏（自己/最后管理员）、写操作审计。
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.db import async_session_factory
from app.main import app
from app.models import AuditLog, Category, User


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _create_user(client, admin_headers, username: str, role: str = "user") -> dict:
    r = await client.post(
        "/api/v1/admin/users",
        json={"username": username, "password": "secret123", "role": role},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


@pytest.mark.asyncio
async def test_list_users_pagination(client, admin_headers) -> None:
    """用户列表返回分页结构。"""
    await _create_user(client, admin_headers, f"list{uuid.uuid4().hex[:6]}")
    r = await client.get("/api/v1/admin/users", headers=admin_headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total"] >= 1
    assert data["page"] == 1
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_create_user_initializes_default_categories(client, admin_headers) -> None:
    """admin 建号：用户创建成功且初始化默认分类（复用注册逻辑）。"""
    username = f"create{uuid.uuid4().hex[:6]}"
    data = await _create_user(client, admin_headers, username)
    assert data["username"] == username
    assert data["role"] == "user"
    assert data["status"] == "active"

    async with async_session_factory() as db:
        uid = uuid.UUID(data["id"])
        count = len(
            (await db.scalars(select(Category).where(Category.user_id == uid))).all()
        )
    assert count >= 4


@pytest.mark.asyncio
async def test_create_duplicate_username_conflict(client, admin_headers) -> None:
    """活跃用户名重复 → 409。"""
    username = f"dup{uuid.uuid4().hex[:6]}"
    await _create_user(client, admin_headers, username)
    r = await client.post(
        "/api/v1/admin/users",
        json={"username": username, "password": "secret123", "role": "user"},
        headers=admin_headers,
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_create_reuses_soft_deleted_username(client, admin_headers) -> None:
    """软删用户名可再次创建（部分唯一索引）。"""
    username = f"reuse{uuid.uuid4().hex[:6]}"
    data = await _create_user(client, admin_headers, username)
    r = await client.request(
        "DELETE",
        f"/api/v1/admin/users/{data['id']}",
        json={"reason": "测试注销"},
        headers=admin_headers,
    )
    assert r.status_code == 200
    r = await client.post(
        "/api/v1/admin/users",
        json={"username": username, "password": "secret123", "role": "user"},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_cannot_demote_or_disable_last_admin(client, admin_headers) -> None:
    """护栏：不能降级/禁用最后一个管理员（含自己）。"""
    me = await client.get("/api/v1/auth/me", headers=admin_headers)
    my_id = me.json()["data"]["id"]

    r = await client.patch(
        f"/api/v1/admin/users/{my_id}", json={"role": "user"}, headers=admin_headers
    )
    assert r.status_code == 400

    r = await client.patch(
        f"/api/v1/admin/users/{my_id}", json={"status": "disabled"}, headers=admin_headers
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_disable_user_blocks_login_and_old_token(client, admin_headers) -> None:
    """禁用用户：status=disabled、token_version+1，旧 token 与再登录均 401。"""
    username = f"dis{uuid.uuid4().hex[:6]}"
    data = await _create_user(client, admin_headers, username)

    # 该用户登录拿 token
    r = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": "secret123"}
    )
    token = r.json()["data"]["token"]
    user_headers = {"Authorization": f"Bearer {token}"}

    # 禁用
    r = await client.patch(
        f"/api/v1/admin/users/{data['id']}",
        json={"status": "disabled"},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "disabled"

    # 旧 token 失效
    r = await client.get("/api/v1/auth/me", headers=user_headers)
    assert r.status_code == 401
    # 重新登录被拒
    r = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": "secret123"}
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_cannot_disable_or_delete_self(client, admin_headers) -> None:
    """护栏：管理员不能禁用/删除自己。"""
    me = await client.get("/api/v1/auth/me", headers=admin_headers)
    my_id = me.json()["data"]["id"]

    r = await client.request(
        "DELETE",
        f"/api/v1/admin/users/{my_id}",
        json={"reason": "x"},
        headers=admin_headers,
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_soft_delete_excluded_then_restore(client, admin_headers) -> None:
    """软删除：不进列表默认视图、数据仍在；恢复后重新可见。"""
    username = f"del{uuid.uuid4().hex[:6]}"
    data = await _create_user(client, admin_headers, username)
    uid = data["id"]

    r = await client.request(
        "DELETE",
        f"/api/v1/admin/users/{uid}",
        json={"reason": "违规"},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["data"] == {"deleted": uid, "soft": True}

    # 默认列表不含；include_deleted=true 可见且带 deleted_at
    r = await client.get("/api/v1/admin/users", headers=admin_headers)
    assert all(u["id"] != uid for u in r.json()["data"]["items"])
    r = await client.get(
        "/api/v1/admin/users?include_deleted=true", headers=admin_headers
    )
    assert any(u["id"] == uid for u in r.json()["data"]["items"])

    # 物理行仍在
    async with async_session_factory() as db:
        row = await db.get(User, uuid.UUID(uid))
        assert row is not None and row.deleted_at is not None

    # 恢复
    r = await client.post(f"/api/v1/admin/users/{uid}/restore", headers=admin_headers)
    assert r.status_code == 200
    r = await client.get("/api/v1/admin/users", headers=admin_headers)
    assert any(u["id"] == uid for u in r.json()["data"]["items"])


@pytest.mark.asyncio
async def test_force_logout_invalidates_token(client, admin_headers) -> None:
    """强制下线：token_version+1，旧 token 401，可重新登录。"""
    username = f"kick{uuid.uuid4().hex[:6]}"
    data = await _create_user(client, admin_headers, username)
    r = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": "secret123"}
    )
    token = r.json()["data"]["token"]

    r = await client.post(
        f"/api/v1/admin/users/{data['id']}/force-logout", headers=admin_headers
    )
    assert r.status_code == 200

    r = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_write_actions_are_audited(client, admin_headers) -> None:
    """管理员写操作必写审计（创建/禁用/软删）。"""
    username = f"audit{uuid.uuid4().hex[:6]}"
    data = await _create_user(client, admin_headers, username)
    uid = data["id"]
    await client.patch(
        f"/api/v1/admin/users/{uid}",
        json={"status": "disabled"},
        headers=admin_headers,
    )
    await client.request(
        "DELETE",
        f"/api/v1/admin/users/{uid}",
        json={"reason": "x"},
        headers=admin_headers,
    )

    async with async_session_factory() as db:
        actions = set(
            (await db.scalars(select(AuditLog.action))).all()
        )
    assert {"user.create", "user.disable", "user.soft_delete"} <= actions


@pytest.mark.asyncio
async def test_get_user_detail(client, admin_headers) -> None:
    """用户详情：统计字段与 Key 状态（仅元数据）。"""
    data = await _create_user(client, admin_headers, f"det{uuid.uuid4().hex[:6]}")
    r = await client.get(f"/api/v1/admin/users/{data['id']}", headers=admin_headers)
    assert r.status_code == 200
    detail = r.json()["data"]
    assert detail["id"] == data["id"]
    assert detail["session_count"] == 0
    assert detail["document_count"] == 0
    assert detail["has_key"] is False


@pytest.mark.asyncio
async def test_promote_user_to_admin(client, admin_headers) -> None:
    """改角色：用户可提升为管理员。"""
    data = await _create_user(client, admin_headers, f"pro{uuid.uuid4().hex[:6]}")
    r = await client.patch(
        f"/api/v1/admin/users/{data['id']}",
        json={"role": "admin"},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["data"]["role"] == "admin"


@pytest.mark.asyncio
async def test_reset_password_invalidates_old_token(client, admin_headers) -> None:
    """重置密码：token_version+1，旧 token 失效，新密码可登录。"""
    username = f"pwd{uuid.uuid4().hex[:6]}"
    data = await _create_user(client, admin_headers, username)
    r = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": "secret123"}
    )
    old_token = r.json()["data"]["token"]

    r = await client.patch(
        f"/api/v1/admin/users/{data['id']}",
        json={"password": "newpass123"},
        headers=admin_headers,
    )
    assert r.status_code == 200

    r = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {old_token}"})
    assert r.status_code == 401
    r = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": "newpass123"}
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_re_enable_user_allows_login(client, admin_headers) -> None:
    """启用被禁用用户后可重新登录（status 回到 active）。"""
    username = f"ena{uuid.uuid4().hex[:6]}"
    data = await _create_user(client, admin_headers, username)
    await client.patch(
        f"/api/v1/admin/users/{data['id']}",
        json={"status": "disabled"},
        headers=admin_headers,
    )
    r = await client.patch(
        f"/api/v1/admin/users/{data['id']}",
        json={"status": "active"},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "active"
    r = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": "secret123"}
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_malformed_and_missing_user_404(client, admin_headers) -> None:
    """畸形/不存在的 user_id 一律 404（不泄露存在性）。"""
    r = await client.get("/api/v1/admin/users/not-a-uuid", headers=admin_headers)
    assert r.status_code == 404
    r = await client.get(
        f"/api/v1/admin/users/{uuid.uuid4()}", headers=admin_headers
    )
    assert r.status_code == 404
    r = await client.post(
        f"/api/v1/admin/users/{uuid.uuid4()}/force-logout", headers=admin_headers
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_restore_when_not_deleted(client, admin_headers) -> None:
    """恢复未删除用户：返回 soft=false，不做变更。"""
    data = await _create_user(client, admin_headers, f"rst{uuid.uuid4().hex[:6]}")
    r = await client.post(
        f"/api/v1/admin/users/{data['id']}/restore", headers=admin_headers
    )
    assert r.status_code == 200
    assert r.json()["data"]["soft"] is False


@pytest.mark.asyncio
async def test_list_filters(client, admin_headers) -> None:
    """列表筛选：角色/状态/关键词。"""
    username = f"flt{uuid.uuid4().hex[:6]}"
    data = await _create_user(client, admin_headers, username)
    r = await client.get(
        f"/api/v1/admin/users?q={username}&role=user&status=active",
        headers=admin_headers,
    )
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    assert [i["id"] for i in items] == [data["id"]]


@pytest.mark.asyncio
async def test_user_handlers_direct(db_session, admin_headers) -> None:
    """直接调用用户 CRUD handler：覆盖各变更分支与审计查询。"""
    from app.api.routes import admin as admin_module
    from app.models import User

    async with async_session_factory() as db:
        admin_user = await db.get(User, uuid.UUID(admin_headers["uid"]))
        created = await admin_module.create_user(
            admin_module.UserCreateRequest(
                username=f"direct{uuid.uuid4().hex[:6]}",
                password="secret123",
                role="user",
            ),
            db=db,
            admin=admin_user,
        )
        uid = created.id

        detail = await admin_module.get_user(uid, db=db, admin=admin_user)
        assert detail.id == uid

        promoted = await admin_module.update_user(
            uid, admin_module.UserUpdateRequest(role="admin"), db=db, admin=admin_user
        )
        assert promoted.role == "admin"
        demoted = await admin_module.update_user(
            uid, admin_module.UserUpdateRequest(role="user"), db=db, admin=admin_user
        )
        assert demoted.role == "user"

        await admin_module.update_user(
            uid, admin_module.UserUpdateRequest(password="newpass123"), db=db, admin=admin_user
        )
        disabled = await admin_module.update_user(
            uid, admin_module.UserUpdateRequest(status="disabled"), db=db, admin=admin_user
        )
        assert disabled.status == "disabled"

        deleted = await admin_module.delete_user(
            uid, admin_module.UserDeleteRequest(reason="direct"), db=db, admin=admin_user
        )
        assert deleted.deleted == uid
        restored = await admin_module.restore_user(uid, db=db, admin=admin_user)
        assert restored.id == uid
        kicked = await admin_module.force_logout_user(uid, db=db, admin=admin_user)
        assert kicked.id == uid

        audit = await admin_module.list_audit(
            action=None,
            user_id=admin_headers["uid"],
            request_id=None,
            result=None,
            page=1,
            page_size=20,
            db=db,
            admin=admin_user,
        )
        assert audit.total >= 1
        # 畸形 user_id 过滤：安全返回空页
        empty = await admin_module.list_audit(
            action=None,
            user_id="not-a-uuid",
            request_id=None,
            result=None,
            page=1,
            page_size=20,
            db=db,
            admin=admin_user,
        )
        assert empty.total == 0
