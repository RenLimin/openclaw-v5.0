"""revenue_analysis P2 — 趋势修正 + Q1 归因 + Q4 预警 单元测试。

覆盖（IMPLEMENTATION-PLAN-REVENUE-ANALYSIS v1.1 §5.5）：
  - A6：R4-R18 计数/金额对齐 golden（202606 逐格，abs 0.01 万）
  - A7：R19 新签预计确收率 = 0.607421038（golden F19）
  - Q1：109 触发行；规则1（AR=合同终止→当年不可消除+客户原因-终止）9 行；
        规则2（BF=3：交付异常）0 行（触发行无此 BF）；留空 100 行
  - Q4：新签消失 2 行（XSZS2512301176，合计 -905 元）
  - 审计：R9 已知快照差异（golden 缓存 6 vs 源表 4）显式标注，不静默

口径说明：设计 §2.4/§12.4 记「106 触发行」为早期快照口径；
2026-11-17 实测源表为 109（AF>0 或 AD<0），本测试按实测断言。

🔒 NO_TOKEN — 纯代码，零 AI 依赖。
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from bdms.modules.revenue_analysis.engine import RevenueAnalysisEngine
from bdms.modules.revenue_analysis.service import RevenueAnalysisService
from bdms.modules.revenue_analysis.trend_builder import TrendBuilder
from bdms.modules.revenue_analysis.attribution_engine import (
    compute_attribution, trigger_reason, apply_rules,
)
from bdms.modules.revenue_analysis.alert_builder import build_alerts

GOLDEN_202606 = Path(
    "/Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告/202606/"
    "2026年计划确收&实际确收对比表202601-06-0724 - 差异分析.xlsx"
)

pytestmark = pytest.mark.skipif(
    not GOLDEN_202606.exists(), reason="202606 黄金财报未就位"
)

# golden 预算趋势分析 R4-R18（计数 + 金额万），C15/C16 未立项/已立项
GOLDEN_TREND = {
    4:  (6, 99.988645, 0, 0, 6, 99.988645, 0, 0, 0, 0, 6, 0),
    5:  (53, 218.031767, 0, 0, 53, 218.031767, 0, 0, 0, 0, 0, 53),
    6:  (6, 208.749999, 0, 0, 6, 208.749999, 0, 0, 0, 0, 0, 6),
    7:  (1248, 7190.000328, 1245, 7179.540332, 1, 2.5, 2, 7.959996, 0, 0, 0, 1),
    8:  (118, 3681.953561, 9, 41.847016, 0, 0, 1, 0, 108, 3640.106545, 0, 0),
    # R9 为 golden 历史缓存（C3=6 硬编码），源表当前为 4 → 断言计算值 + 审计
    12: (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    13: (8, 170.282, 0, 0, 8, 170.282, 0, 0, 0, 0, 0, 8),
    14: (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    15: (513, 4718.530146, 510, 4685.513476, 1, 6.26667, 0, 0, 2, 26.75, 0, 1),
    16: (117, 2835.0329, 1, 6.112503, 0, 0, 0, 0, 116, 2828.920397, 0, 0),
}


# golden 导入一次（8985 行）→ 模块级共享，避免每用例重复解析
_GOLDEN_DIR = Path(tempfile.mkdtemp(prefix="ra_p2_"))
_GOLDEN_ENG = None


def _golden_eng():
    global _GOLDEN_ENG
    if _GOLDEN_ENG is None:
        e = RevenueAnalysisEngine(_GOLDEN_DIR / "p2.db")
        e.import_source("202606", GOLDEN_202606)
        _GOLDEN_ENG = e
    return _GOLDEN_ENG


@pytest.fixture(scope="module")
def eng():
    return _golden_eng()


@pytest.fixture(scope="module")
def lines(eng):
    return eng.compute_budget_trend("202606")


def _row_map(lines):
    rows, cells = TrendBuilder().build(lines)
    return {r["row_index"]: r for r in rows}, cells


# ─── A6：R4-R18 逐格对齐 ───

@pytest.mark.parametrize("row_index", sorted(GOLDEN_TREND))
def test_a6_trend_row_matches_golden(lines, row_index):
    """R4-R18（除 R9）计数 + 金额逐格对齐 golden。"""
    idx, _ = _row_map(lines)
    r = idx[row_index]
    g = GOLDEN_TREND[row_index]
    calc = (r["init_count"], r["init_amount_wan"],
            r["normal_count"], r["normal_amount_wan"],
            r["exception_count"], r["exception_amount_wan"],
            r["disappear_count"], r["disappear_amount_wan"],
            r["future_count"], r["future_amount_wan"],
            r["check_count"], r["check_amount"])
    assert calc[0] == g[0], f"R{row_index} init_count"
    for i in (1, 3, 5, 7, 9):
        assert calc[i] == pytest.approx(g[i], abs=0.01), f"R{row_index} 金额[{i}]"
    assert calc[2] == g[2] and calc[4] == g[4]
    assert calc[6] == g[6] and calc[8] == g[8]
    # 恒等式：期初 = 正常 + 异常 + 消失 + 未来（容差 0.01）
    assert r["check_count"] == 0
    assert r["check_amount"] == pytest.approx(0.0, abs=0.01)


def test_a6_r9_known_snapshot_diff(lines):
    """R9 为 golden 历史缓存差异：计算 4 vs golden 6，审计显式标注。"""
    idx, _ = _row_map(lines)
    r9 = idx[9]
    assert r9["init_count"] == 4          # 源表当前（AW=统计 且 BQ=之前年度已确收）
    audit = r9["routing_audit"]
    assert audit["r9_golden_c3"] == 6
    assert audit["r9_computed_c3"] == 4
    assert "快照" in audit["r9_known_diff"]


def test_a6_r18_total_amount(lines):
    """R18 共计 = golden − R9 快照差异（2075−2=2073；11916.985699−3.972372）。"""
    idx, _ = _row_map(lines)
    r18 = idx[18]
    assert r18["init_amount_wan"] == pytest.approx(19122.569346, abs=0.01)
    # golden 11916.985699 − R9 金额差 3.972372（R9 本年正常交付 golden 3.972372 vs 源表 0）
    assert r18["normal_amount_wan"] == pytest.approx(11913.013327, abs=0.01)
    assert r18["init_count"] == 2073       # golden 2075 − R9 差异 2
    assert r18["normal_count"] == 1765     # golden 1767 − R9 差异 2
    # 与 golden 的差额恰为 R9 已知快照差异（审计闭环）
    assert 11916.985699 - r18["normal_amount_wan"] == pytest.approx(3.972372, abs=0.01)


def test_a6_amount_unit_and_no_redline_for_202606(lines):
    """202606 有权威金额 → amount_pending 为 None（红线只针对 202609）。"""
    for line in lines:
        assert line["amount_unit"] == "万元"
        if line["group"] != "新签" or line["row_label"] != "新签预计确收率":
            assert line["amount_pending"] is None


# ─── A7：R19 确收率 ───

def test_a7_r19_rate_amount(lines):
    """R19 新签预计确收率 = 金额口径 F17/D17 = 0.607421038。"""
    _, cells = _row_map(lines)
    cell_map = {c["col_index"]: json.loads(c["value"]) for c in cells}
    assert cell_map[1]["value"] == pytest.approx(0.607421038, abs=1e-6)


def test_a7_r19_rate_count_audit(lines):
    """R19 数量口径（0.800940）保留为审计值，不与 golden 混淆。"""
    _, cells = _row_map(lines)
    cell_map = {c["col_index"]: json.loads(c["value"]) for c in cells}
    assert cell_map[0]["value"] == pytest.approx(0.8009404389, abs=1e-6)


# ─── Q1：归因引擎 ───

def test_q1_trigger_count(eng):
    """触发条件 AF>0 或 AD<0 → 109 行（2026-11-17 实测）。"""
    rows = _golden_eng()._load_budget_rows("202606")
    attr = compute_attribution(rows)
    assert attr["triggered"] == 109


def test_q1_rule1_terminate(eng):
    """规则1：AR=合同终止 → 状态=当年不可消除 + 原因=客户原因-终止（9 行）。"""
    rows = _golden_eng()._load_budget_rows("202606")
    attr = compute_attribution(rows)
    assert attr["rule_hits"]["rule1_terminate"] == 9
    r1 = [x for x in attr["rows"]
          if x["reason"] == "客户原因-终止"]
    assert len(r1) == 9
    for x in r1:
        assert x["status"] == "差异确收（当年不可消除）"
        assert x["auto_filled"] == 1


def test_q1_rule2_no_hit(eng):
    """规则2：触发行中无 BF=3：交付异常 → 命中 0（golden 异常项目行 BF 为其他值）。"""
    rows = _golden_eng()._load_budget_rows("202606")
    attr = compute_attribution(rows)
    assert attr["rule_hits"]["rule2_exception"] == 0
    assert not any(x["reason"] == "综合原因-项目异常" and x["auto_filled"]
                   for x in attr["rows"])


def test_q1_pending_list(eng):
    """未命中 → 留空 + 人工清单（100 行），含上下文特征。"""
    rows = _golden_eng()._load_budget_rows("202606")
    attr = compute_attribution(rows)
    assert attr["pending"] == 100
    assert attr["auto_filled"] == 9
    assert attr["pair_violations"] == 0
    pend = [x for x in attr["rows"] if not x["auto_filled"]]
    assert len(pend) == 100
    for x in pend:
        assert x["status"] is None and x["reason"] is None
        assert "AF" in x["context"] or "AD" in x["context"]


def test_q1_non_trigger_never_filled():
    """非触发行不进入归因结果（触发条件为唯一门槛）。"""
    rows = [
        {"A": "递延", "B": "C1", "E": "E1", "AF": 0, "AD": 0, "AR": "合同终止"},
        {"A": "递延", "B": "C2", "E": "E2", "AF": 100, "AD": 0},
    ]
    attr = compute_attribution(rows)
    assert attr["triggered"] == 1
    assert attr["rows"][0]["perf_id"] == "E2"


def test_q1_trigger_reason_text():
    """触发说明含命中列与数值。"""
    assert trigger_reason({"AF": 5}) == "AF(滞后未完成)=5>0"
    assert trigger_reason({"AD": -3}) == "AD(确收)=-3<0"
    assert trigger_reason({"AF": 0, "AD": 0}) is None


# ─── Q4：预警 ───

def test_q4_new_sign_disappear(eng):
    """新签消失 2 行（XSZS2512301176），金额不进履约汇总。"""
    rows = _golden_eng()._load_budget_rows("202606")
    attr = compute_attribution(rows)
    alerts = build_alerts(rows, attr)
    nsd = [a for a in alerts if a["alert_type"] == "new_sign_disappear"]
    assert len(nsd) == 2
    assert all(a["contract_no"] == "XSZS2512301176" for a in nsd)
    assert sum(a["amount"] for a in nsd) == pytest.approx(-905.0, abs=0.01)
    assert any("汇率" in a["context"]["note"] or "终止" in a["context"]["note"]
               for a in nsd)


def test_q4_attribution_pending_alerts(eng):
    """归因留空行全部进预警清单。"""
    rows = _golden_eng()._load_budget_rows("202606")
    attr = compute_attribution(rows)
    alerts = build_alerts(rows, attr)
    pend = [a for a in alerts if a["alert_type"] == "attribution_pending"]
    assert len(pend) == attr["pending"] == 100


# ─── 落盘 + Service ───

def test_persist_and_service_roundtrip(tmp_path):
    """generate → ra_attribution / ra_alert 落盘 → service 读回。"""
    svc = RevenueAnalysisService(tmp_path / "rt.db")
    svc.import_source("202606", GOLDEN_202606)
    svc.generate("202606", "auto")

    attr = svc.attribution("202606")
    assert attr["triggered"] == 109
    assert attr["auto_filled"] == 9
    assert len(attr["pending_rows"]) == 100

    alerts = svc.alerts("202606")
    assert len([a for a in alerts
                if a["alert_type"] == "new_sign_disappear"]) == 2


def test_service_fail_closed(tmp_path):
    """无数据 → fail-closed 报错。"""
    svc = RevenueAnalysisService(tmp_path / "fc.db")
    with pytest.raises(ValueError):
        svc.attribution("202606")
    assert svc.alerts("202606") == []


# ─── 202609 红线回归 ───

REAL_202609 = Path(
    "/Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告/202609/"
    "2026年计划确收&实际确收对比表202601-09-1017-差异分析.xlsx"
)


@pytest.mark.skipif(not REAL_202609.exists(), reason="202609 财报未就位")
def test_202609_amount_redline(tmp_path):
    """202609 J/K/L 全 0 → 趋势金额一律 None + amount_pending 标注。"""
    eng = RevenueAnalysisEngine(tmp_path / "r9.db")
    eng.import_source("202609", REAL_202609)
    lines = eng.compute_budget_trend("202609")
    idx, _ = _row_map(lines)
    r18 = idx[18]
    assert r18["init_amount_wan"] is None
    assert r18["amount_pending"] and "J/K/L" in r18["amount_pending"]
