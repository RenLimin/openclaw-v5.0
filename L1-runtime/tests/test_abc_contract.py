"""
L1 抽象基类（ABC）契约测试

验证所有运行时适配器必须满足的接口契约。
"""

import pytest

from adapters.base import (
    ChannelInterface,
    CredentialInterface,
    MemoryInterface,
    RuntimeAdapter,
    SandboxInterface,
)
from adapters.base.models import (
    Conversation,
    ErrorCode,
    ExecResult,
    HealthStatus,
    MemoryItem,
    Message,
    SendResult,
    ToolResult,
)


# =====================================================================
# 1. ABC 不能被直接实例化
# =====================================================================

class TestABCNotInstantiable:
    """测试：ABC 不能被直接实例化。"""

    def test_runtime_adapter_not_instantiable(self):
        """RuntimeAdapter ABC 不能直接实例化。"""
        with pytest.raises(TypeError, match="abstract"):
            RuntimeAdapter()

    def test_memory_interface_not_instantiable(self):
        """MemoryInterface ABC 不能直接实例化。"""
        with pytest.raises(TypeError, match="abstract"):
            MemoryInterface()

    def test_channel_interface_not_instantiable(self):
        """ChannelInterface ABC 不能直接实例化。"""
        with pytest.raises(TypeError, match="abstract"):
            ChannelInterface()

    def test_sandbox_interface_not_instantiable(self):
        """SandboxInterface ABC 不能直接实例化。"""
        with pytest.raises(TypeError, match="abstract"):
            SandboxInterface()

    def test_credential_interface_not_instantiable(self):
        """CredentialInterface ABC 不能直接实例化。"""
        with pytest.raises(TypeError, match="abstract"):
            CredentialInterface()


# =====================================================================
# 2. 抽象方法清单验证（确保契约完整）
# =====================================================================

class TestAbstractMethods:
    """测试：所有抽象方法必须在 ABC 中声明。"""

    def test_runtime_adapter_has_all_abstract_methods(self):
        """RuntimeAdapter 必须包含 8 个抽象方法。"""
        expected = {
            "health_check",
            "get_config",
            "set_config",
            "execute_tool",
            "get_memory",
            "get_channel",
            "get_sandbox",
            "get_credentials",
        }
        actual = RuntimeAdapter.__abstractmethods__
        assert expected == actual, f"缺失抽象方法: {expected - actual}; 多余: {actual - expected}"

    def test_memory_interface_has_all_abstract_methods(self):
        """MemoryInterface 必须包含 5 个抽象方法。"""
        expected = {"search", "get", "put", "delete", "list"}
        actual = MemoryInterface.__abstractmethods__
        assert expected == actual

    def test_channel_interface_has_all_abstract_methods(self):
        """ChannelInterface 必须包含 3 个抽象方法。"""
        expected = {"send", "receive", "list_conversations"}
        actual = ChannelInterface.__abstractmethods__
        assert expected == actual

    def test_sandbox_interface_has_all_abstract_methods(self):
        """SandboxInterface 必须包含 4 个抽象方法。"""
        expected = {"exec", "read_file", "write_file", "list_dir"}
        actual = SandboxInterface.__abstractmethods__
        assert expected == actual

    def test_credential_interface_has_all_abstract_methods(self):
        """CredentialInterface 必须包含 3 个抽象方法。"""
        expected = {"get", "list", "has"}
        actual = CredentialInterface.__abstractmethods__
        assert expected == actual


# =====================================================================
# 3. 数据模型测试
# =====================================================================

class TestDataModels:
    """测试：数据模型的序列化和构造。"""

    def test_health_status_serialization(self):
        """HealthStatus 序列化/反序列化。"""
        hs = HealthStatus(status="ok", message="正常", details={"version": "1.0"})
        d = hs.to_dict()
        assert d["status"] == "ok"
        assert d["message"] == "正常"
        assert d["details"]["version"] == "1.0"
        assert hs.is_ok()
        assert not hs.is_degraded()
        assert not hs.is_down()

    def test_health_status_states(self):
        """HealthStatus 三态判断。"""
        assert HealthStatus("ok", "").is_ok()
        assert HealthStatus("degraded", "").is_degraded()
        assert HealthStatus("down", "").is_down()

    def test_tool_result_ok(self):
        """ToolResult 成功构造。"""
        r = ToolResult.ok(output={"answer": 42})
        assert r.success
        assert r.output == {"answer": 42}
        assert r.error is None
        assert r.error_code == ErrorCode.OK

    def test_tool_result_fail(self):
        """ToolResult 失败构造。"""
        r = ToolResult.fail("timeout", ErrorCode.TIMEOUT)
        assert not r.success
        assert r.error == "timeout"
        assert r.error_code == ErrorCode.TIMEOUT

    def test_exec_result_ok(self):
        """ExecResult 成功构造。"""
        r = ExecResult.ok(exit_code=0, stdout="hello", stderr="")
        assert r.success
        assert r.exit_code == 0
        assert r.stdout == "hello"

    def test_exec_result_fail(self):
        """ExecResult 失败构造。"""
        r = ExecResult.fail("command not found", ErrorCode.SANDBOX_EXEC_FAILED)
        assert not r.success
        assert r.error == "command not found"
        assert r.exit_code == -1

    def test_send_result_ok(self):
        """SendResult 成功构造。"""
        r = SendResult.ok("msg_123")
        assert r.success
        assert r.message_id == "msg_123"

    def test_send_result_fail(self):
        """SendResult 失败构造。"""
        r = SendResult.fail("channel offline", ErrorCode.CHANNEL_NOT_FOUND)
        assert not r.success
        assert r.error_code == ErrorCode.CHANNEL_NOT_FOUND

    def test_memory_item_serialization(self):
        """MemoryItem 序列化。"""
        item = MemoryItem(key="user/name", value="Rex", score=0.95, metadata={"source": "memory.md"})
        d = item.to_dict()
        assert d["key"] == "user/name"
        assert d["value"] == "Rex"
        assert d["score"] == 0.95
        assert d["metadata"]["source"] == "memory.md"

    def test_message_serialization(self):
        """Message 序列化。"""
        msg = Message(
            id="msg_001",
            channel="wecom",
            sender="user_123",
            content="hello",
            timestamp="2026-09-10T09:00:00Z",
            metadata={"type": "text"},
        )
        d = msg.to_dict()
        assert d["id"] == "msg_001"
        assert d["content"] == "hello"

    def test_conversation_serialization(self):
        """Conversation 序列化。"""
        conv = Conversation(
            id="conv_001",
            channel="wecom",
            title="测试群",
            participants=["alice", "bob"],
            last_message_at="2026-09-10T09:00:00Z",
            unread_count=5,
        )
        d = conv.to_dict()
        assert d["id"] == "conv_001"
        assert d["unread_count"] == 5

    def test_error_code_enum_values(self):
        """错误码枚举值格式正确。"""
        # 错误码必须以 ERR_ 开头或为 OK
        for code in ErrorCode:
            if code == ErrorCode.OK:
                assert code.value == "OK"
            else:
                assert code.value.startswith("ERR_"), f"{code.name} 格式错误: {code.value}"
