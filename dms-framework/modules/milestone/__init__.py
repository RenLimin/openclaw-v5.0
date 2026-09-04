"""
milestone 模块 — 里程碑生命周期管理

里程碑（Milestone）是项目中的关键节点，用于追踪项目进度。
里程碑数据存储在 work_items 表中，type='milestone'。

状态机：pending → in_progress → achieved (terminal)
        额外：missed (terminal), deferred (terminal)
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Optional

from core.module import BaseModule, ModuleManifest, CommandDef
from core.database import BaseModel, Repository, Database
from core.state_machine import StateMachine, State, Transition
from core.event_bus import Event
from core.saas import TenantContext


# ---------------------------------------------------------------------------
# Milestone 数据模型
# ---------------------------------------------------------------------------

@dataclass
class Milestone(BaseModel):
    """里程碑模型，基于 work_items 表，type='milestone'。

    字段说明：
    - project_id: 所属项目 ID
    - type: 类型，固定为 'milestone'
    - title: 里程碑标题
    - description: 里程碑描述
    - status: 当前状态（由状态机管理）
    - priority: 优先级（low/medium/high）
    - assignee_id: 负责人 ID
    - due_date: 截止日期
    - metadata: 扩展元数据（JSON 字符串）
    """

    project_id: str = ""
    type: str = "milestone"
    title: str = ""
    description: str = ""
    status: str = "pending"
    priority: str = "medium"
    assignee_id: str = ""
    due_date: str = ""
    completed_at: str = ""
    metadata: str = ""

    __tablename__ = "work_items"


# ---------------------------------------------------------------------------
# 状态机构建
# ---------------------------------------------------------------------------

def _build_state_machine() -> StateMachine:
    """构建里程碑生命周期状态机。

    状态流转：
        pending ──start──▶ in_progress ──achieve──▶ achieved (terminal)
            │                  │
            │ defer            │ miss
            ▼                  ▼
        deferred (terminal)  missed (terminal)
            │
            │ restart
            ▼
        in_progress
    """
    sm = StateMachine(name="milestone", description="里程碑生命周期状态机")

    # 状态定义
    sm.add_state(State(
        name="pending", category="todo", is_start=True,
        description="待开始，里程碑尚未启动",
    ))
    sm.add_state(State(
        name="in_progress", category="in_progress",
        description="进行中，里程碑正在推进",
    ))
    sm.add_state(State(
        name="achieved", category="done", is_terminal=True,
        description="已达成，里程碑正常完成",
    ))
    sm.add_state(State(
        name="missed", category="cancelled", is_terminal=True,
        description="已延期错过，里程碑未能按时达成",
    ))
    sm.add_state(State(
        name="deferred", category="blocked", is_terminal=True,
        description="已延期，里程碑被推迟",
    ))

    # 迁移定义
    sm.add_transition(Transition(
        name="start", from_state="pending", to_state="in_progress",
        description="启动里程碑",
    ))
    sm.add_transition(Transition(
        name="achieve", from_state="in_progress", to_state="achieved",
        description="达成里程碑",
    ))
    sm.add_transition(Transition(
        name="miss", from_state="in_progress", to_state="missed",
        description="错过里程碑",
    ))
    sm.add_transition(Transition(
        name="defer", from_state="pending", to_state="deferred",
        description="延期里程碑",
    ))
    sm.add_transition(Transition(
        name="restart", from_state="deferred", to_state="in_progress",
        description="重新启动延期的里程碑",
    ))

    return sm


# ---------------------------------------------------------------------------
# MilestoneModule
# ---------------------------------------------------------------------------

class MilestoneModule(BaseModule):
    """里程碑模块。

    职责：
    1. 注册里程碑状态机到状态机引擎
    2. 发布里程碑相关事件（created / status_changed / achieved / missed）
    3. 订阅 project.cancelled 事件，自动取消项目下所有里程碑
    4. 提供里程碑 CRUD 与状态流转业务方法
    5. 提供 CLI 命令
    """

    def initialize(self, db: Database, config: dict[str, Any], container: Any) -> None:
        """初始化：注册状态机 + 初始化仓储 + 注册事件监听。"""
        self._db = db
        self._config = config
        self._container = container
        self._repo: Repository[Milestone] = Repository(db, Milestone, "work_items")

        # 注册状态机
        sm = _build_state_machine()
        self._sm = sm
        if hasattr(container, "_state_machine_engine"):
            container._state_machine_engine.register("milestone", sm)

    def on_ready(self, container: Any) -> None:
        """所有模块就绪后：订阅 project.cancelled 事件。"""
        event_bus = self._get_event_bus()
        if event_bus:
            event_bus.subscribe("project.cancelled", self._on_project_cancelled)

    # -- 业务方法 ----------------------------------------------------------

    def create_milestone(
        self,
        project_id: str,
        title: str,
        description: str = "",
        due_date: str = "",
        priority: str = "medium",
        assignee_id: str = "",
    ) -> Milestone:
        """创建里程碑，初始状态为 pending。"""
        milestone = Milestone(
            id=str(uuid.uuid4()),
            tenant_id=TenantContext.current(),
            project_id=project_id,
            type="milestone",
            title=title,
            description=description,
            status="pending",
            priority=priority,
            assignee_id=assignee_id,
            due_date=due_date,
        )
        self._repo.add(milestone)
        self._publish_event("milestone.created", milestone)
        return milestone

    def get_milestone(self, milestone_id: str) -> Optional[Milestone]:
        """根据 ID 获取里程碑。"""
        entity = self._repo.get(milestone_id)
        if entity and entity.type == "milestone":
            return entity
        return None

    def list_milestones(self, project_id: str) -> list[Milestone]:
        """列出指定项目下的所有里程碑。"""
        items = self._repo.list(project_id=project_id, type="milestone")
        return items

    def transition_milestone(
        self,
        milestone_id: str,
        transition_name: str,
        context: dict[str, Any] | None = None,
    ) -> Milestone:
        """触发里程碑状态迁移。"""
        milestone = self.get_milestone(milestone_id)
        if not milestone:
            raise ValueError(f"里程碑不存在: {milestone_id}")

        ctx = context or {}
        ctx.setdefault("milestone_id", milestone_id)
        ctx.setdefault("project_id", milestone.project_id)
        ctx.setdefault("tenant_id", TenantContext.current())

        old_status = milestone.status
        _, new_status = self._sm.fire(milestone.status, transition_name, ctx)
        milestone.status = new_status
        self._repo.update(milestone)

        # 发布事件
        self._publish_status_changed(milestone, old_status, new_status)
        if new_status == "achieved":
            self._publish_event("milestone.achieved", milestone)
        elif new_status == "missed":
            self._publish_event("milestone.missed", milestone)

        return milestone

    def delete_milestone(self, milestone_id: str) -> bool:
        """删除里程碑。"""
        return self._repo.delete(milestone_id)

    # -- 事件处理 ----------------------------------------------------------

    def _on_project_cancelled(self, event: Event) -> None:
        """项目取消时，将项目下所有里程碑设为 missed。"""
        project_id = event.payload.get("project_id", "")
        if not project_id:
            return

        # 切换到事件对应的租户上下文
        tenant_id = event.payload.get("tenant_id", TenantContext.current())
        with TenantContext.scope(tenant_id):
            milestones = self.list_milestones(project_id)
            for m in milestones:
                # 只有非终态的里程碑才迁移
                if m.status in ("pending", "in_progress"):
                    try:
                        transition = "miss" if m.status == "in_progress" else "defer"
                        self.transition_milestone(
                            m.id, transition,
                            context={"reason": "project_cancelled"},
                        )
                    except (ValueError, PermissionError):
                        # 迁移失败则跳过
                        continue

    # -- 事件发布 ----------------------------------------------------------

    def _get_event_bus(self) -> Any:
        """从容器中获取事件总线实例。"""
        if hasattr(self._container, "_event_bus"):
            return self._container._event_bus
        return None

    def _publish_event(self, event_name: str, milestone: Milestone) -> None:
        """发布里程碑事件。"""
        event_bus = self._get_event_bus()
        if not event_bus:
            return
        payload = {
            "milestone_id": milestone.id,
            "project_id": milestone.project_id,
            "title": milestone.title,
            "status": milestone.status,
            "tenant_id": milestone.tenant_id,
        }
        event_bus.publish(
            name=event_name,
            payload=payload,
            source="milestone",
            entity_type="milestone",
            entity_id=milestone.id,
        )

    def _publish_status_changed(
        self, milestone: Milestone, old_status: str, new_status: str
    ) -> None:
        """发布状态变更事件。"""
        event_bus = self._get_event_bus()
        if not event_bus:
            return
        payload = {
            "milestone_id": milestone.id,
            "project_id": milestone.project_id,
            "title": milestone.title,
            "old_status": old_status,
            "new_status": new_status,
            "tenant_id": milestone.tenant_id,
        }
        event_bus.publish(
            name="milestone.status_changed",
            payload=payload,
            source="milestone",
            entity_type="milestone",
            entity_id=milestone.id,
        )


# ---------------------------------------------------------------------------
# CLI 命令处理器
# ---------------------------------------------------------------------------

def _cmd_create(args: Any, context: dict[str, Any]) -> None:
    """创建里程碑。"""
    module: MilestoneModule = context["module"]
    milestone = module.create_milestone(
        project_id=args.project_id,
        title=args.title,
        due_date=getattr(args, "due_date", "") or "",
        priority=getattr(args, "priority", "medium") or "medium",
    )
    print(f"✅ 里程碑已创建: {milestone.title} (ID: {milestone.id})")
    print(f"   状态: {milestone.status}")


def _cmd_list(args: Any, context: dict[str, Any]) -> None:
    """列出项目下的里程碑。"""
    module: MilestoneModule = context["module"]
    milestones = module.list_milestones(project_id=args.project_id)
    if not milestones:
        print("暂无里程碑")
        return
    print(f"{'ID':<36} {'标题':<20} {'状态':<14} {'优先级':<8} {'截止日期':<12}")
    print("-" * 90)
    for m in milestones:
        print(f"{m.id:<36} {m.title:<20} {m.status:<14} {m.priority:<8} {m.due_date or '-':<12}")


def _cmd_get(args: Any, context: dict[str, Any]) -> None:
    """查看里程碑详情。"""
    module: MilestoneModule = context["module"]
    milestone = module.get_milestone(args.id)
    if not milestone:
        print(f"里程碑不存在: {args.id}")
        return
    print(f"  ID:          {milestone.id}")
    print(f"  项目ID:      {milestone.project_id}")
    print(f"  标题:        {milestone.title}")
    print(f"  描述:        {milestone.description}")
    print(f"  状态:        {milestone.status}")
    print(f"  优先级:      {milestone.priority}")
    print(f"  负责人:      {milestone.assignee_id or '-'}")
    print(f"  截止日期:    {milestone.due_date or '-'}")
    print(f"  创建时间:    {milestone.created_at}")
    print(f"  更新时间:    {milestone.updated_at}")


def _cmd_transition(args: Any, context: dict[str, Any]) -> None:
    """触发里程碑状态迁移。"""
    module: MilestoneModule = context["module"]
    try:
        milestone = module.transition_milestone(args.id, args.transition)
        print(f"✅ 状态已迁移: {milestone.title} → {milestone.status}")
    except (ValueError, PermissionError) as e:
        print(f"❌ 迁移失败: {e}")


def _cmd_delete(args: Any, context: dict[str, Any]) -> None:
    """删除里程碑。"""
    module: MilestoneModule = context["module"]
    if module.delete_milestone(args.id):
        print(f"✅ 里程碑已删除: {args.id}")
    else:
        print(f"里程碑不存在: {args.id}")


# ---------------------------------------------------------------------------
# Manifest + 导出
# ---------------------------------------------------------------------------

manifest = ModuleManifest(
    name="milestone",
    version="1.0.0",
    description="里程碑管理模块 — 生命周期状态机 + 事件驱动",
    dependencies=["project"],
    tables=["work_items"],
    commands=[
        CommandDef(
            name="milestone create",
            help="创建里程碑",
            handler=_cmd_create,
            arguments=[
                {"flags": ["--project-id"], "required": True, "help": "项目 ID"},
                {"flags": ["--title"], "required": True, "help": "里程碑标题"},
                {"flags": ["--due-date"], "help": "截止日期 (YYYY-MM-DD)"},
                {"flags": ["--priority"], "help": "优先级 (low/medium/high)"},
            ],
        ),
        CommandDef(
            name="milestone list",
            help="列出项目下的里程碑",
            handler=_cmd_list,
            arguments=[
                {"flags": ["--project-id"], "required": True, "help": "项目 ID"},
            ],
        ),
        CommandDef(
            name="milestone get",
            help="查看里程碑详情",
            handler=_cmd_get,
            arguments=[
                {"flags": ["--id"], "required": True, "help": "里程碑 ID"},
            ],
        ),
        CommandDef(
            name="milestone transition",
            help="触发里程碑状态迁移",
            handler=_cmd_transition,
            arguments=[
                {"flags": ["--id"], "required": True, "help": "里程碑 ID"},
                {"flags": ["--transition"], "required": True,
                 "help": "迁移名 (start/achieve/miss/defer/restart)"},
            ],
        ),
        CommandDef(
            name="milestone delete",
            help="删除里程碑",
            handler=_cmd_delete,
            arguments=[
                {"flags": ["--id"], "required": True, "help": "里程碑 ID"},
            ],
        ),
    ],
)


def _factory(m: ModuleManifest) -> MilestoneModule:
    return MilestoneModule(m)
