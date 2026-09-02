"""
L2 会话隔离与共享服务 — 核心服务层
Copyright (c) 2026 Bangcle, Inc. All rights reserved.
遵循 ADR-012：只依赖 L1 抽象契约，不绑定具体运行时
"""
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from adapters.openclaw.adapter import adapter as openclaw_adapter
from scripts.session_isolation.task_init import TaskInitializer
from scripts.session_isolation.state_reducer import StateReducer
from scripts.session_isolation.event_logger import EventLogger

@dataclass
class TaskInfo:
    """任务信息"""
    task_id: str
    name: str
    status: str
    created_at: str
    updated_at: str

class SessionIsolationService:
    """L2 会话隔离与共享核心服务"""

    def __init__(self):
        self.adapter = openclaw_adapter  # 依赖 L1 抽象接口，不绑定具体实现
        self.task_initializer = TaskInitializer()
        self.state_reducer = StateReducer()
        self.event_logger = EventLogger()

    def create_isolated_task(
        self,
        task_id: str,
        name: str,
        owner: str,
        scope_project: str,
        scope_component: str,
        scope_version: str,
        goals: List[Dict[str, str]],
        context_paths: Optional[List[str]] = None,
        priority: str = "medium"
    ) -> Tuple[bool, str]:
        """创建一个隔离任务，创建文件任务卡 + 记录事件"""
        # 先创建文件任务卡
        ok, msg = self.task_initializer.create_task(
            task_id=task_id,
            name=name,
            owner=owner,
            scope_project=scope_project,
            scope_component=scope_component,
            scope_version=scope_version,
            goals=goals,
            context_paths=context_paths,
            priority=priority
        )
        if not ok:
            return False, msg

        # 记录创建事件
        ok, evt_msg = self.event_logger.log_event(
            task_id=task_id,
            event_type="task.created",
            data={"by": owner}
        )
        if not ok:
            return False, f"Task created but failed to log event: {evt_msg}"

        return True, f"Isolated task {task_id} created successfully"

    def spawn_isolated_session(self, scope: str) -> Optional[str]:
        """生成一个隔离会话，返回会话key"""
        return self.adapter.session_create(scope)

    def send_to_isolated_session(self, session_key: str, message: str) -> bool:
        """发送消息到隔离会话"""
        return self.adapter.session_send(session_key, message)

    def get_isolated_session_history(self, session_key: str, limit: int = 100) -> Optional[List[Dict[str, Any]]]:
        """获取隔离会话历史"""
        return self.adapter.session_history(session_key, limit)

    def write_shared_state(
        self,
        scope: str,
        key: str,
        data: Any,
        reducer: str = "last-write-wins"
    ) -> Tuple[bool, str]:
        """写入共享状态（应用reducer）"""
        return self.state_reducer.write_state(scope, key, data, reducer)

    def read_shared_state(self, scope: str, key: str) -> Tuple[Optional[Any], str]:
        """读取共享状态"""
        return self.state_reducer.read_state(scope, key)

    def log_task_event(self, task_id: str, event_type: str, data: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
        """记录任务事件"""
        return self.event_logger.log_event(task_id, event_type, data)

    def get_task_events(self, task_id: str, limit: Optional[int] = None) -> Tuple[Optional[List[Dict[str, Any]]], str]:
        """获取任务事件日志"""
        return self.event_logger.read_events(task_id, limit)

    def update_task_goal_status(self, task_id: str, goal_id: str, status: str) -> Tuple[bool, str]:
        """更新任务目标状态"""
        from scripts.session_isolation.utils import load_task_yaml, save_task_yaml
        data, err = load_task_yaml(task_id)
        if err:
            return False, err

        # 更新目标状态
        found = False
        for goal in data.get("goals", []):
            if goal.get("id") == goal_id:
                goal["status"] = status
                found = True
                break

        if not found:
            return False, f"Goal {goal_id} not found in task {task_id}"

        # 更新更新时间
        from scripts.session_isolation.utils import get_current_datetime
        data["updated_at"] = get_current_datetime()

        ok, err = save_task_yaml(task_id, data)
        if not ok:
            return False, err

        # 记录更新事件
        self.log_task_event(task_id, "goal.updated", {"goal_id": goal_id, "new_status": status})
        return True, f"Goal {goal_id} status updated to {status}"

