"""importer — 确收分析导入器：xlsx → rr_sheet_row 宽表。

按 202609 实测表头（DESIGN-DETAIL-REVENUE-ANALYSIS v1.0 §4.1/§4.2）：
  - Sheet「预算执行表」：表头 R3，45 原始列（A–AS），数据 R4 起
  - Sheet「计划确收底稿」：表头 R3，52 列（A–AZ），数据 R4 起
  - 复用 rr_sheet_row / rr_sheet_meta（RR_SCHEMA）宽表，period 维度

设计要点：
  - 表头自适应（HeaderMapper）：列名优先，缺列记录不静默
  - 金额红线：202609 的 J/K/L 全 0，导入时原样保留 + 标记 zero_semantic，
    不推导、不回填（待 Rex 拍板 A/B/C）
  - 幂等：同 period 重复导入覆盖（overwrite=True）

🔒 NO_TOKEN — 纯代码，零 AI 依赖。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from openpyxl import load_workbook

from bdms.core import db as _db
from bdms.core.header_mapper import HeaderMapper, read_header
from bdms.modules.base import ImportError_

from .config import (
    SHEET_BUDGET, SHEET_DRAFT,
    HEADER_ROW_BUDGET, HEADER_ROW_DRAFT, DATA_START_ROW,
    BUDGET_COLUMNS, DRAFT_COLUMNS,
    COMPUTED_COLUMNS,
    PLAN_MONTHS, ACTUAL_MONTHS,
    ZERO_SEMANTIC_COLUMNS,
)

PREFIX = "rr"


def _build_field_index(headers: list[str], columns: dict[str, str]) -> dict[str, int]:
    """按表头名建立 field → 列索引（1-based）。同名按出现顺序消歧。"""
    mapper = HeaderMapper(headers)
    field_idx: dict[str, int] = {}
    # 统计每个列名在 columns.values() 中的出现顺序，同名按 nth 消歧
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


def _read_sheet_rows(path: Path, sheet: str, header_row: int,
                     columns: dict[str, str],
                     extra_columns: dict[str, str] | None = None,
                     zero_semantic: bool = False) -> tuple[list[str], list[dict]]:
    """读 sheet 数据。返回 (字段名列表, 行字典列表)。

    extra_columns: 可选附加列（如已计算好的 AT–AX），源表头存在才纳入。
    """
    wb = load_workbook(path, data_only=True, read_only=True)
    try:
        if sheet not in wb.sheetnames:
            raise ImportError_(f"缺少 Sheet: {sheet}")
        ws = wb[sheet]
        headers = read_header(ws, header_row)  # 已归一化（全角→半角等）
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
            # 跳过全空行
            if all(v in (None, "") for v in r):
                continue
            rows.append(_row_to_dict(r, field_idx, zero_semantic))
        return all_fields, rows, missing
    finally:
        wb.close()


class RevenueAnalysisImporter:
    """统一确收分析导入器：xlsx → rr_sheet_row 宽表。"""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path: Path = Path(db_path) if db_path else _db.DB_PATH

    def import_budget_exec(self, excel_path: Path, period: str) -> dict:
        """导入「预算执行表」（45 列 + 计算列 AT–AX 若存在）。"""
        # AT–AX 表头名（202609_with_trend_cols.xlsx 产物）：
        computed_headers = {
            "AT": "合同数量统计唯一值",
            "AU": "统计位",
            "AV": "预算填报",
            "AW": "预算趋势",
            "AX": "预算趋势类别",
        }
        fields, rows, missing = _read_sheet_rows(
            Path(excel_path), SHEET_BUDGET, HEADER_ROW_BUDGET,
            BUDGET_COLUMNS, extra_columns=computed_headers,
            zero_semantic=True,
        )
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
            "zero_semantic_columns": list(ZERO_SEMANTIC_COLUMNS),
        }

    def import_plan_draft(self, excel_path: Path, period: str) -> dict:
        """导入「计划确收底稿」（52 列）。"""
        fields, rows, missing = _read_sheet_rows(
            Path(excel_path), SHEET_DRAFT, HEADER_ROW_DRAFT, DRAFT_COLUMNS,
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
        }

    def import_all(self, excel_path: Path, period: str) -> dict:
        """导入全部核心 Sheet（预算执行表 + 计划确收底稿）。"""
        budget = self.import_budget_exec(excel_path, period)
        draft = self.import_plan_draft(excel_path, period)
        return {
            "period": period,
            "source_path": str(excel_path),
            "sheets": {
                SHEET_BUDGET: budget["rows"],
                SHEET_DRAFT: draft["rows"],
            },
            "total_rows": budget["rows"] + draft["rows"],
            "missing": {
                SHEET_BUDGET: budget["missing_columns"],
                SHEET_DRAFT: draft["missing_columns"],
            },
            "zero_semantic_columns": budget["zero_semantic_columns"],
        }
