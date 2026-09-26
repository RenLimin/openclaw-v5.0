"""项目利润管理模块 v2.1 — 单元测试。

对齐 DESIGN-DETAIL-PROFIT-MANAGEMENT-v2.1.md：
  1. ProfitEngine 利润计算（revenue - cost）
  2. 成本汇总（工时×费率 + 设备 + 差旅）
  3. 预算告警（warning/critical）
  4. 部门/时间聚合
  5. ProfitService 工时提交/审批 + 差旅导入 + 利润报表
"""

import sys
import pytest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

import pandas as pd

from bdms.core import db as _db
from bdms.core.db import get_connection
from bdms.modules.project_management import ProjectEngine
from bdms.modules.profit_management import ProfitEngine, ProfitService
from bdms.modules.base import ValidationError, NotFoundError


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.db"
    _db.init_db(path)
    return path


@pytest.fixture
def project_id(db_path):
    """造一个项目 + 7 阶段（3 个 completed 推进度）。"""
    pe = ProjectEngine(db_path=db_path)
    pid = pe.create_project(project_name="利润测试项目", pm="rex",
                            budget=100000, dept="交付一部")
    pe.init_default_phases(pid)
    phases = pe.list_phases(pid)
    for ph in phases[:3]:
        pe.update_phase(ph["id"], status="completed")
    return pid


@pytest.fixture
def engine(db_path):
    return ProfitEngine(db_path=db_path)


@pytest.fixture
def svc(db_path):
    return ProfitService(db_path=db_path)


def _seed_cost(db_path, project_id):
    """造成本数据：8h×500 工时 + 3000 设备 + 3500 差旅。"""
    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT INTO pf_staff_rate (person_name, role, rate, effective_date) "
            "VALUES ('张三', '工程师', 500, '2026-01-01')")
        conn.execute(
            "INSERT INTO pf_timesheet (project_id, person_id, work_date, hours, "
            "work_type, status) VALUES (?, '张三', '2026-06-10', 8, '开发', 'approved')",
            (project_id,))
        conn.execute(
            "INSERT INTO pf_device_usage (project_id, device_name, start_date, "
            "end_date, cost_per_day, total_cost) "
            "VALUES (?, '设备A', '2026-06-10', '2026-06-12', 1000, 3000)",
            (project_id,))
        conn.execute(
            "INSERT INTO pf_travel_cost (project_id, employee_name, travel_date, "
            "cost_type, amount) VALUES (?, '张三', '2026-06-15', '交通', 3500)",
            (project_id,))
        conn.commit()
    finally:
        conn.close()


# ─── 1. 利润计算 ───

class TestComputeProfit:

    def test_basic_profit(self, db_path, engine, project_id):
        _seed_cost(db_path, project_id)
        # 7 阶段 3 completed → progress = 3/7 → revenue = 100000 × 3/7 ≈ 42857
        r = engine.compute_profit(project_id, "2026-06")
        assert r["cost"] == 10500.0  # 4000 + 3000 + 3500
        assert r["cost_breakdown"]["labor_cost"] == 4000.0
        assert r["cost_breakdown"]["device_cost"] == 3000.0
        assert r["cost_breakdown"]["travel_cost"] == 3500.0
        assert r["revenue"] == pytest.approx(100000 * 3 / 7, rel=0.01)
        assert r["profit"] == pytest.approx(r["revenue"] - 10500, rel=0.01)

    def test_revenue_override(self, engine, project_id):
        r = engine.compute_profit(project_id, "2026-06", revenue_override=50000)
        assert r["revenue"] == 50000
        assert r["profit"] == 50000 - r["cost"]

    def test_invalid_period(self, engine, project_id):
        with pytest.raises(ValidationError):
            engine.compute_profit(project_id, "202606")

    def test_project_not_found(self, engine):
        with pytest.raises(NotFoundError):
            engine.compute_profit(99999, "2026-06")


# ─── 2. 成本汇总 ───

class TestCostSummary:

    def test_summary(self, db_path, engine, project_id):
        _seed_cost(db_path, project_id)
        s = engine.get_cost_summary(project_id)
        assert s["total"] == 10500.0
        assert s["labor_cost"] == 4000.0
        assert s["total_hours"] == 8.0
        assert len(s["by_person"]) == 1
        assert s["by_person"][0]["cost"] == 4000.0

    def test_pending_timesheet_excluded(self, db_path, engine, project_id):
        _seed_cost(db_path, project_id)
        conn = get_connection(db_path)
        conn.execute(
            "INSERT INTO pf_timesheet (project_id, person_id, work_date, hours, "
            "work_type, status) VALUES (?, '张三', '2026-06-11', 4, '开发', 'pending')",
            (project_id,))
        conn.commit()
        conn.close()
        s = engine.get_cost_summary(project_id)
        assert s["total_hours"] == 8.0  # pending 不计


# ─── 3. 预算告警 ───

