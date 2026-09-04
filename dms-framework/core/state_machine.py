"""
core/state_machine.py — 状态机引擎
通用有限状态机：状态定义 + 迁移 + guard + on_enter/on_exit hook + 审计。
StateMachineEngine 管理多个命名状态机（每种实体类型一个）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional


# ---------------------------------------------------------------------------
# State / Transition — 数据模型
# ---------------------------------------------------------------------------

@dataclass
class State:
    """状态定义。

    category 用于高层聚合统计：
    - todo: 未开始
    - in_progress: 进行中
    - done: 已完成
    - cancelled: 已取消
    - blocked: 阻塞
    """

    name: str
    category: str = "todo"  # todo | in_progress | done | cancelled | blocked
    is_start: bool = False
    is_terminal: bool = False
    description: str = ""

    def __post_init__(self) -> None:
        valid_categories = {"todo", "in_progress", "done", "cancelled", "blocked"}
        if self.category not in valid_categories:
            raise ValueError(f"Invalid category: {self.category}, must be one of {valid_categories}")


@dataclass
class Transition:
    """迁移定义。

    guards: 守卫函数列表，全部返回 True 才能执行
    on_enter: 进入目标状态前的 hook
    on_exit: 离开源状态前的 hook
    """

    name: str
    from_state: str
    to_state: str
    guards: list[Callable[[dict[str, Any]], bool]] = field(default_factory=list)
    on_enter: list[Callable[[dict[str, Any]], None]] = field(default_factory=list)
    on_exit: list[Callable[[dict[str, Any]], None]] = field(default_factory=list)
    description: str = ""


@dataclass
class EntityState:
    """实体的当前状态记录。

    每个受状态机管理的实体都有一个 EntityState，追踪当前状态和历史。
    """

    entity_type: str
    entity_id: str
    current_state: str
    history: list[dict[str, Any]] = field(default_factory=list)
    tenant_id: str = "system"

    def record_transition(self, transition: str, from_state: str, to_state: str, context: dict[str, Any]) -> None:
        self.history.append({
            "transition": transition,
            "from": from_state,
            "to": to_state,
            "at": datetime.now(timezone.utc).isoformat(),
            "context": {k: v for k, v in context.items() if not k.startswith("_")},
        })
        self.current_state = to_state


# ---------------------------------------------------------------------------
# StateMachine — 单台状态机
# ---------------------------------------------------------------------------

class StateMachine:
    """单个状态机定义 + 执行逻辑。

    不直接持有实体状态，实体状态由调用方（StateMachineEngine）管理。
    这样同一个 StateMachine 定义可以服务于无数个同类型实体。
    """

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description
        self.states: dict[str, State] = {}
        self.transitions: dict[str, Transition] = {}
        self._from_index: dict[str, list[str]] = {}  # from_state -> [transition_names]

    # -- 定义 --------------------------------------------------------------

    def add_state(self, state: State) -> None:
        if state.name in self.states:
            raise ValueError(f"State '{state.name}' already exists in machine '{self.name}'")
        self.states[state.name] = state

    def add_transition(self, transition: Transition) -> None:
        if transition.name in self.transitions:
            raise ValueError(f"Transition '{transition.name}' already exists in machine '{self.name}'")
        if transition.from_state not in self.states:
            raise ValueError(f"from_state '{transition.from_state}' not defined")
        if transition.to_state not in self.states:
            raise ValueError(f"to_state '{transition.to_state}' not defined")
        self.transitions[transition.name] = transition
        if transition.from_state not in self._from_index:
            self._from_index[transition.from_state] = []
        self._from_index[transition.from_state].append(transition.name)

    def get_start_state(self) -> str:
        for s in self.states.values():
            if s.is_start:
                return s.name
        raise ValueError(f"No start state defined in machine '{self.name}'")

    # -- 查询 --------------------------------------------------------------

    def can_transition(self, current_state: str, transition_name: str) -> bool:
        """检查指定迁移能否从当前状态触发（仅校验状态 + guards）。"""
        if transition_name not in self.transitions:
            return False
        t = self.transitions[transition_name]
        if t.from_state != current_state:
            return False
        return True  # guards 需要 context，这里只做结构检查

    def get_available_transitions(self, current_state: str, context: dict[str, Any] | None = None) -> list[str]:
        """获取当前状态下可执行的迁移名列表（通过 guards 的才返回）。"""
        ctx = context or {}
        available = []
        for t_name in self._from_index.get(current_state, []):
            t = self.transitions[t_name]
            try:
                if all(guard(ctx) for guard in t.guards):
                    available.append(t_name)
            except Exception:
                # guard 异常视为不可用
                continue
        return available

    # -- 执行 --------------------------------------------------------------

    def fire(
        self,
        current_state: str,
        transition_name: str,
        context: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        """执行迁移。返回 (from_state, to_state)。

        执行顺序：on_exit (源状态) → guards → on_enter (目标状态)
        """
        ctx = context or {}
        if transition_name not in self.transitions:
            raise ValueError(f"Unknown transition: {transition_name}")

        t = self.transitions[transition_name]
        if t.from_state != current_state:
            raise ValueError(
                f"Cannot fire '{transition_name}' from state '{current_state}' "
                f"(expected '{t.from_state}')"
            )

        # 检查 guards
        for guard in t.guards:
            if not guard(ctx):
                raise PermissionError(f"Guard failed for transition '{transition_name}'")

        # on_exit hooks
        for hook in t.on_exit:
            hook(ctx)

        # on_enter hooks
        for hook in t.on_enter:
            hook(ctx)

        return t.from_state, t.to_state


# ---------------------------------------------------------------------------
# StateMachineEngine — 状态机引擎（多机管理）
# ---------------------------------------------------------------------------

class StateMachineEngine:
    """命名状态机注册中心 + 实体状态管理。

    每种实体类型（task / milestone / deliverable / risk）对应一台状态机。
    实体状态存在内存中（生产环境应持久化到 DB）。
    """

    def __init__(self) -> None:
        self._machines: dict[str, StateMachine] = {}
        self._entities: dict[tuple[str, str], EntityState] = {}  # (type, id) -> EntityState

    def register(self, name: str, machine: StateMachine) -> None:
        if name in self._machines:
            raise ValueError(f"StateMachine '{name}' already registered")
        self._machines[name] = machine

    def get(self, name: str) -> StateMachine:
        if name not in self._machines:
            raise KeyError(f"StateMachine '{name}' not found")
        return self._machines[name]

    def list_machines(self) -> list[str]:
        return list(self._machines.keys())

    # -- 实体操作 ----------------------------------------------------------

    def create_entity(self, entity_type: str, entity_id: str, tenant_id: str = "system") -> EntityState:
        """创建一个新的实体状态，初始化为 start state。"""
        if entity_type not in self._machines:
            raise KeyError(f"No state machine for entity type: {entity_type}")
        machine = self._machines[entity_type]
        start = machine.get_start_state()
        state = EntityState(
            entity_type=entity_type,
            entity_id=entity_id,
            current_state=start,
            tenant_id=tenant_id,
        )
        state.history.append({
            "transition": "__init__",
            "from": None,
            "to": start,
            "at": datetime.now(timezone.utc).isoformat(),
            "context": {},
        })
        self._entities[(entity_type, entity_id)] = state
        return state

    def get_entity_state(self, entity_type: str, entity_id: str) -> Optional[EntityState]:
        return self._entities.get((entity_type, entity_id))

    def transition(
        self,
        entity_type: str,
        entity_id: str,
        transition_name: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """触发实体的状态迁移，返回新状态名。"""
        key = (entity_type, entity_id)
        if key not in self._entities:
            raise KeyError(f"No entity state for {entity_type}/{entity_id}, call create_entity first")

        entity = self._entities[key]
        machine = self._machines[entity_type]
        from_state, to_state = machine.fire(entity.current_state, transition_name, context)
        entity.record_transition(transition_name, from_state, to_state, context or {})
        return to_state

    def get_available_transitions(self, entity_type: str, entity_id: str, context: dict[str, Any] | None = None) -> list[str]:
        key = (entity_type, entity_id)
        if key not in self._entities:
            return []
        entity = self._entities[key]
        machine = self._machines[entity_type]
        return machine.get_available_transitions(entity.current_state, context)
