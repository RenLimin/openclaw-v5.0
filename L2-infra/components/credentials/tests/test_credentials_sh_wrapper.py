"""回归测试：credentials.sh github-sync 的脚本路径解析。

事故（2026-11-25）：`cmd_github_sync` 曾用 `${REPO_ROOT}/L2-infra/components/credentials/…`
拼接同步脚本路径，而顶部 `REPO_ROOT="$(cd "$(dirname …)/.." && pwd)"` 实为上溯**两层**
（→ `L2-infra/components`），于是拼出重复一层的 `L2-infra/components/L2-infra/…`，
独立调用 `credentials.sh github-sync --check` 直接报「未找到同步脚本」。
（pre-push hook 走的是相对路径，故 push 不受影响——但任何文档化的手动自检都会误报失败。）

本测试**不联网**：用 PATH 前置的假 python3 记录被调用的脚本路径，断言解析结果真实存在。
"""
from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

COMP_DIR = Path(__file__).resolve().parent.parent
SH = COMP_DIR / "credentials.sh"
SYNC = COMP_DIR / "github_credential_sync.py"


def _run_wrapper_with_stub(tmp_path: Path) -> tuple[int, str, Path]:
    """以假 python3 跑 `credentials.sh github-sync --check`，返回 (rc, log, stub_log)。"""
    stub_dir = tmp_path / "stub"
    stub_dir.mkdir()
    stub_log = tmp_path / "called.txt"

    stub = stub_dir / "python3"
    # 逐参数记录（用 "$@" 而非 "$*"）：路径与参数必须分行，才能单独校验解析结果
    stub.write_text(
        "#!/usr/bin/env bash\n"
        "for a in \"$@\"; do\n"
        f'  printf \"%s\\n\" \"$a\" >> "{stub_log}"\n'
        "done\n"
        "exit 0\n",
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)

    env = dict(os.environ)
    env["PATH"] = f"{stub_dir}{os.pathsep}{env.get('PATH', '')}"

    proc = subprocess.run(
        ["bash", str(SH), "github-sync", "--check"],
        capture_output=True, text=True, env=env, cwd=str(COMP_DIR),
    )
    return proc.returncode, (stub_log.read_text(encoding="utf-8") if stub_log.exists() else ""), stub_log


def test_sync_script_exists():
    assert SYNC.is_file(), f"同步脚本不存在: {SYNC}"


def test_wrapper_resolves_sync_script(tmp_path):
    """包装器必须把**真实存在**的绝对路径交给 python3（旧实现会解析到不存在的重复路径）。"""
    rc, log, _ = _run_wrapper_with_stub(tmp_path)
    assert rc == 0, f"github-sync --check 退出码非 0（应为路径修复后正常放行）: {rc}"
    called = [line.strip() for line in log.splitlines() if line.strip()]
    assert called, "python3 未被调用——说明包装器在解析阶段就报了「未找到同步脚本」"
    # 第一个实参应是脚本绝对路径；后续才是 --check
    target = Path(called[0])
    assert target.is_absolute(), f"应传绝对路径，实际: {target}"
    assert target.exists(), f"解析出的脚本路径不存在: {target}"
    assert target.resolve() == SYNC.resolve(), (
        f"解析目标错误: {target} != {SYNC}"
    )


def test_no_repo_root_double_prefix():
    """静态防线：禁止再出现 `${REPO_ROOT}/L2-infra/…` 这种重复前缀拼接。"""
    src = SH.read_text(encoding="utf-8")
    assert "${REPO_ROOT}/L2-infra" not in src, (
        "检测到 REPO_ROOT 重复前缀拼接——REPO_ROOT 已含 L2-infra/components，会多一层"
    )


if __name__ == "__main__":
    sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q", str(Path(__file__))]))
