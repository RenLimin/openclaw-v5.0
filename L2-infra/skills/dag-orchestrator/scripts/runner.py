"""执行入口（runner）：组合 loader/graph/executor/state/viz。

- 提供默认执行器（可注入；默认实现打印任务信息并透传 inputs，供框架演示/测试）
- 支持契约门禁回调：末端产物过 check_answer_contract（fail-closed）
- CLI: python runner.py <dag.yaml> [--max-workers N] [--timeout S]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Callable

from artifact_store import ArtifactStore
from executor import (
    DEFAULT_OVERALL_TIMEOUT_S,
    DEFAULT_TASK_TIMEOUT_S,
    TaskRunner,
    run_dag,
)
from loader import DagSpec, load_dag
from state import RunState
from viz import to_mermaid

# 契约校验器路径（fail-closed 门禁，DESIGN §4.1）
CONTRACT_CHECKER = (
    Path(__file__).resolve().parents[3]
    / "prompts" / "tools" / "check_answer_contract.py"
)


def default_runner(task, inputs: dict) -> dict | None:
    """默认执行器：打印任务信息，透传 inputs 到 outputs。

    真实场景替换为 sessions_spawn 派发（agent/action 语义）。
    """
    print(
        f"[dag] {task.id} (agent={task.agent}, action={task.action}) "
        f"inputs={list(inputs)}",
        flush=True,
    )
    return {o: inputs.get(o) for o in task.outputs} if task.outputs else None


def run_with_contract(
    dag: DagSpec,
    runner: TaskRunner,
    *,
    max_workers: int = 4,
    task_timeout_s: int = DEFAULT_TASK_TIMEOUT_S,
    overall_timeout_s: int = DEFAULT_OVERALL_TIMEOUT_S,
    contract_report: str | Path | None = None,
    state: RunState | None = None,
    store: ArtifactStore | None = None,
) -> tuple[bool, str]:
    """执行 DAG；若指定 contract_report 则对末端产物过契约校验。

    返回 (ok, message)。契约校验失败 → ok=False（fail-closed）。
    """
    result = run_dag(
        dag,
        runner,
        max_workers=max_workers,
        task_timeout_s=task_timeout_s,
        overall_timeout_s=overall_timeout_s,
        state=state,
        store=store,
    )
    msg = f"run 状态: {result.status}"
    if result.error:
        msg += f" | 失败: {result.error}"
    if result.status != "success":
        return False, msg

    # 契约门禁（fail-closed）：仅全部成功时才校验
    if contract_report:
        report = Path(contract_report)
        if not report.exists():
            return False, f"契约报告不存在: {report}（fail-closed）"
        checker = CONTRACT_CHECKER
        if not checker.exists():
            return False, f"契约校验器不存在: {checker}（fail-closed）"
        proc = subprocess.run(
            [sys.executable, str(checker), str(report)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.returncode != 0:
            tail = proc.stdout.strip().splitlines()[-5:] or proc.stderr.strip().splitlines()[-5:]
            return False, "契约校验失败（fail-closed）: " + " | ".join(tail)
        msg += " | 契约校验 PASS"
    return True, msg


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="dag-orchestrator 执行器")
    ap.add_argument("dag", help="DAG 定义 YAML 路径")
    ap.add_argument("--max-workers", type=int, default=4)
    ap.add_argument("--task-timeout", type=int, default=DEFAULT_TASK_TIMEOUT_S)
    ap.add_argument("--overall-timeout", type=int, default=DEFAULT_OVERALL_TIMEOUT_S)
    ap.add_argument("--contract-report", help="末端产物路径（过契约校验，fail-closed）")
    ap.add_argument("--mermaid", action="store_true", help="仅输出 Mermaid 定义")
    args = ap.parse_args(argv)

    try:
        dag = load_dag(args.dag)
    except Exception as exc:
        print(f"❌ DAG 加载失败: {exc}")
        return 1

    if args.mermaid:
        print(to_mermaid(dag))
        return 0

    ok, msg = run_with_contract(
        dag,
        default_runner,
        max_workers=args.max_workers,
        task_timeout_s=args.task_timeout,
        overall_timeout_s=args.overall_timeout,
        contract_report=args.contract_report,
    )
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
