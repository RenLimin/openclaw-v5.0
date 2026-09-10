"""
SandboxInterface — 沙箱抽象接口

定义运行时必须提供的沙箱隔离执行能力，包括：
- 命令执行
- 文件读写
- 目录列举

L2-L4 只依赖此接口，不直接调用具体运行时的沙箱 API。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from .models import ExecResult


class SandboxInterface(ABC):
    """沙箱隔离执行抽象接口。

    所有运行时适配器的沙子系统必须实现本接口。
    接口设计为最小能力集：命令执行 + 文件读写 + 目录列举。
    """

    @abstractmethod
    def exec(self, command: str, timeout: float = 30.0) -> ExecResult:
        """在沙箱中执行命令。

        Args:
            command: 要执行的 Shell 命令
            timeout: 超时时间（秒）

        Returns:
            ExecResult — 执行结果，含 exit_code / stdout / stderr。
        """
        ...

    @abstractmethod
    def read_file(self, path: str) -> Optional[str]:
        """读取沙箱内的文件内容。

        Args:
            path: 文件路径（沙箱内相对或绝对路径）

        Returns:
            文件内容（文本），文件不存在或不可读返回 None。
        """
        ...

    @abstractmethod
    def write_file(self, path: str, content: str) -> bool:
        """写入文件到沙箱内。

        Args:
            path: 文件路径
            content: 文件内容（文本）

        Returns:
            写入成功返回 True，失败返回 False。
        """
        ...

    @abstractmethod
    def list_dir(self, path: str = ".") -> List[str]:
        """列举沙箱内的目录内容。

        Args:
            path: 目录路径，默认为当前目录

        Returns:
            文件名和子目录名列表。目录不存在返回空列表。
        """
        ...
