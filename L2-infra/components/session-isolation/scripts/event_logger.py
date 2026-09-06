"""
会话隔离与共享组件 — 事件日志追加
Copyright (c) 2026 Bangcle, Inc. All rights reserved.
"""
import os
import json
from typing import Dict, Any, Tuple, List, Optional
from datetime import datetime
from .utils import (
    get_task_path,
    validate_task_id,
    IN_PROGRESS
)

class EventLogger:
    """事件日志 — append-only"""

    def log_event(
        self,
        task_id: str,
        event_type: str,
        data: Optional[Dict[str, Any]] = None,
        task_status: str = IN_PROGRESS
    ) -> Tuple[bool, str]:
        """
        追加一个事件日志
        :param task_id: 任务ID
        :param event_type: 事件类型 (task.created / goal.completed / subtask.spawned / ...)
        :param data: 事件附加数据
        :param task_status: 任务状态目录 (in-progress / done / archive)
        :return: (success, message)
        """
        valid, err = validate_task_id(task_id)
        if not valid:
            return False, err

        task_path = get_task_path(task_id, task_status)
        events_path = os.path.join(task_path, "events.jsonl")

        if not os.path.exists(task_path):
            return False, f"Task {task_id} not found at {task_path}"

        event = {
            "ts": datetime.now().astimezone().isoformat(),
            "type": event_type,
            **(data or {})
        }

        try:
            with open(events_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
            return True, f"Event {event_type} logged to {events_path}"
        except Exception as e:
            return False, f"Failed to log event: {str(e)}"

    def read_events(
        self,
        task_id: str,
        task_status: str = IN_PROGRESS,
        limit: Optional[int] = None
    ) -> Tuple[Optional[List[Dict[str, Any]]], str]:
        """
        读取全部事件，可限制条数
        :param task_id: 任务ID
        :param task_status: 任务状态目录
        :param limit: 最大返回条数 (None = 全部)
        :return: (events, error)
        """
        valid, err = validate_task_id(task_id)
        if not valid:
            return None, err

        task_path = get_task_path(task_id, task_status)
        events_path = os.path.join(task_path, "events.jsonl")

        if not os.path.exists(events_path):
            return None, f"Events file not found for task {task_id}"

        try:
            events = []
            with open(events_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    events.append(json.loads(line))
                    if limit is not None and len(events) >= limit:
                        break
            return events, ""
        except Exception as e:
            return None, f"Failed to read events: {str(e)}"

    def clear_events(
        self,
        task_id: str,
        task_status: str = IN_PROGRESS
    ) -> Tuple[bool, str]:
        """清空事件日志（归档压缩用）"""
        valid, err = validate_task_id(task_id)
        if not valid:
            return False, err

        task_path = get_task_path(task_id, task_status)
        events_path = os.path.join(task_path, "events.jsonl")

        if not os.path.exists(events_path):
            return False, f"Events file not found for task {task_id}"

        try:
            with open(events_path, "w", encoding="utf-8") as f:
                f.write("")
            return True, f"Events cleared for task {task_id}"
        except Exception as e:
            return False, f"Failed to clear events: {str(e)}"
