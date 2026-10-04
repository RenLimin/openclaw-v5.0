"""Router implementation — 消息路由具体实现."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from channel_adapter import ChannelAdapter
from models import InternalMessage, MessageDirection, RouteTarget

logger = logging.getLogger(__name__)


class MessageRouter:
    """消息路由器实现.
    
    负责：
    - 通道适配器注册与发现
    - 入站消息路由到目标 Agent
    - 出站消息路由到目标通道
    """

    def __init__(self) -> None:
        self._adapters: Dict[str, ChannelAdapter] = {}
        self._default_target = RouteTarget(
            target_type="agent",
            target_id="main",
        )

    def register_adapter(self, name: str, adapter: ChannelAdapter) -> None:
        """注册通道适配器."""
        self._adapters[name] = adapter
        logger.info(f"Channel adapter registered: {name}")

    def unregister_adapter(self: str) -> None:
        """注销通道适配器."""
        if name in self._adapters:
            del self._adapters[name]
            logger.info(f"Channel adapter unregistered: {name}")

    def list_adapters(self) -> List[str]:
        """列出所有适配器."""
        return list(self._adapters.keys())

    def get_adapter(self, name: str) -> Optional[ChannelAdapter]:
        """按名称获取适配器."""
        return self._adapters.get(name)

    def route_inbound(self, message: InternalMessage) -> RouteTarget:
        """入站路由.
        
        根据消息通道和会话信息决定路由目标。
        默认路由到 main agent。
        """
        # 通道消息默认路由到 main agent
        return RouteTarget(
            target_type="agent",
            target_id="main",
            agent_id="main",
            metadata={
                "channel": message.channel,
                "session_id": message.session_id,
                "original_sender": message.sender.user_id,
            },
        )

    def route_outbound(
        self,
        message: InternalMessage,
        target: RouteTarget,
    ) -> ChannelAdapter:
        """出站路由.
        
        根据路由目标找到对应的通道适配器。
        """
        channel = message.channel
        adapter = self._adapters.get(channel)
        if adapter is None:
            raise ValueError(
                f"No adapter found for channel: {channel}. "
                f"Available: {list(self._adapters.keys())}"
            )
        return adapter

    def health_check(self) -> Dict[str, str]:
        """健康检查."""
        results: Dict[str, str] = {}
        for name, adapter in self._adapters.items():
            try:
                result = adapter.health_check()
                results[name] = result.get("status", "unknown")
            except Exception as e:
                results[name] = f"error: {e}"
        return results


class PriorityRouter(MessageRouter):
    """优先级路由器 — 根据消息优先级路由.
    
    高优先级消息路由到快速响应 agent，
    低优先级消息路由到普通 agent。
    """

    def __init__(self) -> None:
        super().__init__()
        self._priority_targets: Dict[str, RouteTarget] = {}

    def set_priority_target(self, priority: str, target: RouteTarget) -> None:
        """设置优先级路由目标."""
        self._priority_targets[priority] = target

    def route_inbound(self, message: InternalMessage) -> RouteTarget:
        """按优先级路由."""
        priority = message.metadata.get("priority", "normal")
        if priority in self._priority_targets:
            return self._priority_targets[priority]
        return super().route_inbound(message)
