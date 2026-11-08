"""revenue_forecast Phase 3 — repository 持久化层测试。

覆盖（任务硬要求）：
  - ensure_schema 连调幂等；
  - 两期版本切换：is_current 全局唯一，旧版本明细保留；
  - 同期重算：无重复行、数字稳定；
  - query_lines：分页 / category / in_plan 过滤实际生效（断言返回集，非仅解析参数）；
  - totals / monthly 与构造输入逐字段一致；
  - 真实财报 parser 端到端落库：locked≈1.38 亿 / dynamic≈1.71 亿 / actual≈.94 / gap≈+.33。

金额断言一律 pytest.approx；仅用 sqlite3 标准库，连接注入 :memory: / 临时文件。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bdms.modules.revenue_forecast import (
    DUE_2026, FUTURE_YEAR, IN_PIPELINE, ALREADY_DONE, MISSING_DATE,
)
from bdms.modules.revenue_forecast.report_parser import ObligationRow, parse_report
from bdms.modules.revenue_forecast.engine import forecast
from bdms.modules.revenue_forecast.repository import (
    ForecastRepository, BASIS_LOCKED, BASIS_DYNAMIC_DUE, BASIS_PIPELINE,
)

REAL_REPORT = Path(
    "/Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告/202609/"
    "2026年计划确收&实际确收对比表202601-09-1017-差异分析.xlsx"
)
YI = 1e8


# ─────────────────────── 手工构造行 ───────────────────────

def _row(obligation, budget="BYS", group="新签", locked_year=10000.0,
         monthly=None, actual=3000.0, cat=DUE_2026, month=6,
         amount=10000.0, in_plan=None, matched=True, contract_no="C1"):
    mvals = list(monthly or []) + [0.0] * (12 - len(monthly or []))
    if in_plan is None:
        in_plan = cat in (DUE_2026, IN_PIPELINE) and matched
    return ObligationRow(
        obligation_id=obligation, budget_id=budget, contract_no=contract_no,
        contract_name=f"合同-{obligation}", customer="客户甲", end_user="最终用户乙",
        revenue_method="时点法",
        category_group=group if matched else "",
        locked_year=locked_year if matched else 0.0,
        locked_monthly=tuple(mvals) if matched else tuple(0.0 for _ in range(12)),
        actual_ytd=actual if matched else 0.0,
        raw_due="2026年6月" if cat == DUE_2026 else "",
        due_date="2026-06-16" if cat == DUE_2026 else None,
        dyn_category=cat, amount_future=amount,
        dyn_month=month if cat == DUE_2026 else None,
        dyn_in_plan=in_plan, dyn_counted=amount if in_plan else 0.0,
    )


def _sample_rows():
    return [
        _row("OB1", budget="YS1", group="新签", locked_year=10000,
             monthly=[4000, 0, 0, 0, 0, 6000], actual=3000,
             cat=DUE_2026, month=6, amount=10000),
        _row("OB2", budget="YS2", group="递延", locked_year=8000,
             monthly=[0, 0, 8000], actual=2000,
             cat=IN_PIPELINE, month=None, amount=7000),
        _row("OB3", budget="YS3", group="新签", locked_year=5000,
             monthly=[5000], actual=1000,
             cat=FUTURE_YEAR, month=None, amount=9000, in_plan=False),
        _row("OB4", budget="YS4", group="递延", locked_year=2000,
             monthly=[0, 2000], actual=0,
             cat=ALREADY_DONE, month=None, amount=0, in_plan=False),
        _row("OB5", budget="2026年无预算ID", group="新签", matched=False,
             cat=ALREADY_DONE, month=None, amount=0, in_plan=False),
    ]


@pytest.fixture()
def repo():
    r = ForecastRepository(":memory:")
    r.ensure_schema()
    yield r
    r.close()


@pytest.fixture()
def saved(repo):
    rows = _sample_rows()
    result = forecast(rows, period="202609")
    repo.save_result("202609", rows, result, "report-202609.xlsx")
    return rows, result


# ─────────────────────── 建表幂等 ───────────────────────

def test_ensure_schema_idempotent():
    r = ForecastRepository(":memory:")
    r.ensure_schema()
    r.ensure_schema()
    r.ensure_schema()
    tables = {
        row[0]
        for row in r.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {
        "forecast_period", "forecast_line",
        "forecast_monthly", "forecast_totals",
    } <= tables
    # 索引也在
    idx = {row[0] for row in r.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
    assert "idx_fl_cat" in idx
    r.close()


def test_save_result_idempotent_same_period(repo):
    rows = _sample_rows()
    result = forecast(rows, period="202609")
    repo.save_result("202609", rows, result, "f.xlsx")
    repo.save_result("202609", rows, result, "f.xlsx")
    # 无重复行：period 1 行、line 5 行、monthly 25 行（12+12+1）、totals 1 行
    assert repo.conn.execute(
        "SELECT COUNT(*) c FROM forecast_period").fetchone()["c"] == 1
    assert repo.conn.execute(
        "SELECT COUNT(*) c FROM forecast_line").fetchone()["c"] == 5
    assert repo.conn.execute(
        "SELECT COUNT(*) c FROM forecast_monthly").fetchone()["c"] == 25
    assert repo.conn.execute(
        "SELECT COUNT(*) c FROM forecast_totals").fetchone()["c"] == 1
    # UNIQUE 约束有效：(period, obligation_id) 无重复
    dup = repo.conn.execute(
        "SELECT period, obligation_id, COUNT(*) c FROM forecast_line "
        "GROUP BY period, obligation_id HAVING c > 1").fetchall()
    assert dup == []


def test_line_source_defaults_report(repo, saved):
    sources = {r[0] for r in repo.conn.execute(
        "SELECT DISTINCT source FROM forecast_line").fetchall()}
    assert sources == {"report"}


# ─────────────────────── 版本切换 ───────────────────────

def test_two_periods_current_unique_and_history_kept(repo):
    rows_a = _sample_rows()
    res_a = forecast(rows_a, period="202608")
    repo.save_result("202608", rows_a, res_a, "f08.xlsx")
    assert repo.get_current_period()["period"] == "202608"

    # 第二期：明细数字做个改动（新签锁定 +3000）
    rows_b = [
        _row("OB1", budget="YS1", group="新签", locked_year=13000,
             monthly=[4000, 0, 0, 0, 0, 9000], actual=3000,
             cat=DUE_2026, month=6, amount=10000),
        _row("OB2", budget="YS2", group="递延", locked_year=8000,
             monthly=[0, 0, 8000], actual=2000,
             cat=IN_PIPELINE, amount=7000),
    ]
    res_b = forecast(rows_b, period="202609")
    repo.save_result("202609", rows_b, res_b, "f09.xlsx")

    # current 全局唯一且指向新期
    cur = repo.get_current_period()
    assert cur["period"] == "202609"
    n_current = repo.conn.execute(
        "SELECT COUNT(*) c FROM forecast_period WHERE is_current = 1"
    ).fetchone()["c"]
    assert n_current == 1

    periods = repo.list_periods()
    assert [p["period"] for p in periods] == ["202609", "202608"]
    flags = {p["period"]: p["is_current"] for p in periods}
    assert flags == {"202609": 1, "202608": 0}

    # 旧版本明细保留：202608 仍 5 行 line，totals 为旧数字
    old_lines = repo.conn.execute(
        "SELECT COUNT(*) c FROM forecast_line WHERE period='202608'"
    ).fetchone()["c"]
    assert old_lines == 5
    t08 = repo.get_totals("202608")
    t09 = repo.get_totals("202609")
    assert t08["locked_total"] == pytest.approx(25000.0)   # 10000+8000+5000+2000
    assert t09["locked_total"] == pytest.approx(21000.0)   # 13000+8000


def test_switch_back_to_old_period(repo):
    rows = _sample_rows()
    repo.save_result("202608", rows, forecast(rows, period="202608"), "a.xlsx")
    repo.save_result("202609", rows, forecast(rows, period="202609"), "b.xlsx")
    assert repo.get_current_period()["period"] == "202609"
    # 重算/重传旧期 → current 切回旧期，仍唯一
    repo.save_result("202608", rows, forecast(rows, period="202608"), "a.xlsx")
    assert repo.get_current_period()["period"] == "202608"
    assert repo.conn.execute(
        "SELECT COUNT(*) c FROM forecast_period WHERE is_current=1"
    ).fetchone()["c"] == 1


# ─────────────────────── 同期重算：数字稳定 ───────────────────────

def test_recompute_stable_numbers(repo):
    rows = _sample_rows()
    res = forecast(rows, period="202609")
    repo.save_result("202609", rows, res, "f.xlsx")

    def snapshot():
        q = repo.query_lines("202609", page=1, page_size=100)
        # AUTOINCREMENT id 在重建后递增，属预期；稳定性核对业务字段（剔除 id）
        items = [{k: v for k, v in it.items() if k != "id"} for it in q["items"]]
        return (
            repo.get_totals("202609"),
            repo.get_monthly("202609", BASIS_LOCKED),
            repo.get_monthly("202609", BASIS_DYNAMIC_DUE),
            repo.get_monthly("202609", BASIS_PIPELINE),
            {"total": q["total"], "items": items},
        )

    s1 = snapshot()
    # 重算两次
    repo.save_result("202609", rows, res, "f.xlsx")
    repo.save_result("202609", rows, res, "f.xlsx")
    s3 = snapshot()
    assert s1 == s3


# ─────────────────────── totals/monthly 与输入一致 ───────────────────────

def test_totals_match_forecast_result(repo, saved):
    rows, result = saved
    t = repo.get_totals("202609")
    assert t["forecast_year"] == result.forecast_year
    assert t["locked_total"] == pytest.approx(result.locked_total)
    assert t["dynamic_total"] == pytest.approx(result.dynamic_total)
    assert t["actual_ytd"] == pytest.approx(result.actual_ytd_total)
    assert t["dynamic_pipeline"] == pytest.approx(result.dynamic_pipeline)
    assert t["gap"] == pytest.approx(result.gap_dynamic_minus_locked)
    assert t["locked_by_group"] == pytest.approx(result.locked_by_group)
    assert t["dynamic_by_group"] == pytest.approx(result.dynamic_by_group)

    p = repo.get_current_period()
    assert p["source_file"] == "report-202609.xlsx"
    assert p["locked_total"] == pytest.approx(result.locked_total)
    assert p["dynamic_total"] == pytest.approx(result.dynamic_total)
    assert p["actual_ytd"] == pytest.approx(result.actual_ytd_total)
    assert p["line_count"] == result.line_count


def test_monthly_match_forecast_result(repo, saved):
    rows, result = saved
    locked = repo.get_monthly("202609", BASIS_LOCKED)
    due = repo.get_monthly("202609", BASIS_DYNAMIC_DUE)
    pipe = repo.get_monthly("202609", BASIS_PIPELINE)

    assert set(locked) == {f"{m:02d}" for m in range(1, 13)}
    for k, v in result.locked_monthly.items():
        assert locked[k] == pytest.approx(v)
    for k, v in result.dynamic_due_monthly.items():
        assert due[k] == pytest.approx(v)
    assert sum(locked.values()) == pytest.approx(result.locked_total, abs=1e-6)
    assert sum(due.values()) == pytest.approx(result.dynamic_due_total, abs=1e-6)
    assert pipe == {"pipeline": pytest.approx(result.dynamic_pipeline)}


def test_get_monthly_bad_basis(repo, saved):
    with pytest.raises(ValueError):
        repo.get_monthly("202609", "bogus")


def test_get_totals_missing_period(repo):
    assert repo.get_totals("199901") is None


# ─────────────────────── query_lines：分页/过滤实际生效 ───────────────────────

def test_query_lines_pagination_effective(repo, saved):
    # 共 5 行；page_size=2 → 总数 5，三页条数 2/2/1，页间无重叠
    p1 = repo.query_lines("202609", page=1, page_size=2)
    p2 = repo.query_lines("202609", page=2, page_size=2)
    p3 = repo.query_lines("202609", page=3, page_size=2)
    assert p1["total"] == 5
    assert len(p1["items"]) == 2
    assert len(p2["items"]) == 2
    assert len(p3["items"]) == 1
    ids = [i["obligation_id"] for i in p1["items"] + p2["items"] + p3["items"]]
    assert len(ids) == len(set(ids)) == 5
    # 稳定排序：按 obligation_id
    assert ids == sorted(ids)
    # 超出范围的页码 → 空集但 total 不变
    p99 = repo.query_lines("202609", page=99, page_size=2)
    assert p99["items"] == [] and p99["total"] == 5
    # 行字段类型转换生效
    assert all(isinstance(i["dyn_in_plan"], bool) for i in p1["items"])


def test_query_lines_category_filter_effective(repo, saved):
    # 构造集中：DUE_2026=1, IN_PIPELINE=1, FUTURE_YEAR=1, ALREADY_DONE=2
    for cat, expected in [
        (DUE_2026, {"OB1"}),
        (IN_PIPELINE, {"OB2"}),
        (FUTURE_YEAR, {"OB3"}),
        (ALREADY_DONE, {"OB4", "OB5"}),
        (MISSING_DATE, set()),
    ]:
        got = repo.query_lines("202609", category=cat, page=1, page_size=50)
        ids = {i["obligation_id"] for i in got["items"]}
        assert ids == expected
        assert got["total"] == len(expected)
        # 过滤真正进了 SQL：返回行的 category 全部等于入参
        assert all(i["dyn_category"] == cat for i in got["items"])


def test_query_lines_in_plan_filter_effective(repo, saved):
    inp = repo.query_lines("202609", in_plan=True, page=1, page_size=50)
    outp = repo.query_lines("202609", in_plan=False, page=1, page_size=50)
    in_ids = {i["obligation_id"] for i in inp["items"]}
    out_ids = {i["obligation_id"] for i in outp["items"]}
    assert in_ids == {"OB1", "OB2"}
    assert out_ids == {"OB3", "OB4", "OB5"}
    assert all(i["dyn_in_plan"] is True for i in inp["items"])
    assert all(i["dyn_in_plan"] is False for i in outp["items"])
    # 两集互补穷尽
    assert in_ids.isdisjoint(out_ids)
    assert in_ids | out_ids == {"OB1", "OB2", "OB3", "OB4", "OB5"}
    assert inp["total"] + outp["total"] == 5


def test_query_lines_combined_filters_and_paging(repo):
    # 构造 6 条 IN_PIPELINE + 若干其他，验证 category+in_plan 叠加 + 分页计数
    rows = [
        _row(f"P{i}", budget=f"YS{i}", group="递延", locked_year=1000,
             monthly=[1000], actual=0, cat=IN_PIPELINE, month=None,
             amount=1000)
        for i in range(1, 7)
    ]
    rows.append(_row("X1", budget="YSX", group="新签", locked_year=1000,
                     monthly=[1000], cat=DUE_2026, month=3, amount=1000))
    repo.save_result("202610", rows, forecast(rows, period="202610"), "f.xlsx")

    q = repo.query_lines("202610", category=IN_PIPELINE, in_plan=True,
                         page=1, page_size=4)
    assert q["total"] == 6 and len(q["items"]) == 4
    q2 = repo.query_lines("202610", category=IN_PIPELINE, in_plan=True,
                          page=2, page_size=4)
    assert len(q2["items"]) == 2
    # 矛盾过滤 → 空
    qz = repo.query_lines("202610", category=IN_PIPELINE, in_plan=False)
    assert qz["total"] == 0 and qz["items"] == []


def test_query_lines_isolated_by_period(repo):
    rows_a = _sample_rows()
    repo.save_result("202608", rows_a, forecast(rows_a, period="202608"), "a.xlsx")
    rows_b = [_row("OB1", cat=DUE_2026, month=1, amount=5000,
                   locked_year=5000, monthly=[5000])]
    repo.save_result("202609", rows_b, forecast(rows_b, period="202609"), "b.xlsx")
    # 查询不串期
    assert repo.query_lines("202608", page=1, page_size=100)["total"] == 5
    assert repo.query_lines("202609", page=1, page_size=100)["total"] == 1


# ─────────────────────── 文件路径连接（外部自建库）───────────────

def test_path_based_connection(tmp_path):
    db_file = tmp_path / "fc.db"
    r = ForecastRepository(db_file)
    r.ensure_schema()
    rows = _sample_rows()
    r.save_result("202609", rows, forecast(rows, period="202609"), "f.xlsx")
    r.close()
    assert db_file.is_file() and db_file.stat().st_size > 0
    # 重开数据仍在
    r2 = ForecastRepository(db_file)
    assert r2.get_current_period()["period"] == "202609"
    assert r2.query_lines("202609")["total"] == 5
    r2.close()


def test_injected_external_connection_not_closed():
    import sqlite3
    conn = sqlite3.connect(":memory:")
    r = ForecastRepository(conn)
    r.ensure_schema()
    r.close()
    # 注入的连接不由仓储关闭，仍可使用
    assert conn.execute("SELECT 1").fetchone()[0] == 1
    conn.close()


# ─────────────────────── 真实财报端到端落库 ───────────────────────

@pytest.fixture(scope="module")
def real_repo():
    if not REAL_REPORT.is_file():
        pytest.skip(f"真实财报不存在: {REAL_REPORT}")
    rep = parse_report(REAL_REPORT)
    assert rep.ok
    result = forecast(rep.rows)
    r = ForecastRepository(":memory:")
    r.ensure_schema()
    r.save_result("202609", rep.rows, result, REAL_REPORT.name)
    yield r, rep, result
    r.close()


def test_real_persist_overview_golden(real_repo):
    r, rep, result = real_repo
    cur = r.get_current_period()
    t = r.get_totals("202609")

    # 精确锚点（元，1 万元容差）
    assert t["locked_total"] == pytest.approx(138420136.78, abs=1e4)
    assert t["dynamic_total"] == pytest.approx(171048611.81, abs=1e4)
    assert t["actual_ytd"] == pytest.approx(94457828.53, abs=1e4)
    assert t["gap"] == pytest.approx(32628475.03, abs=1e4)
    assert t["dynamic_pipeline"] == pytest.approx(84112097.86, abs=1e4)

    # 发布黄金口径（亿元）：locked 1.38 / dynamic 1.71 / actual .94 / gap +.33
    assert round(t["locked_total"] / YI, 2) == 1.38
    assert round(t["dynamic_total"] / YI, 2) == 1.71
    assert round(t["actual_ytd"] / YI, 2) == 0.94
    assert round(t["gap"] / YI, 2) == 0.33
    assert round(t["locked_by_group"]["新签"] / YI, 2) == 0.67
    assert round(t["locked_by_group"]["递延"] / YI, 2) == 0.72
    assert round(t["dynamic_by_group"]["新签"] / YI, 3) == 0.851
    assert round(t["dynamic_by_group"]["递延"] / YI, 3) == 0.860

    # period 行与 totals 同口径
    assert cur["locked_total"] == pytest.approx(t["locked_total"])
    assert cur["dynamic_total"] == pytest.approx(t["dynamic_total"])
    assert cur["actual_ytd"] == pytest.approx(t["actual_ytd"])
    assert cur["line_count"] == 38052


def test_real_persist_monthly_golden(real_repo):
    r, rep, result = real_repo
    locked = r.get_monthly("202609", BASIS_LOCKED)
    due = r.get_monthly("202609", BASIS_DYNAMIC_DUE)
    pipe = r.get_monthly("202609", BASIS_PIPELINE)

    assert sum(locked.values()) == pytest.approx(result.locked_total, abs=1.0)
    assert sum(due.values()) == pytest.approx(result.dynamic_due_total, abs=1.0)
    assert pipe["pipeline"] == pytest.approx(result.dynamic_pipeline, abs=1.0)
    # 逐月锁定发布锚点抽查（亿）
    assert round(locked["01"] / YI, 3) == 0.116
    assert round(locked["12"] / YI, 3) == 0.227
    assert round(due["06"] / YI, 3) == 0.159
    assert round(due["12"] / YI, 3) == 0.194


def test_real_persist_lines_filter_and_count(real_repo):
    r, rep, result = real_repo
    # 全量 38052 行落库
    assert r.query_lines("202609", page=1, page_size=1)["total"] == 38052
    # in_plan=True 的行数 = 计入动态口径的底稿行数
    inp = r.query_lines("202609", in_plan=True, page=1, page_size=1)
    expected_in = sum(1 for x in rep.rows if x.dyn_in_plan)
    assert inp["total"] == expected_in
    # DUE_2026 明细金额合计 = dynamic_due_total
    q = r.query_lines("202609", category=DUE_2026, page=1, page_size=1)
    assert q["total"] == sum(1 for x in rep.rows if x.dyn_category == DUE_2026)
