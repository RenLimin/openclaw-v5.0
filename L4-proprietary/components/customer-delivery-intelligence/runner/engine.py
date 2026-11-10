"""薄 runner 状态机引擎：9 状态 + 跃迁表；节点=纯函数 step(state)->state。

设计要点：
- HITL 节点（N3/N6）进入 waiting 态，等待 decide() 注入决策后推进。
- 每节点跃迁成功后写检查点；崩溃后 resume() 从当前态继续（不重跑已完成节点）。
- 失败重试由节点内计数；连续 3 次失败 -> failed。
"""
from __future__ import annotations
from typing import Callable, Optional
from .state import CheckpointStore, new_state

# 状态 + 跃迁
TRANSITIONS: dict[str, dict[str, str]] = {
    "N1_guard":         {"pass": "N2_collect", "fail": "failed"},
    "N2_collect":       {"pass": "N3_manifest_gate", "fail": "failed"},
    "N3_manifest_gate": {"approve": "N4_parse", "reject": "N2_collect", "skip": "N4_parse"},
    "N4_parse":         {"pass": "N5_compose", "partial": "N5_compose", "fail": "failed"},
    "N5_compose":       {"pass": "N6_sign_gate", "fail": "failed"},
    "N6_sign_gate":     {"approve": "N7_render", "revise": "N5_compose"},
    "N7_render":        {"pass": "done"},
}

# HITL 等待态（不自动推进）
HITL_STATES = {"N3_manifest_gate", "N6_sign_gate"}
TERMINAL_STATES = {"done", "failed"}

# 节点 step 注册表（由编排层注入，保持引擎与业务解耦）
StepFn = Callable[[dict], dict]


class Engine:
    def __init__(self, store: CheckpointStore, steps: dict[str, StepFn]):
        self.store = store
        self.steps = steps

    # ---------- 生命周期 ----------
    def start(self, task_id: str, input_norm: dict) -> dict:
        if self.store.load(task_id):
            raise ValueError(f"task already exists: {task_id}")
        state = new_state(task_id, input_norm)
        self.store.save(state)
        return self.run_until_pause(task_id)

    def run_until_pause(self, task_id: str) -> dict:
        """从当前态推进，直到 HITL 等待 / 终态 / 失败。"""
        state = self.store.load(task_id)
        if not state:
            raise KeyError(task_id)

        while state["current_state"] not in HITL_STATES and \
              state["current_state"] not in TERMINAL_STATES:
            node = state["current_state"]
            step = self.steps.get(node)
            if step is None:
                raise RuntimeError(f"no step registered for {node}")
            try:
                state = step(state)
            except Exception as exc:  # 节点抛错 -> failed（业务重试在节点内处理）
                state["current_state"] = "failed"
                state["errors"].append(f"{node}: {exc!r}")
                self.store.save(state)
                return state
            event = state.get("_event", "pass")
            state.pop("_event", None)
            nxt = TRANSITIONS[node].get(event)
            if nxt is None:
                raise RuntimeError(f"illegal event {event!r} at {node}")
            state["current_state"] = nxt
            self.store.save(state)
        return state

    def decide(self, task_id: str, gate: str, decision: str) -> dict:
        state = self.store.load(task_id)
        if not state:
            raise KeyError(task_id)
        cur = state["current_state"]
        gate_state = "N3_manifest_gate" if gate == "gate1" else "N6_sign_gate"
        if cur != gate_state:
            raise RuntimeError(f"task not at {gate_state} (at {cur})")
        valid = set(TRANSITIONS[cur].keys())
        if decision not in valid:
            raise ValueError(f"invalid decision {decision!r}, want one of {sorted(valid)}")
        state["hitl_decisions"][gate] = decision
        nxt = TRANSITIONS[cur][decision]
        state["current_state"] = nxt
        self.store.save(state)
        return self.run_until_pause(task_id)

    def resume(self, task_id: str) -> dict:
        return self.run_until_pause(task_id)

    def get(self, task_id: str) -> Optional[dict]:
        return self.store.load(task_id)
