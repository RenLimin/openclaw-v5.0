"""Context Bus — 上下文总线抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Dict, List, Optional

from models import BusEvent, BusContext


class ContextBus(ABC):
    """上下文总线抽象基类。

    提供三种通信模式：
    1. Pub/Sub — 发布订阅（一对多，异步）
    2. Request/Response — 请求响应（一对一，同步/异步）
    3. Context Propagation — 上下文传播（trace/session/user）

    具体实现：
    - InMemoryBus — 内存实现（单进程）
    - RedisBus — Redis Pub/Sub（分布式）
    - KafkaBus — Kafka 流（高吞吐）
    """

    # ------------------------------------------------------------------
    # Pub/Sub
    # ------------------------------------------------------------------

    @abstractmethod
    def publish(self, topic: str, event: BusEvent) -> None:
        """发布事件到指定主题。

        Args:
            topic: 主题名（支持层级，如 "tool.call"）
            event: 事件对象
        """
        ...

    @abstractmethod
    def subscribe(self, topic: str, handler: Callable[[BusEvent], None]) -> str:
        """订阅一个主题。

        Args:
            topic: 主题名（支持通配符，如 "tool.*"）
            handler: 事件处理函数

        Returns:
            subscription_id — 用于取消订阅
        """
        ...

    @abstractmethod
    def unsubscribe(self, subscription_id: str) -> bool:
        """取消订阅。返回是否成功。"""
        ...

    # ------------------------------------------------------------------
    # Request / Response
    # ------------------------------------------------------------------

    @abstractmethod
    def request(self, topic: str, request: BusEvent,
                timeout: float = 30.0) -> BusEvent:
        """同步请求-响应模式。

        发布请求并等待响应，超时抛出异常。

        Args:
            topic: 请求主题
            request: 请求事件
            timeout: 超时秒数

        Returns:
            BusEvent — 响应事件

        Raises:
            TimeoutError: 超时未收到响应
        """
        ...

    @abstractmethod
    def reply(self, request: BusEvent, response: BusEvent) -> None:
        """回复一个请求。

        Args:
            request: 原始请求事件（含 reply_to）
            response: 响应事件
        """
        ...

    # ------------------------------------------------------------------
    # Context Management
    # ------------------------------------------------------------------

    @abstractmethod
    def get_current_context(self) -> BusContext:
        """获取当前线程/协程的上下文。"""
        ...

    @abstractmethod
    def set_current_context(self, context: BusContext) -> None:
        """设置当前上下文。"""
        ...

    @abstractmethod
    def update_context(self, **kwargs) -> BusContext:
        """更新当前上下文字段，返回新的上下文。"""
        ...

    # ------------------------------------------------------------------
    # Admin / Stats
    # ------------------------------------------------------------------

    @abstractmethod
    def list_subscriptions(self) -> List[Dict[str, str]]:
        """列出所有订阅。"""
        ...

    @abstractmethod
    def stats(self) -> Dict[str, int]:
        """获取总线统计。

        Returns:
            {"events_published": N, "events_handled": N,
             "active_subscriptions": N, "dead_letter_count": N}
        """
        ...
