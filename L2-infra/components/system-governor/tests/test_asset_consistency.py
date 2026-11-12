"""system-governor v1.1 — §12 资产一致性六探针测试。

黄金基准见 DESIGN-DETAIL-system-governor-v1.1.md §5。
策略：monkeypatch WORKSPACE/_COMPONENT_BASES/DOCS_DIR/ASSET_INVENTORY_DOC
到 tmp_path，构造完全隔离的注入环境，不碰真实工作区、测试后自动清理。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "scripts"))

import system_full_audit as a  # noqa: E402


def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """把全部扫描基路径重定向到 tmp_path，隔离真实工作区。"""
    monkeypatch.setattr(a, "WORKSPACE", tmp_path)
    monkeypatch.setattr(a, "DOCS_DIR", tmp_path / "docs" / "architecture")
    monkeypatch.setattr(a, "ASSET_INVENTORY_DOC", tmp_path / "docs" / "architecture" / "01-asset-inventory.md")
    monkeypatch.setattr(a, "_COMPONENT_BASES", [
        tmp_path / "L2-infra" / "components",
        tmp_path / "L3-business" / "components",
        tmp_path / "L4-proprietary" / "components",
    ])
    a.DOCS_DIR.mkdir(parents=True, exist_ok=True)


# ── P1 计数漂移 ───────────────────────────────────────────────────────

def test_p1_count_drift_hit_and_clear(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(a, "_count_discovered_components", lambda: "41")
    monkeypatch.setattr(a, "_count_inventory_components", lambda: 42)
    r = a._p1_count_drift()
    assert r["status"] == "⚠️"
    assert "41 / 登记 42" in r["detail"]

    monkeypatch.setattr(a, "_count_inventory_components", lambda: 41)
    r2 = a._p1_count_drift()
    assert r2["status"] == "✅"


def test_p1_count_drift_unparsable_is_ok(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(a, "_count_discovered_components", lambda: "?")
    monkeypatch.setattr(a, "_count_inventory_components", lambda: -1)
    assert a._p1_count_drift()["status"] == "✅"  # 不可解析不误报


# ── P2 路径断链 ───────────────────────────────────────────────────────

def test_p2_path_broken_hit_and_clear(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    # 组件目录 + README 引用不存在的路径
    comp = tmp_path / "L2-infra" / "components" / "e2e-probe"
    comp.mkdir(parents=True, exist_ok=True)
    (comp / "README.md").write_text("见 `L2-infra/components/nonexistent-xyz-999`\n", encoding="utf-8")

    r = a._p2_path_broken()
    assert r["status"] == "⚠️"
    assert "nonexistent-xyz-999" in r["detail"]

    # 修复引用 → 清零
    (comp / "README.md").write_text("见 `L2-infra/components/e2e-probe`\n", encoding="utf-8")
    assert a._p2_path_broken()["status"] == "✅"


def test_p2_accepts_trailing_slash(tmp_path, monkeypatch):
    """带尾斜杠引用也检出（文档两种写法各半，66/66）。"""
    _isolate(tmp_path, monkeypatch)
    comp = tmp_path / "L2-infra" / "components" / "e2e-probe"
    comp.mkdir(parents=True, exist_ok=True)
    (comp / "README.md").write_text("见 `L2-infra/components/nonexistent-xyz-999/`\n", encoding="utf-8")
    r = a._p2_path_broken()
    assert r["status"] == "⚠️"
    assert "nonexistent-xyz-999" in r["detail"]


# ── P3 空壳组件 ───────────────────────────────────────────────────────

def test_p3_skeleton_hit_and_clear(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    comp = tmp_path / "L2-infra" / "components" / "e2e-skeleton"
    comp.mkdir(parents=True, exist_ok=True)
    (comp / "README.md").write_text("# 空壳\n\n✅ 已上线\n", encoding="utf-8")

    r = a._p3_skeleton_components()
    assert r["status"] == "⚠️"
    assert "e2e-skeleton" in r["detail"]

    # 补一个 py → 非空壳 → 清零
    (comp / "main.py").write_text("x = 1\n", encoding="utf-8")
    assert a._p3_skeleton_components()["status"] == "✅"


def test_p3_ignores_prd_design_docs(tmp_path, monkeypatch):
    """PRD/DESIGN 里的「已实现」是设计描述，不算完成声明。"""
    _isolate(tmp_path, monkeypatch)
    comp = tmp_path / "L2-infra" / "components" / "e2e-skeleton"
    comp.mkdir(parents=True, exist_ok=True)
    (comp / "PRD-v1.0.md").write_text("本模块已实现如下功能...\n", encoding="utf-8")
    assert a._p3_skeleton_components()["status"] == "✅"


# ── P4 未跟踪/未提交 ──────────────────────────────────────────────────

def test_p4_reports_threshold_consistently(tmp_path, monkeypatch):
    """不依赖真实工作区状态：detail 与 status 必须自洽。"""
    _isolate(tmp_path, monkeypatch)
    # tmp_path 非 git 仓库 → git status 不可用 → ✅ 不误报
    r = a._p4_untracked_uncommitted()
    assert r["status"] == "✅"


# ── P5 硬编码根路径 ───────────────────────────────────────────────────

def test_p5_hardcoded_root_hit_and_clear(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    base = tmp_path / "L2-infra"
    base.mkdir(parents=True, exist_ok=True)
    py = base / "legacy.py"
    py.write_text("# old\np = 'workspace/model-scheduling/scripts'\n", encoding="utf-8")

    r = a._p5_hardcoded_root()
    assert r["status"] == "⚠️"
    assert "legacy.py" in r["detail"]

    py.write_text("# fixed\np = 'L2-infra/components/model-scheduling/scripts'\n", encoding="utf-8")
    assert a._p5_hardcoded_root()["status"] == "✅"


def test_p5_excludes_audit_script_self(tmp_path, monkeypatch):
    """审计脚本自身含 _REMOVED_ROOT_PATHS 常量定义，必须排除自指。"""
    _isolate(tmp_path, monkeypatch)
    base = tmp_path / "L2-infra"
    base.mkdir(parents=True, exist_ok=True)
    (base / "system_full_audit.py").write_text(
        "_REMOVED_ROOT_PATHS = ['workspace/model-scheduling/']\n", encoding="utf-8")
    assert a._p5_hardcoded_root()["status"] == "✅"


# ── P6 重复资产 ───────────────────────────────────────────────────────

def test_p6_duplicate_hit_and_clear(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    a_dir = tmp_path / "L2-infra" / "components" / "e2e-dup-a"
    b_dir = tmp_path / "L3-business" / "components" / "e2e-dup-b"
    a_dir.mkdir(parents=True, exist_ok=True)
    b_dir.mkdir(parents=True, exist_ok=True)
    content = b"z" * 2048  # ≥1KB 阈值
    (a_dir / "dup.txt").write_bytes(content)
    (b_dir / "dup.txt").write_bytes(content)

    r = a._p6_duplicate_assets()
    assert r["status"] == "⚠️"
    assert "e2e-dup-a" in r["detail"] and "e2e-dup-b" in r["detail"]

    # 删一份 → 清零
    (a_dir / "dup.txt").unlink()
    assert a._p6_duplicate_assets()["status"] == "✅"


def test_p6_ignores_small_files_and_backup_dirs(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    a_dir = tmp_path / "L2-infra" / "components" / "e2e-a"
    b_dir = tmp_path / "L2-infra" / "components" / "e2e-b"
    a_dir.mkdir(parents=True, exist_ok=True)
    b_dir.mkdir(parents=True, exist_ok=True)
    # <1KB：忽略
    small = b"x" * 100
    (a_dir / "small.txt").write_bytes(small)
    (b_dir / "small.txt").write_bytes(small)
    # 备份目录：忽略
    bkp = tmp_path / "L2-infra" / "components" / "e2e-bkp" / "backups"
    bkp.mkdir(parents=True, exist_ok=True)
    (bkp / "dup.txt").write_bytes(b"y" * 2048)
    (a_dir / "dup.txt").write_bytes(b"y" * 2048)
    r = a._p6_duplicate_assets()
    assert r["status"] == "✅", r["detail"]


# ── 误报防护：预留/废弃/夹具/vendor/版本代际/fork ─────────────────────

def test_p2_ignores_reserved_deprecated_lines(tmp_path, monkeypatch):
    """路径所在行明确标 📋 预留/❌ 废弃/~~删除线~~ 时，有意不存在不报断链。"""
    _isolate(tmp_path, monkeypatch)
    doc = a.DOCS_DIR / "00-system-architecture.md"
    doc.write_text(
        "| MCP | `L2-infra/components/future-svc/` | 📋 预留（目录待建） |\n"
        "| old | `L2-infra/components/old-svc/` | ❌ 已废弃，并入 other |\n"
        "| strike | ~~`L2-infra/components/gone-svc/`~~ |\n",
        encoding="utf-8")
    assert a._p2_path_broken()["status"] == "✅"


def test_p2_still_flags_unmarked_broken(tmp_path, monkeypatch):
    """未标注的真实断链仍须检出（防过度豁免）。"""
    _isolate(tmp_path, monkeypatch)
    doc = a.DOCS_DIR / "00-system-architecture.md"
    doc.write_text("见 `L2-infra/components/real-broken-xyz/` 详情\n", encoding="utf-8")
    r = a._p2_path_broken()
    assert r["status"] == "⚠️" and "real-broken-xyz" in r["detail"]


def test_p5_ignores_test_fixture_files(tmp_path, monkeypatch):
    """tests/ 下文件里的历史路径是夹具数据，不算代码残留。"""
    _isolate(tmp_path, monkeypatch)
    tdir = tmp_path / "L2-infra" / "components" / "x" / "tests"
    tdir.mkdir(parents=True)
    (tdir / "test_fixture.py").write_text(
        "p = 'workspace/model-scheduling/scripts'\n", encoding="utf-8")
    assert a._p5_hardcoded_root()["status"] == "✅"


def test_p6_exclusions_in_git_repo(tmp_path, monkeypatch):
    """P6 在真实 git 仓库下：vendor/min/版本/fork 排除，且 gitignored data 不被扫。"""
    _isolate(tmp_path, monkeypatch)
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=str(tmp_path), check=True)
    (tmp_path / ".gitignore").write_text("data/\n", encoding="utf-8")

    def put(rel: str, data: bytes) -> None:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    V = b"v" * 2048
    M = b"m" * 2048
    C = b"c" * 2048
    F = b"f" * 2048
    D = b"d" * 2048

    # vendor 目录重复（排除）
    put("L2-infra/components/x/vendor/lib.js", V)
    put("L3-business/components/y/vendor/lib.js", V)
    # .min.js 重复（排除）
    put("L2-infra/components/a/web/foo.min.js", M)
    put("L4-proprietary/components/b/web/foo.min.js", M)
    # v1/v2 版本代际重复（排除）
    put("L4-proprietary/components/dc/src/dc/v1/config/a.json", C)
    put("L4-proprietary/components/dc/src/dc/v2/config/a.json", C)
    # L3 引擎 ↔ L4 src 内 fork 副本（排除）
    put("L3-business/components/engine/services/cat.py", F)
    put("L4-proprietary/components/inst/src/inst/services/cat.py", F)
    # gitignored data 副本 vs tracked 副本：data 不应被扫
    put("L4-proprietary/components/bdms/data/x.bin", D)
    put("L2-infra/components/z/keep.bin", D)

    subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), check=True)
    # 明确 data 文件未被跟踪
    assert not subprocess.run(
        ["git", "ls-files", "--error-unmatch",
         "L4-proprietary/components/bdms/data/x.bin"],
        cwd=str(tmp_path), capture_output=True).returncode == 0

    r = a._p6_duplicate_assets()
    assert r["status"] == "✅", r["detail"]


# ── 汇总 ──────────────────────────────────────────────────────────────

def test_audit_asset_consistency_returns_six_checks(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(a, "_count_discovered_components", lambda: "41")
    monkeypatch.setattr(a, "_count_inventory_components", lambda: 41)
    res = a.audit_asset_consistency()
    assert len(res) == 6
    names = [r["name"] for r in res]
    assert "P1 计数漂移" in names and "P6 重复资产" in names
    for r in res:
        assert r["status"] in ("✅", "⚠️")
