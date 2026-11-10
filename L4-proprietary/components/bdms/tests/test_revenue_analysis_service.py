"""revenue_analysis Phase 5 — Service 层 + CLI 链路单元测试。

覆盖（DESIGN-DETAIL-REVENUE-ANALYSIS-v1.0 §9.2 / §9.6）：
  - RevenueAnalysisService.generate 三模式幂等（auto/read/regenerate）
  - summary / caliber / trend 读 ra_* 快照（fail-closed 无数据报错）
  - export 生成 10 Sheet 工作簿
  - 锚点：锁定 1.3842 亿 / 动态 1.7105 亿 / 差异 .3263 亿
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from bdms.modules.revenue_analysis.service import RevenueAnalysisService

REAL_REPORT = Path(
    "/Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告/202609/"
    "2026年计划确收&实际确收对比表202601-09-1017-差异分析.xlsx"
)
TREND_COLS_REPORT = Path(
    "/Users/bangcle/.openclaw/workspace/L4-proprietary/components/bdms/"
    "tmp/202609_with_trend_cols.xlsx"
)

pytestmark = pytest.mark.skipif(
    not REAL_REPORT.exists(), reason="真实财报未就位"
)


@pytest.fixture()
def svc(tmp_path):
    return RevenueAnalysisService(tmp_path / "ra_test.db")


def test_generate_three_modes_idempotent(svc):
    """三模式幂等：auto→read（import 后宽表在）/ generated，read→read，
    regenerate→generated。"""
    if not TREND_COLS_REPORT.exists():
        # 无计算列产物时用原始财报（trend 计数为 0，但口径表仍生成）
        svc.import_source("202609", REAL_REPORT)
    else:
        svc.import_source("202609", TREND_COLS_REPORT)

    # import 已建宽表 → auto 走 read，但快照由 _ensure_snapshots 兜底补齐
    r1 = svc.generate("202609", "auto")
    assert r1["action"] in ("read", "generated")
    assert svc.summary("202609")["locked"]["total"] > 0  # 快照已生成

    r2 = svc.generate("202609", "read")
    assert r2["action"] == "read"
    assert r2["sheets"]["预算执行表"] == 10473

    r3 = svc.generate("202609", "regenerate")
    assert r3["action"] == "generated"
    assert r3["sheets"]["计划确收底稿"] == 38052


def test_summary_golden_anchors(svc):
    """双口径黄金锚点。"""
    svc.import_source("202609", REAL_REPORT)
    svc.generate("202609", "auto")
    s = svc.summary("202609")
    assert s["locked"]["total"] == pytest.approx(138420136.78, abs=0.01)
    assert s["dynamic"]["total"] == pytest.approx(171048611.81, abs=0.01)
    assert s["difference"] == pytest.approx(32628475.03, abs=0.01)
    assert s["locked"]["by_group"]["新签"] == pytest.approx(66520133.5, abs=0.01)
    assert s["locked"]["by_group"]["递延"] == pytest.approx(71900003.28, abs=0.01)


def test_caliber_snapshot_shape(svc):
    """caliber() 读快照与 engine 同构。"""
    svc.import_source("202609", REAL_REPORT)
    svc.generate("202609", "auto")
    cal = svc.caliber("202609")
    assert cal["locked"]["合计"] == pytest.approx(138420136.78, abs=0.01)
    assert cal["dynamic"]["合计"] == pytest.approx(171048611.81, abs=0.01)
    assert cal["dynamic"]["DUE_2026"] == pytest.approx(86936513.95, abs=0.01)
    assert cal["dynamic"]["IN_PIPELINE"] == pytest.approx(84112097.86, abs=0.01)
    assert cal["difference"] == pytest.approx(32628475.03, abs=0.01)


def test_trend_rows_19(svc):
    """trend() 返回 15 条 ra_trend_row（R4-R19，含 R19 率）。"""
    svc.import_source("202609", TREND_COLS_REPORT if TREND_COLS_REPORT.exists()
                      else REAL_REPORT)
    svc.generate("202609", "auto")
    rows = svc.trend("202609")
    idx = {r["row_index"] for r in rows}
    assert {4, 5, 6, 7, 8, 9, 10, 12, 13, 14, 15, 16, 17, 18, 19} <= idx
    r18 = next(r for r in rows if r["row_index"] == 18)
    assert r18["init_count"] == 2463  # R18 递延+新签共计（202609 实测）
    r19 = next(r for r in rows if r["row_index"] == 19)
    assert r19["recognize_rate_count"] is not None
    # 金额红线：J/K/L 全 0 → 金额一律 None
    assert r18["init_amount_wan"] is None


def test_fail_closed_no_data(svc):
    with pytest.raises(ValueError):
        svc.summary("202609")
    with pytest.raises(ValueError):
        svc.trend("202609")


def test_export_ten_sheets(svc):
    """export() 生成 10 Sheet 工作簿。"""
    from openpyxl import load_workbook
    svc.import_source("202609", REAL_REPORT)
    svc.generate("202609", "auto")
    out = svc.export("202609", tmp := svc.engine.db_path.parent / "out.xlsx")
    assert out.exists()
    wb = load_workbook(out, read_only=True)
    names = wb.sheetnames
    wb.close()
    assert len(names) == 10
    assert "预算执行表" in names and "计划确收底稿" in names
    assert "预算趋势分析" in names and "汇总" in names


def test_list_periods(svc):
    svc.import_source("202609", REAL_REPORT)
    svc.generate("202609", "auto")
    assert "202609" in svc.list_periods()
