"""project 模块 — 项目生命周期管理。数据存储：projects 表。"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Optional

from core.module import BaseModule, ModuleManifest, CommandDef
from core.database import BaseModel, Repository, Database
from core.state_machine import StateMachine, State, Transition
from core.saas import TenantContext


# 可从任意非 terminal 状态取消
_CANCEL_FROM = ("planning", "in_progress", "on_hold", "review")


@dataclass
class Project(BaseModel):
    """项目模型，基于 projects 表。"""
    name: str = ""
    description: str = ""
    status: str = "planning"
    priority: str = "medium"
    start_date: str = ""
    end_date: str = ""
    proprietary_metadata: str = ""
    __tablename__ = "projects"


def _build_state_machine() -> StateMachine:
    """构建项目生命周期状态机。

    planning → in_progress → review → completed
    额外: on_hold, cancelled
    cancel 可从任意非 terminal 状态触发（内部按状态分别命名）。
    """
    sm = StateMachine(name="project", description="项目生命周期状态机")
    sm.add_state(State("planning", "todo", is_start=True, description="规划中"))
    sm.add_state(State("in_progress", "in_progress", description="进行中"))
    sm.add_state(State("on_hold", "blocked", description="暂停中"))
    sm.add_state(State("review", "in_progress", description="评审中"))
    sm.add_state(State("completed", "done", is_terminal=True, description="已完成"))
    sm.add_state(State("cancelled", "cancelled", is_terminal=True, description="已取消"))

    sm.add_transition(Transition("start", "planning", "in_progress", description="启动项目"))
    sm.add_transition(Transition("pause", "in_progress", "on_hold", description="暂停项目"))
    sm.add_transition(Transition("resume", "on_hold", "in_progress", description="恢复项目"))
    sm.add_transition(Transition("submit", "in_progress", "review", description="提交评审"))
    sm.add_transition(Transition("accept", "review", "completed", description="验收通过"))
    sm.add_transition(Transition("reject", "review", "in_progress", description="验收驳回"))
    for s in _CANCEL_FROM:
        sm.add_transition(Transition(f"cancel_{s}", s, "cancelled", description=f"从{s}取消"))
    return sm


def _resolve_transition(current_state: str, transition_name: str) -> str:
    """将外部迁移名映射为状态机内部名（处理 cancel 的多源状态）。"""
    if transition_name == "cancel" and current_state in _CANCEL_FROM:
        return f"cancel_{current_state}"
    return transition_name


class ProjectModule(BaseModule):
    """项目模块：CRUD + 状态机 + 事件发布 + CLI。"""

    def initialize(self, db: Database, config: dict[str, Any], container: Any) -> None:
        self._db = db
        self._config = config
        self._container = container
        self._repo: Repository[Project] = Repository(db, Project, "projects")
        self._sm = _build_state_machine()
        if hasattr(container, "_state_machine_engine") and container._state_machine_engine:
            container._state_machine_engine.register("project", self._sm)

    def on_ready(self, container: Any) -> None:
        """项目为基础模块，无跨模块订阅。"""
        pass

    # -- 业务方法 ----------------------------------------------------------

    def create_project(self, name: str, description: str = "",
                       priority: str = "medium", start_date: str = "",
                       end_date: str = "") -> Project:
        """创建项目，初始状态 planning。"""
        p = Project(
            id=str(uuid.uuid4()), tenant_id=TenantContext.current(),
            name=name, description=description, status="planning",
            priority=priority, start_date=start_date, end_date=end_date,
        )
        self._repo.add(p)
        self._publish("project.created", p)
        return p

    def get_project(self, project_id: str) -> Optional[Project]:
        return self._repo.get(project_id)

    def list_projects(
        self,
        status: str | None = None,
        search: str | None = None,
        sort_by: str | None = None,
        sort_order: str = "desc",
        offset: int = 0,
        limit: int | None = None,
    ) -> list[Project]:
        filters: dict[str, Any] = {}
        if status:
            filters["status"] = status
        return self._repo.list(
            search=search,
            sort_by=sort_by,
            sort_order=sort_order,
            offset=offset,
            limit=limit,
            **filters,
        )

    def transition_project(self, project_id: str, transition_name: str,
                           context: dict[str, Any] | None = None) -> Project:
        """触发状态迁移，支持 cancel 从任意非 terminal 状态。"""
        p = self.get_project(project_id)
        if not p:
            raise ValueError(f"项目不存在: {project_id}")
        ctx = context or {}
        ctx.setdefault("project_id", project_id)
        ctx.setdefault("tenant_id", TenantContext.current())
        internal = _resolve_transition(p.status, transition_name)
        old = p.status
        _, new = self._sm.fire(p.status, internal, ctx)
        p.status = new
        self._repo.update(p)
        self._publish("project.status_changed", p, {"old_status": old, "new_status": new})
        if new == "completed":
            self._publish("project.completed", p)
        elif new == "cancelled":
            self._publish("project.cancelled", p)
        return p

    def delete_project(self, project_id: str) -> bool:
        return self._repo.delete(project_id)

    # -- 内部方法 ----------------------------------------------------------

    def _event_bus(self) -> Any:
        if hasattr(self._container, "_event_bus"):
            return self._container._event_bus
        return None

    def _publish(self, event_name: str, p: Project, extra: dict[str, Any] | None = None) -> None:
        bus = self._event_bus()
        if not bus:
            return
        payload = {
            "project_id": p.id, "name": p.name, "status": p.status,
            "tenant_id": p.tenant_id,
        }
        if extra:
            payload.update(extra)
        bus.publish(event_name, payload, source="project",
                    entity_type="project", entity_id=p.id)


# -- CLI 命令 --------------------------------------------------------------

def _cmd_create(args: Any, ctx: dict[str, Any]) -> None:
    m: ProjectModule = ctx["module"]
    p = m.create_project(name=args.name,
                         description=getattr(args, "description", "") or "")
    print(f"✅ 项目已创建: {p.name} (ID: {p.id})\n   状态: {p.status}")


def _cmd_list(args: Any, ctx: dict[str, Any]) -> None:
    m: ProjectModule = ctx["module"]
    projects = m.list_projects(status=getattr(args, "status", None))
    if not projects:
        print("暂无项目")
        return
    print(f"{'ID':<36} {'名称':<20} {'状态':<14} {'优先级':<8}")
    print("-" * 78)
    for p in projects:
        print(f"{p.id:<36} {p.name:<20} {p.status:<14} {p.priority:<8}")


def _cmd_get(args: Any, ctx: dict[str, Any]) -> None:
    m: ProjectModule = ctx["module"]
    p = m.get_project(args.id)
    if not p:
        print(f"项目不存在: {args.id}")
        return
    print(f"  ID:          {p.id}")
    print(f"  名称:        {p.name}")
    print(f"  描述:        {p.description}")
    print(f"  状态:        {p.status}")
    print(f"  优先级:      {p.priority}")
    print(f"  开始日期:    {p.start_date or '-'}")
    print(f"  结束日期:    {p.end_date or '-'}")
    print(f"  创建时间:    {p.created_at}")
    print(f"  更新时间:    {p.updated_at}")


def _cmd_transition(args: Any, ctx: dict[str, Any]) -> None:
    m: ProjectModule = ctx["module"]
    try:
        p = m.transition_project(args.id, args.transition)
        print(f"✅ 状态已迁移: {p.name} → {p.status}")
    except (ValueError, PermissionError) as e:
        print(f"❌ 迁移失败: {e}")


def _cmd_delete(args: Any, ctx: dict[str, Any]) -> None:
    m: ProjectModule = ctx["module"]
    if m.delete_project(args.id):
        print(f"✅ 项目已删除: {args.id}")
    else:
        print(f"项目不存在: {args.id}")


# -- Manifest --------------------------------------------------------------

manifest = ModuleManifest(
    name="project",
    version="1.0.0",
    description="项目管理模块 — 生命周期状态机 + 事件驱动",
    dependencies=[],
    tables=["projects"],
    commands=[
        CommandDef("project create", "创建项目", _cmd_create, [
            {"flags": ["--name"], "required": True, "help": "项目名称"},
            {"flags": ["--description"], "help": "项目描述"},
        ]),
        CommandDef("project list", "列出项目", _cmd_list, [
            {"flags": ["--status"], "help": "按状态过滤"},
        ]),
        CommandDef("project get", "查看项目详情", _cmd_get, [
            {"flags": ["--id"], "required": True, "help": "项目 ID"},
        ]),
        CommandDef("project transition", "触发项目状态迁移", _cmd_transition, [
            {"flags": ["--id"], "required": True, "help": "项目 ID"},
            {"flags": ["--transition"], "required": True,
             "help": "迁移名 (start/pause/resume/submit/accept/reject/cancel)"},
        ]),
        CommandDef("project delete", "删除项目", _cmd_delete, [
            {"flags": ["--id"], "required": True, "help": "项目 ID"},
        ]),
    ],
)


def _factory(m: ModuleManifest) -> ProjectModule:
    return ProjectModule(m)
