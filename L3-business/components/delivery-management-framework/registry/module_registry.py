#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module Registry — 模块注册引擎
负责模块发现、注册、依赖解析、生命周期管理
"""

from dataclasses import dataclass, field
from typing import List, Dict, Callable, Optional, Any
import logging

logger = logging.getLogger(__name__)

@dataclass
class CommandDef:
    """CLI 命令定义"""
    name: str
    handler: Callable
    description: str

@dataclass
class ModuleManifest:
    """模块声明"""
    name: str
    version: str
    description: str
    tables: List[str] = field(default_factory=list)
    commands: List[CommandDef] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    hooks: Dict[str, str] = field(default_factory=dict)  # event -> handler
    config_schema: Optional[Dict[str, Any]] = None

class ModuleRegistry:
    """模块注册中心"""

    def __init__(self):
        self._modules: Dict[str, ModuleManifest] = {}
        self._dependencies_resolved: bool = False

    def register(self, manifest: ModuleManifest) -> None:
        """注册一个模块"""
        if manifest.name in self._modules:
            logger.warning(f"Module {manifest.name} already registered, overwriting")
        self._modules[manifest.name] = manifest
        self._dependencies_resolved = False
        logger.info(f"Registered module: {manifest.name} v{manifest.version}")

    def unregister(self, name: str) -> None:
        """注销一个模块"""
        if name in self._modules:
            del self._modules[name]
            logger.info(f"Unregistered module: {name}")
        else:
            logger.warning(f"Module {name} not found, cannot unregister")

    def get_module(self, name: str) -> Optional[ModuleManifest]:
        """获取模块信息"""
        return self._modules.get(name)

    def list_modules(self) -> List[ModuleManifest]:
        """列出所有已注册模块"""
        return list(self._modules.values())

    def resolve_dependencies(self) -> Dict[str, List[str]]:
        """解析依赖，返回依赖链"""
        # 简单的深度优先依赖解析
        resolved: List[str] = []
        unresolved: List[str] = []

        def resolve(name: str) -> None:
            if name in resolved:
                return
            if name in unresolved:
                raise ValueError(f"Dependency cycle detected: {name}")
            unresolved.append(name)
            module = self.get_module(name)
            if not module:
                raise ValueError(f"Dependency {name} not found")
            for dep in module.dependencies:
                resolve(dep)
            unresolved.remove(name)
            resolved.append(name)

        for name in self._modules:
            if name not in resolved:
                resolve(name)

        self._dependencies_resolved = True
        # 返回按解析顺序排列的模块列表
        return resolved

    def get_dependency_order(self) -> List[str]:
        """获取依赖排序后的模块列表"""
        if not self._dependencies_resolved:
            return self.resolve_dependencies()
        return [m.name for m in self._modules.values()]

    def has_module(self, name: str) -> bool:
        """检查模块是否存在"""
        return name in self._modules
