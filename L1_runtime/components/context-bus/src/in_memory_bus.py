"""In-Memory Context Bus — 内存上下文总线实现."""

from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from models import BusContext, BusEvent

logger = logging.getLogger(__name__)


class InMemoryBus:
    """内存上下文总线实现.
    
    支持：
    - Pub/Sub 发布订阅（支持通配符 * 和 **）
    - Request/Response 同步请求响应
    - 上下文传播（线程本地存储）
    - 死信队列（处理失败的事件）
    """

    def __init__(self, max_dead_letter: int = 1000) -> None:
        self._subscriptions: Dict[str, Dict[str, Callable]] = {}
        self._lock = threading.Lock()
        self._thread_local = threading.local()
        self._events_published = 0
        self._events_handled = 0
        self._dead_letter: List[Dict[str, Any]] = []
        self._max_dead_letter = max_dead_letter
        # Request/Response 等待
        self._pending_requests: Dict[str, BusEvent] = {}
        self._request_events: Dict[str, threading.Event] = {}

    def publish(self, topic: str, event: BusEvent) -> None:
        """发布事件."""
        with self._lock:
            self._events_published += 1
            # 匹配订阅
            matched = False
            for pattern, handlers in self._subscriptions.items():
                if self._match_topic(pattern, topic):
                    matched = True
                    for sub_id, handler in handlers.items():
                        try:
                            handler(event)
                            self._events_handled += 1
                        except Exception as e:
                            logger.error(f"Handler error for {topic}: {e}")
                            self._dead_letter.append({
                                "topic": topic,
                                "event": event.to_dict(),
                                "error": str(e),
                                "timestamp": time.time(),
                            })
            # 检查 request/reply
            if event.reply_to and event.reply_to in self._pending_requests:
                self._pending_requests[event.reply_to] = event
                if event.reply_to in self._request_events:
                    self._request_events[event.reply_to].set()

    def subscribe(self, topic: str, handler: Callable[[BusEvent], None]) -> str:
        """订阅主题."""
        sub_id = str(uuid.uuid4())
        with self._lock:
            if topic not in self._subscriptions:
                self._subscriptions[topic] = {}
            self._subscriptions[topic][sub_id] = handler
        return sub_id

    def unsubscribe(self, subscription_id: str) -> bool:
        """取消订阅."""
        with self._lock:
            for topic, handlers in self._subscriptions.items():
                if subscription_id in handlers:
                    del handlers[subscription_id]
                    return True
        return False

    def request(self, topic: str, request: BusEvent, timeout: float = 30.0) -> BusEvent:
        """同步请求响应."""
        reply_event_id = str(uuid.uuid4())
        request.reply_to = reply_event_id
        event = threading.Event()
        with self._lock:
            self._request_events[reply_event_id] = event
            self._pending_requests[reply_event_id] = None
        self.publish(topic, request)
        if event.wait(timeout=timeout):
            response = self._pending_requests.pop(reply_event_id, None)
            self._request_events.pop(reply_event_id, None)
            if response is None:
                raise TimeoutError(f"No response for request {reply_event_id}")
            return response
        else:
            self._pending_requests.pop(reply_event_id, None)
            self._request_events.pop(reply_event_id, None)
            raise TimeoutError(f"Request timeout after {timeout}s")

    def reply(self, request: BusEvent, response: BusEvent) -> None:
        """回复请求."""
        if request.reply_to:
            self.publish(f"reply.{request.reply_to}", response)

    def get_current_context(self) -> BusContext:
        """获取当前线程上下文."""
        ctx = getattr(self._thread_local, "context", None)
        if ctx is None:
            ctx = BusContext()
            self._thread_local.context = ctx
        return ctx

    def set_current_context(self, context: BusContext) -> None:
        """设置当前线程上下文."""
        self._thread_local.context = context

    def update_context(self, **kwargs) -> BusContext:
        """更新当前上下文."""
        ctx = self.get_current_context()
        new_data = ctx.to_dict()
        new_data.update(kwargs)
        # 移除 extra 中的重复键
        extra = new_data.get("extra", {})
        extra.update(kwargs)
        new_data["extra"] = extra
        new_ctx = BusContext(**{k: v for k, v in new_data.items() if k != "extra"})
        new_ctx.extra = extra
        self._thread_local.context = new_ctx
        return new_ctx

    def list_subscriptions(self) -> List[Dict[str, str]]:
        """列出订阅."""
        result = []
        with self._lock:
            for topic, handlers in self._subscriptions.items():
                for sub_id in handlers:
                    result.append({
                        "subscription_id": sub_id,
                        "topic": topic,
                    })
        return result

    def stats(self) -> Dict[str, int]:
        """获取统计."""
        with self._lock:
            return {
                "events_published": self._events_published,
                "events_handled": self._events_handled,
                "active_subscriptions": sum(len(h) for h in self._subscriptions.values()),
                "dead_letter_count": len(self._dead_letter),
            }

    def get_dead_letter(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取死信."""
        return self._dead_letter[-limit:]

    def clear_dead_letter(self) -> int:
        """清空死信."""
        count = len(self._dead_letter)
        self._dead_letter.clear()
        return count

    def _match_topic(self, pattern: str, topic: str) -> bool:
        """通配符匹配."""
        # 精确匹配
        if pattern == topic:
            return True
        # ** 匹配任意层级
        if "**" in pattern:
            regex = pattern.replace("**", ".*")
            return bool(re.fullmatch(regex, topic))
        # * 匹配单层级
        if "*" in pattern:
            regex = pattern.replace("*", "[^.]+")
            return bool(re.fullmatch(regex, topic))
        return False


class ContextScope:
    """上下文作用域管理器.
    
    用法：
        with ContextScope(bus, trace_id="xxx", user_id="yyy"):
            # 此范围内的代码共享上下文
            ...
    """

    def __init__(self, bus: InMemoryBus, **kwargs) -> None:
        self._bus = bus
        self._kwargs = kwargs
        self._previous_context: Optional[BusContext] = None

    def __enter__(self) -> BusContext:
        self._previous_context = self._bus.get_current_context()
        new_context = self._previous_context.copy(**self._kwargs)
        self._bus.set_current_context(new_context)
        return new_context

    def __exit__(self, *args) -> None:
        if self._previous_context is not None:
            self._bus.set_current_context(self._previous_context)
