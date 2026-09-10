"""Recovery Strategy — 自愈策略抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict

from models import AppError, RecoveryAction


class RecoveryStrategy(ABC):
    """自愈策略抽象基类。

    每种策略封装一种错误恢复方式。
    """

    name: str = "base"
    action: RecoveryAction = RecoveryAction.NONE

    @abstractmethod
    def can_handle(self, error: AppError) -> bool:
        """判断此策略是否能处理该错误。"""
        ...

    @abstractmethod
    def execute(self, error: AppError, context: Dict[str, Any] | None = None,
                operation: Callable | None = None) -> tuple[bool, str]:
        """执行自愈。

        Args:
            error: 要处理的错误
            context: 上下文信息
            operation: 可重试的操作函数（重试策略需要）

        Returns:
            (success: bool, message: str)
        """
        ...

    @abstractmethod
    def reset(self) -> None:
        """重置策略状态（如熔断器复位）。"""
        ...


class RetryStrategy(RecoveryStrategy):
    """重试策略 — 指数退避重试。

    注意：这是骨架定义，完整实现在后续版本。
    """
    name = "retry"
    action = RecoveryAction.RETRY

    def can_handle(self, error: AppError) -> bool:
        # 默认：网络/超时类错误可重试
        from models import ErrorCategory
        return error.category in (ErrorCategory.NETWORK, ErrorCategory.TIMEOUT)

    def execute(self, error: AppError, context: Dict[str, Any] | None = None,
                operation: Callable | None = None) -> tuple[bool, str]:
        raise NotImplementedError("RetryStrategy.execute not implemented (skeleton)")

    def reset(self) -> None:
        pass


class FallbackStrategy(RecoveryStrategy):
    """降级策略 — 切换到备用实现。"""
    name = "fallback"
    action = RecoveryAction.FALLBACK

    def can_handle(self, error: AppError) -> bool:
        return error.severity.value != "sev1"  # 非致命错误可降级

    def execute(self, error: AppError, context: Dict[str, Any] | None = None,
                operation: Callable | None = None) -> tuple[bool, str]:
        raise NotImplementedError("FallbackStrategy.execute not implemented (skeleton)")

    def reset(self) -> None:
        pass
