"""Wiki M1 测试：语法解析 / zip 安全 / 导入同步 / 页面与链接图 / 隔离。"""

import hashlib
import io
import uuid
import zipfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app
from app.rag.vector_store import VectorStore
from app.wiki import importer as wiki_importer
from app.wiki.links import (
    extract_frontmatter,
    extract_links,
    extract_tags,
    slugify,
)


class FakeEmbeddings:
    """确定性伪嵌入（8 维）。"""

    dim = 8

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            digest = hashlib.md5(text.encode()).hexdigest()
            out.append(
                [float(int(digest[i : i + 2], 16)) / 255.0 for i in range(0, 16, 2)]
            )
        return out


@pytest.fixture
def wiki_env(monkeypatch, tmp_path):
    """隔离存储根 + Fake 嵌入 + 8 维向量库。"""
    from app.wiki import service as wiki_service

    monkeypatch.setattr(settings, "WIKI_STORAGE_ROOT", str(tmp_path / "wiki"))
    monkeypatch.setattr(wiki_service, "get_embedding_service", lambda: FakeEmbeddings())
    store = VectorStore(dimension=8)
    monkeypatch.setattr(wiki_service, "get_vector_store", lambda: store)
    return store


def _make_zip(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return buffer.getvalue()


# ---------------- 语法解析 ----------------


def test_extract_links_and_tags_skip_code_blocks():
    text = "# A\n[[Note B]] [[Note C|别名]] ![[Img]] #tag1 #标签2\n```\n[[ignored]]\n```\n"
    links = extract_links(text)
    pairs = {(ref.target, ref.kind) for ref in links}
    assert ("Note B", "link") in pairs
    assert ("Note C", "link") in pairs
    assert ("Img", "embed") in pairs
    assert all("ignored" not in ref.target for ref in links)
    assert extract_tags(text) == ["tag1", "标签2"]


def test_extract_frontmatter():
    text = "---\ntitle: 我的页\ntags: [a, b]\naliases:\n  - x\n---\n正文内容"
    meta, body = extract_frontmatter(text)
    assert meta["title"] == "我的页"
    assert meta["tags"] == ["a", "b"]
    assert meta["aliases"] == ["x"]
    assert body.startswith("正文内容")


def test_slugify():
    assert slugify("Note B") == "note-b"
    assert slugify("我的 笔记") == "我的-笔记"


# ---------------- zip 安全 ----------------


def test_zip_path_traversal_rejected(tmp_path):
    with pytest.raises(wiki_importer.WikiImportError):
        wiki_importer.extract_zip(_make_zip({"../evil.md": "x"}), tmp_path / "d")


def test_zip_oversize_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "WIKI_MAX_ARCHIVE_BYTES", 10)
    with pytest.raises(wiki_importer.WikiImportError):
        wiki_importer.extract_zip(b"x" * 100, tmp_path / "d")


def test_zip_extracts_and_skips_macos(tmp_path):
    data = _make_zip(
        {"a.md": "# A", "__MACOSX/x": "junk", "._a.md": "junk", "sub/b.md": "# B"}
    )
    count = wiki_importer.extract_zip(data, tmp_path / "d")
    assert count == 2
    assert (tmp_path / "d" / "a.md").exists()
    assert (tmp_path / "d" / "sub" / "b.md").exists()


# ---------------- 导入 / 同步 / 页面 ----------------


