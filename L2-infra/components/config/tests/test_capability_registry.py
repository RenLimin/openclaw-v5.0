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
    allowed_path = "L4-proprietary/components/bdms/scripts/reconcile_oa.py"
    assert cr._is_allowed(reg, allowed_path)


def test_non_py_ignored(reg):
    assert cr.detect_duplicates(reg, ["L4-proprietary/components/bdms/scripts/readme.md"]) == []


def test_supersedes_paths_are_recorded(reg):
    cap = next(c for c in reg.capabilities if c.id == "ones-export")
    assert any("export_ones_202609.py" in p for p in cap.supersedes)
