# -*- coding: utf-8 -*-
"""BaseRepository 仓储层测试。"""

import pytest
from dataclasses import dataclass, field, asdict
from models.base import TenantContext
from repo.base_repo import BaseRepository


@dataclass
class DummyModel:
    """测试用简单模型，字段与 dummy 表结构对齐。"""
    id: str = None
    created_at: str = None
    updated_at: str = None
    tenant_id: str = "system"
    name: str = ""
    value: int = 0

    def dict(self):
        """返回字段字典，兼容 BaseRepository。"""
        return asdict(self)


class DummyRepository(BaseRepository[DummyModel]):
    """测试用仓储。"""

    def __init__(self, db_path: str):
        super().__init__(db_path, DummyModel, table_name="dummy")

    def create_table(self):
        """创建测试表。"""
        self.create_table_if_not_exists(
            "CREATE TABLE IF NOT EXISTS dummy ("
            "id TEXT PRIMARY KEY, created_at TEXT, updated_at TEXT, tenant_id TEXT, "
            "name TEXT, value INTEGER)"
        )


@pytest.fixture(autouse=True)
def reset_tenant():
    """每个测试前重置租户上下文为 system（与 DummyModel 默认值对齐）。"""
    TenantContext.set("system")


@pytest.fixture
def repo(tmp_path):
    """创建带临时文件的仓储实例。"""
    db_path = str(tmp_path / "test.db")
    r = DummyRepository(db_path)
    r.create_table()
    return r


class TestBaseRepository:
    """BaseRepository CRUD 操作测试。"""

    def test_insert_and_get(self, repo):
        """插入后应能通过 ID 获取。"""
        m = DummyModel(id="test-1", name="test", value=42)
        assert repo.insert(m) is True
        result = repo.get_by_id("test-1")
        assert result is not None
        assert result.name == "test"
        assert result.value == 42

    def test_get_nonexistent_returns_none(self, repo):
        """获取不存在的记录应返回 None。"""
        assert repo.get_by_id("no-such-id") is None

    def test_update(self, repo):
        """更新应修改记录。"""
        m = DummyModel(id="test-2", name="old", value=1)
        repo.insert(m)
        m.name = "new"
        m.value = 99
        assert repo.update(m) is True
        result = repo.get_by_id("test-2")
        assert result.name == "new"
        assert result.value == 99

    def test_upsert_insert_new(self, repo):
        """upsert 不存在的记录应插入。"""
        m = DummyModel(id="test-3", name="fresh", value=10)
        assert repo.upsert(m) is True
        assert repo.get_by_id("test-3") is not None

    def test_upsert_update_existing(self, repo):
        """upsert 已存在的记录应更新。"""
        m = DummyModel(id="test-4", name="original", value=1)
        repo.insert(m)
        m.name = "updated"
        repo.upsert(m)
        result = repo.get_by_id("test-4")
        assert result.name == "updated"

    def test_delete(self, repo):
        """删除后应无法获取。"""
        m = DummyModel(id="test-5", name="to-delete", value=0)
        repo.insert(m)
        assert repo.delete_by_id("test-5") is True
        assert repo.get_by_id("test-5") is None

    def test_delete_nonexistent_returns_false(self, repo):
        """删除不存在的记录应返回 False。"""
        assert repo.delete_by_id("no-such-id") is False

    def test_list_all(self, repo):
        """应列出所有记录。"""
        repo.insert(DummyModel(id="a1", name="a", value=1))
        repo.insert(DummyModel(id="a2", name="b", value=2))
        results = repo.list_all()
        assert len(results) == 2

    def test_count(self, repo):
        """count 应返回记录数。"""
        assert repo.count() == 0
        repo.insert(DummyModel(id="c1", name="a", value=1))
        repo.insert(DummyModel(id="c2", name="b", value=2))
        assert repo.count() == 2
