"""P5 · 汇总分析 64×50 完整化 + Q5 同比区（DESIGN-DETAIL §6 + 计划 §8）

- 结构：64 行 × 50 列（月度主体 R2-R17 + 同比区 V6:AD6 + 产线展开 + 年度目标）
- Q5 同比区：Y25 同期取自月度台账（SUMIFS 等价逻辑），5 指标 = 销售/确收/确收度/比重/增长率
- 年度目标 r21/r22：DB 优先，缺省回退 config（23000/13340）
"""

import pytest

from bdms.modules.revenue_analysis.service import RevenueAnalysisService


def _build(tmp_path, rows):
    """构造最小预算执行表行集（A=分类、I=金额、D=月份、P..AA=计划月、AG..AO=实际月）。"""
    base = {
        "A": "新签", "B": "C1", "C": "主体", "D": "202606", "E": "P1",
        "G": "P1_01_01", "I": 800.0,
    }
    for i, m in enumerate(["P", "Q", "R", "S", "T", "U", "V", "W",
                           "X", "Y", "Z", "AA"]):
        base[m] = 800.0 if i < 6 else 0.0
    for i, m in enumerate(["AG", "AH", "AI", "AJ", "AK", "AL"]):
        base[m] = 100.0
    out = []
    for r in rows:
        row = dict(base)
        row.update(r)
        out.append(row)
    return out


@pytest.fixture()
def svc(tmp_path):
    return RevenueAnalysisService(tmp_path / "p5.db")


def test_summary_analysis_64_rows(svc, tmp_path):
    rows = _build(tmp_path, [{"D": "202601"}, {"D": "202602"}])
    data = {"月度汇总记录": [], "履约汇总记录": []}
    out = svc.engine._build_summary_analysis(rows, period="202606")
    assert len(out) == 64


def test_summary_analysis_width_50(svc, tmp_path):
    rows = _build(tmp_path, [{"D": "202601"}])
    out = svc.engine._build_summary_analysis(rows, period="202606")
    maxw = max(len(r) for r in out)
    assert maxw == 50


def test_annual_target_row_present(svc, tmp_path):
    rows = _build(tmp_path, [{"D": "202601"}])
    out = svc.engine._build_summary_analysis(rows, period="202606")
    r21 = [r for r in out if r[1] == "年度目标"]
    assert r21, "缺少年度目标行"
    assert r21[0][2] == 23000.0  # config 默认（未设 DB 值）


def test_annual_target_db_priority(svc, tmp_path):
    svc.set_annual_target(2026, 25000.0)
    rows = _build(tmp_path, [{"D": "202601"}])
    out = svc.engine._build_summary_analysis(rows, period="202606")
    r21 = [r for r in out if r[1] == "年度目标"][0]
    assert r21[2] == 25000.0


def test_yoy_area_columns_present(svc, tmp_path):
    """同比区 B 块：col14=类别, 15/16=Y26销售/确收, 21/22=Y25销售/确收, 27/28=增长率。"""
    rows = _build(tmp_path, [{"D": "202601"}])
    out = svc.engine._build_summary_analysis(rows, period="202606")
    # 行6（0基5）新签合同
    b = out[5]
    assert b[14] == "新签合同"
    assert b[15] is not None and b[16] is not None
    # 行8（0基7）合计行：确收度=1
    assert out[7][14] == "合计"
