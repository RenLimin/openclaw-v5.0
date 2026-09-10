"""Error Handler — 统一错误处理器抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Dict, List, Optional

from models import AppError, ErrorOutcome, ErrorStats, Severity
from strategy import RecoveryStrategy


class ErrorHandler(ABC):
    """统一错误处理器抽象基类。

    职责：
    - 错误捕获与标准化（Exception → AppError）
    - 错误分类与分级
    - 自愈策略执行（按错误类型匹配策略）
    - 错误上报（通知 / 日志 / 指标）
    - 错误统计与分析

    处理流程：
    1. 捕获异常 → 转换为 AppError
    2. 匹配严重级别 + 分类
    3. 查找自愈策略，按优先级尝试
    4. 成功 → 标记 resolved + 记录指标
    5. 失败 → Sev1/2 通知，全部记录日志
    """

    # ------------------------------------------------------------------
    # Error Capture
    # ------------------------------------------------------------------

    @abstractmethod
    def capture(self, exception: Exception, source: str = "unknown",
                severity: Severity | None = None,
                context: Dict | None = None) -> AppError:
        """捕获一个异常并转换为 AppError。

        Args:
            exception: Python 异常
            source: 来源组件
            severity: 强制指定严重级别（None 则自动判断）
            context: 附加上下文

        Returns:
            AppError — 标准化错误对象
        """
        ...

    @abstractmethod
    def report(self, error: AppError) -> None:
        """直接上报一个已构造的 AppError。"""
        ...

    # ------------------------------------------------------------------
    # Error Handling
    # ------------------------------------------------------------------

    @abstractmethod
    def handle(self, error: AppError, context: Dict | None = None,
               operation: Callable | None = None) -> ErrorOutcome:
        """处理一个错误（尝试自愈）。

        Args:
            error: 错误对象
            context: 上下文
            operation: 可重试的操作（重试策略需要）

        Returns:
            ErrorOutcome — 处理结果
        """
        ...

    def handle_exception(self, exception: Exception, source: str = "unknown",
                         **kwargs) -> ErrorOutcome:
        """便捷方法：捕获 + 处理 一体化。"""
        error = self.capture(exception, source)
        return self.handle(error, **kwargs)

    # ------------------------------------------------------------------
    # Strategy Management
    # ------------------------------------------------------------------

    @abstractmethod
    def register_strategy(self, error_pattern: str,
                          strategy: RecoveryStrategy, priority: int = 0) -> None:
        """注册自愈策略。

        Args:
            error_pattern: 错误码匹配模式（支持通配符）
            strategy: 策略实例
            priority: 优先级（数字大先尝试）
        """
        ...

    @abstractmethod
    def unregister_strategy(self, strategy_name: str) -> bool:
        """注销策略。"""
        ...

    @abstractmethod
    def list_strategies(self) -> List[Dict[str, str]]:
        """列出所有已注册策略。"""
        ...

    # ------------------------------------------------------------------
    # Stats & Query
    # ------------------------------------------------------------------

    @abstractmethod
    def get_stats(self, window_seconds: int = 3600) -> ErrorStats:
        """获取指定时间窗口内的错误统计。"""
        ...

    @abstractmethod
    def get_error(self, error_id: str) -> Optional[AppError]:
        """按 ID 获取错误详情。"""
        ...

    @abstractmethod
    def list_errors(self, severity: Severity | None = None,
                    limit: int = 100) -> List[AppError]:
        """列出错误，可按严重级别过滤。"""
        ...

    # ------------------------------------------------------------------
    # Decorator / Context Manager
    # ------------------------------------------------------------------

    @abstractmethod
    def catch(self, source: str = "unknown", reraise: bool = False):
        """错误捕获装饰器 / 上下文管理器。

        用法：
            @handler.catch(source="my-component")
            def my_function():
                ...

            with handler.catch(source="my-component"):
                ...
        """
        ...
