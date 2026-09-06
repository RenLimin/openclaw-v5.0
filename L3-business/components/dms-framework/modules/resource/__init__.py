"""resource 模块 — 资源管理

数据存储：work_items 表，type='resource'
状态机：requested → allocated → released（terminal）
        requested → cancelled（terminal）
        allocated → reallocated → allocated
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


@migration("1.2.5")
def upgrade_1_2_5(conn):
    """为 resource 类型 work_items 添加部分索引。"""
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_work_items_type_resource "
        "ON work_items(type) WHERE type='resource'"
    )


@dataclass
class Resource(BaseModel):
    """资源模型（work_items, type='resource'）。metadata 存储 resource_type/capacity/allocated/cost_per_unit。"""
    project_id: str = ""
    title: str = ""
    description: str = ""
    status: str = "requested"
    priority: str = "medium"
    assignee_id: str = ""
    type: str = "resource"
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
    def resource_type(self) -> str:
        return self._meta("resource_type", "general")

    @resource_type.setter
    def resource_type(self, v: str) -> None:
        self._set_meta("resource_type", v)

    @property
    def capacity(self) -> float:
        return self._meta("capacity", 0.0)

    @capacity.setter
    def capacity(self, v: float) -> None:
        self._set_meta("capacity", v)

    @property
    def allocated(self) -> float:
        return self._meta("allocated", 0.0)

    @allocated.setter
    def allocated(self, v: float) -> None:
        self._set_meta("allocated", v)

    @property
    def cost_per_unit(self) -> float:
        return self._meta("cost_per_unit", 0.0)

    @cost_per_unit.setter
    def cost_per_unit(self, v: float) -> None:
        self._set_meta("cost_per_unit", v)


def _build_state_machine() -> StateMachine:
    """构建资源分配生命周期状态机。"""
    sm = StateMachine(name="resource", description="资源分配生命周期状态机")
    sm.add_state(State("requested", "todo", is_start=True, description="已申请"))
    sm.add_state(State("allocated", "in_progress", description="已分配"))
    sm.add_state(State("reallocated", "in_progress", description="重新分配"))
    sm.add_state(State("released", "done", is_terminal=True, description="已释放"))
    sm.add_state(State("cancelled", "cancelled", is_terminal=True, description="已取消"))
    for n, f, t in [
        ("allocate", "requested", "allocated"),
        ("release", "allocated", "released"),
        ("cancel", "requested", "cancelled"),
        ("reallocate", "allocated", "reallocated"),
        ("confirm", "reallocated", "allocated"),
    ]:
        sm.add_transition(Transition(n, f, t))
    return sm


class ResourceModule(BaseModule):
    """资源模块：状态机 + 事件 + CLI。"""

    def initialize(self, db: Database, config: dict[str, Any], container: Any) -> None:
        self._db = db
        self._config = config
        self._container = container
        self._repo: Repository[Resource] = Repository(db, Resource, "work_items")
        self._sm = _build_state_machine()
        if hasattr(container, "_state_machine_engine"):
            container._state_machine_engine.register("resource", self._sm)

    def on_ready(self, container: Any) -> None:
        bus = self._bus(container)
        if bus:
            bus.subscribe("project.cancelled", self._on_project_cancelled)

    def _bus(self, container: Any) -> Any:
        return getattr(container, "_event_bus", None)

    def _publish(self, name: str, item: Resource, extra: dict[str, Any] | None = None) -> None:
        bus = self._bus(self._container) if self._container else None
        if not bus:
            return
        payload = {"resource_id": item.id, "project_id": item.project_id,
                   "title": item.title, "status": item.status, "tenant_id": item.tenant_id}
        if extra:
            payload.update(extra)
        bus.publish(name=name, payload=payload, source="resource",
                    entity_type="resource", entity_id=item.id)

    def _on_project_cancelled(self, event: Event) -> None:
        """项目取消 → 释放项目下所有已分配资源。"""
        pid = event.payload.get("project_id", "")
        if not pid:
            return
        for it in self._repo.list(project_id=pid, type="resource"):
            if it.status != "allocated":
                continue
            try:
                _, new = self._sm.fire(it.status, "release",
                                       {"resource_id": it.id, "reason": "project_cancelled"})
                old, it.status = it.status, new
                self._repo.update(it)
                self._publish("resource.status_changed", it,
                              {"old_status": old, "new_status": new})
                self._publish("resource.released", it, {"reason": "project_cancelled"})
            except Exception:
                pass

    def create_resource(self, project_id: str, title: str, description: str = "",
                        priority: str = "medium", assignee_id: str = "") -> Resource:
        """创建资源申请。"""
        item = Resource(id=str(uuid.uuid4()), tenant_id=TenantContext.current(),
                        project_id=project_id, title=title, description=description,
                        status="requested", priority=priority,
                        assignee_id=assignee_id, type="resource")
        self._repo.add(item)
        self._publish("resource.created", item)
        return item

    def get_resource(self, resource_id: str) -> Optional[Resource]:
        item = self._repo.get(resource_id)
        return item if item and item.type == "resource" else None

    def list_resources(self, project_id: str, status: str | None = None) -> list[Resource]:
        filters: dict[str, Any] = {"project_id": project_id, "type": "resource"}
        if status:
            filters["status"] = status
        return self._repo.list(**filters)

    def transition_resource(self, resource_id: str, transition_name: str,
                            context: dict[str, Any] | None = None) -> Resource:
        """触发资源状态迁移。"""
        item = self.get_resource(resource_id)
        if not item:
            raise ValueError(f"资源不存在: {resource_id}")
        ctx = context or {}
        ctx.setdefault("resource_id", resource_id)
        ctx.setdefault("tenant_id", TenantContext.current())
        old = item.status
        _, new = self._sm.fire(item.status, transition_name, ctx)
        item.status = new
        self._repo.update(item)
        self._publish("resource.status_changed", item, {"old_status": old, "new_status": new})
        if new == "allocated":
            self._publish("resource.allocated", item)
        if new == "released":
            self._publish("resource.released", item)
        return item

    def delete_resource(self, resource_id: str) -> bool:
        if not self.get_resource(resource_id):
            return False
        return self._repo.delete(resource_id)

    def allocation_overview(self, project_id: str) -> dict[str, Any]:
        """资源分配概览：按状态统计、容量、利用率、预估成本。"""
        items = self.list_resources(project_id)
        by_status: dict[str, int] = {}
        cap = alloc = cost = 0.0
        for it in items:
            by_status[it.status] = by_status.get(it.status, 0) + 1
            cap += it.capacity
            alloc += it.allocated
            cost += it.allocated * it.cost_per_unit
        util = (alloc / cap * 100.0) if cap > 0 else 0.0
        return {"project_id": project_id, "total": len(items),
                "by_status": by_status, "total_capacity": cap,
                "total_allocated": alloc, "utilization_rate": round(util, 2),
                "estimated_cost": round(cost, 2)}


# -- CLI -------------------------------------------------------------------

def _cmd_create(args: Any, ctx: dict[str, Any]) -> None:
    m: ResourceModule = ctx["module"]
    r = m.create_resource(args.project_id, args.title,
                          description=getattr(args, "description", "") or "",
                          priority=getattr(args, "priority", "medium") or "medium",
                          assignee_id=getattr(args, "assignee_id", "") or "")
    print(f"✅ 资源已创建: {r.title} (ID: {r.id})  状态: {r.status}")


def _cmd_list(args: Any, ctx: dict[str, Any]) -> None:
    m: ResourceModule = ctx["module"]
    items = m.list_resources(args.project_id, status=getattr(args, "status", None))
    if not items:
        print("暂无资源"); return
    print(f"{'ID':<36} {'名称':<20} {'状态':<12} {'优先级':<8} {'类型':<12}")
    print("-" * 92)
    for it in items:
        print(f"{it.id:<36} {it.title:<20} {it.status:<12} {it.priority:<8} {it.resource_type:<12}")


def _cmd_get(args: Any, ctx: dict[str, Any]) -> None:
    m: ResourceModule = ctx["module"]
    r = m.get_resource(args.id)
    if not r:
        print(f"资源不存在: {args.id}"); return
    print(f"ID: {r.id}\n名称: {r.title}\n状态: {r.status}\n优先级: {r.priority}")
    print(f"负责人: {r.assignee_id}\n项目: {r.project_id}\n类型: {r.resource_type}")
    print(f"容量: {r.capacity}  已分配: {r.allocated}  单位成本: {r.cost_per_unit}")


def _cmd_transition(args: Any, ctx: dict[str, Any]) -> None:
    m: ResourceModule = ctx["module"]
    try:
        r = m.transition_resource(args.id, args.transition)
        print(f"✅ 状态已迁移: {r.title} → {r.status}")
    except ValueError as e:
        print(f"❌ 迁移失败: {e}")


def _cmd_delete(args: Any, ctx: dict[str, Any]) -> None:
    m: ResourceModule = ctx["module"]
    print(f"✅ 资源已删除: {args.id}" if m.delete_resource(args.id) else f"资源不存在: {args.id}")


def _cmd_allocation(args: Any, ctx: dict[str, Any]) -> None:
    m: ResourceModule = ctx["module"]
    ov = m.allocation_overview(args.project_id)
    print(f"📊 项目 {ov['project_id']} 资源分配概览")
    print(f"   总数: {ov['total']}  状态分布: {ov['by_status']}")
    print(f"   容量: {ov['total_capacity']}  已分配: {ov['total_allocated']}")
    print(f"   利用率: {ov['utilization_rate']}%  成本: {ov['estimated_cost']}")


# -- Manifest --------------------------------------------------------------

manifest = ModuleManifest(
    name="resource", version="1.0.0",
    description="资源管理模块 — 分配生命周期状态机 + 事件驱动",
    dependencies=["project"], tables=["work_items"],
    commands=[
        CommandDef("resource create", "创建资源申请", _cmd_create, [
            {"flags": ["--project-id"], "required": True, "help": "项目 ID"},
            {"flags": ["--title"], "required": True, "help": "资源名称"},
            {"flags": ["--description"], "default": "", "help": "资源描述"},
            {"flags": ["--priority"], "default": "medium", "help": "优先级"},
            {"flags": ["--assignee-id"], "help": "负责人 ID"},
        ]),
        CommandDef("resource list", "列出项目下的资源", _cmd_list, [
            {"flags": ["--project-id"], "required": True, "help": "项目 ID"},
            {"flags": ["--status"], "help": "按状态过滤"},
        ]),
        CommandDef("resource get", "查看资源详情", _cmd_get, [
            {"flags": ["--id"], "required": True, "help": "资源 ID"},
        ]),
        CommandDef("resource transition", "触发资源状态迁移", _cmd_transition, [
            {"flags": ["--id"], "required": True, "help": "资源 ID"},
            {"flags": ["--transition"], "required": True,
             "help": "迁移名 (allocate/release/cancel/reallocate/confirm)"},
        ]),
        CommandDef("resource delete", "删除资源", _cmd_delete, [
            {"flags": ["--id"], "required": True, "help": "资源 ID"},
        ]),
        CommandDef("resource allocation", "资源分配概览", _cmd_allocation, [
            {"flags": ["--project-id"], "required": True, "help": "项目 ID"},
        ]),
    ],
)


def _factory(m: ModuleManifest) -> ResourceModule:
    return ResourceModule(m)
