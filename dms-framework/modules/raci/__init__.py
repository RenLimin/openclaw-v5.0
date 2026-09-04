"""modules/raci — RACI 持久化模块（Phase 2）。
基于内存引擎 RACIEngine，提供 SQLite 持久化 + CLI。双写：先 DB 后内存。
发布 raci.assigned / raci.unassigned / raci.conflict_detected；订阅 project.deleted。"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from core.database import BaseModel, Database, Repository
from core.event_bus import Event, EventBus
from core.module import BaseModule, CommandDef, ModuleManifest
from core.raci import RACI_ROLES, Assignment, Conflict, Gap, RACIEngine
from core.saas import TenantContext


@dataclass
class ResponsibilityAssignment(BaseModel):
    """RACI 分配持久化模型，对应 responsibility_assignments 表。"""
    project_id: str = ""
    work_item_id: str | None = None
    member_id: str = ""
    capability: str = ""
    raci_role: str = ""
    role_template: str | None = None
    __tablename__ = "responsibility_assignments"

    def to_assignment(self) -> Assignment:
        return Assignment(
            project_id=self.project_id, member_id=self.member_id,
            capability=self.capability, raci_role=self.raci_role,
            work_item_id=self.work_item_id or None,
            role_template=self.role_template or None,
            tenant_id=self.tenant_id,
        )

    @classmethod
    def from_assignment(cls, a: Assignment) -> "ResponsibilityAssignment":
        return cls(
            id=str(uuid.uuid4()), tenant_id=a.tenant_id,
            project_id=a.project_id, work_item_id=a.work_item_id or None,
            member_id=a.member_id, capability=a.capability,
            raci_role=a.raci_role, role_template=a.role_template or "",
        )


class RACIModule(BaseModule):
    """RACI 模块：持久化的 RACI 分配管理。

    - 内存 RACIEngine 负责计算（冲突、覆盖、矩阵）
    - Repository 负责持久化到 responsibility_assignments 表
    - 双写策略：先写 DB，再更新内存引擎
    """

    def __init__(self, manifest: ModuleManifest) -> None:
        super().__init__(manifest)
        self._db: Database | None = None
        self._config: dict[str, Any] = {}
        self._container: Any = None
        self._repo: Repository[ResponsibilityAssignment] | None = None
        self._engine: RACIEngine | None = None

    def initialize(self, db: Any, config: dict[str, Any], container: Any) -> None:
        """初始化 Repository + 内存引擎，从 DB 加载已有分配。"""
        self._db, self._config, self._container = db, config, container
        self._repo = Repository(db, ResponsibilityAssignment, "responsibility_assignments")
        self._engine = RACIEngine()
        self._load_from_db()

    def on_ready(self, container: Any) -> None:
        """订阅 project.deleted 事件，项目删除时清理其 RACI 分配。"""
        bus = self._get_event_bus()
        if bus:
            bus.subscribe("project.deleted", self._on_project_deleted)

    def _get_event_bus(self) -> EventBus | None:
        if hasattr(self._container, "_event_bus"):
            return self._container._event_bus
        return None

    def _load_from_db(self) -> None:
        assert self._repo and self._engine
        for entity in self._repo.list():
            self._engine.assign(entity.to_assignment())

    def _publish(self, name: str, payload: dict[str, Any], entity_id: str = "") -> None:
        bus = self._get_event_bus()
        if bus:
            bus.publish(name=name, payload=payload, source="raci",
                        entity_type="assignment", entity_id=entity_id)

    def _find_existing(self, a: Assignment) -> ResponsibilityAssignment | None:
        assert self._repo
        results = self._repo.list(
            project_id=a.project_id, work_item_id=a.work_item_id or None,
            member_id=a.member_id, capability=a.capability, raci_role=a.raci_role,
        )
        return results[0] if results else None

    def _on_project_deleted(self, event: Event) -> None:
        pid = event.payload.get("project_id")
        if not pid or not self._repo or not self._engine:
            return
        for entity in self._repo.list(project_id=pid):
            self._repo.delete(entity.id)
            self._engine.unassign(entity.to_assignment())

    # -- 核心 API ----------------------------------------------------------

    def assign(self, assignment: Assignment) -> Assignment:
        """分配 RACI 角色。先写 DB，再更新内存，发布 assigned + 冲突事件。"""
        assert self._repo and self._engine
        if assignment.tenant_id == "system":
            assignment.tenant_id = TenantContext.current()
        if self._find_existing(assignment):
            self._engine.assign(assignment)
            return assignment
        entity = ResponsibilityAssignment.from_assignment(assignment)
        entity.tenant_id = assignment.tenant_id
        self._repo.add(entity)
        self._engine.assign(assignment)
        self._publish("raci.assigned", {
            "project_id": assignment.project_id, "member_id": assignment.member_id,
            "capability": assignment.capability, "raci_role": assignment.raci_role,
            "work_item_id": assignment.work_item_id, "tenant_id": assignment.tenant_id,
        }, entity_id=entity.id)
        conflicts = self._engine.check_conflicts(assignment.project_id)
        if conflicts:
            self._publish("raci.conflict_detected", {
                "project_id": assignment.project_id, "tenant_id": assignment.tenant_id,
                "conflicts": [{"type": c.type, "work_item_id": c.work_item_id,
                               "capability": c.capability, "description": c.description,
                               "details": c.details} for c in conflicts],
            })
        return assignment

    def unassign(self, assignment: Assignment) -> bool:
        """取消 RACI 分配。先删 DB，再更新内存，发布 unassigned 事件。"""
        assert self._repo and self._engine
        existing = self._find_existing(assignment)
        if not existing:
            return False
        self._repo.delete(existing.id)
        self._engine.unassign(assignment)
        self._publish("raci.unassigned", {
            "project_id": assignment.project_id, "member_id": assignment.member_id,
            "capability": assignment.capability, "raci_role": assignment.raci_role,
            "work_item_id": assignment.work_item_id, "tenant_id": assignment.tenant_id,
        }, entity_id=existing.id)
        return True

    def get_assignments(self, project_id: str, work_item_id: str | None = None,
                        capability: str | None = None, member_id: str | None = None,
                        raci_role: str | None = None) -> list[Assignment]:
        """查询分配（走内存引擎，高性能）。"""
        assert self._engine
        return self._engine.get_assignments(
            project_id=project_id, work_item_id=work_item_id,
            capability=capability, member_id=member_id, raci_role=raci_role,
        )

    def check_conflicts(self, project_id: str) -> list[Conflict]:
        """检查项目的 RACI 冲突。"""
        assert self._engine
        return self._engine.check_conflicts(project_id)

    def validate_coverage(self, project_id: str, work_item_id: str | None = None,
                          required_capabilities: list[str] | None = None) -> list[Gap]:
        """验证 RACI 覆盖。"""
        assert self._engine
        return self._engine.validate_coverage(project_id, work_item_id, required_capabilities)

    def get_responsibility_matrix(self, project_id: str) -> dict[str, Any]:
        """生成 RACI 责任矩阵。"""
        assert self._engine
        return self._engine.get_responsibility_matrix(project_id)


# ---------------------------------------------------------------------------
# CLI 命令处理器
# ---------------------------------------------------------------------------

def _mod(ns: Any, ctx: dict[str, Any]) -> RACIModule:
    return ctx["container"].get("raci")  # type: ignore[no-any-return]


def cmd_assign(ns: Any, ctx: dict[str, Any]) -> None:
    """分配 RACI 角色。"""
    a = Assignment(project_id=ns.project_id, member_id=ns.member_id,
                   capability=ns.capability, raci_role=ns.role,
                   work_item_id=getattr(ns, "work_item_id", None))
    _mod(ns, ctx).assign(a)
    print(f"✅ 已分配: {ns.member_id} → {ns.capability} ({ns.role}) @ {ns.project_id}")


def cmd_list(ns: Any, ctx: dict[str, Any]) -> None:
    """列出项目的 RACI 分配。"""
    m = _mod(ns, ctx)
    items = m.get_assignments(project_id=ns.project_id,
                              work_item_id=getattr(ns, "work_item_id", None))
    if not items:
        print("（无分配记录）")
        return
    print(f"项目 {ns.project_id} 的 RACI 分配（共 {len(items)} 条）：")
    for a in items:
        wi = a.work_item_id or "(项目级)"
        print(f"  {a.member_id:20s} {a.capability:28s} {a.raci_role}  {wi}")


def cmd_matrix(ns: Any, ctx: dict[str, Any]) -> None:
    """显示 RACI 责任矩阵。"""
    matrix = _mod(ns, ctx).get_responsibility_matrix(ns.project_id)
    print(f"RACI 矩阵 — 项目 {ns.project_id}")
    for wi_key, caps in matrix["work_items"].items():
        print(f"\n  工作项: {wi_key}")
        for cap, roles in caps.items():
            parts = [f"{r}={','.join(mem)}" for r, mem in roles.items() if mem]
            print(f"    {cap:28s}  {' | '.join(parts)}")


def cmd_conflicts(ns: Any, ctx: dict[str, Any]) -> None:
    """检查 RACI 冲突。"""
    conflicts = _mod(ns, ctx).check_conflicts(ns.project_id)
    if not conflicts:
        print("✅ 未检测到冲突")
        return
    print(f"⚠️  检测到 {len(conflicts)} 个冲突：")
    for c in conflicts:
        wi = c.work_item_id or "(项目级)"
        print(f"  [{c.type}] {wi} / {c.capability}: {c.description}")


def cmd_coverage(ns: Any, ctx: dict[str, Any]) -> None:
    """验证 RACI 覆盖。"""
    gaps = _mod(ns, ctx).validate_coverage(ns.project_id)
    if not gaps:
        print("✅ 所有能力均已覆盖 R/A 角色")
        return
    print(f"⚠️  发现 {len(gaps)} 个覆盖缺口：")
    for g in gaps:
        wi = g.work_item_id or "(项目级)"
        print(f"  {wi} / {g.capability}: 缺少 {', '.join(g.missing_roles)}")


def cmd_unassign(ns: Any, ctx: dict[str, Any]) -> None:
    """取消 RACI 分配。"""
    m = _mod(ns, ctx)
    a = Assignment(project_id=ns.project_id, member_id=ns.member_id,
                   capability=ns.capability, raci_role=ns.role,
                   work_item_id=getattr(ns, "work_item_id", None))
    if m.unassign(a):
        print(f"✅ 已取消: {ns.member_id} → {ns.capability} ({ns.role}) @ {ns.project_id}")
    else:
        print("❌ 未找到分配记录")


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

_R = sorted(RACI_ROLES)
_arg = lambda f, h, **kw: {"flags": [f], "help": h, **kw}  # helper, 压缩命令定义

manifest = ModuleManifest(
    name="raci",
    version="1.0.0",
    description="RACI 责任分配模块（持久化版）— 管理项目成员在各能力上的 R/A/C/I 角色",
    dependencies=["project"],
    tables=["responsibility_assignments"],
    commands=[
        CommandDef(name="raci assign", help="分配 RACI 角色", handler=cmd_assign, arguments=[
            _arg("--project-id", "项目 ID", required=True),
            _arg("--member-id", "成员 ID", required=True),
            _arg("--capability", "能力原子名", required=True),
            _arg("--role", "RACI 角色 (R/A/C/I)", required=True, choices=_R),
            _arg("--work-item-id", "工作项 ID（可选）"),
        ]),
        CommandDef(name="raci list", help="列出项目的 RACI 分配", handler=cmd_list, arguments=[
            _arg("--project-id", "项目 ID", required=True),
            _arg("--work-item-id", "按工作项过滤"),
        ]),
        CommandDef(name="raci matrix", help="显示 RACI 责任矩阵", handler=cmd_matrix, arguments=[
            _arg("--project-id", "项目 ID", required=True),
        ]),
        CommandDef(name="raci conflicts", help="检查项目的 RACI 冲突", handler=cmd_conflicts, arguments=[
            _arg("--project-id", "项目 ID", required=True),
        ]),
        CommandDef(name="raci coverage", help="验证 RACI 覆盖情况", handler=cmd_coverage, arguments=[
            _arg("--project-id", "项目 ID", required=True),
        ]),
        CommandDef(name="raci unassign", help="取消 RACI 分配", handler=cmd_unassign, arguments=[
            _arg("--project-id", "项目 ID", required=True),
            _arg("--member-id", "成员 ID", required=True),
            _arg("--capability", "能力原子名", required=True),
            _arg("--role", "RACI 角色 (R/A/C/I)", required=True, choices=_R),
            _arg("--work-item-id", "工作项 ID（可选）"),
        ]),
    ],
)


def _factory(m: ModuleManifest) -> RACIModule:
    return RACIModule(m)
