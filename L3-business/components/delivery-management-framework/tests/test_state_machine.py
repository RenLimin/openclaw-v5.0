# -*- coding: utf-8 -*-
"""StateMachine 状态机引擎测试。"""

import pytest
from state_machine import StateMachine, StateMachineEngine, Transition


def _make_simple_sm() -> StateMachine:
    """创建一个简单的草稿->审核->批准 状态机。"""
    return StateMachine(
        name="doc_review",
        states=["draft", "review", "approved", "rejected"],
        initial="draft",
        transitions=[
            Transition(event="submit", source="draft", target="review"),
            Transition(event="approve", source="review", target="approved"),
            Transition(event="reject", source="review", target="rejected"),
            Transition(event="revise", source="rejected", target="draft"),
        ],
    )


class TestStateMachine:
    """StateMachine 定义层测试。"""

    def test_initial_state_must_be_in_states(self):
        """初始状态必须在状态列表中，否则抛出 ValueError。"""
        with pytest.raises(ValueError, match="not in states"):
            StateMachine(
                name="bad",
                states=["a", "b"],
                initial="c",
                transitions=[],
            )

    def test_valid_definition(self):
        """正确定义不应抛异常。"""
        sm = _make_simple_sm()
        assert sm.name == "doc_review"
        assert len(sm.states) == 4
        assert len(sm.transitions) == 4


class TestStateMachineEngine:
    """StateMachineEngine 引擎层测试。"""

    def setup_method(self):
        self.engine = StateMachineEngine()
        self.engine.register(_make_simple_sm())

    def test_register_and_get(self):
        """注册后应能通过名称获取状态机。"""
        sm = self.engine.get_state_machine("doc_review")
        assert sm is not None
        assert sm.name == "doc_review"

    def test_get_nonexistent_returns_none(self):
        """获取不存在的状态机应返回 None。"""
        assert self.engine.get_state_machine("nonexistent") is None

    def test_basic_transition(self):
        """基本状态转换：draft --submit--> review。"""
        result = self.engine.trigger("doc_review", "draft", "submit")
        assert result == "review"

    def test_full_happy_path(self):
        """完整正向路径：draft -> review -> approved。"""
        s = self.engine.trigger("doc_review", "draft", "submit")
        assert s == "review"
        s = self.engine.trigger("doc_review", s, "approve")
        assert s == "approved"

    def test_reject_path(self):
        """拒绝路径：draft -> review -> rejected -> draft。"""
        s = self.engine.trigger("doc_review", "draft", "submit")
        s = self.engine.trigger("doc_review", s, "reject")
        assert s == "rejected"
        s = self.engine.trigger("doc_review", s, "revise")
        assert s == "draft"

    def test_invalid_transition_returns_none(self):
        """无效转换应返回 None（如 draft 不能直接 approve）。"""
        result = self.engine.trigger("doc_review", "draft", "approve")
        assert result is None

    def test_nonexistent_sm_returns_none(self):
        """触发不存在的状态机应返回 None。"""
        result = self.engine.trigger("nonexistent", "draft", "submit")
        assert result is None

    def test_multiple_source_states(self):
        """转换支持多源状态列表。"""
        sm = StateMachine(
            name="multi_source",
            states=["a", "b", "c"],
            initial="a",
            transitions=[
                Transition(event="go", source=["a", "b"], target="c"),
            ],
        )
        self.engine.register(sm)
        assert self.engine.trigger("multi_source", "a", "go") == "c"
        assert self.engine.trigger("multi_source", "b", "go") == "c"

    def test_guard_blocks_transition(self):
        """守卫条件不满足时应阻止转换。"""
        sm = StateMachine(
            name="guarded",
            states=["start", "end"],
            initial="start",
            transitions=[
                Transition(event="go", source="start", target="end", guard="allow"),
            ],
            guards={"allow": lambda ctx: ctx.get("allowed", False)},
        )
        self.engine.register(sm)
        # 守卫不满足
        result = self.engine.trigger("guarded", "start", "go", context={"allowed": False})
        assert result is None
        # 守卫满足
        result = self.engine.trigger("guarded", "start", "go", context={"allowed": True})
        assert result == "end"

    def test_guard_passes_without_guard(self):
        """无守卫的转换应直接通过。"""
        result = self.engine.trigger("doc_review", "draft", "submit")
        assert result == "review"

    def test_hooks_fire_on_transition(self):
        """钩子函数应在转换时正确触发。"""
        events = []

        def on_exit(ctx, trans):
            events.append(("exit", trans.source))

        def on_enter(ctx, trans):
            events.append(("enter", trans.target))

        self.engine.add_hook("doc_review", "draft_exit", on_exit)
        self.engine.add_hook("doc_review", "review_enter", on_enter)

        self.engine.trigger("doc_review", "draft", "submit")
        assert ("exit", "draft") in events
        assert ("enter", "review") in events

    def test_add_guard_to_existing_sm(self):
        """应能向已注册状态机动态添加守卫。"""
        sm = StateMachine(
            name="dynamic_guard",
            states=["a", "b"],
            initial="a",
            transitions=[
                Transition(event="go", source="a", target="b", guard="check"),
            ],
        )
        self.engine.register(sm)
        # 未添加守卫前，有 guard 名称但无函数 -> 守卫失败 -> 无法转换
        result = self.engine.trigger("dynamic_guard", "a", "go")
        assert result is None
        # 添加守卫函数
        assert self.engine.add_guard("dynamic_guard", "check", lambda ctx: True) is True
        result = self.engine.trigger("dynamic_guard", "a", "go")
        assert result == "b"

    def test_add_hook_to_nonexistent_sm_returns_false(self):
        """向不存在的状态机添加钩子应返回 False。"""
        assert self.engine.add_hook("nonexistent", "hook", lambda ctx, trans: None) is False

    def test_add_guard_to_nonexistent_sm_returns_false(self):
        """向不存在的状态机添加守卫应返回 False。"""
        assert self.engine.add_guard("nonexistent", "g", lambda ctx: True) is False

    def test_overwrite_register(self):
        """重复注册同名状态机应覆盖。"""
        sm = _make_simple_sm()
        self.engine.register(sm)
        # 不抛异常即为成功
        assert self.engine.get_state_machine("doc_review") is not None
