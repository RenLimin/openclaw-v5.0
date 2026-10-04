"""Agent Registry — 注册与发现抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from models import AgentSpec, AgentHandle, AgentStatus


class AgentRegistry(ABC):
    """Agent 注册与发现抽象基类。

    负责 Agent 的注册、查询、发现、实例化。
    具体实现可以是：
    - 内存注册表（单进程）
    - 配置文件驱动（从 YAML/JSON 加载）
    - 分布式注册中心（Consul / etcd）
    """

    @abstractmethod
    def register(self, spec: AgentSpec) -> None:
        """注册一个 Agent。

        Raises:
            ValueError: agent_id 已存在
        """
        ...

    @abstractmethod
    def unregister(self, agent_id: str) -> bool:
        """注销一个 Agent。返回是否成功。"""
        ...

    @abstractmethod
    def get(self, agent_id: str) -> Optional[AgentSpec]:
        """按 ID 获取 Agent 规格。"""
        ...

    @abstractmethod
    def list(self) -> List[AgentSpec]:
        """列出所有已注册的 Agent。"""
        ...

    @abstractmethod
    def find_by_capability(self, capability: str) -> List[AgentSpec]:
        """按能力标签查找 Agent。"""
        ...

    @abstractmethod
    def find_by_tag(self, tag: str) -> List[AgentSpec]:
        """按自定义标签查找 Agent。"""
        ...

    @abstractmethod
    def find_by_runtime(self, runtime: str) -> List[AgentSpec]:
        """按运行时类型查找 Agent。"""
        ...

    @abstractmethod
    def instantiate(self, agent_id: str, **config) -> AgentHandle:
        """实例化一个 Agent。

        Args:
            agent_id: 要实例化的 Agent ID
            **config: 实例化配置（覆盖默认 config_schema）

        Returns:
            AgentHandle — 实例句柄

        Raises:
            ValueError: Agent 不存在
            RuntimeError: 实例化失败
        """
        ...

    @abstractmethod
    def health_check(self, agent_id: str) -> Dict[str, str]:
        """检查指定 Agent 的健康状态。

        Returns:
            {"status": "ok|degraded|down", "message": "..."}
        """
        ...

    @abstractmethod
    def count(self) -> int:
        """返回已注册 Agent 数量。"""
        ...
