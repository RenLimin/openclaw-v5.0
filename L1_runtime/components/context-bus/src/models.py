"""Context Bus — 事件与上下文数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional
import uuid


@dataclass
class BusContext:
    """总线上下文 — 随每条消息传播的元信息。

    用于：
    - 分布式追踪（trace_id）
    - 会话关联（session_id）
    - 用户身份（user_id）
    - 请求链路（request_id）
    """
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str | None = None
    user_id: str | None = None
    request_id: str | None = None
    parent_event_id: str | None = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "request_id": self.request_id,
            "parent_event_id": self.parent_event_id,
            "extra": self.extra,
        }

    def copy(self, **overrides) -> "BusContext":
        """复制上下文并覆盖指定字段。"""
        data = self.to_dict()
        data.update(overrides)
        return BusContext(**data)


@dataclass
class BusEvent:
    """总线上的标准事件。"""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = "generic"          # 事件类型：tool.call / session.start / error.occur ...
    topic: str = "system.generic"        # 主题（用于 pub/sub 路由）
    source: str = "unknown"              # 来源组件
    payload: Dict[str, Any] = field(default_factory=dict)
    context: BusContext = field(default_factory=BusContext)
    timestamp: datetime = field(default_factory=datetime.now)
    reply_to: str | None = None          # 用于 request/reply 模式

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "topic": self.topic,
            "source": self.source,
            "payload": self.payload,
            "context": self.context.to_dict(),
            "timestamp": self.timestamp.isoformat(),
            "reply_to": self.reply_to,
        }

    @classmethod
    def create(cls, event_type: str, topic: str, source: str,
               payload: Dict[str, Any] | None = None,
               context: BusContext | None = None) -> "BusEvent":
        """便捷创建事件。"""
        return cls(
            event_type=event_type,
            topic=topic,
            source=source,
            payload=payload or {},
            context=context or BusContext(),
        )
