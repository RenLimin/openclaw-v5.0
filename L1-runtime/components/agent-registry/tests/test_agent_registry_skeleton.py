"""Agent Registry — 骨架测试。"""

import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from models import AgentSpec, AgentHandle, AgentStatus
from registry import AgentRegistry


class TestAgentSpec:
    def test_creation_defaults(self):
        spec = AgentSpec(agent_id="test-agent", name="Test", description="Test agent")
        assert spec.agent_id == "test-agent"
        assert spec.version == "0.1.0"
        assert spec.runtime == "openclaw"
        assert spec.capabilities == []

    def test_has_capability_and_tag(self):
        spec = AgentSpec(
            agent_id="a1", name="A", description="d",
            capabilities=["coding", "research"],
            tags=["work", "important"],
        )
        assert spec.has_capability("coding")
        assert not spec.has_capability("writing")
        assert spec.has_tag("work")

    def test_to_dict(self):
        spec = AgentSpec(agent_id="a1", name="A", description="d")
        d = spec.to_dict()
        assert d["agent_id"] == "a1"
        assert "created_at" in d
        assert isinstance(d["capabilities"], list)


class TestAgentHandle:
    def test_handle_creation(self):
        h = AgentHandle(instance_id="i1", agent_id="a1")
        assert h.is_available is True
        assert h.status == AgentStatus.AVAILABLE


class TestRegistryABC:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            AgentRegistry()

    def test_has_required_methods(self):
        methods = ["register", "unregister", "get", "list",
                   "find_by_capability", "find_by_tag", "find_by_runtime",
                   "instantiate", "health_check", "count"]
        for m in methods:
            assert hasattr(AgentRegistry, m), f"Missing method: {m}"

    def test_abstract_method_count(self):
        # ABC 应该有足够的抽象方法
        abstract_methods = getattr(AgentRegistry, "__abstractmethods__", set())
        assert len(abstract_methods) >= 8
