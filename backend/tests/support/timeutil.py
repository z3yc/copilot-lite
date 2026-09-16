"""测试用时间助手：构造 naive UTC 时间戳。

库里 `DateTime` 列存 naive（本地/测试/生产同构）；而 ruff 的 `DTZ001` 禁止不带
`tzinfo` 的 datetime 构造，故统一走本助手：显式给 UTC 再剥离时区。
"""

from datetime import UTC, datetime


def naive_utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    """构造 naive UTC 时间（等价于 `datetime.now(UTC).replace(tzinfo=None)` 的定点版）。"""
    return datetime(year, month, day, hour, minute, tzinfo=UTC).replace(tzinfo=None)
