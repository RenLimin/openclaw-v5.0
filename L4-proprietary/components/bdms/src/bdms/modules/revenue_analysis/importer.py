"""importer — 确收分析导入器：xlsx → rr_sheet_row 宽表。

支持两种黄金结构（按表头自动探测）：
  - 202609：预算执行表 45 列（A–AS，R3 表头）、底稿 52 列（A–AZ）
  - 202606：预算执行表 93 列（A–CO，R3 表头）、底稿 45 列（A–AS）

202606 投影（Rex 2026-11-12 口径，DESIGN-DETAIL v1.1 §7.3/§9）：
  - 预算执行表 93 列布局与 202609 45 列硬冲突（实际月区 vs 消失区互撞），
    导入时投影为 202609 规范字母（engine 取数零改动）；
    202606 独有列（AV..CO）以原字母保留为扩展键，供归因/分桶取数。
  - 台账 sheet（月度汇总记录/履约汇总记录）= 人工月报冻结快照：
    历史行直接原样导入，不从当期明细重算（§7.3）。

金额红线：202609 J/K/L 全 0 → 原样保留 + zero_semantic 标记，不推导。
幂等：同 period 重复导入覆盖（overwrite=True）。

🔒 NO_TOKEN — 纯代码，零 AI 依赖。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from openpyxl import load_workbook

from bdms.core import db as _db
from bdms.core.header_mapper import HeaderMapper, read_header
from bdms.modules.base import ImportError_

from .config import (
    SHEET_BUDGET, SHEET_DRAFT,
    HEADER_ROW_BUDGET, HEADER_ROW_DRAFT, DATA_START_ROW,
    BUDGET_COLUMNS, BUDGET_COLUMNS_202606, DRAFT_COLUMNS, DRAFT_COLUMNS_202606,
    BUDGET_CANONICAL_FROM_202606, BUDGET_EXTRA_FROM_202606,
    LEDGER_SHEETS, LEDGER_HEADERS,
    COMPUTED_COLUMNS,
    ZERO_SEMANTIC_COLUMNS,
)

PREFIX = "rr"

# 202609 计算列（预算趋势产物）：AT–AX
COMPUTED_HEADERS = {
    "AT": "合同数量统计唯一值",
    "AU": "统计位",
    "AV": "预算填报",
    "AW": "预算趋势",
    "AX": "预算趋势类别",
}


def _build_field_index(headers: list[str], columns: dict[str, str]) -> dict[str, int]:
    """按表头名建立 field → 列索引（1-based）。同名按出现顺序消歧。"""
    mapper = HeaderMapper(headers)
    field_idx: dict[str, int] = {}
    seen_count: dict[str, int] = {}
    for field, header in columns.items():
        seen_count[header] = seen_count.get(header, 0) + 1
        idx = mapper.index(header, nth=seen_count[header])
        if idx is not None:
            field_idx[field] = idx
    return field_idx


def _row_to_dict(ws_row: tuple, field_idx: dict[str, int],
                 zero_semantic: bool = False) -> dict[str, Any]:
    """行 → 字段字典。零值列标记 zero_semantic 元数据。"""
    row: dict[str, Any] = {}
    for field, idx in field_idx.items():
        val = ws_row[idx - 1] if idx <= len(ws_row) else None
        row[field] = val
    if zero_semantic:
        for col in ZERO_SEMANTIC_COLUMNS:
            field = BUDGET_COLUMNS.get(col)
            if field:
                row[f"{field}__zero_semantic"] = True
    return row


def _detect_budget_layout(headers: list[str]) -> str:
    """预算执行表结构探测：'202606'（93 列） / '202609'（45 列）。"""
    from .config import _norm_set, _BUDGET_HITS_202606, _BUDGET_HITS_202609
    h = {x.strip() for x in headers if x}
    hit6 = len(h & _BUDGET_HITS_202606)
    hit9 = len(h & _BUDGET_HITS_202609)
    # 202606 专属列（偏差/周报/产线区）命中即判定 202606。
    # 注意 "预算填报" 不能作为 marker：202609 计算列产物（AV）也有该表头。
    for marker in ("偏差-状态/趋势", "偏差-原因类别", "所属产线（周报）",
                   "是否完成下单流程", "项目验收状态（周报）",
                   "预算-预估交付完成日期（周报）"):
        if marker in h:
            return "202606"
    return "202609" if hit9 >= hit6 else "202606"


def _project_202606_row(src: dict[str, Any],
                        src_idx: dict[str, int],
                        ws_row: tuple) -> dict[str, Any]:
    """202606 93 列行 → 202609 规范字母 + 扩展键。"""
    def v(field: str) -> Any:
        idx = src_idx.get(field)
        if idx is None or idx > len(ws_row):
            return None
        return ws_row[idx - 1]

    row: dict[str, Any] = {}
    # 规范投影（语义列）
    for canon, src in BUDGET_CANONICAL_FROM_202606.items():
        row[canon] = v(src)
    # 扩展键（202606 独有列）
    for key, src in BUDGET_EXTRA_FROM_202606.items():
        row[key] = v(src)
    # 202606 无源的 202607-09 实际列：显式置空（AM/AN/AO 规范位）
    for missing in ("AM", "AN", "AO"):
        row.setdefault(missing, None)
    return row


def _read_sheet_rows(path: Path, sheet: str, header_row: int,
                     columns: dict[str, str],
                     extra_columns: dict[str, str] | None = None,
                     zero_semantic: bool = False) -> tuple[list[str], list[dict], list[str]]:
    """读 sheet 数据。返回 (字段名列表, 行字典列表, 缺失列)。"""
    wb = load_workbook(path, data_only=True, read_only=True)
    try:
        if sheet not in wb.sheetnames:
            raise ImportError_(f"缺少 Sheet: {sheet}")
        ws = wb[sheet]
        headers = read_header(ws, header_row)
        field_idx = _build_field_index(headers, columns)
        all_fields = list(columns.keys())
        if extra_columns:
            for field, header in extra_columns.items():
                idx = HeaderMapper(headers).index(header)
                if idx is not None:
                    field_idx[field] = idx
                    all_fields.append(field)
        missing = [c for c in columns if c not in field_idx]
        rows: list[dict] = []
        for r in ws.iter_rows(min_row=DATA_START_ROW, values_only=True):
            if all(v in (None, "") for v in r):
                continue
            rows.append(_row_to_dict(r, field_idx, zero_semantic))
        return all_fields, rows, missing
    finally:
        wb.close()


def _read_budget_rows(path: Path) -> tuple[list[str], list[dict], list[str], str]:
    """读预算执行表，自动探测结构。

    返回 (字段名列表, 行字典列表, 缺失列, 结构标签)。
    """
    wb = load_workbook(path, data_only=True, read_only=True)
    try:
        if SHEET_BUDGET not in wb.sheetnames:
            raise ImportError_(f"缺少 Sheet: {SHEET_BUDGET}")
        ws = wb[SHEET_BUDGET]
        headers = read_header(ws, HEADER_ROW_BUDGET)
        layout = _detect_budget_layout(headers)

        if layout == "202606":
            # 投影读取：先按 202606 93 列取数，再投影为规范字母
            src_idx = _build_field_index(headers, BUDGET_COLUMNS_202606)
            # 202606 底稿/投影源：BUDGET_COLUMNS_202606 是 {字母: 中文表头}，
            # src_idx 已按表头名解析出 202606 字母 → 列索引
            rows: list[dict] = []
            for r in ws.iter_rows(min_row=DATA_START_ROW, values_only=True):
                if all(v in (None, "") for v in r):
                    continue
                rows.append(_project_202606_row({}, src_idx, r))
            fields = list(BUDGET_CANONICAL_FROM_202606.keys()) + \
                     list(BUDGET_EXTRA_FROM_202606.keys()) + \
                     ["AM", "AN", "AO"]
            # 真正缺失的 202606 源列（表头名未命中）
            missing = [f for f in BUDGET_COLUMNS_202606 if f not in src_idx]
            return fields, rows, missing, layout

        # 202609：45 列 + 计算列 AT–AX（若存在）
        fields, rows, missing = _read_sheet_rows(
            Path(path), SHEET_BUDGET, HEADER_ROW_BUDGET,
            BUDGET_COLUMNS, extra_columns=COMPUTED_HEADERS,
            zero_semantic=True,
        )
        return fields, rows, missing, layout
    finally:
        wb.close()


def _read_ledger_sheet(path: Path, sheet: str,
                       config: dict) -> tuple[list[str], list[dict]]:
    """台账冻结 sheet 原样导入（表头 + 数据行）。"""
    wb = load_workbook(path, data_only=True, read_only=True)
    try:
        if sheet not in wb.sheetnames:
            return [], []
        ws = wb[sheet]
        header_row = config["header_row"]
        data_start = config["data_start"]
        headers: list[str] = []
        for row in ws.iter_rows(min_row=header_row, max_row=header_row,
                                values_only=True):
            headers = [str(v) if v is not None else "" for v in row]
        rows: list[dict] = []
        for r in ws.iter_rows(min_row=data_start, values_only=True):
            if all(v in (None, "") for v in r):
                continue
            rows.append({str(i): v for i, v in enumerate(r)})
        return headers, rows
    finally:
        wb.close()


class RevenueAnalysisImporter:
    """统一确收分析导入器：xlsx → rr_sheet_row 宽表。"""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path: Path = Path(db_path) if db_path else _db.DB_PATH
        # 幂等建表：独立使用（测试/临时库）也保证 rr_* schema 存在
        _db.init_db(self.db_path)

    def import_budget_exec(self, excel_path: Path, period: str) -> dict:
        """导入「预算执行表」（自动探测 202606/202609 结构）。"""
        fields, rows, missing, layout = _read_budget_rows(Path(excel_path))
        conn = _db.get_connection(self.db_path)
        try:
            n = _db.save_sheet_rows(conn, period, SHEET_BUDGET, fields, rows,
                                    prefix=PREFIX, overwrite=True)
            conn.commit()
        finally:
            conn.close()
        return {
            "sheet": SHEET_BUDGET, "period": period,
            "rows": n, "missing_columns": missing,
            "layout": layout,
            "zero_semantic_columns": list(ZERO_SEMANTIC_COLUMNS),
        }

    def import_plan_draft(self, excel_path: Path, period: str) -> dict:
        """导入「计划确收底稿」（自动探测 202606 45 列 / 202609 52 列）。"""
        wb = load_workbook(excel_path, data_only=True, read_only=True)
        try:
            if SHEET_DRAFT not in wb.sheetnames:
                raise ImportError_(f"缺少 Sheet: {SHEET_DRAFT}")
            ws = wb[SHEET_DRAFT]
            headers = read_header(ws, HEADER_ROW_DRAFT)
            from .config import _DRAFT_HITS_202606, _DRAFT_HITS_202609
            h = {x.strip() for x in headers if x}
            hit6 = len(h & _DRAFT_HITS_202606)
            hit9 = len(h & _DRAFT_HITS_202609)
            columns = DRAFT_COLUMNS_202606 if hit6 >= hit9 else DRAFT_COLUMNS
            layout = "202606" if hit6 >= hit9 else "202609"
        finally:
            wb.close()
        fields, rows, missing = _read_sheet_rows(
            Path(excel_path), SHEET_DRAFT, HEADER_ROW_DRAFT, columns,
        )
        conn = _db.get_connection(self.db_path)
        try:
            n = _db.save_sheet_rows(conn, period, SHEET_DRAFT, fields, rows,
                                    prefix=PREFIX, overwrite=True)
            conn.commit()
        finally:
            conn.close()
        return {
            "sheet": SHEET_DRAFT, "period": period,
            "rows": n, "missing_columns": missing,
            "layout": layout,
        }

    def import_ledgers(self, excel_path: Path, period: str) -> dict:
        """导入台账冻结 sheet（月度汇总记录/履约汇总记录）。

        §7.3 口径：台账 = 人工月报冻结快照，历史行原样导入、不回写。
        """
        conn = _db.get_connection(self.db_path)
        counts: dict[str, int] = {}
        try:
            for sheet, cfg in LEDGER_SHEETS.items():
                headers, rows = _read_ledger_sheet(Path(excel_path), sheet, cfg)
                if rows:
                    n = _db.save_sheet_rows(conn, period, sheet, headers,
                                            rows, prefix=PREFIX, overwrite=True)
                    counts[sheet] = n
                else:
                    counts[sheet] = 0
            conn.commit()
        finally:
            conn.close()
        return {
            "period": period,
            "ledgers": counts,
            "source_path": str(excel_path),
        }

    def import_all(self, excel_path: Path, period: str) -> dict:
        """导入全部核心 Sheet（预算执行表 + 底稿 + 台账冻结）。"""
        budget = self.import_budget_exec(excel_path, period)
        draft = self.import_plan_draft(excel_path, period)
        ledgers = self.import_ledgers(excel_path, period)
        return {
            "period": period,
            "source_path": str(excel_path),
            "sheets": {
                SHEET_BUDGET: budget["rows"],
                SHEET_DRAFT: draft["rows"],
            },
            "total_rows": budget["rows"] + draft["rows"],
            "layout": {
                SHEET_BUDGET: budget["layout"],
                SHEET_DRAFT: draft["layout"],
            },
            "ledgers": ledgers["ledgers"],
            "missing": {
                SHEET_BUDGET: budget["missing_columns"],
                SHEET_DRAFT: draft["missing_columns"],
            },
            "zero_semantic_columns": budget["zero_semantic_columns"],
        }
