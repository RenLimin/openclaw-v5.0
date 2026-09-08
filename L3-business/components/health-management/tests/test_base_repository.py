"""BaseRepository + 多租户基础测试。"""

import pytest
from pydantic import BaseModel

from repository.base import (
    BaseRepository,
    TenantModel,
    _current_tenant,
    set_current_tenant,
    reset_current_tenant,
)


# ─── 测试用模型 ──────────────────────────────────────────────────

class SampleModel(TenantModel):
    name: str
    value: int = 0


class SampleRepository(BaseRepository[SampleModel]):
    model_cls = SampleModel


# ─── 测试 ────────────────────────────────────────────────────────

class TestTenantContext:
    def test_current_tenant_default_error(self):
        # 在上下文外直接调用应抛出
        # 先保存并清除当前（fixture 里设了）
        from repository.base import _current_tenant_var
        saved = _current_tenant_var.get()
        _current_tenant_var.set(None)
        try:
            with pytest.raises(RuntimeError, match="No tenant context"):
                _current_tenant()
        finally:
            _current_tenant_var.set(saved)

    def test_set_and_get(self):
        token = set_current_tenant("t-abc")
        assert _current_tenant() == "t-abc"
        reset_current_tenant(token)


class TestBaseRepositoryCRUD:
    def test_create_and_get(self):
        obj = SampleRepository.create(name="foo", value=42)
        assert obj.id
        assert obj.name == "foo"
        assert obj.value == 42
        assert obj.tenant_id == "tenant-a-001"
        assert obj.is_deleted is False

        fetched = SampleRepository.get_by_id(obj.id)
        assert fetched is not None
        assert fetched.name == "foo"

    def test_get_nonexistent(self):
        assert SampleRepository.get_by_id("nope") is None

    def test_list(self):
        for i in range(5):
            SampleRepository.create(name=f"item-{i}", value=i)
        items = SampleRepository.list()
        assert len(items) == 5

    def test_filter(self):
        SampleRepository.create(name="a", value=1)
        SampleRepository.create(name="b", value=2)
        SampleRepository.create(name="c", value=2)
        results = SampleRepository.filter(value=2)
        assert len(results) == 2
        assert all(r.value == 2 for r in results)

    def test_update(self):
        obj = SampleRepository.create(name="old", value=1)
        updated = SampleRepository.update(obj.id, name="new", value=100)
        assert updated.name == "new"
        assert updated.value == 100
        assert updated.updated_at > obj.created_at

    def test_update_raises_not_found(self):
        with pytest.raises(ValueError, match="not found"):
            SampleRepository.update("nope", name="x")

    def test_delete_soft(self):
        obj = SampleRepository.create(name="del", value=99)
        SampleRepository.delete(obj.id)
        fetched = SampleRepository.get_by_id(obj.id)
        assert fetched is None
        # 计数排除软删除
        assert SampleRepository.count() == 0

    def test_count(self):
        for i in range(3):
            SampleRepository.create(name=f"x{i}", value=i)
        assert SampleRepository.count() == 3

    def test_create_with_explicit_tenant_mismatch_raises(self):
        with pytest.raises(ValueError, match="tenant_id mismatch"):
            SampleRepository.create(name="x", value=1, tenant_id="other")

    def test_update_cannot_change_id_or_tenant(self):
        obj = SampleRepository.create(name="x", value=1)
        updated = SampleRepository.update(
            obj.id, id="new-id", tenant_id="new-t", name="y"
        )
        assert updated.id == obj.id
        assert updated.tenant_id == obj.tenant_id


class TestMultiTenant:
    def test_tenant_isolation(self):
        token_a = set_current_tenant("t-a")
        a = SampleRepository.create(name="A", value=1)
        reset_current_tenant(token_a)

        token_b = set_current_tenant("t-b")
        b = SampleRepository.create(name="B", value=2)
        assert SampleRepository.count() == 1
        assert SampleRepository.get_by_id(a.id) is None
        reset_current_tenant(token_b)

        token_a = set_current_tenant("t-a")
        assert SampleRepository.count() == 1
        assert SampleRepository.get_by_id(b.id) is None
        reset_current_tenant(token_a)
