"""communication 模块 — 沟通管理

数据存储：work_items 表，type='communication'
状态机：planned → in_progress → completed
        附加：cancelled(terminal)、escalated（可回 in_progress）
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


@migration("1.2.4")
def upgrade_1_2_4(conn):
    """为 communication 类型的 work_items 建索引。"""
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_work_items_type_communication "
        "ON work_items(type) WHERE type='communication'"
    )


_META_FIELDS = ("channel", "audience", "frequency", "message_type", "scheduled_at")


@dataclass
class Communication(BaseModel):
    """沟通记录模型（work_items, type='communication'）。

    metadata 存储：channel / audience / frequency / message_type / scheduled_at
    """
    project_id: str = ""
    title: str = ""
    description: str = ""
    status: str = "planned"
    priority: str = "medium"
    assignee_id: str = ""
    due_date: str = ""
    type: str = "communication"
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

    def __getattr__(self, name: str) -> Any:
        if name in _META_FIELDS:
            return self._meta(name, "")
        raise AttributeError(name)


def _build_state_machine() -> StateMachine:
    """构建沟通记录生命周期状态机。"""
    sm = StateMachine(name="communication", description="沟通记录生命周期状态机")
    sm.add_state(State("planned", "todo", is_start=True, description="已计划"))
    sm.add_state(State("in_progress", "in_progress", description="进行中"))
    sm.add_state(State("escalated", "blocked", description="已升级"))
    sm.add_state(State("completed", "done", is_terminal=True, description="已完成"))
    sm.add_state(State("cancelled", "cancelled", is_terminal=True, description="已取消"))
    for n, f, t in [
        ("start", "planned", "in_progress"),
        ("complete", "in_progress", "completed"),
        ("cancel", "planned", "cancelled"),
        ("escalate", "in_progress", "escalated"),
        ("deescalate", "escalated", "in_progress"),
    ]:
        sm.add_transition(Transition(n, f, t))
    return sm


class CommunicationModule(BaseModule):
    """沟通模块：状态机 + 事件 + CLI。"""

    def initialize(self, db: Database, config: dict[str, Any], container: Any) -> None:
        self._db = db
        self._config = config
        self._container = container
        self._repo: Repository[Communication] = Repository(db, Communication, "work_items")
        self._sm = _build_state_machine()
        if hasattr(container, "_state_machine_engine"):
            container._state_machine_engine.register("communication", self._sm)

    def on_ready(self, container: Any) -> None:
        bus = self._bus(container)
        if bus:
            bus.subscribe("project.cancelled", self._on_project_cancelled)

    def _bus(self, container: Any) -> Any:
        return getattr(container, "_event_bus", None)

    def _publish(self, name: str, item: Communication, extra: dict[str, Any] | None = None) -> None:
        bus = self._bus(self._container) if self._container else None
        if not bus:
            return
        payload = {"communication_id": item.id, "project_id": item.project_id,
                   "title": item.title, "status": item.status, "tenant_id": item.tenant_id}
        if extra:
            payload.update(extra)
        bus.publish(name=name, payload=payload, source="communication",
                    entity_type="communication", entity_id=item.id)

    def _on_project_cancelled(self, event: Event) -> None:
        """项目取消 → 取消项目下所有非终态沟通计划。"""
        pid = event.payload.get("project_id", "")
        if not pid:
            return
        terminal = {"completed", "cancelled"}
        for it in self._repo.list(project_id=pid, type="communication"):
            if it.status in terminal:
                continue
            try:
                if it.status == "planned":
                    self._sm.fire(it.status, "cancel",
                                  {"communication_id": it.id, "reason": "project_cancelled"})
                    old, it.status = it.status, "cancelled"
                    self._repo.update(it)
                    self._publish("communication.status_changed", it,
                                  {"old_status": old, "new_status": "cancelled"})
            except Exception:
                pass

    def create_communication(self, project_id: str, title: str, description: str = "",
                             priority: str = "medium", assignee_id: str = "",
                             **meta_kwargs: str) -> Communication:
        """创建沟通记录。meta_kwargs 支持 channel/audience/frequency/message_type/scheduled_at。"""
        item = Communication(
            id=str(uuid.uuid4()), tenant_id=TenantContext.current(),
            project_id=project_id, title=title, description=description,
            status="planned", priority=priority, assignee_id=assignee_id,
            type="communication",
        )
        for k, v in meta_kwargs.items():
            if k in _META_FIELDS and v:
                item._set_meta(k, v)
        self._repo.add(item)
        self._publish("communication.created", item)
        return item

    def get_communication(self, comm_id: str) -> Optional[Communication]:
        item = self._repo.get(comm_id)
        return item if item and item.type == "communication" else None

    def list_communications(self, project_id: str, status: str | None = None) -> list[Communication]:
        filters: dict[str, Any] = {"project_id": project_id, "type": "communication"}
        if status:
            filters["status"] = status
        return self._repo.list(**filters)

    def calendar(self, project_id: str) -> list[Communication]:
        """沟通日历：按 scheduled_at 升序排列。"""
        items = self.list_communications(project_id)
        items.sort(key=lambda x: (x._meta("scheduled_at") or "9999-12-31", x.created_at or ""))
        return items

    def transition_communication(self, comm_id: str, transition_name: str,
                                 context: dict[str, Any] | None = None) -> Communication:
        """触发沟通记录状态迁移。"""
        item = self.get_communication(comm_id)
        if not item:
            raise ValueError(f"沟通记录不存在: {comm_id}")
        ctx = context or {}
        ctx.setdefault("communication_id", comm_id)
        ctx.setdefault("tenant_id", TenantContext.current())
        old = item.status
        _, new = self._sm.fire(item.status, transition_name, ctx)
        item.status = new
        self._repo.update(item)
        self._publish("communication.status_changed", item,
                      {"old_status": old, "new_status": new})
        if new == "completed":
            self._publish("communication.completed", item)
        if new == "escalated":
            self._publish("communication.escalated", item)
        return item

    def delete_communication(self, comm_id: str) -> bool:
        if not self.get_communication(comm_id):
            return False
        return self._repo.delete(comm_id)


def _cmd_create(args: Any, ctx: dict[str, Any]) -> None:
    m: CommunicationModule = ctx["module"]
    meta = {k: getattr(args, k, "") or "" for k in _META_FIELDS}
    r = m.create_communication(
        args.project_id, args.title,
        description=getattr(args, "description", "") or "",
        priority=getattr(args, "priority", "medium") or "medium",
        assignee_id=getattr(args, "assignee_id", "") or "",
        **meta,
    )
    print(f"✅ 沟通已创建: {r.title} (ID: {r.id})  状态: {r.status}")


def _cmd_list(args: Any, ctx: dict[str, Any]) -> None:
    m: CommunicationModule = ctx["module"]
    items = m.list_communications(args.project_id, status=getattr(args, "status", None))
    if not items:
        print("暂无沟通记录"); return
    print(f"{'ID':<36} {'标题':<20} {'状态':<12} {'优先级':<8} {'渠道':<12}")
    print("-" * 92)
    for it in items:
        print(f"{it.id:<36} {it.title:<20} {it.status:<12} {it.priority:<8} "
              f"{it._meta('channel', ''):<12}")


def _cmd_get(args: Any, ctx: dict[str, Any]) -> None:
    m: CommunicationModule = ctx["module"]
    r = m.get_communication(args.id)
    if not r:
        print(f"沟通记录不存在: {args.id}"); return
    print(f"ID: {r.id}\n标题: {r.title}\n状态: {r.status}\n优先级: {r.priority}")
    print(f"负责人: {r.assignee_id}\n项目: {r.project_id}")
    print(f"渠道: {r._meta('channel')}  受众: {r._meta('audience')}  "
          f"频率: {r._meta('frequency')}")
    print(f"消息类型: {r._meta('message_type')}  计划时间: {r._meta('scheduled_at')}")


def _cmd_transition(args: Any, ctx: dict[str, Any]) -> None:
    m: CommunicationModule = ctx["module"]
    try:
        r = m.transition_communication(args.id, args.transition)
        print(f"✅ 状态已迁移: {r.title} → {r.status}")
    except ValueError as e:
        print(f"❌ 迁移失败: {e}")


def _cmd_delete(args: Any, ctx: dict[str, Any]) -> None:
    m: CommunicationModule = ctx["module"]
    if m.delete_communication(args.id):
        print(f"✅ 沟通已删除: {args.id}")
    else:
        print(f"沟通记录不存在: {args.id}")


def _cmd_calendar(args: Any, ctx: dict[str, Any]) -> None:
    m: CommunicationModule = ctx["module"]
    items = m.calendar(args.project_id)
    if not items:
        print("暂无沟通计划"); return
    print(f"{'计划时间':<20} {'标题':<20} {'状态':<12} {'渠道':<12} {'负责人':<16}")
    print("-" * 80)
    for it in items:
        sched = it._meta("scheduled_at") or "—"
        print(f"{sched:<20} {it.title:<20} {it.status:<12} "
              f"{it._meta('channel',''):<12} {it.assignee_id:<16}")


manifest = ModuleManifest(
    name="communication", version="1.2.0",
    description="沟通管理模块 — 生命周期状态机 + 事件驱动 + 沟通日历",
    dependencies=["project"], tables=["work_items"],
    commands=[
        CommandDef("communication create", "创建沟通记录", _cmd_create, [
            {"flags": ["--project-id"], "required": True, "help": "项目 ID"},
            {"flags": ["--title"], "required": True, "help": "沟通标题"},
            {"flags": ["--description"], "default": "", "help": "沟通描述"},
            {"flags": ["--priority"], "default": "medium", "help": "优先级 (low/medium/high)"},
            {"flags": ["--assignee-id"], "help": "负责人 ID"},
            {"flags": ["--channel"], "help": "沟通渠道 (email/slack/meeting 等)"},
            {"flags": ["--audience"], "help": "受众 (stakeholders/team/client 等)"},
            {"flags": ["--frequency"], "help": "频率 (daily/weekly/biweekly/on-demand 等)"},
            {"flags": ["--message-type"], "help": "消息类型 (status/alert/report 等)"},
            {"flags": ["--scheduled-at"], "help": "计划时间 (ISO 格式)"},
        ]),
        CommandDef("communication list", "列出项目下的沟通记录", _cmd_list, [
            {"flags": ["--project-id"], "required": True, "help": "项目 ID"},
            {"flags": ["--status"], "help": "按状态过滤"},
        ]),
        CommandDef("communication get", "查看沟通详情", _cmd_get, [
            {"flags": ["--id"], "required": True, "help": "沟通记录 ID"},
        ]),
        CommandDef("communication transition", "触发沟通状态迁移", _cmd_transition, [
            {"flags": ["--id"], "required": True, "help": "沟通记录 ID"},
            {"flags": ["--transition"], "required": True,
             "help": "迁移名 (start/complete/cancel/escalate/deescalate)"},
        ]),
        CommandDef("communication delete", "删除沟通记录", _cmd_delete, [
            {"flags": ["--id"], "required": True, "help": "沟通记录 ID"},
        ]),
        CommandDef("communication calendar", "沟通日历（按计划时间排序）", _cmd_calendar, [
            {"flags": ["--project-id"], "required": True, "help": "项目 ID"},
        ]),
    ],
)


def _factory(m: ModuleManifest) -> CommunicationModule:
    return CommunicationModule(m)
