"""
L2 会话隔离与共享服务 — API 导出
Copyright (c) 2026 Bangcle, Inc. All rights reserved.
"""

__all__ = ["SessionIsolationService", "TaskInfo"]


def __getattr__(name):
    """延迟导入，避免非包路径下 relative import 失败"""
    if name in __all__:
        from .service import SessionIsolationService, TaskInfo
        return locals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
