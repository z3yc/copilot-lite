# R3 · M5 引用来源标注 实施计划

> **REQUIRED SUB-SKILL:** 执行本计划时使用 superpowers:executing-plans（或在同一会话按任务逐条 TDD 执行）。
> 设计依据：`2026-09-15-r3-citation-source-design.md`（同目录）。
> 分支：`feat/rag-citation-source`（自 `develop` 切出）；文档提交在 `private-docs` 工作区（`../copilot-lite-private`）。

**Goal:** 引用条目区分「Wiki / 空间 / 页面」与「文档 / 页码」，并支持点击跳转到对应 Wiki 页面或文档详情。

**Architecture:** 来源身份解析收敛到连接器 seam（`SourceConnector.describe_sources` 默认实现 + `collect_source_meta` 汇总），展示标签格式化收敛到 `app/rag/citations.py` 纯函数；前端用 App 层 `openTarget` 状态驱动跨页签跳转。

**Tech Stack:** FastAPI + SQLAlchemy(async) + PostgreSQL（后端）；React 18 + TS + Ant Design + vitest（前端）。

**标签口径（测试断言以此为准）**

| 场景 | `source_kind` | `source` |
|---|---|---|
| Wiki（连接器命中） | `wiki` | `Wiki / 我的笔记 / 方法论` |
| Wiki（meta 兜底，页面行已删/重建） | `wiki` | `Wiki / 我的笔记 / 方法论`（无 `wiki` 跳转对象） |
| 文档（有标题路径与页码） | `document` | `文档 / 学习笔记.md / 第一章 > 第一节 / 第 3 页` |
| 文档（无页码） | `document` | `文档 / 学习笔记.md / 第一章` |
| 文档（无标题路径无页码） | `document` | `文档 / 学习笔记.md` |

> 相对设计 §1 的一句补充：**文档标签保留标题路径**（无标题路径时省略），信息量不降级；Wiki 标签按设计只到「空间 / 页面」。

---

## Task 1: 后端纯函数 `app/rag/citations.py`

**Files:**
- Create: `backend/app/rag/citations.py`
- Test: `backend/tests/test_citation_sources.py`

**Step 1: 写失败测试**

```python
"""引用构造：来源类型标签（Wiki/文档）+ 可跳转身份。"""
from app.rag.citations import build_citation, build_source_label
from app.rag.retriever import RetrievedChunk


def _chunk(meta: dict, document_id: str = "d1") -> RetrievedChunk:
    return RetrievedChunk(chunk_id="c1", content="正文内容", meta=meta, score=0.5, document_id=document_id)


def test_wiki_label_from_origin():
    kind, label = build_source_label(
        {"document_title": "方法论"}, {"kind": "wiki", "space_name": "我的笔记", "title": "方法论"}
    )
    assert kind == "wiki"
    assert label == "Wiki / 我的笔记 / 方法论"


def test_wiki_label_falls_back_to_chunk_meta():
    kind, label = build_source_label(
        {"wiki_space": "我的笔记", "wiki_title": "方法论"}, None
    )
    assert (kind, label) == ("wiki", "Wiki / 我的笔记 / 方法论")


def test_document_label_with_headings_and_page():
    kind, label = build_source_label(
        {"document_title": "学习笔记.md", "headings": ["第一章", "第一节"], "page": 3}, None
    )
    assert (kind, label) == ("document", "文档 / 学习笔记.md / 第一章 > 第一节 / 第 3 页")


def test_wiki_citation_carries_navigation():
    cite = build_citation(
        1,
        _chunk({"wiki_space": "我的笔记", "wiki_title": "方法论"}),
        {
            "kind": "wiki",
            "page_id": "p1",
            "space_id": "s1",
            "space_name": "我的笔记",
            "rel_path": "笔记/方法论.md",
            "title": "方法论",
        },
    )
    assert cite["source"] == "Wiki / 我的笔记 / 方法论"
    assert cite["source_kind"] == "wiki"
    assert cite["wiki"] == {
        "page_id": "p1",
        "space_id": "s1",
        "space_name": "我的笔记",
        "rel_path": "笔记/方法论.md",
    }
    assert cite["index"] == 1 and cite["chunk_id"] == "c1" and cite["document_id"] == "d1"


def test_wiki_fallback_has_no_navigation():
    cite = build_citation(1, _chunk({"wiki_space": "我的笔记", "wiki_title": "方法论"}), None)
    assert cite["source_kind"] == "wiki"
    assert "wiki" not in cite


def test_document_citation_page_none_when_absent():
    cite = build_citation(2, _chunk({"document_title": "报告.pdf"}), None)
    assert cite["source"] == "文档 / 报告.pdf"
    assert cite["source_kind"] == "document"
    assert cite["page"] is None
```

**Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_citation_sources.py -q`
Expected: FAIL（`ModuleNotFoundError: app.rag.citations`）

**Step 3: 最小实现**

```python
"""引用构造：把检索结果 + 来源身份格式化为可展示、可跳转的引用。

来源身份由连接器提供（`SourceConnector.describe_sources`），本模块**不含任何具体来源知识**：
只做「类型判定 → 标签格式化 → 契约字段拼装」，保证展示口径唯一（AGENTS §12 连接器收口）。
"""

WIKI_KIND = "wiki"
DOC_KIND = "document"

_MAX_SNIPPET = 160


def build_source_label(meta: dict, origin: dict | None) -> tuple[str, str]:
    """返回 (source_kind, 展示标签)。

    Wiki 优先用连接器身份（含空间名，可跳转）；缺失时回退 chunk meta 快照
    （页面行已软删/重建时仍显示正确标签，只是不可跳）。
    """
    meta = meta or {}
    if origin and origin.get("kind") == WIKI_KIND:
        parts = ["Wiki", str(origin.get("space_name") or ""), str(origin.get("title") or "")]
        return WIKI_KIND, " / ".join(p for p in parts if p)

    wiki_space = meta.get("wiki_space")
    wiki_title = meta.get("wiki_title")
    if wiki_space or wiki_title:
        parts = ["Wiki", str(wiki_space or ""), str(wiki_title or meta.get("document_title") or "")]
        return WIKI_KIND, " / ".join(p for p in parts if p)

    parts = ["文档", str(meta.get("document_title") or "未知文档")]
    headings = meta.get("headings") or []
    if headings:
        parts.append(" > ".join(str(h) for h in headings))
    if isinstance(meta.get("page"), int):
        parts.append(f"第 {meta['page']} 页")
    return DOC_KIND, " / ".join(parts)


def build_citation(index: int, result, origin: dict | None = None) -> dict:
    """构造单条引用（落 Message.extra.citations）。"""
    kind, label = build_source_label(result.meta or {}, origin)
    page = (result.meta or {}).get("page")
    cite: dict = {
        "index": index,
        "chunk_id": result.chunk_id,
        "document_id": result.document_id,
        "source": label,
        "source_kind": kind,
        "page": page if isinstance(page, int) else None,
        "snippet": result.content[:_MAX_SNIPPET],
    }
    if kind == WIKI_KIND and origin and origin.get("page_id"):
        cite["wiki"] = {
            "page_id": str(origin["page_id"]),
            "space_id": str(origin.get("space_id") or ""),
            "space_name": str(origin.get("space_name") or ""),
            "rel_path": str(origin.get("rel_path") or ""),
        }
    return cite
```

**Step 4: 跑测试确认通过**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_citation_sources.py -q`
Expected: 6 passed

**Step 5: 提交**

```bash
git add backend/app/rag/citations.py backend/tests/test_citation_sources.py
git commit -m "feat(rag): 引用来源标签纯函数——类型判定/标签格式化收敛到 citations.py"
```

---

## Task 2: 连接器 seam（默认实现 + 汇总容错）

**Files:**
- Modify: `backend/app/connectors/base.py`（`SourceConnector` 末尾新增方法）
- Modify: `backend/app/connectors/registry.py`（新增 `collect_source_meta` + `import logging` + `logger`）
- Test: `backend/tests/test_citation_sources.py`（追加）

**Step 1: 写失败测试（追加到 Task 1 的测试文件）**

```python
async def test_collect_source_meta_merges_and_tolerates_failure(monkeypatch):
    from app.connectors import registry as registry_module

    class Good:
        name = "good"

        async def describe_sources(self, db, user_id, document_ids):
            return {"d1": {"kind": "wiki", "page_id": "p1"}}

    class Boom:
        name = "boom"

        async def describe_sources(self, db, user_id, document_ids):
            raise RuntimeError("连接器故障")

    monkeypatch.setattr(registry_module, "_REGISTRY", {"good": Good(), "boom": Boom()})
    merged = await registry_module.collect_source_meta(object(), "u1", ["d1"])
    assert merged["d1"]["page_id"] == "p1"  # 故障连接器不拖垮汇总


async def test_collect_source_meta_skips_without_session_or_ids():
    from app.connectors import registry as registry_module

    assert await registry_module.collect_source_meta(None, "u1", ["d1"]) == {}
    assert await registry_module.collect_source_meta(object(), "u1", []) == {}
```

**Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_citation_sources.py -q`
Expected: FAIL（`AttributeError: module ... has no attribute 'collect_source_meta'`）

**Step 3: 实现**

`base.py` 追加（放在 `sync` 之后）：

```python
    async def describe_sources(self, db, user_id, document_ids: list[str]) -> dict[str, dict]:
        """按 document_id 返回引用所需的来源身份（可选能力）。

        默认返回空：不提供引用身份的连接器无需实现。检索/工具层据此
        展示来源标签与跳转目标，**不感知具体来源**（AGENTS §12）。
        """
        return {}
```

`registry.py` 追加：

```python
import logging
...
logger = logging.getLogger(__name__)


async def collect_source_meta(db, user_id, document_ids: list[str]) -> dict[str, dict]:
    """汇总各连接器提供的来源身份（document_id → 身份 dict）。

    增强能力，失败只记警告并跳过：来源标注不能拖垮检索主链路（AGENTS §10）。
    """
    if db is None or not document_ids:
        return {}
    merged: dict[str, dict] = {}
    for connector in _REGISTRY.values():
        try:
            merged.update(await connector.describe_sources(db, user_id, document_ids) or {})
        except Exception:
            logger.warning("连接器 %s 来源身份解析失败", connector.name, exc_info=True)
    return merged
```

**Step 4: 跑测试确认通过**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_citation_sources.py -q`
Expected: 8 passed

**Step 5: 提交**

```bash
git add backend/app/connectors/base.py backend/app/connectors/registry.py backend/tests/test_citation_sources.py
git commit -m "feat(connectors): SourceConnector 来源身份 hook——默认空实现 + 汇总容错"
```

---

## Task 3: Obsidian 连接器实现 `describe_sources`

**Files:**
- Modify: `backend/app/connectors/obsidian/connector.py`
- Modify: `backend/app/connectors/obsidian/service.py`
- Test: `backend/tests/test_citation_sources.py`（追加；复用 `tests/test_wiki_graph.py` 的建表方式）

**Step 1: 写失败测试**

```python
async def test_obsidian_describe_sources_returns_wiki_identity(db_session):
    import uuid

    from app.connectors.obsidian import service as wiki_service
    from app.models import Document, WikiPage, WikiSpace

    uid = uuid.uuid4()
    space = WikiSpace(owner_id=uid, name="我的笔记", source_type="upload", root_path="/tmp/x")
    db_session.add(space)
    await db_session.flush()
    doc = Document(user_id=uid, title="方法论", source_type="wiki", status="ready")
    db_session.add(doc)
    await db_session.flush()
    page = WikiPage(
        user_id=uid, space_id=space.id, rel_path="笔记/方法论.md", title="方法论",
        slug="方法论", document_id=doc.id,
    )
    db_session.add(page)
    await db_session.commit()

    meta = await wiki_service.describe_sources(db_session, uid, [str(doc.id)])
    origin = meta[str(doc.id)]
    assert origin["kind"] == "wiki"
    assert origin["page_id"] == str(page.id)
    assert origin["space_id"] == str(space.id)
    assert origin["space_name"] == "我的笔记"
    assert origin["rel_path"] == "笔记/方法论.md"


async def test_obsidian_describe_sources_filters_other_user_and_deleted(db_session):
    import uuid

    from app.connectors.obsidian import service as wiki_service
    from app.models import Document, WikiPage, WikiSpace

    owner, other = uuid.uuid4(), uuid.uuid4()
    space = WikiSpace(owner_id=owner, name="私有", source_type="upload", root_path="/tmp/y")
    db_session.add(space)
    await db_session.flush()
    doc = Document(user_id=owner, title="私密", source_type="wiki", status="ready")
    db_session.add(doc)
    await db_session.flush()
    db_session.add(
        WikiPage(user_id=owner, space_id=space.id, rel_path="a.md", title="私密", slug="a", document_id=doc.id)
    )
    await db_session.commit()

    # 跨用户：无权者拿不到任何身份（AGENTS §6.3）
    assert await wiki_service.describe_sources(db_session, other, [str(doc.id)]) == {}
    # user_id 缺失：fail-closed
    assert await wiki_service.describe_sources(db_session, None, [str(doc.id)]) == {}
    # 软删页面：不再提供身份
    page = (await db_session.execute(__import__("sqlalchemy").select(WikiPage))).scalar_one()
    page.deleted_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    await db_session.commit()
    assert await wiki_service.describe_sources(db_session, owner, [str(doc.id)]) == {}
```

**Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_citation_sources.py -q`
Expected: FAIL（`AttributeError: ... has no attribute 'describe_sources'`）

**Step 3: 实现（service.py 追加）**

```python
async def describe_sources(db, user_id, document_ids: list[str]) -> dict[str, dict]:
    """按 document_id 批量解析 Wiki 页面身份（引用标签 + 跳转目标）。

    单次 JOIN 查询（`wiki_pages.document_id` 已有索引，非 N+1）；
    强制 user_id 与软删过滤——跨用户/已删页面一律不返回（AGENTS §6.3/§13）。
    """
    if db is None or user_id is None:
        return {}
    ids: list[uuid.UUID] = []
    for raw in document_ids or []:
        try:
            ids.append(uuid.UUID(str(raw)))
        except (ValueError, AttributeError, TypeError):
            continue
    if not ids:
        return {}
    rows = (
        await db.execute(
            select(WikiPage, WikiSpace.name)
            .join(WikiSpace, WikiPage.space_id == WikiSpace.id)
            .where(
                WikiPage.document_id.in_(ids),
                WikiPage.user_id == uuid.UUID(str(user_id)),
                WikiPage.deleted_at.is_(None),
                WikiSpace.deleted_at.is_(None),
            )
        )
    ).all()
    return {
        str(page.document_id): {
            "kind": "wiki",
            "page_id": str(page.id),
            "space_id": str(page.space_id),
            "space_name": space_name,
            "rel_path": page.rel_path,
            "title": page.title,
        }
        for page, space_name in rows
    }
```

> 落地时按 service.py 现有 import 风格补齐 `uuid` / `select` / `WikiPage` / `WikiSpace`（若已存在则复用，勿重复 import）。

`connector.py` 追加：

```python
    async def describe_sources(self, db, user_id, document_ids: list[str]) -> dict[str, dict]:
        return await service.describe_sources(db, user_id, document_ids)
```

**Step 4: 跑测试确认通过**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_citation_sources.py -q`
Expected: 10 passed

**Step 5: 提交**

```bash
git add backend/app/connectors/obsidian/
git commit -m "feat(connectors): Obsidian 来源身份解析——单次 JOIN + 用户/软删过滤，引用可跳转"
```

---

## Task 4: `kb_search` 接线（LLM 可见来源同口径）

**Files:**
- Modify: `backend/app/tools/kb_tool.py`
- Modify: `backend/tests/test_kb_tool.py:54`（断言更新）
- Test: `backend/tests/test_citations.py`（既有用例保持通过 = 旧格式兼容）

**Step 1: 先改断言（失败测试）**

`backend/tests/test_kb_tool.py` 中：

```python
    assert results[0]["来源"] == "文档 / 学习笔记.md / 第一章 > 第一节 / 第 3 页"
```

追加一个 Wiki 命中用例（直接 mock 检索 + monkeypatch `collect_source_meta`）：

```python
@pytest.mark.asyncio
async def test_kb_search_wiki_citation_is_navigable(db_session, monkeypatch) -> None:
    """Wiki 命中：来源标签带类型，citation 带可跳转 page_id。"""
    import app.tools.kb_tool as kb_module
    from app.connectors import registry as connectors_registry

    monkeypatch.setattr(
        kb_module,
        "hybrid_search",
        FakeHybridSearch(
            [
                RetrievedChunk(
                    chunk_id="c9",
                    content="方法论正文",
                    meta={"headings": [], "document_title": "方法论", "wiki_space": "我的笔记", "wiki_title": "方法论"},
                    score=0.8,
                    document_id="d9",
                )
            ]
        ),
    )

    async def fake_collect(db, user_id, document_ids):
        return {"d9": {"kind": "wiki", "page_id": "p9", "space_id": "s9", "space_name": "我的笔记", "rel_path": "a.md", "title": "方法论"}}

    monkeypatch.setattr(connectors_registry, "collect_source_meta", fake_collect)
    monkeypatch.setattr(kb_module, "collect_source_meta", fake_collect)

    ctx = ToolContext(session=db_session, user_id=DEFAULT_USER_ID)
    result = await registry.execute("kb_search", '{"query": "方法论", "top_k": 3}', ctx)

    assert ctx.citations[0]["wiki"]["page_id"] == "p9"
    assert ctx.citations[0]["source"] == "Wiki / 我的笔记 / 方法论"
    assert json.loads(result)["结果"][0]["来源"] == "Wiki / 我的笔记 / 方法论"
```

