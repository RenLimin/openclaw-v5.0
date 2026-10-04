"""Telemetry — 骨架测试。"""

import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from models import MetricPoint, Span, MetricsSnapshot, MetricType, LogLevel
from telemetry import TelemetryProvider
from exporter import MetricsExporter


class TestMetricPoint:
    def test_creation(self):
        mp = MetricPoint(name="test.counter", type=MetricType.COUNTER, value=5.0,
                         labels={"host": "test"})
        assert mp.name == "test.counter"
        assert mp.value == 5.0
        assert mp.labels["host"] == "test"

    def test_to_dict(self):
        mp = MetricPoint(name="m1", type=MetricType.GAUGE, value=1.0)
        d = mp.to_dict()
        assert d["name"] == "m1"
        assert d["type"] == "gauge"
        assert "timestamp" in d


class TestSpan:
    def test_span_lifecycle(self):
        span = Span(span_id="s1", name="test-op", trace_id="t1")
        assert span.is_ended() is False
        assert span.duration_ms is None
        span.add_event("step1", detail="started")
        span.end(status="ok")
        assert span.is_ended() is True
        assert span.duration_ms is not None
        assert span.duration_ms >= 0
        assert len(span.events) == 1


class TestMetricsSnapshot:
    def test_empty_snapshot(self):
        snap = MetricsSnapshot()
        d = snap.to_dict()
        assert d["counters_count"] == 0
        assert "timestamp" in d


class TestABCs:
    def test_telemetry_provider_abstract(self):
        with pytest.raises(TypeError):
            TelemetryProvider()

    def test_telemetry_has_metric_methods(self):
        for m in ["counter", "gauge", "histogram", "timing", "metric"]:
            assert hasattr(TelemetryProvider, m), f"Missing {m}"

    def test_telemetry_has_tracing_methods(self):
        for m in ["start_span", "end_span", "span"]:
            assert hasattr(TelemetryProvider, m), f"Missing {m}"

    def test_telemetry_has_log_methods(self):
        for m in ["log", "debug", "info", "warning", "error", "critical"]:
            assert hasattr(TelemetryProvider, m), f"Missing {m}"

    def test_exporter_abstract(self):
        with pytest.raises(TypeError):
            MetricsExporter()

    def test_exporter_methods(self):
        for m in ["export", "export_points", "flush", "close"]:
            assert hasattr(MetricsExporter, m), f"Missing {m}"
