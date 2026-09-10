"""Auth Gateway — 身份与认证数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class AuthStatus(str, Enum):
    """认证结果状态。"""
    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"       # 需二次验证
    EXPIRED = "expired"


@dataclass
class Identity:
    """已认证身份。"""
    user_id: str
    channel: str
    roles: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    authenticated_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def has_role(self, role: str) -> bool:
        return role in self.roles

    def has_permission(self, perm: str) -> bool:
        return perm in self.permissions

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "channel": self.channel,
            "roles": self.roles,
            "permissions": self.permissions,
            "authenticated_at": self.authenticated_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "metadata": self.metadata,
        }


@dataclass
class AuthRequest:
    """认证请求。"""
    auth_type: str                 # signature / token / api_key / oauth
    channel: str
    credentials: Dict[str, Any]    # 认证凭据（签名/Token/Key 等）
    sender_ref: str                # 发送者标识
    request_id: str | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AuthResult:
    """认证结果。"""
    status: AuthStatus
    identity: Identity | None = None
    error_code: str | None = None
    error_message: str | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == AuthStatus.SUCCESS and self.identity is not None