> 顶部补 `import json`。

**Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_kb_tool.py -q`
Expected: FAIL（旧断言 `学习笔记.md > 第一章 ...` 与新实现不符 / `collect_source_meta` 未接入）

**Step 3: 实现 `kb_tool.py`**

```python
from app.connectors.registry import collect_source_meta
from app.rag.citations import build_citation
```

在拿到 `results` 之后（双链扩展之后）插入：

```python
    # 来源身份（Wiki 等连接器提供；失败不影响检索，AGENTS §10）
    origins = await collect_source_meta(
        ctx.session, user_filter, [r.document_id for r in results if r.document_id]
    )
```

把循环体里的 `source` 拼装与 `citations.append(...)` 替换为：

```python
    for i, r in enumerate(results, start=1):
        cite = build_citation(i, r, origins.get(str(r.document_id)))
        payload.append(
            {
                "编号": i,
                "chunk_id": r.chunk_id,
                "来源": cite["source"],
                "内容": r.content[:500],
            }
        )
        citations.append(cite)
```

（`meta`/`headings`/`title` 局部变量随之删除；`ctx.citations = citations` 与返回 JSON 结构保持不变。）

**Step 4: 跑测试确认通过**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_kb_tool.py tests/test_citations.py -q`
Expected: 全部 passed

**Step 5: 提交**

```bash
git add backend/app/tools/kb_tool.py backend/tests/test_kb_tool.py
git commit -m "feat(rag): kb_search 引用带来源类型与跳转身份——LLM 可见来源同口径"
```

---

## Task 5: 前端类型 + ChatPanel 标签与回调

**Files:**
- Modify: `web/src/types.ts`（`Citation`）
- Modify: `web/src/components/ChatPanel.tsx:341-365`
- Test: `web/src/components/ChatPanel.test.tsx`

**Step 1: 写失败测试（追加）**

```tsx
it("Wiki 引用显示类型标签并可点击跳转", async () => {
  const onOpenCitation = vi.fn();
  renderChat({
    citations: [
      {
        index: 1, chunk_id: "c1", document_id: "d1",
        source: "Wiki / 我的笔记 / 方法论", source_kind: "wiki",
        wiki: { page_id: "p1", space_id: "s1", space_name: "我的笔记", rel_path: "a.md" },
      },
    ],
    onOpenCitation,
  });
  const link = await screen.findByRole("button", { name: "查看来源 1" });
  expect(link).toHaveTextContent("[1]");
  expect(link).toHaveAttribute("title", "Wiki / 我的笔记 / 方法论");
  await userEvent.click(link);
  expect(onOpenCitation).toHaveBeenCalledTimes(1);
  expect(onOpenCitation.mock.calls[0][0].wiki.page_id).toBe("p1");
});

it("旧格式引用（无 source_kind）仍渲染且不可跳", async () => {
  const onOpenCitation = vi.fn();
  renderChat({
    citations: [{ index: 1, chunk_id: "c1", source: "旧文档 > 第一章" }],
    onOpenCitation,
  });
  expect(await screen.findByText("旧文档 > 第一章")).toBeInTheDocument();
  expect(onOpenCitation).not.toHaveBeenCalled();
});
```

> 具体写法对齐该文件既有 helper（渲染 assistant 消息 + `extra.citations`）；不可跳条目用 `<span className="cite">`，不注册 `role="button"`。

**Step 2: 跑测试确认失败**

Run: `cd web && npx vitest run src/components/ChatPanel.test.tsx`
Expected: FAIL（`onOpenCitation` 未定义 / 新标签未渲染）

**Step 3: 实现**

`types.ts`：

