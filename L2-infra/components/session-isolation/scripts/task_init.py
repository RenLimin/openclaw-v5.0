"""
会话隔离与共享组件 — 任务初始化
Copyright (c) 2026 Bangcle, Inc. All rights reserved.
"""
import os
from typing import Optional, Tuple, Dict, Any, List
import shutil
from .utils import (
    TEMPLATES_ROOT,
    IN_PROGRESS,
    validate_task_id,
    get_task_path,
    get_current_datetime,
    save_task_yaml,
    ensure_directory
)

class TaskInitializer:
    """任务初始化器 — 创建任务卡目录结构 + 模板填充"""

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
        priority: str = "medium"
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

        # 复制模板
        template_path = os.path.join(TEMPLATES_ROOT, "TASK.yml")
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                template = f.read()
        except Exception as e:
            shutil.rmtree(task_path)
            return False, f"Failed to read template: {str(e)}"

        # 填充模板
        now = get_current_datetime()
        filled = template\
            .replace("task-YYYYMMDD-NNN", task_id)\
            .replace("<任务名称>", name)\
            .replace("pending", "in-progress")\
            .replace("<负责人: main-agent / subagent-xxx / rex>", owner)\
            .replace("<项目名>", scope_project)\
            .replace("<组件名>", scope_component)\
            .replace("<版本号>", scope_version)\
            .replace("medium", priority)\
            .replace("YYYY-MM-DDTHH:MM:SS+08:00", now)

        # 写入TASK.yml
        task_yaml_path = os.path.join(task_path, "TASK.yml")
        try:
            with open(task_yaml_path, "w", encoding="utf-8") as f:
                f.write(filled)
        except Exception as e:
            shutil.rmtree(task_path)
            return False, f"Failed to write TASK.yml: {str(e)}"

        # 创建默认CONTEXT.md
        context_path = os.path.join(task_path, "CONTEXT.md")
        try:
            with open(context_path, "w", encoding="utf-8") as f:
                f.write(f"# CONTEXT.md — {name}\n\n> 本文件存储任务现场上下文，会话重置后读取即可恢复\n\n## 任务ID: {task_id}\n\n## 待填\n")
        except Exception as e:
            shutil.rmtree(task_path)
            return False, f"Failed to write CONTEXT.md: {str(e)}"

        # 创建默认events.jsonl
        events_path = os.path.join(task_path, "events.jsonl")
        try:
            with open(events_path, "w", encoding="utf-8") as f:
                f.write("")
        except Exception as e:
            shutil.rmtree(task_path)
            return False, f"Failed to write events.jsonl: {str(e)}"

        # 如果有上下文路径，添加到TASK.yml
        if context_paths:
            from .utils import load_task_yaml
            data, err = load_task_yaml(task_id)
            if err:
                shutil.rmtree(task_path)
                return False, err
            data["context"] = [{"path": p} for p in context_paths]
            ok, err = save_task_yaml(task_id, data)
            if not ok:
                shutil.rmtree(task_path)
                return False, err

        return True, f"Task {task_id} created successfully at {task_path}"
