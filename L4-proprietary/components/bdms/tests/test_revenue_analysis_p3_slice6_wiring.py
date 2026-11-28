"""P3 切片6：BQ 落库 + OA/ONES 信号装载接线（DESIGN-DETAIL v1.1 §3.5/§3.6）

锁定三处实证缺口（2026-11-27）：
① apply_bucket_rules 硬编码只判 BU → budget_fill 从未落库；
② compute() 不传 OA/ONES 信号 → ②③④ 桶永远 fail-closed；
③ _resolve_ones_export 单月回退 → 202606 的 634 行新签合同被假阴性为
   「无法匹配」（时间错配），误判「已下单但无法交付」。

口径红线：DB 行键为规范字母（G=履约ID、BU=预算趋势、BQ=预算填报）；
信号缺失 fail-closed；规则不得覆盖继承/人工值。
"""

import csv
from pathlib import Path

import pytest

from bdms.modules.base import ImportError_
from bdms.modules.revenue_analysis.engine import RevenueAnalysisEngine as E


@pytest.fixture
def eng(tmp_path):
    return E(tmp_path / "p3s6.db")


# ─── ① BQ 列落库 ───

def test_apply_bucket_rules_bq_writes_budget_fill(eng):
    """BQ 规则结果必须写入 budget_fill，而非 budget_trend。"""
    eng._load_sheet_rows = lambda p, s: [
        {"G": "A", "B": "C1", "M": 202603, "N": 202609, "O": 202609},
    ]
    r = eng.apply_bucket_rules("202606", column="BQ")
    assert r["results"] == {"A": "本年度正常可确收"}
    assert eng.load_buckets("202606", column="BQ") == {"A": "本年度正常可确收"}
    # BU 列不得被 BQ 规则污染
    assert eng.load_buckets("202606") == {}


def test_apply_default_column_is_bu(eng):
    """默认列保持 BU（向后兼容冻结契约）。"""
    eng._load_sheet_rows = lambda p, s: [{"G": "A", "B": "C1", "BX": 202612}]
    eng.apply_bucket_rules("202606")
    assert eng.load_buckets("202606") == {"A": "本年度正常可确收"}


def test_persist_bq_does_not_clobber_bu(eng):
    """双列共用一行：先写 BU 再写 BQ 不得清掉 BU。"""
    eng.persist_buckets("202606", {
        "total": 1, "inherited": 0, "prev": None,
        "result": {"A": "未来可确收"}})
    eng.persist_buckets("202606", {
        "total": 1, "inherited": 0, "prev": None,
        "result": {"A": "本年度正常可确收"}}, column="BQ")
    import sqlite3
    con = sqlite3.connect(eng.db_path)
    row = con.execute(
        "SELECT budget_trend, budget_fill FROM ra_bucket "
        "WHERE period='202606' AND perf_id='A'").fetchone()
    con.close()
    assert tuple(row) == ("未来可确收", "本年度正常可确收")


def test_inherit_bq_column(eng):
    """BQ 继承按履约ID取上期 budget_fill。"""
    eng._load_sheet_rows = lambda p, s: (
        [{"G": "X", "BQ": "未来可确收"}] if p == "202605"
        else [{"G": "X"}, {"G": "Y"}])
    eng._prev_period = lambda period: "202605"
    r = eng.inherit_previous_buckets("202606", column="BQ")
    assert r["inherited"] == 1 and r["blank"] == 1
    assert r["result"]["X"] == "未来可确收"


# ─── ② 信号装载（fail-closed）───

def test_load_signals_fail_closed_when_no_sources(eng, monkeypatch):
    """OA 与 ONES 都不可用 → available=False，两字典 None。"""
    eng._load_sheet_rows = lambda p, s: [{"G": "A", "B": "C1"}]
    monkeypatch.setattr(E, "_ones_family_files", staticmethod(lambda: []))
    monkeypatch.setattr(E, "_read_oa_order_map",
                        lambda self, cands: None)
    sig = eng.load_bucket_signals("202606")
    assert sig["available"] is False
    assert set(sig["missing_sources"]) == {"oa", "ones"}
    assert sig["oa_ordered"] is None and sig["ones_matched"] is None


def test_load_signals_partial_source_is_not_available(eng, monkeypatch):
    """只接一个源 → 仍不可用（禁止用另一源推断，§3.5）。"""
    eng._load_sheet_rows = lambda p, s: [{"G": "A", "B": "C1"}]
    monkeypatch.setattr(E, "_ones_family_files", staticmethod(lambda: []))
    monkeypatch.setattr(E, "_read_oa_order_map",
                        lambda self, cands: {"C1": True})
    sig = eng.load_bucket_signals("202606")
    assert sig["available"] is False
    assert sig["oa_ordered"] == {"C1": True}
    assert sig["ones_matched"] is None
    assert sig["missing_sources"] == ["ones"]


