"""
CredentialInterface — 凭据抽象接口

定义运行时必须提供的凭据管理能力，包括：
- 凭据读取（仅引用，不暴露明文的上层语义由 L2 保障）
- 凭据列举
- 存在性检查

安全原则：
- L1 层提供凭据读取原语
- 明文避免原则由 L2 的凭据治理组件保障
- L1 不做权限判断，只负责从安全存储中取出
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional


class CredentialInterface(ABC):
    """凭据管理抽象接口。

    所有运行时适配器的凭据子系统必须实现本接口。
    接口设计为最小能力集：读取、列举、存在性检查。
    """

    @abstractmethod
    def get(self, name: str) -> Optional[str]:
        """获取凭据值。

        Args:
            name: 凭据名称或引用标识

        Returns:
            凭据值（字符串），不存在时返回 None。

        注意：
            调用方有责任不将凭据明文写入日志或持久化存储。
            L2 的凭据治理组件会额外提供脱敏和审计。
        """
        ...

    @abstractmethod
    def list(self) -> List[str]:
        """列举所有可用凭据名称。

        Returns:
            凭据名称列表（不含值）。
        """
        ...

    @abstractmethod
    def has(self, name: str) -> bool:
        """检查凭据是否存在。

        Args:
            name: 凭据名称

        Returns:
            存在返回 True，否则返回 False。
        """
        ...
