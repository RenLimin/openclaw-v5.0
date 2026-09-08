#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EventBus — 模块间解耦通信
支持发布订阅、事件持久化
"""

from dataclasses import dataclass
from typing import List, Dict, Callable, Any
import logging
import datetime

logger = logging.getLogger(__name__)

@dataclass
class Event:
    """事件实例"""
    event_type: str
    payload: Dict[str, Any]
    created_at: datetime.datetime = None
    entity_type: str = None
    entity_id: str = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.datetime.now()

class EventBus:
    """事件总线"""

    def __init__(self):
        self._subscribers: Dict[str, List[Callable[[Event], None]]] = {}
        self._history: List[Event] = []

    def subscribe(self, event_type: str, handler: Callable[[Event], None]) -> None:
        """订阅一个事件"""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)
        logger.debug(f"Subscribed to event: {event_type}")

    def unsubscribe(self, event_type: str, handler: Callable[[Event], None]) -> None:
        """取消订阅"""
        if event_type not in self._subscribers:
            return
        if handler in self._subscribers[event_type]:
            self._subscribers[event_type].remove(handler)
            logger.debug(f"Unsubscribed from event: {event_type}")

    def publish(self, event: Event) -> None:
        """发布一个事件"""
        self._history.append(event)
        if event.event_type not in self._subscribers:
            logger.debug(f"No subscribers for event: {event.event_type}")
            return
        for handler in self._subscribers[event.event_type]:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Error handling event {event.event_type}: {e}", exc_info=True)
        logger.debug(f"Published event: {event.event_type}")

    def publish_simple(self, event_type: str, payload: Dict[str, Any] = None,
                      entity_type: str = None, entity_id: str = None) -> None:
        """简化发布接口"""
        event = Event(
            event_type=event_type,
            payload=payload or {},
            entity_type=entity_type,
            entity_id=entity_id
        )
        self.publish(event)

    def get_history(self, entity_type: str = None, entity_id: str = None) -> List[Event]:
        """获取事件历史，可以按实体过滤"""
        result = []
        for event in self._history:
            if entity_type is not None and event.entity_type != entity_type:
                continue
            if entity_id is not None and event.entity_id != entity_id:
                continue
            result.append(event)
        return result

    def clear_history(self) -> None:
        """清空历史"""
        self._history.clear()
