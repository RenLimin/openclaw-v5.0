"""quality 模块 — 质量管理

数据存储：work_items 表，type='quality'
状态机：identified → in_review → passed / failed
        failed → in_review（重新评审）
        passed → verified（terminal）
        closed（terminal，可从 identified 直接关闭）
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


@migration("1.2.2")
def upgrade_1_2_2(conn):
    """为 quality 类型 work_items 添加部分索引。"""
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_work_items_type_quality "
        "ON work_items(type) WHERE type='quality'"
    )


@dataclass
class Quality(BaseModel):
    """质量记录模型（work_items, type='quality'）。

    metadata 存储 defect_count / review_score / test_pass_rate 等质量专有字段。
    """
    project_id: str = ""
    title: str = ""
    description: str = ""
    status: str = "identified"
    priority: str = "medium"
    assignee_id: str = ""
    type: str = "quality"
    metadata: str = ""
    __tablename__ = "work_items"

    # -- metadata 辅助 --------------------------------------------------

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

    # -- 质量专有字段 ----------------------------------------------------

    @property
    def defect_count(self) -> int:
        return self._meta("defect_count", 0)

    @defect_count.setter
    def defect_count(self, v: int) -> None:
        self._set_meta("defect_count", v)

    @property
    def review_score(self) -> float:
        return self._meta("review_score", 0.0)

    @review_score.setter
    def review_score(self, v: float) -> None:
        self._set_meta("review_score", v)

    @property
    def test_pass_rate(self) -> float:
        return self._meta("test_pass_rate", 0.0)

    @test_pass_rate.setter
    def test_pass_rate(self, v: float) -> None:
        self._set_meta("test_pass_rate", v)


def _build_state_machine() -> StateMachine:
    """构建质量记录生命周期状态机。"""
    sm = StateMachine(name="quality", description="质量记录生命周期状态机")
    sm.add_state(State("identified", "todo", is_start=True, description="已识别"))
    sm.add_state(State("in_review", "in_progress", description="评审中"))
    sm.add_state(State("passed", "done", description="通过"))
    sm.add_state(State("failed", "blocked", description="未通过"))
    sm.add_state(State("verified", "done", is_terminal=True, description="已验证"))
    sm.add_state(State("closed", "cancelled", is_terminal=True, description="已关闭"))
    for n, f, t in [
        ("start_review", "identified", "in_review"),
        ("pass", "in_review", "passed"),
        ("fail", "in_review", "failed"),
        ("re_review", "failed", "in_review"),
        ("verify", "passed", "verified"),
        ("close", "identified", "closed"),
    ]:
        sm.add_transition(Transition(n, f, t))
    return sm


class QualityModule(BaseModule):
    """质量管理模块：状态机 + 事件 + CLI + 统计。"""

    def initialize(self, db: Database, config: dict[str, Any], container: Any) -> None:
        self._db = db
        self._config = config
        self._container = container
        self._repo: Repository[Quality] = Repository(db, Quality, "work_items")
        self._sm = _build_state_machine()
        if hasattr(container, "_state_machine_engine"):
            container._state_machine_engine.register("quality", self._sm)

    def on_ready(self, container: Any) -> None:
        bus = self._bus(container)
        if bus:
            bus.subscribe("project.cancelled", self._on_project_cancelled)

    # -- 内部 --------------------------------------------------------------

    def _bus(self, container: Any) -> Any:
        return getattr(container, "_event_bus", None)

    def _publish(self, name: str, item: Quality, extra: dict[str, Any] | None = None) -> None:
        bus = self._bus(self._container) if self._container else None
        if not bus:
            return
        payload = {
            "quality_id": item.id,
            "project_id": item.project_id,
            "title": item.title,
            "status": item.status,
            "tenant_id": item.tenant_id,
        }
        if extra:
            payload.update(extra)
        bus.publish(
            name=name, payload=payload, source="quality",
            entity_type="quality", entity_id=item.id,
        )

    # -- 事件处理 ----------------------------------------------------------

    def _on_project_cancelled(self, event: Event) -> None:
        """项目取消 → 关闭项目下所有非终态质量记录。"""
        pid = event.payload.get("project_id", "")
        if not pid:
            return
        terminal = {"verified", "closed"}
        for it in self._repo.list(project_id=pid, type="quality"):
            if it.status in terminal:
                continue
            try:
                if it.status == "identified":
                    self._sm.fire(it.status, "close",
                                  {"quality_id": it.id, "reason": "project_cancelled"})
                    old = it.status
                    it.status = "closed"
                    self._repo.update(it)
                    self._publish("quality.status_changed", it,
                                  {"old_status": old, "new_status": "closed"})
            except Exception:
                pass

    # -- 业务方法 ----------------------------------------------------------

    def create_quality(self, project_id: str, title: str, description: str = "",
                       priority: str = "medium", assignee_id: str = "") -> Quality:
        """创建质量记录。"""
        item = Quality(
            id=str(uuid.uuid4()), tenant_id=TenantContext.current(),
            project_id=project_id, title=title, description=description,
            status="identified", priority=priority,
            assignee_id=assignee_id, type="quality",
        )
        self._repo.add(item)
        self._publish("quality.created", item)
        return item

    def get_quality(self, quality_id: str) -> Optional[Quality]:
        item = self._repo.get(quality_id)
        return item if item and item.type == "quality" else None

    def list_qualities(self, project_id: str, status: str | None = None) -> list[Quality]:
        filters: dict[str, Any] = {"project_id": project_id, "type": "quality"}
        if status:
            filters["status"] = status
        return self._repo.list(**filters)

    def transition_quality(self, quality_id: str, transition_name: str,
                           context: dict[str, Any] | None = None) -> Quality:
        """触发质量记录状态迁移。"""
        item = self.get_quality(quality_id)
        if not item:
            raise ValueError(f"质量记录不存在: {quality_id}")
        ctx = context or {}
        ctx.setdefault("quality_id", quality_id)
        ctx.setdefault("tenant_id", TenantContext.current())
        old = item.status
        _, new = self._sm.fire(item.status, transition_name, ctx)
        item.status = new
        self._repo.update(item)
        self._publish("quality.status_changed", item,
                      {"old_status": old, "new_status": new})
        if new == "passed":
            self._publish("quality.passed", item)
        if new == "failed":
            self._publish("quality.failed", item)
        return item

    def delete_quality(self, quality_id: str) -> bool:
        if not self.get_quality(quality_id):
            return False
        return self._repo.delete(quality_id)

    def get_metrics(self, project_id: str) -> dict[str, Any]:
        """质量统计：总数、各状态数、缺陷总数、平均通过率等。"""
        items = self._repo.list(project_id=project_id, type="quality")
        total = len(items)
        by_status: dict[str, int] = {}
        total_defects = 0
        pass_rates: list[float] = []
        for it in items:
            by_status[it.status] = by_status.get(it.status, 0) + 1
            total_defects += it.defect_count
            if it.test_pass_rate > 0:
                pass_rates.append(it.test_pass_rate)
        avg_pass_rate = (sum(pass_rates) / len(pass_rates)) if pass_rates else 0.0
        return {
            "project_id": project_id,
            "total": total,
            "by_status": by_status,
            "total_defects": total_defects,
            "avg_pass_rate": round(avg_pass_rate, 2),
            "passed_count": by_status.get("passed", 0) + by_status.get("verified", 0),
            "failed_count": by_status.get("failed", 0),
        }


# -- CLI -------------------------------------------------------------------

def _cmd_create(args: Any, ctx: dict[str, Any]) -> None:
    m: QualityModule = ctx["module"]
    r = m.create_quality(
        args.project_id, args.title,
        description=getattr(args, "description", "") or "",
        priority=getattr(args, "priority", "medium") or "medium",
        assignee_id=getattr(args, "assignee_id", "") or "",
    )
    print(f"✅ 质量记录已创建: {r.title} (ID: {r.id})  状态: {r.status}")


def _cmd_list(args: Any, ctx: dict[str, Any]) -> None:
    m: QualityModule = ctx["module"]
    items = m.list_qualities(args.project_id, status=getattr(args, "status", None))
    if not items:
        print("暂无质量记录")
        return
    print(f"{'ID':<36} {'标题':<20} {'状态':<12} {'优先级':<8}")
    print("-" * 76)
    for it in items:
        print(f"{it.id:<36} {it.title:<20} {it.status:<12} {it.priority:<8}")


def _cmd_get(args: Any, ctx: dict[str, Any]) -> None:
    m: QualityModule = ctx["module"]
    q = m.get_quality(args.id)
    if not q:
        print(f"质量记录不存在: {args.id}")
        return
    print(f"ID: {q.id}\n标题: {q.title}\n状态: {q.status}\n优先级: {q.priority}")
    print(f"负责人: {q.assignee_id}\n项目: {q.project_id}")
    print(f"缺陷数: {q.defect_count}  评审得分: {q.review_score}  测试通过率: {q.test_pass_rate}%")


def _cmd_transition(args: Any, ctx: dict[str, Any]) -> None:
    m: QualityModule = ctx["module"]
    try:
        r = m.transition_quality(args.id, args.transition)
        print(f"✅ 状态已迁移: {r.title} → {r.status}")
    except ValueError as e:
        print(f"❌ 迁移失败: {e}")


def _cmd_delete(args: Any, ctx: dict[str, Any]) -> None:
    m: QualityModule = ctx["module"]
    if m.delete_quality(args.id):
        print(f"✅ 质量记录已删除: {args.id}")
    else:
        print(f"质量记录不存在: {args.id}")


def _cmd_metrics(args: Any, ctx: dict[str, Any]) -> None:
    m: QualityModule = ctx["module"]
    metrics = m.get_metrics(args.project_id)
    print(f"📊 项目质量统计 (项目 ID: {metrics['project_id']})")
    print(f"  质量记录总数:   {metrics['total']}")
    print(f"  通过/已验证:    {metrics['passed_count']}")
    print(f"  未通过:         {metrics['failed_count']}")
    print(f"  缺陷总数:       {metrics['total_defects']}")
    print(f"  平均测试通过率: {metrics['avg_pass_rate']}%")
    print(f"  各状态分布:")
    for s, c in metrics["by_status"].items():
        print(f"    {s:<12} {c}")


# -- Manifest --------------------------------------------------------------

manifest = ModuleManifest(
    name="quality", version="1.0.0",
    description="质量管理模块 — 生命周期状态机 + 事件驱动 + 质量统计",
    dependencies=["project"], tables=["work_items"],
    commands=[
        CommandDef("quality create", "创建质量记录", _cmd_create, [
            {"flags": ["--project-id"], "required": True, "help": "项目 ID"},
            {"flags": ["--title"], "required": True, "help": "质量记录标题"},
            {"flags": ["--description"], "default": "", "help": "质量记录描述"},
            {"flags": ["--priority"], "default": "medium",
             "help": "优先级 (low/medium/high)"},
            {"flags": ["--assignee-id"], "help": "负责人 ID"},
        ]),
        CommandDef("quality list", "列出项目下的质量记录", _cmd_list, [
            {"flags": ["--project-id"], "required": True, "help": "项目 ID"},
            {"flags": ["--status"], "help": "按状态过滤"},
        ]),
        CommandDef("quality get", "查看质量记录详情", _cmd_get, [
            {"flags": ["--id"], "required": True, "help": "质量记录 ID"},
        ]),
        CommandDef("quality transition", "触发质量记录状态迁移", _cmd_transition, [
            {"flags": ["--id"], "required": True, "help": "质量记录 ID"},
            {"flags": ["--transition"], "required": True,
             "help": "迁移名 (start_review/pass/fail/re_review/verify/close)"},
        ]),
        CommandDef("quality delete", "删除质量记录", _cmd_delete, [
            {"flags": ["--id"], "required": True, "help": "质量记录 ID"},
        ]),
        CommandDef("quality metrics", "查看项目质量统计", _cmd_metrics, [
            {"flags": ["--project-id"], "required": True, "help": "项目 ID"},
        ]),
    ],
)


def _factory(m: ModuleManifest) -> QualityModule:
    return QualityModule(m)
