"""
会话隔离组件 — 任务初始化
Copyright (c) 2026 Bangcle, Inc. All rights reserved.
"""
import os
from typing import Optional, Tuple, Dict, Any, List
import shutil
import yaml

from utils import (
    TEMPLATES_ROOT,
    IN_PROGRESS,
    validate_task_id,
    get_task_path,
    get_current_datetime,
    save_task_yaml,
    ensure_directory
)


class TaskInitializer:
    """任务初始化器 — 创建任务卡目录结构 + YAML 填充"""

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
        """
        创建新任务
        :param task_id: 任务ID (task-YYYYMMDD-slug)
        :param name: 任务名称
        :param owner: 负责人 (main-agent / subagent-id / rex)
        :param scope_project: 项目名称
        :param scope_component: 组件名称
        :param scope_version: 版本
        :param goals: 目标列表 [{"id": "g1", "description": "...", "status": "pending"}, ...]
        :param context_paths: 上下文文件路径列表 (相对 workspace 根)
        :param priority: 优先级 low/medium/high/urgent
        :param initial_status: 初始状态 (pending / in-progress)
        :param dependencies: 依赖任务ID列表
        :return: (success, message)
        """
        # 验证ID
        valid, err = validate_task_id(task_id)
        if not valid:
            return False, err

        task_path = get_task_path(task_id, IN_PROGRESS)
        if os.path.exists(task_path):
            return False, f"Task {task_id} already exists at {task_path}"

        # 创建目录
        ok, err = ensure_directory(task_path)
        if not ok:
            return False, err

        now = get_current_datetime()

        # 结构化构建任务数据（不再做脆弱的字符串替换）
        task_data = {
            "id": task_id,
            "name": name,
            "status": initial_status,
            "priority": priority,
            "created_at": now,
            "updated_at": now,
            "owner": owner,
            "scope": {
                "project": scope_project,
                "component": scope_component,
                "version": scope_version,
            },
            "goals": goals if goals else [],
            "dependencies": dependencies or [],
            "blockers": [],
            "context": [{"path": p} for p in (context_paths or [])],
            "artifacts": [],
        }

        # 写入 TASK.yml
        task_yaml_path = os.path.join(task_path, "TASK.yml")
        try:
            with open(task_yaml_path, "w", encoding="utf-8") as f:
                yaml.dump(
                    task_data, f,
                    default_flow_style=False,
                    sort_keys=False,
                    allow_unicode=True,
                )
        except Exception as e:
            shutil.rmtree(task_path)
            return False, f"Failed to write TASK.yml: {str(e)}"

        # 创建默认 CONTEXT.md
        context_path = os.path.join(task_path, "CONTEXT.md")
        try:
            with open(context_path, "w", encoding="utf-8") as f:
                f.write(
                    f"# CONTEXT.md — {name}\n\n"
                    f"> 本文件存储任务现场上下文，会话重置后读取即可恢复\n\n"
                    f"## 任务ID: {task_id}\n\n"
                    f"## 待填\n"
                )
        except Exception as e:
            shutil.rmtree(task_path)
            return False, f"Failed to write CONTEXT.md: {str(e)}"

        # 创建空 events.jsonl
        events_path = os.path.join(task_path, "events.jsonl")
        try:
            with open(events_path, "w", encoding="utf-8") as f:
                f.write("")
        except Exception as e:
            shutil.rmtree(task_path)
            return False, f"Failed to write events.jsonl: {str(e)}"

        return True, f"Task {task_id} created successfully at {task_path}"
