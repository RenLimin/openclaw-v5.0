"""BDMS 模块4 —— 交付统计看板。

对外入口：
    from bdms.modules.dashboard import DashboardEngine, DashboardService
"""

from .engine import DashboardEngine
from .service import DashboardService

__all__ = ["DashboardEngine", "DashboardService"]
