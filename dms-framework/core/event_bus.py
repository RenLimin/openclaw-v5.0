"""
core/event_bus.py — 事件总线
模块间解耦通信：发布/订阅 + 历史回溯 + 模式匹配。
"""
from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Event — 事件对象
# ---------------------------------------------------------------------------

@dataclass
class Event:
    """事件对象。

    name: 点分路径，如 "project.created" / "work_item.status_changed"
    payload: 事件数据，必须可序列化（dict 基础类型）
    source: 发出事件的模块名，用于追踪
    entity_type / entity_id: 可选，关联的业务实体
    """

    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = ""
    entity_type: str = ""
    entity_id: str = ""


# ---------------------------------------------------------------------------
# EventBus — 发布订阅
# ---------------------------------------------------------------------------

class EventBus:
    """事件总线：支持 glob 模式订阅 + 历史记录。

    设计原则：
    - 同步发布（当前线程直接调用 handler），简单可靠
    - 订阅模式支持 fnmatch 通配符，如 "project.*" / "*.status_changed"
    - 历史记录保留最近 N 条，便于审计和回放
    - 事件发布不会因单个 handler 异常中断其他 handler
    """

    # 预定义事件 — 框架核心生命周期事件
    PREDEFINED_EVENTS: list[str] = [
        "project.created",
        "project.status_changed",
        "work_item.created",
        "work_item.status_changed",
        "work_item.assigned",
        "deliverable.accepted",
        "deliverable.rejected",
        "risk.occurred",
        "risk.mitigated",
        "milestone.reached",
        "milestone.missed",
        "member.assigned",
        "member.removed",
        "tenant.created",
        "schema.migrated",
    ]

    def __init__(self, max_history: int = 10000) -> None:
        self._subscribers: dict[str, list[Callable[[Event], None]]] = {}
        self._history: list[Event] = []
        self._max_history = max_history
        self._publishing: bool = False
        self._pending: list[Event] = []

    # -- 订阅 --------------------------------------------------------------

    def subscribe(self, pattern: str, handler: Callable[[Event], None]) -> None:
        """订阅事件模式。pattern 支持 fnmatch 通配符。"""
        if pattern not in self._subscribers:
            self._subscribers[pattern] = []
        self._subscribers[pattern].append(handler)

    def unsubscribe(self, pattern: str, handler: Callable[[Event], None]) -> None:
        """取消订阅。"""
        if pattern in self._subscribers:
            self._subscribers[pattern] = [
                h for h in self._subscribers[pattern] if h is not handler
            ]

    # -- 发布 --------------------------------------------------------------

    def publish(
        self,
        name: str,
        payload: dict[str, Any] | None = None,
        source: str = "",
        entity_type: str = "",
        entity_id: str = "",
    ) -> None:
        """发布事件。匹配所有模式的 handler 会被依次调用。

        单个 handler 异常不影响其他 handler，异常会被捕获并跳过。
        递归发布安全：发布过程中新产生的事件排队，等当前发布完再处理。
        """
        event = Event(
            name=name,
            payload=payload or {},
            source=source,
            entity_type=entity_type,
            entity_id=entity_id,
        )

        # 历史记录
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        # 防递归：正在发布时，新事件入队
        if self._publishing:
            self._pending.append(event)
            return

        self._publishing = True
        try:
            self._dispatch(event)
            # 处理队列里的递归事件
            while self._pending:
                pending_event = self._pending.pop(0)
                self._dispatch(pending_event)
        finally:
            self._publishing = False

    def _dispatch(self, event: Event) -> None:
        for pattern, handlers in self._subscribers.items():
            if fnmatch.fnmatch(event.name, pattern):
                for handler in handlers:
                    try:
                        handler(event)
                    except Exception:
                        # 单个 handler 失败不影响总线
                        import traceback
                        traceback.print_exc()

    # -- 历史 --------------------------------------------------------------

    def get_history(
        self,
        entity_type: str | None = None,
        entity_id: str | None = None,
        event_pattern: str | None = None,
        limit: int = 100,
    ) -> list[Event]:
        """查询历史事件，支持多维度过滤。"""
        result = self._history
        if entity_type:
            result = [e for e in result if e.entity_type == entity_type]
        if entity_id:
            result = [e for e in result if e.entity_id == entity_id]
        if event_pattern:
            result = [e for e in result if fnmatch.fnmatch(e.name, event_pattern)]
        return result[-limit:]

    def clear_history(self) -> None:
        self._history.clear()

    # -- 统计 --------------------------------------------------------------

    def stats(self) -> dict[str, int]:
        return {
            "subscribers": sum(len(v) for v in self._subscribers.values()),
            "patterns": len(self._subscribers),
            "history_size": len(self._history),
        }
