"""
deliverable 模块 — 交付物生命周期管理
存储于 work_items 表(type='deliverable')，状态机 draft→in_review→accepted/rejected/withdrawn
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
class Deliverable(BaseModel):
    """交付物模型，基于 work_items 表。parent_id(里程碑关联)存于 metadata JSON。"""
    project_id: str = ""
    title: str = ""
    description: str = ""
    status: str = "draft"
    priority: str = "medium"
    assignee_id: str = ""
    due_date: str = ""
    type: str = "deliverable"
    metadata: str = ""
    __tablename__ = "work_items"

    @property
    def parent_id(self) -> str:
        try:
            return json.loads(self.metadata).get("parent_id", "") if self.metadata else ""
        except (json.JSONDecodeError, AttributeError):
            return ""

    @parent_id.setter
    def parent_id(self, value: str) -> None:
        data = {}
        if self.metadata:
            try: data = json.loads(self.metadata)
            except (json.JSONDecodeError, AttributeError): data = {}
        data["parent_id"] = value
        self.metadata = json.dumps(data, ensure_ascii=False)


def _build_state_machine() -> StateMachine:
    """构建交付物生命周期状态机。"""
    sm = StateMachine(name="deliverable", description="交付物生命周期")
    sm.add_state(State("draft", "todo", is_start=True, description="草稿"))
    sm.add_state(State("in_review", "in_progress", description="评审中"))
    sm.add_state(State("accepted", "done", is_terminal=True, description="已验收"))
    sm.add_state(State("rejected", "blocked", description="被驳回"))
    sm.add_state(State("withdrawn", "cancelled", is_terminal=True, description="已撤回"))
    sm.add_transition(Transition("submit", "draft", "in_review", description="提交评审"))
    sm.add_transition(Transition("approve", "in_review", "accepted", description="验收通过"))
    sm.add_transition(Transition("reject", "in_review", "rejected", description="驳回"))
    sm.add_transition(Transition("revise", "rejected", "in_review", description="修改重提"))
    sm.add_transition(Transition("withdraw", "draft", "withdrawn", description="撤回"))
    return sm


class DeliverableModule(BaseModule):
    """交付物模块：CRUD + 状态机 + 事件 + CLI。"""

    def initialize(self, db: Database, config: dict[str, Any], container: Any) -> None:
        """注册状态机 + 初始化仓储。"""
        self._db, self._config, self._container = db, config, container
        self._repo: Repository[Deliverable] = Repository(db, Deliverable, "work_items")
        self._sm = _build_state_machine()
        if hasattr(container, "_state_machine_engine"):
            container._state_machine_engine.register("deliverable", self._sm)

    def on_ready(self, container: Any) -> None:
        """订阅 project.cancelled → 撤回项目下草稿交付物。"""
        bus = self._bus()
        if bus:
            bus.subscribe("project.cancelled", self._on_project_cancelled)

    def _bus(self) -> Any:
        return getattr(self._container, "_event_bus", None) if self._container else None

    def _publish(self, name: str, item: Deliverable, extra: dict | None = None) -> None:
        bus = self._bus()
        if not bus: return
        payload = {"deliverable_id": item.id, "project_id": item.project_id,
                   "title": item.title, "status": item.status, "tenant_id": item.tenant_id}
        if extra: payload.update(extra)
        bus.publish(name, payload, source="deliverable",
                    entity_type="deliverable", entity_id=item.id)

    def _on_project_cancelled(self, event: Event) -> None:
        pid = event.payload.get("project_id", "")
        if not pid: return
        for item in self._repo.list(project_id=pid, type="deliverable"):
            if item.status == "draft":
                try:
                    self._sm.fire(item.status, "withdraw",
                                  {"deliverable_id": item.id, "reason": "project_cancelled"})
                    old = item.status
                    item.status = "withdrawn"
                    self._repo.update(item)
                    self._publish("deliverable.status_changed", item,
                                  {"old_status": old, "new_status": "withdrawn"})
                except Exception: pass

    # -- 业务方法 --
    def create_deliverable(self, project_id: str, title: str, **kw: Any) -> Deliverable:
        item = Deliverable(
            id=str(uuid.uuid4()), tenant_id=TenantContext.current(),
            project_id=project_id, title=title,
            description=kw.get("description", ""), status="draft",
            priority=kw.get("priority", "medium"),
            assignee_id=kw.get("assignee_id", ""),
            due_date=kw.get("due_date", ""), type="deliverable",
        )
        if kw.get("parent_id"): item.parent_id = kw["parent_id"]
        self._repo.add(item)
        self._publish("deliverable.created", item)
        return item

    def get_deliverable(self, deliverable_id: str) -> Optional[Deliverable]:
        item = self._repo.get(deliverable_id)
        return item if item and item.type == "deliverable" else None

    def list_deliverables(self, project_id: str, status: str | None = None) -> list[Deliverable]:
        filters: dict[str, Any] = {"project_id": project_id, "type": "deliverable"}
        if status: filters["status"] = status
        return self._repo.list(**filters)

    def transition_deliverable(self, deliverable_id: str, transition_name: str,
                               context: dict | None = None) -> Deliverable:
        item = self.get_deliverable(deliverable_id)
        if not item: raise ValueError(f"交付物不存在: {deliverable_id}")
        ctx = context or {}
        ctx.setdefault("deliverable_id", deliverable_id)
        ctx.setdefault("tenant_id", TenantContext.current())
        old = item.status
        _, new_status = self._sm.fire(item.status, transition_name, ctx)
        item.status = new_status
        self._repo.update(item)
        self._publish("deliverable.status_changed", item,
                      {"old_status": old, "new_status": new_status})
        if new_status == "accepted": self._publish("deliverable.accepted", item)
        elif new_status == "rejected": self._publish("deliverable.rejected", item)
        return item

    def delete_deliverable(self, deliverable_id: str) -> bool:
        return self._repo.delete(deliverable_id) if self.get_deliverable(deliverable_id) else False


# -- CLI --
def _cmd_create(args: Any, ctx: dict) -> None:
    m: DeliverableModule = ctx["module"]
    it = m.create_deliverable(args.project_id, args.title,
        description=getattr(args, "description", "") or "",
        due_date=getattr(args, "due_date", "") or "",
        priority=getattr(args, "priority", "medium") or "medium")
    print(f"✅ 交付物已创建: {it.title} (ID: {it.id})  状态: {it.status}")

def _cmd_list(args: Any, ctx: dict) -> None:
    m: DeliverableModule = ctx["module"]
    items = m.list_deliverables(args.project_id, getattr(args, "status", None))
    if not items: print("暂无交付物"); return
    print(f"{'ID':<36} {'标题':<20} {'状态':<12} {'优先级':<8} {'截止日期'}")
    print("-" * 88)
    for it in items:
        print(f"{it.id:<36} {it.title:<20} {it.status:<12} {it.priority:<8} {it.due_date}")

def _cmd_get(args: Any, ctx: dict) -> None:
    m: DeliverableModule = ctx["module"]
    it = m.get_deliverable(args.id)
    if not it: print(f"交付物不存在: {args.id}"); return
    for k in ["id", "title", "description", "status", "priority",
              "due_date", "assignee_id", "project_id", "created_at"]:
        print(f"  {k}: {getattr(it, k, '')}")

def _cmd_transition(args: Any, ctx: dict) -> None:
    m: DeliverableModule = ctx["module"]
    try:
        it = m.transition_deliverable(args.id, args.transition)
        print(f"✅ 状态已迁移: {it.title} → {it.status}")
    except ValueError as e: print(f"❌ 迁移失败: {e}")

def _cmd_delete(args: Any, ctx: dict) -> None:
    m: DeliverableModule = ctx["module"]
    print(f"✅ 交付物已删除: {args.id}" if m.delete_deliverable(args.id)
          else f"交付物不存在: {args.id}")


# -- Manifest --
manifest = ModuleManifest(
    name="deliverable", version="1.0.0",
    description="交付物管理模块 — 生命周期状态机 + 事件驱动",
    dependencies=["project"], tables=["work_items"],
    commands=[
        CommandDef("deliverable create", "创建交付物", _cmd_create, [
            {"flags": ["--project-id"], "required": True, "help": "项目 ID"},
            {"flags": ["--title"], "required": True, "help": "交付物标题"},
            {"flags": ["--description"], "help": "描述"},
            {"flags": ["--due-date"], "help": "截止日期"},
            {"flags": ["--priority"], "default": "medium", "help": "优先级"},
        ]),
        CommandDef("deliverable list", "列出项目下交付物", _cmd_list, [
            {"flags": ["--project-id"], "required": True, "help": "项目 ID"},
            {"flags": ["--status"], "help": "按状态过滤"},
        ]),
        CommandDef("deliverable get", "查看交付物详情", _cmd_get, [
            {"flags": ["--id"], "required": True, "help": "交付物 ID"},
        ]),
        CommandDef("deliverable transition", "触发状态迁移", _cmd_transition, [
            {"flags": ["--id"], "required": True, "help": "交付物 ID"},
            {"flags": ["--transition"], "required": True, "help": "迁移名"},
        ]),
        CommandDef("deliverable delete", "删除交付物", _cmd_delete, [
            {"flags": ["--id"], "required": True, "help": "交付物 ID"},
        ]),
    ],
)

def _factory(m: ModuleManifest) -> DeliverableModule:
    return DeliverableModule(m)
