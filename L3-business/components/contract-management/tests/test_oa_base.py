"""OaProvider 抽象基类：约束子类实现 + 基类方法默认抛 NotImplementedError。"""
import pytest

import contract_management as cm


def test_concrete_subclass_must_implement_all():
    class Incomplete(cm.OaProvider):
        def get_contract_attachment(self, pid): ...
    with pytest.raises(TypeError):
        Incomplete()  # 仍有抽象方法未实现


class _Concrete(cm.OaProvider):
    def get_contract_attachment(self, pid):
        return super().get_contract_attachment(pid)

    def query_process(self, pid):
        return super().query_process(pid)

    def push_result(self, pid, action, comment, approver):
        return super().push_result(pid, action, comment, approver)

    def register_callback(self, handler):
        return super().register_callback(handler)


def test_base_methods_raise_not_implemented():
    o = _Concrete()
    with pytest.raises(NotImplementedError):
        o.get_contract_attachment("p")
    with pytest.raises(NotImplementedError):
        o.query_process("p")
    with pytest.raises(NotImplementedError):
        o.push_result("p", "a", "c", "u")
    with pytest.raises(NotImplementedError):
        o.register_callback(None)
