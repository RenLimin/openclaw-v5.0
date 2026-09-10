"""Error Handler — 错误数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


class Severity(str, Enum):
    """错误严重级别。

    SEV1: 系统不可用，立即通知 + 自动自愈
    SEV2: 功能受损，通知 + 尝试自愈
    SEV3: 局部异常，仅记录 + 告警阈值触发
    SEV4: 轻微/可忽略，仅记录
    """
    SEV1 = "sev1"    # 严重
    SEV2 = "sev2"    # 重要
    SEV3 = "sev3"    # 一般
    SEV4 = "sev4"    # 轻微

    @property
    def should_notify(self) -> bool:
        return self in (Severity.SEV1, Severity.SEV2)

    @property
    def numeric(self) -> int:
        return {"sev1": 1, "sev2": 2, "sev3": 3, "sev4": 4}[self.value]


class ErrorCategory(str, Enum):
    """错误分类。"""
    NETWORK = "network"
    TIMEOUT = "timeout"
    CONFIG = "config"
    AUTH = "auth"
    PERMISSION = "permission"
    NOT_FOUND = "not_found"
    VALIDATION = "validation"
    BUSINESS = "business"
    RUNTIME = "runtime"
    UNKNOWN = "unknown"


class RecoveryAction(str, Enum):
    """自愈动作。"""
    NONE = "none"
    RETRY = "retry"
    FALLBACK = "fallback"
    CIRCUIT_BREAK = "circuit_break"
    NOTIFY = "notify"
    ESCALATE = "escalate"


@dataclass
class AppError:
    """统一应用错误模型。"""
    error_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    code: str = "ERR_UNKNOWN"
    message: str = "Unknown error"
    severity: Severity = Severity.SEV3
    category: ErrorCategory = ErrorCategory.UNKNOWN
    source: str = "unknown"
    trace_id: str | None = None
    session_id: str | None = None
    stack_trace: str | None = None
    context: Dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=datetime.now)
    retry_count: int = 0
    resolved: bool = False
    resolution: str | None = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_id": self.error_id,
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
            "category": self.category.value,
            "source": self.source,
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "stack_trace": self.stack_trace,
            "context": self.context,
            "occurred_at": self.occurred_at.isoformat(),
            "retry_count": self.retry_count,
            "resolved": self.resolved,
            "resolution": self.resolution,
        }

    @classmethod
    def from_exception(cls, exc: Exception, source: str = "unknown",
                       severity: Severity = Severity.SEV3) -> "AppError":
        """从 Python 异常创建 AppError。"""
        import traceback
        return cls(
            code=f"ERR_{type(exc).__name__.upper()}",
            message=str(exc),
            severity=severity,
            source=source,
            stack_trace=traceback.format_exc(),
        )


@dataclass
class ErrorOutcome:
    """错误处理结果。"""
    error: AppError
    action: RecoveryAction
    success: bool = False          # 自愈是否成功
    resolution: str = ""
    handled_at: datetime = field(default_factory=datetime.now)

    @property
    def is_resolved(self) -> bool:
        return self.success or self.action == RecoveryAction.NONE


@dataclass
class ErrorStats:
    """错误统计。"""
    window_seconds: int = 3600
    total: int = 0
    by_severity: Dict[str, int] = field(default_factory=dict)
    by_category: Dict[str, int] = field(default_factory=dict)
    by_source: Dict[str, int] = field(default_factory=dict)
    resolved_rate: float = 0.0
    top_errors: List[Dict[str, Any]] = field(default_factory=list)
