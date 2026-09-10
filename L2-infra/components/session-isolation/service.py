"""
L2 会话隔离组件 — 核心服务层
Copyright (c) 2026 Bangcle, Inc. All rights reserved.
遵循 ADR-012：只依赖 L1 抽象契约，不绑定具体运行时
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass

# 兼容包和非包两种导入方式
try:
    from .scripts.task_init import TaskInitializer
    from .scripts.state_reducer import StateReducer
    from .scripts.event_logger import EventLogger
    from .scheduler import TaskScheduler, Task
except (ImportError, ValueError):
    _root = Path(__file__).resolve().parent
    _scripts = _root / "scripts"
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))
    if str(_scripts) not in sys.path:
        sys.path.insert(0, str(_scripts))
    from task_init import TaskInitializer
    from state_reducer import StateReducer
    from event_logger import EventLogger
    from scheduler import TaskScheduler, Task


@dataclass
class TaskInfo:
    """任务信息"""
    task_id: str
    name: str
    status: str
    created_at: str
    updated_at: str


class SessionIsolationService:
    """L2 会话隔离核心服务 — 统一入口"""

    def __init__(self):
        self.task_initializer = TaskInitializer()
        self.state_reducer = StateReducer()
        self.event_logger = EventLogger()
        self._scheduler = None

    # ---- Task Protocol ----

    def create_task(
        self,
        task_id: str,
        name: str,
        owner: str,
        scope_project: str,
        scope_component: str,
        scope_version: str,
        goals: List[Dict[str, str]],
        context_paths: Optional[List[str]] = None,
        priority: str = "medium",
        initial_status: str = "in-progress",
        dependencies: Optional[List[str]] = None,
    ) -> Tuple[bool, str]:
        """创建一个隔离任务，创建文件任务卡 + 记录事件"""
        ok, msg = self.task_initializer.create_task(
            task_id=task_id,
            name=name,
            owner=owner,
            scope_project=scope_project,
            scope_component=scope_component,
            scope_version=scope_version,
            goals=goals,
            context_paths=context_paths,
            priority=priority,
            initial_status=initial_status,
            dependencies=dependencies,
        )
        if not ok:
            return False, msg

        ok, evt_msg = self.event_logger.log_event(
            task_id=task_id,
            event_type="task.created",
            data={"by": owner},
        )
        if not ok:
            return False, f"Task created but failed to log event: {evt_msg}"

        return True, f"Isolated task {task_id} created successfully"

    def update_task_goal_status(
        self, task_id: str, goal_id: str, status: str
    ) -> Tuple[bool, str]:
        """更新任务目标状态"""
        try:
            from .scripts.utils import load_task_yaml, save_task_yaml, get_current_datetime
        except (ImportError, ValueError):
            from utils import load_task_yaml, save_task_yaml, get_current_datetime

        data, err = load_task_yaml(task_id)
        if err:
            return False, err

        found = False
        for goal in data.get("goals", []):
            if goal.get("id") == goal_id:
                goal["status"] = status
                found = True
                break

        if not found:
            return False, f"Goal {goal_id} not found in task {task_id}"

        data["updated_at"] = get_current_datetime()

        ok, err = save_task_yaml(task_id, data)
        if not ok:
            return False, err

        self.log_task_event(
            task_id, "goal.updated", {"goal_id": goal_id, "new_status": status}
        )
        return True, f"Goal {goal_id} status updated to {status}"

    # ---- State Protocol ----

    def write_shared_state(
        self,
        scope: str,
        key: str,
        data: Any,
        reducer: str = "last-write-wins",
    ) -> Tuple[bool, str]:
        """写入共享状态（应用 reducer）"""
        return self.state_reducer.write_state(scope, key, data, reducer)

    def read_shared_state(self, scope: str, key: str) -> Tuple[Optional[Any], str]:
        """读取共享状态"""
        return self.state_reducer.read_state(scope, key)

    def list_shared_states(self, scope: str) -> Tuple[Optional[List[str]], str]:
        """列出 scope 下所有状态键"""
        return self.state_reducer.list_states(scope)

    def delete_shared_state(self, scope: str, key: str) -> Tuple[bool, str]:
        """删除共享状态"""
        return self.state_reducer.delete_state(scope, key)

    # ---- Event Protocol ----

    def log_task_event(
        self, task_id: str, event_type: str, data: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, str]:
        """记录任务事件"""
        return self.event_logger.log_event(task_id, event_type, data)

    def get_task_events(
        self, task_id: str, limit: Optional[int] = None
    ) -> Tuple[Optional[List[Dict[str, Any]]], str]:
        """获取任务事件日志"""
        return self.event_logger.read_events(task_id, limit=limit)

    # ---- Scheduler ----

    def get_scheduler(self, **kwargs) -> TaskScheduler:
        """获取调度器实例（懒加载）"""
        if self._scheduler is None:
            self._scheduler = TaskScheduler(**kwargs)
        return self._scheduler

    def run_scheduler(
        self,
        spawn_callback: Callable[[Task], bool],
        interval_sec: Optional[float] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """运行任务调度器，发起所有 pending 任务"""
        sched = self.get_scheduler()
        return sched.run(
            spawn_callback=spawn_callback,
            interval_sec=interval_sec,
            dry_run=dry_run,
        )
