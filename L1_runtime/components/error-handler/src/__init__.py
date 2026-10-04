"""Error Handler — 统一错误处理组件。"""

from models import (
    AppError, ErrorOutcome, ErrorStats,
    Severity, ErrorCategory, RecoveryAction,
)
from error_handler import ErrorHandler
from handler import DefaultErrorHandler
from strategy import RecoveryStrategy, RetryStrategy, FallbackStrategy

__all__ = [
    "ErrorHandler", "DefaultErrorHandler",
    "RecoveryStrategy", "RetryStrategy", "FallbackStrategy",
    "AppError", "ErrorOutcome", "ErrorStats",
    "Severity", "ErrorCategory", "RecoveryAction",
]
