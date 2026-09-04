"""task 模块 — 任务管理

数据存储：work_items 表，type='task'
状态机：backlog → todo → in_progress → done
        附加：blocked、cancelled(terminal)
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


@migration("1.3.0")
def upgrade_1_3_0(conn):
    """task 模块迁移：添加 type='task' 部分索引。"""
    conn.execute("CREATE INDEX IF NOT EXISTS idx_work_items_type_task ON work_items(type) WHERE type='task'")


@dataclass
class Task(BaseModel):
    """任务模型（work_items, type='task'）。metadata 存储 estimate_hours/actual_hours/tags 等。"""
    project_id: str = ""
    title: str = ""
    description: str = ""
    status: str = "backlog"
    priority: str = "medium"
    assignee_id: str = ""
    due_date: str = ""
    type: str = "task"
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
    def estimate_hours(self) -> float:
        return self._meta("estimate_hours", 0.0)

    @estimate_hours.setter
    def estimate_hours(self, v: float) -> None:
        self._set_meta("estimate_hours", v)

    @property
    def actual_hours(self) -> float:
        return self._meta("actual_hours", 0.0)

    @actual_hours.setter
    def actual_hours(self, v: float) -> None:
        self._set_meta("actual_hours", v)

    @property
    def tags(self) -> str:
        return self._meta("tags", "")

    @tags.setter
    def tags(self, v: str) -> None:
        self._set_meta("tags", v)


def _build_state_machine() -> StateMachine:
    """构建任务生命周期状态机。"""
    sm = StateMachine(name="task", description="任务生命周期状态机")
    sm.add_state(State("backlog", "todo", is_start=True, description="待办池"))
    sm.add_state(State("todo", "todo", description="待开始"))
    sm.add_state(State("in_progress", "in_progress", description="进行中"))
    sm.add_state(State("blocked", "blocked", description="已阻塞"))
    sm.add_state(State("done", "done", is_terminal=True, description="已完成"))
    sm.add_state(State("cancelled", "cancelled", is_terminal=True, description="已取消"))
    for n, f, t in [
        ("pull", "backlog", "todo"),
        ("start", "todo", "in_progress"),
        ("block", "in_progress", "blocked"),
        ("unblock", "blocked", "in_progress"),
        ("complete", "in_progress", "done"),
        ("cancel_todo", "todo", "cancelled"),
        ("cancel_backlog", "backlog", "cancelled"),
        ("cancel_in_progress", "in_progress", "cancelled"),
        ("cancel_blocked", "blocked", "cancelled"),
    ]:
        sm.add_transition(Transition(n, f, t))
    return sm


_CANCEL_FROM = ("backlog", "todo", "in_progress", "blocked")


def _resolve_transition(current_state: str, transition_name: str) -> str:
    """统一 cancel 迁移名。"""
    if transition_name == "cancel" and current_state in _CANCEL_FROM:
        return f"cancel_{current_state}"
    return transition_name


class TaskModule(BaseModule):
    """任务模块：状态机 + 事件 + CLI。"""

    def initialize(self, db: Database, config: dict[str, Any], container: Any) -> None:
        self._db = db
        self._config = config
        self._container = container
        self._repo: Repository[Task] = Repository(db, Task, "work_items")
        self._sm = _build_state_machine()
        if hasattr(container, "_state_machine_engine"):
            container._state_machine_engine.register("task", self._sm)

    def on_ready(self, container: Any) -> None:
        bus = self._bus(container)
        if bus:
            bus.subscribe("project.cancelled", self._on_project_cancelled)

    def _bus(self, container: Any) -> Any:
        return getattr(container, "_event_bus", None)

    def _publish(self, name: str, item: Task, extra: dict[str, Any] | None = None) -> None:
        bus = self._bus(self._container) if self._container else None
        if not bus:
            return
        payload = {"task_id": item.id, "project_id": item.project_id,
                   "title": item.title, "status": item.status, "tenant_id": item.tenant_id}
        if extra:
            payload.update(extra)
        bus.publish(name=name, payload=payload, source="task",
                    entity_type="task", entity_id=item.id)

    def _on_project_cancelled(self, event: Event) -> None:
        """项目取消 → 取消项目下所有非终态任务。"""
        pid = event.payload.get("project_id", "")
        if not pid:
            return
        terminal = {"done", "cancelled"}
        for it in self._repo.list(project_id=pid, type="task"):
            if it.status in terminal:
                continue
            try:
                internal = _resolve_transition(it.status, "cancel")
                if self._sm.can_transition(it.status, internal):
                    old = it.status
                    _, new = self._sm.fire(it.status, internal, {"task_id": it.id})
                    it.status = new
                    self._repo.update(it)
                    self._publish("task.status_changed", it, {"old_status": old, "new_status": new})
            except Exception:
                pass

    def create_task(self, project_id: str, title: str, description: str = "",
                    priority: str = "medium", assignee_id: str = "") -> Task:
        """创建任务。"""
        item = Task(id=str(uuid.uuid4()), tenant_id=TenantContext.current(),
                    project_id=project_id, title=title, description=description,
                    status="backlog", priority=priority, assignee_id=assignee_id, type="task")
        self._repo.add(item)
        self._publish("task.created", item)
        return item

    def get_task(self, task_id: str) -> Optional[Task]:
        item = self._repo.get(task_id)
        return item if item and item.type == "task" else None

    def list_tasks(self, project_id: str, status: str | None = None) -> list[Task]:
        filters: dict[str, Any] = {"project_id": project_id, "type": "task"}
        if status:
            filters["status"] = status
        return self._repo.list(**filters)

    def transition_task(self, task_id: str, transition_name: str,
                        context: dict[str, Any] | None = None) -> Task:
        """触发任务状态迁移。"""
        item = self.get_task(task_id)
        if not item:
            raise ValueError(f"任务不存在: {task_id}")
        ctx = context or {}
        ctx.setdefault("task_id", task_id)
        ctx.setdefault("tenant_id", TenantContext.current())
        internal = _resolve_transition(item.status, transition_name)
        old = item.status
        _, new = self._sm.fire(item.status, internal, ctx)
        item.status = new
        self._repo.update(item)
        self._publish("task.status_changed", item, {"old_status": old, "new_status": new})
        if new == "done":
            self._publish("task.completed", item)
        return item

    def delete_task(self, task_id: str) -> bool:
        if not self.get_task(task_id):
            return False
        return self._repo.delete(task_id)

    def board(self, project_id: str) -> dict[str, list[Task]]:
        """看板视图：按状态分组。"""
        result: dict[str, list[Task]] = {}
        for t in self.list_tasks(project_id):
            result.setdefault(t.status, []).append(t)
        return result


# -- CLI -------------------------------------------------------------------

def _cmd_create(args: Any, ctx: dict[str, Any]) -> None:
    m: TaskModule = ctx["module"]
    r = m.create_task(args.project_id, args.title,
                      priority=getattr(args, "priority", "medium") or "medium",
                      assignee_id=getattr(args, "assignee_id", "") or "")
    print(f"✅ 任务已创建: {r.title} (ID: {r.id})  状态: {r.status}")


def _cmd_list(args: Any, ctx: dict[str, Any]) -> None:
    m: TaskModule = ctx["module"]
    items = m.list_tasks(args.project_id, status=getattr(args, "status", None))
    if not items:
        print("暂无任务"); return
    print(f"{'ID':<36} {'标题':<20} {'状态':<12} {'优先级':<8} {'负责人'}")
    print("-" * 82)
    for it in items:
        print(f"{it.id:<36} {it.title:<20} {it.status:<12} {it.priority:<8} {it.assignee_id or '-'}")


def _cmd_get(args: Any, ctx: dict[str, Any]) -> None:
    m: TaskModule = ctx["module"]
    r = m.get_task(args.id)
    if not r:
        print(f"任务不存在: {args.id}"); return
    print(f"ID: {r.id}\n标题: {r.title}\n状态: {r.status}\n优先级: {r.priority}")
    print(f"负责人: {r.assignee_id or '-'}\n项目: {r.project_id}")
    print(f"预估/实际工时: {r.estimate_hours}h / {r.actual_hours}h  标签: {r.tags or '-'}")


def _cmd_transition(args: Any, ctx: dict[str, Any]) -> None:
    m: TaskModule = ctx["module"]
    try:
        r = m.transition_task(args.id, args.transition)
        print(f"✅ 状态已迁移: {r.title} → {r.status}")
    except (ValueError, PermissionError) as e:
        print(f"❌ 迁移失败: {e}")


def _cmd_delete(args: Any, ctx: dict[str, Any]) -> None:
    m: TaskModule = ctx["module"]
    if m.delete_task(args.id):
        print(f"✅ 任务已删除: {args.id}")
    else:
        print(f"任务不存在: {args.id}")


def _cmd_board(args: Any, ctx: dict[str, Any]) -> None:
    m: TaskModule = ctx["module"]
    board = m.board(args.project_id)
    if not board:
        print("暂无任务"); return
    for status in ["backlog", "todo", "in_progress", "blocked", "done", "cancelled"]:
        items = board.get(status, [])
        if items:
            print(f"\n[{status}] ({len(items)})")
            for it in items:
                assignee = f" @{it.assignee_id}" if it.assignee_id else ""
                print(f"  {it.title}{assignee}")


# -- Manifest --------------------------------------------------------------

manifest = ModuleManifest(
    name="task", version="1.0.0",
    description="任务管理模块 — 看板 + 生命周期状态机 + 事件驱动",
    dependencies=["project"], tables=["work_items"],
    commands=[
        CommandDef("task create", "创建任务", _cmd_create, [
            {"flags": ["--project-id"], "required": True, "help": "项目 ID"},
            {"flags": ["--title"], "required": True, "help": "任务标题"},
            {"flags": ["--priority"], "default": "medium", "help": "优先级"},
            {"flags": ["--assignee-id"], "help": "负责人 ID"},
        ]),
        CommandDef("task list", "列出任务", _cmd_list, [
            {"flags": ["--project-id"], "required": True, "help": "项目 ID"},
            {"flags": ["--status"], "help": "按状态过滤"},
        ]),
        CommandDef("task get", "查看任务详情", _cmd_get, [
            {"flags": ["--id"], "required": True, "help": "任务 ID"},
        ]),
        CommandDef("task transition", "触发状态迁移", _cmd_transition, [
            {"flags": ["--id"], "required": True, "help": "任务 ID"},
            {"flags": ["--transition"], "required": True,
             "help": "迁移名 (pull/start/block/unblock/complete/cancel)"},
        ]),
        CommandDef("task delete", "删除任务", _cmd_delete, [
            {"flags": ["--id"], "required": True, "help": "任务 ID"},
        ]),
        CommandDef("task board", "看板视图", _cmd_board, [
            {"flags": ["--project-id"], "required": True, "help": "项目 ID"},
        ]),
    ],
)


def _factory(m: ModuleManifest) -> TaskModule:
    return TaskModule(m)
