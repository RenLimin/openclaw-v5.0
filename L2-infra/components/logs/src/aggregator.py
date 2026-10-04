"""Log Aggregator — 日志聚合器实现."""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class LogLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class LogEntry:
    """单条日志记录."""
    timestamp: datetime
    level: LogLevel
    source: str
    message: str
    trace_id: Optional[str] = None
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "level": self.level.value,
            "source": self.source,
            "message": self.message,
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "metadata": self.metadata,
        }


@dataclass
class RotationPolicy:
    """日志轮转策略."""
    max_size_bytes: int = 10 * 1024 * 1024  # 10MB
    max_age_days: int = 7
    max_files: int = 5
    compress: bool = True


class LogAggregator:
    """日志聚合器 — 多源日志采集 + 查询 + 轮转.
    
    特性：
    - 多源采集（L0/L1/L2/L3/L4 组件日志）
    - 级别过滤
    - 按来源/时间/关键词查询
    - 自动轮转（按大小 + 按时间）
    - 线程安全
    """

    def __init__(
        self,
        log_dir: str = "~/.openclaw/logs/components",
        policy: Optional[RotationPolicy] = None,
    ) -> None:
        self._log_dir = Path(log_dir).expanduser()
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._policy = policy or RotationPolicy()
        self._lock = threading.Lock()
        self._sources: Dict[str, Any] = {}
        self._entries: List[LogEntry] = []

    def register_source(self, name: str, handler: Any) -> None:
        """注册日志源."""
        with self._lock:
            self._sources[name] = handler

    def unregister_source(self, name: str) -> bool:
        """注销日志源."""
        with self._lock:
            return self._sources.pop(name, None) is not None

    def log(
        self,
        level: LogLevel,
        source: str,
        message: str,
        trace_id: Optional[str] = None,
        session_id: Optional[str] = None,
        **metadata,
    ) -> LogEntry:
        """记录日志."""
        entry = LogEntry(
            timestamp=datetime.now(),
            level=level,
            source=source,
            message=message,
            trace_id=trace_id,
            session_id=session_id,
            metadata=metadata,
        )
        with self._lock:
            self._entries.append(entry)
            # 保留最近 10000 条
            if len(self._entries) > 10000:
                self._entries = self._entries[-5000:]
        # 写入文件
        self._write_to_file(entry)
        return entry

    def query(
        self,
        level: Optional[LogLevel] = None,
        source: Optional[str] = None,
        keyword: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[LogEntry]:
        """查询日志."""
        with self._lock:
            results = self._entries
            if level:
                level_value = level.value if isinstance(level, LogLevel) else level
                results = [e for e in results if e.level.value == level_value]
            if source:
                results = [e for e in results if e.source == source]
            if keyword:
                results = [e for e in results if keyword in e.message]
            if start_time:
                results = [e for e in results if e.timestamp >= start_time]
            if end_time:
                results = [e for e in results if e.timestamp <= end_time]
            return results[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        """获取日志统计."""
        with self._lock:
            stats = {
                "total_entries": len(self._entries),
                "sources": list(self._sources.keys()),
                "by_level": {level.value: 0 for level in LogLevel},
                "by_source": {},
            }
            for entry in self._entries:
                stats["by_level"][entry.level.value] += 1
                stats["by_source"][entry.source] = stats["by_source"].get(entry.source, 0) + 1
            return stats

    def rotate(self, force: bool = False) -> int:
        """执行日志轮转."""
        log_file = self._log_dir / "aggregated.log"
        if not log_file.exists():
            return 0
        if not force and log_file.stat().st_size < self._policy.max_size_bytes:
            return 0
        # 简单的轮转: 重命名为 .log.1, .log.2 等
        rotated = 0
        for i in range(self._policy.max_files - 1, 0, -1):
            src = self._log_dir / f"aggregated.log.{i}"
            dst = self._log_dir / f"aggregated.log.{i+1}"
            if src.exists():
                src.rename(dst)
                rotated += 1
        log_file.rename(self._log_dir / "aggregated.log.1")
        return rotated

    def _write_to_file(self, entry: LogEntry) -> None:
        """写入日志文件."""
        log_file = self._log_dir / "aggregated.log"
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"{entry.timestamp.isoformat()} [{entry.level.value.upper()}] [{entry.source}] {entry.message}")
                if entry.trace_id:
                    f.write(f" (trace={entry.trace_id})")
                f.write("\n")
        except Exception as e:
            logger.error(f"Failed to write log: {e}")


class FileLogSource:
    """文件日志源 — 读取现有日志文件."""

    def __init__(self, name: str, path: str, pattern: str = "") -> None:
        self.name = name
        self.path = Path(path)
        self.pattern = re.compile(pattern) if pattern else None

    def read_entries(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """读取日志条目."""
        if not self.path.exists():
            return []
        entries = []
        try:
            with open(self.path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if self.pattern and not self.pattern.search(line):
                        continue
                    entries.append({
                        "source": self.name,
                        "raw": line.strip(),
                        "timestamp": datetime.now().isoformat(),
                    })
        except Exception as e:
            logger.error(f"Failed to read {self.path}: {e}")
        return entries[-limit:]
