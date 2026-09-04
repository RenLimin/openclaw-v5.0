"""issue 模块 — 问题管理

数据存储：work_items 表，type='issue'
状态机：open → investigating → resolving → resolved
        附加：reopened、closed(terminal)
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


@migration("1.3.1")
def upgrade_1_3_1(conn):
    """issue 模块迁移：添加 type='issue' 部分索引。"""
    conn.execute("CREATE INDEX IF NOT EXISTS idx_work_items_type_issue ON work_items(type) WHERE type='issue'")


@dataclass
class Issue(BaseModel):
    """问题模型（work_items, type='issue'）。metadata 存储 severity/category/root_cause 等。"""
    project_id: str = ""
    title: str = ""
    description: str = ""
    status: str = "open"
    priority: str = "medium"
    assignee_id: str = ""
    due_date: str = ""
    type: str = "issue"
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
    def severity(self) -> str:
        return self._meta("severity", "medium")

    @severity.setter
    def severity(self, v: str) -> None:
        self._set_meta("severity", v)

    @property
    def category(self) -> str:
        return self._meta("category", "")

    @category.setter
    def category(self, v: str) -> None:
        self._set_meta("category", v)

    @property
    def root_cause(self) -> str:
        return self._meta("root_cause", "")

    @root_cause.setter
    def root_cause(self, v: str) -> None:
        self._set_meta("root_cause", v)


def _build_state_machine() -> StateMachine:
    """构建问题生命周期状态机。"""
    sm = StateMachine(name="issue", description="问题生命周期状态机")
    sm.add_state(State("open", "todo", is_start=True, description="待处理"))
    sm.add_state(State("investigating", "in_progress", description="调查中"))
    sm.add_state(State("resolving", "in_progress", description="解决中"))
    sm.add_state(State("resolved", "done", is_terminal=True, description="已解决"))
    sm.add_state(State("reopened", "in_progress", description="重新打开"))
    sm.add_state(State("closed", "cancelled", is_terminal=True, description="已关闭"))
    for n, f, t in [
        ("investigate", "open", "investigating"),
        ("resolve", "investigating", "resolving"),
        ("verify", "resolving", "resolved"),
        ("reopen", "resolved", "reopened"),
        ("close", "open", "closed"),
        ("close_reopened", "reopened", "closed"),
        ("resolve_again", "reopened", "resolving"),
    ]:
        sm.add_transition(Transition(n, f, t))
    return sm


class IssueModule(BaseModule):
    """问题模块：状态机 + 事件 + CLI。"""

    def initialize(self, db: Database, config: dict[str, Any], container: Any) -> None:
        self._db = db
        self._config = config
        self._container = container
        self._repo: Repository[Issue] = Repository(db, Issue, "work_items")
        self._sm = _build_state_machine()
        if hasattr(container, "_state_machine_engine"):
            container._state_machine_engine.register("issue", self._sm)

    def on_ready(self, container: Any) -> None:
        bus = self._bus(container)
        if bus:
            bus.subscribe("project.cancelled", self._on_project_cancelled)

    def _bus(self, container: Any) -> Any:
        return getattr(container, "_event_bus", None)

    def _publish(self, name: str, item: Issue, extra: dict[str, Any] | None = None) -> None:
        bus = self._bus(self._container) if self._container else None
        if not bus:
            return
        payload = {"issue_id": item.id, "project_id": item.project_id,
                   "title": item.title, "status": item.status, "tenant_id": item.tenant_id}
        if extra:
            payload.update(extra)
        bus.publish(name=name, payload=payload, source="issue",
                    entity_type="issue", entity_id=item.id)

    def _on_project_cancelled(self, event: Event) -> None:
        """项目取消 → 关闭项目下所有非终态问题。"""
        pid = event.payload.get("project_id", "")
        if not pid:
            return
        terminal = {"resolved", "closed"}
        for it in self._repo.list(project_id=pid, type="issue"):
            if it.status in terminal:
                continue
            try:
                old = it.status
                if it.status == "reopened":
                    self._sm.fire(it.status, "close_reopened", {"issue_id": it.id})
                    it.status = "closed"
                else:
                    self._sm.fire(it.status, "close", {"issue_id": it.id})
                    it.status = "closed"
                self._repo.update(it)
                self._publish("issue.status_changed", it, {"old_status": old, "new_status": "closed"})
            except Exception:
                pass

    def create_issue(self, project_id: str, title: str, description: str = "",
                     priority: str = "medium", assignee_id: str = "") -> Issue:
        """创建问题。"""
        item = Issue(id=str(uuid.uuid4()), tenant_id=TenantContext.current(),
                     project_id=project_id, title=title, description=description,
                     status="open", priority=priority, assignee_id=assignee_id, type="issue")
        self._repo.add(item)
        self._publish("issue.created", item)
        return item

    def get_issue(self, issue_id: str) -> Optional[Issue]:
        item = self._repo.get(issue_id)
        return item if item and item.type == "issue" else None

    def list_issues(self, project_id: str, status: str | None = None) -> list[Issue]:
        filters: dict[str, Any] = {"project_id": project_id, "type": "issue"}
        if status:
            filters["status"] = status
        return self._repo.list(**filters)

    def transition_issue(self, issue_id: str, transition_name: str,
                         context: dict[str, Any] | None = None) -> Issue:
        """触发问题状态迁移。"""
        item = self.get_issue(issue_id)
        if not item:
            raise ValueError(f"问题不存在: {issue_id}")
        ctx = context or {}
        ctx.setdefault("issue_id", issue_id)
        ctx.setdefault("tenant_id", TenantContext.current())
        old = item.status
        _, new = self._sm.fire(item.status, transition_name, ctx)
        item.status = new
        self._repo.update(item)
        self._publish("issue.status_changed", item, {"old_status": old, "new_status": new})
        if new == "resolved":
            self._publish("issue.resolved", item)
        return item

    def delete_issue(self, issue_id: str) -> bool:
        if not self.get_issue(issue_id):
            return False
        return self._repo.delete(issue_id)

    def triage(self, project_id: str) -> dict[str, list[Issue]]:
        """分诊视图：按严重性分组。"""
        result: dict[str, list[Issue]] = {}
        for it in self.list_issues(project_id):
            sev = it.severity
            result.setdefault(sev, []).append(it)
        return result


# -- CLI -------------------------------------------------------------------

def _cmd_create(args: Any, ctx: dict[str, Any]) -> None:
    m: IssueModule = ctx["module"]
    r = m.create_issue(args.project_id, args.title,
                       priority=getattr(args, "priority", "medium") or "medium",
                       assignee_id=getattr(args, "assignee_id", "") or "")
    print(f"✅ 问题已创建: {r.title} (ID: {r.id})  状态: {r.status}")


def _cmd_list(args: Any, ctx: dict[str, Any]) -> None:
    m: IssueModule = ctx["module"]
    items = m.list_issues(args.project_id, status=getattr(args, "status", None))
    if not items:
        print("暂无问题"); return
    print(f"{'ID':<36} {'标题':<20} {'状态':<12} {'优先级':<8} {'严重性'}")
    print("-" * 82)
    for it in items:
        print(f"{it.id:<36} {it.title:<20} {it.status:<12} {it.priority:<8} {it.severity}")


def _cmd_get(args: Any, ctx: dict[str, Any]) -> None:
    m: IssueModule = ctx["module"]
    r = m.get_issue(args.id)
    if not r:
        print(f"问题不存在: {args.id}"); return
    print(f"ID: {r.id}\n标题: {r.title}\n状态: {r.status}\n优先级: {r.priority}")
    print(f"严重性: {r.severity}\n类别: {r.category or '-'}\n根因: {r.root_cause or '-'}")
    print(f"负责人: {r.assignee_id or '-'}\n项目: {r.project_id}")


def _cmd_transition(args: Any, ctx: dict[str, Any]) -> None:
    m: IssueModule = ctx["module"]
    try:
        r = m.transition_issue(args.id, args.transition)
        print(f"✅ 状态已迁移: {r.title} → {r.status}")
    except (ValueError, PermissionError) as e:
        print(f"❌ 迁移失败: {e}")


def _cmd_delete(args: Any, ctx: dict[str, Any]) -> None:
    m: IssueModule = ctx["module"]
    if m.delete_issue(args.id):
        print(f"✅ 问题已删除: {args.id}")
    else:
        print(f"问题不存在: {args.id}")


def _cmd_triage(args: Any, ctx: dict[str, Any]) -> None:
    m: IssueModule = ctx["module"]
    triage = m.triage(args.project_id)
    if not triage:
        print("暂无问题"); return
    for sev in ["critical", "high", "medium", "low"]:
        items = triage.get(sev, [])
        if items:
            print(f"\n[{sev}] ({len(items)})")
            for it in items:
                print(f"  {it.title} ({it.status})")


# -- Manifest --------------------------------------------------------------

manifest = ModuleManifest(
    name="issue", version="1.0.0",
    description="问题管理模块 — 分诊 + 生命周期状态机 + 事件驱动",
    dependencies=["project"], tables=["work_items"],
    commands=[
        CommandDef("issue create", "创建问题", _cmd_create, [
            {"flags": ["--project-id"], "required": True, "help": "项目 ID"},
            {"flags": ["--title"], "required": True, "help": "问题标题"},
            {"flags": ["--priority"], "default": "medium", "help": "优先级"},
            {"flags": ["--assignee-id"], "help": "负责人 ID"},
        ]),
        CommandDef("issue list", "列出问题", _cmd_list, [
            {"flags": ["--project-id"], "required": True, "help": "项目 ID"},
            {"flags": ["--status"], "help": "按状态过滤"},
        ]),
        CommandDef("issue get", "查看问题详情", _cmd_get, [
            {"flags": ["--id"], "required": True, "help": "问题 ID"},
        ]),
        CommandDef("issue transition", "触发状态迁移", _cmd_transition, [
            {"flags": ["--id"], "required": True, "help": "问题 ID"},
            {"flags": ["--transition"], "required": True,
             "help": "迁移名 (investigate/resolve/verify/reopen/close)"},
        ]),
        CommandDef("issue delete", "删除问题", _cmd_delete, [
            {"flags": ["--id"], "required": True, "help": "问题 ID"},
        ]),
        CommandDef("issue triage", "分诊视图", _cmd_triage, [
            {"flags": ["--project-id"], "required": True, "help": "项目 ID"},
        ]),
    ],
)


def _factory(m: ModuleManifest) -> IssueModule:
    return IssueModule(m)
