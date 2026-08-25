"""全局常量。"""

import uuid

# P1 简化：单用户模式使用的固定默认用户
# （用户体系/认证将在后续里程碑引入，届时替换为真实用户）
DEFAULT_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
DEFAULT_USERNAME = "default"
