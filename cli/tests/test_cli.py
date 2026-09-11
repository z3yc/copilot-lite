"""CLI 登录态与命令测试（不触网：monkeypatch httpx / _request）。"""

import json

import httpx
import pytest
import typer
from typer.testing import CliRunner

from copilot_cli import auth
from copilot_cli.main import app


@pytest.fixture(autouse=True)
def isolated_credentials(tmp_path, monkeypatch):
    """凭据文件隔离到临时目录，避免污染真实用户目录。"""
    monkeypatch.setenv(auth.CREDENTIALS_ENV, str(tmp_path / "credentials.json"))
    monkeypatch.delenv(auth.TOKEN_ENV, raising=False)
    yield


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _resp(payload: dict, status: int = 200) -> httpx.Response:
    request = httpx.Request("GET", "http://test")
    return httpx.Response(status_code=status, json=payload, request=request)


# ---------------- auth 模块（纯函数） ----------------


def test_save_load_clear_roundtrip():
    auth.save_credentials("tok-123", "alice")
    assert auth.get_token() == "tok-123"
    assert auth.get_username() == "alice"
    assert auth.clear_credentials() is True
    assert auth.get_token() is None
    assert auth.clear_credentials() is False


def test_env_token_takes_priority(monkeypatch):
    auth.save_credentials("file-tok", "alice")
    monkeypatch.setenv(auth.TOKEN_ENV, "env-tok")
    assert auth.get_token() == "env-tok"
    assert auth.auth_header() == {"Authorization": "Bearer env-tok"}


def test_auth_header_empty_when_logged_out():
    assert auth.auth_header() == {}


def test_corrupted_credentials_returns_empty(tmp_path, monkeypatch):
    path = tmp_path / "credentials.json"
    path.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv(auth.CREDENTIALS_ENV, str(path))
    assert auth.load_credentials() == {}
    assert auth.get_token() is None


def test_request_injects_bearer_token(monkeypatch):
    captured: dict = {}

    def fake_request(method, url, timeout=120, headers=None, **kwargs):
        captured.update(headers or {})
        captured["url"] = url
        return _resp({"ok": True})

    monkeypatch.setattr("copilot_cli.main.httpx.request", fake_request)
    auth.save_credentials("abc", "alice")

    from copilot_cli.main import _request

    assert _request("GET", "/api/v1/todos") == {"ok": True}
    assert captured["Authorization"] == "Bearer abc"
    assert captured["url"].endswith("/api/v1/todos")


def test_request_401_gives_login_hint(monkeypatch, runner):
    def fake_request(method, url, timeout=120, headers=None, **kwargs):
        return _resp({"detail": "未登录"}, status=401)

    monkeypatch.setattr("copilot_cli.main.httpx.request", fake_request)
    result = runner.invoke(app, ["todo", "list"])
    assert result.exit_code != 0
    assert "copilot login" in result.output


# ---------------- 命令 ----------------


def test_login_saves_token(monkeypatch, runner):
    monkeypatch.setattr(
        "copilot_cli.main._request",
        lambda *a, **k: {"token": "tok-login", "user": {"username": "alice"}},
    )
    result = runner.invoke(app, ["login", "-u", "alice"], input="secret\n")
    assert result.exit_code == 0, result.output
    assert auth.get_token() == "tok-login"
    assert auth.get_username() == "alice"


def test_login_when_already_logged_in(runner):
    auth.save_credentials("existing", "alice")
    result = runner.invoke(app, ["login", "-u", "bob"])
    assert result.exit_code == 0
    assert "已登录" in result.output
    assert auth.get_token() == "existing"


def test_logout_removes_token(runner):
    auth.save_credentials("tok", "alice")
    result = runner.invoke(app, ["logout"])
    assert result.exit_code == 0
    assert auth.get_token() is None
    assert "已退出登录" in result.output


def test_whoami_when_logged_out(runner):
    result = runner.invoke(app, ["whoami"])
    assert result.exit_code == 0
    assert "未登录" in result.output


def test_whoami_when_logged_in(monkeypatch, runner):
    auth.save_credentials("tok", "alice")
    monkeypatch.setattr(
        "copilot_cli.main._request",
        lambda *a, **k: {"id": "12345678-0000", "username": "alice", "role": "user"},
    )
    result = runner.invoke(app, ["whoami"])
    assert result.exit_code == 0
    assert "alice" in result.output


def test_credentials_file_is_valid_json():
    path = auth.save_credentials("tok", "alice")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == {"token": "tok", "username": "alice"}


def test_request_unwraps_envelope(monkeypatch):
    """统一响应结构：成功时解包 data。"""

    def fake_request(method, url, timeout=120, headers=None, **kwargs):
        return _resp({"code": 0, "message": "ok", "data": {"reply": "hi"}})

    monkeypatch.setattr("copilot_cli.main.httpx.request", fake_request)
    from copilot_cli.main import _request

    assert _request("POST", "/api/v1/chat") == {"reply": "hi"}


def test_request_raises_on_error_envelope(monkeypatch):
    """统一响应结构：code!=0 抛出 message。"""

    def fake_request(method, url, timeout=120, headers=None, **kwargs):
        return _resp({"code": 2001, "message": "会话不存在", "data": None})

    monkeypatch.setattr("copilot_cli.main.httpx.request", fake_request)
    from copilot_cli.main import _request

    with pytest.raises(typer.Exit):
        _request("GET", "/api/v1/sessions/x")


def test_error_envelope_message_shown(monkeypatch, runner):
    def fake_request(method, url, timeout=120, headers=None, **kwargs):
        return _resp({"code": 2001, "message": "会话不存在", "data": None})

    monkeypatch.setattr("copilot_cli.main.httpx.request", fake_request)
    result = runner.invoke(app, ["todo", "list"])
    assert result.exit_code != 0
    assert "会话不存在" in result.output
