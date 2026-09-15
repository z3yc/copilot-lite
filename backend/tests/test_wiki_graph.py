"""Wiki 图谱服务单测：空分支、无文档页、悬空/已删除目标边过滤。"""

import uuid

from app.connectors.obsidian.service import build_graph
from app.core.soft_delete import mark_deleted
from app.models import User, WikiLink, WikiPage, WikiSpace


async def _new_user(db) -> uuid.UUID:
    uid = uuid.uuid4()
    db.add(User(id=uid, username=f"u{uid.hex[:10]}", password_hash=""))
    await db.commit()
    return uid


async def test_build_graph_handles_orphans_and_deleted_targets(db_session):
    """无文档页（标签为空）、悬空链接、指向已删除页的边都应被正确处理。"""
    uid = await _new_user(db_session)
    space = WikiSpace(owner_id=uid, name="s", source_type="upload", root_path="/tmp/x")
    db_session.add(space)
    await db_session.flush()

    page_a = WikiPage(
        user_id=uid, space_id=space.id, rel_path="A.md", title="A", slug="a"
    )
    page_b = WikiPage(
        user_id=uid, space_id=space.id, rel_path="B.md", title="B", slug="b"
    )
    db_session.add_all([page_a, page_b])
    await db_session.flush()
    # 悬空边（target 为空）+ 指向 B 的边（B 稍后软删除）
    db_session.add(
        WikiLink(
            user_id=uid, space_id=space.id, source_page_id=page_a.id, target_slug="x"
        )
    )
    db_session.add(
        WikiLink(
            user_id=uid,
            space_id=space.id,
            source_page_id=page_a.id,
            target_slug="b",
            target_page_id=page_b.id,
        )
    )
    await db_session.commit()

    mark_deleted(page_b, uid)
    await db_session.commit()

    data = await build_graph(db_session, uid, space.id)
    assert {n["title"] for n in data["nodes"]} == {"A"}  # 已删除页不出现
    assert data["nodes"][0]["tags"] == []  # 无 document_id → 无标签
    assert data["edges"] == []  # 悬空边 + 指向已删除页的边都被过滤


async def test_build_graph_empty_for_unknown_space(db_session):
    """非法/不存在的空间参数：返回空图谱而非报错。"""
    uid = await _new_user(db_session)
    data = await build_graph(db_session, uid, "not-a-uuid")
    assert data == {"nodes": [], "edges": [], "total_nodes": 0, "truncated": False}
