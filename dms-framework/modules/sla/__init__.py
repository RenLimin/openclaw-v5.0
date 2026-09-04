"""sla 模块 — SLA 跟踪

数据存储：work_items 表，type='sla'
状态机：defined → monitoring → met / breached
        breached → monitoring / escalated → monitoring
        met → monitoring
        任意非终态 → closed(terminal)
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


@migration("1.2.3")
def upgrade_1_2_3(conn):
    conn.execute("CREATE INDEX IF NOT EXISTS idx_work_items_type_sla ON work_items(type) WHERE type='sla'")


@dataclass
class SLA(BaseModel):
    """SLA 模型（work_items, type='sla'）。metadata 存储 metric_name/target_value/actual_value/measurement_unit/evaluation_period。"""
    project_id: str = ""
    title: str = ""
    description: str = ""
    status: str = "defined"
    priority: str = "medium"
    assignee_id: str = ""
    due_date: str = ""
    type: str = "sla"
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
    def metric_name(self) -> str:
        return self._meta("metric_name", "")

    @metric_name.setter
    def metric_name(self, v: str) -> None:
        self._set_meta("metric_name", v)

    @property
    def target_value(self) -> float:
        return self._meta("target_value", 0.0)

    @target_value.setter
    def target_value(self, v: float) -> None:
        self._set_meta("target_value", v)

    @property
    def actual_value(self) -> float:
        return self._meta("actual_value", 0.0)

    @actual_value.setter
    def actual_value(self, v: float) -> None:
        self._set_meta("actual_value", v)

    @property
    def measurement_unit(self) -> str:
        return self._meta("measurement_unit", "")

    @measurement_unit.setter
    def measurement_unit(self, v: str) -> None:
        self._set_meta("measurement_unit", v)

    @property
    def evaluation_period(self) -> str:
        return self._meta("evaluation_period", "monthly")

    @evaluation_period.setter
    def evaluation_period(self, v: str) -> None:
        self._set_meta("evaluation_period", v)


def _build_state_machine() -> StateMachine:
    """构建 SLA 生命周期状态机。"""
    sm = StateMachine(name="sla", description="SLA 生命周期状态机")
    sm.add_state(State("defined", "todo", is_start=True, description="已定义"))
    sm.add_state(State("monitoring", "in_progress", description="监控中"))
    sm.add_state(State("met", "done", description="已达标"))
    sm.add_state(State("breached", "blocked", description="已违约"))
    sm.add_state(State("escalated", "blocked", description="已升级"))
    sm.add_state(State("closed", "cancelled", is_terminal=True, description="已关闭"))
    for n, f, t in [
        ("start_monitoring", "defined", "monitoring"),
        ("meet", "monitoring", "met"),
        ("breach", "monitoring", "breached"),
        ("resume", "breached", "monitoring"),
        ("escalate", "breached", "escalated"),
        ("escalate_resume", "escalated", "monitoring"),
        ("continue_monitoring", "met", "monitoring"),
        ("close", "defined", "closed"),
        ("close_monitoring", "monitoring", "closed"),
        ("close_met", "met", "closed"),
        ("close_breached", "breached", "closed"),
        ("close_escalated", "escalated", "closed"),
    ]:
        sm.add_transition(Transition(n, f, t))
    return sm


class SLAModule(BaseModule):
    """SLA 模块：状态机 + 事件 + CLI。"""

    def initialize(self, db: Database, config: dict[str, Any], container: Any) -> None:
        self._db = db
        self._config = config
        self._container = container
        self._repo: Repository[SLA] = Repository(db, SLA, "work_items")
        self._sm = _build_state_machine()
        if hasattr(container, "_state_machine_engine"):
            container._state_machine_engine.register("sla", self._sm)

    def on_ready(self, container: Any) -> None:
        bus = self._bus(container)
        if bus:
            bus.subscribe("project.cancelled", self._on_project_cancelled)

    # -- 内部 --------------------------------------------------------------

    def _bus(self, container: Any) -> Any:
        return getattr(container, "_event_bus", None)

    def _publish(self, name: str, item: SLA, extra: dict[str, Any] | None = None) -> None:
        bus = self._bus(self._container) if self._container else None
        if not bus:
            return
        payload = {"sla_id": item.id, "project_id": item.project_id,
                   "title": item.title, "status": item.status, "tenant_id": item.tenant_id}
        if extra:
            payload.update(extra)
        bus.publish(name=name, payload=payload, source="sla",
                    entity_type="sla", entity_id=item.id)

    # -- 事件处理 ----------------------------------------------------------

    def _on_project_cancelled(self, event: Event) -> None:
        """项目取消 → 关闭项目下所有非终态 SLA。"""
        pid = event.payload.get("project_id", "")
        if not pid:
            return
        terminal = {"closed"}
        for it in self._repo.list(project_id=pid, type="sla"):
            if it.status in terminal:
                continue
            try:
                old = it.status
                it.status = "closed"
                self._repo.update(it)
                self._publish("sla.status_changed", it, {"old_status": old, "new_status": "closed"})
            except Exception:
                pass

    # -- 业务方法 ----------------------------------------------------------

    def create_sla(self, project_id: str, title: str, description: str = "",
                   priority: str = "medium", assignee_id: str = "") -> SLA:
        """创建 SLA 记录。"""
        item = SLA(id=str(uuid.uuid4()), tenant_id=TenantContext.current(),
                   project_id=project_id, title=title, description=description,
                   status="defined", priority=priority, assignee_id=assignee_id, type="sla")
        self._repo.add(item)
        self._publish("sla.created", item)
        return item

    def get_sla(self, sla_id: str) -> Optional[SLA]:
        item = self._repo.get(sla_id)
        return item if item and item.type == "sla" else None

    def list_slas(self, project_id: str, status: str | None = None) -> list[SLA]:
        filters: dict[str, Any] = {"project_id": project_id, "type": "sla"}
        if status:
            filters["status"] = status
        return self._repo.list(**filters)

    def transition_sla(self, sla_id: str, transition_name: str,
                       context: dict[str, Any] | None = None) -> SLA:
        """触发 SLA 状态迁移。"""
        item = self.get_sla(sla_id)
        if not item:
            raise ValueError(f"SLA 不存在: {sla_id}")
        ctx = context or {}
        ctx.setdefault("sla_id", sla_id)
        ctx.setdefault("tenant_id", TenantContext.current())
        old = item.status
        _, new = self._sm.fire(item.status, transition_name, ctx)
        item.status = new
        self._repo.update(item)
        self._publish("sla.status_changed", item, {"old_status": old, "new_status": new})
        if new == "met":
            self._publish("sla.met", item)
        if new == "breached":
            self._publish("sla.breached", item)
        if new == "escalated":
            self._publish("sla.escalated", item)
        return item

    def delete_sla(self, sla_id: str) -> bool:
        if not self.get_sla(sla_id):
            return False
        return self._repo.delete(sla_id)

    def dashboard(self, project_id: str) -> dict[str, Any]:
        """SLA 仪表盘统计：总数、各状态数量、达标率。"""
        items = self.list_slas(project_id)
        total = len(items)
        by_status: dict[str, int] = {}
        for it in items:
            by_status[it.status] = by_status.get(it.status, 0) + 1
        met_count = by_status.get("met", 0)
        breached_count = by_status.get("breached", 0)
        monitoring_count = by_status.get("monitoring", 0)
        escalated_count = by_status.get("escalated", 0)
        closed_count = by_status.get("closed", 0)
        defined_count = by_status.get("defined", 0)
        # 达标率：已达标的 / (已达标 + 已违约)，没有结果则为 0
        result_total = met_count + breached_count
        met_rate = round(met_count / result_total * 100, 2) if result_total > 0 else 0.0
        return {
            "total": total,
            "by_status": by_status,
            "defined": defined_count,
            "monitoring": monitoring_count,
            "met": met_count,
            "breached": breached_count,
            "escalated": escalated_count,
            "closed": closed_count,
            "met_rate_pct": met_rate,
        }


# -- CLI -------------------------------------------------------------------

def _cmd_create(args: Any, ctx: dict[str, Any]) -> None:
    m: SLAModule = ctx["module"]
    r = m.create_sla(args.project_id, args.title,
                     description=getattr(args, "description", "") or "",
                     priority=getattr(args, "priority", "medium") or "medium",
                     assignee_id=getattr(args, "assignee_id", "") or "")
    print(f"✅ SLA 已创建: {r.title} (ID: {r.id})  状态: {r.status}")


def _cmd_list(args: Any, ctx: dict[str, Any]) -> None:
    m: SLAModule = ctx["module"]
    items = m.list_slas(args.project_id, status=getattr(args, "status", None))
    if not items:
        print("暂无 SLA 记录"); return
    print(f"{'ID':<36} {'标题':<20} {'状态':<12} {'优先级':<8}")
    print("-" * 76)
    for it in items:
        print(f"{it.id:<36} {it.title:<20} {it.status:<12} {it.priority:<8}")


def _cmd_get(args: Any, ctx: dict[str, Any]) -> None:
    m: SLAModule = ctx["module"]
    s = m.get_sla(args.id)
    if not s:
        print(f"SLA 不存在: {args.id}"); return
    print(f"ID: {s.id}\n标题: {s.title}\n状态: {s.status}\n优先级: {s.priority}")
    print(f"负责人: {s.assignee_id}\n项目: {s.project_id}")
    print(f"指标: {s.metric_name}  目标: {s.target_value} {s.measurement_unit}")
    print(f"当前值: {s.actual_value} {s.measurement_unit}")
    print(f"评估周期: {s.evaluation_period}")


def _cmd_transition(args: Any, ctx: dict[str, Any]) -> None:
    m: SLAModule = ctx["module"]
    try:
        r = m.transition_sla(args.id, args.transition)
        print(f"✅ 状态已迁移: {r.title} → {r.status}")
    except ValueError as e:
        print(f"❌ 迁移失败: {e}")


def _cmd_delete(args: Any, ctx: dict[str, Any]) -> None:
    m: SLAModule = ctx["module"]
    if m.delete_sla(args.id):
        print(f"✅ SLA 已删除: {args.id}")
    else:
        print(f"SLA 不存在: {args.id}")


def _cmd_dashboard(args: Any, ctx: dict[str, Any]) -> None:
    m: SLAModule = ctx["module"]
    d = m.dashboard(args.project_id)
    print(f"📊 SLA 仪表盘 — 项目 {args.project_id}")
    print(f"   总数: {d['total']}")
    print(f"   已定义: {d['defined']}  监控中: {d['monitoring']}  已达标: {d['met']}")
    print(f"   已违约: {d['breached']}  已升级: {d['escalated']}  已关闭: {d['closed']}")
    print(f"   达标率: {d['met_rate_pct']}%")


# -- Manifest --------------------------------------------------------------

manifest = ModuleManifest(
    name="sla", version="1.0.0",
    description="SLA 跟踪模块 — 服务水平协议生命周期管理 + 达标率统计",
    dependencies=["project"], tables=["work_items"],
    commands=[
        CommandDef("sla create", "创建 SLA 记录", _cmd_create, [
            {"flags": ["--project-id"], "required": True, "help": "项目 ID"},
            {"flags": ["--title"], "required": True, "help": "SLA 标题"},
            {"flags": ["--description"], "default": "", "help": "描述"},
            {"flags": ["--priority"], "default": "medium", "help": "优先级 (low/medium/high)"},
            {"flags": ["--assignee-id"], "help": "负责人 ID"},
        ]),
        CommandDef("sla list", "列出项目下的 SLA 记录", _cmd_list, [
            {"flags": ["--project-id"], "required": True, "help": "项目 ID"},
            {"flags": ["--status"], "help": "按状态过滤"},
        ]),
        CommandDef("sla get", "查看 SLA 详情", _cmd_get, [
            {"flags": ["--id"], "required": True, "help": "SLA ID"},
        ]),
        CommandDef("sla transition", "触发 SLA 状态迁移", _cmd_transition, [
            {"flags": ["--id"], "required": True, "help": "SLA ID"},
            {"flags": ["--transition"], "required": True,
             "help": "迁移名 (start_monitoring/meet/breach/resume/escalate/escalate_resume/continue_monitoring/close_*)"},
        ]),
        CommandDef("sla delete", "删除 SLA 记录", _cmd_delete, [
            {"flags": ["--id"], "required": True, "help": "SLA ID"},
        ]),
        CommandDef("sla dashboard", "SLA 仪表盘（达标率/违约统计）", _cmd_dashboard, [
            {"flags": ["--project-id"], "required": True, "help": "项目 ID"},
        ]),
    ],
)


def _factory(m: ModuleManifest) -> SLAModule:
    return SLAModule(m)
