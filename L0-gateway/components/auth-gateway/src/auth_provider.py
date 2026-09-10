"""Auth Provider — 认证提供者与限流器抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List

from models import AuthRequest, AuthResult, Identity


class AuthProvider(ABC):
    """认证提供者抽象基类。

    不同认证方式实现不同的 AuthProvider：
    - SignatureAuthProvider — 签名验证（WeCom/钉钉等回调）
    - TokenAuthProvider — Bearer Token / JWT
    - ApiKeyAuthProvider — API Key 验证
    - OAuthProvider — OAuth 2.0
    """

    name: str = "base"

    @abstractmethod
    def verify(self, request: AuthRequest) -> AuthResult:
        """验证一个认证请求。

        Args:
            request: 认证请求

        Returns:
            AuthResult — 认证结果（含身份信息或错误信息）
        """
        ...

    def issue(self, identity: Identity) -> str:
        """签发认证凭据（可选实现）。

        默认抛出 NotImplementedError。无状态认证（如签名）不需要此方法。
        """
        raise NotImplementedError(f"{self.name} does not support issuing credentials")

    def revoke(self, token: str) -> bool:
        """吊销凭据（可选实现）。"""
        raise NotImplementedError(f"{self.name} does not support revoking")

    @abstractmethod
    def supports(self, auth_type: str) -> bool:
        """检查是否支持指定的认证类型。"""
        ...

    def supported_types(self) -> List[str]:
        """返回支持的认证类型列表。"""
        return []


class RateLimiter(ABC):
    """限流器抽象基类。

    用于：
    - 按用户限流（防止刷屏）
    - 按通道限流（防攻击）
    - 全局限流（保护后端）

    常见实现：
    - TokenBucketRateLimiter — 令牌桶，支持突发
    - LeakyBucketRateLimiter — 漏桶，平滑速率
    - SlidingWindowLimiter — 滑动窗口计数
    """

    @abstractmethod
    def allow(self, key: str, tokens: int = 1) -> bool:
        """尝试获取指定数量的令牌。

        Args:
            key: 限流键（如 user_id / channel / global）
            tokens: 需要的令牌数

        Returns:
            True — 允许通过；False — 被限流
        """
        ...

    @abstractmethod
    def remaining(self, key: str) -> int:
        """查询剩余令牌数。"""
        ...

    @abstractmethod
    def reset_at(self, key: str) -> datetime:
        """查询下次重置时间。"""
        ...

    @abstractmethod
    def reset(self, key: str) -> None:
        """重置指定键的限流状态。"""
        ...
