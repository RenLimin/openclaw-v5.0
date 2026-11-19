"""回归测试：gen_asset_inventory 在最小 PATH 下不得降级。

背景（事故 2026-11-19）：launchd `ai.openclaw.system-audit` 的 PATH 可能只有
`/usr/bin:/bin`，生成器 8 处命令（openclaw/node/git）全部找不到 → 静默降级成
「⚠️ 数据源不可用」，而 `--check` 比对的是降级稿 vs 降级稿，把降级内容当权威
写入 `01-asset-inventory.md` 并登记「漂移归零」。

修复：`_resolve_bin()` 绝对路径兜底。本测试锁定该行为不回退。
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

COMP_DIR = Path(__file__).resolve().parent.parent
GENERATOR = COMP_DIR / "gen_asset_inventory.py"

MINIMAL_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"


def _load_module():
    spec = importlib.util.spec_from_file_location("gen_asset_inventory", GENERATOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_generator_exists():
    assert GENERATOR.is_file(), f"生成器不存在: {GENERATOR}"


def test_resolve_bin_finds_openclaw_without_path():
    """PATH 里没有 openclaw 时，仍应解析到绝对路径。"""
    mod = _load_module()
    import os

    env = {"PATH": MINIMAL_PATH, "HOME": os.environ.get("HOME", "/Users/bangcle")}
    script = (
        "import importlib.util,os;"
        f"spec=importlib.util.spec_from_file_location('g',{str(GENERATOR)!r});"
        "m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);"
        "print(m._resolve_bin('openclaw'));print(m._resolve_bin('node'));"
        "print(m._resolve_bin('git'))"
    )
    r = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert r.returncode == 0, r.stderr
    lines = r.stdout.strip().splitlines()
    assert len(lines) == 3, r.stdout
    for name, resolved in zip(("openclaw", "node", "git"), lines):
        assert resolved.startswith("/"), f"{name} 未解析为绝对路径: {resolved}"
        assert Path(resolved).exists(), f"{name} 解析路径不存在: {resolved}"


def test_no_degradation_under_minimal_path():
    """最小 PATH 下生成器不得产出「数据源不可用」。"""
    import os

    env = {"PATH": MINIMAL_PATH, "HOME": os.environ.get("HOME", "/Users/bangcle")}
    r = subprocess.run(
        [sys.executable, str(GENERATOR), "--stdout"],
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
    )
    assert r.returncode == 0, r.stderr
    assert "数据源不可用" not in r.stdout, (
        "最小 PATH 下仍出现「数据源不可用」降级行，说明 PATH 兜底失效"
    )
    assert "| OpenClaw | OpenClaw" in r.stdout, "L1 版本行缺失"
    assert "| Node.js | v" in r.stdout, "L1 Node 行缺失"


def test_resolve_cmd_executable_and_mjs_wrapped():
    """解析结果必须可执行；.mjs 入口（无 shebang）必须显式用 node 执行。"""
    import os

    mod = _load_module()
    cmd = mod._resolve_cmd(["openclaw", "--version"])
    assert cmd[-1] == "--version", cmd
    first = cmd[0]
    assert os.path.exists(first), f"首元素不存在: {first}"
    if first.endswith(".mjs"):
        assert cmd[1].endswith("node") or "node" in cmd[1], f".mjs 未用 node 执行: {cmd}"
        assert cmd[2].endswith(".mjs"), cmd
    else:
        assert os.access(first, os.X_OK), f"首元素不可执行: {first}"


def test_resolve_cmd_under_minimal_path():
    """最小 PATH 下解析结果同样可执行（不依赖 PATH 命中）。"""
    import os

    env = {"PATH": MINIMAL_PATH, "HOME": os.environ.get("HOME", "/Users/bangcle")}
    script = (
        "import importlib.util;"
        f"spec=importlib.util.spec_from_file_location('g',{str(GENERATOR)!r});"
        "m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);"
        "print('|'.join(m._resolve_cmd(['openclaw','--version'])))"
    )
    r = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert r.returncode == 0, r.stderr
    parts = r.stdout.strip().split("|")
    assert parts[-1] == "--version", parts
    assert os.path.exists(parts[0]), f"最小 PATH 下解析失败: {parts}"
    if parts[0].endswith(".mjs"):
        assert "node" in parts[1], parts
