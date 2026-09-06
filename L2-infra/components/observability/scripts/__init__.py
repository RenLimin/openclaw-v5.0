"""
L2 可观测性适配 — 基础工具封装
遵循 OpenTelemetry GenAI semantic conventions
"""
from .logging import (
    init_logging,
    log_event,
    redact_sensitive,
    get_daily_log_path,
)
from .tracing import (
    start_trace,
    end_trace,
    start_span,
    end_span,
    get_current_trace,
)

__all__ = [
    # logging
    "init_logging",
    "log_event",
    "redact_sensitive",
    "get_daily_log_path",
    # tracing
    "start_trace",
    "end_trace",
    "start_span",
    "end_span",
    "get_current_trace",
]
