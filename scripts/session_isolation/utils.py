"""
会话隔离与共享组件 — 通用工具
Copyright (c) 2026 Bangcle, Inc. All rights reserved.
"""
import os
import re
from datetime import datetime
from typing import Optional, Tuple, Dict, Any
import yaml

# 常量定义
TASKS_ROOT = "tasks"
TEMPLATES_ROOT = os.path.join(TASKS_ROOT, "_templates")
IN_PROGRESS = "in-progress"
DONE = "done"
ARCHIVE = "archive"

def validate_task_id(task_id: str) -> Tuple[bool, str]:
    """验证任务ID格式: task-YYYYMMDD-slug (slug: 字母/数字/-)"""
    pattern = r'^task-\d{8}-[a-zA-Z0-9-]+$'
    if not re.match(pattern, task_id):
        return False, f"Invalid task_id format: {task_id}, expected: task-YYYYMMDD-slug"
    return True, ""

def get_task_path(task_id: str, status: str = IN_PROGRESS) -> str:
    """获取任务根路径"""
    return os.path.join(TASKS_ROOT, status, task_id)

def get_current_datetime() -> str:
    """获取当前格式化时间 (RFC 3339)"""
    return datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")

def load_task_yaml(task_id: str, status: str = IN_PROGRESS) -> Tuple[Optional[Dict[str, Any]], str]:
    """加载任务YAML"""
    valid, err = validate_task_id(task_id)
    if not valid:
        return None, err

    task_path = get_task_path(task_id, status)
    task_yaml_path = os.path.join(task_path, "TASK.yml")
    if not os.path.exists(task_yaml_path):
        return None, f"Task {task_id} not found at {task_yaml_path}"

    try:
        with open(task_yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data, ""
    except Exception as e:
        return None, f"Failed to load TASK.yml: {str(e)}"

def save_task_yaml(task_id: str, data: Dict[str, Any], status: str = IN_PROGRESS) -> Tuple[bool, str]:
    """保存任务YAML"""
    valid, err = validate_task_id(task_id)
    if not valid:
        return False, err

    task_path = get_task_path(task_id, status)
    os.makedirs(task_path, exist_ok=True)
    task_yaml_path = os.path.join(task_path, "TASK.yml")

    try:
        with open(task_yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        return True, ""
    except Exception as e:
        return False, f"Failed to save TASK.yml: {str(e)}"

def ensure_directory(path: str) -> Tuple[bool, str]:
    """确保目录存在，不存在则创建"""
    try:
        os.makedirs(path, exist_ok=True)
        return True, ""
    except Exception as e:
        return False, f"Failed to create directory {path}: {str(e)}"
