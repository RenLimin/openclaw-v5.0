"""
会话编排调度器 — 任务依赖排序 + 错峰发起 + 状态回写
Copyright (c) 2026 Bangcle, Inc. All rights reserved.
遵循 ADR-012 运行时抽象：核心逻辑纯 Python，不绑定任何具体 AI Agent 运行时
仅依赖任务卡协议，依赖 L1 适配层实现会话发起接口
"""

import os
import sys
import time
import yaml
from dataclasses import dataclass
from typing import List, Dict, Optional, Callable, Any, Tuple
from pathlib import Path

# 导入当前组件工具
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils import get_task_path, IN_PROGRESS

@dataclass
class Task:
    id: str
    name: str
    status: str
    dependencies: List[str]
    priority: str
    scope: Dict[str, str]
    goals: List[Dict[str, str]]
    blockers: List[str]
    context: List[Dict[str, str]]
    artifacts: List[Dict[str, str]]
    created_at: str
    updated_at: str
    owner: str
    file_path: str

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
            yaml.dump(task_dict, f, allow_unicode=True, default_flow_style=False)

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
        :param tasks_dir: 待办任务目录 (tasks/in-progress)
        :param default_start_interval_sec: 可并行任务启动间隔，默认 10s (避免 burst 限流)
        :param task_loader: 可选自定义任务加载器
        """
        self.tasks_dir = tasks_dir
        self.default_start_interval_sec = default_start_interval_sec
        self.task_loader = task_loader if task_loader else self._default_task_loader

    def _default_task_loader(self, task_file: str) -> Task:
        """默认任务加载器：从 YAML 文件加载"""
        with open(task_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return Task(
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
            file_path=task_file,
        )

    def load_pending_tasks(self) -> List[Task]:
        """加载所有 pending 任务"""
        pending: List[Task] = []
        tasks_root = Path(self.tasks_dir)
        if not tasks_root.exists():
            return pending

        for task_dir in tasks_root.iterdir():
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
        返回：(批次列表, 已完成任务集合)
        """
        # 建立依赖图
        adj: Dict[str, List[str]] = {}  # taskid → 依赖它的任务
        in_degree: Dict[str, int] = {}  # taskid → 入度

        task_map: Dict[str, Task] = {t.id: t for t in tasks}
        all_task_ids = set(task_map.keys())

        # 初始化图
        for tid in all_task_ids:
            adj[tid] = []
            in_degree[tid] = 0

        for task in tasks:
            for dep in task.dependencies:
                if dep in all_task_ids:  # 依赖也在待办中
                    adj[dep].append(task.id)
                    in_degree[task.id] += 1

        # Kahn 算法拓扑排序
        queue: List[str] = [tid for tid in all_task_ids if in_degree[tid] == 0]
        done: List[str] = []
        batches: List[List[Task]] = []

        while queue:
            # 这一批是当前入度为 0 的所有任务，可以并行
            current_batch: List[Task] = []
            for tid in queue:
                current_batch.append(task_map[tid])
                done.append(tid)
            batches.append(current_batch)
            # 更新下一批入度
            next_queue: List[str] = []
            for tid in queue:
                for neighbor in adj[tid]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        next_queue.append(neighbor)
            queue = next_queue

        # 检查环（拓扑排序后还有入度>0 → 有环）
        if len(done) != len(all_task_ids):
            # 有循环依赖，返回空
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
            }

        batches, done_ids = self.topological_sort(pending_tasks)
        if not batches:
            return {
                "total_pending": len(pending_tasks),
                "batches": 0,
                "started": 0,
                "status": "cycle detected in dependencies",
            }

        total_started = 0
        stats = {
            "total_pending": len(pending_tasks),
            "batches": len(batches),
            "started": 0,
            "status": "running",
        }

        for batch_idx, batch in enumerate(batches):
            print(f"\n=== 批次 {batch_idx+1}/{len(batches)} (可并行 {len(batch)} 个任务) ===")
            for task in batch:
                if dry_run:
                    print(f"[dry-run] 准备发起: {task.id} - {task.name}")
                    total_started += 1
                    continue

                print(f"发起任务: {task.id} - {task.name}")
                success = spawn_callback(task)
                if success:
                    task.status = "in-progress"
                    total_started += 1
                else:
                    print(f"⚠️  发起失败: {task.id}")
                task.updated_at = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())
                task.save()
                # 间隔等待（下一个任务）
                if batch_idx != len(batches) - 1 or task is not batch[-1]:
                    print(f"等待 {interval}s 后发起下一个...")
                    time.sleep(interval)

        stats["started"] = total_started
        stats["status"] = "completed"
        print(f"\n=== 调度完成: 共 {total_started}/{len(pending_tasks)} 任务发起成功 ===")

        return stats
