"""BDMS 集成模块同步调度器 — cron 定时 + event 事件驱动.

Aligns with DESIGN-DETAIL-INTEGRATION-v2.1.md §7.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from .error_handler import DeadLetterQueue, SyncStatus

logger = logging.getLogger(__name__)


class FrequencyType(str, Enum):
    """同步频率类型"""
    MANUAL = "manual"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    EVENT = "event"  # 事件驱动（比如合同创建后触发项目同步）


@dataclass
class SyncConfig:
    """单个连接器同步配置"""
    connector_name: str
    frequency_type: FrequencyType
    cron_expression: Optional[str] = None  # 标准 cron 表达式
    parameters: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class SyncTask:
    """待执行的同步任务"""
    config: SyncConfig
    scheduled_at: datetime
    status: SyncStatus = SyncStatus.PENDING
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error: Optional[str] = None


class SyncScheduler:
    """同步任务调度器.

    负责：
    1. 存储所有连接器同步配置
    2. 计算下一次执行时间
    3. 取出到期任务执行
    4. 记录任务执行状态
    """

    def __init__(self, dlq: DeadLetterQueue):
        self.dlq = dlq
        self._configs: Dict[str, SyncConfig] = {}  # key: connector_name
        self._queue: List[SyncTask] = []

    def add_config(self, config: SyncConfig) -> None:
        """Add or update sync configuration"""
        if config.connector_name in self._configs:
            logger.info(f"Updating sync config for {config.connector_name}")
            old = self._configs[config.connector_name]
            config.created_at = old.created_at
            config.updated_at = datetime.now()
        else:
            logger.info(f"Adding new sync config for {config.connector_name}")
        self._configs[config.connector_name] = config
        self._schedule_next(config)
        logger.info(f"Config added/updated: {config.connector_name}")

    def remove_config(self, connector_name: str) -> bool:
        """Remove sync configuration"""
        if connector_name not in self._configs:
            return False
        del self._configs[connector_name]
        # Remove from queue
        self._queue = [t for t in self._queue if t.config.connector_name != connector_name]
        logger.info(f"Config removed: {connector_name}")
        return True

    def list_configs(self) -> List[SyncConfig]:
        """List all sync configurations"""
        return list(self._configs.values())

    def get_config(self, connector_name: str) -> Optional[SyncConfig]:
        """Get config by connector name"""
        return self._configs.get(connector_name)

    def schedule_now(self, connector_name: str) -> Optional[SyncTask]:
        """Schedule a task to run immediately"""
        config = self.get_config(connector_name)
        if not config:
            logger.warning(f"Cannot schedule now: no config for {connector_name}")
            return None
        task = SyncTask(
            config=config,
            scheduled_at=datetime.now(),
        )
        self._queue.append(task)
        logger.info(f"Scheduled immediately: {connector_name}")
        return task

    def pop_due_tasks(self) -> List[SyncTask]:
        """Get all due tasks to run now"""
        now = datetime.now()
        due = [t for t in self._queue if t.scheduled_at <= now and t.status == SyncStatus.PENDING and t.config.enabled]
        self._queue = [t for t in self._queue if not (t.scheduled_at <= now and t.status == SyncStatus.PENDING and t.config.enabled)]
        if due:
            logger.info(f"Popped {len(due)} due tasks")
        return due

    def mark_started(self, task: SyncTask) -> None:
        """Mark task as started"""
        task.status = SyncStatus.IN_PROGRESS
        task.started_at = datetime.now()

    def mark_finished(self, task: SyncTask, success: bool, error: Optional[str] = None) -> None:
        """Mark task as finished"""
        task.finished_at = datetime.now()
        if success:
            task.status = SyncStatus.SUCCESS
            logger.info(f"Task succeeded: {task.config.connector_name}")
        else:
            task.status = SyncStatus.PERMANENT_FAILURE
            task.error = error
            # Add to dead letter queue
            self.dlq.add(
                source_id=f"{task.config.connector_name}-{datetime.now().isoformat()}",
                source_type="sync_task",
                error=error or "unknown error",
                metadata={
                    "connector_name": task.config.connector_name,
                    "scheduled_at": task.scheduled_at.isoformat(),
                }
            )
            logger.error(f"Task failed: {task.config.connector_name}, error: {error}")
        # Schedule next run for periodic tasks
        if task.config.frequency_type != FrequencyType.MANUAL:
            self._schedule_next(task.config)

    def _schedule_next(self, config: SyncConfig) -> None:
        """Schedule next run based on frequency"""
        next_at = self._calculate_next_run(config.frequency_type)
        if not next_at:
            return
        task = SyncTask(
            config=config,
            scheduled_at=next_at,
        )
        self._queue.append(task)
        logger.debug(f"Scheduled next run for {config.connector_name} at {next_at}")

    def _calculate_next_run(self, frequency: FrequencyType) -> Optional[datetime]:
        """Calculate next run time based on frequency"""
        now = datetime.now()
        match frequency:
            case FrequencyType.DAILY:
                # Next day same time
                next_day = now + timedelta(days=1)
                return datetime(next_day.year, next_day.month, next_day.day, now.hour, now.minute)
            case FrequencyType.WEEKLY:
                # Next week same day/time
                next_week = now + timedelta(weeks=1)
                return datetime(next_week.year, next_week.month, next_week.day, now.hour, now.minute)
            case FrequencyType.MONTHLY:
                # Next month same day/time
                year = now.year
                month = now.month + 1
                if month > 12:
                    month = 1
                    year += 1
                try:
                    return datetime(year, month, now.day, now.hour, now.minute)
                except ValueError:
                    # Handle month with fewer days (e.g. 31 -> 30/28/29)
                    # Roll to first day of next month
                    if month == 12:
                        return datetime(year + 1, 1, 1, now.hour, now.minute)
                    else:
                        return datetime(year, month + 1, 1, now.hour, now.minute)
            case _:  # manual/event don't auto-schedule
                return None

    def get_queue_size(self) -> int:
        """Get pending queue size"""
        return len([t for t in self._queue if t.status == SyncStatus.PENDING])
