"""tests/test_tenant.py — 租户管理模块测试。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.database import Database
from core.migrations import migrate
from core.saas import TenantContext
from modules.tenant import TenantModule, manifest as tenant_manifest


class TestTenantModule(unittest.TestCase):
    """租户模块单元测试。"""

    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        self.db_path = tmp.name
        self.db = Database(f"sqlite:///{self.db_path}")
        migrate(self.db.connect())
        TenantContext.set("system")
        self.mod = TenantModule(tenant_manifest)
        self.mod.initialize(self.db, {}, None)

    def tearDown(self):
        self.db.close()
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def test_create_tenant(self):
        """创建租户。"""
        t = self.mod.create_tenant("Acme Corp", slug="acme", tier="business")
        self.assertEqual(t.name, "Acme Corp")
        self.assertEqual(t.slug, "acme")
        self.assertEqual(t.tier, "business")
        self.assertEqual(t.status, "active")
        self.assertTrue(t.id)

    def test_create_tenant_auto_slug(self):
        """自动生成 slug。"""
        t = self.mod.create_tenant("My Company")
        self.assertEqual(t.slug, "my-company")

    def test_create_tenant_invalid_tier(self):
        """非法 tier 报错。"""
        with self.assertRaises(ValueError):
            self.mod.create_tenant("Bad", tier="platinum")

    def test_get_tenant(self):
        """获取租户。"""
        t = self.mod.create_tenant("Test", slug="test")
        fetched = self.mod.get_tenant(t.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.name, "Test")

    def test_get_tenant_by_slug(self):
        """按 slug 查找。"""
        self.mod.create_tenant("Slug Test", slug="slug-test")
        t = self.mod.get_tenant_by_slug("slug-test")
        self.assertIsNotNone(t)
        self.assertEqual(t.name, "Slug Test")

    def test_list_tenants(self):
        """列出租户。"""
        self.mod.create_tenant("T1", slug="t1")
        self.mod.create_tenant("T2", slug="t2")
        tenants = self.mod.list_tenants()
        self.assertGreaterEqual(len(tenants), 2)

    def test_update_tenant(self):
        """更新租户。"""
        t = self.mod.create_tenant("Old Name", slug="update-test")
        updated = self.mod.update_tenant(t.id, name="New Name", tier="enterprise")
        self.assertIsNotNone(updated)
        self.assertEqual(updated.name, "New Name")
        self.assertEqual(updated.tier, "enterprise")

    def test_delete_tenant(self):
        """删除租户。"""
        t = self.mod.create_tenant("To Delete", slug="delete-me")
        result = self.mod.delete_tenant(t.id)
        self.assertTrue(result)
        self.assertIsNone(self.mod.get_tenant(t.id))

    def test_delete_nonexistent(self):
        """删除不存在的租户。"""
        result = self.mod.delete_tenant("nonexistent")
        self.assertFalse(result)

    def test_check_quota(self):
        """配额检查。"""
        t = self.mod.create_tenant("Quota Test", slug="quota", max_projects=5)
        result = self.mod.check_quota(t.id, "projects", 3)
        self.assertTrue(result["allowed"])
        self.assertEqual(result["remaining"], 2)

    def test_check_quota_exceeded(self):
        """配额超限。"""
        t = self.mod.create_tenant("Over", slug="over", max_projects=2)
        result = self.mod.check_quota(t.id, "projects", 5)
        self.assertFalse(result["allowed"])
        self.assertEqual(result["remaining"], 0)


class TestTenantAPI(unittest.TestCase):
    """租户 API 端点测试。"""

    @classmethod
    def setUpClass(cls):
        from core.api import create_app
        from core.auth import _user_store, create_access_token
        from fastapi.testclient import TestClient

        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        cls.db_path = tmp.name
        cls.db = Database(f"sqlite:///{cls.db_path}")
        migrate(cls.db.connect())
        TenantContext.set("test-tenant")

        # 动态导入 build_registry 确保 tenant 已注册
        from dms import build_registry
        cls.registry = build_registry()
        cls.registry.initialize_all(cls.db, {})
        cls.app = create_app(cls.registry, cls.db, {})
        cls.client = TestClient(cls.app)

        cls.user_id = _user_store.create_user("tenantadmin", "pass", tenant_id="test-tenant", roles=["admin"])
        cls.token = create_access_token(cls.user_id, "test-tenant", roles=["admin"])
        cls.headers = {"Authorization": f"Bearer {cls.token}"}

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        try:
            os.unlink(cls.db_path)
        except OSError:
            pass

    def test_list_tenants_api(self):
        """GET /api/v1/tenants。"""
        resp = self.client.get("/api/v1/tenants", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)

    def test_create_tenant_api(self):
        """POST /api/v1/tenants。"""
        resp = self.client.post(
            "/api/v1/tenants",
            json={"name": "API Tenant", "slug": "api-tenant", "tier": "free"},
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["name"], "API Tenant")
        self.assertEqual(data["slug"], "api-tenant")

    def test_get_tenant_api(self):
        """GET /api/v1/tenants/{id}。"""
        resp = self.client.post(
            "/api/v1/tenants",
            json={"name": "Get Test", "slug": "get-test"},
            headers=self.headers,
        )
        tid = resp.json()["id"]
        resp = self.client.get(f"/api/v1/tenants/{tid}", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["id"], tid)

    def test_delete_tenant_api(self):
        """DELETE /api/v1/tenants/{id}。"""
        resp = self.client.post(
            "/api/v1/tenants",
            json={"name": "Del Test", "slug": "del-test"},
            headers=self.headers,
        )
        tid = resp.json()["id"]
        resp = self.client.delete(f"/api/v1/tenants/{tid}", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        # 确认已删除
        resp = self.client.get(f"/api/v1/tenants/{tid}", headers=self.headers)
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
