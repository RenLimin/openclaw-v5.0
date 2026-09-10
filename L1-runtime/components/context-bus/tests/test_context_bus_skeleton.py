"""Context Bus — 骨架测试。"""

import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from models import BusEvent, BusContext
from bus import ContextBus


class TestBusContext:
    def test_default_trace_id(self):
        ctx = BusContext()
        assert ctx.trace_id is not None
        assert len(ctx.trace_id) > 0

    def test_copy_with_overrides(self):
        ctx = BusContext(session_id="s1", user_id="u1")
        ctx2 = ctx.copy(user_id="u2")
        assert ctx2.session_id == "s1"  # 保留
        assert ctx2.user_id == "u2"     # 覆盖
        assert ctx.user_id == "u1"      # 原对象不变

    def test_to_dict(self):
        ctx = BusContext(session_id="s1")
        d = ctx.to_dict()
        assert "trace_id" in d
        assert d["session_id"] == "s1"
        assert isinstance(d["extra"], dict)


class TestBusEvent:
    def test_create_factory(self):
        ev = BusEvent.create("tool.call", "tool.exec", "test-agent",
                             payload={"cmd": "ls"})
        assert ev.event_type == "tool.call"
        assert ev.topic == "tool.exec"
        assert ev.payload["cmd"] == "ls"
        assert ev.context.trace_id is not None

    def test_to_dict(self):
        ev = BusEvent.create("test.event", "test", "source")
        d = ev.to_dict()
        assert d["event_type"] == "test.event"
        assert "context" in d
        assert "timestamp" in d


class TestContextBusABC:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            ContextBus()

    def test_has_pubsub_methods(self):
        for m in ["publish", "subscribe", "unsubscribe"]:
            assert hasattr(ContextBus, m), f"Missing {m}"

    def test_has_request_methods(self):
        for m in ["request", "reply"]:
            assert hasattr(ContextBus, m), f"Missing {m}"

    def test_has_context_methods(self):
        for m in ["get_current_context", "set_current_context", "update_context"]:
            assert hasattr(ContextBus, m), f"Missing {m}"

    def test_has_stats_methods(self):
        for m in ["list_subscriptions", "stats"]:
            assert hasattr(ContextBus, m), f"Missing {m}"
