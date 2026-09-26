# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""ProjectManagementService — 项目管理编排服务。

对齐 DESIGN-DETAIL-PROJECT-MANAGEMENT-v2.1.md §3.2：
- 生命周期编排（创建/启动/交付/验收/转售后/结项/取消/重新激活）
- 售后管理编排（§3.2.8）
- 风险/变更委托
- 项目详情聚合（§3.2.12）/ 项目仪表盘（§3.2.13）
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from bdms.core.db import get_connection
from bdms.modules.base import NotFoundError, ValidationError

from .engine import ProjectEngine
from .models import is_valid_transition


class ProjectManagementService:
    """项目管理编排服务：跨子引擎事务编排 + 生命周期推进。"""

    def __init__(self, db_path=None):
        self.engine = ProjectEngine(db_path)
        self.db_path = self.engine.db_path

    # ─── 子引擎懒加载（避免循环导入）───

    def _cost_engine(self):
        from .cost.engine import CostEngine
        return CostEngine(self.db_path)

    def _risk_engine(self):
        from .risk.engine import RiskEngine
        return RiskEngine(self.db_path)

    def _change_engine(self):
        from .change.engine import ChangeManagementEngine
        return ChangeManagementEngine(self.db_path)

    def _after_sales_engine(self):
        from .after_sales.engine import AfterSalesEngine
        return AfterSalesEngine(self.db_path)

    # ========================================================
    # 生命周期编排（§3.2.1 ~ 3.2.7）
    # ========================================================

    def create_project(self, **data) -> int:
        """创建项目 + 初始化 7 阶段默认模板（§3.2.1）。"""
        project_id = self.engine.create_project(**data)
        self.engine.init_default_phases(project_id)
        return project_id

    def start_project(self, project_id: int, operator: str = "system") -> None:
        """启动项目：initiating → planning → executing（§3.2.2）。

        前置：有 PM + 至少一个团队成员。
        """
        project = self.engine.get_project(project_id)
        if not project:
            raise NotFoundError(f"项目 {project_id} 不存在")
        if not project["pm"]:
            raise ValidationError("启动失败：项目缺少项目经理（pm）")
        members = self.engine.list_team_members(project_id)
        if not members:
            raise ValidationError("启动失败：项目至少需要一名团队成员")

        self.engine.transition_state(project_id, "planning", operator, "启动项目")
        self.engine.transition_state(project_id, "executing", operator, "进入执行")

    def submit_delivery(
        self, project_id: int, report_type: str, title: str, **data
    ) -> int:
        """提交交付报告并推进到 delivering（§3.2.3）。"""
        status = self.engine.get_status(project_id)
        if status not in ("executing", "delivering"):
            raise ValidationError(
                f"当前状态 {status} 不可提交交付（需 executing/delivering）"
            )
        report_id = self.engine.submit_delivery_report(
            project_id, report_type, title, **data
        )
        if status == "executing":
            self.engine.transition_state(
                project_id, "delivering",
                data.get("created_by", "system"), "提交交付"
            )
        return report_id

    def accept_project(self, project_id: int, operator: str = "system") -> None:
        """项目验收：delivering → accepting（§3.2.4）。

        前置：无未关闭的 critical/high 风险。
        """
        status = self.engine.get_status(project_id)
        if status != "delivering":
            raise ValidationError(f"当前状态 {status} 不可验收（需 delivering）")

        if self._risk_engine().has_open_high_risks(project_id):
            raise ValidationError("验收失败：存在未关闭的 critical/high 风险")

        self.engine.transition_state(project_id, "accepting", operator, "验收")

    def close_project(self, project_id: int, operator: str = "system",
                      confirm_no_after_sales: bool = False) -> None:
        """结项：accepting/after_sales → closing → closed（§3.2.5 + §3.2.8.8）。

        前置三重检查：
        1. 所有风险已关闭
        2. 所有交付报告已审核（无 draft/submitted）
        3. 无未关闭工单（或确认无需售后）
        """
        status = self.engine.get_status(project_id)
        if status not in ("accepting", "after_sales", "closing"):
            raise ValidationError(
                f"当前状态 {status} 不可结项（需 accepting/after_sales/closing）"
            )

        # 检查 1：风险全关闭
        if self._risk_engine().has_unclosed_risks(project_id):
            raise ValidationError("结项失败：存在未关闭风险")

        # 检查 2：交付报告全审核
        reports = self.engine.list_delivery_reports(project_id)
        pending = [r for r in reports if r["status"] in ("draft", "submitted")]
        if pending:
            raise ValidationError(
                f"结项失败：{len(pending)} 份交付报告待审核"
            )

        # 检查 3：无未关闭工单（§3.2.8.8）
        if status == "after_sales" or not confirm_no_after_sales:
            summary = self._after_sales_engine().get_ticket_summary(project_id=project_id)
            unclosed = summary["total"] - summary["closed"]
            if unclosed > 0:
                raise ValidationError(
                    f"结项失败：{unclosed} 个未关闭售后工单"
                )

        if status != "closing":
            self.engine.transition_state(project_id, "closing", operator, "结项")
        self.engine.transition_state(project_id, "closed", operator, "结项完成")

    def cancel_project(self, project_id: int, reason: str,
                       operator: str = "system") -> None:
        """取消项目（任意非 closed → cancelled）（§3.2.6）。"""
        status = self.engine.get_status(project_id)
        if status == "closed":
            raise ValidationError("已结项项目不可取消")

        self.engine.transition_state(project_id, "cancelled", operator, reason)

        # 取消时 open 风险自动标记 transferred（§6.6）
        risks, _ = self._risk_engine().list_risks(project_id=project_id, status="open")
        for r in risks:
            self._risk_engine().review_risk(
                r["id"], operator, "transfer",
                action_plan=f"项目取消，风险自动转移。原因: {reason}"
            )

    def reactivate_project(self, project_id: int, operator: str = "system") -> None:
        """重新激活：cancelled → initiating（§3.2.7）。"""
        self.engine.transition_state(project_id, "initiating", operator, "重新激活")

    # ========================================================
    # 售后管理编排（§3.2.8）
    # ========================================================

    def transfer_to_after_sales(
        self,
        project_id: int,
        operator: str = "system",
        service_level: str = "silver",
        warranty_start: Optional[str] = None,
        warranty_end: Optional[str] = None,
    ) -> Dict[str, Any]:
        """转售后：验收通过后创建维保合同，进入售后服务期（§3.2.8.1）。"""
        status = self.engine.get_status(project_id)
        if status != "accepting":
            raise ValidationError(
                f"当前状态 {status} 不可转售后（需 accepting）"
            )

        engine_as = self._after_sales_engine()
        warranty_id = engine_as.create_warranty_contract(
            project_id=project_id,
            service_level=service_level,
            warranty_start=warranty_start,
            warranty_end=warranty_end,
        )
        self.engine.transition_state(
            project_id, "after_sales", operator, "转售后服务期"
        )

        warranty = engine_as.get_warranty_by_project(project_id)
        return {
            "project_id": project_id,
            "warranty_id": warranty_id,
            "status": "after_sales",
            "service_start": warranty.get("warranty_start") if warranty else None,
            "service_end": warranty.get("warranty_end") if warranty else None,
        }

    def create_ticket(self, project_id: int, **data) -> int:
        """创建售后工单（§3.2.8.2）。"""
        return self._after_sales_engine().create_ticket(project_id=project_id, **data)

    def assign_ticket(self, ticket_id: int, assignee: str, operator: str = "system") -> None:
        """分派工单（§3.2.8.3）。"""
        self._after_sales_engine().assign_ticket(ticket_id, assignee, assigner=operator)

    def resolve_ticket(self, ticket_id: int, resolution: str,
                       operator: str = "system") -> None:
        """解决工单（§3.2.8.4）。"""
        self._after_sales_engine().resolve_ticket(
            ticket_id, resolver=operator, resolution=resolution
        )

    def close_ticket(self, ticket_id: int, operator: str = "system",
                     close_note: str = "") -> None:
        """关闭工单（§3.2.8.5）。"""
        self._after_sales_engine().close_ticket(
            ticket_id, closer=operator, close_note=close_note
        )

    def get_after_sales_summary(self, project_id: int) -> Dict[str, Any]:
        """售后概览（§3.2.8.7，结项前检查依据）。"""
        engine_as = self._after_sales_engine()
        warranty = engine_as.get_warranty_by_project(project_id)
        summary = engine_as.get_ticket_summary(project_id=project_id)

        unclosed = summary["total"] - summary["closed"]
        return {
            "warranty": (
                {
                    "id": warranty["id"],
                    "service_start": warranty.get("warranty_start"),
                    "service_end": warranty.get("warranty_end"),
                    "status": warranty.get("status"),
                }
                if warranty else None
            ),
            "tickets": {
                "total": summary["total"],
                "open": summary["open"],
                "resolved": summary["resolved"],
                "closed": summary["closed"],
            },
            "sla": {
                "breached": summary.get("overdue_resolution", 0),
                "at_risk": 0,
            },
            "ready_to_close": unclosed == 0,
        }

    # ========================================================
    # 风险委托（§3.2.9 ~ 3.2.11）
    # ========================================================

    def report_risk(self, **data) -> int:
        """风险报备（委托 RiskEngine）。"""
        return self._risk_engine().report_risk(**data)

    def resolve_risk(self, risk_id: int, action: str, **data) -> None:
        """风险处置（委托 RiskEngine）。"""
        self._risk_engine().review_risk(risk_id, action=action, **data)

    def list_risks(self, **kwargs):
        """查询风险列表（委托 RiskEngine）。"""
        return self._risk_engine().list_risks(**kwargs)

    # ========================================================
    # 变更委托
    # ========================================================

    def create_change_request(self, **data) -> int:
        """创建变更请求（委托 ChangeManagementEngine）。"""
        return self._change_engine().create_change_request(**data)

    # ========================================================
    # 聚合视图（§3.2.12 ~ 3.2.13）
    # ========================================================

    def get_project_detail(self, project_id: int) -> Dict[str, Any]:
        """获取项目完整详情（聚合所有子引擎数据）。"""
        project = self.engine.get_project(project_id)
        if not project:
            raise NotFoundError(f"项目 {project_id} 不存在")

        return {
            "project": project,
            "phases": self.engine.list_phases(project_id),
            "team_members": self.engine.list_team_members(project_id),
            "milestones": self.engine.list_milestones(project_id),
            "delivery_reports": self.engine.list_delivery_reports(project_id),
            "cost_summary": self._cost_engine().get_cost_summary(project_id),
            "risk_summary": self._risk_engine().get_risk_summary(project_id),
        }

    def get_project_dashboard(self, project_id: int) -> Dict[str, Any]:
        """项目仪表盘：进度/成本/风险 概览（§3.2.13）。"""
        project = self.engine.get_project(project_id)
        if not project:
            raise NotFoundError(f"项目 {project_id} 不存在")

        cost = self._cost_engine().get_cost_summary(project_id)
        risk = self._risk_engine().get_risk_summary(project_id)
        milestones = self.engine.list_milestones(project_id)
        phases = self.engine.list_phases(project_id)

        # 进度：已完成阶段 / 总阶段
        completed_phases = sum(1 for p in phases if p["status"] == "completed")
        progress_pct = (
            round(completed_phases / len(phases) * 100, 1) if phases else 0.0
        )

        budget = float(project.get("budget") or 0)
        total_cost = cost["total"]

        return {
            "project_id": project_id,
            "project_name": project["project_name"],
            "status": project["status"],
            "progress_pct": progress_pct,
            "budget": budget,
            "total_cost": total_cost,
            "budget_usage_pct": round(total_cost / budget * 100, 1) if budget else 0.0,
            "milestones_total": len(milestones),
            "milestones_completed": sum(
                1 for m in milestones if m["status"] == "achieved"
            ),
            "risk_total": risk["total"],
            "risk_open": risk["total"] - risk["closed"],
            "risk_critical": risk["by_level"]["critical"],
            "team_size": len(self.engine.list_team_members(project_id)),
        }
