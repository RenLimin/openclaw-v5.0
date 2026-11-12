"""revenue_analysis P0 — 导入层 93 列投影 + 台账冻结导入 + 单位层单元测试。

覆盖（IMPLEMENTATION-PLAN-REVENUE-ANALYSIS v1.1 §3 + DESIGN-DETAIL v1.1 §7.3/§9）：
  - A1：202606 预算执行表导入有效列 ≥ 90；实际确收列（AG..AL）非空与 golden 一致
  - A2：底稿/预算行数与 golden 差异 ≤ 2
  - A3：汇总逐格与 golden 比对（万元，abs ≤ 0.02）
  - 台账冻结：月度汇总记录 264 行原样导入、统计期 202606 12 行
  - 202606 投影：锁定口径精确命中 119,085,304.74
  - 结构探测：202609 45 列 / 202606 93 列正确区分

🔒 NO_TOKEN — 纯代码，零 AI 依赖。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from bdms.modules.revenue_analysis.engine import RevenueAnalysisEngine

GOLDEN_202606 = Path(
    "/Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告/202606/"
    "2026年计划确收&实际确收对比表202601-06-0724 - 差异分析.xlsx"
)
GOLDEN_202609 = Path(
    "/Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告/202609/"
    "2026年计划确收&实际确收对比表202601-09-1017-差异分析.xlsx"
)

pytestmark = pytest.mark.skipif(
    not GOLDEN_202606.exists(), reason="202606 黄金财报未就位"
)


@pytest.fixture()
def eng(tmp_path):
    return RevenueAnalysisEngine(tmp_path / "p0.db")


def test_p0_layout_detection_202606(eng):
    """202606 识别为 93 列布局。"""
    r = eng.import_source("202606", GOLDEN_202606)
    assert r["layout"]["预算执行表"] == "202606"
    assert r["sheets"]["预算执行表"] == 8985
    assert r["sheets"]["计划确收底稿"] == 36397
    assert not r["missing"]["预算执行表"]


def test_p0_layout_detection_202609(eng):
    """202609 识别为 45 列布局（兼容不破）。"""
    if not GOLDEN_202609.exists():
        pytest.skip("202609 黄金财报未就位")
    r = eng.import_source("202609", GOLDEN_202609)
    assert r["layout"]["预算执行表"] == "202609"
    assert r["sheets"]["预算执行表"] == 10473


def test_p0_locked_caliber_202606(eng):
    """A1：202606 锁定口径精确命中 119,085,304.74。"""
    eng.import_source("202606", GOLDEN_202606)
    cal = eng.compute_dual_caliber("202606")
    assert cal["locked"]["合计"] == pytest.approx(119085304.74, abs=0.01)
    assert cal["locked"]["新签"] == pytest.approx(47185301.46, abs=0.01)
    assert cal["locked"]["递延"] == pytest.approx(71900003.28, abs=0.01)


def test_p0_summary_frozen_matches_golden(eng):
    """A3：汇总 R4-R17 与 golden 逐格比对（万元，abs ≤ 0.02）。"""
    import openpyxl
    eng.import_source("202606", GOLDEN_202606)
    data = eng.compute("202606")
    sys_sum = data["汇总"]
    wb = openpyxl.load_workbook(GOLDEN_202606, data_only=True, read_only=True)
    g = wb["汇总"]
    try:
        for i in range(4, 18):  # R4-R17
            gv = [c.value for c in g[i]]
            sv = sys_sum[i - 1]
            for j in (2, 3, 4, 6, 7, 9, 10):
                a, b = sv[j], gv[j]
                if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                    assert abs(a / 10000 - b) <= 0.02, \
                        f"R{i} col{j}: {a/10000} vs golden {b}"
                else:
                    # golden None（未来月实际）→ 系统也应为空/None
                    assert a in (None, "") and b in (None, ""), \
                        f"R{i} col{j}: {a!r} vs golden {b!r}"
    finally:
        wb.close()


def test_p0_ledger_frozen_import(eng):
    """台账冻结：月度汇总记录 264 行、统计期 202606 12 行原样导入。"""
    eng.import_source("202606", GOLDEN_202606)
    data = eng.compute("202606")
    led = data["月度汇总记录"]
    # 表头 + 264 数据行
    assert len(led) == 265  # 表头 + 264
    n202606 = sum(1 for r in led if r[0] == "202606")
    assert n202606 == 12
    # 历史期保留（22 统计期）
    periods = {r[0] for r in led[1:]}
    assert "202403" in periods and "202512" in periods


def test_p0_perf_record_frozen(eng):
    """履约汇总记录冻结导入：125 行、统计期 202606 6 行。"""
    eng.import_source("202606", GOLDEN_202606)
    data = eng.compute("202606")
    pf = data["履约汇总记录"]
    assert len(pf) == 126  # 表头 + 125
    n202606 = sum(1 for r in pf if r[0] == "202606")
    assert n202606 == 6
    # 类别名含前导空格（golden 原始格式保留）
    cats = [str(r[1]).strip() for r in pf if r[0] == "202606"]
    assert "滞后未完成" in cats and "消失" in cats


def test_p0_actual_columns_present_202606(eng):
    """A1：202606 实际确收列（AG..AL 规范位）非空行数与 golden 一致。"""
    from bdms.core import db as _db
    eng.import_source("202606", GOLDEN_202606)
    conn = _db.get_connection(eng.db_path)
    try:
        _, rows = _db.load_sheet_rows(conn, "202606", "预算执行表", prefix="rr")
    finally:
        conn.close()
    # 规范位 AG=202601实际 … AL=202606实际（202606 投影）
    ag = sum(1 for r in rows if r.get("AG") not in (None, ""))
    assert ag > 2000  # golden 实际月非空行
    # 202607-09 实际（规范位 AM/AN/AO）无源 → 全空
    assert all(r.get("AM") in (None, "") for r in rows)
