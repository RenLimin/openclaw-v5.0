# -*- coding: utf-8 -*-
"""BaseModel 基础模型测试。"""

import datetime
from models.base import BaseModel, TenantContext


class TestBaseModel:
    """BaseModel 核心行为测试。"""

    def test_auto_generate_id(self):
        """未指定 id 时应自动生成 UUID。"""
        m = BaseModel()
        assert m.id is not None
        assert len(m.id) == 36  # UUID4 标准长度

    def test_preserve_explicit_id(self):
        """显式传入 id 时不应覆盖。"""
        m = BaseModel(id="custom-id-123")
        assert m.id == "custom-id-123"

    def test_auto_timestamps(self):
        """created_at 和 updated_at 应自动设置。"""
        before = datetime.datetime.now()
        m = BaseModel()
        after = datetime.datetime.now()
        assert before <= m.created_at <= after
        assert before <= m.updated_at <= after

    def test_tenant_injection_from_context(self):
        """tenant_id 默认应从 TenantContext 获取。"""
        TenantContext.set("tenant-abc")
        try:
            m = BaseModel()
            assert m.tenant_id == "tenant-abc"
        finally:
            TenantContext.set("system")

    def test_explicit_tenant_not_overridden(self):
        """显式传入非默认 tenant_id 时不应被上下文覆盖。"""
        TenantContext.set("tenant-abc")
        try:
            m = BaseModel(tenant_id="tenant-xyz")
            assert m.tenant_id == "tenant-xyz"
        finally:
            TenantContext.set("system")

    def test_dict_serialization(self):
        """dict() 应返回所有字段的字典。"""
        m = BaseModel(id="test-1", tenant_id="t1")
        d = m.dict()
        assert d["id"] == "test-1"
        assert d["tenant_id"] == "t1"
        assert "created_at" in d
        assert "updated_at" in d

    def test_table_name(self):
        """table_name() 应返回类名小写。"""
        assert BaseModel.table_name() == "basemodel"

    def test_unique_ids(self):
        """每次实例化应生成唯一 id。"""
        m1 = BaseModel()
        m2 = BaseModel()
        assert m1.id != m2.id
