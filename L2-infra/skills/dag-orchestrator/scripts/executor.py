"""任务调度与并发执行（executor）。

- 波次推进（wave）：只提交「所有直接依赖已成功完成」的任务（DESIGN §3.4）
- ThreadPoolExecutor + 显式 max_workers（并行规则 1）
- 任一失败 → 下游递归标记 skipped，不再派发（规则 3）
- 单任务超时 timeout_s / 整体超时 overall_timeout_s（规则 4）
- 执行器可注入（runner 传 callable），hermetic 测试用假执行器
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable

from artifact_store import ArtifactStore
from loader import DagSpec, TaskSpec
from state import RunState, mark_finished, mark_started

# 默认值来自 SKILL 执行规则 4
DEFAULT_TASK_TIMEOUT_S = 300
DEFAULT_OVERALL_TIMEOUT_S = 1800

# 任务执行函数签名: fn(task, inputs: dict[str, object]) -> dict[str, object] | None
TaskRunner = Callable[[TaskSpec, dict], dict | None]


@dataclass
class RunResult:
    """一次 run 的结果。"""

    status: str  # success / failed
    task_statuses: dict[str, str]
    error: str | None = None
    duration_s: float = 0.0


def run_dag(
    dag: DagSpec,
    runner: TaskRunner,
    *,
    max_workers: int = 4,
    task_timeout_s: int = DEFAULT_TASK_TIMEOUT_S,
    overall_timeout_s: int = DEFAULT_OVERALL_TIMEOUT_S,
    state: RunState | None = None,
    store: ArtifactStore | None = None,
) -> RunResult:
    """按波次并发执行 DAG。

    runner(task, inputs) 返回该任务产出的 outputs 字典（key=output 名）；
    抛异常/超时视为任务失败，其下游全部 skipped。
    """
    state = state or RunState(dag)
    store = store or ArtifactStore()
    task_map = dag.task_map()

    # 递归下游（用于失败传播）
    downstream: dict[str, set[str]] = {t.id: set() for t in dag.tasks}
    for t in dag.tasks:
        for dep in t.depends_on:
            downstream[dep].add(t.id)

    completed: set[str] = set()   # 成功完成
    failed: set[str] = set()      # 失败/超时
    skipped: set[str] = set()     # 被失败传播阻断
    running: dict[str, object] = {}  # tid -> future（本波）

    t0 = time.monotonic()

    def _skip_downstream(task_id: str) -> None:
        for nxt in downstream[task_id]:
            if nxt in failed or nxt in skipped or nxt in completed:
                continue
            mark_finished(state, nxt, "skipped")
            skipped.add(nxt)
            _skip_downstream(nxt)

    def _wave() -> list[str]:
        """当前就绪层：所有依赖均已成功完成的任务。"""
        return [
            t.id
            for t in dag.tasks
            if t.id not in completed
            and t.id not in failed
            and t.id not in skipped
            and t.id not in running
            and all(dep in completed for dep in t.depends_on)
        ]

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        while True:
            wave = _wave()
            if not wave:
                # 剩余任务（若还有）全部依赖失败者 → 标 skipped
                for t in dag.tasks:
                    if t.id not in completed and t.id not in failed and t.id not in skipped:
                        mark_finished(state, t.id, "skipped")
                        skipped.add(t.id)
                break
            if time.monotonic() - t0 > overall_timeout_s:
                for t in dag.tasks:
                    if t.id not in completed and t.id not in failed and t.id not in skipped:
                        mark_finished(state, t.id, "failed", f"整体超时({overall_timeout_s}s)")
                        failed.add(t.id)
                break

            running = {}
            for tid in wave:
                task = task_map[tid]
                inputs = {inp: store.get(inp) for inp in task.inputs}  # 依赖已全完成，安全
                mark_started(state, tid)
                running[tid] = pool.submit(runner, task, inputs)

            # 本波结果回收（futures 并发运行，串行 result() 仅等各自完成）
            for tid, fut in running.items():
                task = task_map[tid]
                remaining = overall_timeout_s - (time.monotonic() - t0)
                eff_timeout = min(
                    task.timeout_s if task.timeout_s != 300 else task_timeout_s,
                    max(0.01, remaining),
                )
                try:
                    outputs = fut.result(timeout=eff_timeout)
                except TimeoutError:
                    mark_finished(state, tid, "failed", f"任务超时({eff_timeout}s)")
                    failed.add(tid)
                    _skip_downstream(tid)
                    continue
                except Exception as exc:
                    mark_finished(state, tid, "failed", f"{type(exc).__name__}: {exc}")
                    failed.add(tid)
                    _skip_downstream(tid)
                    continue
                if outputs:
                    for k, v in outputs.items():
                        store.put(k, v)
                mark_finished(state, tid, "success")
                completed.add(tid)

            running = {}

    duration = time.monotonic() - t0
    status = "success" if not failed else "failed"
    error = None
    if failed:
        errs = [f"{tid}: {state.tasks[tid].error or 'unknown'}" for tid in sorted(failed)]
        error = "; ".join(errs)
    return RunResult(
        status=status,
        task_statuses={k: v.status for k, v in state.tasks.items()},
        error=error,
        duration_s=round(duration, 3),
    )
