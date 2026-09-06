"""
OpenClaw 运行时配置映射
将 L1 抽象配置映射到 OpenClaw 原生配置路径
"""

from typing import Any, Dict, Optional
from .adapter import adapter

# 配置映射表：L1 抽象路径 → OpenClaw 原生配置路径
CONFIG_MAPPING: Dict[str, str] = {
    "agent_loop.max_tokens": "agents.defaults.model.contextWindow",
    "agent_loop.compaction_model": "agents.defaults.compaction.model",
    "tool_policy.allowed_tools": "tools.alsoAllow",
    "tool_policy.denied_tools": "tools.deny",
    "credentials.default_provider": "credentials.defaultProvider",
    "memory.search.provider": "memory.search.provider",
    "sandbox.mode": "agents.defaults.sandbox.mode",
    "sandbox.backend": "agents.defaults.sandbox.backend",
    "context.compaction.enabled": "agents.defaults.autoCompaction.enabled",
    "context.compaction.keep_recent_tokens": "agents.defaults.autoCompaction.keepRecentTokens",
    "healthcheck.interval_minutes": "gateway.healthcheck.interval",
}

def get_config(abstract_path: str) -> Optional[Any]:
    """从抽象路径获取 OpenClaw 配置值"""
    openclaw_path = CONFIG_MAPPING.get(abstract_path)
    if not openclaw_path:
        return None
    return adapter.config_get(openclaw_path)

def set_config(abstract_path: str, value: Any) -> bool:
    """设置抽象路径的配置值，映射到 OpenClaw 原生路径"""
    openclaw_path = CONFIG_MAPPING.get(abstract_path)
    if not openclaw_path:
        return False
    return adapter.config_set(openclaw_path, value)

def validate_config() -> bool:
    """验证当前配置是否符合 L1 契约"""
    valid, errors = adapter.config_validate()
    return valid

def get_all_mappings() -> Dict[str, str]:
    """获取完整的配置映射表"""
    return CONFIG_MAPPING.copy()
