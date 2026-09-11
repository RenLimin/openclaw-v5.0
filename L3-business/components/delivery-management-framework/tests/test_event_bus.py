# -*- coding: utf-8 -*-
"""EventBus 事件总线测试。"""

import pytest
from event_bus.event_bus import EventBus, Event


class TestEvent:
    """Event 数据类测试。"""

    def test_event_creation(self):
        e = Event(event_type="project.created", payload={"id": "p1"})
        assert e.event_type == "project.created"
        assert e.payload == {"id": "p1"}
        assert e.created_at is not None

    def test_event_default_timestamp(self):
        """Event 应自动设置 created_at。"""
        e = Event(event_type="test", payload={})
        assert e.created_at is not None

    def test_event_with_entity_ref(self):
        """Event 可携带实体引用信息。"""
        e = Event(
            event_type="work_item.status_changed",
            payload={"old": "draft", "new": "active"},
            entity_type="WorkItem",
            entity_id="wi-1",
        )
        assert e.entity_type == "WorkItem"
        assert e.entity_id == "wi-1"


class TestEventBus:
    """EventBus 核心功能测试。"""

    def setup_method(self):
        self.bus = EventBus()

    def test_subscribe_and_publish(self):
        """订阅者应能收到已发布事件。"""
        received = []
        self.bus.subscribe("test.event", lambda e: received.append(e))
        self.bus.publish(Event(event_type="test.event", payload={"x": 1}))
        assert len(received) == 1
        assert received[0].payload == {"x": 1}

    def test_multiple_subscribers(self):
        """多个订阅者应都收到事件。"""
        r1, r2 = [], []
        self.bus.subscribe("evt", lambda e: r1.append(e))
        self.bus.subscribe("evt", lambda e: r2.append(e))
        self.bus.publish(Event(event_type="evt", payload={}))
        assert len(r1) == 1
        assert len(r2) == 1

    def test_no_subscribers_silent(self):
        """无订阅者时发布不应报错。"""
        self.bus.publish(Event(event_type="nobody.listens", payload={}))

    def test_unsubscribe(self):
        """取消订阅后不应再收到事件。"""
        received = []
        handler = lambda e: received.append(e)
        self.bus.subscribe("evt", handler)
        self.bus.unsubscribe("evt", handler)
        self.bus.publish(Event(event_type="evt", payload={}))
        assert len(received) == 0

    def test_publish_simple(self):
        """publish_simple 应简化发布接口。"""
        received = []
        self.bus.subscribe("simple", lambda e: received.append(e))
        self.bus.publish_simple("simple", {"key": "val"}, entity_type="P", entity_id="1")
        assert len(received) == 1
        assert received[0].payload == {"key": "val"}
        assert received[0].entity_type == "P"
        assert received[0].entity_id == "1"

    def test_history_records_all_published(self):
        """所有发布的事件应记录到历史。"""
        self.bus.publish(Event(event_type="a", payload={}))
        self.bus.publish(Event(event_type="b", payload={}))
        history = self.bus.get_history()
        assert len(history) == 2

    def test_history_filter_by_entity(self):
        """历史应支持按实体类型过滤。"""
        self.bus.publish(Event(event_type="x", payload={}, entity_type="Project", entity_id="p1"))
        self.bus.publish(Event(event_type="y", payload={}, entity_type="WorkItem", entity_id="wi1"))
        self.bus.publish(Event(event_type="z", payload={}, entity_type="Project", entity_id="p2"))
        result = self.bus.get_history(entity_type="Project")
        assert len(result) == 2

    def test_history_filter_by_entity_id(self):
        """历史应支持按实体 ID 过滤。"""
        self.bus.publish(Event(event_type="x", payload={}, entity_type="Project", entity_id="p1"))
        self.bus.publish(Event(event_type="y", payload={}, entity_type="Project", entity_id="p2"))
        result = self.bus.get_history(entity_type="Project", entity_id="p1")
        assert len(result) == 1
        assert result[0].entity_id == "p1"

    def test_clear_history(self):
        """清空历史后应无记录。"""
        self.bus.publish(Event(event_type="x", payload={}))
        self.bus.clear_history()
        assert len(self.bus.get_history()) == 0

    def test_handler_exception_does_not_break_others(self):
        """某个订阅者异常不应影响其他订阅者。"""
        r_good = []

        def bad_handler(e):
            raise RuntimeError("订阅者异常")

        def good_handler(e):
            r_good.append(e)

        self.bus.subscribe("evt", bad_handler)
        self.bus.subscribe("evt", good_handler)
        # 不应抛异常
        self.bus.publish(Event(event_type="evt", payload={}))
        assert len(r_good) == 1

    def test_duplicate_unsubscribe_silent(self):
        """取消未订阅的处理函数不应报错。"""
        self.bus.unsubscribe("nonexistent", lambda e: None)
