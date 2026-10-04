"""Error Handler — 统一错误处理（骨架）。"""

from models import AppError, ErrorOutcome, ErrorStats, Severity, ErrorCategory
from error_handler import ErrorHandler
from strategy import RecoveryStrategy, RetryStrategy, FallbackStrategy

__all__ = [
    "AppError", "ErrorOutcome", "ErrorStats", "Severity", "ErrorCategory",
    "ErrorHandler", "RecoveryStrategy", "RetryStrategy", "FallbackStrategy",
]