class TestBudgetAlert:

    def test_no_alert_under_budget(self, db_path, engine, project_id):
        _seed_cost(db_path, project_id)  # 10500 < 100000
        assert engine.check_budget_alert(project_id) == []

    def test_warning_over_budget(self, db_path, engine, project_id):
        _seed_cost(db_path, project_id)
        conn = get_connection(db_path)
        conn.execute(
            "INSERT INTO pf_travel_cost (project_id, employee_name, travel_date, "
            "cost_type, amount) VALUES (?, '张三', '2026-06-20', '超支', 90000)",
            (project_id,))
        conn.commit()
        conn.close()
        # 总成本 100500，超 0.5%，threshold 0.10 → warning
        alerts = engine.check_budget_alert(project_id, threshold=0.10)
        assert len(alerts) == 1
        assert alerts[0]["alert_level"] == "warning"

    def test_critical_over_budget(self, db_path, engine, project_id):
        conn = get_connection(db_path)
        conn.execute(
            "INSERT INTO pf_travel_cost (project_id, employee_name, travel_date, "
            "cost_type, amount) VALUES (?, '张三', '2026-06-20', '严重超支', 150000)",
            (project_id,))
        conn.commit()
        conn.close()
        alerts = engine.check_budget_alert(project_id, threshold=0.10)
        assert alerts[0]["alert_level"] == "critical"


# ─── 4. 聚合 ───

class TestAggregation:

    def test_aggregate_by_department(self, db_path, engine, project_id):
        _seed_cost(db_path, project_id)
        result = engine.aggregate_by_department("2026-06")
        assert len(result) >= 1
        d = result[0]
        assert d["dept"] == "交付一部"
        assert d["project_count"] == 1
        assert d["total_cost"] == 10500.0

    def test_aggregate_by_period(self, db_path, engine, project_id):
        _seed_cost(db_path, project_id)
        result = engine.aggregate_by_period(project_id, ["2026-05", "2026-06"])
        assert len(result) == 2
        june = [r for r in result if r["period"] == "2026-06"][0]
        assert june["cost"] == 10500.0


# ─── 5. 服务层 ───

class TestProfitService:

    def test_timesheet_flow(self, svc, project_id):
        r = svc.submit_timesheet(project_id, "李四", "2026-06-01", 6,
                                 submitter="李四")
        assert r["status"] == "pending"
        r2 = svc.approve_timesheet(r["timesheet_id"], approver="rex")
        assert r2["status"] == "approved"

    def test_future_date_rejected(self, svc, project_id):
        with pytest.raises(ValidationError):
            svc.submit_timesheet(project_id, "李四", "2099-01-01", 8)

    def test_timesheet_idempotent(self, svc, project_id):
        r1 = svc.submit_timesheet(project_id, "王五", "2026-06-01", 4)
        r2 = svc.submit_timesheet(project_id, "王五", "2026-06-01", 6)
        assert r1["timesheet_id"] == r2["timesheet_id"]

    def test_travel_import_csv(self, svc, project_id, tmp_path):
        csv_path = tmp_path / "travel.csv"
        csv_path.write_text(
            "员工姓名,金额,日期,费用类型\n"
            "张三,1000,2026-06-01,交通\n"
            "李四,2000,2026-06-02,住宿\n"
            ",500,2026-06-03,其他\n"  # 姓名空 → 失败
        )
        r = svc.import_travel_cost(project_id, str(csv_path))
        assert r["imported"] == 2
        assert r["failed"] == 1
        assert r["total_amount"] == 3000.0

    def test_travel_import_excel(self, svc, project_id, tmp_path):
        xlsx = tmp_path / "travel.xlsx"
        pd.DataFrame({
            "员工姓名": ["张三"], "金额": [800], "日期": ["2026-06-05"],
        }).to_excel(xlsx, index=False)
        r = svc.import_travel_cost(project_id, str(xlsx))
        assert r["imported"] == 1

    def test_travel_import_bad_format(self, svc, project_id, tmp_path):
        p = tmp_path / "travel.txt"
        p.write_text("x")
        with pytest.raises(ValidationError):
            svc.import_travel_cost(project_id, str(p))

    def test_profit_report(self, db_path, svc, project_id):
        _seed_cost(db_path, project_id)
        r = svc.get_profit_report(project_id, "2026-06")
        assert r["project"]["project_name"] == "利润测试项目"
        assert r["cost"] == 10500.0
        assert r["budget_status"] in ("normal", "warning", "over_budget")
        assert len(r["monthly_trend"]) == 6

    def test_list_projects_profit(self, db_path, svc, project_id):
        _seed_cost(db_path, project_id)
        r = svc.list_projects_profit("2026-06")
        assert r["total"] >= 1
        assert r["items"][0]["project_id"] == project_id

    def test_sync_revenue(self, svc, project_id):
        r = svc.sync_revenue(project_id, "2026-06", 60000)
        assert r["synced"]
        assert r["profit"]["revenue"] == 60000
