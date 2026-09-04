"""tests/test_config.py — 配置管理测试。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestAppConfig(unittest.TestCase):
    """配置加载测试。"""

    def test_defaults(self):
        """默认配置加载。"""
        from core.config import AppConfig
        cfg = AppConfig.load()
        self.assertEqual(cfg.jwt_algorithm, "HS256")
        self.assertEqual(cfg.jwt_expire_hours, 24)
        self.assertEqual(cfg.api_port, 8000)
        self.assertTrue(cfg.webui_enabled)

    def test_config_file_override(self):
        """配置文件覆盖默认值。"""
        from core.config import AppConfig
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"api_port": 9000, "webui_enabled": False}, f)
            f.flush()
            cfg = AppConfig.load(config_file=f.name)
            self.assertEqual(cfg.api_port, 9000)
            self.assertFalse(cfg.webui_enabled)
        os.unlink(f.name)

    def test_env_override(self):
        """环境变量覆盖配置文件。"""
        from core.config import _load_env_overrides
        os.environ["DMS_API_PORT"] = "7777"
        os.environ["DMS_WEBUI_ENABLED"] = "false"
        try:
            overrides = _load_env_overrides()
            self.assertEqual(overrides.get("api_port"), 7777)
            self.assertEqual(overrides.get("webui_enabled"), False)
        finally:
            del os.environ["DMS_API_PORT"]
            del os.environ["DMS_WEBUI_ENABLED"]

    def test_modules_enabled_all(self):
        """modules_enabled = '*' 时全部启用。"""
        from core.config import AppConfig
        cfg = AppConfig.load()
        self.assertTrue(cfg.is_module_enabled("project"))
        self.assertTrue(cfg.is_module_enabled("anything"))

    def test_modules_enabled_list(self):
        """modules_enabled 为列表时按列表启用。"""
        from core.config import AppConfig
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"modules_enabled": ["project", "task"]}, f)
            f.flush()
            cfg = AppConfig.load(config_file=f.name)
            self.assertTrue(cfg.is_module_enabled("project"))
            self.assertTrue(cfg.is_module_enabled("task"))
            self.assertFalse(cfg.is_module_enabled("risk"))
        os.unlink(f.name)

    def test_to_safe_dict_hides_secrets(self):
        """to_safe_dict 隐藏 secret 字段。"""
        from core.config import AppConfig
        cfg = AppConfig.load()
        safe = cfg.to_safe_dict()
        self.assertEqual(safe["jwt_secret"], "***")


if __name__ == "__main__":
    unittest.main()
