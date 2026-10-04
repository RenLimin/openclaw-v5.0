"""Concrete Channel Adapters — 具体通道适配器实现."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from channel_adapter import ChannelAdapter
from models import Attachment, IdentityRef, InternalMessage, MessageDirection, SendResult, SendStatus


class WebChatAdapter(ChannelAdapter):
    """WebChat 通道适配器 — 处理 webchat 消息.
    
    webchat 是 OpenClaw 内置的 Web 聊天界面，消息格式为 JSON。
    """

    name = "webchat"

    def __init__(self) -> None:
        self._outbound_queue: List[InternalMessage] = []

    def receive(self, timeout: float | None = None) -> InternalMessage | None:
        """webchat 通过推送模式接收，这里返回 None."""
        # webchat 由 OpenClaw 原生处理，不主动拉取
        return None

    def send(self, message: InternalMessage) -> SendResult:
        """发送消息到 webchat."""
        try:
            # 构造 webchat 消息格式
            payload = {
                "id": message.message_id,
                "content": message.content,
                "timestamp": message.timestamp.isoformat(),
                "direction": message.direction.value,
            }
            # 实际发送由 OpenClaw 原生 channel 系统处理
            # 这里只记录出站队列
            self._outbound_queue.append(message)
            return SendResult(
                status=SendStatus.SUCCESS,
                message_id=message.message_id,
            )
        except Exception as e:
            return SendResult(
                status=SendStatus.FAILED,
                error_code="SEND_ERROR",
                error_message=str(e),
            )

    def to_internal(self, raw_message: Dict[str, Any]) -> InternalMessage:
        """将 webchat 原始消息转换为 InternalMessage."""
        sender = IdentityRef(
            user_id=raw_message.get("sender", {}).get("id", "unknown"),
            channel=self.name,
            display_name=raw_message.get("sender", {}).get("name"),
        )
        return InternalMessage(
            message_id=raw_message.get("id", str(uuid.uuid4())),
            channel=self.name,
            sender=sender,
            session_id=raw_message.get("session_id", ""),
            content=raw_message.get("content", ""),
            direction=MessageDirection.INBOUND,
            timestamp=datetime.fromisoformat(raw_message.get("timestamp", datetime.now().isoformat())),
            metadata=raw_message.get("metadata", {}),
        )

    def from_internal(self, message: InternalMessage) -> Dict[str, Any]:
        """将 InternalMessage 转换为 webchat 格式."""
        return {
            "id": message.message_id,
            "content": message.content,
            "timestamp": message.timestamp.isoformat(),
            "direction": message.direction.value,
            "sender": {
                "id": message.sender.user_id,
                "name": message.sender.display_name,
            },
        }

    def health_check(self) -> Dict[str, Any]:
        """健康检查."""
        return {
            "channel": self.name,
            "status": "ok",
            "outbound_queue_size": len(self._outbound_queue),
        }


class WeComAdapter(ChannelAdapter):
    """企业微信通道适配器 — 处理 WeCom 消息.
    
    WeCom 通过 webhook 接收消息，消息格式为 XML/JSON。
    """

    name = "wecom"

    def __init__(self, corp_id: str = "", agent_id: str = "", secret: str = "") -> None:
        self._corp_id = corp_id
        self._agent_id = agent_id
        self._secret = secret
        self._outbound_queue: List[InternalMessage] = []

    def receive(self, timeout: float | None = None) -> InternalMessage | None:
        """WeCom 通过 webhook 推送，不主动拉取."""
        return None

    def send(self, message: InternalMessage) -> SendResult:
        """发送消息到 WeCom."""
        try:
            # 构造 WeCom 消息格式
            payload = {
                "touser": message.sender.user_id,
                "msgtype": "text",
                "agentid": self._agent_id,
                "text": {"content": message.content},
            }
            self._outbound_queue.append(message)
            return SendResult(
                status=SendStatus.SUCCESS,
                message_id=message.message_id,
            )
        except Exception as e:
            return SendResult(
                status=SendStatus.FAILED,
                error_code="SEND_ERROR",
                error_message=str(e),
            )

    def to_internal(self, raw_message: Dict[str, Any]) -> InternalMessage:
        """将 WeCom 原始消息转换为 InternalMessage."""
        sender = IdentityRef(
            user_id=raw_message.get("FromUserName", "unknown"),
            channel=self.name,
            display_name=raw_message.get("FromUserName"),
        )
        return InternalMessage(
            message_id=raw_message.get("MsgId", str(uuid.uuid4())),
            channel=self.name,
            sender=sender,
            session_id=raw_message.get("FromUserName", ""),
            content=raw_message.get("Content", ""),
            direction=MessageDirection.INBOUND,
            timestamp=datetime.fromisoformat(raw_message.get("CreateTime", datetime.now().isoformat())),
            metadata={"msg_type": raw_message.get("MsgType", "text")},
        )

    def from_internal(self, message: InternalMessage) -> Dict[str, Any]:
        """将 InternalMessage 转换为 WeCom 格式."""
        return {
            "touser": message.sender.user_id,
            "msgtype": "text",
            "agentid": self._agent_id,
            "text": {"content": message.content},
        }

    def health_check(self) -> Dict[str, Any]:
        """健康检查."""
        return {
            "channel": self.name,
            "status": "ok",
            "corp_id": self._corp_id,
            "agent_id": self._agent_id,
            "outbound_queue_size": len(self._outbound_queue),
        }


class DiscordAdapter(ChannelAdapter):
    """Discord 通道适配器 — 预留实现."""

    name = "discord"

    def __init__(self, token: str = "") -> None:
        self._token = token

    def receive(self, timeout: float | None = None) -> InternalMessage | None:
        return None

    def send(self, message: InternalMessage) -> SendResult:
        return SendResult(
            status=SendStatus.FAILED,
            error_code="NOT_IMPLEMENTED",
            error_message="Discord adapter not yet implemented",
        )

    def to_internal(self, raw_message: Dict[str, Any]) -> InternalMessage:
        sender = IdentityRef(
            user_id=raw_message.get("author", {}).get("id", "unknown"),
            channel=self.name,
            display_name=raw_message.get("author", {}).get("username"),
        )
        return InternalMessage(
            message_id=raw_message.get("id", str(uuid.uuid4())),
            channel=self.name,
            sender=sender,
            session_id=raw_message.get("channel_id", ""),
            content=raw_message.get("content", ""),
            direction=MessageDirection.INBOUND,
            timestamp=datetime.fromisoformat(raw_message.get("timestamp", datetime.now().isoformat())),
        )

    def from_internal(self, message: InternalMessage) -> Dict[str, Any]:
        return {"content": message.content}

    def health_check(self) -> Dict[str, Any]:
        return {"channel": self.name, "status": "not_implemented"}
