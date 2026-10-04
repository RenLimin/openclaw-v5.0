"""In-Memory Telemetry Provider — 内存遥测提供者实现."""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

from exporter import MetricsExporter
from models import LogLevel, MetricPoint, MetricType, MetricsSnapshot, Span
from telemetry import TelemetryProvider

logger = logging.getLogger(__name__)


class InMemoryTelemetryProvider(TelemetryProvider):
    """内存遥测提供者.
    
    三大支柱实现：
    - Metrics: counter / gauge / histogram / timing
    - Tracing: span 嵌套追踪
    - Logging: 结构化日志
    
    可选导出器：ConsoleExporter / FileExporter / PrometheusExporter
    """

    def __init__(self) -> None:
        self._counters: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self._gauges: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self._histograms: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
        self._spans: List[Span] = []
        self._exporters: Dict[str, MetricsExporter] = {}
        self._log_buffer: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def counter(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        key = self._labels_key(labels)
        with self._lock:
            self._counters[name][key] += value

    def gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        key = self._labels_key(labels)
        with self._lock:
            self._gauges[name][key] = value

    def histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        key = self._labels_key(labels)
        with self._lock:
            self._histograms[name][key].append(value)

    def timing(self, name: str, duration_seconds: float, labels: Optional[Dict[str, str]] = None) -> None:
        self.histogram(name, duration_seconds, labels)

    def metric(self, metric_type: MetricType, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        if metric_type == MetricType.COUNTER:
            self.counter(name, value, labels)
        elif metric_type == MetricType.GAUGE:
            self.gauge(name, value, labels)
        elif metric_type == MetricType.HISTOGRAM:
            self.histogram(name, value, labels)
        elif metric_type == MetricType.TIMING:
            self.timing(name, value, labels)

    def start_span(self, name: str, parent_span_id: Optional[str] = None,
                   trace_id: Optional[str] = None, **attributes) -> Span:
        import uuid
        span = Span(
            span_id=str(uuid.uuid4()),
            name=name,
            trace_id=trace_id or str(uuid.uuid4()),
            parent_span_id=parent_span_id,
            attributes=attributes,
        )
        return span

    def end_span(self, span: Span, status: str = "ok") -> None:
        span.end(status)
        with self._lock:
            self._spans.append(span)

    def log(self, level: LogLevel | str, message: str, **kwargs) -> None:
        if isinstance(level, str):
            level = LogLevel(level)
        entry = {
            "level": level.value,
            "message": message,
            "timestamp": time.time(),
            **kwargs,
        }
        with self._lock:
            self._log_buffer.append(entry)
            if len(self._log_buffer) > 5000:
                self._log_buffer = self._log_buffer[-2500:]
        logger.log(
            getattr(logging, level.value.upper(), logging.INFO),
            message,
        )

    def register_exporter(self, exporter: MetricsExporter) -> None:
        self._exporters[exporter.name] = exporter

    def unregister_exporter(self, name: str) -> bool:
        return self._exporters.pop(name, None) is not None

    def collect(self) -> MetricsSnapshot:
        with self._lock:
            return MetricsSnapshot(
                counters={k: dict(v) for k, v in self._counters.items()},
                gauges={k: dict(v) for k, v in self._gauges.items()},
                histograms={k: dict(v) for k, v in self._histograms.items()},
            )

    def list_metrics(self) -> List[str]:
        with self._lock:
            return list(set(
                list(self._counters.keys())
                + list(self._gauges.keys())
                + list(self._histograms.keys())
            ))

    def flush_exporters(self) -> None:
        snapshot = self.collect()
        for exporter in self._exporters.values():
            try:
                exporter.export(snapshot)
                exporter.flush()
            except Exception as e:
                logger.error(f"Exporter {exporter.name} error: {e}")

    def get_recent_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            return self._log_buffer[-limit:]

    def get_spans(self, limit: int = 100) -> List[Span]:
        with self._lock:
            return self._spans[-limit:]

    def _labels_key(self, labels: Optional[Dict[str, str]]) -> str:
        if not labels:
            return "_"
        return ",".join(f"{k}={v}" for k, v in sorted(labels.items()))


class ConsoleExporter(MetricsExporter):
    """控制台导出器."""

    name = "console"

    def __init__(self) -> None:
        self._buffer: List[MetricsSnapshot] = []

    def export(self, snapshot: MetricsSnapshot) -> None:
        self._buffer.append(snapshot)
        print(f"[Telemetry] {snapshot.to_dict()}")

    def export_points(self, points: List[MetricPoint]) -> None:
        for p in points:
            print(f"[Metric] {p.name}={p.value} ({p.type.value})")

    def flush(self) -> None:
        self._buffer.clear()

    def close(self) -> None:
        pass
