"""Session Store — 会话存储抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from models import Session, SessionStatus


class SessionStore(ABC):
    """会话存储抽象基类。

    定义会话持久化接口。具体实现可以是：
    - 内存存储（开发/测试）
    - L1 MemoryInterface（复用运行时记忆系统）
    - Redis（分布式部署）
    - SQL 数据库（需要复杂查询）
    """

    @abstractmethod
    def get(self, session_id: str) -> Optional[Session]:
        """按 ID 获取会话。

        Args:
            session_id: 会话 ID

        Returns:
            Session — 找到返回；未找到返回 None
        """
        ...

    @abstractmethod
    def create(self, session: Session) -> Session:
        """创建一个新会话。

        Args:
            session: 会话对象

        Returns:
            Session — 创建后的会话（可能包含生成的字段）

        Raises:
            ValueError: session_id 已存在
        """
        ...

    @abstractmethod
    def update(self, session_id: str, **kwargs) -> Session:
        """更新会话字段。

        Args:
            session_id: 会话 ID
            **kwargs: 要更新的字段键值对

        Returns:
            Session — 更新后的会话

        Raises:
            ValueError: 会话不存在
        """
        ...

    @abstractmethod
    def delete(self, session_id: str) -> bool:
        """删除会话（软删除，状态标记为 DELETED）。

        Args:
            session_id: 会话 ID

        Returns:
            True — 成功；False — 不存在
        """
        ...

    @abstractmethod
    def list_by_user(self, user_id: str, status: SessionStatus | None = None) -> List[Session]:
        """列出指定用户的所有会话。

        Args:
            user_id: 用户 ID
            status: 可选，按状态过滤

        Returns:
            Session 列表
        """
        ...

    @abstractmethod
    def list_by_channel(self, channel: str, status: SessionStatus | None = None) -> List[Session]:
        """列出指定通道的所有会话。"""
        ...

    @abstractmethod
    def find_active(self, user_id: str, channel: str) -> Optional[Session]:
        """查找用户在指定通道上的活跃会话。

        如果有多个，返回最近活跃的那个。
        """
        ...

    @abstractmethod
    def cleanup_idle(self, idle_seconds: int) -> int:
        """清理空闲超过指定时间的会话（标记为 ARCHIVED）。

        Args:
            idle_seconds: 空闲秒数阈值

        Returns:
            int — 被清理的会话数量
        """
        ...

    @abstractmethod
    def count(self, status: SessionStatus | None = None) -> int:
        """统计会话数量。"""
        ...
