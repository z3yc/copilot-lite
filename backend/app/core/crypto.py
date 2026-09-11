"""对称加密：用户模型 API Key 加密存储（Fernet，密钥派生自 SECRET_KEY）。

安全说明（AGENTS.md §6）：
- 明文 Key 只存在于请求处理内存，**加密后**才落库；
- 接口只回传掩码预览，日志不打印明文；
- 加密密钥派生自 `SECRET_KEY`——轮换 SECRET_KEY 会导致已存 Key 无法解密
  （届时需在页面重新填写）。
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(
        hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    )
    return Fernet(key)


def encrypt_secret(plain: str) -> str:
    """加密明文密钥，返回可存库的字符串。"""
    return _fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_secret(token: str) -> str:
    """解密；密钥轮换/数据损坏时返回空串（调用方回退环境变量）。"""
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        return ""


def mask_secret(plain: str) -> str:
    """掩码预览：sk-abc****wxyz；永不回传明文。"""
    if not plain:
        return ""
    if len(plain) <= 8:
        return "*" * len(plain)
    return f"{plain[:3]}****{plain[-4:]}"
