"""Metrics Exporter — 指标导出器抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from models import MetricPoint, MetricsSnapshot


class MetricsExporter(ABC):
    """指标导出器抽象基类。

    将遥测数据导出到外部系统。
    常见实现：
    - ConsoleExporter — 控制台输出（调试用）
    - FileExporter — 文件输出（JSON / CSV）
    - PrometheusExporter — Prometheus /metrics 端点
    - OpenTelemetryExporter — OTLP 协议
    - StatsDExporter — StatsD 协议
    """

    name: str = "base"

    @abstractmethod
    def export(self, snapshot: MetricsSnapshot) -> None:
        """导出一份指标快照。

        Args:
            snapshot: 指标快照
        """
        ...

    @abstractmethod
    def export_points(self, points: List[MetricPoint]) -> None:
        """增量导出一组指标数据点。

        Args:
            points: 指标数据点列表
        """
        ...

    @abstractmethod
    def flush(self) -> None:
        """刷新缓冲区（如果有）。"""
        ...

    @abstractmethod
    def close(self) -> None:
        """关闭导出器，释放资源。"""
        ...
