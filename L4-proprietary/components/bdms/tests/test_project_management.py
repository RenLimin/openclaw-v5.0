"""项目管理模块 v2.1 — 单元测试。

对齐 DESIGN-DETAIL-PROJECT-MANAGEMENT-v2.1.md 验收标准：
  1. 项目 CRUD + 软删除 + 实施字段
  2. 状态机 9 状态全流转（含 after_sales）
  3. 7 阶段默认模板
  4. 团队/里程碑/交付报告
  5. 成本引擎（工时×费率 + 设备 + 差旅 + 汇总）
  6. 风险引擎（报备→评审→关闭 + 等级矩阵 + 验收/结项拦截）
  7. 售后引擎（工单 5 状态 + SLA + 维保合同 + 结项拦截）
  8. 变更引擎（4 状态流转）
  9. 财务服务（利润汇总 + 健康度评分）
  10. 编排服务（全生命周期 + 前置校验 + 聚合视图）
"""

import sys
import pytest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from bdms.core import db as _db
from bdms.modules.project_management import (
    ProjectEngine,
    CostEngine,
    RiskEngine,
    ChangeManagementEngine,
    AfterSalesEngine,
    ProjectManagementService,
    ProjectFinancialService,
    ProjectStatus,
    TicketState,
    DEFAULT_PHASES_V21,
    SLA_HOURS,
    is_valid_transition,
    is_valid_ticket_transition,
    calculate_risk_level,
)
from bdms.modules.base import ValidationError, NotFoundError, StateTransitionError


# ─── Fixtures ───

@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.db"
    _db.init_db(path)
    return path


@pytest.fixture
def engine(db_path):
    return ProjectEngine(db_path=db_path)


@pytest.fixture
def cost_engine(db_path):
    return CostEngine(db_path=db_path)


@pytest.fixture
def risk_engine(db_path):
    return RiskEngine(db_path=db_path)


@pytest.fixture
def svc(db_path):
    return ProjectManagementService(db_path=db_path)


@pytest.fixture
def project_id(engine):
    return engine.create_project(project_name="测试项目", pm="rex", budget=100000)


# ─── 1. 项目 CRUD + 实施字段 ───

class TestProjectCRUD:

    def test_create_generates_project_no(self, engine, project_id):
        p = engine.get_project(project_id)
        assert p["project_no"].startswith("PROJ-")
        assert p["status"] == "initiating"

    def test_create_requires_name(self, engine):
        with pytest.raises(ValidationError):
            engine.create_project(project_name="")

    def test_impl_fields(self, engine):
        pid = engine.create_project(
            project_name="实施项目", impl_owner="eng1",
            impl_status="in_progress", impl_start_date="2026-09-01",
        )
        p = engine.get_project(pid)
        assert p["impl_owner"] == "eng1"
        assert p["impl_status"] == "in_progress"
        assert p["impl_start_date"] == "2026-09-01"

    def test_invalid_impl_status_rejected(self, engine):
        with pytest.raises(ValidationError):
            engine.create_project(project_name="x", impl_status="bogus")

    def test_filter_by_impl(self, engine):
        engine.create_project(project_name="A", impl_owner="eng1", impl_status="in_progress")
        engine.create_project(project_name="B", impl_owner="eng2")
        rows, n = engine.list_projects(impl_owner="eng1")
        assert n == 1 and rows[0]["project_name"] == "A"
        rows, n = engine.list_projects(impl_status="in_progress")
        assert n == 1

    def test_update_project(self, engine, project_id):
        engine.update_project(project_id, budget=200000, pm="new_pm")
        p = engine.get_project(project_id)
        assert p["budget"] == 200000 and p["pm"] == "new_pm"

    def test_update_cannot_touch_status(self, engine, project_id):
        engine.update_project(project_id, status="closed")  # status 不在白名单
        assert engine.get_project(project_id)["status"] == "initiating"

    def test_soft_delete(self, engine, project_id):
        engine.delete_project(project_id)
        assert engine.get_project(project_id) is None
        with pytest.raises(NotFoundError):
            engine.get_status(project_id)

    def test_keyword_search(self, engine):
        engine.create_project(project_name="等保测评项目A")
        rows, n = engine.list_projects(keyword="等保")
        assert n == 1


# ─── 2. 状态机 ───