async def _create_space(client: AsyncClient, headers: dict, name: str = "vault") -> str:
    resp = await client.post(
        "/api/v1/wiki/spaces", json={"name": name}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["id"]


async def _import(client: AsyncClient, headers: dict, space_id: str, files: dict):
    return await client.post(
        f"/api/v1/wiki/spaces/{space_id}/import",
        files={"file": ("vault.zip", _make_zip(files), "application/zip")},
        headers=headers,
    )


async def test_wiki_import_sync_pages_and_links(authed_headers, wiki_env):
    files = {
        "Note A.md": "---\ntitle: A\n---\n# A\n\n链接到 [[Note B]] 与 [[Note C|别名]] #tag1",
        "Note B.md": "# B\n\n内容B",
        "sub/Note C.md": "# C\n\n![[Note A]]",
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        sid = await _create_space(client, authed_headers)
        imported = await _import(client, authed_headers, sid, files)
        assert imported.status_code == 200, imported.text
        stats = imported.json()["data"]
        assert stats["added"] == 3
        assert stats["imported_files"] == 3

        # 二次同步应无变更（幂等）
        again = (
            await client.post(f"/api/v1/wiki/spaces/{sid}/sync", headers=authed_headers)
        ).json()["data"]
        assert again["added"] == 0 and again["updated"] == 0 and again["moved"] == 0

        pages = (
            await client.get(f"/api/v1/wiki/pages?space={sid}", headers=authed_headers)
        ).json()["data"]
        assert pages["total"] == 3

        page_a = next(p for p in pages["items"] if p["rel_path"] == "Note A.md")
        detail = (
            await client.get(f"/api/v1/wiki/pages/{page_a['id']}", headers=authed_headers)
        ).json()["data"]
        assert detail["content"].startswith("---")
        # [[Note B]] 解析到 Note B 页面（slug note-b，target_page_id 非空）
        link_b = next(l for l in detail["links"] if l["target_slug"] == "note-b")
        assert link_b["target_page_id"] is not None
        assert "tag1" in detail["tags"]
        # 反向链接：Note C 嵌入/链接了 A
        assert len(detail["backlinks"]) >= 1


async def test_wiki_update_and_delete(authed_headers, wiki_env):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        sid = await _create_space(client, authed_headers)
        await _import(
            client,
            authed_headers,
            sid,
            {"A.md": "# A\n\n原始", "B.md": "# B\n\n将被删除"},
        )
        # 重导入：A 修改、B 删除（导入后会自动同步）
        second = await _import(client, authed_headers, sid, {"A.md": "# A\n\n修改后"})
        stats = second.json()["data"]
        assert stats["deleted"] == 1
        assert stats["added"] == 0

        pages = (
            await client.get(f"/api/v1/wiki/pages?space={sid}", headers=authed_headers)
        ).json()["data"]
        assert pages["total"] == 1
        assert pages["items"][0]["rel_path"] == "A.md"


async def test_wiki_cross_user_isolation(authed_headers, wiki_env):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        sid = await _create_space(client, authed_headers, "private")
        await _import(client, authed_headers, sid, {"A.md": "# A"})

        other = await client.post(
            "/api/v1/auth/register",
            json={"username": f"u{uuid.uuid4().hex[:8]}", "password": "secret123"},
        )
        other_headers = {"Authorization": f"Bearer {other.json()['data']['token']}"}

        # 看不到他人空间与页面
        spaces = (
            await client.get("/api/v1/wiki/spaces", headers=other_headers)
        ).json()["data"]
        assert all(s["id"] != sid for s in spaces)
        pages = (
            await client.get(f"/api/v1/wiki/pages?space={sid}", headers=other_headers)
        ).json()["data"]
        assert pages["total"] == 0
        # 不能同步/删除他人空间
        assert (
            await client.post(f"/api/v1/wiki/spaces/{sid}/sync", headers=other_headers)
        ).status_code == 404
        assert (
            await client.delete(f"/api/v1/wiki/spaces/{sid}", headers=other_headers)
        ).status_code == 404


async def test_wiki_local_space_and_errors(authed_headers, wiki_env):
    transport = ASGITransport(app=app)
    root = Path(settings.WIKI_STORAGE_ROOT)
    (root / "vault1").mkdir(parents=True, exist_ok=True)
    (root / "vault1" / "a.md").write_text("# A\n\n[[B]]", encoding="utf-8")

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/wiki/spaces",
            json={"name": "l1", "source_type": "local"},
            headers=authed_headers,
        )
        assert resp.status_code == 400
        resp = await client.post(
            "/api/v1/wiki/spaces",
            json={"name": "l2", "source_type": "local", "server_path": "nope"},
            headers=authed_headers,
        )
        assert resp.status_code == 400
        resp = await client.post(
            "/api/v1/wiki/spaces",
            json={"name": "l3", "source_type": "local", "server_path": "vault1"},
            headers=authed_headers,
        )
        assert resp.status_code == 200, resp.text
        sid = resp.json()["data"]["id"]
        sync = await client.post(
            f"/api/v1/wiki/spaces/{sid}/sync", headers=authed_headers
        )
        assert sync.json()["data"]["added"] == 1
        resp = await client.post(
            f"/api/v1/wiki/spaces/{sid}/import",
            files={"file": ("v.zip", _make_zip({"x.md": "# x"}), "application/zip")},
            headers=authed_headers,
        )
        assert resp.status_code == 400


async def test_wiki_delete_space(authed_headers, wiki_env):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        sid = await _create_space(client, authed_headers, "to-delete")
        await _import(client, authed_headers, sid, {"A.md": "# A"})
        resp = await client.delete(f"/api/v1/wiki/spaces/{sid}", headers=authed_headers)
        assert resp.status_code == 200
        spaces = (
            await client.get("/api/v1/wiki/spaces", headers=authed_headers)
        ).json()["data"]
        assert all(s["id"] != sid for s in spaces)


async def test_wiki_move_detection(authed_headers, wiki_env):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        sid = await _create_space(client, authed_headers, "move")
        await _import(client, authed_headers, sid, {"A.md": "# 标题\n\n内容保持不变"})
        second = await _import(client, authed_headers, sid, {"B.md": "# 标题\n\n内容保持不变"})
        stats = second.json()["data"]
        assert stats["moved"] == 1
        assert stats["added"] == 0


async def test_wiki_import_invalid_or_empty_zip(authed_headers, wiki_env):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        sid = await _create_space(client, authed_headers, "badzip")
        bad = await client.post(
            f"/api/v1/wiki/spaces/{sid}/import",
            files={"file": ("bad.zip", b"not-a-zip", "application/zip")},
            headers=authed_headers,
        )
        assert bad.status_code == 400
        empty = await client.post(
            f"/api/v1/wiki/spaces/{sid}/import",
            files={"file": ("e.zip", b"", "application/zip")},
            headers=authed_headers,
        )
        assert empty.status_code == 400


async def test_sync_space_direct_unit(authed_headers, wiki_env):
    """直接调用 service（用于验证覆盖率/核心逻辑）。"""
    from app.core.db import async_session_factory
    from app.wiki import service as wiki_service

    uid = uuid.UUID(authed_headers["uid"])
    async with async_session_factory() as db:
        space = await wiki_service.create_space(db, uid, "direct")
        root = Path(space.root_path)
        (root / "P.md").write_text("# P\n\n正文 [[Q]]", encoding="utf-8")
        (root / "Q.md").write_text("# Q\n\nQ正文", encoding="utf-8")
        stats = await wiki_service.sync_space(db, uid, space)
    assert stats["added"] == 2


async def test_wiki_local_absolute_path(authed_headers, wiki_env, tmp_path, monkeypatch):
    """本地/自托管：允许绝对文件夹路径直接扫描（免上传）。"""
    monkeypatch.setattr(settings, "WIKI_ALLOW_LOCAL_PATH", True)
    vault = tmp_path / "my_obsidian_vault"
    vault.mkdir()
    (vault / "Home.md").write_text("# 首页\n\n[[Other]]", encoding="utf-8")
    (vault / "Other.md").write_text("# 其他\n\n内容", encoding="utf-8")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/wiki/spaces",
            json={"name": "abs", "source_type": "local", "server_path": str(vault)},
            headers=authed_headers,
        )
        assert resp.status_code == 200, resp.text
        sid = resp.json()["data"]["id"]
        sync = await client.post(
            f"/api/v1/wiki/spaces/{sid}/sync", headers=authed_headers
        )
        assert sync.json()["data"]["added"] == 2


async def test_wiki_absolute_path_disallowed(authed_headers, wiki_env, tmp_path, monkeypatch):
    """云端多用户：禁止绝对路径（WIKI_ALLOW_LOCAL_PATH=false）。"""
    monkeypatch.setattr(settings, "WIKI_ALLOW_LOCAL_PATH", False)
    vault = tmp_path / "v2"
    vault.mkdir()
    (vault / "a.md").write_text("# a\n\n正文", encoding="utf-8")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/wiki/spaces",
            json={"name": "x", "source_type": "local", "server_path": str(vault)},
            headers=authed_headers,
        )
        assert resp.status_code == 400
