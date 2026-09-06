"""
core/config.py — 配置管理
支持环境变量 > 配置文件 > 默认值 三级优先级。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# 默认配置
# ---------------------------------------------------------------------------

_DEFAULTS: dict[str, Any] = {
    # JWT
    "jwt_secret": "dev-secret-change-in-production",
    "jwt_algorithm": "HS256",
    "jwt_expire_hours": 24,
    # API
    "api_host": "127.0.0.1",
    "api_port": 8000,
    "api_cors_origins": ["*"],
    # 租户
    "default_tenant": "system",
    "tenant_isolation": "shared",  # shared | schema | database
    # Web UI
    "webui_enabled": True,
    "webui_title": "DMS Framework",
    # 模块开关
    "modules_enabled": "*",  # "*" = 全部, 或 ["project", "task", ...]
    # 数据库
    "db_url": "sqlite:///delivery.db",
    # 日志
    "log_level": "INFO",
}


# ---------------------------------------------------------------------------
# 配置加载
# ---------------------------------------------------------------------------


def _load_config_file(path: str | None = None) -> dict[str, Any]:
    """从 JSON 文件加载配置。"""
    if path:
        p = Path(path)
        if p.is_file():
            with open(p) as f:
                return json.load(f)
    # 默认查找 dms.json
    for candidate in ["dms.json", "config/dms.json", "/etc/dms/config.json"]:
        p = Path(candidate)
        if p.is_file():
            with open(p) as f:
                return json.load(f)
    return {}


def _load_env_overrides() -> dict[str, Any]:
    """从环境变量加载配置（前缀 DMS_）。

    例: DMS_JWT_SECRET=xxx → {"jwt_secret": "xxx"}
         DMS_API_PORT=8080 → {"api_port": 8080}
         DMS_MODULES_ENABLED=project,task → {"modules_enabled": ["project", "task"]]
    """
    overrides: dict[str, Any] = {}
    prefix = "DMS_"
    special = {
        "DMS_MODULES_ENABLED": ("modules_enabled", lambda v: v.split(",") if v != "*" else "*"),
    }

    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue
        config_key = key[len(prefix):].lower()

        # 特殊处理
        if key in special:
            field_name, transform = special[key]
            overrides[field_name] = transform(value)
            continue

        # 自动类型推断
        if value.isdigit():
            overrides[config_key] = int(value)
        elif value.lower() in ("true", "false"):
            overrides[config_key] = value.lower() == "true"
        else:
            overrides[config_key] = value

    return overrides


@dataclass
class AppConfig:
    """应用配置（不可变，加载后只读）。"""

    # JWT
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 24
    # API
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    api_cors_origins: list[str] = field(default_factory=lambda: ["*"])
    # 租户
    default_tenant: str = "system"
    tenant_isolation: str = "shared"
    # Web UI
    webui_enabled: bool = True
    webui_title: str = "DMS Framework"
    # 模块开关
    modules_enabled: str | list[str] = "*"
    # 数据库
    db_url: str = "sqlite:///delivery.db"
    # 日志
    log_level: str = "INFO"

    @classmethod
    def load(cls, config_file: str | None = None) -> "AppConfig":
        """加载配置：默认值 → 配置文件 → 环境变量。"""
        merged = dict(_DEFAULTS)
        # 1. 配置文件覆盖默认值
        file_config = _load_config_file(config_file)
        merged.update(file_config)
        # 2. 环境变量覆盖配置文件
        env_overrides = _load_env_overrides()
        merged.update(env_overrides)

        # 过滤出 dataclass 字段
        import dataclasses
        valid_fields = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in merged.items() if k in valid_fields}
        return cls(**filtered)

    def is_module_enabled(self, module_name: str) -> bool:
        """检查模块是否启用。"""
        if self.modules_enabled == "*":
            return True
        if isinstance(self.modules_enabled, list):
            return module_name in self.modules_enabled
        return True

    def to_safe_dict(self) -> dict[str, Any]:
        """返回安全的配置 dict（不含 secret）。"""
        d = {}
        for k, v in self.__dict__.items():
            if "secret" in k.lower() or "password" in k.lower():
                d[k] = "***"
            else:
                d[k] = v
        return d


# 全局实例（懒加载）
_config: AppConfig | None = None


def get_config(config_file: str | None = None, force_reload: bool = False) -> AppConfig:
    """获取全局配置实例（单例）。"""
    global _config
    if _config is None or force_reload:
        _config = AppConfig.load(config_file)
    return _config
