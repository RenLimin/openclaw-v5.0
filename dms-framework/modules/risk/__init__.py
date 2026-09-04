"""risk 模块 — 风险管理

数据存储：work_items 表，type='risk'
状态机：identified → analyzing → mitigating → resolved
        附加：occurred、accepted(terminal)、closed(terminal)
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


@dataclass
class Risk(BaseModel):
    """风险模型（work_items, type='risk'）。metadata 存储 probability/impact/risk_score 等。"""
    project_id: str = ""
    title: str = ""
    description: str = ""
    status: str = "identified"
    priority: str = "medium"
    assignee_id: str = ""
    due_date: str = ""
    type: str = "risk"
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
    def probability(self) -> int:
        return self._meta("probability", 0)

    @probability.setter
    def probability(self, v: int) -> None:
        self._set_meta("probability", v)

    @property
    def impact(self) -> str:
        return self._meta("impact", "medium")

    @impact.setter
    def impact(self, v: str) -> None:
        self._set_meta("impact", v)

    @property
    def risk_score(self) -> int:
        return self._meta("risk_score", 0)

    @risk_score.setter
    def risk_score(self, v: int) -> None:
        self._set_meta("risk_score", v)


def _build_state_machine() -> StateMachine:
    """构建风险生命周期状态机。"""
    sm = StateMachine(name="risk", description="风险生命周期状态机")
    sm.add_state(State("identified", "todo", is_start=True, description="已识别"))
    sm.add_state(State("analyzing", "in_progress", description="分析中"))
    sm.add_state(State("mitigating", "in_progress", description="缓解中"))
    sm.add_state(State("occurred", "blocked", description="风险已发生"))
    sm.add_state(State("resolved", "done", is_terminal=True, description="已解决"))
    sm.add_state(State("accepted", "done", is_terminal=True, description="已接受"))
    sm.add_state(State("closed", "cancelled", is_terminal=True, description="已关闭"))
    for n, f, t in [
        ("analyze", "identified", "analyzing"),
        ("plan", "analyzing", "mitigating"),
        ("resolve", "mitigating", "resolved"),
        ("occur", "analyzing", "occurred"),
        ("mitigate", "occurred", "mitigating"),
        ("accept", "analyzing", "accepted"),
        ("close", "identified", "closed"),
    ]:
        sm.add_transition(Transition(n, f, t))
    return sm


class RiskModule(BaseModule):
    """风险模块：状态机 + 事件 + CLI。"""

    def initialize(self, db: Database, config: dict[str, Any], container: Any) -> None:
        self._db = db
        self._config = config
        self._container = container
        self._repo: Repository[Risk] = Repository(db, Risk, "work_items")
        self._sm = _build_state_machine()
        if hasattr(container, "_state_machine_engine"):
            container._state_machine_engine.register("risk", self._sm)

    def on_ready(self, container: Any) -> None:
        bus = self._bus(container)
        if bus:
            bus.subscribe("project.cancelled", self._on_project_cancelled)

    # -- 内部 --------------------------------------------------------------

    def _bus(self, container: Any) -> Any:
        return getattr(container, "_event_bus", None)

    def _publish(self, name: str, item: Risk, extra: dict[str, Any] | None = None) -> None:
        bus = self._bus(self._container) if self._container else None
        if not bus:
            return
        payload = {"risk_id": item.id, "project_id": item.project_id,
                   "title": item.title, "status": item.status, "tenant_id": item.tenant_id}
        if extra:
            payload.update(extra)
        bus.publish(name=name, payload=payload, source="risk",
                    entity_type="risk", entity_id=item.id)

    # -- 事件处理 ----------------------------------------------------------

    def _on_project_cancelled(self, event: Event) -> None:
        """项目取消 → 关闭项目下所有非终态风险。"""
        pid = event.payload.get("project_id", "")
        if not pid:
            return
        terminal = {"resolved", "accepted", "closed"}
        for it in self._repo.list(project_id=pid, type="risk"):
            if it.status in terminal:
                continue
            try:
                if it.status == "identified":
                    self._sm.fire(it.status, "close", {"risk_id": it.id, "reason": "project_cancelled"})
                    old = it.status
                    it.status = "closed"
                    self._repo.update(it)
                    self._publish("risk.status_changed", it, {"old_status": old, "new_status": "closed"})
            except Exception:
                pass

    # -- 业务方法 ----------------------------------------------------------

    def create_risk(self, project_id: str, title: str, description: str = "",
                    priority: str = "medium", assignee_id: str = "") -> Risk:
        """创建风险。"""
        item = Risk(id=str(uuid.uuid4()), tenant_id=TenantContext.current(),
                    project_id=project_id, title=title, description=description,
                    status="identified", priority=priority, assignee_id=assignee_id, type="risk")
        self._repo.add(item)
        self._publish("risk.created", item)
        return item

    def get_risk(self, risk_id: str) -> Optional[Risk]:
        item = self._repo.get(risk_id)
        return item if item and item.type == "risk" else None

    def list_risks(self, project_id: str, status: str | None = None) -> list[Risk]:
        filters: dict[str, Any] = {"project_id": project_id, "type": "risk"}
        if status:
            filters["status"] = status
        return self._repo.list(**filters)

    def transition_risk(self, risk_id: str, transition_name: str,
                        context: dict[str, Any] | None = None) -> Risk:
        """触发风险状态迁移。"""
        item = self.get_risk(risk_id)
        if not item:
            raise ValueError(f"风险不存在: {risk_id}")
        ctx = context or {}
        ctx.setdefault("risk_id", risk_id)
        ctx.setdefault("tenant_id", TenantContext.current())
        old = item.status
        _, new = self._sm.fire(item.status, transition_name, ctx)
        item.status = new
        self._repo.update(item)
        self._publish("risk.status_changed", item, {"old_status": old, "new_status": new})
        if new == "resolved":
            self._publish("risk.resolved", item)
        if new == "occurred":
            self._publish("risk.occurred", item)
        return item

    def delete_risk(self, risk_id: str) -> bool:
        if not self.get_risk(risk_id):
            return False
        return self._repo.delete(risk_id)


# -- CLI -------------------------------------------------------------------

def _cmd_create(args: Any, ctx: dict[str, Any]) -> None:
    m: RiskModule = ctx["module"]
    r = m.create_risk(args.project_id, args.title,
                      priority=getattr(args, "priority", "medium") or "medium",
                      assignee_id=getattr(args, "assignee_id", "") or "")
    print(f"✅ 风险已创建: {r.title} (ID: {r.id})  状态: {r.status}")


def _cmd_list(args: Any, ctx: dict[str, Any]) -> None:
    m: RiskModule = ctx["module"]
    items = m.list_risks(args.project_id, status=getattr(args, "status", None))
    if not items:
        print("暂无风险"); return
    print(f"{'ID':<36} {'标题':<20} {'状态':<12} {'优先级':<8}")
    print("-" * 76)
    for it in items:
        print(f"{it.id:<36} {it.title:<20} {it.status:<12} {it.priority:<8}")


def _cmd_get(args: Any, ctx: dict[str, Any]) -> None:
    m: RiskModule = ctx["module"]
    r = m.get_risk(args.id)
    if not r:
        print(f"风险不存在: {args.id}"); return
    print(f"ID: {r.id}\n标题: {r.title}\n状态: {r.status}\n优先级: {r.priority}")
    print(f"负责人: {r.assignee_id}\n项目: {r.project_id}")
    print(f"概率/影响: {r.probability}% / {r.impact}  评分: {r.risk_score}")


def _cmd_transition(args: Any, ctx: dict[str, Any]) -> None:
    m: RiskModule = ctx["module"]
    try:
        r = m.transition_risk(args.id, args.transition)
        print(f"✅ 状态已迁移: {r.title} → {r.status}")
    except ValueError as e:
        print(f"❌ 迁移失败: {e}")


def _cmd_delete(args: Any, ctx: dict[str, Any]) -> None:
    m: RiskModule = ctx["module"]
    if m.delete_risk(args.id):
        print(f"✅ 风险已删除: {args.id}")
    else:
        print(f"风险不存在: {args.id}")


# -- Manifest --------------------------------------------------------------

manifest = ModuleManifest(
    name="risk", version="1.0.0",
    description="风险管理模块 — 生命周期状态机 + 事件驱动",
    dependencies=["project"], tables=["work_items"],
    commands=[
        CommandDef("risk create", "创建风险", _cmd_create, [
            {"flags": ["--project-id"], "required": True, "help": "项目 ID"},
            {"flags": ["--title"], "required": True, "help": "风险标题"},
            {"flags": ["--priority"], "default": "medium", "help": "优先级 (low/medium/high)"},
            {"flags": ["--assignee-id"], "help": "负责人 ID"},
        ]),
        CommandDef("risk list", "列出项目下的风险", _cmd_list, [
            {"flags": ["--project-id"], "required": True, "help": "项目 ID"},
            {"flags": ["--status"], "help": "按状态过滤"},
        ]),
        CommandDef("risk get", "查看风险详情", _cmd_get, [
            {"flags": ["--id"], "required": True, "help": "风险 ID"},
        ]),
        CommandDef("risk transition", "触发风险状态迁移", _cmd_transition, [
            {"flags": ["--id"], "required": True, "help": "风险 ID"},
            {"flags": ["--transition"], "required": True,
             "help": "迁移名 (analyze/plan/resolve/occur/mitigate/accept/close)"},
        ]),
        CommandDef("risk delete", "删除风险", _cmd_delete, [
            {"flags": ["--id"], "required": True, "help": "风险 ID"},
        ]),
    ],
)


def _factory(m: ModuleManifest) -> RiskModule:
    return RiskModule(m)
