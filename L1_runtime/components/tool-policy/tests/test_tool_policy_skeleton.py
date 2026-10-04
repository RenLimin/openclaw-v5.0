"""Tool Policy — 骨架测试。"""

import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from models import ToolPolicy, ToolAccessRequest, PolicyDecision, PolicyEffect, DecisionResult
from policy_engine import ToolPolicyEngine


class TestToolPolicy:
    def test_creation(self):
        p = ToolPolicy(policy_id="p1", effect=PolicyEffect.ALLOW, tools=["exec"])
        assert p.policy_id == "p1"
        assert p.effect == PolicyEffect.ALLOW
        assert p.enabled is True

    def test_matches_tool_exact(self):
        p = ToolPolicy(policy_id="p1", effect=PolicyEffect.ALLOW, tools=["exec", "read"])
        assert p.matches_tool("exec") is True
        assert p.matches_tool("write") is False

    def test_matches_tool_wildcard(self):
        p = ToolPolicy(policy_id="p1", effect=PolicyEffect.ALLOW, tools=["git.*"])
        assert p.matches_tool("git.status") is True
        assert p.matches_tool("exec") is False

    def test_matches_subject(self):
        p = ToolPolicy(policy_id="p1", effect=PolicyEffect.ALLOW, subject="agent-1")
        assert p.matches_subject("agent-1") is True
        assert p.matches_subject("agent-2") is False
        p2 = ToolPolicy(policy_id="p2", effect=PolicyEffect.ALLOW)
        assert p2.matches_subject("anyone") is True


class TestPolicyDecision:
    def test_allowed_property(self):
        d_allow = PolicyDecision(result=DecisionResult.ALLOW)
        d_deny = PolicyDecision(result=DecisionResult.DENY, reason="blocked")
        assert d_allow.allowed is True
        assert d_deny.allowed is False


class TestPolicyEngineABC:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            ToolPolicyEngine()

    def test_has_required_methods(self):
        methods = ["evaluate", "add_policy", "remove_policy", "get_policy",
                   "list_policies", "enable_policy", "disable_policy",
                   "record_usage", "check_rate_limit", "get_usage_stats"]
        for m in methods:
            assert hasattr(ToolPolicyEngine, m), f"Missing method: {m}"
