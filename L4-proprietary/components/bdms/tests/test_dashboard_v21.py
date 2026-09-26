"""驾驶舱模块 v2.1 — 单元测试。

对齐 DESIGN-DETAIL-DASHBOARD-v2.1.md：
  1. 视图管理（CRUD + 预置模板 + 默认视图）
  2. 明细编辑（权限 + 编辑 + 历史 + 撤销 + 批量）
  3. 数据源注册（SQL 校验 + 指标计算 + 试运行）
"""

import sys
import pytest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from bdms.core import db as _db
from bdms.modules.dashboard import (
    DashboardCustomizationService,
    DashboardEditService,
    DashboardDataSourceService,
    SqlValidationError,
)
from bdms.modules.project_management import ProjectEngine


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.db"
    _db.init_db(path)
    return path


@pytest.fixture
def project_id(db_path):
    pe = ProjectEngine(db_path=db_path)
    return pe.create_project(project_name="驾驶舱测试项目", pm="rex")


# ─── 1. 视图管理 ───

class TestCustomization:

    @pytest.fixture
    def svc(self, db_path):
        return DashboardCustomizationService(db_path=db_path)

    def test_create_and_get(self, svc):
        r = svc.create_view("user1", "我的看板",
                            {"layout": ["kpi", "risk"]})
        assert r["view_id"]  # TEXT 标识
        v = svc.get_view(r["view_id"])
        assert v["view_name"] == "我的看板"
        assert v["config"]["layout"] == ["kpi", "risk"]

    def test_list_views(self, svc):
        svc.create_view("user1", "A", {})
        svc.create_view("user1", "B", {}, set_default=True)
        views = svc.list_views("user1")
        assert len(views) == 2
        assert views[0]["view_name"] == "B"  # 默认在前

    def test_update_view(self, svc):
        r = svc.create_view("user1", "X", {"a": 1})
        svc.update_view(r["view_id"], {"layout": ["x"]})
        assert svc.get_view(r["view_id"])["config"]["layout"] == ["x"]

    def test_delete_view(self, svc):
        r = svc.create_view("user1", "X", {})
        svc.delete_view(r["view_id"])
        assert svc.get_view(r["view_id"]) is None
        with pytest.raises(ValueError):
            svc.delete_view(r["view_id"])

    def test_default_view_flow(self, svc):
        r1 = svc.create_view("u", "A", {}, set_default=True)
        r2 = svc.create_view("u", "B", {})
        assert svc.get_default_view("u")["view_name"] == "A"
        svc.set_default_view(r2["view_id"], "u")
        assert svc.get_default_view("u")["view_name"] == "B"

    def test_default_view_fallback(self, svc):
        """无自定义视图时返回内置默认。"""
        v = svc.get_default_view("newuser")
        assert v["view_name"] == "默认驾驶舱"

    def test_apply_preset(self, svc):
        r = svc.apply_preset("profit", "user1")
        assert r["view_id"]
        v = svc.get_view(r["view_id"])
        assert v["view_name"] == "利润视图"

    def test_apply_unknown_preset(self, svc):
        with pytest.raises(ValueError):
            svc.apply_preset("bogus", "u")


# ─── 2. 明细编辑 ───

class TestEditService:

    @pytest.fixture
    def svc(self, db_path):
        s = DashboardEditService(db_path=db_path)
        s.set_current_roles(["admin"])
        return s

    def test_edit_pm_field(self, svc, project_id):
        """admin 角色可编辑 pm_projects.pm。"""
        svc.set_current_roles(["admin"])
        r = svc.edit_field(project_id, "pm", "new_pm", "pm_projects", "admin")
        assert r["changed"]
        assert r["new_value"] == "new_pm"

    def test_permission_denied(self, svc, project_id):
        """tech 角色不可编辑 pm_projects.pm。"""
        svc.set_current_roles(["tech"])
        with pytest.raises(PermissionError):
            svc.edit_field(project_id, "pm", "x", "pm_projects", "tech_user")

    def test_edit_history(self, svc, project_id):
        svc.edit_field(project_id, "pm", "pm1", "pm_projects", "admin")
        svc.edit_field(project_id, "pm", "pm2", "pm_projects", "admin")
        history = svc.get_edit_history(project_id, "pm_projects")
        assert len(history) == 2
        # 最新在前
        assert history[0]["new_value"] == "pm2"

    def test_undo_edit(self, svc, project_id):
        svc.edit_field(project_id, "pm", "v1", "pm_projects", "admin")
        r = svc.edit_field(project_id, "pm", "v2", "pm_projects", "admin")
        undo = svc.undo_edit(r["edit_id"], "admin")
        assert undo["undone"]
        # 值已恢复
        from bdms.core.db import get_connection
        conn = get_connection(svc.db_path)
        v = conn.execute(
            "SELECT pm FROM pm_projects WHERE id = ?", (project_id,)
        ).fetchone()[0]
        conn.close()
        assert v == "v1"

    def test_undo_other_user_denied(self, svc, project_id):
        r = svc.edit_field(project_id, "pm", "v", "pm_projects", "admin")
        with pytest.raises(PermissionError):
            svc.undo_edit(r["edit_id"], "other_user")

    def test_batch_edit(self, svc, db_path, project_id):
        pe = ProjectEngine(db_path=db_path)
        pid2 = pe.create_project(project_name="批量2")
        r = svc.batch_edit([project_id, pid2], "pm", "batch_pm",
                           "pm_projects", "admin")
        assert r["succeeded"] == 2

    def test_no_change_no_history(self, svc, project_id):
        r = svc.edit_field(project_id, "pm", "rex", "pm_projects", "admin")
        assert not r["changed"]


# ─── 3. 数据源注册 ───

class TestDataSource:

    @pytest.fixture
    def svc(self, db_path):
        return DashboardDataSourceService(db_path=db_path)

    def test_register_and_compute(self, svc, project_id):
        r = svc.register_source(
            "project_count", "project_management", "项目总数",
            "project", "SELECT COUNT(*) FROM pm_projects WHERE deleted_at IS NULL")
        assert r["source_key"] == "project_count"
        assert "COUNT" in r["description_auto"]

        m = svc.compute_metric("project_count")
        assert m["value"] >= 1

    def test_list_sources(self, svc):
        svc.register_source("s1", "m1", "T1", "c1", "SELECT COUNT(*) FROM sys_settings")
        svc.register_source("s2", "m2", "T2", "c2", "SELECT COUNT(*) FROM md_reference")
        sources = svc.list_sources()
        assert len(sources) >= 2

    def test_sql_validation_rejects_write(self, svc):
        with pytest.raises(SqlValidationError):
            svc.validate_sql("DELETE FROM pm_projects")

    def test_sql_validation_rejects_drop(self, svc):
        with pytest.raises(SqlValidationError):
            svc.validate_sql("DROP TABLE pm_projects")

    def test_sql_validation_rejects_non_select(self, svc):
        with pytest.raises(SqlValidationError):
            svc.validate_sql("PRAGMA table_info(x)")

    def test_dry_run(self, svc):
        r = svc.dry_run_sql("SELECT COUNT(*) AS n FROM pm_projects")
        assert r["row_count"] >= 1

    def test_describe_sql(self, svc):
        d = svc.describe_sql(
            "SELECT dept, COUNT(*) FROM pm_projects GROUP BY dept")
        assert "pm_projects" in d["tables"]
        assert "COUNT" in d["aggregations"]
        assert d["has_group_by"]

    def test_compute_unknown_source(self, svc):
        with pytest.raises(ValueError):
            svc.compute_metric("bogus_key")
