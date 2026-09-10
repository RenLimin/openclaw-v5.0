"""Tool Policy Engine — 工具策略引擎抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from models import ToolAccessRequest, PolicyDecision, ToolPolicy


class ToolPolicyEngine(ABC):
    """工具策略引擎抽象基类。

    负责：
    - 策略的增删改查
    - 访问请求评估（核心）
    - 调用记录审计
    - 速率限制检查

    评估顺序：
    1. 按优先级从高到低排序策略
    2. 找到第一个匹配的策略（工具 + 主体 + 作用域）
    3. 返回策略效果（ALLOW / DENY）
    4. 无匹配策略时，使用默认决策（默认 DENY，可配置）
    """

    default_decision: DecisionResult  # type: ignore — 子类需设置

    @abstractmethod
    def evaluate(self, request: ToolAccessRequest) -> PolicyDecision:
        """评估一个工具访问请求。

        Args:
            request: 访问请求

        Returns:
            PolicyDecision — 评估决策
        """
        ...

    @abstractmethod
    def add_policy(self, policy: ToolPolicy) -> None:
        """添加一条策略。

        Raises:
            ValueError: policy_id 已存在
        """
        ...

    @abstractmethod
    def remove_policy(self, policy_id: str) -> bool:
        """删除一条策略。返回是否成功。"""
        ...

    @abstractmethod
    def get_policy(self, policy_id: str) -> Optional[ToolPolicy]:
        """按 ID 获取策略。"""
        ...

    @abstractmethod
    def list_policies(self, scope: str | None = None,
                      effect: str | None = None) -> List[ToolPolicy]:
        """列出策略，可按作用域或效果过滤。"""
        ...

    @abstractmethod
    def enable_policy(self, policy_id: str) -> bool:
        """启用一条策略。"""
        ...

    @abstractmethod
    def disable_policy(self, policy_id: str) -> bool:
        """禁用一条策略。"""
        ...

    @abstractmethod
    def record_usage(self, request: ToolAccessRequest,
                     decision: PolicyDecision) -> None:
        """记录一次工具调用（审计用）。"""
        ...

    @abstractmethod
    def check_rate_limit(self, key: str, tool_name: str) -> bool:
        """检查是否触发速率限制。

        Args:
            key: 限流键（user_id / agent_id / 全局）
            tool_name: 工具名称

        Returns:
            True — 允许调用；False — 被限流
        """
        ...

    @abstractmethod
    def get_usage_stats(self, key: str, window_seconds: int = 3600) -> dict:
        """获取指定键在时间窗口内的调用统计。"""
        ...
