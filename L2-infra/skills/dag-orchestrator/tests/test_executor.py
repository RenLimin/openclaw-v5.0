"""T05-T09：executor 并行 / 失败停下游 / 超时 / 变量传递。"""

from __future__ import annotations

import time

import loader
from artifact_store import ArtifactStore
from executor import run_dag


def _sleep_runner(task, inputs):
    """假执行器：每个任务 sleep 0.5s，透传 inputs。"""
    time.sleep(0.5)
    return {o: inputs.get(o, f"val-{o}") for o in task.outputs} if task.outputs else None


def _parallel3_dag():
    """3 个无依赖任务（纯并行，T05 用）。"""
    return loader.parse_dag(
        {
            "name": "p3",
            "tasks": [
                {"id": "a", "agent": "x", "action": "x", "outputs": ["oa"]},
                {"id": "b", "agent": "x", "action": "x", "outputs": ["re"]},
                {"id": "c", "agent": "x", "action": "x", "outputs": ["ac"]},
            ],
        }
    )


def _fail_runner(task, inputs):
    """中间任务抛错，其余透传。"""
    if task.id == "join_data":
        raise RuntimeError("boom")
    time.sleep(0.1)
    return {o: inputs.get(o, f"val-{o}") for o in task.outputs} if task.outputs else None


class TestParallel:
    def test_t05_parallel_real(self):
        """T05: 3 个无依赖任务并行（各 sleep 0.5s），总耗时 < 1.0s。"""
        dag = _parallel3_dag()
        t0 = time.monotonic()
        res = run_dag(dag, _sleep_runner, max_workers=4)
        dur = time.monotonic() - t0
        assert res.status == "success"
        assert dur < 1.0, f"并行应 <1.0s，实际 {dur:.2f}s（说明串行执行）"

    def test_t05b_serial_control(self):
        """T05 对照组：并发度=1 时耗时 ≈1.5s（串行）。"""
        dag = _parallel3_dag()
        t0 = time.monotonic()
        res = run_dag(dag, _sleep_runner, max_workers=1)
        dur = time.monotonic() - t0
        assert res.status == "success"
        assert dur >= 1.2, f"串行应 ≥1.2s，实际 {dur:.2f}s"


class TestArtifact:
    def test_t06_variable_passing(self, sample_dag):
        """T06: 上游 outputs → 下游 inputs 传递。"""
        seen = {}

        def runner(task, inputs):
            seen[task.id] = dict(inputs)
            if task.id == "generate_report":
                assert inputs["analysis_result"] == "val-analysis_result"
            return {o: inputs.get(o, f"val-{o}") for o in task.outputs} if task.outputs else None

        res = run_dag(sample_dag, runner, max_workers=4)
        assert res.status == "success"
        # join_data 应看到 3 个上游输出
        assert set(seen["join_data"]) == {"oa_data", "revenue_data", "acceptance_data"}
        # analyze 应看到 joined_data
        assert seen["analyze"] == {"joined_data": "val-joined_data"}


class TestFailure:
    def test_t07_failure_stops_downstream(self, sample_dag):
        """T07: 中间任务失败 → 下游 skipped、run 终态 failed、无下游工件。"""
        store = ArtifactStore()
        res = run_dag(sample_dag, _fail_runner, max_workers=4, store=store)
        assert res.status == "failed"
        assert "boom" in (res.error or "")
        assert res.task_statuses["join_data"] == "failed"
        assert res.task_statuses["analyze"] == "skipped"
        assert res.task_statuses["generate_report"] == "skipped"
        # 失败的中间任务不应产出 joined_data
        with __import__("pytest").raises(KeyError):
            store.get("joined_data")


class TestTimeout:
    def test_t08_single_task_timeout(self):
        """T08: 单任务超时 → failed(timeout)、下游 skipped。"""
        dag = loader.parse_dag(
            {
                "name": "t",
                "tasks": [
                    {"id": "a", "agent": "x", "action": "x", "outputs": ["o"],
                     "timeout_s": 1},
                    {"id": "b", "agent": "x", "action": "x", "inputs": ["o"],
                     "depends_on": ["a"]},
                ],
            }
        )

        def slow_runner(task, inputs):
            time.sleep(3)
            return {o: "v" for o in task.outputs}

        res = run_dag(sample_dag := dag, slow_runner, max_workers=2, task_timeout_s=1)
        assert res.status == "failed"
        assert res.task_statuses["a"] == "failed"
        assert res.task_statuses["b"] == "skipped"

    def test_t09_overall_timeout(self):
        """T09: 整体超时 → run failed、超时任务标记 failed。"""
        dag = loader.parse_dag(
            {
                "name": "t",
                "tasks": [
                    {"id": "a", "agent": "x", "action": "x"},
                    {"id": "b", "agent": "x", "action": "x"},
                ],
            }
        )

        def slow_runner(task, inputs):
            time.sleep(3)
            return None

        res = run_dag(dag, slow_runner, max_workers=2, overall_timeout_s=1)
        assert res.status == "failed"
        assert res.task_statuses["a"] == "failed"
        assert res.task_statuses["b"] == "failed"
