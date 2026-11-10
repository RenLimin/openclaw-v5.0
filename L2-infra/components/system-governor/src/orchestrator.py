"""编排器：并发调度四条 lane，聚合结果。

契约见 DESIGN-DETAIL-system-governor-v1.0.md §4。
设计：薄编排，四 lane 无相互依赖 → ThreadPoolExecutor 并发；
单 lane 异常/超时隔离，不影响其余 lane。
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from .models import Finding, LaneResult
from . import ledger

# 每条 lane 的 wall-clock 预算（秒）
LANE_BUDGET_SEC = 120


def run_lane_with_budget(
    lane: str,
    runner: Callable[[], list[Finding]],
    budget: int = LANE_BUDGET_SEC,
) -> LaneResult:
    """有界时间运行一个 lane，异常/超时隔离。

    返回 LaneResult：
      - 正常：runner() 的 findings + stats
      - 超时：仅一条 lane_timeout Finding（守护线程自行收尾，不阻塞）
      - 异常：仅一条 lane_error Finding
    """
    started = time.monotonic()
    result: dict[str, list[Finding] | Exception] = {"findings": [], "error": None}

    def _run() -> None:
        try:
            result["findings"] = runner()
        except Exception as exc:  # noqa: BLE001 — 隔离上报
            result["error"] = exc

    import threading

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=budget)

    elapsed = round(time.monotonic() - started, 2)
    lane_result = LaneResult(lane=lane)
    lane_result.stats["elapsed_s"] = elapsed

    if t.is_alive():
        # 超时：daemon 线程自行收尾，主流程继续
        lane_result.add(Finding(
            lane=lane,
            item="lane_timeout",
            severity="warning",
            status="open",
            evidence=f"lane {lane} exceeded {budget}s budget",
            action="re-run lane alone or raise --timeout",
        ))
        lane_result.stats["error"] = "timeout"
        return lane_result

    error = result.get("error")
    if error is not None:
        lane_result.add(Finding(
            lane=lane,
            item="lane_error",
            severity="warning",
            status="open",
            evidence=f"lane {lane} raised {type(error).__name__}: {error}",
        ))
        lane_result.stats["error"] = str(error)
        return lane_result

    findings = result["findings"] or []
    for f in findings:
        lane_result.add(f)
    lane_result.stats["scanned"] = len(findings)
    lane_result.stats["errors"] = sum(1 for f in findings if f.severity == "critical")
    lane_result.stats["warnings"] = sum(1 for f in findings if f.severity == "warning")
    return lane_result


def orchestrate(
    runners: dict[str, Callable[[], list[Finding]]],
    *,
    apply: bool = False,
    max_workers: int = 4,
) -> dict[str, LaneResult]:
    """并发运行指定 lanes，返回 {lane: LaneResult}。"""
    lane_results: dict[str, LaneResult] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(run_lane_with_budget, lane, runner): lane
            for lane, runner in runners.items()
        }
        for fut in as_completed(futures):
            lane = futures[fut]
            lane_results[lane] = fut.result()

    # 保持 A/B/C/D 顺序
    return {k: lane_results[k] for k in sorted(lane_results, key=lambda x: "ABCD".index(x))}
