"""
OpenClaw 适配器契约测试

验证 OpenClawRuntimeAdapter 正确实现了 RuntimeAdapter ABC。
"""

import pytest

from adapters.base import (
    ChannelInterface,
    CredentialInterface,
    MemoryInterface,
    RuntimeAdapter,
    SandboxInterface,
)
from adapters.openclaw.openclaw.runtime_adapter import (
    OpenClawChannel,
    OpenClawCredentials,
    OpenClawMemory,
    OpenClawRuntimeAdapter,
    OpenClawSandbox,
)


class TestOpenClawAdapterInheritance:
    """测试：OpenClaw 适配器继承关系正确。"""

    def test_is_runtime_adapter_subclass(self):
        """OpenClawRuntimeAdapter 是 RuntimeAdapter 子类。"""
        assert issubclass(OpenClawRuntimeAdapter, RuntimeAdapter)

    def test_all_abstract_methods_implemented(self):
        """所有抽象方法都被实现了。"""
        # 如果有未实现的抽象方法，实例化会抛 TypeError
        # 这里实例化成功就证明所有抽象方法都已实现
        adapter = OpenClawRuntimeAdapter()
        assert adapter is not None
        # 没有未实现的抽象方法（抽象方法集合变空了）
        assert not getattr(OpenClawRuntimeAdapter, "__abstractmethods__", None) or \
            len(OpenClawRuntimeAdapter.__abstractmethods__) == 0

    def test_name_and_version(self):
        """名称和版本属性正确。"""
        adapter = OpenClawRuntimeAdapter()
        assert adapter.name == "openclaw"
        assert adapter.version  # 非空字符串

    def test_capabilities_dict(self):
        """capabilities 是字典，含关键能力。"""
        adapter = OpenClawRuntimeAdapter()
        assert isinstance(adapter.capabilities, dict)
        # 至少要有这些顶层能力分类
        for key in ["tool", "memory", "channel", "sandbox", "credential", "config"]:
            assert key in adapter.capabilities, f"缺少能力分类: {key}"


class TestOpenClawSubsystemTypes:
    """测试：子系统返回正确的接口类型。"""

    def setup_method(self):
        self.adapter = OpenClawRuntimeAdapter()

    def test_get_memory_returns_memory_interface(self):
        """get_memory 返回 MemoryInterface 实现。"""
        mem = self.adapter.get_memory()
        assert isinstance(mem, MemoryInterface)
        assert isinstance(mem, OpenClawMemory)

    def test_get_memory_scope_caching(self):
        """同一 scope 的 memory 实例被缓存。"""
        mem1 = self.adapter.get_memory("scope1")
        mem2 = self.adapter.get_memory("scope1")
        assert mem1 is mem2

    def test_get_memory_different_scope(self):
        """不同 scope 返回不同实例。"""
        mem1 = self.adapter.get_memory("scope1")
        mem2 = self.adapter.get_memory("scope2")
        assert mem1 is not mem2

    def test_get_channel_returns_channel_interface(self):
        """get_channel 返回 ChannelInterface 实现。"""
        ch = self.adapter.get_channel("test-channel")
        assert isinstance(ch, ChannelInterface)
        assert isinstance(ch, OpenClawChannel)
        assert ch.name == "test-channel"

    def test_get_channel_caching(self):
        """同一 channel 实例被缓存。"""
        ch1 = self.adapter.get_channel("ch1")
        ch2 = self.adapter.get_channel("ch1")
        assert ch1 is ch2

    def test_get_sandbox_returns_sandbox_interface(self):
        """get_sandbox 返回 SandboxInterface 实现。"""
        sb = self.adapter.get_sandbox()
        assert isinstance(sb, SandboxInterface)
        assert isinstance(sb, OpenClawSandbox)

    def test_get_sandbox_singleton(self):
        """sandbox 是单例。"""
        sb1 = self.adapter.get_sandbox()
        sb2 = self.adapter.get_sandbox()
        assert sb1 is sb2

    def test_get_credentials_returns_credential_interface(self):
        """get_credentials 返回 CredentialInterface 实现。"""
        cr = self.adapter.get_credentials()
        assert isinstance(cr, CredentialInterface)
        assert isinstance(cr, OpenClawCredentials)

    def test_get_credentials_singleton(self):
        """credentials 是单例。"""
        cr1 = self.adapter.get_credentials()
        cr2 = self.adapter.get_credentials()
        assert cr1 is cr2


class TestOpenClawCapabilities:
    """测试：能力声明和 supports 方法。"""

    def setup_method(self):
        self.adapter = OpenClawRuntimeAdapter()

    def test_supports_memory_get(self):
        assert self.adapter.supports("memory.get")

    def test_supports_memory_search(self):
        assert self.adapter.supports("memory.search")

    def test_does_not_support_memory_delete(self):
        assert not self.adapter.supports("memory.delete")

    def test_does_not_support_memory_list(self):
        assert not self.adapter.supports("memory.list")

    def test_does_not_support_nonexistent(self):
        assert not self.adapter.supports("completely.nonexistent.feature")

    def test_list_capabilities_not_empty(self):
        caps = self.adapter.list_capabilities()
        assert len(caps) > 0
        # 都是点号路径格式
        for cap in caps:
            assert isinstance(cap, str)
            assert len(cap) > 0


class TestOpenClawHealthCheck:
    """测试：健康检查返回正确格式。"""

    def test_health_check_returns_health_status(self):
        """health_check 返回 HealthStatus 对象。"""
        from adapters.base import HealthStatus
        adapter = OpenClawRuntimeAdapter()
        # 注意：在测试环境中可能没有 openclaw 命令，
        # 但应该返回 status=down 的 HealthStatus，而不是抛异常
        result = adapter.health_check()
        assert isinstance(result, HealthStatus)
        assert result.status in {"ok", "degraded", "down"}
        assert isinstance(result.message, str)
