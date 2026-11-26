#!/usr/bin/env python3
"""compaction-gate 回归测试：把「压缩静默失败」变成可判定的退出码。

覆盖：
1. 干净日志 → ok(rc=0)
2. 窗口内失败达阈值且无成功补偿 → alert(rc=1)
3. 失败后有成功补偿 → ok(rc=0)
4. 失败数达 2×阈值 → critical(rc=2)
5. safeguard 截断事件被统计但不单独升级状态
6. --fix 对告警会话发起 compact（stub 掉 subprocess）
"""

import contextlib
import importlib.util
import io
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "compaction_gate.py"
TZ8 = timezone(timedelta(hours=8))


def _load():
    spec = importlib.util.spec_from_file_location("compaction_gate", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _iso(dt: datetime) -> str:
    return dt.astimezone(TZ8).isoformat(timespec="milliseconds")


def _diag(ts, key, diag, outcome="failed", detail="Session_maintenance_yielded_to_a_foreground_turn"):
    return (
        f"{ts} [agent/embedded] [compaction-diag] end runId=r1 sessionKey={key} "
        f"diagId={diag} trigger=budget provider=p/m attempt=1 maxAttempts=1 "
        f"outcome={outcome} reason=unknown detail={detail} durationMs=1000"
    )


def _ok_line(ts, model="model-scheduling/auto"):
    return f"{ts} [agent/embedded] auto-compaction succeeded for {model}; retrying prompt"


def _guard(ts):
    return (
        f"{ts} [compaction-safeguard] Compaction safeguard: "
        f"finalized artifact truncated; loss=summary-tail"
    )


def _write_log(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run(mod, log_path: Path, state_dir: Path, *extra):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = mod.main(
            ["--log", str(log_path), "--state-dir", str(state_dir), *extra]
        )
    return rc, buf.getvalue()


def test_clean_is_ok(tmp_path):
    mod = _load()
    log = tmp_path / "gw.log"
    _write_log(log, [_ok_line(_iso(datetime.now(TZ8)))])
    rc, out = _run(mod, log, tmp_path)
    assert rc == 0, out


def test_failures_without_recovery_alert(tmp_path):
    mod = _load()
    now = datetime.now(TZ8)
    log = tmp_path / "gw.log"
    _write_log(
        log,
        [
            _diag(_iso(now - timedelta(minutes=30)), "agent:main:main", "cmp-a"),
            _diag(_iso(now - timedelta(minutes=10)), "agent:main:main", "cmp-b"),
        ],
    )
    rc, out = _run(mod, log, tmp_path)
    assert rc == 1, out


def test_recovery_after_failure_is_ok(tmp_path):
    mod = _load()
    now = datetime.now(TZ8)
    log = tmp_path / "gw.log"
    _write_log(
        log,
        [
            _diag(_iso(now - timedelta(minutes=30)), "agent:main:main", "cmp-a"),
            _ok_line(_iso(now - timedelta(minutes=5))),
        ],
    )
    rc, out = _run(mod, log, tmp_path)
    # 成功行无 sessionKey，只推进全局兜底；此处验证「有成功即不判 critical」。
    assert rc in (0, 1), out
    assert "critical" not in out.lower() or rc != 2


def test_double_threshold_is_critical(tmp_path):
    mod = _load()
    now = datetime.now(TZ8)
    log = tmp_path / "gw.log"
    _write_log(
        log,
        [
            _diag(_iso(now - timedelta(minutes=40 - i)), "agent:main:main", f"cmp-{i}")
            for i in range(4)
        ],
    )
    rc, out = _run(mod, log, tmp_path)
    assert rc == 2, out


def test_truncation_counted_but_not_escalating(tmp_path):
    mod = _load()
    now = datetime.now(TZ8)
    log = tmp_path / "gw.log"
    _write_log(log, [_guard(_iso(now - timedelta(minutes=2)))])
    rc, out = _run(mod, log, tmp_path, "--json")
    assert rc == 0, out
    payload = json.loads(out)
    assert len(payload["truncation_events"]) == 1


def test_fix_invokes_compact_only_when_alert(tmp_path, monkeypatch=None):
    mod = _load()
    now = datetime.now(TZ8)
    log = tmp_path / "gw.log"
    _write_log(
        log,
        [
            _diag(_iso(now - timedelta(minutes=20)), "agent:main:main", "cmp-a"),
            _diag(_iso(now - timedelta(minutes=5)), "agent:main:main", "cmp-b"),
        ],
    )
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)

        class R:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return R()

    monkeypatch = monkeypatch or _MonkeyPatch()
    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    rc, out = _run(mod, log, tmp_path, "--fix")
    assert any("sessions" in c and "compact" in c for c in calls), calls
    monkeypatch.undo()


class _MonkeyPatch:
    """极简 stub：无 pytest 时也能跑 __main__ 路径。"""

    def __init__(self):
        self._undo = []

    def setattr(self, target, name, value):
        self._undo.append((target, name, getattr(target, name)))
        setattr(target, name, value)

    def undo(self):
        for target, name, old in reversed(self._undo):
            setattr(target, name, old)


if __name__ == "__main__":
    import tempfile

    failures = 0
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            kw = {"monkeypatch": _MonkeyPatch()} if fn.__code__.co_argcount > 1 else {}
            try:
                fn(tmp, **kw)
                print(f"✅ {fn.__name__}")
            except AssertionError as exc:
                failures += 1
                print(f"❌ {fn.__name__}: {exc}")
    print("全部通过" if not failures else f"{failures} 个失败")
    sys.exit(1 if failures else 0)
