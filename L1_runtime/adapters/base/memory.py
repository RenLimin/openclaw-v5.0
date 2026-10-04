"""
MemoryInterface — 记忆抽象接口

定义运行时必须提供的持久化记忆能力，包括：
- 键值读写
- 前缀列举
- 语义搜索

L2-L4 只依赖此接口，不直接调用具体运行时的记忆 API。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from .models import MemoryItem


class MemoryInterface(ABC):
    """记忆系统抽象接口。

    所有运行时适配器的记忆子系统必须实现本接口。
    接口设计为最小能力集：键值读写 + 前缀列举 + 语义搜索。
    """

    @abstractmethod
    def search(self, query: str, limit: int = 5) -> List[MemoryItem]:
        """语义搜索记忆。

        Args:
            query: 搜索查询字符串
            limit: 最大返回结果数

        Returns:
            匹配的记忆条目列表，按相关度降序排列。
            无匹配时返回空列表，不抛异常。
        """
        ...

    @abstractmethod
    def get(self, key: str) -> Optional[str]:
        """根据键读取记忆值。

        Args:
            key: 记忆键

        Returns:
            记忆值（字符串），不存在时返回 None。
        """
        ...

    @abstractmethod
    def put(self, key: str, value: str) -> bool:
        """写入记忆。

        Args:
            key: 记忆键
            value: 记忆值（字符串）

        Returns:
            写入成功返回 True，失败返回 False。
        """
        ...

    @abstractmethod
    def delete(self, key: str) -> bool:
        """删除记忆。

        Args:
            key: 记忆键

        Returns:
            删除成功返回 True；键不存在或失败返回 False。
        """
        ...

    @abstractmethod
    def list(self, prefix: str = "") -> List[str]:
        """列举匹配前缀的所有键。

        Args:
            prefix: 键名前缀，空字符串表示列举全部

        Returns:
            匹配的键名列表。
        """
        ...
