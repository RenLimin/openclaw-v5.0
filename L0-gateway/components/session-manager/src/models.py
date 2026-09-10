"""Session Manager — 会话数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict


class SessionStatus(str, Enum):
    """会话状态枚举。"""
    CREATING = "creating"
    ACTIVE = "active"
    IDLE = "idle"
    ARCHIVED = "archived"
    DELETED = "deleted"


# 合法状态流转
VALID_TRANSITIONS: Dict[SessionStatus, set[SessionStatus]] = {
    SessionStatus.CREATING: {SessionStatus.ACTIVE},
    SessionStatus.ACTIVE: {SessionStatus.IDLE, SessionStatus.ARCHIVED, SessionStatus.DELETED},
    SessionStatus.IDLE: {SessionStatus.ACTIVE, SessionStatus.ARCHIVED, SessionStatus.DELETED},
    SessionStatus.ARCHIVED: {SessionStatus.ACTIVE, SessionStatus.DELETED},
    SessionStatus.DELETED: set(),
}


@dataclass
class Session:
    """会话数据模型。

    一次用户与 Agent 的交互会话，绑定一个通道 + 一个用户。
    """
    session_id: str
    channel: str
    user_id: str
    status: SessionStatus = SessionStatus.CREATING
    created_at: datetime = field(default_factory=datetime.now)
    last_active_at: datetime = field(default_factory=datetime.now)
    context_ref: str | None = None     # 传给 L1 的 memory scope 或 session id
    title: str | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_active(self) -> bool:
        return self.status == SessionStatus.ACTIVE

    def is_idle_for(self, seconds: int) -> bool:
        """检查是否空闲超过指定秒数。"""
        if self.status not in (SessionStatus.ACTIVE, SessionStatus.IDLE):
            return False
        return (datetime.now() - self.last_active_at) > timedelta(seconds=seconds)

    def can_transition_to(self, new_status: SessionStatus) -> bool:
        """检查是否可以从当前状态流转到目标状态。"""
        return new_status in VALID_TRANSITIONS.get(self.status, set())

    def transition_to(self, new_status: SessionStatus) -> None:
        """执行状态流转。

        Raises:
            ValueError: 状态流转不合法
        """
        if not self.can_transition_to(new_status):
            raise ValueError(
                f"Invalid session state transition: {self.status} → {new_status}"
            )
        self.status = new_status

    def touch(self) -> None:
        """更新最后活跃时间。"""
        self.last_active_at = datetime.now()
        if self.status == SessionStatus.IDLE:
            self.status = SessionStatus.ACTIVE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "channel": self.channel,
            "user_id": self.user_id,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "last_active_at": self.last_active_at.isoformat(),
            "context_ref": self.context_ref,
            "title": self.title,
            "metadata": self.metadata,
        }
