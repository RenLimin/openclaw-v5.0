"""Channel Router — 消息路由组件（骨架）。"""

from models import InternalMessage, RouteTarget, SendResult, Attachment
from router import Router
from channel_adapter import ChannelAdapter

__all__ = [
    "InternalMessage",
    "RouteTarget",
    "SendResult",
    "Attachment",
    "Router",
    "ChannelAdapter",
]
