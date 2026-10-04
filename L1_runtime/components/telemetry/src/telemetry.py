"""Telemetry Provider — 遥测提供者抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Dict, List, Optional

from exporter import MetricsExporter
from models import LogLevel, MetricType, MetricsSnapshot, Span


class TelemetryProvider(ABC):
    """遥测提供者抽象基类。

    三大支柱：
    - Metrics — 指标（counter / gauge / histogram / timing）
    - Tracing — 分布式追踪（span）
    - Logging — 结构化日志

    具体实现：
    - InMemoryTelemetry — 内存实现（测试/开发）
    - OpenTelemetryProvider — OTLP 标准协议
    - PrometheusProvider — Prometheus 指标
    """

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    @abstractmethod
    def counter(self, name: str, value: float = 1.0,
                labels: Dict[str, str] | None = None) -> None:
        """增加计数器。

        Args:
            name: 指标名
            value: 增量（默认 1）
            labels: 标签字典
        """
        ...

    @abstractmethod
    def gauge(self, name: str, value: float,
              labels: Dict[str, str] | None = None) -> None:
        """设置仪表盘值。"""
        ...

    @abstractmethod
    def histogram(self, name: str, value: float,
                  labels: Dict[str, str] | None = None) -> None:
        """记录直方图观测值。"""
        ...

    @abstractmethod
    def timing(self, name: str, duration_seconds: float,
               labels: Dict[str, str] | None = None) -> None:
        """记录耗时（秒）。"""
        ...

    @abstractmethod
    def metric(
        self,
        metric_type: MetricType,
        name: str,
        value: float,
        labels: Dict[str, str] | None = None,
    ) -> None:
        """通用指标记录方法。"""
        ...

    # ------------------------------------------------------------------
    # Tracing
    # ------------------------------------------------------------------

    @abstractmethod
    def start_span(self, name: str, parent_span_id: str | None = None,
                   trace_id: str | None = None, **attributes) -> Span:
        """开始一个追踪 Span。

        Args:
            name: Span 名称
            parent_span_id: 父 Span ID（None = 根 Span）
            trace_id: Trace ID（None = 自动生成或从上下文取）
            **attributes: 附加属性

        Returns:
            Span — 追踪区间对象
        """
        ...

    @abstractmethod
    def end_span(self, span: Span, status: str = "ok") -> None:
        """结束一个 Span。"""
        ...

    @contextmanager
    def span(self, name: str, **attributes):
        """上下文管理器：自动 start + end。"""
        s = self.start_span(name, **attributes)
        try:
            yield s
        except Exception as e:
            s.end(status="error")
            raise
        else:
            s.end(status="ok")

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    @abstractmethod
    def log(self, level: LogLevel | str, message: str, **kwargs) -> None:
        """记录结构化日志。"""
        ...

    def debug(self, message: str, **kwargs) -> None:
        self.log(LogLevel.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs) -> None:
        self.log(LogLevel.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs) -> None:
        self.log(LogLevel.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs) -> None:
        self.log(LogLevel.ERROR, message, **kwargs)

    def critical(self, message: str, **kwargs) -> None:
        self.log(LogLevel.CRITICAL, message, **kwargs)

    # ------------------------------------------------------------------
    # Export & Collection
    # ------------------------------------------------------------------

    @abstractmethod
    def register_exporter(self, exporter: MetricsExporter) -> None:
        """注册一个指标导出器。"""
        ...

    @abstractmethod
    def unregister_exporter(self, name: str) -> bool:
        """注销一个导出器。"""
        ...

    @abstractmethod
    def collect(self) -> MetricsSnapshot:
        """收集当前所有指标快照。"""
        ...

    @abstractmethod
    def list_metrics(self) -> List[str]:
        """列出所有已记录的指标名。"""
        ...
