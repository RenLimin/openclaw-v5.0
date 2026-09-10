"""Telemetry — 数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class MetricType(str, Enum):
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMING = "timing"


class LogLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class MetricPoint:
    """单个指标数据点。"""
    name: str
    type: MetricType
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type.value,
            "value": self.value,
            "labels": self.labels,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class Span:
    """追踪 Span — 一次操作的时间区间。"""
    span_id: str
    name: str
    trace_id: str
    parent_span_id: str | None = None
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    status: str = "ok"  # ok / error / timeout
    events: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def duration_ms(self) -> float | None:
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time).total_seconds() * 1000

    def add_event(self, name: str, **attrs) -> None:
        self.events.append({
            "name": name,
            "timestamp": datetime.now().isoformat(),
            "attributes": attrs,
        })

    def end(self, status: str = "ok") -> None:
        self.end_time = datetime.now()
        self.status = status

    def is_ended(self) -> bool:
        return self.end_time is not None


@dataclass
class MetricsSnapshot:
    """指标快照 — 某一时刻的所有指标。"""
    timestamp: datetime = field(default_factory=datetime.now)
    counters: Dict[str, Dict[str, float]] = field(default_factory=dict)  # name -> {labels_str: value}
    gauges: Dict[str, Dict[str, float]] = field(default_factory=dict)
    histograms: Dict[str, Dict[str, List[float]]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "counters_count": len(self.counters),
            "gauges_count": len(self.gauges),
            "histograms_count": len(self.histograms),
        }