def test_read_oa_order_map_from_db(tmp_path, monkeypatch):
    """从指定库读 htbh + 合同下单（y/n），空串归一 False，未知跳过。"""
    import sqlite3
    db = tmp_path / "oa.db"
    con = sqlite3.connect(db)
    con.execute('CREATE TABLE oa_contracts (htbh TEXT, "合同下单（y/n）" TEXT)')
    con.executemany('INSERT INTO oa_contracts VALUES (?,?)', [
        ("C1", "是"), ("C2", "否"), ("C3", ""), ("C4", "未知"), (None, "是"),
    ])
    con.commit(); con.close()
    eng = E(tmp_path / "x.db")
    got = eng._read_oa_order_map([db])
    # 空串按 §3.2「为空或否」归一为 False；NULL/「未知」不可解析 → 跳过
    assert got == {"C1": True, "C2": False, "C3": False}
    assert eng._read_oa_order_map([tmp_path / "nope.db"]) is None


def test_read_oa_empty_string_is_false():
    """OA 空值按 §3.2「为空或否」归一为 False（不得当作未知）。"""
    e = E.__new__(E)
    assert e._is_yes("") is False
    assert e._is_yes(None) is None


# ─── ③ ONES 家族并集 ───

def test_ones_family_excludes_abnormal(tmp_path, monkeypatch):
    """信号源只取「签约项目统计」家族，排除「异常处置」。"""
    base = tmp_path / ".openclaw" / "data" / "ones_exports"
    base.mkdir(parents=True)
    for n in ["202605周报-签约项目统计.csv", "202610周报-签约项目统计.csv",
              "202605-签约项目异常处置.csv"]:
        (base / n).write_text("销售合同编号\n", encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    fam = E._ones_family_files()
    names = [p.name for p in fam]
    assert "202605-签约项目异常处置.csv" not in names
    assert set(names) == {"202605周报-签约项目统计.csv",
                          "202610周报-签约项目统计.csv"}


def test_ones_union_covers_across_snapshots(tmp_path, monkeypatch):
    """多期快照取并集：早期导出缺的合同号由后期补上。"""
    base = tmp_path / ".openclaw" / "data" / "ones_exports"
    base.mkdir(parents=True)
    (base / "202605周报-签约项目统计.csv").write_text(
        "销售合同编号\nOLD1\n", encoding="utf-8")
    (base / "202610周报-签约项目统计.csv").write_text(
        "销售合同编号\nNEW1\nNEW2\n", encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    u = E._read_ones_contract_set(E._ones_family_files())
    assert u == {"OLD1", "NEW1", "NEW2"}


def test_ones_union_no_readable_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert E._read_ones_contract_set([]) is None


# ─── compute 接线 ───

def test_compute_passes_signals_and_populates_both_columns(eng, monkeypatch):
    """compute 后 BU/BQ 双列均落库，且 bucket_result 带 signals。"""
    rows = [
        {"G": "A", "B": "C1", "M": 202603, "N": 202609, "O": 202609},
        {"G": "B", "B": "C2", "BX": 202701},
    ]
    eng._load_budget_rows = lambda p: rows
    eng._load_draft_rows = lambda p: rows
    eng._load_sheet_rows = lambda p, s: rows
    monkeypatch.setattr(E, "load_bucket_signals",
                        lambda self, p: {"available": True, "missing_sources": [],
                                         "oa_ordered": None, "ones_matched": None})
    d = eng.compute("202606")
    br = d["bucket_result"]
    assert "signals" in br and "rules_fill" in br and "inherit_fill" in br
    assert eng.load_buckets("202606", column="BQ").get("A") == "本年度正常可确收"
    assert eng.load_buckets("202606").get("B") == "未来可确收"


def test_compute_signal_loader_failure_does_not_break(eng, monkeypatch):
    """装载器抛异常 → 降级继续生成，不中断主流程。"""
    _rows = [{"G": "A", "B": "C1", "BX": 202612}]
    eng._load_budget_rows = lambda p: _rows
    eng._load_draft_rows = lambda p: _rows
    eng._load_sheet_rows = lambda p, s: _rows
    def boom(self, p):
        raise RuntimeError("oa down")
    monkeypatch.setattr(E, "load_bucket_signals", boom)
    d = eng.compute("202606")
    assert d["bucket_result"]["signals"]["missing_sources"] == ["loader"]
    assert eng.load_buckets("202606") == {"A": "本年度正常可确收"}
