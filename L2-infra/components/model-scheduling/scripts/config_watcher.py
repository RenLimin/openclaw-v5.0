#!/usr/bin/env python3
"""热更新监听模块 — 监听配置文件变更,自动重载到内存。"""

import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

logger = logging.getLogger("model-scheduling.config")


class ConfigWatcher:
    """配置文件热更新监听器。"""

    def __init__(self, config_dir: str, reload_interval: int = 10):
        self.config_dir = Path(config_dir)
        self.reload_interval = reload_interval
        self._last_mtime: dict[str, float] = {}
        self._config_cache: dict[str, Any] = {}
        self._callbacks: dict[str, list[Callable]] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def register_callback(self, config_name: str, callback: Callable):
        self._callbacks.setdefault(config_name, []).append(callback)

    def load(self, config_name: str) -> Any:
        path = self.config_dir / config_name
        if not path.exists():
            logger.warning(f"配置文件不存在: {path}")
            return {}
        content = path.read_text(encoding="utf-8")
        if config_name.endswith((".yaml", ".yml")):
            if HAS_YAML:
                return yaml.safe_load(content) or {}
            logger.error("PyYAML 未安装")
            return {}
        elif config_name.endswith(".json"):
            import json
            return json.loads(content)
        return content

    def get(self, config_name: str) -> Any:
        if config_name not in self._config_cache:
            self._config_cache[config_name] = self.load(config_name)
            path = self.config_dir / config_name
            if path.exists():
                self._last_mtime[config_name] = path.stat().st_mtime
        return self._config_cache[config_name]

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
        logger.info("热更新监听已启动")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _watch_loop(self):
        while self._running:
            try:
                self._check_changes()
            except Exception as e:
                logger.error(f"热更新检查失败: {e}")
            time.sleep(self.reload_interval)

    def _check_changes(self):
        for config_name in list(self._config_cache.keys()):
            path = self.config_dir / config_name
            if not path.exists():
                continue
            mtime = path.stat().st_mtime
            if self._last_mtime.get(config_name) != mtime:
                new_config = self.load(config_name)
                self._config_cache[config_name] = new_config
                self._last_mtime[config_name] = mtime
                logger.info(f"热更新: {config_name}")
                for cb in self._callbacks.get(config_name, []):
                    try:
                        cb(None, new_config)
                    except Exception as e:
                        logger.error(f"回调失败: {e}")


_watcher: Optional[ConfigWatcher] = None


def get_watcher(config_dir: str = None) -> ConfigWatcher:
    global _watcher
    if _watcher is None:
        if config_dir is None:
            config_dir = str(Path(__file__).resolve().parent.parent / "config")
        _watcher = ConfigWatcher(config_dir)
    return _watcher
