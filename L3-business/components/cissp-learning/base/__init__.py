"""基础层：BaseModel + BaseRepository + 多租户上下文。

从 health-engine 复制并保持接口一致，确保 L3 各组件架构统一。
生产环境可替换为 SQLAlchemy / MongoDB 实现，接口不变。
"""

from .base_model import (
    TenantModel,
    _current_tenant,
    set_current_tenant,
    reset_current_tenant,
    _current_tenant_var,
)
from .base_repository import BaseRepository

__all__ = [
    "TenantModel",
    "BaseRepository",
    "_current_tenant",
    "set_current_tenant",
    "reset_current_tenant",
    "_current_tenant_var",
]
