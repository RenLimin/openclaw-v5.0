"""
core/module.py — 模块注册系统
ModuleManifest 声明 + ModuleRegistry 管理 + 依赖拓扑排序 + 生命周期初始化。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# ---------------------------------------------------------------------------
# CommandDef — CLI 命令声明
# ---------------------------------------------------------------------------

@dataclass
class CommandDef:
    """模块提供的 CLI 命令定义。

    模块通过声明 CommandDef 把自己的命令注册到统一 CLI 入口。
    handler 是可调用对象，接收 (argparse namespace, context dict)。
    """

    name: str
    help: str = ""
    handler: Callable[..., None] = lambda **kw: None
    arguments: list[dict[str, Any]] = field(default_factory=list)  # argparse add_kwargs

    def __post_init__(self) -> None:
        for arg in self.arguments:
            if "flags" not in arg and "name" not in arg:
                raise ValueError(f"Command argument must have 'flags' or 'name': {arg}")


# ---------------------------------------------------------------------------
# BaseModule — 模块基类
# ---------------------------------------------------------------------------

class BaseModule(ABC):
    """模块基类，所有模块必须继承。

    生命周期：
    1. register — 注册 manifest + factory
    2. initialize — 框架启动时调用，传入 db + config + 全局容器
    3. ready — 所有模块初始化完成后调用，可做跨模块交互
    """

    def __init__(self, manifest: "ModuleManifest") -> None:
        self.manifest = manifest
        self._initialized = False
        self._ready = False

    @abstractmethod
    def initialize(self, db: Any, config: dict[str, Any], container: "ModuleRegistry") -> None:
        """初始化模块：建表、注册事件监听、注册状态机等。"""
        ...

    def on_ready(self, container: "ModuleRegistry") -> None:
        """所有模块初始化完成后调用，可做跨模块交互。默认空实现。"""
        pass

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def is_initialized(self) -> bool:
        return self._initialized


# ---------------------------------------------------------------------------
# ModuleManifest — 模块声明
# ---------------------------------------------------------------------------

@dataclass
class ModuleManifest:
    """模块清单：模块的元数据声明。

    模块通过 manifest 声明自己的身份、依赖、提供的命令、拥有的表等。
    框架在注册时读取 manifest，用于依赖解析、命令聚合、表所有权追踪。
    """

    name: str
    version: str = "0.1.0"
    description: str = ""
    dependencies: list[str] = field(default_factory=list)
    commands: list[CommandDef] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)
    events_subscribed: list[str] = field(default_factory=list)
    config_schema: dict[str, Any] = field(default_factory=dict)
    migrations: list[tuple[str, str]] = field(default_factory=list)  # (version, description)

    def __post_init__(self) -> None:
        if not self.name or not isinstance(self.name, str):
            raise ValueError("Module name must be a non-empty string")
        # 简单 semver 校验：x.y.z
        parts = self.version.split(".")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            raise ValueError(f"Version must be semver (x.y.z), got: {self.version}")


# ---------------------------------------------------------------------------
# ModuleRegistry — 模块注册中心
# ---------------------------------------------------------------------------

class ModuleRegistry:
    """模块注册中心：管理所有模块的注册、依赖解析、生命周期。

    设计原则：
    - 注册即声明，不做实际初始化
    - initialize_all 按拓扑顺序初始化，保证依赖先初始化
    - 初始化后调用 on_ready，模块可在此时做跨模块交互
    """

    def __init__(self) -> None:
        self._manifests: dict[str, ModuleManifest] = {}
        self._factories: dict[str, Callable[[ModuleManifest], BaseModule]] = {}
        self._instances: dict[str, BaseModule] = {}
        self._initialized = False

    # -- 注册 --------------------------------------------------------------

    def register(self, manifest: ModuleManifest, factory: Callable[[ModuleManifest], BaseModule]) -> None:
        """注册一个模块。factory 接收 manifest，返回 BaseModule 实例。"""
        if manifest.name in self._manifests:
            raise ValueError(f"Module '{manifest.name}' already registered")
        self._manifests[manifest.name] = manifest
        self._factories[manifest.name] = factory

    # -- 查询 --------------------------------------------------------------

    def get(self, name: str) -> BaseModule:
        if name not in self._instances:
            raise KeyError(f"Module '{name}' not found or not initialized")
        return self._instances[name]

    def get_manifest(self, name: str) -> ModuleManifest:
        if name not in self._manifests:
            raise KeyError(f"Module manifest '{name}' not found")
        return self._manifests[name]

    def list_modules(self) -> list[ModuleManifest]:
        return list(self._manifests.values())

    def has_module(self, name: str) -> bool:
        return name in self._manifests

    # -- 依赖解析 ----------------------------------------------------------

    def resolve_dependencies(self) -> list[str]:
        """拓扑排序：返回按依赖顺序排列的模块名列表。

        依赖在前，被依赖在后。即初始化按这个顺序来。
        """
        # 校验所有依赖都已注册
        for name, manifest in self._manifests.items():
            for dep in manifest.dependencies:
                if dep not in self._manifests:
                    raise ValueError(f"Module '{name}' depends on '{dep}', which is not registered")

        # Kahn 算法拓扑排序
        in_degree = {name: 0 for name in self._manifests}
        for name, manifest in self._manifests.items():
            for dep in manifest.dependencies:
                in_degree[name] += 1

        queue = [name for name, d in in_degree.items() if d == 0]
        result: list[str] = []

        # 反向图：dep -> [modules that depend on dep]
        reverse: dict[str, list[str]] = {name: [] for name in self._manifests}
        for name, manifest in self._manifests.items():
            for dep in manifest.dependencies:
                reverse[dep].append(name)

        while queue:
            current = queue.pop(0)
            result.append(current)
            for dependent in reverse[current]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if len(result) != len(self._manifests):
            cycle = set(self._manifests.keys()) - set(result)
            raise ValueError(f"Circular dependency detected among: {cycle}")

        return result

    # -- 生命周期 ----------------------------------------------------------

    def initialize_all(self, db: Any, config: dict[str, Any]) -> None:
        """按依赖顺序初始化所有模块。

        1. 拓扑排序
        2. 依次实例化 + initialize
        3. 全部初始化完成后，依次调用 on_ready
        """
        if self._initialized:
            raise RuntimeError("Modules already initialized")

        order = self.resolve_dependencies()

        # Phase 1: initialize
        for name in order:
            manifest = self._manifests[name]
            factory = self._factories[name]
            instance = factory(manifest)
            instance.initialize(db, config.get(name, {}), self)
            instance._initialized = True
            self._instances[name] = instance

        # Phase 2: on_ready (跨模块交互)
        for name in order:
            self._instances[name].on_ready(self)

        self._initialized = True

    @property
    def is_initialized(self) -> bool:
        return self._initialized
