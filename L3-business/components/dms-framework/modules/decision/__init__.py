"""decision 模块 — 决策记录管理

数据存储：work_items 表，type='decision'
状态机：proposed → approved / rejected
        附加：superseded(terminal)
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


@migration("1.3.3")
def upgrade_1_3_3(conn):
    """decision 模块迁移：添加 type='decision' 部分索引。"""
    conn.execute("CREATE INDEX IF NOT EXISTS idx_work_items_type_decision ON work_items(type) WHERE type='decision'")


@dataclass
class Decision(BaseModel):
    """决策记录模型（work_items, type='decision'）。metadata 存储 context/options/rationale 等。"""
    project_id: str = ""
    title: str = ""
    description: str = ""
    status: str = "proposed"
    priority: str = "medium"
    assignee_id: str = ""
    due_date: str = ""
    type: str = "decision"
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
    def context(self) -> str:
        return self._meta("context", "")

    @context.setter
    def context(self, v: str) -> None:
        self._set_meta("context", v)

    @property
    def options(self) -> str:
        return self._meta("options", "")

    @options.setter
    def options(self, v: str) -> None:
        self._set_meta("options", v)

    @property
    def rationale(self) -> str:
        return self._meta("rationale", "")

    @rationale.setter
    def rationale(self, v: str) -> None:
        self._set_meta("rationale", v)


def _build_state_machine() -> StateMachine:
    """构建决策生命周期状态机。"""
    sm = StateMachine(name="decision", description="决策记录生命周期状态机")
    sm.add_state(State("proposed", "todo", is_start=True, description="已提议"))
    sm.add_state(State("approved", "done", is_terminal=True, description="已通过"))
    sm.add_state(State("rejected", "cancelled", is_terminal=True, description="已否决"))
    sm.add_state(State("superseded", "cancelled", is_terminal=True, description="已取代"))
    for n, f, t in [
        ("approve", "proposed", "approved"),
        ("reject", "proposed", "rejected"),
        ("supersede", "approved", "superseded"),
    ]:
        sm.add_transition(Transition(n, f, t))
    return sm


class DecisionModule(BaseModule):
    """决策记录模块：状态机 + 事件 + CLI。"""

    def initialize(self, db: Database, config: dict[str, Any], container: Any) -> None:
        self._db = db
        self._config = config
        self._container = container
        self._repo: Repository[Decision] = Repository(db, Decision, "work_items")
        self._sm = _build_state_machine()
        if hasattr(container, "_state_machine_engine"):
            container._state_machine_engine.register("decision", self._sm)

    def on_ready(self, container: Any) -> None:
        bus = self._bus(container)
        if bus:
            bus.subscribe("project.cancelled", self._on_project_cancelled)

    def _bus(self, container: Any) -> Any:
        return getattr(container, "_event_bus", None)

    def _publish(self, name: str, item: Decision, extra: dict[str, Any] | None = None) -> None:
        bus = self._bus(self._container) if self._container else None
        if not bus:
            return
        payload = {"decision_id": item.id, "project_id": item.project_id,
                   "title": item.title, "status": item.status, "tenant_id": item.tenant_id}
        if extra:
            payload.update(extra)
        bus.publish(name=name, payload=payload, source="decision",
                    entity_type="decision", entity_id=item.id)

    def _on_project_cancelled(self, event: Event) -> None:
        """项目取消 → 否决所有待处理的决策提议。"""
        pid = event.payload.get("project_id", "")
        if not pid:
            return
        for it in self._repo.list(project_id=pid, type="decision"):
            if it.status != "proposed":
                continue
            try:
                old = it.status
                self._sm.fire(it.status, "reject", {"decision_id": it.id})
                it.status = "rejected"
                self._repo.update(it)
                self._publish("decision.status_changed", it, {"old_status": old, "new_status": "rejected"})
            except Exception:
                pass

    def create_decision(self, project_id: str, title: str, description: str = "",
                        priority: str = "medium", assignee_id: str = "") -> Decision:
        """创建决策记录。"""
        item = Decision(id=str(uuid.uuid4()), tenant_id=TenantContext.current(),
                         project_id=project_id, title=title, description=description,
                         status="proposed", priority=priority, assignee_id=assignee_id, type="decision")
        self._repo.add(item)
        self._publish("decision.created", item)
        return item

    def get_decision(self, decision_id: str) -> Optional[Decision]:
        item = self._repo.get(decision_id)
        return item if item and item.type == "decision" else None

    def list_decisions(self, project_id: str, status: str | None = None) -> list[Decision]:
        filters: dict[str, Any] = {"project_id": project_id, "type": "decision"}
        if status:
            filters["status"] = status
        return self._repo.list(**filters)

    def transition_decision(self, decision_id: str, transition_name: str,
                            context: dict[str, Any] | None = None) -> Decision:
        """触发决策状态迁移。"""
        item = self.get_decision(decision_id)
        if not item:
            raise ValueError(f"决策不存在: {decision_id}")
        ctx = context or {}
        ctx.setdefault("decision_id", decision_id)
        ctx.setdefault("tenant_id", TenantContext.current())
        old = item.status
        _, new = self._sm.fire(item.status, transition_name, ctx)
        item.status = new
        self._repo.update(item)
        self._publish("decision.status_changed", item, {"old_status": old, "new_status": new})
        if new == "approved":
            self._publish("decision.approved", item)
        return item

    def delete_decision(self, decision_id: str) -> bool:
        if not self.get_decision(decision_id):
            return False
        return self._repo.delete(decision_id)

    def log(self, project_id: str) -> list[Decision]:
        """决策日志：按创建时间倒序。"""
        items = self.list_decisions(project_id)
        items.sort(key=lambda x: x.created_at or "", reverse=True)
        return items


# -- CLI -------------------------------------------------------------------

def _cmd_create(args: Any, ctx: dict[str, Any]) -> None:
    m: DecisionModule = ctx["module"]
    r = m.create_decision(args.project_id, args.title,
                          priority=getattr(args, "priority", "medium") or "medium",
                          assignee_id=getattr(args, "assignee_id", "") or "")
    print(f"✅ 决策已创建: {r.title} (ID: {r.id})  状态: {r.status}")


def _cmd_list(args: Any, ctx: dict[str, Any]) -> None:
    m: DecisionModule = ctx["module"]
    items = m.list_decisions(args.project_id, status=getattr(args, "status", None))
    if not items:
        print("暂无决策"); return
    print(f"{'ID':<36} {'标题':<20} {'状态':<12} {'优先级':<8}")
    print("-" * 76)
    for it in items:
        print(f"{it.id:<36} {it.title:<20} {it.status:<12} {it.priority:<8}")


def _cmd_get(args: Any, ctx: dict[str, Any]) -> None:
    m: DecisionModule = ctx["module"]
    r = m.get_decision(args.id)
    if not r:
        print(f"决策不存在: {args.id}"); return
    print(f"ID: {r.id}\n标题: {r.title}\n状态: {r.status}\n优先级: {r.priority}")
    print(f"背景: {r.context or '-'}\n选项: {r.options or '-'}")
    print(f"依据: {r.rationale or '-'}\n决策人: {r.assignee_id or '-'}\n项目: {r.project_id}")


def _cmd_transition(args: Any, ctx: dict[str, Any]) -> None:
    m: DecisionModule = ctx["module"]
    try:
        r = m.transition_decision(args.id, args.transition)
        print(f"✅ 状态已迁移: {r.title} → {r.status}")
    except (ValueError, PermissionError) as e:
        print(f"❌ 迁移失败: {e}")


def _cmd_delete(args: Any, ctx: dict[str, Any]) -> None:
    m: DecisionModule = ctx["module"]
    if m.delete_decision(args.id):
        print(f"✅ 决策已删除: {args.id}")
    else:
        print(f"决策不存在: {args.id}")


def _cmd_log(args: Any, ctx: dict[str, Any]) -> None:
    m: DecisionModule = ctx["module"]
    items = m.log(args.project_id)
    if not items:
        print("暂无决策"); return
    print(f"{'ID':<36} {'标题':<20} {'状态':<12} {'创建时间'}")
    print("-" * 82)
    for it in items:
        print(f"{it.id:<36} {it.title:<20} {it.status:<12} {it.created_at}")


# -- Manifest --------------------------------------------------------------

manifest = ModuleManifest(
    name="decision", version="1.0.0",
    description="决策记录模块 — 决策日志 + 生命周期状态机 + 事件驱动",
    dependencies=["project"], tables=["work_items"],
    commands=[
        CommandDef("decision create", "创建决策记录", _cmd_create, [
            {"flags": ["--project-id"], "required": True, "help": "项目 ID"},
            {"flags": ["--title"], "required": True, "help": "决策标题"},
            {"flags": ["--priority"], "default": "medium", "help": "优先级"},
            {"flags": ["--assignee-id"], "help": "决策人 ID"},
        ]),
        CommandDef("decision list", "列出决策", _cmd_list, [
            {"flags": ["--project-id"], "required": True, "help": "项目 ID"},
            {"flags": ["--status"], "help": "按状态过滤"},
        ]),
        CommandDef("decision get", "查看决策详情", _cmd_get, [
            {"flags": ["--id"], "required": True, "help": "决策 ID"},
        ]),
        CommandDef("decision transition", "触发状态迁移", _cmd_transition, [
            {"flags": ["--id"], "required": True, "help": "决策 ID"},
            {"flags": ["--transition"], "required": True,
             "help": "迁移名 (approve/reject/supersede)"},
        ]),
        CommandDef("decision delete", "删除决策", _cmd_delete, [
            {"flags": ["--id"], "required": True, "help": "决策 ID"},
        ]),
        CommandDef("decision log", "决策日志", _cmd_log, [
            {"flags": ["--project-id"], "required": True, "help": "项目 ID"},
        ]),
    ],
)


def _factory(m: ModuleManifest) -> DecisionModule:
    return DecisionModule(m)