```ts
export interface Citation {
  index: number;
  chunk_id: string;
  document_id?: string;
  /** 带类型的展示标签（Wiki / 空间 / 页面 或 文档 / 文件名 / 第 N 页） */
  source: string;
  /** 旧数据无此字段 → 仅文本展示、不可跳转 */
  source_kind?: "wiki" | "document";
  page?: number | null;
  snippet?: string;
  /** source_kind=wiki 且解析成功时提供（前端跳转目标） */
  wiki?: { page_id: string; space_id: string; space_name: string; rel_path: string };
}
```

`ChatPanel.tsx`：Props 增 `onOpenCitation?: (c: Citation) => void;`，渲染改为：

```tsx
{m.extra!.citations!.map((c) => {
  const navigable = !!(c.wiki?.page_id || c.document_id);
  const onClick = () => (navigable && onOpenCitation ? onOpenCitation(c) : message.info(`[${c.index}] ${c.source}`));
  return navigable ? (
    <a key={c.index} className="cite" role="button" tabIndex={0}
       aria-label={`查看来源 ${c.index}`} title={c.source}
       onClick={(e) => { e.stopPropagation(); onClick(); }}
       onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onClick(); } }}>
      [{c.index}]
    </a>
  ) : (
    <span key={c.index} className="cite" title={c.source}>[{c.index}]</span>
  );
})}
```

（`snippet` 不再用于 `title`：类型标签 + 空间/页码信息量更高；如需保留可 `title={`${c.source}\n${c.snippet ?? ""}`}`。）以实际落地为准，但测试断言以 `title === c.source` 为准。

**Step 4: 跑测试确认通过**

Run: `cd web && npx vitest run src/components/ChatPanel.test.tsx`
Expected: PASS

**Step 5: 提交**

```bash
git add web/src/types.ts web/src/components/ChatPanel.tsx web/src/components/ChatPanel.test.tsx
git commit -m "feat(web): 引用显示来源类型标签——Wiki/文档可点击，旧格式降级不可跳"
```

---

## Task 6: App 层跳转路由 + WikiPanel 消费

**Files:**
- Modify: `web/src/App.tsx`
- Modify: `web/src/components/WikiPanel.tsx`
- Test: `web/src/components/WikiPanel.test.tsx`

**Step 1: 写失败测试（追加）**

```tsx
it("openTarget 指定页面时自动打开（必要时切空间）", async () => {
  await renderWiki({ openTarget: { pageId: "p2", spaceId: "s2" } });
  expect(await screen.findByText("页面正文")).toBeInTheDocument();
  expect(fetchWikiPage).toHaveBeenCalledWith("p2");
  expect(onOpened).toHaveBeenCalled();
});
```

**Step 2: 跑测试确认失败**

Run: `cd web && npx vitest run src/components/WikiPanel.test.tsx`
Expected: FAIL（未消费 `openTarget`）

**Step 3: 实现**

`App.tsx`：

```tsx
export type OpenTarget =
  | { kind: "wiki"; pageId: string; spaceId?: string }
  | { kind: "doc"; docId: string };
const [openTarget, setOpenTarget] = useState<OpenTarget | null>(null);

const openCitation = useCallback((c: Citation) => {
  if (c.wiki?.page_id) {
    setTab("wiki");
    setOpenTarget({ kind: "wiki", pageId: c.wiki.page_id, spaceId: c.wiki.space_id || undefined });
  } else if (c.document_id) {
    setTab("kb");
    setActiveCat("all");
    setOpenTarget({ kind: "doc", docId: c.document_id });
  }
}, []);
```

传给面板：

```tsx
<ChatPanel ... onOpenCitation={openCitation} />
<WikiPanel openTarget={openTarget?.kind === "wiki" ? openTarget : null} onOpened={() => setOpenTarget(null)} />
<KbPanel ... openTarget={openTarget?.kind === "doc" ? openTarget : null} onOpened={() => setOpenTarget(null)} />
```

`WikiPanel.tsx`：

```tsx
interface Props {
  openTarget?: { pageId: string; spaceId?: string } | null;
  onOpened?: () => void;
}

useEffect(() => {
  if (!openTarget) return;
  const { pageId, spaceId } = openTarget;
  if (spaceId && spaceId !== activeSpace) {
    setActiveSpace(spaceId);       // 左栏与详情保持一致
    loadPages(spaceId);
  }
  void openPage(pageId);
  onOpened?.();
}, [openTarget]);
```

> `loadPages` 若现有实现从状态取 `activeSpace`，则改为接受可选参数 `spaceId`（不传时用状态值），避免闭包读到旧空间。

**Step 4: 跑测试确认通过**

