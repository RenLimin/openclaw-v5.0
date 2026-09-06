"""
OpenClaw L1 适配层
"""
from .adapter import OpenClawAdapter, HealthStatus, ToolCallResult, ContextStatus
from .config import get_config, set_config, validate_config, get_all_mappings
from .health import check_all_components, full_health_check

__all__ = [
    "OpenClawAdapter",
    "HealthStatus",
    "ToolCallResult",
    "ContextStatus",
    "get_config",
    "set_config",
    "validate_config",
    "get_all_mappings",
    "check_all_components",
    "full_health_check",
]

# 导出单例
adapter = OpenClawAdapter()
