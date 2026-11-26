#!/usr/bin/env python3
"""scheduler-guard plist 卫生门禁回归测试。

覆盖 2026-11-25 事故：launchd 裸环境无 /opt/homebrew/bin 导致定时任务
FileNotFoundError 静默失败；以及重构遗留 plist 引用不存在路径的假象。
"""
import os
import plistlib
import subprocess
import sys
from pathlib import Path

import audit as sg

TMP = Path("/tmp/_sg_hygiene_test")


def _write_plist(path: Path, args, env=None):
    d = {"Label": path.stem, "ProgramArguments": args}
    if env is not None:
        d["EnvironmentVariables"] = env
    path.write_bytes(plistlib.dumps(d))
    return path


def setup_function(_):
    TMP.mkdir(exist_ok=True)


def teardown_function(_):
    for p in TMP.glob("*"):
        p.unlink(missing_ok=True)
    TMP.rmdir()


# ── 缺 PATH 必须被拦 ─────────────────────────────────────────────

def test_missing_path_env_detected():
    p = _write_plist(
        TMP / "ai.openclaw.a.plist",
        ["/bin/bash", "-c", "exec openclaw status"],
        {"HOME": "/Users/bangcle"},
    )
    probs = sg.check_plist_hygiene([p])
    assert any(x["kind"] == "missing_path_env" for x in probs), probs


def test_no_env_section_detected():
    p = _write_plist(TMP / "ai.openclaw.b.plist", ["/bin/bash", "-c", "exec colima status"])
    probs = sg.check_plist_hygiene([p])
    assert any(x["kind"] == "missing_path_env" for x in probs), probs


# ── 有 PATH 放行 ─────────────────────────────────────────────────

def test_path_present_passes(tmp_path):
    script = tmp_path / "ok.py"
    script.write_text("print('ok')\n")
    p = _write_plist(
        TMP / "ai.openclaw.c.plist",
        ["/bin/bash", "-c", f"exec /opt/homebrew/bin/python3 {script}"],
        {"HOME": "/Users/bangcle", "PATH": "/opt/homebrew/bin:/usr/bin:/bin"},
    )
    assert sg.check_plist_hygiene([p]) == []


# ── service-env wrapper 注入 PATH 是合法形态，不得误报 ─────────────

def test_wrapper_injected_path_not_flagged():
    label = "ai.openclaw.gateway"
    svc = Path.home() / ".openclaw" / "service-env"
    wrapper = svc / f"{label}-env-wrapper.sh"
    env_file = svc / f"{label}.env"
    if not (wrapper.is_file() and env_file.is_file()):
        # 环境不具备 wrapper 形态时，仅验证判定函数本身逻辑
        assert sg._path_via_wrapper(TMP / "x.plist", ["/bin/sh", "/nonexistent-wrapper.sh"]) is False
        return
    p = _write_plist(
        TMP / f"{label}.plist",
        ["/bin/sh", str(wrapper), str(env_file),
         "/opt/homebrew/opt/node/bin/node", "/opt/homebrew/lib/node_modules/openclaw/dist/index.js"],
    )
    assert sg.check_plist_hygiene([p]) == [], "wrapper 注入 PATH 的 plist 被误报"


# ── 陈旧引用必须被拦 ─────────────────────────────────────────────

def test_stale_reference_detected(tmp_path):
    real = tmp_path / "real.py"
    real.write_text("#!/usr/bin/env python3\nprint('ok')\n")
    ghost = tmp_path / "gone.py"  # 不创建
    p = _write_plist(
        TMP / "ai.openclaw.d.plist",
        ["/bin/bash", "-c", f"exec /opt/homebrew/bin/python3 {real} && exec python3 {ghost}"],
        {"HOME": "/Users/bangcle", "PATH": "/opt/homebrew/bin:/usr/bin:/bin"},
    )
    probs = sg.check_plist_hygiene([p])
    kinds = [x["kind"] for x in probs]
    assert "stale_reference" in kinds, probs
    assert any(ghost.name in x["detail"] for x in probs), probs


def test_bash_c_string_refs_are_traced(tmp_path):
    """bash -c 合成串里的 .py/.sh 也要被提取，否则陈旧引用会漏检。"""
    missing = tmp_path / "does_not_exist_xyz.py"
    p = _write_plist(
        TMP / "ai.openclaw.e.plist",
        ["/bin/bash", "-c", f"source ~/.zshenv; exec /opt/homebrew/bin/python3 {missing}"],
        {"HOME": "/Users/bangcle", "PATH": "/opt/homebrew/bin:/usr/bin:/bin"},
    )
    refs = sg._referenced_paths(["/bin/bash", "-c", f"exec /opt/homebrew/bin/python3 {missing}"])
    assert str(missing) in refs, refs
    probs = sg.check_plist_hygiene([p])
    assert any(x["kind"] == "stale_reference" for x in probs), probs


# ── 审计整体退出码语义 ───────────────────────────────────────────

def test_audit_blocking_exit_code_on_hygiene_problem():
    """有问题时必须非零退出——否则定时任务形同虚设。

    用 SCHEDULER_GUARD_LAUNCHAGENTS_DIR 环境变量驱动（子进程会重新导入模块，
    父进程 monkeypatch 无效）。

    注：不做「空夹具 → 退出 0」的反向断言——夹具目录内不含 manifest 声明的
    全部 plist，脚本必然全判 unscheduled，而非零退出正是该语义的正确表现。
    """
    bad = _write_plist(
        TMP / "ai.openclaw.zz_bad.plist",
        ["/bin/bash", "-c", "exec openclaw status"],
        {"HOME": "/Users/bangcle"},
    )
    env = dict(os.environ, SCHEDULER_GUARD_LAUNCHAGENTS_DIR=str(TMP))
    proc = subprocess.run(
        [sys.executable, str(Path(sg.__file__).resolve()), "--json"],
        capture_output=True, text=True, env=env,
    )
    assert proc.returncode != 0, (
        "存在 plist 卫生问题时 audit 必须非零退出；stdout=" + proc.stdout[:300]
    )

    # 门禁确实「看见了」那条卫生问题（而非因其它原因非零）
    import json as _json
    payload = _json.loads(proc.stdout)
    hyg = payload.get("hygiene_problems") or []
    assert any(h["kind"] == "missing_path_env" for h in hyg), hyg
