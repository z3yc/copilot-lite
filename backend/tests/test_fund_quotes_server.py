"""MCP server 端：东财解析（MockTransport，不联网）+ 工具行为（进程内直测）。"""

import httpx
import pytest

from app.mcp_servers.fund_quotes.eastmoney import LSJZ_URL, EastmoneyProvider
from app.mcp_servers.fund_quotes.server import TOOL_NAME, build_server

_SAMPLE = {
    "Data": {
        "LSJZList": [
            {"FSRQ": "2026-09-15", "DWJZ": "1.2500", "JZZZL": "1.21"},
            {"FSRQ": "2026-09-14", "DWJZ": "1.2350", "JZZZL": "-1.52"},
        ],
        "TotalCount": 6007,
    },
    "ErrCode": 0,
    "ErrMsg": None,
}


@pytest.fixture
async def mock_client_factory():
    """用 MockTransport 造 httpx client（**不联网**），返回 (factory, requests)。"""
    requests: list[httpx.Request] = []
    clients: list[httpx.AsyncClient] = []

    def _make(handler) -> httpx.AsyncClient:
        def _record(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return handler(request)

        client = httpx.AsyncClient(transport=httpx.MockTransport(_record))
        clients.append(client)
        return client

    yield _make, requests
    for client in clients:
        await client.aclose()


async def test_parses_latest_and_previous_nav(mock_client_factory) -> None:
    make, requests = mock_client_factory

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith(LSJZ_URL)
        assert request.url.path.endswith("/f10/lsjz")
        assert request.url.params["fundCode"] == "000001"
        assert request.url.params["pageSize"] == "2"
        return httpx.Response(200, json=_SAMPLE)

    provider = EastmoneyProvider(client=make(handler))
    raw = await provider.fetch_nav("000001")
    assert raw == {
        "code": "000001",
        "nav": 1.25,
        "nav_date": "2026-09-15",
        "prev_nav": 1.235,
        "change_pct": 1.21,
    }
    assert len(requests) == 1  # 确实发过一次请求（且只走 MockTransport）


async def test_single_row_has_no_previous_nav(mock_client_factory) -> None:
    make, _ = mock_client_factory
    payload = {"Data": {"LSJZList": [_SAMPLE["Data"]["LSJZList"][0]]}, "ErrCode": 0}
    provider = EastmoneyProvider(
        client=make(lambda request: httpx.Response(200, json=payload))
    )
    raw = await provider.fetch_nav("000001")
    assert raw["nav"] == 1.25
    assert raw["prev_nav"] is None


async def test_empty_list_returns_none(mock_client_factory) -> None:
    make, _ = mock_client_factory
    provider = EastmoneyProvider(
        client=make(lambda request: httpx.Response(200, json={"Data": {"LSJZList": []}}))
    )
    assert await provider.fetch_nav("000001") is None


async def test_http_error_returns_none_and_warns(mock_client_factory, caplog) -> None:
    make, _ = mock_client_factory
    provider = EastmoneyProvider(
        client=make(lambda request: httpx.Response(500, text="boom"))
    )
    with caplog.at_level("WARNING"):
        assert await provider.fetch_nav("000001") is None
    assert "行情取数失败" in caplog.text


async def test_non_json_response_returns_none(mock_client_factory) -> None:
    make, _ = mock_client_factory
    provider = EastmoneyProvider(
        client=make(lambda request: httpx.Response(200, text="<html>not json</html>"))
    )
    assert await provider.fetch_nav("000001") is None


def _structured(result):
    """进程内直测的形状归一。

    `FastMCP.call_tool()` 直调返回 `(unstructured_content, structuredContent)` 二元组；
    而**走 stdio 协议时**低层 handler 会把同一对拆开，client 拿到的
    `CallToolResult.structuredContent` 就是纯 dict（由 Task 4 的客户端用例坐实）。
    """
    if isinstance(result, tuple):
        return result[1]
    return result


class _FakeProvider:
    """进程内 Fake 数据源（配合 build_server 直测工具行为）。"""

    def __init__(self, missing: set[str] | None = None) -> None:
        self.missing = missing or set()
        self.calls: list[str] = []

    async def fetch_nav(self, code: str):
        self.calls.append(code)
        if code in self.missing:
            return None
        return {
            "code": code,
            "nav": 1.25,
            "nav_date": "2026-09-15",
            "prev_nav": 1.235,
            "change_pct": 1.21,
        }


async def test_server_exposes_single_structured_tool() -> None:
    server = build_server(_FakeProvider())
    tools = await server.list_tools()
    assert [t.name for t in tools] == [TOOL_NAME]


async def test_tool_dedups_codes_and_reports_missing() -> None:
    provider = _FakeProvider(missing={"999999"})
    server = build_server(provider)
    result = _structured(
        await server.call_tool(TOOL_NAME, {"codes": ["000001", "999999", "000001"]})
    )
    assert result["missing"] == ["999999"]
    assert [q["code"] for q in result["quotes"]] == ["000001"]
    assert provider.calls == ["000001", "999999"]  # 去重后只取两次