Run: `cd web && npx vitest run src/components/WikiPanel.test.tsx src/App.test.tsx`
Expected: PASS

**Step 5: 提交**

```bash
git add web/src/App.tsx web/src/components/WikiPanel.tsx web/src/components/WikiPanel.test.tsx
git commit -m "feat(web): 引用跳转接线——App openTarget 状态 + Wiki 面板消费（含切空间）"
```

---

## Task 7: KbPanel 消费 `openTarget`

**Files:**
- Modify: `web/src/components/KbPanel.tsx`
- Test: `web/src/components/KbPanel.test.tsx`

**Step 1: 写失败测试（追加）**

```tsx
it("openTarget 指定文档时复位过滤并展开详情", async () => {
  await renderKb({ openTarget: { docId: "d9" }, activeCat: "pdf" });
  expect(await screen.findByText("分块正文")).toBeInTheDocument();
  expect(fetchDocDetail).toHaveBeenCalledWith("d9");
  expect(onOpened).toHaveBeenCalled();
});
```

**Step 2: 跑测试确认失败**

Run: `cd web && npx vitest run src/components/KbPanel.test.tsx`
Expected: FAIL

**Step 3: 实现**

```tsx
interface Props {
  activeCat: string;
  onCatChange: (cat: string) => void;
  openTarget?: { docId: string } | null;
  onOpened?: () => void;
}

const [pendingOpen, setPendingOpen] = useState<string | null>(null);

// 1) 收到跳转请求：复位搜索并回到「全部」分类（否则目标文档可能不在列表里）
useEffect(() => {
  if (!openTarget?.docId) return;
  setSearch("");
  if (activeCat !== "all") onCatChange("all");
  setPendingOpen(openTarget.docId);
}, [openTarget]);

// 2) 列表就绪且含目标文档时再展开（详情渲染挂在列表卡片内）
useEffect(() => {
  if (!pendingOpen || loadingDocs) return;
  if (!docs.some((d) => d.id === pendingOpen)) return;
  void toggleDetail(pendingOpen);
  setPendingOpen(null);
  onOpened?.();
}, [pendingOpen, docs, loadingDocs]);
```

**Step 4: 跑测试确认通过**

Run: `cd web && npx vitest run src/components/KbPanel.test.tsx`
Expected: PASS

**Step 5: 提交**

```bash
git add web/src/components/KbPanel.tsx web/src/components/KbPanel.test.tsx
git commit -m "feat(web): 文档引用跳转——知识库面板复位过滤并展开目标文档详情"
```

---

## Task 8: 全量验收 + 记录

**Step 1: 后端全量**

Run: `cd backend && .venv/Scripts/python.exe -m pytest && .venv/Scripts/ruff.exe check .`
Expected: 全绿、覆盖率 ≥ 80%、ruff 无输出

**Step 2: 前端全量**

Run: `cd web && npm test && npm run build`
Expected: 全绿、`tsc -b && vite build` 零错误

**Step 3: 记录（`private-docs` 工作区）**

在 `../copilot-lite-private/docs/优化落地记录.md` 追加 R3 小节（改动文件 / 原理 / 踩坑 / 测试结果 / 面试一句话话术），并更新 `OPTIMIZATION_PLAN.md` §13 勾选 R3、§1 进度表 M5 状态、§12 推送待批准项。

**Step 4: 提交（各自分支）**

```bash
cd ../copilot-lite-private && git add docs/ && git commit -m "docs: R3 引用来源标注落地记录——连接器身份 seam 与前端跳转接线"
cd ../../copilot-lite && git add -A && git commit -m "docs(plan): R3 完成——路线图勾选与基线数字更新"
```

> 合并/推送需维护者明确批准（AGENTS §11）。

---

## 验收清单（AGENTS §20/§21）

- [ ] 一个提交 = 一个问题，commit message 符合 §3
- [ ] 后端覆盖率 ≥80%、ruff 全过；前端 test/build 全过
- [ ] 无新增配置项（§7 三件套不适用）；无迁移（§13 不适用）
- [ ] 安全红线：跨用户身份不泄露（§6.3）、软删页面不返回身份（§13）、无物理删除（§6.11）
- [ ] 后台任务/全局状态无新增（§8）；连接器故障降级不拖垮主链路（§10）
- [ ] 契约新增字段为可选，旧数据兼容；无 `dangerouslySetInnerHTML` 新增（§5）
