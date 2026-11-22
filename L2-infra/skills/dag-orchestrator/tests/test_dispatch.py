"""dispatch 后端 hermetic 测试（fake CLI 注入，不触真实 Gateway）。"""

from __future__ import annotations

import json
import stat
from pathlib import Path

import dispatch
import loader
import pytest


def _task(task_id="t1", outputs=("o1",)):
    return loader.TaskSpec(
        id=task_id, name="测试任务", agent="data-collector", action="do",
        inputs=(), outputs=list(outputs), depends_on=(), timeout_s=300,
    )


def _write_fake_cli(tmp_path: Path, stdout: str, rc: int = 0) -> str:
    """写一个假 opencli 可执行文件，返回路径。"""
    cli = tmp_path / "fake_openclaw"
    cli.write_text(f'#!/bin/sh\ncat <<\'EOF\'\n{stdout}\nEOF\nexit {rc}\n', encoding="utf-8")
    cli.chmod(cli.stat().st_mode | stat.S_IEXEC)
    return str(cli)


class TestPrompt:
    def test_prompt_contains_contract(self):
        p = dispatch.build_prompt(_task(), {"a": 1})
        assert "t1" in p and "do" in p and "data-collector" in p
        assert "outputs" in p and "o1" in p
        assert json.dumps({"a": 1}, ensure_ascii=False) in p


class TestParseReply:
    def test_plain_json(self):
        assert dispatch.parse_reply('{"outputs": {"o1": 42}}') == {"o1": 42}

    def test_with_surrounding_text(self):
        text = '好的，结果如下：\n{"outputs": {"o1": "x"}}\n以上。'
        assert dispatch.parse_reply(text) == {"o1": "x"}

    def test_error_envelope_raises(self):
        with pytest.raises(ValueError, match="boom"):
            dispatch.parse_reply('{"error": "boom"}')

    def test_unparseable_raises(self):
        with pytest.raises(ValueError, match="未含可解析"):
            dispatch.parse_reply("我没有输出 JSON")


class TestResolveCli:
    def test_path_found(self, monkeypatch):
        monkeypatch.setattr(dispatch.shutil, "which", lambda n: "/opt/homebrew/bin/openclaw")
        assert dispatch.resolve_cli() == "/opt/homebrew/bin/openclaw"

    def test_candidate_fallback(self, monkeypatch, tmp_path):
        monkeypatch.setattr(dispatch.shutil, "which", lambda n: None)
        cand = tmp_path / "openclaw"
        cand.write_text("#!/bin/sh\n")
        monkeypatch.setattr(dispatch, "_CLI_CANDIDATES", (str(cand),))
        assert dispatch.resolve_cli() == str(cand)

    def test_not_found_raises(self, monkeypatch, tmp_path):
        monkeypatch.setattr(dispatch.shutil, "which", lambda n: None)
        monkeypatch.setattr(dispatch, "_CLI_CANDIDATES", (str(tmp_path / "nope"),))
        with pytest.raises(FileNotFoundError):
            dispatch.resolve_cli()


class TestDispatcher:
    def test_success(self, tmp_path):
        cli = _write_fake_cli(tmp_path, json.dumps(
            {"ok": True, "status": "ok", "final": '{"outputs": {"o1": "v1"}}'}))
        fn = dispatch.make_agent_dispatcher(cli=cli, run_id="r1")
        assert fn(_task(), {}) == {"o1": "v1"}

    def test_no_outputs_returns_none(self, tmp_path):
        cli = _write_fake_cli(tmp_path, json.dumps(
            {"ok": True, "status": "ok", "final": "完成"}))
        fn = dispatch.make_agent_dispatcher(cli=cli)
        assert fn(_task(outputs=()), {}) is None

    def test_cli_nonzero_raises(self, tmp_path):
        cli = _write_fake_cli(tmp_path, "oops", rc=1)
        fn = dispatch.make_agent_dispatcher(cli=cli)
        with pytest.raises(RuntimeError, match="派发失败"):
            fn(_task(), {})

    def test_ok_false_raises(self, tmp_path):
        cli = _write_fake_cli(tmp_path, json.dumps(
            {"ok": False, "error": {"message": "model exhausted"}}))
        fn = dispatch.make_agent_dispatcher(cli=cli)
        with pytest.raises(RuntimeError, match="model exhausted"):
            fn(_task(), {})

    def test_bad_reply_raises(self, tmp_path):
        cli = _write_fake_cli(tmp_path, json.dumps(
            {"ok": True, "status": "ok", "final": "没有 JSON"}))
        fn = dispatch.make_agent_dispatcher(cli=cli)
        with pytest.raises(ValueError):
            fn(_task(), {})

    def test_end_to_end_with_executor(self, tmp_path, sample_dag):
        """dispatcher 接入 executor：真实 run_dag 调度链。"""
        from executor import run_dag
        cli = _write_fake_cli(tmp_path, json.dumps(
            {"ok": True, "status": "ok", "final": '{"outputs": {"o1": "v1"}}'}))
        fn = dispatch.make_agent_dispatcher(cli=cli, run_id="e2e")
        # 仅跑单节点 DAG，避免多任务都需要 fake CLI 输出不同值
        dag = loader.parse_dag({"name": "x", "tasks": [
            {"id": "a", "agent": "x", "action": "x", "outputs": ["o1"]}]})
        res = run_dag(dag, fn, max_workers=1)
        assert res.status == "success"
        assert res.task_statuses["a"] == "success"
