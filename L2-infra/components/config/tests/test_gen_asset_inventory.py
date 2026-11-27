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


def test_architecture_adr_dir_is_listed():
    """Q-6 跨目录同号治理：docs/architecture/adr/ 必须入册，不得只扫 knowledge-base。

    背景（事故 2026-11-27）：原 render_docs() 只扫 docs/knowledge-base/**（32 份），
    docs/architecture/adr/（7 份，含 ADR-037）完全未收录；而 ADR-037 执行记录却写
    「01-asset-inventory.md 重生成入册」——结论先于执行的假账。本测试锁定该口径不回退。
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("gen_asset_inventory", GENERATOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    out = "\n".join(mod.render_docs())
    assert "ADR（架构目录）" in out, "清单缺少「架构目录」ADR 分类行"
    assert "../architecture/adr/ADR-202611-037-capability-routing-orchestration-layer.md" in out, (
        "ADR-037 未出现在资产清单中"
    )
    # 知识库目录仍须保留，避免修一处漏一处
    assert "ADR（架构决策记录）" in out, "清单缺少知识库 ADR 分类行"


def test_adr_status_variants():
    """状态解析兼容三种格式：frontmatter / `> 状态：**x**` / `> **状态**：x`。"""
    import importlib.util

    spec = importlib.util.spec_from_file_location("gen_asset_inventory", GENERATOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    root = mod.REPO_ROOT
    cases = {
        "ADR-202611-036-session-boundary-guard": "proposed",
        "ADR-202611-037-capability-routing-orchestration-layer": "accepted",
        "ADR-032-context-overflow-auto-recovery": "accepted",
    }
    for stem, expected in cases.items():
        hits = list((root / "docs").rglob(stem + ".md"))
        assert hits, f"找不到 ADR: {stem}"
        got = mod._adr_status(hits[0])
        assert got == expected, f"{stem} 状态解析错误: {got!r} != {expected!r}"


def test_l0_gateway_section_listed():
    """Q-1（ADR-037）：L0-gateway 三组件须入册，且状态据实读自 README 组件表。

    背景：原 render_l1() 只扫 L1_runtime，L0 的状态变更无任何机器可读登记；
    ADR-037 执行记录写「资产清单重生成入册」却查无此项 = 假账。
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("gen_asset_inventory", GENERATOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    out = "\n".join(mod.render_l0())
    assert "## L0 — 接入层资产（消息网关）" in out, "清单缺少 L0 段"
    for comp in ("auth-gateway", "channel-router", "session-manager"):
        assert f"`L0-gateway/components/{comp}/`" in out, f"L0 组件未入册: {comp}"
    # 状态必须来自 README，且不得再出现骨架口径
    assert "架构预留" in out, "L0 状态未反映「架构预留」"
    assert "📐 骨架" not in out, "L0 组件仍标骨架，与 ADR-037 拍板不一致"


def test_readme_component_status_parsed():
    """README §3 组件表解析：表头行与分隔行不得被当作组件。"""
    import importlib.util

    spec = importlib.util.spec_from_file_location("gen_asset_inventory", GENERATOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    got = mod._l0_readme_status()
    assert set(got) == {"channel-router", "session-manager", "auth-gateway"}, got
    for name, status in got.items():
        assert status == "📋 架构预留（参考设计）", f"{name}: {status!r}"
