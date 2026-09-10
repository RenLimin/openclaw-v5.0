"""
任务编排调度器 — 任务依赖排序 + 错峰发起 + 状态回写
Copyright (c) 2026 Bangcle, Inc. All rights reserved.
遵循 ADR-012 运行时抽象：核心逻辑纯 Python，不绑定任何具体 AI Agent 运行时
仅依赖任务卡协议，依赖 L1 适配层实现会话发起接口
"""

import os
import sys
import time
import yaml
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Any, Tuple
from pathlib import Path

# 兼容两种导入方式：
# 1. 作为包使用：from session-isolation.scheduler import ...（相对 import）
# 2. 直接运行或从 scripts 目录导入：sys.path 注入
try:
    from .scripts.utils import (
        get_task_path, IN_PROGRESS, load_task_yaml,
        save_task_yaml, get_current_datetime
    )
except (ImportError, ValueError):
    # 非包模式，从 scripts 目录导入
    _scripts_dir = Path(__file__).resolve().parent / "scripts"
    if str(_scripts_dir) not in sys.path:
        sys.path.insert(0, str(_scripts_dir))
    from utils import (
        get_task_path, IN_PROGRESS, load_task_yaml,
        save_task_yaml, get_current_datetime
    )


@dataclass
class Task:
    """任务数据类 — 对应 TASK.yml 结构"""
    id: str
    name: str
    status: str = "pending"
    dependencies: List[str] = field(default_factory=list)
    priority: str = "medium"
    scope: Dict[str, str] = field(default_factory=dict)
    goals: List[Dict[str, str]] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    context: List[Dict[str, str]] = field(default_factory=list)
    artifacts: List[Dict[str, str]] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    owner: str = ""
    file_path: str = ""

    def is_pending(self) -> bool:
        return self.status == "pending"

    def is_blocked_by_unmet_deps(self, done_tasks: set) -> bool:
        """检查是否有未完成依赖"""
        for dep in self.dependencies:
            if dep not in done_tasks:
                return True
        return False

    def save(self) -> None:
        """回写状态到文件"""
        task_dict = {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "dependencies": self.dependencies,
            "priority": self.priority,
            "scope": self.scope,
            "goals": self.goals,
            "blockers": self.blockers,
            "context": self.context,
            "artifacts": self.artifacts,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "owner": self.owner,
        }
        with open(self.file_path, "w", encoding="utf-8") as f:
            yaml.dump(task_dict, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    @classmethod
    def from_yaml(cls, file_path: str) -> "Task":
        """从 YAML 文件加载 Task"""
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            status=data.get("status", "pending"),
            dependencies=data.get("dependencies", []),
            priority=data.get("priority", "medium"),
            scope=data.get("scope", {}),
            goals=data.get("goals", []),
            blockers=data.get("blockers", []),
            context=data.get("context", []),
            artifacts=data.get("artifacts", []),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            owner=data.get("owner", ""),
            file_path=file_path,
        )


class TaskScheduler:
    """
    多任务编排调度器
    输入：任务卡目录，输出：错峰分批发起，完成后回写状态
    职责：只做排序和错峰，并发控制交给运行时原生能力
    """

    def __init__(
        self,
        tasks_dir: str = IN_PROGRESS,
        default_start_interval_sec: float = 10.0,
        task_loader: Optional[Callable[[str], Task]] = None,
    ):
        """
        :param tasks_dir: 待办任务目录 relative to tasks/ (default: in-progress)
        :param default_start_interval_sec: 可并行任务启动间隔，默认 10s (避免 burst 限流)
        :param task_loader: 可选自定义任务加载器
        """
        self.tasks_dir = os.path.join("tasks", tasks_dir)
        self.default_start_interval_sec = default_start_interval_sec
        self.task_loader = task_loader if task_loader else Task.from_yaml

    def load_pending_tasks(self) -> List[Task]:
        """加载所有 pending 任务"""
        pending: List[Task] = []
        tasks_root = Path(self.tasks_dir)
        if not tasks_root.exists():
            return pending

        for task_dir in sorted(tasks_root.iterdir()):
            if not task_dir.is_dir():
                continue
            task_file = task_dir / "TASK.yml"
            if not task_file.exists():
                continue
            task = self.task_loader(str(task_file))
            if task.is_pending():
                pending.append(task)
        return pending

    def topological_sort(self, tasks: List[Task]) -> Tuple[List[List[Task]], List[str]]:
        """
        拓扑排序 → 输出批次：每批内任务无依赖，可并行
        同批次内按优先级排序（urgent > high > medium > low）
        返回：(批次列表, 已完成任务id列表)
        """
        adj: Dict[str, List[str]] = {}
        in_degree: Dict[str, int] = {}

        task_map: Dict[str, Task] = {t.id: t for t in tasks}
        all_task_ids = set(task_map.keys())

        for tid in all_task_ids:
            adj[tid] = []
            in_degree[tid] = 0

        for task in tasks:
            for dep in task.dependencies:
                if dep in all_task_ids:
                    adj[dep].append(task.id)
                    in_degree[task.id] += 1

        priority_order = {"urgent": 0, "high": 1, "medium": 2, "low": 3}

        queue: List[str] = sorted(
            [tid for tid in all_task_ids if in_degree[tid] == 0],
            key=lambda t: priority_order.get(task_map[t].priority, 99)
        )
        done: List[str] = []
        batches: List[List[Task]] = []

        while queue:
            current_batch: List[Task] = []
            for tid in queue:
                current_batch.append(task_map[tid])
                done.append(tid)
            batches.append(current_batch)

            next_queue: List[str] = []
            for tid in queue:
                for neighbor in adj[tid]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        next_queue.append(neighbor)
            next_queue.sort(key=lambda t: priority_order.get(task_map[t].priority, 99))
            queue = next_queue

        # 有环检测
        if len(done) != len(all_task_ids):
            return [], []

        return batches, done

    def run(
        self,
        spawn_callback: Callable[[Task], bool],
        interval_sec: Optional[float] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        运行调度：按拓扑排序分批错峰发起任务
        :param spawn_callback: 发起会话回调 → 输入 Task，输出是否成功发起
        :param interval_sec: 可并行批次内启动间隔，None → 使用默认
        :param dry_run: 只排序不发起，用于测试
        :return: 调度结果统计
        """
        interval = interval_sec if interval_sec is not None else self.default_start_interval_sec
        pending_tasks = self.load_pending_tasks()
        if not pending_tasks:
            return {
                "total_pending": 0,
                "batches": 0,
                "started": 0,
                "status": "no pending tasks",
                "failed": [],
            }

        batches, done_ids = self.topological_sort(pending_tasks)
        if not batches:
            return {
                "total_pending": len(pending_tasks),
                "batches": 0,
                "started": 0,
                "status": "cycle detected in dependencies",
                "failed": [],
            }

        total_started = 0
        failed: List[str] = []

        for batch_idx, batch in enumerate(batches):
            for i, task in enumerate(batch):
                if dry_run:
                    total_started += 1
                    continue

                success = spawn_callback(task)
                if success:
                    task.status = "in-progress"
                    total_started += 1
                else:
                    failed.append(task.id)
                task.updated_at = get_current_datetime()
                task.save()
                # 同批内任务间隔
                if i < len(batch) - 1:
                    time.sleep(interval)

        return {
            "total_pending": len(pending_tasks),
            "batches": len(batches),
            "started": total_started,
            "status": "completed",
            "failed": failed,
        }
