"""Channel Router — 消息路由组件。"""

from models import Attachment, IdentityRef, InternalMessage, MessageDirection, RouteTarget, SendResult, SendStatus
from channel_adapter import ChannelAdapter
from router import Router
from adapters import DiscordAdapter, WebChatAdapter, WeComAdapter

__all__ = [
    "ChannelAdapter", "Router",
    "InternalMessage", "SendResult", "SendStatus",
    "Attachment", "IdentityRef", "MessageDirection", "RouteTarget",
    "WebChatAdapter", "WeComAdapter", "DiscordAdapter",
]
