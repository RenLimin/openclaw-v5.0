"""周报签约项目统计导入器 — 回归测试。

覆盖：
  1. 「、」串联的多履约ID 单元格必须拆分为独立索引行
  2. 幂等：重复导入同一月份不产生重复行
  3. 跨月查询：优先近月，且不越界取「报表月份之后」的数据
  4. 缺关键列时必须报错（不静默失败）

背景：手工报表 c93「所属产线（周报）」是跨月 VLOOKUP，
早期实现只查当月且不支持多值单元格，导致 1,463 处 #N/A。
"""

import csv
import sqlite3

import pytest

from bdms.modules.revenue.weekly_importer import (
    import_weekly_csv, load_prod_line_index, _split_perf_ids, ensure_schema,
)

HEADER = [
    "BI履约ID", "最终用户名称", "客户名称", "责任销售（履约项）", "责任销售所属团队",
    "负责人", "所属项目", "项目类型(概览)", "项目状态", "立项日期",
    "基线-预估结项日期", "实际结项日期", "销售合同编号", "合同名称", "直签或代理",
    "合同归档日期", "合同起始日期", "合同结束日期", "交付服务开始日期", "交付服务结束日期",
    "合同验收条款", "验收时点", "验收方式", "标题", "标准产品/服务序号",
    "履约类型", "所属产线", "状态", "履约项异常/变更备注", "履约项优先级",
    "预估交付完成日期", "预算-预估交付完成日期", "交付邮件发送日期",
    "实际服务/授权开始日期", "实际服务/授权结束日期", "预估验收完成日期",
    "预算-预估验收完成日期", "备注", "PMO备注", "ID",
    "事业部（区域）", "事业部负责人", "异常报备日期", "预估异常处置完成日期",
    "异常归档日期", "异常影响情况", "异常项目-类别", "异常项目-处置方案",
    "异常处置方案-影响", "交付说明（异常履约项统计类别）",
    "交付说明（履约项交付情况、合同交付条款）", "交付中心反馈", "营销中心反馈",
    "项目异常内容", "预估金额",
]


def _row(perf_id, prod_line, status="验收文件已归档", pmo="", note=""):
    r = [""] * len(HEADER)
    r[0] = perf_id
    r[26] = prod_line
    r[27] = status
    r[37] = note
    r[38] = pmo
    return r


def _write_csv(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(rows)


# ─── 多值拆分 ───

def test_split_perf_ids_basic():
    assert _split_perf_ids("A、B、C") == ["A", "B", "C"]


def test_split_perf_ids_single():
    assert _split_perf_ids("SINGLE_01") == ["SINGLE_01"]


def test_split_perf_ids_empty():
    assert _split_perf_ids("") == []


def test_multi_value_cell_creates_row_per_subkey(tmp_path):
    """回归：单元格 'A、B' 曾只按整串建索引，导致子项查不到。"""
    csvp = tmp_path / "w.csv"
    dbp = tmp_path / "t.db"
    _write_csv(csvp, [
        _row("X_01_001、X_02_001", "1：安全保护产品线"),
        _row("Y_01_001", "2：安全服务产品线"),
    ])
    import_weekly_csv(csvp, dbp, "202606")
    idx = load_prod_line_index(dbp, "202606")
    assert idx["X_01_001"] == "1：安全保护产品线", "子项 A 应可查到"
    assert idx["X_02_001"] == "1：安全保护产品线", "子项 B 应可查到"
    assert idx["Y_01_001"] == "2：安全服务产品线"


# ─── 幂等 ───

def test_reimport_is_idempotent(tmp_path):
    csvp = tmp_path / "w.csv"
    dbp = tmp_path / "t.db"
    _write_csv(csvp, [_row("A_01_001", "1：安全保护产品线")])
    import_weekly_csv(csvp, dbp, "202606")
    import_weekly_csv(csvp, dbp, "202606")
    conn = sqlite3.connect(dbp)
    n = conn.execute("SELECT COUNT(*) FROM weekly_signing WHERE month='202606'").fetchone()[0]
    conn.close()
    assert n == 1


def test_same_perf_id_keeps_first(tmp_path):
    """同一履约ID 多行时保留首次（与手工 VLOOKUP 语义一致）。"""
    csvp = tmp_path / "w.csv"
    dbp = tmp_path / "t.db"
    _write_csv(csvp, [
        _row("A_01_001", "1：安全保护产品线"),
        _row("A_01_001", "9：不应覆盖"),
    ])
    import_weekly_csv(csvp, dbp, "202606")
    assert load_prod_line_index(dbp, "202606")["A_01_001"] == "1：安全保护产品线"


# ─── 跨月语义 ───

def test_month_isolation(tmp_path):
    """不同月份数据互不串台。"""
    csvp = tmp_path / "w.csv"
    dbp = tmp_path / "t.db"
    _write_csv(csvp, [_row("A_01_001", "1：安全保护产品线")])
    import_weekly_csv(csvp, dbp, "202605")
    _write_csv(csvp, [_row("A_01_001", "2：安全服务产品线")])
    import_weekly_csv(csvp, dbp, "202606")
    assert load_prod_line_index(dbp, "202605")["A_01_001"] == "1：安全保护产品线"
    assert load_prod_line_index(dbp, "202606")["A_01_001"] == "2：安全服务产品线"


# ─── 失败不静默 ───

def test_missing_key_column_raises(tmp_path):
    """缺 BI履约ID 列必须抛错，不得静默产空索引。"""
    csvp = tmp_path / "bad.csv"
    dbp = tmp_path / "t.db"
    with open(csvp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["列A", "列B"])
        w.writerow(["1", "2"])
    with pytest.raises(ValueError, match="BI履约ID"):
        import_weekly_csv(csvp, dbp, "202606")


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        import_weekly_csv(tmp_path / "nope.csv", tmp_path / "t.db", "202606")


# ─── 产线为空的行不应污染索引 ───

def test_null_prod_line_excluded(tmp_path):
    csvp = tmp_path / "w.csv"
    dbp = tmp_path / "t.db"
    _write_csv(csvp, [
        _row("A_01_001", ""),                 # 产线为空
        _row("B_01_001", "1：安全保护产品线"),
    ])
    import_weekly_csv(csvp, dbp, "202606")
    idx = load_prod_line_index(dbp, "202606")
    assert "A_01_001" not in idx, "产线为空的行不应进入索引"
    assert idx["B_01_001"] == "1：安全保护产品线"
