"""T01-T04：loader 加载/校验 + graph 拓扑/环检测。"""

from __future__ import annotations

import graph
import loader
import pytest

from loader import DagValidationError


class TestLoader:
    def test_t01_yaml_load_and_validate(self, sample_dag):
        """T01: YAML 加载与校验 → 6 任务，id 唯一。"""
        dag = sample_dag
        assert dag.name == "交付月报生成"
        assert len(dag.tasks) == 6
        ids = [t.id for t in dag.tasks]
        assert len(ids) == len(set(ids)), "id 必须唯一"

    def test_t02_dangling_dep_detected(self):
        """T02: 悬空依赖 → 抛错且信息含缺失 id。"""
        with pytest.raises(DagValidationError) as ei:
            loader.parse_dag(
                {
                    "name": "x",
                    "tasks": [
                        {"id": "a", "agent": "x", "action": "x", "depends_on": ["nope"]},
                    ],
                }
            )
        assert "nope" in str(ei.value)

    def test_t02b_inputs_not_produced_detected(self):
        """T02b: inputs 引用无人产出的变量 → 抛错。"""
        with pytest.raises(DagValidationError) as ei:
            loader.parse_dag(
                {
                    "name": "x",
                    "tasks": [
                        {"id": "a", "agent": "x", "action": "x", "inputs": ["ghost"]},
                    ],
                }
            )
        assert "ghost" in str(ei.value)

    def test_t02c_duplicate_id_detected(self):
        """T02c: 重复 id → 抛错。"""
        with pytest.raises(DagValidationError) as ei:
            loader.parse_dag(
                {
                    "name": "x",
                    "tasks": [
                        {"id": "a", "agent": "x", "action": "x"},
                        {"id": "a", "agent": "y", "action": "y"},
                    ],
                }
            )
        assert "重复" in str(ei.value)


class TestGraph:
    def test_t04_topological_order(self, sample_dag):
        """T04: 拓扑序正确（collect_* 均在 join_data 前）。"""
        order = graph.topological_order(sample_dag)
        assert order[-1] == "generate_report"
        assert order.index("join_data") > order.index("collect_oa")
        assert order.index("join_data") > order.index("collect_revenue")
        assert order.index("join_data") > order.index("collect_acceptance")
        assert order.index("analyze") > order.index("join_data")

    def test_t03_cycle_detected(self):
        """T03: 环 A→B→A → 抛 DagCycleError。"""
        dag = loader.parse_dag(
            {
                "name": "cyc",
                "tasks": [
                    {"id": "a", "agent": "x", "action": "x", "depends_on": ["b"]},
                    {"id": "b", "agent": "x", "action": "x", "depends_on": ["a"]},
                ],
            }
        )
        with pytest.raises(graph.DagCycleError):
            graph.topological_order(dag)
