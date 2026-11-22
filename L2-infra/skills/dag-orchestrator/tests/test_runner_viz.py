"""T10-T13：runner 契约门禁 + state 落盘 + viz Mermaid。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import loader
import viz
from artifact_store import ArtifactStore
from executor import run_dag
from runner import run_with_contract
from state import RunState

CONTRACT_DIR = Path(__file__).resolve().parents[3] / "prompts"
CONTRACT_CHECKER = CONTRACT_DIR / "tools" / "check_answer_contract.py"

# 契约合规/不合规报告（内容契约：时间戳、溯源链、推断标记、降级标注）
GOOD_REPORT = CONTRACT_DIR / "tests" / "fixtures" / "good-report.md"
BAD_REPORT = CONTRACT_DIR / "tests" / "fixtures" / "bad-no-envelope.md"


def _pass_runner(task, inputs):
    return {o: inputs.get(o, f"val-{o}") for o in task.outputs} if task.outputs else None


class TestContractGate:
    def test_t10_contract_pass(self, sample_dag):
        """T10: 全部成功 + 合规报告 → run success、契约 PASS。"""
        if not CONTRACT_CHECKER.exists() or not GOOD_REPORT.exists():
            import pytest
            pytest.skip("契约校验器/夹具不存在（非 hermetic 环境）")
        ok, msg = run_with_contract(
            sample_dag, _pass_runner, max_workers=4, contract_report=GOOD_REPORT
        )
        assert ok is True
        assert "契约校验 PASS" in msg

    def test_t11_contract_block(self, sample_dag):
        """T11: 报告缺溯源链 → fail-closed 拦截。"""
        if not CONTRACT_CHECKER.exists() or not BAD_REPORT.exists():
            import pytest
            pytest.skip("契约校验器/夹具不存在（非 hermetic 环境）")
        ok, msg = run_with_contract(
            sample_dag, _pass_runner, max_workers=4, contract_report=BAD_REPORT
        )
        assert ok is False
        assert "契约校验失败" in msg

    def test_t11b_contract_report_missing(self, sample_dag):
        """T11b: 报告不存在 → fail-closed。"""
        ok, msg = run_with_contract(
            sample_dag, _pass_runner, max_workers=4, contract_report="/nonexistent.md"
        )
        assert ok is False
        assert "不存在" in msg


class TestState:
    def test_t12_state_serializable(self, sample_dag, tmp_path):
        """T12: 状态落盘 JSON 可被独立解析。"""
        state = RunState(sample_dag)
        run_dag(sample_dag, _pass_runner, max_workers=4, state=state)
        path = tmp_path / "run_state.json"
        state.save(path)
        data = RunState.load(path)
        assert data["status"] == "running"
        assert len(data["tasks"]) == 6
        assert data["tasks"]["generate_report"]["status"] == "success"
        # 可独立 json 解析
        json.loads(path.read_text(encoding="utf-8"))


class TestViz:
    def test_t13_mermaid(self, sample_dag):
        """T13: Mermaid 输出含 6 节点 + 5 条边。"""
        m = viz.to_mermaid(sample_dag)
        assert m.startswith("graph TD")
        assert m.count('["') == 6  # 6 个节点
        assert m.count(" --> ") == 5  # 5 条边
        assert "collect_oa --> join_data" in m
        assert "analyze --> generate_report" in m
