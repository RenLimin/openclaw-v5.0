"""
运行时适配器注册表（工厂模式）

统一管理所有运行时适配器的注册、发现和实例化。

使用方式：
    # 注册
    from L1_runtime.adapters.registry import register_adapter
    register_adapter("openclaw", OpenClawAdapter)

    # 获取
    from L1_runtime.adapters.registry import get_adapter
    adapter = get_adapter("openclaw")

    # 自动加载（通过配置）
    from L1_runtime.adapters.registry import RuntimeRegistry
    registry = RuntimeRegistry()
    registry.load_from_config({"runtime": "openclaw"})
"""

from __future__ import annotations

import importlib
from typing import Any, Dict, Optional, Type

from .base.runtime import RuntimeAdapter


class RuntimeRegistry:
    """运行时适配器注册表。

    维护运行时名称 → 适配器类的映射，支持：
    - 手动注册
    - 按名称获取/实例化
    - 通过配置自动加载（含 import path 懒加载）
    """

    def __init__(self) -> None:
        self._adapters: Dict[str, Type[RuntimeAdapter]] = {}
        self._instances: Dict[str, RuntimeAdapter] = {}
        self._import_paths: Dict[str, str] = {}

    def register(
        self,
        name: str,
        adapter_class: Type[RuntimeAdapter],
        import_path: Optional[str] = None,
    ) -> None:
        """注册一个适配器类。

        Args:
            name: 运行时名称（小写，kebab-case，如 "openclaw"）
            adapter_class: 适配器类（必须是 RuntimeAdapter 的子类）
            import_path: 可选的懒加载 import 路径，用于配置驱动加载
        """
        if not issubclass(adapter_class, RuntimeAdapter):
            raise TypeError(
                f"{adapter_class.__name__} 必须继承 RuntimeAdapter ABC"
            )
        self._adapters[name] = adapter_class
        if import_path:
            self._import_paths[name] = import_path

    def unregister(self, name: str) -> None:
        """注销适配器。

        Args:
            name: 运行时名称
        """
        self._adapters.pop(name, None)
        self._instances.pop(name, None)
        self._import_paths.pop(name, None)

    def is_registered(self, name: str) -> bool:
        """检查运行时是否已注册。"""
        return name in self._adapters or name in self._import_paths

    def get_adapter_class(self, name: str) -> Type[RuntimeAdapter]:
        """获取适配器类（不实例化）。

        支持懒加载：如果类未注册但 import_path 已注册，
        自动 import 并注册。

        Args:
            name: 运行时名称

        Returns:
            适配器类对象。

        Raises:
            KeyError: 运行时未注册
        """
        if name not in self._adapters and name in self._import_paths:
            self._lazy_load(name)
        if name not in self._adapters:
            raise KeyError(f"未注册的运行时: {name}. 已注册: {list(self._adapters.keys())}")
        return self._adapters[name]

    def get_adapter(self, name: str, **kwargs: Any) -> RuntimeAdapter:
        """获取适配器实例。

        默认单例：同一名只创建一个实例。
        需要新建实例时传 new_instance=True。

        Args:
            name: 运行时名称
            **kwargs: 传递给适配器构造函数的参数

        Keyword Args:
            new_instance (bool): 强制创建新实例，默认 False

        Returns:
            RuntimeAdapter 实例
        """
        new_instance = kwargs.pop("new_instance", False)

        if not new_instance and name in self._instances:
            return self._instances[name]

        cls = self.get_adapter_class(name)
        instance = cls(**kwargs)

        if not new_instance:
            self._instances[name] = instance

        return instance

    def list_adapters(self) -> Dict[str, Type[RuntimeAdapter]]:
        """列出所有已注册的适配器类。"""
        return dict(self._adapters)

    def load_from_config(self, config: Dict[str, Any]) -> None:
        """从配置字典加载适配器注册信息。

        配置格式：
        {
            "adapters": {
                "openclaw": {
                    "import_path": "L1_runtime.adapters.openclaw.OpenClawAdapter",
                    "enabled": true
                },
                "claude-code": {
                    "import_path": "L1_runtime.adapters.claude_code.ClaudeCodeAdapter",
                    "enabled": false
                }
            }
        }

        Args:
            config: 配置字典
        """
        adapters_cfg = config.get("adapters", {})
        for name, cfg in adapters_cfg.items():
            if not cfg.get("enabled", True):
                continue
            import_path = cfg.get("import_path")
            if import_path:
                self._import_paths[name] = import_path

    def _lazy_load(self, name: str) -> None:
        """懒加载适配器类。

        根据 import_path 动态 import 并注册。
        """
        import_path = self._import_paths[name]
        module_path, class_name = import_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)

        if not issubclass(cls, RuntimeAdapter):
            raise TypeError(
                f"懒加载失败: {import_path} 不是 RuntimeAdapter 子类"
            )

        self._adapters[name] = cls


# ---------------------------------------------------------------------------
# 模块级便捷函数（使用全局默认注册表）
# ---------------------------------------------------------------------------

_default_registry = RuntimeRegistry()


def register_adapter(name: str, adapter_class: Type[RuntimeAdapter]) -> None:
    """注册适配器（全局默认注册表便捷函数）。"""
    _default_registry.register(name, adapter_class)


def get_adapter(name: str, **kwargs: Any) -> RuntimeAdapter:
    """获取适配器实例（全局默认注册表便捷函数）。"""
    return _default_registry.get_adapter(name, **kwargs)


def get_adapter_class(name: str) -> Type[RuntimeAdapter]:
    """获取适配器类（全局默认注册表便捷函数）。"""
    return _default_registry.get_adapter_class(name)


def is_registered(name: str) -> bool:
    """检查运行时是否已注册（全局默认注册表便捷函数）。"""
    return _default_registry.is_registered(name)


def list_registered() -> Dict[str, Type[RuntimeAdapter]]:
    """列出所有已注册的适配器。"""
    return _default_registry.list_adapters()
