"""DAG 拓扑排序与环检测（graph）。

用标准库 graphlib.TopologicalSorter（Python 3.9+；本机 3.14.7 验证）。
不引入 networkx / 外部依赖。
"""

from __future__ import annotations

from graphlib import TopologicalSorter

from loader import DagSpec


class DagCycleError(ValueError):
    """DAG 存在环，无法拓扑排序。"""


def topological_order(dag: DagSpec) -> list[str]:
    """返回拓扑序的任务 id 列表；存在环时抛 DagCycleError。"""
    ts: TopologicalSorter[str] = TopologicalSorter()
    for t in dag.tasks:
        ts.add(t.id, *t.depends_on)
    try:
        return list(ts.static_order())
    except Exception as exc:  # graphlib 内部对环抛 CycleError
        raise DagCycleError(f"DAG 存在环: {exc}") from exc
