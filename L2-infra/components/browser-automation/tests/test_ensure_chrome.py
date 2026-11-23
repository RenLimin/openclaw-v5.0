"""ensure_chrome.py 单测（不启真浏览器、不碰用户 Chrome）。

覆盖：幂等复用 / 启动失败回收 / stop 只杀专用实例 / 绝对路径解析。
真实浏览器 E2E 由 VERIFICATION 文档记录（需人工确认）。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "ensure_chrome.py"
spec = importlib.util.spec_from_file_location("ensure_chrome", SCRIPT)
ec = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(ec)


def test_resolve_chrome_absolute_or_none(monkeypatch, tmp_path):
    """解析结果必须是绝对路径或 None（禁止裸命令名）。"""
    fake = tmp_path / "chrome"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setattr(ec.shutil, "which", lambda n: None)
    monkeypatch.setattr(ec, "_CHROME_CANDIDATES", (fake,))
    assert ec.resolve_chrome() == str(fake)


def test_ensure_reuse_when_available(monkeypatch):
    """CDP 已可用 → 直接复用，不启动新进程。"""
    launched = {"n": 0}
    monkeypatch.setattr(ec, "is_available", lambda: True)
    monkeypatch.setattr(ec, "_launch", lambda c: launched.__setitem__("n", launched["n"] + 1))
    ok, msg = ec.ensure()
    assert ok and "复用" in msg
    assert launched["n"] == 0


def test_ensure_launch_and_wait(monkeypatch, tmp_path):
    """不可用 → 启动并等待就绪。"""
    monkeypatch.setattr(ec, "is_available", lambda: False)
    monkeypatch.setattr(ec, "resolve_chrome", lambda: "/fake/chrome")
    monkeypatch.setattr(ec, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ec, "LOCK_FILE", tmp_path / "oa-live.lock")
    monkeypatch.setattr(ec, "_launch", lambda c: type("P", (), {"pid": 123})())
    monkeypatch.setattr(ec, "_wait_ready", lambda t: True)
    ok, msg = ec.ensure()
    assert ok and "已启动" in msg and "123" in msg


def test_ensure_launch_timeout_recycles(monkeypatch, tmp_path):
    """启动后未就绪 → 回收进程并显式失败（不静默成功）。"""
    monkeypatch.setattr(ec, "is_available", lambda: False)
    monkeypatch.setattr(ec, "resolve_chrome", lambda: "/fake/chrome")
    monkeypatch.setattr(ec, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ec, "LOCK_FILE", tmp_path / "oa-live.lock")
    killed = {"pids": []}
    monkeypatch.setattr(ec, "_launch", lambda c: type("P", (), {"pid": 999})())
    monkeypatch.setattr(ec, "_wait_ready", lambda t: False)
    monkeypatch.setattr(ec, "_kill", lambda p: killed.__setitem__("pids", p))
    ok, msg = ec.ensure()
    assert not ok and "未就绪" in msg
    assert killed["pids"] == [999]


def test_ensure_no_chrome(monkeypatch, tmp_path):
    """无 Chrome 可执行 → 显式失败。"""
    monkeypatch.setattr(ec, "is_available", lambda: False)
    monkeypatch.setattr(ec, "resolve_chrome", lambda: None)
    monkeypatch.setattr(ec, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ec, "LOCK_FILE", tmp_path / "oa-live.lock")
    ok, msg = ec.ensure()
    assert not ok and "Chrome" in msg


def test_stop_noop_when_absent(monkeypatch):
    """无专用实例 → stop 幂等成功。"""
    monkeypatch.setattr(ec, "_dedicated_pids", lambda: [])
    ok, msg = ec.stop()
    assert ok and "无" in msg


def test_stop_kills_dedicated(monkeypatch):
    """stop 杀「本 profile + 本端口」的进程，并在二次确认后报告。"""
    calls = {"n": 0}

    def fake_pids():
        calls["n"] += 1
        return [] if calls["n"] > 1 else [4242]

    monkeypatch.setattr(ec, "_dedicated_pids", fake_pids)
    killed = {"pids": None}
    monkeypatch.setattr(ec, "_kill", lambda p: killed.__setitem__("pids", p))
    ok, msg = ec.stop()
    assert ok and killed["pids"] == [4242]


def test_dedicated_pids_filters_by_profile(monkeypatch):
    """_dedicated_pids 必须用 profile 路径过滤（否则会误杀用户 Chrome）。"""
    cmds = {
        "100": f"--user-data-dir={ec.PROFILE_DIR} --remote-debugging-port={ec.CDP_PORT}",
        "200": "--user-data-dir=/Users/bangcle/Library/Application Support/Google/Chrome",
    }

    def fake_run(args, **k):
        if args[:2] == ["pgrep", "-f"]:
            return type("R", (), {"stdout": "100\n200\n", "returncode": 0})()
        if args[:3] == ["ps", "-o", "command="]:
            return type("R", (), {"stdout": cmds.get(args[-1], ""), "returncode": 0})()
        return type("R", (), {"stdout": "", "returncode": 1})()

    monkeypatch.setattr(ec.subprocess, "run", fake_run)
    assert ec._dedicated_pids() == [100]


def test_main_status_exit_code(monkeypatch):
    """status 可用→0，不可用→1。"""
    monkeypatch.setattr(ec, "status", lambda: (True, {"pids": [1]}))
    assert ec.main(["status"]) == 0
    monkeypatch.setattr(ec, "status", lambda: (False, {"pids": []}))
    assert ec.main(["status"]) == 1


def test_main_ensure_exit_code(monkeypatch):
    """ensure 成功→0，失败→1。"""
    monkeypatch.setattr(ec, "ensure", lambda: (True, "ok"))
    assert ec.main([]) == 0
    monkeypatch.setattr(ec, "ensure", lambda: (False, "bad"))
    assert ec.main(["ensure"]) == 1


def test_probe_state_down(monkeypatch):
    """probe_state(down)：实例关闭时为通过（rc=0）。"""
    monkeypatch.setattr(ec, "status", lambda: (False, {"pids": []}))
    ok, msg = ec.probe_state("down")
    assert ok is True
    assert ec.main(["status", "--expect=down"]) == 0


def test_probe_state_up_fails_when_down(monkeypatch):
    """probe_state(up)：实例关闭时必须判失败（rc=1），不得误放行。"""
    monkeypatch.setattr(ec, "status", lambda: (False, {"pids": []}))
    ok, msg = ec.probe_state("up")
    assert ok is False
    assert ec.main(["status", "--expect=up"]) == 1


def test_probe_state_down_fails_when_up(monkeypatch):
    """probe_state(down)：实例在跑时必须判失败（防止该关不关）。"""
    monkeypatch.setattr(ec, "status", lambda: (True, {"pids": [1]}))
    ok, msg = ec.probe_state("down")
    assert ok is False
    assert ec.main(["status", "--expect=down"]) == 1


def test_probe_state_rejects_unknown_expect(monkeypatch):
    """未知 expect 值必须判失败（fail-closed）。"""
    monkeypatch.setattr(ec, "status", lambda: (False, {"pids": []}))
    ok, msg = ec.probe_state("sideways")
    assert ok is False


# ── 可调用性探针（health 门禁用，只读、不要求实例状态）──

def test_callability_probe_passes_when_prereqs_ok(monkeypatch, tmp_path):
    """前置齐备（chrome + profile + 可写）→ 探针通过，且**不启动/不关闭**进程。"""
    monkeypatch.setattr(ec, "resolve_chrome", lambda: "/fake/chrome")
    monkeypatch.setattr(ec, "PROFILE_DIR", tmp_path / "oa-live")
    monkeypatch.setattr(ec, "DATA_DIR", tmp_path)
    (tmp_path / "oa-live").mkdir()
    monkeypatch.setattr(ec, "is_available", lambda: False)
    monkeypatch.setattr(ec, "ensure", lambda: (_ for _ in ()).throw(AssertionError("不该启动")))
    monkeypatch.setattr(ec, "stop", lambda: (_ for _ in ()).throw(AssertionError("不该关闭")))
    ok, msg = ec.probe()
    assert ok is True
    assert ec.main(["status", "--probe"]) == 0


def test_callability_probe_fails_without_chrome(monkeypatch, tmp_path):
    """无 Chrome 可执行 → 探针失败（能力不可用）。"""
    monkeypatch.setattr(ec, "resolve_chrome", lambda: None)
    monkeypatch.setattr(ec, "PROFILE_DIR", tmp_path / "oa-live")
    monkeypatch.setattr(ec, "DATA_DIR", tmp_path)
    (tmp_path / "oa-live").mkdir()
    ok, msg = ec.probe()
    assert ok is False
    assert ec.main(["status", "--probe"]) == 1


def test_callability_probe_fails_without_profile(monkeypatch, tmp_path):
    """profile 不存在 → 探针失败（防止「需要时才发现没初始化」）。"""
    monkeypatch.setattr(ec, "resolve_chrome", lambda: "/fake/chrome")
    monkeypatch.setattr(ec, "PROFILE_DIR", tmp_path / "oa-live")
    monkeypatch.setattr(ec, "DATA_DIR", tmp_path)
    ok, msg = ec.probe()
    assert ok is False


def test_callability_probe_passes_even_when_instance_up(monkeypatch, tmp_path):
    """关键：实例在跑时探针仍应通过（否则用户合法使用时会被误判阻断提交）。"""
    monkeypatch.setattr(ec, "resolve_chrome", lambda: "/fake/chrome")
    monkeypatch.setattr(ec, "PROFILE_DIR", tmp_path / "oa-live")
    monkeypatch.setattr(ec, "DATA_DIR", tmp_path)
    (tmp_path / "oa-live").mkdir()
    monkeypatch.setattr(ec, "is_available", lambda: True)
    ok, msg = ec.probe()
    assert ok is True
    assert "CDP 可用=True" in msg
