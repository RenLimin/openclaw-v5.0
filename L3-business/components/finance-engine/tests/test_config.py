"""配置模块测试 — Settings 加载、环境变量覆盖、默认值"""

import os
import pytest
from pathlib import Path

# 确保每个测试用干净的环境
import finance_engine.config as config_mod


class TestSettingsDefaults:
    """Settings 默认值"""

    def _make_settings(self, monkeypatch):
        """创建 Settings，清除相关环境变量"""
        for key in ["FIN4_HOST", "FIN4_PORT", "FIN4_DB_DIR", "FIN4_FAMILY_ID",
                     "FIN4_APP_NAME", "FIN4_DEBUG", "FIN4_EXTERNAL_READONLY"]:
            monkeypatch.delenv(key, raising=False)
        # 重置单例
        config_mod._settings = None
        return config_mod.Settings()

    def test_default_host(self, monkeypatch):
        s = self._make_settings(monkeypatch)
        assert s.host == "127.0.0.1"

    def test_default_port(self, monkeypatch):
        s = self._make_settings(monkeypatch)
        assert s.port == 8500

    def test_default_family_id(self, monkeypatch):
        s = self._make_settings(monkeypatch)
        assert s.family_id == "default"

    def test_default_app_name(self, monkeypatch):
        s = self._make_settings(monkeypatch)
        assert s.app_name == "FIN-L4 家庭理财管理系统"

    def test_default_debug(self, monkeypatch):
        s = self._make_settings(monkeypatch)
        assert s.debug is False

    def test_default_external_readonly(self, monkeypatch):
        s = self._make_settings(monkeypatch)
        assert s.external_readonly is True


class TestSettingsEnvOverride:
    """环境变量覆盖"""

    def test_env_host(self, monkeypatch):
        monkeypatch.setenv("FIN4_HOST", "0.0.0.0")
        config_mod._settings = None
        s = config_mod.Settings()
        assert s.host == "0.0.0.0"

    def test_env_port(self, monkeypatch):
        monkeypatch.setenv("FIN4_PORT", "9090")
        config_mod._settings = None
        s = config_mod.Settings()
        assert s.port == 9090

    def test_env_port_invalid(self, monkeypatch):
        """无效端口值应回退到默认值"""
        monkeypatch.setenv("FIN4_PORT", "not_a_number")
        config_mod._settings = None
        s = config_mod.Settings()
        assert s.port == 8500

    def test_env_family_id(self, monkeypatch):
        monkeypatch.setenv("FIN4_FAMILY_ID", "family-abc")
        config_mod._settings = None
        s = config_mod.Settings()
        assert s.family_id == "family-abc"

    def test_env_debug_true(self, monkeypatch):
        monkeypatch.setenv("FIN4_DEBUG", "1")
        config_mod._settings = None
        s = config_mod.Settings()
        assert s.debug is True

    def test_env_debug_false(self, monkeypatch):
        monkeypatch.setenv("FIN4_DEBUG", "0")
        config_mod._settings = None
        s = config_mod.Settings()
        assert s.debug is False

    def test_env_external_readonly(self, monkeypatch):
        monkeypatch.setenv("FIN4_EXTERNAL_READONLY", "0")
        config_mod._settings = None
        s = config_mod.Settings()
        assert s.external_readonly is False


class TestSettingsDbPath:
    """数据库路径"""

    def test_default_db_dir(self, monkeypatch, tmp_path):
        """默认 db_dir 为 ~/.fin-l4"""
        monkeypatch.delenv("FIN4_DB_DIR", raising=False)
        config_mod._settings = None
        s = config_mod.Settings()
        # 默认路径是 ~/.fin-l4
        assert s.db_dir == Path(os.path.expanduser("~/.fin-l4"))

    def test_custom_db_dir(self, monkeypatch, tmp_path):
        """自定义 db_dir"""
        monkeypatch.setenv("FIN4_DB_DIR", str(tmp_path))
        config_mod._settings = None
        s = config_mod.Settings()
        assert s.db_dir == tmp_path

    def test_db_path(self, monkeypatch, tmp_path):
        monkeypatch.setenv("FIN4_DB_DIR", str(tmp_path))
        config_mod._settings = None
        s = config_mod.Settings()
        assert s.db_path == str(tmp_path / "fin_l4.db")


class TestSettingsToDict:
    """to_dict 序列化"""

    def test_to_dict_keys(self, monkeypatch):
        for key in ["FIN4_HOST", "FIN4_PORT", "FIN4_DB_DIR", "FIN4_FAMILY_ID",
                     "FIN4_APP_NAME", "FIN4_DEBUG", "FIN4_EXTERNAL_READONLY"]:
            monkeypatch.delenv(key, raising=False)
        config_mod._settings = None
        s = config_mod.Settings()
        d = s.to_dict()
        expected_keys = {"host", "port", "db_dir", "db_path", "family_id",
                         "app_name", "debug", "external_readonly"}
        assert set(d.keys()) == expected_keys


class TestGetSettings:
    """get_settings 单例"""

    def test_singleton(self, monkeypatch):
        for key in ["FIN4_HOST", "FIN4_PORT", "FIN4_DB_DIR", "FIN4_FAMILY_ID",
                     "FIN4_APP_NAME", "FIN4_DEBUG", "FIN4_EXTERNAL_READONLY"]:
            monkeypatch.delenv(key, raising=False)
        config_mod._settings = None
        s1 = config_mod.get_settings()
        s2 = config_mod.get_settings()
        assert s1 is s2


class TestLoadDotenv:
    """_load_dotenv 轻量 .env 加载"""

    def test_load_existing_dotenv(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("FIN4_HOST=10.0.0.1\nFIN4_PORT=7777\n# comment\n\n")
        # 不覆盖已存在的环境变量
        os.environ["FIN4_HOST"] = "192.168.1.1"
        config_mod._load_dotenv(env_file)
        assert os.environ.get("FIN4_HOST") == "192.168.1.1"
        assert os.environ.get("FIN4_PORT") == "7777"
        # 清理
        del os.environ["FIN4_HOST"]
        del os.environ["FIN4_PORT"]

    def test_load_nonexistent_dotenv(self, tmp_path):
        """不存在的 .env 文件不报错"""
        env_file = tmp_path / "nonexistent.env"
        config_mod._load_dotenv(env_file)  # 不应抛异常

    def test_load_dotenv_quotes(self, tmp_path):
        """带引号的值"""
        env_file = tmp_path / ".env"
        env_file.write_text('FIN4_FAMILY_ID="my-family"\n')
        if "FIN4_FAMILY_ID" in os.environ:
            del os.environ["FIN4_FAMILY_ID"]
        config_mod._load_dotenv(env_file)
        assert os.environ.get("FIN4_FAMILY_ID") == "my-family"
        del os.environ["FIN4_FAMILY_ID"]
