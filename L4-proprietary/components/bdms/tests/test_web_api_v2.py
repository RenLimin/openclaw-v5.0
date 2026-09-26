"""Web API v2.1 路由测试。

对齐各模块 DESIGN-DETAIL 的 Web API 契约。
用 FastAPI TestClient 做 API 冒烟（安全/Cookie 类测试在 E2E 阶段用真实 HTTP）。
"""

import sys
import pytest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from fastapi.testclient import TestClient

from bdms.core import db as _db
from bdms.modules.project_management import ProjectManagementService


@pytest.fixture(scope="module")
def client():
    """模块级 TestClient（共享 DB 状态）。"""
    from bdms.web.main import app
    return TestClient(app)


@pytest.fixture(scope="module")
def seed_project():
    """造一个项目供 API 查询。"""
    from bdms.core.paths import DATA_DIR
    _db.init_db()
    svc = ProjectManagementService()
    pid = svc.create_project(
        project_name="API测试项目", pm="rex", budget=88888, dept="API部")
    return pid


# ─── 项目管理 API ───

class TestProjectAPI:

    def test_list_projects(self, client):
        r = client.get("/api/v2/projects")
        assert r.status_code == 200
        body = r.json()
        assert "items" in body and "total" in body

    def test_create_and_get(self, client):
        r = client.post("/api/v2/projects", json={
            "project_name": "API创建项目", "pm": "api_user", "budget": 10000})
        assert r.status_code == 200
        pid = r.json()["id"]

        r2 = client.get(f"/api/v2/projects/{pid}")
        assert r2.status_code == 200
        assert r2.json()["project"]["project_name"] == "API创建项目"

    def test_get_404(self, client):
        r = client.get("/api/v2/projects/999999")
        assert r.status_code == 404

    def test_create_invalid(self, client):
        r = client.post("/api/v2/projects", json={"project_name": ""})
        assert r.status_code == 400

    def test_project_dashboard(self, client, seed_project):
        r = client.get(f"/api/v2/projects/{seed_project}/dashboard")
        assert r.status_code == 200
        body = r.json()
        assert body["project_id"] == seed_project
        assert "budget_usage_pct" in body

    def test_transition(self, client, seed_project):
        # 需要团队成员才能启动
        svc = ProjectManagementService()
        svc.engine.add_team_member(seed_project, "API成员")
        r = client.post(f"/api/v2/projects/{seed_project}/transition",
                        json={"to_state": "planning", "operator": "api"})
        assert r.status_code == 200
        assert r.json()["status"] == "planning"

    def test_transition_invalid(self, client, seed_project):
        r = client.post(f"/api/v2/projects/{seed_project}/transition",
                        json={"to_state": "closed"})
        assert r.status_code == 400


# ─── 利润 API ───

class TestProfitAPI:

    def test_profit_report(self, client, seed_project):
        r = client.get(f"/api/v2/profit/report/{seed_project}",
                       params={"period": "2026-09"})
        assert r.status_code == 200
        body = r.json()
        assert "profit" in body and "profit_margin" in body

    def test_profit_projects(self, client):
        r = client.get("/api/v2/profit/projects", params={"period": "2026-09"})
        assert r.status_code == 200
        assert "items" in r.json()

    def test_profit_alerts(self, client, seed_project):
        r = client.get(f"/api/v2/profit/alerts/{seed_project}")
        assert r.status_code == 200
        assert "alerts" in r.json()


# ─── 集成 API ───

class TestIntegrationAPI:

    def test_connectors(self, client):
        r = client.get("/api/v2/integration/connectors")
        assert r.status_code == 200
        names = [c["name"] for c in r.json()["connectors"]]
        assert "ones" in names and "local_import" in names

    def test_connector_status(self, client):
        r = client.get("/api/v2/integration/connectors/ones/status")
        assert r.status_code == 200
        assert r.json()["name"] == "ones"

    def test_connector_404(self, client):
        r = client.get("/api/v2/integration/connectors/bogus/status")
        assert r.status_code == 404

    def test_sync_history(self, client):
        r = client.get("/api/v2/integration/history")
        assert r.status_code == 200


# ─── 驾驶舱视图 API ───

class TestDashboardViewAPI:

    def test_create_view(self, client):
        r = client.post("/api/v2/dashboard/views", json={
            "user_id": "api_user",
            "view_name": "API看板",
            "config": {"layout": ["kpi", "risk"]},
        })
        assert r.status_code == 200
        assert r.json()["view_id"]

    def test_list_views(self, client):
        r = client.get("/api/v2/dashboard/views", params={"user_id": "api_user"})
        assert r.status_code == 200
        assert len(r.json()["views"]) >= 1

    def test_default_view(self, client):
        r = client.get("/api/v2/dashboard/views/default",
                       params={"user_id": "nobody"})
        assert r.status_code == 200
        assert r.json()["view_name"] == "默认驾驶舱"

    def test_update_and_delete(self, client):
        r = client.post("/api/v2/dashboard/views", json={
            "user_id": "api_user", "view_name": "临时", "config": {}})
        vid = r.json()["view_id"]

        r2 = client.put(f"/api/v2/dashboard/views/{vid}",
                        json={"config": {"layout": ["x"]}})
        assert r2.status_code == 200

        r3 = client.delete(f"/api/v2/dashboard/views/{vid}")
        assert r3.status_code == 200

        r4 = client.get(f"/api/v2/dashboard/views/{vid}")
        # 软删除后查询返回 404
        assert r4.status_code == 404
