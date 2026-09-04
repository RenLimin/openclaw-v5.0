"""tests/test_webui.py — Web UI 页面测试。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@unittest.skipUnless(
    __import__("importlib.util", fromlist=["find_spec"]).find_spec("jinja2") is not None,
    "jinja2 not installed",
)
class TestWebUI(unittest.TestCase):
    """Web UI 页面渲染测试。"""

    @classmethod
    def setUpClass(cls):
        from core.api import create_app
        from core.auth import _user_store, create_access_token
        from core.database import Database
        from core.migrations import migrate
        from core.saas import TenantContext
        from dms import build_registry
        from fastapi.testclient import TestClient

        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        cls.db_path = tmp.name
        cls.db = Database(f"sqlite:///{cls.db_path}")
        migrate(cls.db.connect())
        TenantContext.set("test-tenant")

        cls.registry = build_registry()
        cls.registry.initialize_all(cls.db, {})
        cls.app = create_app(cls.registry, cls.db, {})
        cls.client = TestClient(cls.app)

        cls.user_id = _user_store.create_user("webui", "pass", tenant_id="test-tenant")
        cls.token = create_access_token(cls.user_id, "test-tenant")
        cls.headers = {"Authorization": f"Bearer {cls.token}"}

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        try:
            os.unlink(cls.db_path)
        except OSError:
            pass

    def test_dashboard_renders(self):
        """GET / 返回 HTML。"""
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers.get("content-type", ""))
        self.assertIn("DMS", resp.text)

    def test_projects_page(self):
        """GET /projects 返回 HTML。"""
        resp = self.client.get("/projects")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers.get("content-type", ""))

    def test_modules_page(self):
        """GET /modules 返回 HTML。"""
        resp = self.client.get("/modules")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers.get("content-type", ""))

    def test_project_detail_page(self):
        """GET /projects/{id} 返回 HTML。"""
        # 先创建项目
        resp = self.client.post(
            "/api/v1/project",
            json={"name": "UI Test Project"},
            headers=self.headers,
        )
        pid = resp.json()["id"]
        # Web UI 管理视图跨 tenant 查询
        resp = self.client.get(f"/projects/{pid}")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("UI Test Project", resp.text)

    def test_static_css(self):
        """GET /static/style.css 返回 CSS。"""
        resp = self.client.get("/static/style.css")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("body", resp.text)


if __name__ == "__main__":
    unittest.main()