class TestStateMachine:

    def test_all_valid_transitions(self):
        assert is_valid_transition("initiating", "planning")
        assert is_valid_transition("planning", "executing")
        assert is_valid_transition("executing", "delivering")
        assert is_valid_transition("delivering", "accepting")
        assert is_valid_transition("accepting", "after_sales")
        assert is_valid_transition("accepting", "closing")
        assert is_valid_transition("after_sales", "closing")
        assert is_valid_transition("closing", "closed")
        assert is_valid_transition("cancelled", "initiating")

    def test_after_sales_in_enum(self):
        assert ProjectStatus.AFTER_SALES.value == "after_sales"

    def test_invalid_transitions(self):
        assert not is_valid_transition("initiating", "executing")
        assert not is_valid_transition("closed", "initiating")
        assert not is_valid_transition("after_sales", "executing")

    def test_any_state_can_cancel(self):
        for s in ["initiating", "planning", "executing", "delivering",
                  "accepting", "after_sales", "closing"]:
            assert is_valid_transition(s, "cancelled"), s

    def test_engine_transition(self, engine, project_id):
        engine.transition_state(project_id, "planning")
        assert engine.get_status(project_id) == "planning"

    def test_engine_invalid_transition_raises(self, engine, project_id):
        with pytest.raises(StateTransitionError):
            engine.transition_state(project_id, "closed")

    def test_same_state_idempotent(self, engine, project_id):
        assert engine.transition_state(project_id, "initiating") == "initiating"


# ─── 3. 7 阶段模板 ───

class TestPhaseTemplate:

    def test_default_phases(self, engine, project_id):
        engine.init_default_phases(project_id)
        phases = engine.list_phases(project_id)
        assert len(phases) == 7
        names = [p["phase_name"] for p in phases]
        assert names == [p["phase_name"] for p in DEFAULT_PHASES_V21]
        # 售后阶段在验收与结项之间
        assert names.index("售后阶段") == 5

    def test_service_create_initializes_phases(self, svc):
        pid = svc.create_project(project_name="svc项目")
        assert len(svc.engine.list_phases(pid)) == 7


# ─── 4. 团队/里程碑/交付报告 ───

class TestProjectComponents:

    def test_team_member_unique(self, engine, project_id):
        engine.add_team_member(project_id, "张三", "工程师")
        with pytest.raises(ValidationError):
            engine.add_team_member(project_id, "张三", "工程师")

    def test_allocation_validation(self, engine, project_id):
        with pytest.raises(ValidationError):
            engine.add_team_member(project_id, "李四", allocation=1.5)

    def test_milestone_achieve(self, engine, project_id):
        mid = engine.add_milestone(project_id, "需求确认", planned_date="2026-10-01")
        engine.achieve_milestone(mid, actual_date="2026-09-28")
        m = engine.list_milestones(project_id)[0]
        assert m["status"] == "achieved" and m["actual_date"] == "2026-09-28"

    def test_delivery_report_flow(self, engine, project_id):
        rid = engine.submit_delivery_report(project_id, "delivery", "报告v1")
        assert engine.list_delivery_reports(project_id)[0]["status"] == "submitted"
        engine.review_delivery_report(rid, approved=True, reviewer="rex")
        assert engine.list_delivery_reports(project_id)[0]["status"] == "approved"
        # 已审核的不能再审
        with pytest.raises(ValidationError):
            engine.review_delivery_report(rid, approved=False)


# ─── 5. 成本引擎 ───

