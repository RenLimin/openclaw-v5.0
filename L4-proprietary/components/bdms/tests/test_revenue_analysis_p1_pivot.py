"""revenue_analysis P1 — 透视引擎（差异分析 + 重拆履约）单元测试。

覆盖（IMPLEMENTATION-PLAN-REVENUE-ANALYSIS v1.1 §4.4）：
  - A4：差异分析 8 类 + 总计逐格对齐 golden（170.58 万，abs 0.01 万）
  - A5：重拆履约 6 合同逐行 + 总计（提前 253.20 / 滞后 181.50 万）
  - pivot_builder 纯函数：group-by 求和 + 行序（Unicode 升序，(空白) 置尾）
  - 标题账期由 period 驱动（202601-{MM}）

🔒 NO_TOKEN — 纯代码，零 AI 依赖。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from bdms.modules.revenue_analysis.engine import RevenueAnalysisEngine
from bdms.modules.revenue_analysis.pivot_builder import pivot, sorted_keys

GOLDEN_202606 = Path(
    "/Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告/202606/"
    "2026年计划确收&实际确收对比表202601-06-0724 - 差异分析.xlsx"
)

pytestmark = pytest.mark.skipif(
    not GOLDEN_202606.exists(), reason="202606 黄金财报未就位"
)


@pytest.fixture()
def eng(tmp_path):
    e = RevenueAnalysisEngine(tmp_path / "p1.db")
    e.import_source("202606", GOLDEN_202606)
    return e


# ─── pivot_builder 纯函数 ───

def test_pivot_group_sum():
    rows = [
        {"k": "a", "v": 1.0}, {"k": "b", "v": 2.0},
        {"k": "a", "v": 3.0}, {"k": "", "v": 4.0},
    ]
    out = pivot(rows, key_fn=lambda r: r["k"] or "(空白)",
                value_fn=lambda r: r["v"])
    assert out == {"a": 4.0, "b": 2.0, "(空白)": 4.0}


def test_pivot_filter():
    rows = [{"k": "a", "v": 1.0, "x": 1}, {"k": "a", "v": 2.0, "x": 0}]
    out = pivot(rows, key_fn=lambda r: r["k"], value_fn=lambda r: r["v"],
                filter_fn=lambda r: r["x"] == 0)
    assert out == {"a": 2.0}


def test_sorted_keys_blank_last():
    keys = {"(空白)", "交付原因-延期", "客户原因-终止", "综合原因-考核扣款"}
    out = sorted_keys(keys)
    assert out[-1] == "(空白)"
    assert out[:-1] == sorted(["交付原因-延期", "客户原因-终止", "综合原因-考核扣款"])


# ─── A4：差异分析 ───

def test_p1_diff_matches_golden(eng):
    """A4：8 类 + 总计逐格对齐 golden（170.58 万）。"""
    import openpyxl
    data = eng.compute("202606")
    sys_diff = data["确收差异分析"]
    wb = openpyxl.load_workbook(GOLDEN_202606, data_only=True, read_only=True)
    g = wb["确收差异分析"]
    try:
        # golden R8-R16：A=行标签 B=递延 C=新签 D=总计
        for i in range(8, 17):
            sv = sys_diff[i - 1]
            gv = [c.value for c in g[i]]
            assert str(sv[0]) == str(gv[0]).strip(), f"R{i} 标签 {sv[0]!r} vs {gv[0]!r}"
            for j in (1, 2, 3):
                a, b = sv[j], gv[j]
                if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                    assert abs(a - b) <= 50, f"R{i} col{j}: {a} vs {b}"
                else:
                    assert (a in (None, "")) == (b in (None, "")), \
                        f"R{i} col{j}: {a!r} vs {b!r}"
    finally:
        wb.close()


def test_p1_diff_total_1705814(eng):
    """差异分析总计 = 1,705,814.84 元（170.58 万）。"""
    data = eng.compute("202606")
    total_row = data["确收差异分析"][-1]
    assert total_row[0] == "总计"
    assert total_row[1] == pytest.approx(1227411.65, abs=0.5)   # 递延
    assert total_row[2] == pytest.approx(478403.19, abs=0.5)    # 新签
    assert total_row[3] == pytest.approx(1705814.84, abs=0.5)   # 总计


def test_p1_diff_title_period(eng):
    """标题账期由 period 驱动。"""
    data = eng.compute("202606")
    assert data["确收差异分析"][5][0] == "求和项:202601-06滞后未完成"


def test_p1_diff_excludes_disappear(eng):
    """AR(消失备注) 非空行不计入差异分析（消失额 109,216.22 不进）。"""
    data = eng.compute("202606")
    # 合计 170.58 万 < 全量 181.50 万（差 = 消失 10.92 万）
    assert data["确收差异分析"][-1][3] == pytest.approx(1705814.84, abs=0.5)


# ─── A5：重拆履约 ───

def test_p1_restructure_matches_golden(eng):
    """A5：6 合同逐行 + 总计对齐 golden。"""
    import openpyxl
    data = eng.compute("202606")
    sys_r = data["重拆履约"]
    wb = openpyxl.load_workbook(GOLDEN_202606, data_only=True, read_only=True)
    g = wb["重拆履约"]
    try:
        for i in range(3, 10):  # R3-R9
            sv = sys_r[i - 1]
            gv = [c.value for c in g[i]]
            assert str(sv[0]) == str(gv[0]), f"R{i} {sv[0]!r} vs {gv[0]!r}"
            for j in (1, 2):
                a, b = sv[j], gv[j]
                if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                    assert abs(a - b) <= 0.5, f"R{i} col{j}: {a} vs {b}"
    finally:
        wb.close()


def test_p1_restructure_total(eng):
    """重拆总计 = 全量 AE/AF（253.20 / 181.50 万），非 6 行合计。"""
    data = eng.compute("202606")
    total_row = data["重拆履约"][-1]
    assert total_row[0] == "总计"
    assert total_row[1] == pytest.approx(2531951.27, abs=0.5)   # 提前全量
    assert total_row[2] == pytest.approx(1815031.06, abs=0.5)   # 滞后全量
    # 6 行合计 ≠ 总计（显示行只含双非零合同）
    six_sum = sum(r[1] for r in data["重拆履约"][2:-1])
    assert abs(six_sum - total_row[1]) > 100000


def test_p1_restructure_only_both_nonzero(eng):
    """显示行仅含双非零合同（提前≠0 且 滞后≠0）。"""
    data = eng.compute("202606")
    rows = data["重拆履约"][2:-1]  # 跳过表头与总计
    assert len(rows) == 6
    for r in rows:
        assert r[1] and r[2], f"{r[0]} 不是双非零"
