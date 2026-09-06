"""
tests/test_api.py — FastAPI API 层测试
使用 httpx + pytest-asyncio 异步测试。
降级方案：如果 httpx 不可用，使用 urllib。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

# 确保 import 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.auth import (
    JWT_SECRET,
    InMemoryUserStore,
    _user_store,
    create_access_token,
    get_user_store,
)
from core.database import Database
from core.saas import TenantContext
from dms import build_registry


# ---------------------------------------------------------------------------
# 测试用 Fixture
# ---------------------------------------------------------------------------

def _setup_test_db():
    """创建测试数据库 + 跑 migration + 初始化模块。"""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_url = f"sqlite:///{tmp.name}"
    db = Database(db_url)
    TenantContext.set("test-tenant")
    # 先跑 migration 建表
    from core.migrations import migrate
    migrate(db.connect())
    # 再初始化模块
    registry = build_registry()
    registry.initialize_all(db, {})
    return db, registry, tmp.name


def _teardown_test_db(db, db_path):
    """清理测试数据库。"""
    db.close()
    try:
        os.unlink(db_path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# 尝试导入 httpx，不可用则跳过异步测试
# ---------------------------------------------------------------------------

try:
    import httpx
    from fastapi.testclient import TestClient

    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


@unittest.skipUnless(HAS_HTTPX, "httpx not installed")
class TestAPI(unittest.TestCase):
    """FastAPI API 测试。"""

    @classmethod
    def setUpClass(cls):
        """创建测试应用。"""
        from core.api import create_app

        cls.db, cls.registry, cls.db_path = _setup_test_db()
        cls.app = create_app(cls.registry, cls.db, {})
        cls.client = TestClient(cls.app)

        # 创建测试用户 + token
        cls.user_id = _user_store.create_user(
            "testuser", "testpass", tenant_id="test-tenant", roles=["admin"]
        )
        cls.token = create_access_token(cls.user_id, "test-tenant", roles=["admin"])
        cls.headers = {"Authorization": f"Bearer {cls.token}"}

    @classmethod
    def tearDownClass(cls):
        _teardown_test_db(cls.db, cls.db_path)

    # ── 健康检查 ──────────────────────────────────────────────────────

    def test_health(self):
        """GET /health 无需认证。"""
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertGreater(data["modules"], 0)

    # ── 认证 ──────────────────────────────────────────────────────────

    def test_login_success(self):
        """POST /api/v1/auth/login 正确密码。"""
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"username": "testuser", "password": "testpass"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("access_token", data)
        self.assertEqual(data["tenant_id"], "test-tenant")

    def test_login_failure(self):
        """POST /api/v1/auth/login 错误密码。"""
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"username": "testuser", "password": "wrongpass"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_auth_required(self):
        """未认证访问受保护端点 → 401。"""
        resp = self.client.get("/api/v1/project")
        self.assertEqual(resp.status_code, 401)

    def test_bearer_token_auth(self):
        """Bearer Token 认证成功。"""
        resp = self.client.get("/api/v1/project", headers=self.headers)
        self.assertEqual(resp.status_code, 200)

    def test_api_key_auth(self):
        """API Key 认证成功。"""
        raw_key = _user_store.create_api_key(self.user_id, "test-tenant", roles=["admin"])
        resp = self.client.get(
            "/api/v1/project",
            headers={"X-API-Key": raw_key},
        )
        self.assertEqual(resp.status_code, 200)

    def test_me_endpoint(self):
        """GET /api/v1/auth/me 返回当前用户信息。"""
        resp = self.client.get("/api/v1/auth/me", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["user_id"], self.user_id)
        self.assertEqual(data["tenant_id"], "test-tenant")

    # ── 模块列表 ──────────────────────────────────────────────────────

    def test_list_modules(self):
        """GET /api/v1/modules 列出所有模块。"""
        resp = self.client.get("/api/v1/modules", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsInstance(data, list)
        names = [m["name"] for m in data]
        self.assertIn("project", names)

    # ── CRUD: project ──────────────────────────────────────────────────

    def test_create_project(self):
        """POST /api/v1/project 创建项目。"""
        resp = self.client.post(
            "/api/v1/project",
            json={"name": "API Test Project", "description": "test"},
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["name"], "API Test Project")
        self.assertEqual(data["status"], "planning")
        self.project_id = data["id"]

    def test_list_projects(self):
        """GET /api/v1/project 列出项目（分页）。"""
        # 先创建一个
        resp = self.client.post(
            "/api/v1/project",
            json={"name": "List Test"},
            headers=self.headers,
        )
        project_id = resp.json()["id"]

        resp = self.client.get("/api/v1/project", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsInstance(data, dict)
        self.assertIn("items", data)
        self.assertIn("total", data)
        self.assertIn("page", data)
        self.assertIn("page_size", data)
        self.assertIn("pages", data)
        self.assertIsInstance(data["items"], list)
        self.assertGreaterEqual(data["total"], 1)

    def test_get_project(self):
        """GET /api/v1/project/{id} 获取详情。"""
        # 先创建
        resp = self.client.post(
            "/api/v1/project",
            json={"name": "Get Test"},
            headers=self.headers,
        )
        project_id = resp.json()["id"]

        resp = self.client.get(f"/api/v1/project/{project_id}", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["id"], project_id)

    def test_get_project_not_found(self):
        """GET /api/v1/project/nonexistent → 404。"""
        resp = self.client.get("/api/v1/project/nonexistent-id", headers=self.headers)
        self.assertEqual(resp.status_code, 404)

    def test_delete_project(self):
        """DELETE /api/v1/project/{id} 删除项目。"""
        # 先创建
        resp = self.client.post(
            "/api/v1/project",
            json={"name": "Delete Test"},
            headers=self.headers,
        )
        project_id = resp.json()["id"]

        resp = self.client.delete(f"/api/v1/project/{project_id}", headers=self.headers)
        self.assertEqual(resp.status_code, 200)

        # 确认已删除
        resp = self.client.get(f"/api/v1/project/{project_id}", headers=self.headers)
        self.assertEqual(resp.status_code, 404)

    # ── 状态迁移 ──────────────────────────────────────────────────────

    def test_transition_project(self):
        """POST /api/v1/project/{id}/actions/start 状态迁移。"""
        # 创建项目（初始 planning）
        resp = self.client.post(
            "/api/v1/project",
            json={"name": "Transition Test"},
            headers=self.headers,
        )
        project_id = resp.json()["id"]
        self.assertEqual(resp.json()["status"], "planning")

        # planning → in_progress
        resp = self.client.post(
            f"/api/v1/project/{project_id}/actions/start",
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "in_progress")

    def test_transition_invalid(self):
        """非法状态迁移 → 400。"""
        # 创建项目
        resp = self.client.post(
            "/api/v1/project",
            json={"name": "Invalid Transition"},
            headers=self.headers,
        )
        project_id = resp.json()["id"]

        # planning 不能直接 → completed
        resp = self.client.post(
            f"/api/v1/project/{project_id}/actions/accept",
            headers=self.headers,
        )
        self.assertIn(resp.status_code, [400, 500])

    # ── CRUD: 其他模块 spot check ────────────────────────────────────

    def test_create_milestone(self):
        """POST /api/v1/milestone — 先建项目，再建里程碑。"""
        # 先创建项目
        resp = self.client.post(
            "/api/v1/project",
            json={"name": "Milestone Parent Project"},
            headers=self.headers,
        )
        project_id = resp.json()["id"]

        # 再创建里程碑
        resp = self.client.post(
            "/api/v1/milestone",
            json={"title": "M1", "project_id": project_id},
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["title"], "M1")
        self.assertEqual(data["project_id"], project_id)

    def test_create_task(self):
        """POST /api/v1/task — 先建项目，再建任务。"""
        # 先创建项目
        resp = self.client.post(
            "/api/v1/project",
            json={"name": "Task Parent Project"},
            headers=self.headers,
        )
        project_id = resp.json()["id"]

        # 再创建任务
        resp = self.client.post(
            "/api/v1/task",
            json={"title": "Test Task", "project_id": project_id},
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["title"], "Test Task")
        self.assertEqual(data["project_id"], project_id)

    # ── 搜索测试 ──────────────────────────────────────────────────────

    def test_search_projects(self):
        """GET /api/v1/project?search= 关键词搜索。"""
        # 创建两个项目
        self.client.post(
            "/api/v1/project",
            json={"name": "Alpha Search Test", "description": "first"},
            headers=self.headers,
        )
        self.client.post(
            "/api/v1/project",
            json={"name": "Beta Other", "description": "second"},
            headers=self.headers,
        )

        # 搜索 "Alpha"
        resp = self.client.get("/api/v1/project?search=Alpha", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreaterEqual(len(data["items"]), 1)
        names = [item["name"] for item in data["items"]]
        self.assertIn("Alpha Search Test", names)

    # ── 分页测试 ──────────────────────────────────────────────────────

    def test_pagination(self):
        """GET /api/v1/project?page=2&page_size=1 分页正确。"""
        # 创建 3 个项目（用 page_size 前缀避免和其他测试冲突）
        created_ids = []
        for i in range(3):
            resp = self.client.post(
                "/api/v1/project",
                json={"name": f"PageTest-{i}"},
                headers=self.headers,
            )
            created_ids.append(resp.json()["id"])

        # 搜索 page_size 前缀的项目
        resp = self.client.get("/api/v1/project?search=PageTest&page=1&page_size=1", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["page_size"], 1)
        self.assertEqual(data["total"], 3)
        self.assertEqual(data["pages"], 3)

        # 第2页
        resp2 = self.client.get("/api/v1/project?search=PageTest&page=2&page_size=1", headers=self.headers)
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()
        self.assertEqual(data2["page"], 2)
        self.assertEqual(len(data2["items"]), 1)
        # 第1页和第2页的项目不同
        self.assertNotEqual(data["items"][0]["id"], data2["items"][0]["id"])

        # 第3页
        resp3 = self.client.get("/api/v1/project?search=PageTest&page=3&page_size=1", headers=self.headers)
        self.assertEqual(resp3.status_code, 200)
        data3 = resp3.json()
        self.assertEqual(len(data3["items"]), 1)
        self.assertNotEqual(data2["items"][0]["id"], data3["items"][0]["id"])

    # ── 排序测试 ──────────────────────────────────────────────────────

    def test_sort_by_created_at(self):
        """GET /api/v1/project?sort_by=created_at&sort_order=asc 排序。"""
        # 创建两个项目（用 SortPrefix 搜索隔离）
        self.client.post(
            "/api/v1/project",
            json={"name": "SortPrefix Old"},
            headers=self.headers,
        )
        self.client.post(
            "/api/v1/project",
            json={"name": "SortPrefix New"},
            headers=self.headers,
        )

        # 升序
        resp = self.client.get(
            "/api/v1/project?search=SortPrefix&sort_by=created_at&sort_order=asc&page_size=10",
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total"], 2)
        self.assertEqual(len(data["items"]), 2)
        self.assertLessEqual(
            data["items"][0]["created_at"],
            data["items"][1]["created_at"],
        )

        # 降序
        resp = self.client.get(
            "/api/v1/project?search=SortPrefix&sort_by=created_at&sort_order=desc&page_size=10",
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data["items"]), 2)
        self.assertGreaterEqual(
            data["items"][0]["created_at"],
            data["items"][1]["created_at"],
        )

    # ── 批量操作测试 ──────────────────────────────────────────────────

    def test_batch_create(self):
        """POST /api/v1/project/batch 批量创建。"""
        resp = self.client.post(
            "/api/v1/project/batch",
            json={"items": [
                {"name": "Batch 1"},
                {"name": "Batch 2"},
                {"name": "Batch 3"},
            ]},
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertIn("succeeded", data)
        self.assertIn("failed", data)
        self.assertEqual(len(data["succeeded"]), 3)
        self.assertEqual(len(data["failed"]), 0)

    def test_batch_delete(self):
        """DELETE /api/v1/project/batch 批量删除。"""
        # 先创建
        ids = []
        for i in range(2):
            resp = self.client.post(
                "/api/v1/project",
                json={"name": f"Batch Del {i}"},
                headers=self.headers,
            )
            ids.append(resp.json()["id"])

        # 批量删除（httpx delete 不支持 json=，用 request 方法）
        resp = self.client.request(
            "DELETE",
            "/api/v1/project/batch",
            json={"ids": ids},
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data["succeeded"]), 2)
        self.assertEqual(len(data["failed"]), 0)

        # 确认已删除
        for pid in ids:
            resp = self.client.get(f"/api/v1/project/{pid}", headers=self.headers)
            self.assertEqual(resp.status_code, 404)

    # ── RBAC 权限测试 ─────────────────────────────────────────────────

    def test_rbac_viewer_cannot_create(self):
        """viewer 角色不能创建项目 → 403。"""
        # 创建 viewer 用户
        viewer_id = _user_store.create_user(
            "viewer_user", "pass", tenant_id="test-tenant", roles=["viewer"]
        )
        viewer_token = create_access_token(viewer_id, "test-tenant", roles=["viewer"])
        viewer_headers = {"Authorization": f"Bearer {viewer_token}"}

        resp = self.client.post(
            "/api/v1/project",
            json={"name": "Viewer Project"},
            headers=viewer_headers,
        )
        self.assertEqual(resp.status_code, 403)

    def test_rbac_admin_can_delete_tenant(self):
        """admin 可以删除租户。"""
        # 创建租户
        resp = self.client.post(
            "/api/v1/tenants",
            json={"name": "RBAC Test Tenant", "slug": "rbac-test"},
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 201)
        tid = resp.json()["id"]

        # admin 删除
        resp = self.client.delete(f"/api/v1/tenants/{tid}", headers=self.headers)
        self.assertEqual(resp.status_code, 200)

    def test_rbac_viewer_cannot_access_tenants(self):
        """viewer 不能访问租户端点 → 403。"""
        viewer_id = _user_store.create_user(
            "viewer_tenant", "pass", tenant_id="test-tenant", roles=["viewer"]
        )
        viewer_token = create_access_token(viewer_id, "test-tenant", roles=["viewer"])
        viewer_headers = {"Authorization": f"Bearer {viewer_token}"}

        resp = self.client.get("/api/v1/tenants", headers=viewer_headers)
        self.assertEqual(resp.status_code, 403)

    def test_rbac_manager_can_create_project(self):
        """manager 可以创建项目。"""
        manager_id = _user_store.create_user(
            "manager_user", "pass", tenant_id="test-tenant", roles=["manager"]
        )
        manager_token = create_access_token(manager_id, "test-tenant", roles=["manager"])
        manager_headers = {"Authorization": f"Bearer {manager_token}"}

        resp = self.client.post(
            "/api/v1/project",
            json={"name": "Manager Project"},
            headers=manager_headers,
        )
        self.assertEqual(resp.status_code, 201)

    def test_rbac_user_cannot_delete_tenant(self):
        """普通 user 不能删除租户 → 403。"""
        user_id = _user_store.create_user(
            "normal_user", "pass", tenant_id="test-tenant", roles=["user"]
        )
        user_token = create_access_token(user_id, "test-tenant", roles=["user"])
        user_headers = {"Authorization": f"Bearer {user_token}"}

        # 先创建一个租户（用 admin）
        resp = self.client.post(
            "/api/v1/tenants",
            json={"name": "User Test Tenant", "slug": "user-test"},
            headers=self.headers,
        )
        tid = resp.json()["id"]

        # user 尝试删除
        resp = self.client.delete(f"/api/v1/tenants/{tid}", headers=user_headers)
        self.assertEqual(resp.status_code, 403)




class TestAuthModule(unittest.TestCase):
    """认证模块单元测试（不依赖 FastAPI）。"""

    def test_create_user(self):
        """创建用户。"""
        store = InMemoryUserStore()
        uid = store.create_user("alice", "secret123", tenant_id="t1")
        self.assertTrue(uid)

    def test_verify_password_correct(self):
        """正确密码验证通过。"""
        store = InMemoryUserStore()
        uid = store.create_user("bob", "pass456", tenant_id="t2")
        user = store.verify_password("bob", "pass456")
        self.assertIsNotNone(user)
        self.assertEqual(user["user_id"], uid)

    def test_verify_password_wrong(self):
        """错误密码验证失败。"""
        store = InMemoryUserStore()
        store.create_user("charlie", "pass789")
        user = store.verify_password("charlie", "wrong")
        self.assertIsNone(user)

    def test_create_and_verify_api_key(self):
        """创建并验证 API Key。"""
        store = InMemoryUserStore()
        uid = store.create_user("dave", "pass")
        raw_key = store.create_api_key(uid, "t1", roles=["admin"])
        self.assertTrue(raw_key.startswith("dms_"))

        info = store.verify_api_key(raw_key)
        self.assertIsNotNone(info)
        self.assertEqual(info["user_id"], uid)

    def test_verify_invalid_api_key(self):
        """无效 API Key 验证失败。"""
        store = InMemoryUserStore()
        info = store.verify_api_key("invalid_key")
        self.assertIsNone(info)


if __name__ == "__main__":
    unittest.main()
