"""contract 模块 — 合同接口管理。

数据存储：work_items 表，type='contract'。metadata 存 contract_id/party/amount/terms/effective_date/expiry_date 等。
状态机：draft→pending_approval→active→fulfilled，含 rejected/disputed/terminated 分支。
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


@migration("1.2.1")
def upgrade_1_2_1(conn: Any) -> None:
    """v1.2.0：为 contract 类型 work_items 加部分索引。"""
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_work_items_type_contract "
        "ON work_items(type) WHERE type='contract'"
    )
    try:
        conn.commit()
    except Exception:
        pass


_META_FIELDS = ("contract_id", "party", "amount", "terms",
                "effective_date", "expiry_date")
_TERMINAL = {"fulfilled", "rejected", "terminated"}
_STATE_EVENTS = {"active": "activated", "fulfilled": "fulfilled",
                 "disputed": "disputed"}


@dataclass
class Contract(BaseModel):
    """合同模型（work_items, type='contract'）。"""
    project_id: str = ""
    title: str = ""
    description: str = ""
    status: str = "draft"
    priority: str = "medium"
    assignee_id: str = ""
    due_date: str = ""
    type: str = "contract"
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
            val = self._meta(name, 0.0 if name == "amount" else "")
            return float(val) if name == "amount" else val
        raise AttributeError(name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in _META_FIELDS:
            self._set_meta(name, value)
        else:
            super().__setattr__(name, value)


def _build_state_machine() -> StateMachine:
    """构建合同生命周期状态机。"""
    sm = StateMachine(name="contract", description="合同生命周期状态机")
    states = [
        ("draft", "todo", True, False, "草稿"),
        ("pending_approval", "in_progress", False, False, "待审批"),
        ("active", "in_progress", False, False, "生效中"),
        ("fulfilled", "done", False, True, "已履约"),
        ("rejected", "cancelled", False, True, "已拒绝"),
        ("disputed", "blocked", False, False, "争议中"),
        ("terminated", "cancelled", False, True, "已终止"),
    ]
    for n, k, s, t, d in states:
        sm.add_state(State(n, k, is_start=s, is_terminal=t, description=d))
    trans = [("submit", "draft", "pending_approval"),
             ("approve", "pending_approval", "active"),
             ("reject", "pending_approval", "rejected"),
             ("fulfill", "active", "fulfilled"),
             ("dispute", "active", "disputed"),
             ("resolve", "disputed", "active"),
             ("terminate", "active", "terminated")]
    for n, f, t in trans:
        sm.add_transition(Transition(n, f, t))
    return sm


class ContractModule(BaseModule):
    """合同模块：状态机 + 事件 + CLI。"""

    def initialize(self, db: Database, config: dict[str, Any], container: Any) -> None:
        self._db = db
        self._config = config
        self._container = container
        self._repo: Repository[Contract] = Repository(db, Contract, "work_items")
        self._sm = _build_state_machine()
        if hasattr(container, "_state_machine_engine"):
            container._state_machine_engine.register("contract", self._sm)

    def on_ready(self, container: Any) -> None:
        bus = self._bus(container)
        if bus:
            bus.subscribe("project.cancelled", self._on_project_cancelled)

    def _bus(self, container: Any) -> Any:
        return getattr(container, "_event_bus", None)

    def _publish(self, name: str, item: Contract, extra: dict[str, Any] | None = None) -> None:
        bus = self._bus(self._container) if self._container else None
        if not bus:
            return
        payload = {"contract_id": item.id, "project_id": item.project_id,
                   "title": item.title, "status": item.status,
                   "tenant_id": item.tenant_id}
        if extra:
            payload.update(extra)
        bus.publish(name=name, payload=payload, source="contract",
                    entity_type="contract", entity_id=item.id)

    def _on_project_cancelled(self, event: Event) -> None:
        """项目取消 → 终止项目下所有非终态合同。"""
        pid = event.payload.get("project_id", "")
        if not pid:
            return
        for it in self._repo.list(project_id=pid, type="contract"):
            if it.status in _TERMINAL:
                continue
            try:
                old = it.status
                new_state = "terminated"
                if it.status == "active":
                    _, new_state = self._sm.fire(
                        it.status, "terminate",
                        {"contract_id": it.id, "reason": "project_cancelled"})
                it.status = new_state
                self._repo.update(it)
                self._publish("contract.status_changed", it,
                              {"old_status": old, "new_status": new_state})
                self._publish("contract.terminated", it)
            except Exception:
                pass

    def create_contract(self, project_id: str, title: str, description: str = "",
                        priority: str = "medium", assignee_id: str = "") -> Contract:
        item = Contract(id=str(uuid.uuid4()), tenant_id=TenantContext.current(),
                        project_id=project_id, title=title, description=description,
                        status="draft", priority=priority, assignee_id=assignee_id,
                        type="contract")
        self._repo.add(item)
        self._publish("contract.created", item)
        return item

    def get_contract(self, contract_id: str) -> Optional[Contract]:
        item = self._repo.get(contract_id)
        return item if item and item.type == "contract" else None

    def list_contracts(self, project_id: str, status: str | None = None) -> list[Contract]:
        filters: dict[str, Any] = {"project_id": project_id, "type": "contract"}
        if status:
            filters["status"] = status
        return self._repo.list(**filters)

    def transition_contract(self, contract_id: str, transition_name: str,
                            context: dict[str, Any] | None = None) -> Contract:
        item = self.get_contract(contract_id)
        if not item:
            raise ValueError(f"合同不存在: {contract_id}")
        ctx = context or {}
        ctx.setdefault("contract_id", contract_id)
        ctx.setdefault("tenant_id", TenantContext.current())
        old = item.status
        _, new = self._sm.fire(item.status, transition_name, ctx)
        item.status = new
        self._repo.update(item)
        self._publish("contract.status_changed", item,
                      {"old_status": old, "new_status": new})
        if new in _STATE_EVENTS:
            self._publish(f"contract.{_STATE_EVENTS[new]}", item)
        return item

    def delete_contract(self, contract_id: str) -> bool:
        if not self.get_contract(contract_id):
            return False
        return self._repo.delete(contract_id)

    def compliance_check(self, project_id: str) -> list[dict[str, Any]]:
        """合同合规检查：返回不合规项列表。"""
        issues: list[dict[str, Any]] = []
        for c in self.list_contracts(project_id):
            p: list[str] = []
            if c.status == "active":
                if not c.party: p.append("缺少合同方")
                if c.amount <= 0: p.append("金额无效")
                if not c.effective_date: p.append("缺少生效日期")
                if not c.expiry_date: p.append("缺少到期日期")
            if c.status == "draft" and not c.title.strip():
                p.append("草稿缺少标题")
            if p:
                issues.append({"contract_id": c.id, "title": c.title,
                               "status": c.status, "issues": p})
        return issues


def _cmd_create(args: Any, ctx: dict[str, Any]) -> None:
    m: ContractModule = ctx["module"]
    r = m.create_contract(args.project_id, args.title,
                          description=getattr(args, "description", "") or "",
                          priority=getattr(args, "priority", "medium") or "medium",
                          assignee_id=getattr(args, "assignee_id", "") or "")
    print(f"✅ 合同已创建: {r.title} (ID: {r.id})  状态: {r.status}")


def _cmd_list(args: Any, ctx: dict[str, Any]) -> None:
    m: ContractModule = ctx["module"]
    items = m.list_contracts(args.project_id, status=getattr(args, "status", None))
    if not items:
        print("暂无合同"); return
    print(f"{'ID':<36} {'标题':<22} {'状态':<16} {'优先级':<8}")
    print("-" * 82)
    for it in items:
        print(f"{it.id:<36} {it.title:<22} {it.status:<16} {it.priority:<8}")


def _cmd_get(args: Any, ctx: dict[str, Any]) -> None:
    m: ContractModule = ctx["module"]
    c = m.get_contract(args.id)
    if not c:
        print(f"合同不存在: {args.id}"); return
    print(f"ID: {c.id}\n标题: {c.title}\n状态: {c.status}\n优先级: {c.priority}")
    print(f"负责人: {c.assignee_id}\n项目: {c.project_id}")
    print(f"合同号: {c.contract_id}\n合同方: {c.party}\n金额: {c.amount}")
    print(f"生效日期: {c.effective_date}\n到期日期: {c.expiry_date}")
    if c.terms: print(f"条款: {c.terms}")


def _cmd_transition(args: Any, ctx: dict[str, Any]) -> None:
    m: ContractModule = ctx["module"]
    try:
        r = m.transition_contract(args.id, args.transition)
        print(f"✅ 状态已迁移: {r.title} → {r.status}")
    except ValueError as e:
        print(f"❌ 迁移失败: {e}")


def _cmd_delete(args: Any, ctx: dict[str, Any]) -> None:
    m: ContractModule = ctx["module"]
    if m.delete_contract(args.id):
        print(f"✅ 合同已删除: {args.id}")
    else:
        print(f"合同不存在: {args.id}")


def _cmd_compliance(args: Any, ctx: dict[str, Any]) -> None:
    m: ContractModule = ctx["module"]
    issues = m.compliance_check(args.project_id)
    if not issues:
        print("✅ 所有合同均合规"); return
    print(f"⚠️  发现 {len(issues)} 个合规问题：")
    for item in issues:
        print(f"  - {item['title']} ({item['status']}): {'; '.join(item['issues'])}")


manifest = ModuleManifest(
    name="contract", version="1.0.0",
    description="合同管理模块 — 生命周期状态机 + 事件驱动 + 合规检查",
    dependencies=["project"], tables=["work_items"],
    commands=[
        CommandDef("contract create", "创建合同", _cmd_create, [
            {"flags": ["--project-id"], "required": True, "help": "项目 ID"},
            {"flags": ["--title"], "required": True, "help": "合同标题"},
            {"flags": ["--description"], "help": "合同描述"},
            {"flags": ["--priority"], "default": "medium", "help": "优先级"},
            {"flags": ["--assignee-id"], "help": "负责人 ID"},
        ]),
        CommandDef("contract list", "列出项目下的合同", _cmd_list, [
            {"flags": ["--project-id"], "required": True, "help": "项目 ID"},
            {"flags": ["--status"], "help": "按状态过滤"},
        ]),
        CommandDef("contract get", "查看合同详情", _cmd_get, [
            {"flags": ["--id"], "required": True, "help": "合同 ID"},
        ]),
        CommandDef("contract transition", "触发合同状态迁移", _cmd_transition, [
            {"flags": ["--id"], "required": True, "help": "合同 ID"},
            {"flags": ["--transition"], "required": True,
             "help": "迁移名 (submit/approve/reject/fulfill/dispute/resolve/terminate)"},
        ]),
        CommandDef("contract delete", "删除合同", _cmd_delete, [
            {"flags": ["--id"], "required": True, "help": "合同 ID"},
        ]),
        CommandDef("contract compliance", "合同合规检查", _cmd_compliance, [
            {"flags": ["--project-id"], "required": True, "help": "项目 ID"},
        ]),
    ],
)


def _factory(m: ModuleManifest) -> ContractModule:
    return ContractModule(m)
