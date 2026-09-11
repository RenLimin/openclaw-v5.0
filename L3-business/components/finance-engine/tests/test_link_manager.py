"""外部系统链接管理测试 — CRUD + 类型校验"""

import pytest
from unittest.mock import MagicMock

# 注意：integration/__init__.py 有 import bug（引用了不存在的 core.integration），
# 这里直接导入模块文件而非包
import sys
import importlib
from pathlib import Path

# 直接加载 links.py 模块
_links_path = Path(__file__).resolve().parent.parent / "integration" / "links.py"
_spec = importlib.util.spec_from_file_location("finance_engine.integration.links", str(_links_path))
_links_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_links_mod)

LinkManager = _links_mod.LinkManager
VALID_LINK_TYPES = _links_mod.VALID_LINK_TYPES


class TestLinkManager:
    """链接管理器"""

    def _make_manager(self):
        repo = MagicMock()
        return LinkManager(repo)

    def test_create_link(self):
        manager = self._make_manager()
        manager.repo.create.return_value = "link-1"
        result = manager.create_link("fam1", "招商银行", "bank", "https://cmbchina.com")
        assert result == "link-1"

    def test_create_link_invalid_type(self):
        """无效链接类型"""
        manager = self._make_manager()
        with pytest.raises(ValueError, match="Invalid link_type"):
            manager.create_link("fam1", "测试", "invalid_type", "https://test.com")

    def test_create_link_empty_name(self):
        """空名称"""
        manager = self._make_manager()
        with pytest.raises(ValueError, match="name cannot be empty"):
            manager.create_link("fam1", "", "bank", "https://test.com")

    def test_create_link_empty_url(self):
        """空 URL"""
        manager = self._make_manager()
        with pytest.raises(ValueError, match="URL cannot be empty"):
            manager.create_link("fam1", "测试", "bank", "")

    def test_list_links(self):
        manager = self._make_manager()
        manager.repo.list_by_family.return_value = [
            {"id": "1", "name": "招商银行", "link_type": "bank"},
            {"id": "2", "name": "券商A", "link_type": "broker"},
        ]
        results = manager.list_links("fam1")
        assert len(results) == 2

    def test_list_links_with_filter(self):
        """按类型过滤"""
        manager = self._make_manager()
        manager.repo.list_by_family.return_value = [
            {"id": "1", "name": "招商银行", "link_type": "bank"},
            {"id": "2", "name": "券商A", "link_type": "broker"},
        ]
        results = manager.list_links("fam1", link_type="bank")
        assert len(results) == 1
        assert results[0]["link_type"] == "bank"

    def test_list_by_type(self):
        manager = self._make_manager()
        manager.repo.list_by_family.return_value = [
            {"id": "1", "name": "招商银行", "link_type": "bank"},
            {"id": "2", "name": "工商银行", "link_type": "bank"},
            {"id": "3", "name": "券商A", "link_type": "broker"},
        ]
        result = manager.list_by_type("fam1")
        assert len(result["bank"]) == 2
        assert len(result["broker"]) == 1

    def test_update_link(self):
        manager = self._make_manager()
        manager.repo.conn = MagicMock()
        manager.repo.conn.total_changes = 1
        result = manager.update_link("link-1", name="新名称")
        assert result is True

    def test_update_link_invalid_type(self):
        """更新时无效类型"""
        manager = self._make_manager()
        manager.repo.conn = MagicMock()
        with pytest.raises(ValueError, match="Invalid link_type"):
            manager.update_link("link-1", link_type="invalid")

    def test_delete_link(self):
        manager = self._make_manager()
        manager.repo.conn = MagicMock()
        # repo.delete 执行后 total_changes 从 0 变为 1
        manager.repo.conn.total_changes = 0
        def _simulate_delete(link_id):
            manager.repo.conn.total_changes = 1
        manager.repo.delete.side_effect = _simulate_delete
        result = manager.delete_link("link-1")
        assert result is True

    def test_count_by_type(self):
        manager = self._make_manager()
        manager.repo.list_by_family.return_value = [
            {"id": "1", "name": "招商银行", "link_type": "bank"},
            {"id": "2", "name": "工商银行", "link_type": "bank"},
            {"id": "3", "name": "券商A", "link_type": "broker"},
        ]
        counts = manager.count_by_type("fam1")
        assert counts["bank"] == 2
        assert counts["broker"] == 1
        assert counts["fund"] == 0


class TestValidLinkTypes:
    """有效链接类型"""

    def test_valid_types(self):
        assert "bank" in VALID_LINK_TYPES
        assert "broker" in VALID_LINK_TYPES
        assert "fund" in VALID_LINK_TYPES
        assert "other" in VALID_LINK_TYPES
