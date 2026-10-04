"""租户模型基类。

所有领域模型继承 TenantModel，自动获得：
- id（UUID hex）
- tenant_id（多租户隔离）
- created_at / updated_at（时间戳）
- is_deleted（软删除标记）
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ─── 多租户上下文 ────────────────────────────────────────────────

_current_tenant_var: ContextVar[Optional[str]] = ContextVar(
    "current_tenant", default=None
)


def _current_tenant() -> str:
    """获取当前租户 ID。未设置时抛出 RuntimeError。"""
    tenant = _current_tenant_var.get()
    if tenant is None:
        raise RuntimeError(
            "No tenant context set. Call set_current_tenant(tenant_id) first."
        )
    return tenant


def set_current_tenant(tenant_id: str) -> Any:
    """设置当前租户，返回 token 用于 reset。"""
    return _current_tenant_var.set(tenant_id)


def reset_current_tenant(token: Any) -> None:
    """重置租户上下文。"""
    _current_tenant_var.reset(token)


# ─── 租户模型基类 ────────────────────────────────────────────────

class TenantModel(BaseModel):
    """带租户隔离的领域模型基类。"""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    tenant_id: str = Field(default_factory=_current_tenant)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_deleted: bool = False

    model_config = {
        "from_attributes": True,
        "use_enum_values": False,
    }
