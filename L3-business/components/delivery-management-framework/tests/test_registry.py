# -*- coding: utf-8 -*-
"""ModuleRegistry 模块注册引擎测试。"""

import pytest
from registry import ModuleRegistry, ModuleManifest


def _make_manifest(name: str, deps: list = None) -> ModuleManifest:
    return ModuleManifest(
        name=name,
        version="1.0.0",
        description=f"{name} 模块",
        tables=[f"{name}_table"],
        dependencies=deps or [],
    )


class TestModuleRegistry:
    """ModuleRegistry 核心功能测试。"""

    def setup_method(self):
        self.registry = ModuleRegistry()

    def test_register_and_get(self):
        """注册后应能通过名称获取模块。"""
        m = _make_manifest("project")
        self.registry.register(m)
        result = self.registry.get_module("project")
        assert result is not None
        assert result.name == "project"
        assert result.version == "1.0.0"

    def test_get_nonexistent_returns_none(self):
        """获取不存在的模块应返回 None。"""
        assert self.registry.get_module("nonexistent") is None

    def test_list_modules(self):
        """应列出所有已注册模块。"""
        self.registry.register(_make_manifest("a"))
        self.registry.register(_make_manifest("b"))
        modules = self.registry.list_modules()
        assert len(modules) == 2
        names = {m.name for m in modules}
        assert names == {"a", "b"}

    def test_has_module(self):
        """has_module 应正确判断模块是否存在。"""
        self.registry.register(_make_manifest("exists"))
        assert self.registry.has_module("exists") is True
        assert self.registry.has_module("notexists") is False

    def test_unregister(self):
        """注销后模块应不再存在。"""
        self.registry.register(_make_manifest("to_remove"))
        assert self.registry.has_module("to_remove") is True
        self.registry.unregister("to_remove")
        assert self.registry.has_module("to_remove") is False

    def test_unregister_nonexistent_silent(self):
        """注销不存在的模块不应报错。"""
        self.registry.unregister("nonexistent")

    def test_overwrite_register(self):
        """重复注册同名模块应覆盖。"""
        m1 = _make_manifest("mod", deps=[])
        m2 = ModuleManifest(
            name="mod",
            version="2.0.0",
            description="v2",
            tables=[],
        )
        self.registry.register(m1)
        self.registry.register(m2)
        assert self.registry.get_module("mod").version == "2.0.0"


class TestDependencyResolution:
    """依赖解析测试。"""

    def setup_method(self):
        self.registry = ModuleRegistry()

    def test_simple_dependency_order(self):
        """被依赖的模块应排在前面。"""
        self.registry.register(_make_manifest("b", deps=["a"]))
        self.registry.register(_make_manifest("a"))
        order = self.registry.resolve_dependencies()
        assert order.index("a") < order.index("b")

    def test_chain_dependency(self):
        """链式依赖应正确排序。"""
        self.registry.register(_make_manifest("c", deps=["b"]))
        self.registry.register(_make_manifest("b", deps=["a"]))
        self.registry.register(_make_manifest("a"))
        order = self.registry.resolve_dependencies()
        assert order.index("a") < order.index("b") < order.index("c")

    def test_no_dependencies(self):
        """无依赖的模块应全部返回。"""
        self.registry.register(_make_manifest("x"))
        self.registry.register(_make_manifest("y"))
        order = self.registry.resolve_dependencies()
        assert set(order) == {"x", "y"}

    def test_missing_dependency_raises(self):
        """依赖未注册的模块应抛出 ValueError。"""
        self.registry.register(_make_manifest("m", deps=["nonexistent"]))
        with pytest.raises(ValueError, match="not found"):
            self.registry.resolve_dependencies()

    def test_cycle_detection(self):
        """循环依赖应被检测并抛出 ValueError。"""
        self.registry.register(_make_manifest("x", deps=["y"]))
        self.registry.register(_make_manifest("y", deps=["x"]))
        with pytest.raises(ValueError, match="cycle"):
            self.registry.resolve_dependencies()

    def test_get_dependency_order_auto_resolves(self):
        """get_dependency_order 在首次调用时应自动解析。"""
        self.registry.register(_make_manifest("b", deps=["a"]))
        self.registry.register(_make_manifest("a"))
        order = self.registry.get_dependency_order()
        assert order.index("a") < order.index("b")

    def test_register_invalidates_cache(self):
        """新注册模块应使依赖缓存失效。"""
        self.registry.register(_make_manifest("a"))
        self.registry.resolve_dependencies()
        self.registry.register(_make_manifest("b", deps=["a"]))
        order = self.registry.get_dependency_order()
        assert order.index("a") < order.index("b")
