"""
运行时适配器注册表（工厂模式）测试
"""

import pytest

from adapters.base import RuntimeAdapter
from adapters.registry import RuntimeRegistry


# 测试用的 Mock 适配器
class MockAdapter(RuntimeAdapter):
    name = "mock"
    version = "1.0.0"
    capabilities = {"test": True}

    def health_check(self):
        pass

    def get_config(self, key):
        pass

    def set_config(self, key, value):
        pass

    def execute_tool(self, name, params):
        pass

    def get_memory(self, scope="default"):
        pass

    def get_channel(self, name):
        pass

    def get_sandbox(self):
        pass

    def get_credentials(self):
        pass


class MockAdapterV2(RuntimeAdapter):
    name = "mock-v2"
    version = "2.0.0"
    capabilities = {"test": True, "v2": True}

    def health_check(self):
        pass

    def get_config(self, key):
        pass

    def set_config(self, key, value):
        pass

    def execute_tool(self, name, params):
        pass

    def get_memory(self, scope="default"):
        pass

    def get_channel(self, name):
        pass

    def get_sandbox(self):
        pass

    def get_credentials(self):
        pass


class NotAnAdapter:
    """不是 RuntimeAdapter 子类，用于测试类型校验。"""
    pass


class TestRuntimeRegistry:
    """注册表核心功能测试。"""

    def test_register_and_get_class(self):
        """注册适配器类并获取。"""
        registry = RuntimeRegistry()
        registry.register("mock", MockAdapter)
        assert registry.is_registered("mock")
        cls = registry.get_adapter_class("mock")
        assert cls is MockAdapter

    def test_register_invalid_class_raises(self):
        """注册非 RuntimeAdapter 子类会抛 TypeError。"""
        registry = RuntimeRegistry()
        with pytest.raises(TypeError, match="必须继承 RuntimeAdapter"):
            registry.register("bad", NotAnAdapter)

    def test_get_unregistered_raises_key_error(self):
        """获取未注册的运行时会抛 KeyError。"""
        registry = RuntimeRegistry()
        with pytest.raises(KeyError, match="未注册的运行时"):
            registry.get_adapter_class("nonexistent")

    def test_get_adapter_instance(self):
        """获取适配器实例（默认单例）。"""
        registry = RuntimeRegistry()
        registry.register("mock", MockAdapter)
        inst1 = registry.get_adapter("mock")
        inst2 = registry.get_adapter("mock")
        assert isinstance(inst1, MockAdapter)
        assert inst1 is inst2  # 单例

    def test_get_adapter_new_instance(self):
        """new_instance=True 时每次返回新实例。"""
        registry = RuntimeRegistry()
        registry.register("mock", MockAdapter)
        inst1 = registry.get_adapter("mock")
        inst2 = registry.get_adapter("mock", new_instance=True)
        assert inst1 is not inst2

    def test_unregister(self):
        """注销适配器。"""
        registry = RuntimeRegistry()
        registry.register("mock", MockAdapter)
        assert registry.is_registered("mock")
        registry.unregister("mock")
        assert not registry.is_registered("mock")

    def test_list_adapters(self):
        """列出所有已注册适配器。"""
        registry = RuntimeRegistry()
        registry.register("mock", MockAdapter)
        registry.register("mock-v2", MockAdapterV2)
        registered = registry.list_adapters()
        assert "mock" in registered
        assert "mock-v2" in registered
        assert len(registered) == 2

    def test_load_from_config(self):
        """从配置加载适配器注册信息。"""
        registry = RuntimeRegistry()
        config = {
            "adapters": {
                "mock-from-config": {
                    "import_path": __name__ + ".MockAdapter",
                    "enabled": True,
                },
                "disabled-adapter": {
                    "import_path": __name__ + ".MockAdapterV2",
                    "enabled": False,
                },
            }
        }
        registry.load_from_config(config)
        # enabled 的会被加入 import_paths（懒加载）
        assert registry.is_registered("mock-from-config")
        # disabled 的不注册
        assert not registry.is_registered("disabled-adapter")

    def test_lazy_load(self):
        """懒加载适配器类。"""
        registry = RuntimeRegistry()
        registry._import_paths["mock-lazy"] = __name__ + ".MockAdapter"
        assert "mock-lazy" not in registry._adapters
        cls = registry.get_adapter_class("mock-lazy")
        assert cls is MockAdapter
        assert "mock-lazy" in registry._adapters


class TestGlobalRegistry:
    """全局注册表便捷函数测试。"""

    def test_module_level_functions(self):
        """模块级便捷函数可用。"""
        from adapters.registry import (
            get_adapter,
            get_adapter_class,
            is_registered,
            list_registered,
            register_adapter,
        )
        # 注册一个测试适配器
        register_adapter("test-mock", MockAdapter)
        assert is_registered("test-mock")
        cls = get_adapter_class("test-mock")
        assert cls is MockAdapter
        inst = get_adapter("test-mock")
        assert isinstance(inst, MockAdapter)
        assert "test-mock" in list_registered()
