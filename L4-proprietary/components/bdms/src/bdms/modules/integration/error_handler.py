"""BDMS 集成模块错误处理 — RetryHandler + DeadLetterQueue + AlertManager.

Aligns with DESIGN-DETAIL-INTEGRATION-v2.1.md §9.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class SyncStatus(str, Enum):
    """同步任务状态"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    PERMANENT_FAILURE = "permanent_failure"
    TRANSIENT_FAILURE = "transient_failure"
    RETRYING = "retrying"


@dataclass
class RetryConfig:
    """重试配置"""
    max_retries: int = 4  # 初始 + 3次重试 = 总尝试 4次
    initial_delay: float = 1.0  # 秒
    backoff_factor: float = 2.0  # 指数退避因子


class RetryHandler:
    """指数退避重试处理器.

    Usage:
        retry_handler = RetryHandler(RetryConfig(max_retries=3))
        result = retry_handler.run(
            callable=my_sync_func,
            args=(arg1, arg2),
            kwargs={"key": value},
            is_transient_error=lambda e: "timeout" in str(e).lower()
        )
    """

    def __init__(self, config: RetryConfig):
        self.config = config

    def run(
        self,
        func: Callable[..., Any],
        args: Tuple[Any, ...] = (),
        kwargs: Dict[str, Any] = None,
        is_transient_error: Optional[Callable[[Exception], bool]] = None,
    ) -> Tuple[bool, Any, Optional[Exception]]:
        """Run function with retries.

        Returns:
            (success, result, last_exception)
            success: True if any attempt succeeded
            result: return value of func if success, else None
            last_exception: last exception if failed
        """
        if kwargs is None:
            kwargs = {}

        delay = self.config.initial_delay
        last_exception = None
        result = None

        for attempt in range(self.config.max_retries):
            try:
                result = func(*args, **kwargs)
                return (True, result, None)
            except Exception as e:
                last_exception = e
                # 默认：所有异常都是 transient，除非用户判断不是
                if is_transient_error is not None and not is_transient_error(e):
                    logger.warning(f"Non-transient error on attempt {attempt+1}/{self.config.max_retries}: {e}")
                    return (False, None, e)

                logger.warning(
                    f"Transient error on attempt {attempt+1}/{self.config.max_retries}: {e}. "
                    f"Retrying in {delay:.1f}s..."
                )
                time.sleep(delay)
                delay *= self.config.backoff_factor

        logger.error(f"All {self.config.max_retries} attempts failed. Last error: {last_exception}")
        return (False, None, last_exception)


@dataclass
class DeadLetterEntry:
    """死信条目"""
    source_id: str
    source_type: str
    error: str
    created_at: datetime = field(default_factory=datetime.now)
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    retry_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class DeadLetterQueue:
    """死信队列 — 存储永久失败的同步任务，支持手动解决和重试.

    Persisted as JSON lines for simplicity.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.db_path.exists():
            self.db_path.touch()

    def add(
        self,
        source_id: str,
        source_type: str,
        error: str,
        metadata: Dict[str, Any] = None,
    ) -> None:
        """Add a new dead letter entry"""
        entry = DeadLetterEntry(
            source_id=source_id,
            source_type=source_type,
            error=error,
            metadata=metadata or {},
        )
        self._append(entry)
        logger.info(f"Added dead letter: {source_type}/{source_id}")

    def resolve(
        self,
        source_id: str,
        source_type: str,
        resolved_by: str,
    ) -> bool:
        """Mark entry as resolved.

        Returns:
            True if entry found and marked, False otherwise
        """
        entries = self._load()
        found = False
        updated = []
        for entry in entries:
            if entry.source_id == source_id and entry.source_type == source_type:
                entry.resolved = True
                entry.resolved_at = datetime.now()
                entry.resolved_by = resolved_by
                found = True
            updated.append(entry)
        self._save(updated)
        if found:
            logger.info(f"Resolved dead letter: {source_type}/{source_id}")
        return found

    def list_unresolved(self) -> List[DeadLetterEntry]:
        """List all unresolved entries"""
        entries = self._load()
        return [e for e in entries if not e.resolved]

    def count_unresolved(self) -> int:
        """Count unresolved entries"""
        return len(self.list_unresolved())

    def retry(self, source_id: str, source_type: str, retry_func: Callable[[DeadLetterEntry], bool]) -> bool:
        """Retry a specific dead letter entry.

        Args:
            retry_func: returns True if retry succeeded
        """
        entries = self._load()
        for entry in entries:
            if (
                entry.source_id == source_id
                and entry.source_type == source_type
                and not entry.resolved
            ):
                entry.retry_count += 1
                success = retry_func(entry)
                if success:
                    entry.resolved = True
                    entry.resolved_at = datetime.now()
                    entry.resolved_by = "auto-retry"
                    logger.info(f"Retry succeeded for {source_type}/{source_id}")
                else:
                    logger.warning(f"Retry failed for {source_type}/{source_id}")
                self._save(entries)
                return success
        logger.warning(f"Entry not found: {source_type}/{source_id}")
        return False

    def retry_all_unresolved(self, retry_func: Callable[[DeadLetterEntry], bool]) -> Tuple[int, int]:
        """Retry all unresolved entries.

        Returns:
            (total, success_count)
        """
        entries = self.list_unresolved()
        success = 0
        for entry in entries:
            if self.retry(entry.source_id, entry.source_type, retry_func):
                success += 1
        return (len(entries), success)

    def _load(self) -> List[DeadLetterEntry]:
        """Load all entries from file"""
        entries: List[DeadLetterEntry] = []
        with open(self.db_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    entry = DeadLetterEntry(**data)
                    # Parse datetime
                    if isinstance(entry.created_at, str):
                        entry.created_at = datetime.fromisoformat(entry.created_at)
                    if entry.resolved_at and isinstance(entry.resolved_at, str):
                        entry.resolved_at = datetime.fromisoformat(entry.resolved_at)
                    entries.append(entry)
                except Exception as e:
                    logger.error(f"Failed to parse dead letter line: {line[:100]}... error: {e}")
                    continue
        return entries

    def _append(self, entry: DeadLetterEntry) -> None:
        """Append new entry to file"""
        with open(self.db_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(entry), default=str) + "\n")

    def _save(self, entries: List[DeadLetterEntry]) -> None:
        """Rewrite entire file with updated entries"""
        with open(self.db_path, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(asdict(entry), default=str) + "\n")


class AlertManager:
    """告警管理器 — 当死信积压、认证过期等事件发生时发送告警.

    TODO: 对接 WeCom 推送，当前只打日志。
    """

    def __init__(self):
        pass

    def alert_dead_letter_backlog(self, count: int) -> None:
        """告警：死信积压超过阈值"""
        logger.critical(f"ALERT: Dead letter backlog: {count} unresolved entries. Requires manual intervention.")

    def alert_auth_expired(self, connector_name: str) -> None:
        """告警：连接器认证过期，需要重新登录"""
        logger.critical(f"ALERT: Authentication expired for connector {connector_name}. Please re-login.")

    def alert_sync_failed(self, connector_name: str, error: str) -> None:
        """告警：同步任务永久失败"""
        logger.error(f"ALERT: Sync failed for connector {connector_name}: {error}")