class TestCostEngine:

    def test_timesheet_validation(self, cost_engine, project_id):
        with pytest.raises(ValidationError):
            cost_engine.submit_timesheet(project_id, "张三", "2026-09-01", 0)
        with pytest.raises(ValidationError):
            cost_engine.submit_timesheet(project_id, "张三", "2026-09-01", 25)
        with pytest.raises(ValidationError):
            cost_engine.submit_timesheet(project_id, "", "2026-09-01", 8)

    def test_timesheet_idempotent_pending(self, cost_engine, project_id):
        t1 = cost_engine.submit_timesheet(project_id, "张三", "2026-09-01", 4, work_type="开发")
        t2 = cost_engine.submit_timesheet(project_id, "张三", "2026-09-01", 6, work_type="开发")
        assert t1 == t2  # 同 pending 记录更新
        rows = cost_engine.list_timesheets(project_id=project_id)
        assert len(rows) == 1 and rows[0]["hours"] == 6

    def test_approve_flow(self, cost_engine, project_id):
        t = cost_engine.submit_timesheet(project_id, "张三", "2026-09-01", 8)
        cost_engine.approve_timesheet(t, approver="rex", approved=True)
        rows = cost_engine.list_timesheets(project_id=project_id)
        assert rows[0]["status"] == "approved"
        # 不能重复审批
        with pytest.raises(ValidationError):
            cost_engine.approve_timesheet(t, approver="rex", approved=True)

    def test_cost_summary_only_counts_approved(self, cost_engine, project_id):
        cost_engine.set_staff_rate("张三", 500)
        t1 = cost_engine.submit_timesheet(project_id, "张三", "2026-09-01", 8)
        cost_engine.submit_timesheet(project_id, "张三", "2026-09-02", 4)  # pending
        cost_engine.approve_timesheet(t1, approver="rex", approved=True)
        summary = cost_engine.get_cost_summary(project_id)
        assert summary["labor_cost"] == 4000.0  # 只算 approved
        assert summary["total_hours"] == 8.0

    def test_device_cost(self, cost_engine, project_id):
        cost_engine.record_device_usage(project_id, "设备A", "2026-09-01", "2026-09-03",
                                        cost_per_day=1000)
        summary = cost_engine.get_cost_summary(project_id)
        assert summary["device_cost"] == 3000.0

    def test_travel_cost(self, cost_engine, project_id):
        cost_engine.add_travel_cost(project_id, "张三", 3500, travel_date="2026-09-02")
        summary = cost_engine.get_cost_summary(project_id)
        assert summary["travel_cost"] == 3500.0

    def test_by_month_breakdown(self, cost_engine, project_id):
        cost_engine.set_staff_rate("张三", 100)
        t = cost_engine.submit_timesheet(project_id, "张三", "2026-09-01", 10)
        cost_engine.approve_timesheet(t, approver="r", approved=True)
        cost_engine.add_travel_cost(project_id, "张三", 500, travel_date="2026-10-01")
        summary = cost_engine.get_cost_summary(project_id)
        months = {m["month"]: m["total"] for m in summary["by_month"]}
        assert months["202609"] == 1000.0
        assert months["202610"] == 500.0


# ─── 6. 风险引擎 ───

class TestRiskEngine:

    def test_risk_level_matrix(self):
        assert calculate_risk_level("high", "high") == "critical"
        assert calculate_risk_level("high", "medium") == "high"
        assert calculate_risk_level("medium", "medium") == "medium"
        assert calculate_risk_level("low", "low") == "low"
        with pytest.raises(ValueError):
            calculate_risk_level("bogus", "high")

    def test_report_auto_level(self, risk_engine, project_id):
        rid = risk_engine.report_risk(project_id=project_id, title="风险",
                                      probability="high", impact="high")
        r = risk_engine.get_risk(rid)
        assert r["risk_level"] == "critical"
        assert r["status"] == "open"
        assert r["risk_no"].startswith("RISK-")

    def test_review_flow(self, risk_engine, project_id):
        rid = risk_engine.report_risk(project_id=project_id, title="风险")
        risk_engine.review_risk(rid, reviewer="rex", action="mitigate", action_plan="计划")
        r = risk_engine.get_risk(rid)
        assert r["status"] == "mitigating"
        assert len(r["history"]) == 3  # report + assessing + mitigate

    def test_close_idempotent(self, risk_engine, project_id):
        rid = risk_engine.report_risk(project_id=project_id, title="风险")
        risk_engine.review_risk(rid, reviewer="r", action="accept")
        risk_engine.close_risk(rid, closer="rex")
        risk_engine.close_risk(rid, closer="rex")  # 幂等不报错
        assert risk_engine.get_risk(rid)["status"] == "closed"

    def test_escalate_upgrades_level(self, risk_engine, project_id):
        rid = risk_engine.report_risk(project_id=project_id, title="风险",
                                      probability="low", impact="low")
        risk_engine.escalate(rid, escalate_to="PMO", reason="升级测试")
        assert risk_engine.get_risk(rid)["risk_level"] == "medium"

    def test_high_risk_blocks_acceptance(self, risk_engine, project_id, engine):
        risk_engine.report_risk(project_id=project_id, title="高危",
                                probability="high", impact="high")
        assert risk_engine.has_open_high_risks(project_id)


# ─── 7. 售后引擎 ───

