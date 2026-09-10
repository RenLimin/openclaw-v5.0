"""
L2 会话隔离组件 — 统一 API 导出
Copyright (c) 2026 Bangcle, Inc. All rights reserved.

组件包含：
- Task Protocol: 任务卡协议（YAML 文件）
- State Protocol: 共享状态协议（带 reducer 的确定性合并）
- Event Protocol: 事件日志协议（append-only）
- Task Scheduler: 多任务编排调度器（依赖排序 + 错峰发起）
- Task Spawner: OpenClaw 子会话发起适配层
"""

__all__ = [
    "SessionIsolationService",
    "TaskInfo",
    "TaskScheduler",
    "Task",
    "TaskInitializer",
    "StateReducer",
    "EventLogger",
    "OpenClawTaskSpawner",
]


def __getattr__(name):
    """延迟导入，避免循环依赖和非包路径 import 失败"""
    if name == "SessionIsolationService":
        from .service import SessionIsolationService
        return SessionIsolationService
    if name == "TaskInfo":
        from .service import TaskInfo
        return TaskInfo
    if name == "TaskScheduler":
        from .scheduler import TaskScheduler
        return TaskScheduler
    if name == "Task":
        from .scheduler import Task
        return Task
    if name == "TaskInitializer":
        from .scripts.task_init import TaskInitializer
        return TaskInitializer
    if name == "StateReducer":
        from .scripts.state_reducer import StateReducer
        return StateReducer
    if name == "EventLogger":
        from .scripts.event_logger import EventLogger
        return EventLogger
    if name == "OpenClawTaskSpawner":
        from .adapters.openclaw.spawner import OpenClawTaskSpawner
        return OpenClawTaskSpawner
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
