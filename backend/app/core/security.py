"""安全模块：密码哈希（PBKDF2）+ JWT 签发/验证。

选型说明（面试可讲）：
- PBKDF2-HMAC-SHA256：标准库实现（hashlib），10 万次迭代，无额外依赖、
  无 passlib 维护问题；盐随机生成，防彩虹表；
- JWT：无状态认证，pyjwt 实现 HS256，令牌携带用户 id 与过期时间。
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import settings

# PBKDF2 迭代次数（OWASP 建议 60 万+，开发用 10 万兼顾速度）
_ITERATIONS = 100_000
_TOKEN_TTL_HOURS = 24


# ---------------- 密码哈希 ----------------

def hash_password(password: str) -> str:
    """生成带盐的 PBKDF2 哈希。格式：pbkdf2_sha256$iter$salt$digest"""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), _ITERATIONS
    ).hex()
    return f"pbkdf2_sha256${_ITERATIONS}${salt}${digest}"


def verify_password(password: str, hashed: str) -> bool:
    """校验密码；使用常量时间比较防时序攻击。"""
    try:
        _algo, iters, salt, digest = hashed.split("$")
        calc = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt.encode(), int(iters)
        ).hex()
        return secrets.compare_digest(calc, digest)
    except (ValueError, TypeError):
        return False


# ---------------- JWT ----------------

def create_token(user_id, token_version: int = 0) -> str:
    """为用户签发 JWT（24 小时有效，携带 token 版本号）。"""
    payload = {
        "sub": str(user_id),
        "ver": token_version,
        "exp": datetime.now(UTC) + timedelta(hours=_TOKEN_TTL_HOURS),
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> tuple[str, int]:
    """解析 JWT，返回 (用户 id, token 版本)；无效/过期抛异常。"""
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    return payload["sub"], int(payload.get("ver", 0))
