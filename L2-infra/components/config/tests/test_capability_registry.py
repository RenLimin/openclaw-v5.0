"""能力注册表引擎测试。

覆盖：加载 / 查询打分 / 门禁检测 / 白名单 / 建议准确性。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

COMP_DIR = Path(__file__).resolve().parent.parent
SCRIPT = COMP_DIR / "capability-registry" / "capability_registry.py"

spec = importlib.util.spec_from_file_location("cr", SCRIPT)
cr = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["cr"] = cr
spec.loader.exec_module(cr)


@pytest.fixture()
def reg():
    return cr.load_registry()


def test_load_registry(reg):
    assert reg.version == 1
    assert len(reg.capabilities) >= 10
    ids = {c.id for c in reg.capabilities}
    assert {"ones-export", "oa-session", "github-credential"} <= ids


def test_query_exact_id(reg):
    hits = cr.query(reg, "ones-export")
    assert hits[0][1].id == "ones-export"


def test_query_alias_ones(reg):
    """'ones' 应命中 ONES 能力，且 ones-export 排名靠前。"""
    hits = cr.query(reg, "ones")
    assert hits
    assert any(c.id == "ones-export" for _, c in hits)


def test_query_oa(reg):
    hits = cr.query(reg, "oa")
    assert hits
    assert any(c.id.startswith("oa-") for _, c in hits)


def test_query_miss_returns_empty(reg):
    assert cr.query(reg, "完全不存在的关键词xyz") == []


def test_every_capability_has_callable_entry(reg):
    """每个能力必须有可直接调用的入口（禁止「见文档」式指针）。"""
    for c in reg.capabilities:
        assert c.entry, f"{c.id} 缺少入口"
        for e in c.entry:
            assert "见文档" not in e, f"{c.id} 入口不可执行: {e}"


def test_detect_export_ones_duplicate(reg):
    hits = cr.detect_duplicates(reg, ["L4-proprietary/components/bdms/scripts/export_ones_202609.py"])
    assert len(hits) == 1
    assert "ones-export" in hits[0]["suggestion"]


def test_detect_diag_iam_duplicate(reg):
    hits = cr.detect_duplicates(reg, ["L4-proprietary/components/bdms/scripts/diag_iam_login.py"])
    assert hits
    assert "ones-auth" in hits[0]["suggestion"]


def test_detect_oa_export_duplicate(reg):
    hits = cr.detect_duplicates(reg, ["L4-proprietary/components/bdms/scripts/oa_export_v2.py"])
    assert hits
    assert "oa-ledger-export" in hits[0]["suggestion"]


def test_allowlist_bypasses(reg):
    allowed_path = "L4-proprietary/components/bangcle-contract/scripts/reconcile_oa.py"
    assert cr._is_allowed(reg, allowed_path)


def test_non_py_ignored(reg):
    assert cr.detect_duplicates(reg, ["L4-proprietary/components/bdms/scripts/readme.md"]) == []


def test_supersedes_paths_are_recorded(reg):
    cap = next(c for c in reg.capabilities if c.id == "ones-export")
    assert any("export_ones_202609.py" in p for p in cap.supersedes)


# ── 覆盖率校验（--coverage）──

def test_all_assets_registered(reg):
    """硬指标：仓库内每个组件/skill 都必须在注册表有条目。"""
    assets = cr._discover_assets()
    registered = cr._registered_names(reg)
    missing = [c for c in assets["components"] if c not in registered]
    missing += [s for s in assets["skills"] if s not in registered]
    assert not missing, f"未登记资产（会被误判能力缺失 → 重复建设）: {missing}"


def test_registered_names_normalize_skill_prefix(reg):
    names = cr._registered_names(reg)
    assert "ones-browser-export" in names  # skill-ones-browser-export 归一
    assert "ones-export" in names


def test_discover_assets_finds_known_dirs():
    assets = cr._discover_assets()
    assert "credentials" in assets["components"]
    assert "delivery-center" in assets["components"]
    assert "knowledge-base" in assets["components"]
    assert "ones-browser-export" in assets["skills"]


def test_coverage_cli_exit_zero(reg, capsys):
    rc = cr.cmd_coverage(type("A", (), {"json": False})(), reg)
    out = capsys.readouterr().out
    assert rc == 0
    assert "100.0%" in out


def test_every_capability_entry_executable(reg):
    """entry 必须是可直接调用的路径/命令，禁止「见文档」类指针。"""
    for c in reg.capabilities:
        assert c.entry, f"{c.id} 缺 entry"
        for e in c.entry:
            assert "见文档" not in e, f"{c.id} entry 不可执行: {e}"
            assert "见 " not in e, f"{c.id} entry 不可执行: {e}"


def test_no_duplicate_capability_ids(reg):
    ids = [c.id for c in reg.capabilities]
    dupes = {i for i in ids if ids.count(i) > 1}
    assert not dupes, f"重复能力 id: {dupes}"


# ── 注册表自校验（--validate）──

def test_validate_all_entries_exist(reg):
    """硬指标：所有 entry 路径必须真实存在（无孤儿 entry）。"""
    rc = cr.cmd_validate(type("A", (), {"json": False})(), reg)
    assert rc == 0


def test_validate_detects_broken_path(reg, monkeypatch):
    """构造一个不存在的 entry，校验必须报错。"""
    original = reg.capabilities[0].entry
    reg.capabilities[0].entry = ["python3 L4-proprietary/components/does_not_exist_xyz.py"]
    try:
        rc = cr.cmd_validate(type("A", (), {"json": False})(), reg)
        assert rc == 1
    finally:
        reg.capabilities[0].entry = original


def test_validate_detects_unexecutable_pointer(reg):
    """entry 禁止「见文档」类不可执行指针。"""
    original = reg.capabilities[0].entry
    reg.capabilities[0].entry = ["见 DESIGN.md"]
    try:
        rc = cr.cmd_validate(type("A", (), {"json": False})(), reg)
        assert rc == 1
    finally:
        reg.capabilities[0].entry = original


# ── 生命周期闭环（--lifecycle）──

def test_lifecycle_new_only_reports_nothing_when_clean(reg, monkeypatch):
    """暂存区无新增资产目录时，报告 0 个且退出 0（hermetic：屏蔽真实 git 状态）。"""
    monkeypatch.setattr(cr, "_new_asset_dirs", lambda: set())
    rc = cr.cmd_lifecycle(type("A", (), {"new_only": True, "require_design": True})(), reg)
    assert rc == 0


def test_lifecycle_detects_missing_design(reg, tmp_path):
    """新增资产缺设计文档 → require_design 时阻断。"""
    fake_root = tmp_path / "ws"
    (fake_root / "L2-infra" / "components" / "new-asset").mkdir(parents=True)
    (fake_root / "L2-infra" / "components" / "new-asset" / "main.py").write_text("x")
    monkey_dir = cr.REPO_ROOT
    cr.REPO_ROOT = fake_root
    try:
        rc = cr.cmd_lifecycle(type("A", (), {"new_only": False, "require_design": True})(), reg)
        assert rc == 1
    finally:
        cr.REPO_ROOT = monkey_dir


def test_lifecycle_new_only_flags_new_asset_missing_design(reg, monkeypatch, tmp_path):
    """--new-only 只对真正新增且缺设计文档的资产生效。"""
    fake = tmp_path / "ws"
    (fake / "L2-infra" / "components" / "brand-new-asset").mkdir(parents=True)
    (fake / "L2-infra" / "components" / "brand-new-asset" / "main.py").write_text("x")
    old_root = cr.REPO_ROOT
    cr.REPO_ROOT = fake
    monkeypatch.setattr(cr, "_new_asset_dirs", lambda: {"L2-infra/components/brand-new-asset"})
    try:
        rc = cr.cmd_lifecycle(type("A", (), {"new_only": True, "require_design": True})(), reg)
        assert rc == 1
    finally:
        cr.REPO_ROOT = old_root


def test_lifecycle_existing_asset_not_flagged(reg, monkeypatch, tmp_path):
    """存量资产（new_dirs 不含）在 --new-only 下不报缺设计。"""
    fake = tmp_path / "ws"
    (fake / "L2-infra" / "components" / "old-asset").mkdir(parents=True)
    (fake / "L2-infra" / "components" / "old-asset" / "main.py").write_text("x")
    old_root = cr.REPO_ROOT
    cr.REPO_ROOT = fake
    monkeypatch.setattr(cr, "_new_asset_dirs", lambda: set())
    try:
        rc = cr.cmd_lifecycle(type("A", (), {"new_only": True, "require_design": True})(), reg)
        assert rc == 0
    finally:
        cr.REPO_ROOT = old_root


def test_lifecycle_recursive_finds_docs_in_subdir(reg, monkeypatch, tmp_path):
    """递归：docs/ 子目录下的 DESIGN/VERIFICATION 必须被识别（防误报）。"""
    fake = tmp_path / "ws"
    (fake / "L2-infra" / "components" / "subdoc-asset" / "docs").mkdir(parents=True)
    (fake / "L2-infra" / "components" / "subdoc-asset" / "docs" / "DESIGN-v1.0.md").write_text("d")
    (fake / "L2-infra" / "components" / "subdoc-asset" / "docs" / "VERIFICATION-v1.0.md").write_text("v")
    old_root = cr.REPO_ROOT
    cr.REPO_ROOT = fake
    try:
        rc = cr.cmd_lifecycle(type("A", (), {"new_only": False, "require_design": True})(), reg)
        assert rc == 0
    finally:
        cr.REPO_ROOT = old_root


# ── health 探针门禁（可调用性硬指标）──

def test_validate_runs_health_probes_and_passes(monkeypatch):
    """登记 health 探针后，--validate 必须真实执行它。"""
    monkeypatch.setattr(cr, "_run_health_probe", lambda cmd, t: (True, "ok"))
    cap = reg_cap = cr.load_registry()
    target = next(c for c in cap.capabilities if c.id == "browser-automation")
    target.health = ["python3 fake.py --probe"]
    try:
        rc = cr.cmd_validate(type("A", (), {"skip_health": False})(), cap)
        assert rc == 0
    finally:
        target.health = []


def test_validate_fails_when_health_probe_fails(monkeypatch):
    """探针失败 = 阻断（可调用性不达标）。"""
    monkeypatch.setattr(cr, "_run_health_probe", lambda cmd, t: (False, "boom"))
    cap = cr.load_registry()
    target = next(c for c in cap.capabilities if c.id == "browser-automation")
    target.health = ["python3 fake.py --probe"]
    try:
        rc = cr.cmd_validate(type("A", (), {"skip_health": False})(), cap)
        assert rc == 1
    finally:
        target.health = []


def test_validate_skip_health_escape_hatch(monkeypatch):
    """--skip-health 必须跳过探针（仅验路径）。"""
    def boom(cmd, t):
        raise AssertionError("不该执行探针")
    monkeypatch.setattr(cr, "_run_health_probe", boom)
    cap = cr.load_registry()
    target = next(c for c in cap.capabilities if c.id == "browser-automation")
    target.health = ["python3 fake.py --probe"]
    try:
        rc = cr.cmd_validate(type("A", (), {"skip_health": True})(), cap)
        assert rc == 0
    finally:
        target.health = []


def test_health_probe_timeout_is_fail_closed(monkeypatch):
    """探针超时不得静默放行（fail-closed）。"""
    import subprocess as sp

    def slow(*a, **k):
        raise sp.TimeoutExpired(a[0] if a else "cmd", 0.1)
    monkeypatch.setattr(cr.subprocess, "run", slow)
    ok, msg = cr._run_health_probe("sleep 99", 0.1)
    assert ok is False
    assert "超时" in msg


def test_health_probe_missing_command_is_fail_closed(monkeypatch):
    """命令不存在（OSError）同样判失败，不得静默放行。"""
    import subprocess as sp

    def boom(*a, **k):
        raise sp.TimeoutExpired("x", 1) if False else OSError("no such binary")
    monkeypatch.setattr(cr.subprocess, "run", boom)
    ok, msg = cr._run_health_probe("definitely_not_a_real_cmd_xyz", 1)
    assert ok is False
    assert "无法执行" in msg


# ── 新增资产可调用性探针强制（--require-health）──

def _fake_ws(tmp_path, name="brand-new-asset"):
    """构造 fake 仓库：一个新资产目录（含 DESIGN 文档，避免被文档检查先拦）。"""
    root = tmp_path / "ws"
    d = root / "L2-infra" / "components" / name
    d.mkdir(parents=True)
    (d / "main.py").write_text("x")
    (d / "DESIGN.md").write_text("d")
    return root, f"L2-infra/components/{name}"


def _lifecycle_args(**kw):
    base = {"new_only": True, "require_design": True,
            "require_health": True, "skip_health_requirement": False}
    base.update(kw)
    return type("A", (), base)()


def test_lifecycle_require_health_blocks_asset_without_probe(monkeypatch, tmp_path):
    """新增资产无 health 探针且无豁免理由 → 阻断（entry 存在 ≠ 可用）。"""
    root, key = _fake_ws(tmp_path)
    old = cr.REPO_ROOT
    cr.REPO_ROOT = root
    monkeypatch.setattr(cr, "_new_asset_dirs", lambda: {key})
    cap = cr.load_registry()
    cap.capabilities.append(cr.Capability(
        id="brand-new-asset", name="新资产", layer="L2", entry=["python3 x.py"]))
    try:
        assert cr.cmd_lifecycle(_lifecycle_args(), cap) == 1
    finally:
        cr.REPO_ROOT = old


def test_lifecycle_require_health_passes_with_probe(monkeypatch, tmp_path):
    """新增资产已登记 health 探针 → 通过（不实际执行，执行由 --validate 负责）。"""
    root, key = _fake_ws(tmp_path)
    old = cr.REPO_ROOT
    cr.REPO_ROOT = root
    monkeypatch.setattr(cr, "_new_asset_dirs", lambda: {key})
    cap = cr.load_registry()
    cap.capabilities.append(cr.Capability(
        id="brand-new-asset", name="新资产", layer="L2",
        entry=["python3 x.py"], health=["python3 x.py --probe"]))
    try:
        assert cr.cmd_lifecycle(_lifecycle_args(), cap) == 0
    finally:
        cr.REPO_ROOT = old


def test_lifecycle_require_health_passes_with_exempt_reason(monkeypatch, tmp_path):
    """无探针但写明豁免理由 → 通过（可审计，不得留空绕过）。"""
    root, key = _fake_ws(tmp_path)
    old = cr.REPO_ROOT
    cr.REPO_ROOT = root
    monkeypatch.setattr(cr, "_new_asset_dirs", lambda: {key})
    cap = cr.load_registry()
    cap.capabilities.append(cr.Capability(
        id="brand-new-asset", name="新资产", layer="L2",
        entry=["python3 x.py"], health_exempt="纯文档型 skill，无稳定可执行入口"))
    try:
        assert cr.cmd_lifecycle(_lifecycle_args(), cap) == 0
    finally:
        cr.REPO_ROOT = old


def test_lifecycle_require_health_escape_hatch(monkeypatch, tmp_path):
    """--skip-health-requirement 应急跳过（须显式传参）。"""
    root, key = _fake_ws(tmp_path)
    old = cr.REPO_ROOT
    cr.REPO_ROOT = root
    monkeypatch.setattr(cr, "_new_asset_dirs", lambda: {key})
    cap = cr.load_registry()
    cap.capabilities.append(cr.Capability(
        id="brand-new-asset", name="新资产", layer="L2", entry=["python3 x.py"]))
    try:
        assert cr.cmd_lifecycle(
            _lifecycle_args(skip_health_requirement=True), cap) == 0
    finally:
        cr.REPO_ROOT = old


def test_capability_health_exempt_field_parses():
    """registry.yaml 的 health_exempt 必须能解析进 Capability。"""
    cap = cr.Capability(id="x", name="X", layer="L2", health_exempt="无稳定入口")
    assert cap.health_exempt == "无稳定入口"
    assert cap.health == []

# ── 口径单一事实源（enumerate_assets）回归 ──
# 事故 2026-11-25/26：health_check 与 system_full_audit 各自 iterdir 判定，
# 导致 .deprecated 被计入组件、design 文档误判。此处锁定公共 API 行为。

def _fake_asset_root(tmp_path):
    """造一个含真实/隐藏/缓存/废弃目录的假仓库根。"""
    root = tmp_path / "ws"
    for rel in ("L2-infra/components/real-comp",
                "L2-infra/skills/real-skill",
                "L4-proprietary/components/legacy"):
        (root / rel).mkdir(parents=True)
    # 应被排除的噪声目录
    (root / "L2-infra/components/.deprecated").mkdir()
    (root / "L2-infra/components/node_modules").mkdir()
    (root / "L2-infra/components/__pycache__").mkdir()
    (root / "L2-infra/components/.git").mkdir()
    (root / "L2-infra/components/.hidden").mkdir()
    return root


def test_is_real_asset_dir_semantics(tmp_path):
    root = _fake_asset_root(tmp_path)
    c = root / "L2-infra/components"
    assert cr.is_real_asset_dir(c / "real-comp")
    for bad in ("node_modules", "__pycache__", ".git", ".hidden"):
        assert not cr.is_real_asset_dir(c / bad), bad


def test_enumerate_assets_excludes_noise(tmp_path):
    """核心锁：枚举结果不含 .deprecated/node_modules/__pycache__/.git/隐藏目录。"""
    rows = cr.enumerate_assets(root=_fake_asset_root(tmp_path))
    names = [d.name for _, _, d in rows]
    assert "real-comp" in names and "real-skill" in names
    for noise in ("node_modules", "__pycache__", ".git", ".hidden"):
        assert noise not in names, f"噪声目录混入: {noise}"


def test_enumerate_assets_layer_and_kind_filter(tmp_path):
    root = _fake_asset_root(tmp_path)
    rows = cr.enumerate_assets(root=root)
    layers = {l for l, _, _ in rows}
    kinds = {k for _, k, _ in rows}
    assert layers == {"L2-infra", "L4-proprietary"}          # 只扫 L2/L3/L4，无 L1
    assert kinds == {"components", "skills"}
    comps = [d.name for _, k, d in cr.enumerate_assets("components", root=root)]
    assert "real-comp" in comps and "legacy" in comps and "real-skill" not in comps


def test_discover_assets_single_source_of_truth(tmp_path):
    """_discover_assets 必须与 enumerate_assets 同口径（防再次分叉）。"""
    root = _fake_asset_root(tmp_path)
    disc = cr._discover_assets(root=root)
    rows = cr.enumerate_assets(root=root)
    assert disc["components"] == sorted({d.name for _, k, d in rows if k == "components"})
    assert disc["skills"] == sorted({d.name for _, k, d in rows if k == "skills"})
    assert ".deprecated" not in disc["components"]


def test_default_root_is_repo_root():
    """不传 root 时默认扫描真实仓库根（REPO_ROOT），且口径与显式传参一致。"""
    rows = cr.enumerate_assets()
    names = {d.name for _, k, d in rows if k == "components"}
    assert {"config", "credentials"} <= names
    # 与显式 root 结果一致（同口径）
    assert {d.name for _, _, d in cr.enumerate_assets(root=cr.REPO_ROOT)} == \
           {d.name for _, _, d in rows}


def test_scope_exemptions_declared_and_on_disk(reg):
    """豁免清单非空、路径真实存在（防写不存在路径绕过门禁）。"""
    ex = reg.scope_exemptions
    assert ex, "scope_exemptions 未加载"
    for x in ex:
        assert (cr.REPO_ROOT / x["path"]).is_dir(), f"豁免路径不存在: {x['path']}"
        assert (x.get("reason") or "").strip(), f"豁免缺理由: {x['path']}"


def test_coverage_reports_exemptions(reg, capsys):
    """--coverage 必须显性列出范围豁免（否则后续会话当缺口重复排查）。"""
    rc = cr.cmd_coverage(type("A", (), {"json": False})(), reg)
    out = capsys.readouterr().out
    assert rc == 0
    assert "范围豁免" in out
    assert any(x["path"].split("/")[-1] in out for x in reg.scope_exemptions)


def test_lifecycle_reports_exemptions(reg, capsys):
    rc = cr.cmd_lifecycle(type("A", (), {"new_only": False, "require_design": True})(), reg)
    out = capsys.readouterr().out
    assert rc == 0
    assert "范围豁免" in out
