"""
OpenClaw L1 适配层

包含两部分：
1. OpenClawAdapter — 原有直接实现（向后兼容）
2. OpenClawRuntimeAdapter — 基于 RuntimeAdapter ABC 的标准适配（推荐）
"""
from .adapter import OpenClawAdapter, HealthStatus, ToolCallResult, ContextStatus
from .config import get_config, set_config, validate_config, get_all_mappings
from .health import check_all_components, full_health_check
from .runtime_adapter import (
    OpenClawChannel,
    OpenClawCredentials,
    OpenClawMemory,
    OpenClawRuntimeAdapter,
    OpenClawSandbox,
)

__all__ = [
    # 原有直接实现（向后兼容）
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
    # RuntimeAdapter ABC 标准实现（推荐）
    "OpenClawRuntimeAdapter",
    "OpenClawMemory",
    "OpenClawChannel",
    "OpenClawSandbox",
    "OpenClawCredentials",
]

# 导出单例（向后兼容）
adapter = OpenClawAdapter()
