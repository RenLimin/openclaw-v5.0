"""BDMS 配置模块 — 统一管理所有配置项。"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

_cache: Optional[Dict[str, Any]] = None


def get_config() -> Dict[str, Any]:
    """获取全局配置（带缓存）。

    配置来源优先级：
    1. 环境变量（BDMS_ 前缀）
    2. 项目 config/config.json
    3. 默认值
    """
    global _cache
    if _cache is not None:
        return _cache

    config: Dict[str, Any] = {
        # wecom 相关
        "wecom.enable_api": True,
        "wecom.enable_browser": True,
        "wecom.cli_bin_path": "",
        "wecom.config_dir": "",
        # 通用
        "log.level": "INFO",
    }

    # 从 config.json 加载
    try:
        from bdms.core.paths import CONFIG_DIR
        cfg_file = CONFIG_DIR / "config.json"
        if cfg_file.exists():
            with open(cfg_file, "r", encoding="utf-8") as f:
                file_cfg = json.load(f)
                config.update(file_cfg)
    except Exception:
        pass

    # 环境变量覆盖（BDMS_ 前缀，下划线分隔层级）
    for key, value in os.environ.items():
        if not key.startswith("BDMS_"):
            continue
        cfg_key = key[5:].lower().replace("_", ".")
        # 转换布尔值
        if value.lower() in ("true", "1", "yes"):
            config[cfg_key] = True
        elif value.lower() in ("false", "0", "no"):
            config[cfg_key] = False
        else:
            config[cfg_key] = value

    _cache = config
    return config


def get(key: str, default: Any = None) -> Any:
    """获取单个配置项。"""
    cfg = get_config()
    return cfg.get(key, default)


def reset_config() -> None:
    """重置配置缓存（测试用）。"""
    global _cache
    _cache = None
