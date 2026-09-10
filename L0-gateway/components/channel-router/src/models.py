"""Channel Router — 统一数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


@dataclass
class Attachment:
    """消息附件。"""
    type: str                          # image / file / audio / video
    url: str | None = None
    path: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class IdentityRef:
    """身份引用（轻量，完整 Identity 见 auth-gateway）。"""
    user_id: str
    channel: str
    display_name: str | None = None


class MessageDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


@dataclass
class InternalMessage:
    """统一内部消息模型 — 所有通道的消息都转换为此格式。"""
    message_id: str
    channel: str
    sender: IdentityRef
    session_id: str
    content: str
    direction: MessageDirection = MessageDirection.INBOUND
    attachments: List[Attachment] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    reply_to: str | None = None         # 回复某条消息的 ID

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "channel": self.channel,
            "sender": {
                "user_id": self.sender.user_id,
                "channel": self.sender.channel,
                "display_name": self.sender.display_name,
            },
            "session_id": self.session_id,
            "content": self.content,
            "direction": self.direction.value,
            "attachments": [a.__dict__ for a in self.attachments],
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
            "reply_to": self.reply_to,
        }


@dataclass
class RouteTarget:
    """路由目标 — 消息应该被送到哪。"""
    target_type: str                    # agent / channel / user / broadcast
    target_id: str
    agent_id: str | None = None         # 如果 target_type == agent
    metadata: Dict[str, Any] = field(default_factory=dict)


class SendStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    QUEUED = "queued"
    RATE_LIMITED = "rate_limited"


@dataclass
class SendResult:
    """消息发送结果。"""
    status: SendStatus
    message_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == SendStatus.SUCCESS