class TestAfterSales:

    def test_ticket_lifecycle(self, db_path, project_id):
        ase = AfterSalesEngine(db_path=db_path)
        tid = ase.create_ticket(title="工单", priority="high", service_level="silver",
                                project_id=project_id)
        t = ase.get_ticket(tid)
        assert t["ticket"]["state"] == "open"
        assert t["ticket"]["ticket_no"].startswith("TK-")

        ase.assign_ticket(tid, assignee="eng1", assigner="pmo")
        ase.start_ticket(tid, operator="eng1")
        ase.resolve_ticket(tid, resolver="eng1", resolution="修复完成")
        ase.close_ticket(tid, closer="customer", close_note="确认")

        t = ase.get_ticket(tid)
        assert t["ticket"]["state"] == "closed"
        assert len(t["history"]) >= 5

    def test_assigned_can_resolve_directly(self, db_path, project_id):
        """§3.2.8.4: assigned 或 in_progress 均可 resolve。"""
        ase = AfterSalesEngine(db_path=db_path)
        tid = ase.create_ticket(title="工单", project_id=project_id)
        ase.assign_ticket(tid, assignee="eng1", assigner="pmo")
        ase.resolve_ticket(tid, resolver="eng1", resolution="直接解决")
        assert ase.get_ticket(tid)["ticket"]["state"] == "resolved"

    def test_sla_deadlines_set(self, db_path, project_id):
        ase = AfterSalesEngine(db_path=db_path)
        tid = ase.create_ticket(title="SLA工单", priority="critical",
                                service_level="silver", project_id=project_id)
        t = ase.get_ticket(tid)
        # critical 提升 silver → gold: 响应 2h 解决 24h
        assert t["ticket"]["response_deadline"] is not None
        assert t["ticket"]["resolution_deadline"] is not None

    def test_ticket_summary(self, db_path, project_id):
        ase = AfterSalesEngine(db_path=db_path)
        t1 = ase.create_ticket(title="A", project_id=project_id)
        t2 = ase.create_ticket(title="B", project_id=project_id)
        ase.assign_ticket(t2, assignee="e", assigner="p")
        s = ase.get_ticket_summary(project_id=project_id)
        assert s["total"] == 2
        assert s["open"] == 1
        assert s["assigned"] == 1

    def test_warranty_contract(self, db_path, project_id):
        ase = AfterSalesEngine(db_path=db_path)
        wid = ase.create_warranty_contract(project_id=project_id, service_level="gold")
        w = ase.get_warranty_by_project(project_id)
        assert w["id"] == wid
        assert w["contract_no"].startswith("WC-")
        assert w["service_level"] == "gold"


# ─── 8. 变更引擎 ───

class TestChangeEngine:

    def test_full_flow(self, db_path, project_id):
        chg = ChangeManagementEngine(db_path=db_path)
        cid = chg.create_change_request(project_id, "scope", "标题",
                                        submitted_by="rex")
        assert chg.get_change_request(cid)["status"] == "submitted"
        chg.assess_change(cid, assessor="pmo")
        chg.approve_change(cid, approver="pmo")
        chg.execute_change(cid, operator="rex")
        assert chg.get_change_request(cid)["status"] == "completed"

    def test_invalid_type_rejected(self, db_path, project_id):
        chg = ChangeManagementEngine(db_path=db_path)
        with pytest.raises(ValidationError):
            chg.create_change_request(project_id, "bogus", "标题")

    def test_reject_flow(self, db_path, project_id):
        chg = ChangeManagementEngine(db_path=db_path)
        cid = chg.create_change_request(project_id, "cost", "标题")
        chg.assess_change(cid, assessor="pmo")
        chg.reject_change(cid, approver="pmo")
        assert chg.get_change_request(cid)["status"] == "rejected"


# ─── 9. 财务服务 ───

class TestFinancialService:

    def test_profit_summary(self, db_path, project_id):
        ce = CostEngine(db_path=db_path)
        ce.set_staff_rate("张三", 500)
        t = ce.submit_timesheet(project_id, "张三", "2026-09-01", 10)
        ce.approve_timesheet(t, approver="r", approved=True)

        fs = ProjectFinancialService(db_path=db_path)
        s = fs.get_profit_summary(project_id)
        assert s["total_cost"] == 5000.0
        assert s["gross_profit"] == s["total_revenue"] - 5000.0

    def test_health_score_range(self, db_path, project_id):
        fs = ProjectFinancialService(db_path=db_path)
        h = fs.get_financial_health_score(project_id)
        assert 0 <= h["score"] <= 100
        assert h["level"] in ("excellent", "good", "fair", "poor", "critical")
        assert set(h["breakdown"].keys()) == {"预算执行率", "毛利率", "成本增长率", "现金流匹配度"}

    def test_profit_alert(self, db_path, project_id):
        fs = ProjectFinancialService(db_path=db_path)
        a = fs.check_profit_alert(project_id, threshold_pct=20.0)
        assert a["level"] in ("info", "warning", "critical")


