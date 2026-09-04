"""budget 模块 — 预算管理

数据存储：work_items 表，type='budget'
状态机：draft → approved → executing → closed(terminal)
        draft → cancelled(terminal) / approved → revised → approved
        executing → over_budget → executing
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from core.module import BaseModule, ModuleManifest, CommandDef
from core.database import BaseModel, Repository, Database
from core.state_machine import StateMachine, State, Transition
from core.event_bus import Event
from core.saas import TenantContext
from core.migrations import migration


@migration("1.2.0")
def upgrade_1_2_0(conn):
    conn.execute("CREATE INDEX IF NOT EXISTS idx_work_items_type_budget ON work_items(type) WHERE type='budget'")


@dataclass
class Budget(BaseModel):
    """预算模型（work_items, type='budget'）。metadata 存储 planned_cost/actual_cost/variance/cost_type。"""
    project_id: str = ""
    title: str = ""
    description: str = ""
    status: str = "draft"
    priority: str = "medium"
    assignee_id: str = ""
    due_date: str = ""
    type: str = "budget"
    metadata: str = ""
    __tablename__ = "work_items"

    def _meta(self, key: str, default: Any = None) -> Any:
        if not self.metadata:
            return default
        try:
            return json.loads(self.metadata).get(key, default)
        except (json.JSONDecodeError, AttributeError):
            return default

    def _set_meta(self, key: str, value: Any) -> None:
        data: dict[str, Any] = {}
        if self.metadata:
            try:
                data = json.loads(self.metadata)
            except (json.JSONDecodeError, AttributeError):
                data = {}
        data[key] = value
        self.metadata = json.dumps(data, ensure_ascii=False)

    @property
    def planned_cost(self) -> float:
        return float(self._meta("planned_cost", 0.0))

    @planned_cost.setter
    def planned_cost(self, v: float) -> None:
        self._set_meta("planned_cost", float(v))
        self._set_meta("variance", float(self._meta("actual_cost", 0.0)) - float(v))

    @property
    def actual_cost(self) -> float:
        return float(self._meta("actual_cost", 0.0))

    @actual_cost.setter
    def actual_cost(self, v: float) -> None:
        self._set_meta("actual_cost", float(v))
        self._set_meta("variance", float(v) - float(self._meta("planned_cost", 0.0)))

    @property
    def variance(self) -> float:
        return float(self._meta("variance", 0.0))

    @property
    def cost_type(self) -> str:
        return self._meta("cost_type", "operational")

    @cost_type.setter
    def cost_type(self, v: str) -> None:
        self._set_meta("cost_type", v)


def _build_state_machine() -> StateMachine:
    """构建预算生命周期状态机。"""
    sm = StateMachine(name="budget", description="预算生命周期状态机")
    sm.add_state(State("draft", "todo", is_start=True, description="草稿"))
    sm.add_state(State("approved", "in_progress", description="已批准"))
    sm.add_state(State("revised", "in_progress", description="已修订"))
    sm.add_state(State("executing", "in_progress", description="执行中"))
    sm.add_state(State("over_budget", "blocked", description="超支"))
    sm.add_state(State("closed", "done", is_terminal=True, description="已关闭"))
    sm.add_state(State("cancelled", "cancelled", is_terminal=True, description="已取消"))
    for n, f, t in [
        ("approve", "draft", "approved"),
        ("revise", "approved", "revised"),
        ("reapprove", "revised", "approved"),
        ("execute", "approved", "executing"),
        ("flag_over_budget", "executing", "over_budget"),
        ("back_to_executing", "over_budget", "executing"),
        ("close", "executing", "closed"),
        ("cancel", "draft", "cancelled"),
    ]:
        sm.add_transition(Transition(n, f, t))
    return sm


class BudgetModule(BaseModule):
    """预算模块：状态机 + 事件 + CLI。"""

    def initialize(self, db: Database, config: dict[str, Any], container: Any) -> None:
        self._db = db
        self._config = config
        self._container = container
        self._repo: Repository[Budget] = Repository(db, Budget, "work_items")
        self._sm = _build_state_machine()
        if hasattr(container, "_state_machine_engine"):
            container._state_machine_engine.register("budget", self._sm)

    def on_ready(self, container: Any) -> None:
        bus = self._bus(container)
        if bus:
            bus.subscribe("project.cancelled", self._on_project_cancelled)

    def _bus(self, c: Any) -> Any:
        return getattr(c, "_event_bus", None)

    def _publish(self, name: str, item: Budget, extra: dict[str, Any] | None = None) -> None:
        bus = self._bus(self._container) if self._container else None
        if not bus:
            return
        payload = {"budget_id": item.id, "project_id": item.project_id,
                   "title": item.title, "status": item.status, "tenant_id": item.tenant_id,
                   "planned_cost": item.planned_cost, "actual_cost": item.actual_cost,
                   "variance": item.variance}
        if extra:
            payload.update(extra)
        bus.publish(name=name, payload=payload, source="budget",
                    entity_type="budget", entity_id=item.id)

    def _on_project_cancelled(self, event: Event) -> None:
        """项目取消 → 关闭项目下所有非终态预算记录。"""
        pid = event.payload.get("project_id", "")
        if not pid:
            return
        for it in self._repo.list(project_id=pid, type="budget"):
            if it.status in ("closed", "cancelled"):
                continue
            try:
                if it.status == "draft":
                    action, target = "cancel", "cancelled"
                elif it.status == "executing":
                    action, target = "close", "closed"
                else:
                    continue
                self._sm.fire(it.status, action, {"budget_id": it.id, "reason": "project_cancelled"})
                old = it.status
                it.status = target
                self._repo.update(it)
                self._publish("budget.status_changed", it, {"old_status": old, "new_status": target})
            except Exception:
                pass

    def create_budget(self, project_id: str, title: str, description: str = "",
                      priority: str = "medium", assignee_id: str = "",
                      planned_cost: float = 0.0, cost_type: str = "operational") -> Budget:
        item = Budget(id=str(uuid.uuid4()), tenant_id=TenantContext.current(),
                      project_id=project_id, title=title, description=description,
                      status="draft", priority=priority, assignee_id=assignee_id, type="budget")
        item.planned_cost = planned_cost
        item.cost_type = cost_type
        self._repo.add(item)
        self._publish("budget.created", item)
        return item

    def get_budget(self, budget_id: str) -> Optional[Budget]:
        item = self._repo.get(budget_id)
        return item if item and item.type == "budget" else None

    def list_budgets(self, project_id: str, status: str | None = None) -> list[Budget]:
        filters: dict[str, Any] = {"project_id": project_id, "type": "budget"}
        if status:
            filters["status"] = status
        return self._repo.list(**filters)

    def transition_budget(self, budget_id: str, transition_name: str,
                          context: dict[str, Any] | None = None) -> Budget:
        item = self.get_budget(budget_id)
        if not item:
            raise ValueError(f"预算不存在: {budget_id}")
        ctx = context or {}
        ctx.setdefault("budget_id", budget_id)
        ctx.setdefault("tenant_id", TenantContext.current())
        old = item.status
        _, new = self._sm.fire(item.status, transition_name, ctx)
        item.status = new
        self._repo.update(item)
        self._publish("budget.status_changed", item, {"old_status": old, "new_status": new})
        if new == "approved":
            self._publish("budget.approved", item)
        if new == "over_budget":
            self._publish("budget.over_budget", item)
        return item

    def delete_budget(self, budget_id: str) -> bool:
        return self._repo.delete(budget_id) if self.get_budget(budget_id) else False

    def summary(self, project_id: str) -> dict[str, Any]:
        """项目预算汇总：计划总额、实际总额、偏差。"""
        items = self.list_budgets(project_id)
        tp = sum(it.planned_cost for it in items)
        ta = sum(it.actual_cost for it in items)
        return {"count": len(items), "total_planned": tp, "total_actual": ta, "total_variance": ta - tp}


# -- CLI -------------------------------------------------------------------

def _cmd_create(args: Any, ctx: dict[str, Any]) -> None:
    m: BudgetModule = ctx["module"]
    r = m.create_budget(
        args.project_id, args.title,
        description=getattr(args, "description", "") or "",
        priority=getattr(args, "priority", "medium") or "medium",
        assignee_id=getattr(args, "assignee_id", "") or "",
        planned_cost=float(getattr(args, "planned_cost", 0) or 0),
        cost_type=getattr(args, "cost_type", "operational") or "operational",
    )
    print(f"✅ 预算已创建: {r.title} (ID: {r.id})  状态: {r.status}  计划: {r.planned_cost}")


def _cmd_list(args: Any, ctx: dict[str, Any]) -> None:
    m: BudgetModule = ctx["module"]
    items = m.list_budgets(args.project_id, status=getattr(args, "status", None))
    if not items:
        print("暂无预算记录"); return
    print(f"{'ID':<36} {'标题':<20} {'状态':<14} {'计划':>8} {'实际':>8} {'偏差':>8}")
    print("-" * 90)
    for it in items:
        print(f"{it.id:<36} {it.title:<20} {it.status:<14} {it.planned_cost:>8.2f} {it.actual_cost:>8.2f} {it.variance:>8.2f}")


def _cmd_get(args: Any, ctx: dict[str, Any]) -> None:
    m: BudgetModule = ctx["module"]
    r = m.get_budget(args.id)
    if not r:
        print(f"预算不存在: {args.id}"); return
    print(f"ID: {r.id}\n标题: {r.title}\n状态: {r.status}\n优先级: {r.priority}")
    print(f"负责人: {r.assignee_id}\n项目: {r.project_id}\n成本类型: {r.cost_type}")
    print(f"计划: {r.planned_cost}  实际: {r.actual_cost}  偏差: {r.variance}")


def _cmd_transition(args: Any, ctx: dict[str, Any]) -> None:
    m: BudgetModule = ctx["module"]
    try:
        r = m.transition_budget(args.id, args.transition)
        print(f"✅ 状态已迁移: {r.title} → {r.status}")
    except ValueError as e:
        print(f"❌ 迁移失败: {e}")


def _cmd_delete(args: Any, ctx: dict[str, Any]) -> None:
    m: BudgetModule = ctx["module"]
    print(f"✅ 预算已删除: {args.id}" if m.delete_budget(args.id) else f"预算不存在: {args.id}")


def _cmd_summary(args: Any, ctx: dict[str, Any]) -> None:
    m: BudgetModule = ctx["module"]
    s = m.summary(args.project_id)
    print(f"项目 {args.project_id} 预算汇总")
    print(f"  数量: {s['count']}  计划: {s['total_planned']:.2f}  实际: {s['total_actual']:.2f}  偏差: {s['total_variance']:.2f}")


manifest = ModuleManifest(
    name="budget", version="1.2.0",
    description="预算管理模块 — 生命周期状态机 + 事件驱动",
    dependencies=["project"], tables=["work_items"],
    commands=[
        CommandDef("budget create", "创建预算", _cmd_create, [
            {"flags": ["--project-id"], "required": True, "help": "项目 ID"},
            {"flags": ["--title"], "required": True, "help": "预算标题"},
            {"flags": ["--description"], "default": "", "help": "预算描述"},
            {"flags": ["--priority"], "default": "medium", "help": "优先级"},
            {"flags": ["--assignee-id"], "help": "负责人 ID"},
            {"flags": ["--planned-cost"], "default": "0", "help": "计划成本"},
            {"flags": ["--cost-type"], "default": "operational", "help": "成本类型"},
        ]),
        CommandDef("budget list", "列出项目预算", _cmd_list, [
            {"flags": ["--project-id"], "required": True, "help": "项目 ID"},
            {"flags": ["--status"], "help": "按状态过滤"},
        ]),
        CommandDef("budget get", "查看预算详情", _cmd_get, [
            {"flags": ["--id"], "required": True, "help": "预算 ID"},
        ]),
        CommandDef("budget transition", "触发状态迁移", _cmd_transition, [
            {"flags": ["--id"], "required": True, "help": "预算 ID"},
            {"flags": ["--transition"], "required": True, "help": "迁移名"},
        ]),
        CommandDef("budget delete", "删除预算", _cmd_delete, [
            {"flags": ["--id"], "required": True, "help": "预算 ID"},
        ]),
        CommandDef("budget summary", "项目预算汇总", _cmd_summary, [
            {"flags": ["--project-id"], "required": True, "help": "项目 ID"},
        ]),
    ],
)


def _factory(m: ModuleManifest) -> BudgetModule:
    return BudgetModule(m)
