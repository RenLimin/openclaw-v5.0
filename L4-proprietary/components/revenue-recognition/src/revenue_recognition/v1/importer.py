"""数据导入：从手工 Excel 读取 → SQLite"""

import openpyxl
import sqlite3
from pathlib import Path
from typing import Optional

from .config import MANUAL_REPORT_PATH
from .db import get_connection, init_db


def _safe_float(val) -> Optional[float]:
    """安全转 float"""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(str(val).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _safe_str(val) -> Optional[str]:
    """安全转 str"""
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def import_plan_draft(excel_path: Path = MANUAL_REPORT_PATH, db_path: Optional[Path] = None) -> int:
    """导入计划确收底稿"""
    print(f"📖 读取计划确收底稿: {excel_path}")
    wb = openpyxl.load_workbook(excel_path, read_only=True)
    ws = wb["计划确收底稿"]

    conn = get_connection(db_path)
    c = conn.cursor()

    # 清空旧数据
    c.execute("DELETE FROM plan_draft")

    count = 0
    # Row 3 = header, data starts row 4
    for row_idx, row in enumerate(ws.iter_rows(min_row=4, values_only=True), 4):
        if row is None or all(v is None for v in row):
            continue
        # 至少要包含合同编号
        if row[3] is None:  # D列 = contract_no
            continue

        data = {
            "note": _safe_str(row[0]),              # A
            "init_est_date": _safe_str(row[1]),      # B
            "est_date": _safe_str(row[2]),           # C
            "contract_no": _safe_str(row[3]),        # D
            "archive_month": _safe_str(row[4]),      # E
            "contract_no2": _safe_str(row[5]),       # F
            "prod_seq": _safe_str(row[6]),           # G
            "perf_id": _safe_str(row[7]),            # H
            "budget_perf_id": _safe_str(row[8]),     # I
            "dept": _safe_str(row[9]),               # J
            "contract_name": _safe_str(row[10]),     # K
            "customer": _safe_str(row[11]),          # L
            "end_user": _safe_str(row[12]),          # M
            "contract_note": _safe_str(row[13]),     # N
            "ops_note": _safe_str(row[14]),          # O
            "tax_rate": _safe_float(row[15]),        # P
            "sign_date": _safe_str(row[16]),         # Q
            "contract_start": _safe_str(row[17]),    # R
            "contract_end": _safe_str(row[18]),      # S
            "service_months": _safe_float(row[19]),  # T
            "contract_type": _safe_str(row[20]),     # U
            "version_type": _safe_str(row[21]),      # V
            "gift": _safe_str(row[22]),              # W
            "prod_category": _safe_str(row[23]),     # X
            "prod_name": _safe_str(row[24]),         # Y
            "perf_detail": _safe_str(row[25]),       # Z
            "std_prod_name": _safe_str(row[26]),     # AA
            "rev_subject": _safe_str(row[27]),       # AB
            "tax_subject": _safe_str(row[28]),       # AC
            "price_basis": _safe_str(row[29]),       # AD
            "accept_type": _safe_str(row[30]),       # AE
            "accept_term": _safe_str(row[31]),       # AF
            "payment_term": _safe_str(row[32]),      # AG
            "rev_method": _safe_str(row[33]),        # AH
            "no_exec_reason": _safe_str(row[34]),    # AI
            "qty_unit": _safe_str(row[35]),          # AJ
            "qty": _safe_float(row[36]),             # AK
            "contract_amount": _safe_float(row[37]), # AL
            "confirm_amount": _safe_float(row[38]),  # AM
            "perf_amount": _safe_float(row[39]),     # AN
            "plan_perf_amount": _safe_float(row[40]),# AO
            "rev_before_2025": _safe_float(row[41]), # AP
            # AQ = AO - AP = plan_perf_amount - rev_before_2025 (公式列，data_only读不到)
            "rev_2026_future": _safe_float(row[40]) - _safe_float(row[41]) if _safe_float(row[40]) is not None else None, # AQ = AO - AP
            "plan_disappear": _safe_float(row[43]),  # AR
            "disappear_reason": _safe_str(row[44] if len(row) > 44 else None),  # AS
        }

        cols = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        c.execute(f"INSERT INTO plan_draft ({cols}) VALUES ({placeholders})", tuple(data.values()))
        count += 1

    conn.commit()
    conn.close()
    wb.close()
    print(f"✅ 计划确收底稿导入完成: {count} 行")
    return count


def import_budget_exec(excel_path: Path = MANUAL_REPORT_PATH, db_path: Optional[Path] = None) -> int:
    """导入预算执行表"""
    print(f"📖 读取预算执行表: {excel_path}")
    wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
    ws = wb["预算执行表"]

    conn = get_connection(db_path)
    c = conn.cursor()

    c.execute("DELETE FROM budget_exec")

    count = 0
    # Row 3 = header, data starts row 4
    for row_idx, row in enumerate(ws.iter_rows(min_row=4, values_only=True), 4):
        if row is None or all(v is None for v in row):
            continue
        if row[1] is None:  # B列 = contract_no
            continue

        # 月度计划 U(20)-AF(31) → indices 20..31
        months_plan = []
        for i in range(12):
            idx = 20 + i  # U=col21 → row index 20
            months_plan.append(_safe_float(row[idx]) if idx < len(row) else None)

        # 月度实际 AL(37)-AQ(42) → indices 37..42
        months_actual = []
        for i in range(6):
            idx = 37 + i  # AL=col38 → row index 37
            months_actual.append(_safe_float(row[idx]) if idx < len(row) else None)

        data = {
            "category": _safe_str(row[0]),           # A
            "contract_no": _safe_str(row[1]),        # B
            "contract_no_cal": _safe_str(row[2]),    # C
            "customer": _safe_str(row[3]),           # D
            "end_user": _safe_str(row[4]),           # E
            "sign_subject": _safe_str(row[5]),       # F
            "archive_month": _safe_str(row[6]),      # G
            "perf_id_budget": _safe_str(row[7]),     # H
            "perf_detail_budget": _safe_str(row[8]), # I
            "perf_id": _safe_str(row[9]),            # J
            "rev_method": _safe_str(row[10]),        # K
            "perf_amount": _safe_float(row[11]),     # L
            "rev_prior": _safe_float(row[12]),       # M
            "rev_future": _safe_float(row[13]),      # N
            "no_plan": _safe_float(row[14]),         # O
            "unrev_prior": _safe_float(row[15]),     # P
            "unrev_adj": _safe_float(row[16]),       # Q
            "plan_start": _safe_str(row[17]),        # R
            "plan_end": _safe_str(row[18]),          # S
            "plan_done": _safe_str(row[19]),         # T
            "m202601": months_plan[0],
            "m202602": months_plan[1],
            "m202603": months_plan[2],
            "m202604": months_plan[3],
            "m202605": months_plan[4],
            "m202606": months_plan[5],
            "m202607": months_plan[6],
            "m202608": months_plan[7],
            "m202609": months_plan[8],
            "m202610": months_plan[9],
            "m202611": months_plan[10],
            "m202612": months_plan[11],
            "year_est": _safe_float(row[32]) if len(row) > 32 else None,   # AG index=32
            "h1_plan": _safe_float(row[33]) if len(row) > 33 else None,    # AH
            "h1_actual": _safe_float(row[34]) if len(row) > 34 else None,  # AI
            "h1_ahead": _safe_float(row[35]) if len(row) > 35 else None,   # AJ
            "h1_behind": _safe_float(row[36]) if len(row) > 36 else None,  # AK
            "a202601": months_actual[0],
            "a202602": months_actual[1],
            "a202603": months_actual[2],
            "a202604": months_actual[3],
            "a202605": months_actual[4],
            "a202606": months_actual[5],
            "disappear_2026": _safe_float(row[43]) if len(row) > 43 else None,   # AR
            "disappear_future": _safe_float(row[44]) if len(row) > 44 else None, # AS
            "disappear_note": _safe_str(row[45]) if len(row) > 45 else None,     # AT
            "rebuild_perf": _safe_str(row[46]) if len(row) > 46 else None,      # AU
            "forecast_category": _safe_str(row[47]) if len(row) > 47 else None,  # AV
        }

        cols = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        c.execute(f"INSERT INTO budget_exec ({cols}) VALUES ({placeholders})", tuple(data.values()))
        count += 1

    conn.commit()
    conn.close()
    wb.close()
    print(f"✅ 预算执行表导入完成: {count} 行")
    return count



def import_monthly_summary(excel_path: Path = MANUAL_REPORT_PATH, db_path: Optional[Path] = None) -> int:
    """导入月度汇总记录 — 从手工报表"月度汇总记录"Sheet 读取所有行"""
    print(f"📖 读取月度汇总记录: {excel_path}")
    wb = openpyxl.load_workbook(excel_path, read_only=True)
    ws = wb["月度汇总记录"]

    conn = get_connection(db_path)
    c = conn.cursor()

    c.execute("DELETE FROM monthly_summary")

    count = 0
    # Row 1: 大标题（跳过），Row 2: 列头（跳过），Row 3+: 数据
    for row_idx, row in enumerate(ws.iter_rows(min_row=3, values_only=True), 3):
        if row is None or all(v is None for v in row):
            continue
        # A列 = stat_period, 不能为空
        if row[0] is None:
            continue

        stat_period = _safe_str(row[0])
        contract_period = _safe_str(row[1])

        # 将整数期间转为文本（保留前导零）
        if stat_period and stat_period.isdigit():
            stat_period = str(int(stat_period))  # 去掉可能的小数部分
        if contract_period and contract_period.isdigit():
            contract_period = str(int(contract_period))

        data = {
            "stat_period": stat_period,
            "contract_period": contract_period,
            "new_amount": _safe_float(row[2]) if len(row) > 2 else None,
            "new_plan_rev": _safe_float(row[3]) if len(row) > 3 else None,
            "new_actual_rev": _safe_float(row[4]) if len(row) > 4 else None,
            "def_plan_rev": _safe_float(row[5]) if len(row) > 5 else None,
            "def_actual_rev": _safe_float(row[6]) if len(row) > 6 else None,
            "total_plan_rev": _safe_float(row[7]) if len(row) > 7 else None,
            "total_actual_rev": _safe_float(row[8]) if len(row) > 8 else None,
            "adj_plan": _safe_float(row[9]) if len(row) > 9 else None,
            "adj_actual": _safe_float(row[10]) if len(row) > 10 else None,
        }

        cols = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        c.execute(
            f"INSERT OR REPLACE INTO monthly_summary ({cols}) VALUES ({placeholders})",
            tuple(data.values())
        )
        count += 1

    conn.commit()
    conn.close()
    wb.close()
    print(f"✅ 月度汇总记录导入完成: {count} 行")
    return count


def import_performance_summary(excel_path: Path = MANUAL_REPORT_PATH, db_path: Optional[Path] = None) -> int:
    """导入履约汇总记录 — 从手工报表"履约汇总记录"Sheet 读取所有行"""
    print(f"📖 读取履约汇总记录: {excel_path}")
    wb = openpyxl.load_workbook(excel_path, read_only=True)
    ws = wb["履约汇总记录"]

    conn = get_connection(db_path)
    c = conn.cursor()

    c.execute("DELETE FROM performance_summary")

    count = 0
    # Row 1: 列头（跳过），Row 2+: 数据
    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
        if row is None or all(v is None for v in row):
            continue
        # A列 = stat_period, 不能为空
        if row[0] is None:
            continue

        stat_period = _safe_str(row[0])
        # 将整数期间转为文本（保留前导零）
        if stat_period and stat_period.isdigit():
            stat_period = str(int(stat_period))

        # B列 category 可能有前导空格，需要 strip()
        category = _safe_str(row[1]) if len(row) > 1 else None
        if category:
            category = category.strip()

        data = {
            "stat_period": stat_period,
            "category": category,
            "new_value": _safe_float(row[2]) if len(row) > 2 else None,
            "deferred_value": _safe_float(row[3]) if len(row) > 3 else None,
            "total_value": _safe_float(row[4]) if len(row) > 4 else None,
            "note": _safe_str(row[5]) if len(row) > 5 else None,
        }

        cols = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        c.execute(
            f"INSERT OR REPLACE INTO performance_summary ({cols}) VALUES ({placeholders})",
            tuple(data.values())
        )
        count += 1

    conn.commit()
    conn.close()
    wb.close()
    print(f"✅ 履约汇总记录导入完成: {count} 行")
    return count


def import_all(excel_path: Path = MANUAL_REPORT_PATH, db_path: Optional[Path] = None):
    """导入所有数据"""
    init_db(db_path)
    plan_count = import_plan_draft(excel_path, db_path)
    budget_count = import_budget_exec(excel_path, db_path)
    monthly_count = import_monthly_summary(excel_path, db_path)
    perf_count = import_performance_summary(excel_path, db_path)
    return {
        "plan_draft": plan_count,
        "budget_exec": budget_count,
        "monthly_summary": monthly_count,
        "performance_summary": perf_count,
    }


if __name__ == "__main__":
    result = import_all()
    print(f"\n📊 导入结果: {result}")