# ─── 10. 编排服务（全生命周期）───

class TestServiceOrchestration:

    def _full_setup(self, svc):
        pid = svc.create_project(project_name="生命周期", pm="rex", budget=100000)
        svc.engine.add_team_member(pid, "张三")
        return pid

    def test_start_requires_pm(self, svc, engine):
        pid = engine.create_project(project_name="无PM项目")  # 无 pm
        with pytest.raises(ValidationError):
            svc.start_project(pid)

    def test_start_requires_team(self, svc, project_id):
        with pytest.raises(ValidationError):
            svc.start_project(project_id)

    def test_full_lifecycle_with_after_sales(self, svc, db_path):
        pid = self._full_setup(svc)
        svc.start_project(pid, operator="rex")
        assert svc.engine.get_status(pid) == "executing"

        # 风险关闭 + 交付审核
        rid = svc.report_risk(project_id=pid, title="风险")
        svc.submit_delivery(pid, "delivery", "交付报告", created_by="rex")
        svc.resolve_risk(rid, action="accept", reviewer="rex")
        RiskEngine(db_path).close_risk(rid, closer="rex")
        reports = svc.engine.list_delivery_reports(pid)
        svc.engine.review_delivery_report(reports[0]["id"], approved=True)

        svc.accept_project(pid, operator="rex")
        assert svc.engine.get_status(pid) == "accepting"

        result = svc.transfer_to_after_sales(pid, operator="rex")
        assert result["status"] == "after_sales"

        tid = svc.create_ticket(pid, title="问题")
        svc.assign_ticket(tid, assignee="e", operator="p")
        svc.resolve_ticket(tid, resolution="解决", operator="e")
        svc.close_ticket(tid, operator="c")

        svc.close_project(pid, operator="rex")
        assert svc.engine.get_status(pid) == "closed"

    def test_acceptance_blocked_by_high_risk(self, svc, db_path):
        pid = self._full_setup(svc)
        svc.start_project(pid)
        svc.report_risk(project_id=pid, title="高危", probability="high", impact="high")
        svc.submit_delivery(pid, "delivery", "报告")
        with pytest.raises(ValidationError, match="风险"):
            svc.accept_project(pid)

    def test_close_blocked_by_open_ticket(self, svc, db_path):
        pid = self._full_setup(svc)
        svc.start_project(pid)
        svc.submit_delivery(pid, "delivery", "报告")
        reports = svc.engine.list_delivery_reports(pid)
        svc.engine.review_delivery_report(reports[0]["id"], approved=True)
        svc.accept_project(pid, operator="rex")
        result = svc.transfer_to_after_sales(pid, operator="rex")
        tid = svc.create_ticket(pid, title="未处理问题")
        with pytest.raises(ValidationError, match="工单"):
            svc.close_project(pid, operator="rex")

    def test_close_blocked_by_pending_report(self, svc, db_path):
        pid = self._full_setup(svc)
        svc.start_project(pid)
        svc.submit_delivery(pid, "delivery", "报告")  # submitted 未审核
        svc.accept_project(pid, operator="rex")
        with pytest.raises(ValidationError, match="报告"):
            svc.close_project(pid, operator="rex", confirm_no_after_sales=True)

    def test_cancel_transfers_open_risks(self, svc, db_path):
        pid = self._full_setup(svc)
        svc.report_risk(project_id=pid, title="风险")
        svc.cancel_project(pid, reason="取消", operator="rex")
        assert svc.engine.get_status(pid) == "cancelled"
        risks, _ = RiskEngine(db_path).list_risks(project_id=pid)
        assert risks[0]["status"] == "transferred"  # open 自动转 transferred

    def test_reactivate(self, svc):
        pid = self._full_setup(svc)
        svc.cancel_project(pid, reason="r", operator="rex")
        svc.reactivate_project(pid)
        assert svc.engine.get_status(pid) == "initiating"

    def test_project_dashboard(self, svc):
        pid = self._full_setup(svc)
        svc.start_project(pid)
        d = svc.get_project_dashboard(pid)
        assert d["project_id"] == pid
        assert d["status"] == "executing"
        assert d["team_size"] == 1
        assert "budget_usage_pct" in d

    def test_project_detail(self, svc):
        pid = self._full_setup(svc)
        d = svc.get_project_detail(pid)
        assert len(d["phases"]) == 7
        assert "cost_summary" in d and "risk_summary" in d
