"""In-Memory Agent Registry — 内存 Agent 注册与发现实现."""

from __future__ import annotations

import threading
import uuid
import logging
from typing import Dict, List, Optional

from models import AgentSpec, AgentHandle, AgentStatus

logger = logging.getLogger(__name__)


class InMemoryAgentRegistry:
    """内存 Agent 注册表实现.
    
    支持：
    - Agent 注册/注销
    - 按能力/标签/运行时发现
    - 实例化（返回句柄）
    - 健康检查
    - 线程安全
    """

    def __init__(self) -> None:
        self._specs: Dict[str, AgentSpec] = {}
        self._handles: Dict[str, AgentHandle] = {}
        self._lock = threading.Lock()

    def register(self, spec: AgentSpec) -> None:
        """注册 Agent 规格."""
        with self._lock:
            if spec.agent_id in self._specs:
                raise ValueError(f"Agent {spec.agent_id} already registered")
            self._specs[spec.agent_id] = spec
            logger.info(f"Agent registered: {spec.agent_id} ({spec.name})")

    def unregister(self, agent_id: str) -> bool:
        """注销 Agent."""
        with self._lock:
            if agent_id in self._specs:
                del self._specs[agent_id]
                # 清理句柄
                handles_to_remove = [
                    iid for iid, h in self._handles.items()
                    if h.agent_id == agent_id
                ]
                for iid in handles_to_remove:
                    del self._handles[iid]
                logger.info(f"Agent unregistered: {agent_id}")
                return True
            return False

    def get(self, agent_id: str) -> Optional[AgentSpec]:
        """获取 Agent 规格."""
        with self._lock:
            return self._specs.get(agent_id)

    def list(self) -> List[AgentSpec]:
        """列出所有 Agent."""
        with self._lock:
            return list(self._specs.values())

    def find_by_capability(self, capability: str) -> List[AgentSpec]:
        """按能力查找."""
        with self._lock:
            return [s for s in self._specs.values() if s.has_capability(capability)]

    def find_by_tag(self, tag: str) -> List[AgentSpec]:
        """按标签查找."""
        with self._lock:
            return [s for s in self._specs.values() if s.has_tag(tag)]

    def find_by_runtime(self, runtime: str) -> List[AgentSpec]:
        """按运行时查找."""
        with self._lock:
            return [s for s in self._specs.values() if s.runtime == runtime]

    def instantiate(self, agent_id: str, **kwargs) -> AgentHandle:
        """实例化 Agent."""
        with self._lock:
            spec = self._specs.get(agent_id)
            if spec is None:
                raise ValueError(f"Agent {agent_id} not found")
            instance_id = f"inst-{uuid.uuid4().hex[:8]}"
            handle = AgentHandle(
                instance_id=instance_id,
                agent_id=agent_id,
                status=AgentStatus.AVAILABLE,
                config={**spec.config_schema, **kwargs},
            )
            self._handles[instance_id] = handle
            logger.info(f"Agent instantiated: {agent_id} -> {instance_id}")
            return handle

    def get_handle(self, instance_id: str) -> Optional[AgentHandle]:
        """获取实例句柄."""
        with self._lock:
            return self._handles.get(instance_id)

    def list_handles(self, agent_id: Optional[str] = None) -> List[AgentHandle]:
        """列出句柄."""
        with self._lock:
            handles = list(self._handles.values())
            if agent_id:
                handles = [h for h in handles if h.agent_id == agent_id]
            return handles

    def update_status(self, instance_id: str, status: AgentStatus) -> bool:
        """更新实例状态."""
        with self._lock:
            handle = self._handles.get(instance_id)
            if handle is None:
                return False
            handle.status = status
            return True

    def destroy(self, instance_id: str) -> bool:
        """销毁实例."""
        with self._lock:
            if instance_id in self._handles:
                del self._handles[instance_id]
                logger.info(f"Instance destroyed: {instance_id}")
                return True
            return False

    def health_check(self, agent_id: str) -> Dict[str, str]:
        """健康检查."""
        spec = self.get(agent_id)
        if spec is None:
            return {"status": "not_found", "message": f"Agent {agent_id} not registered"}
        handles = self.list_handles(agent_id)
        if not handles:
            return {"status": "no_instance", "message": "No running instances"}
        available = sum(1 for h in handles if h.is_available)
        if available == len(handles):
            return {"status": "ok", "message": f"All {len(handles)} instances available"}
        return {"status": "degraded", "message": f"{available}/{len(handles)} instances available"}

    def count(self) -> int:
        """注册数量."""
        with self._lock:
            return len(self._specs)

    def stats(self) -> Dict[str, int]:
        """统计."""
        with self._lock:
            return {
                "registered_agents": len(self._specs),
                "active_instances": len(self._handles),
                "available_instances": sum(
                    1 for h in self._handles.values() if h.is_available
                ),
            }
