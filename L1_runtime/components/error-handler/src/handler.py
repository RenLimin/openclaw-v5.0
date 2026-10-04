"""Default Error Handler — 默认错误处理器实现."""

from __future__ import annotations

import logging
import threading
import time
import traceback
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional

from models import (
    AppError,
    ErrorCategory,
    ErrorOutcome,
    ErrorStats,
    RecoveryAction,
    Severity,
)
from strategy import RecoveryStrategy

logger = logging.getLogger(__name__)


class DefaultErrorHandler:
    """默认错误处理器实现.
    
    特性：
    - 异常自动分类 + 严重级别判定
    - 自愈策略注册与执行（优先级排序）
    - 错误统计（按严重级别/分类/来源）
    - 自愈成功记录
    - 线程安全
    """

    def __init__(self) -> None:
        self._strategies: List[tuple[int, str, RecoveryStrategy]] = []
        self._errors: List[AppError] = []
        self._lock = threading.Lock()

    def capture(
        self,
        exception: Exception,
        source: str = "unknown",
        severity: Optional[Severity] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> AppError:
        """捕获异常."""
        error = AppError.from_exception(exception, source, severity or self._auto_severity(exception))
        error.category = self._auto_category(exception)
        if context:
            error.context.update(context)
        return error

    def report(self, error: AppError) -> None:
        """上报错误."""
        with self._lock:
            self._errors.append(error)
            # 保留最近 10000 条
            if len(self._errors) > 10000:
                self._errors = self._errors[-5000:]
        logger.error(f"[{error.code}] {error.message} (source={error.source})")

    def handle(
        self,
        error: AppError,
        context: Optional[Dict[str, Any]] = None,
        operation: Optional[Callable[..., Any]] = None,
        **kwargs,
    ) -> ErrorOutcome:
        """处理错误."""
        self.report(error)
        with self._lock:
            # 按优先级排序策略
            sorted_strategies = sorted(self._strategies, key=lambda s: s[0], reverse=True)
            for priority, name, strategy in sorted_strategies:
                if strategy.can_handle(error):
                    try:
                        success, message = strategy.execute(error, context, operation)
                        if success:
                            error.resolved = True
                            error.resolution = message
                            return ErrorOutcome(
                                error=error,
                                action=strategy.action,
                                success=True,
                                resolution=message,
                            )
                    except Exception as e:
                        logger.error(f"Strategy {name} failed: {e}")
            # 无匹配策略
            return ErrorOutcome(
                error=error,
                action=RecoveryAction.NONE,
                success=False,
                resolution="No matching recovery strategy",
            )

    def register_strategy(
        self,
        error_pattern: str,
        strategy: RecoveryStrategy,
        priority: int = 0,
    ) -> None:
        """注册自愈策略."""
        with self._lock:
            self._strategies.append((priority, error_pattern, strategy))

    def unregister_strategy(self, strategy_name: str) -> bool:
        """注销策略."""
        with self._lock:
            original_len = len(self._strategies)
            self._strategies = [
                (p, n, s) for p, n, s in self._strategies if n != strategy_name
            ]
            return len(self._strategies) < original_len

    def list_strategies(self) -> List[Dict[str, str]]:
        """列出策略."""
        with self._lock:
            return [
                {"pattern": name, "priority": str(priority), "action": strategy.action.value}
                for priority, name, strategy in sorted(self._strategies, reverse=True)
            ]

    def get_stats(self, window_seconds: int = 3600) -> ErrorStats:
        """获取统计."""
        now = time.time()
        with self._lock:
            cutoff = now - window_seconds
            recent = [
                e for e in self._errors
                if e.occurred_at.timestamp() > cutoff
            ]
            stats = ErrorStats(
                window_seconds=window_seconds,
                total=len(recent),
                by_severity={s.value: 0 for s in Severity},
                by_category={c.value: 0 for c in ErrorCategory},
                by_source={},
            )
            for e in recent:
                stats.by_severity[e.severity.value] += 1
                stats.by_category[e.category.value] += 1
                stats.by_source[e.source] = stats.by_source.get(e.source, 0) + 1
            resolved = sum(1 for e in recent if e.resolved)
            stats.resolved_rate = resolved / len(recent) if recent else 0.0
            return stats

    def get_error(self, error_id: str) -> Optional[AppError]:
        """获取错误."""
        with self._lock:
            for e in self._errors:
                if e.error_id == error_id:
                    return e
        return None

    def list_errors(
        self,
        severity: Optional[Severity] = None,
        limit: int = 100,
    ) -> List[AppError]:
        """列出错误."""
        with self._lock:
            errors = self._errors[-limit:]
            if severity:
                errors = [e for e in errors if e.severity == severity]
            return list(reversed(errors))

    def catch(self, source: str = "unknown", reraise: bool = False):
        """装饰器 / 上下文管理器."""
        import functools

        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    error = self.capture(e, source)
                    self.handle(error, operation=func, **kwargs)
                    if reraise:
                        raise
            return wrapper

        # 支持无参数用法: @handler.catch(source="...")
        if callable(source):
            func = source
            source = "unknown"
            return decorator(func)

        return decorator

    def _auto_severity(self, exc: Exception) -> Severity:
        """自动判断严重级别."""
        if isinstance(exc, (ConnectionError, TimeoutError)):
            return Severity.SEV2
        if isinstance(exc, (ValueError, TypeError, KeyError)):
            return Severity.SEV3
        if isinstance(exc, (PermissionError,)):
            return Severity.SEV2
        return Severity.SEV3

    def _auto_category(self, exc: Exception) -> ErrorCategory:
        """自动分类."""
        if isinstance(exc, ConnectionError):
            return ErrorCategory.NETWORK
        if isinstance(exc, TimeoutError):
            return ErrorCategory.TIMEOUT
        if isinstance(exc, PermissionError):
            return ErrorCategory.PERMISSION
        if isinstance(exc, FileNotFoundError):
            return ErrorCategory.NOT_FOUND
        if isinstance(exc, (ValueError, TypeError)):
            return ErrorCategory.VALIDATION
        return ErrorCategory.UNKNOWN
