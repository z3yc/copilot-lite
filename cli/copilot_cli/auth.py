"""CLI 登录态管理：令牌持久化与请求头构造。

令牌来源优先级：环境变量 ``COPILOT_TOKEN`` > 凭据文件。
凭据默认存于 ``~/.copilot/credentials.json``（可用 ``COPILOT_CREDENTIALS`` 覆盖，
便于测试与多环境隔离），文件权限尽力收紧为仅属主可读。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# 环境变量名（测试/多环境可用）
CREDENTIALS_ENV = "COPILOT_CREDENTIALS"
TOKEN_ENV = "COPILOT_TOKEN"


def credentials_path() -> Path:
    """凭据文件路径（支持环境变量覆盖）。"""
    override = os.environ.get(CREDENTIALS_ENV)
    if override:
        return Path(override)
    return Path.home() / ".copilot" / "credentials.json"


def load_credentials() -> dict:
    """读取凭据；文件缺失/损坏时返回空 dict（不抛错）。"""
    try:
        data = json.loads(credentials_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_credentials(token: str, username: str | None = None) -> Path:
    """保存令牌到凭据文件，返回文件路径。"""
    path = credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, str] = {"token": token}
    if username:
        payload["username"] = username
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:  # Windows 下 chmod 语义有限，失败忽略，不影响登录
        path.chmod(0o600)
    except OSError:
        pass
    return path


def clear_credentials() -> bool:
    """删除本地凭据；不存在返回 False。"""
    try:
        credentials_path().unlink()
        return True
    except OSError:
        return False


def get_token() -> str | None:
    """获取当前令牌：环境变量优先，其次凭据文件。"""
    env = os.environ.get(TOKEN_ENV)
    if env:
        return env.strip() or None
    token = load_credentials().get("token")
    return token if isinstance(token, str) and token else None


def get_username() -> str | None:
    """获取已保存的用户名（仅用于展示）。"""
    name = load_credentials().get("username")
    return name if isinstance(name, str) and name else None


def auth_header() -> dict[str, str]:
    """构造 Authorization 请求头；未登录时返回空 dict。"""
    token = get_token()
    return {"Authorization": f"Bearer {token}"} if token else {}
