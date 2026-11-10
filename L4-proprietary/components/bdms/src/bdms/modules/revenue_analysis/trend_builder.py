"""trend_builder — 预算趋势分析构建器（19 行 → ra_trend_row/ra_trend_cell）。

契约：DESIGN-DETAIL-REVENUE-ANALYSIS-v1.0 §5 / §8.1：
  - 行结构 19 行：R4-R9 递延 6 状态 + R10 递延合计 + R12-R16 新签 5 状态
    + R17 新签合计 + R18 共计 + R19 新签预计确收率；
  - engine.compute_budget_trend() 输出 15 条 line（行标签/分组/四桶计数/审计），
    本 builder 负责映射 row_index 并拆出 R19 特殊单元格；
  - 金额列受 202609 J/K/L 全 0 红线影响 → 一律 None（DB 存 NULL），不硬摊不造假。

🔒 NO_TOKEN — 纯代码，零 AI 依赖。
"""

from __future__ import annotations

import json
from typing import Any, Optional

from .config import TREND_ROWS

# R19 特殊单元格列索引（ra_trend_cell 约定）
CELL_RATE_COUNT = 0     # 新签预计确收率（数量口径）
CELL_RATE_AMOUNT = 1    # 新签预计确收率（金额口径，待拍板为 null）


class TrendBuilder:
    """预算趋势分析构建器：engine 行 → 落盘行/单元格。"""

    def build(self, lines: list[dict]) -> tuple[list[dict], list[dict]]:
        """把 compute_budget_trend() 的 15 条 line 映射为 ra_trend_row/ra_trend_cell。

        Returns:
            (rows, cells)：rows 为 ra_trend_row 数据行（row_index 4-19），
            cells 为 ra_trend_cell 特殊单元格（R19 确收率）。
        """
        rows: list[dict] = []
        cells: list[dict] = []

        for line in lines:
            idx = self._row_index(line.get("group"), line.get("row_label"))
            if idx is None:
                # 表头/未知行不入库（审计字段保留在 line 内）
                continue
            if idx == 19:
                # R19 确收率：数值进 ra_trend_cell
                rate_count = line.get("recognize_rate_count")
                rate_amount = line.get("recognize_rate_amount")
                if rate_count is not None:
                    cells.append({
                        "row_index": 19, "col_index": CELL_RATE_COUNT,
                        "value": json.dumps({"kind": "recognize_rate_count",
                                             "value": rate_count},
                                            ensure_ascii=False),
                    })
                cells.append({
                    "row_index": 19, "col_index": CELL_RATE_AMOUNT,
                    "value": json.dumps({"kind": "recognize_rate_amount",
                                         "value": rate_amount},
                                        ensure_ascii=False),
                })
                rows.append({
                    "row_index": idx,
                    "category_group": line.get("group"),
                    "status": line.get("row_label"),
                    "init_count": line.get("init_count"),
                    "init_amount_wan": line.get("init_amount_wan"),
                    "normal_count": line.get("normal_count"),
                    "normal_amount_wan": line.get("normal_amount_wan"),
                    "exception_count": line.get("exception_count"),
                    "exception_amount_wan": line.get("exception_amount_wan"),
                    "disappear_count": line.get("disappear_count"),
                    "disappear_amount_wan": line.get("disappear_amount_wan"),
                    "future_count": line.get("future_count"),
                    "future_amount_wan": line.get("future_amount_wan"),
                    "check_count": line.get("check_count"),
                    "check_amount": line.get("check_amount"),
                    "note": self._note(line),
                    "routing_audit": line.get("routing_audit"),
                    "amount_pending": line.get("amount_pending"),
                })
                continue
            rows.append({
                "row_index": idx,
                "category_group": line.get("group"),
                "status": line.get("row_label"),
                "init_count": line.get("init_count"),
                "init_amount_wan": line.get("init_amount_wan"),
                "normal_count": line.get("normal_count"),
                "normal_amount_wan": line.get("normal_amount_wan"),
                "exception_count": line.get("exception_count"),
                "exception_amount_wan": line.get("exception_amount_wan"),
                "disappear_count": line.get("disappear_count"),
                "disappear_amount_wan": line.get("disappear_amount_wan"),
                "future_count": line.get("future_count"),
                "future_amount_wan": line.get("future_amount_wan"),
                "check_count": line.get("check_count"),
                "check_amount": line.get("check_amount"),
                "note": self._note(line),
                "routing_audit": line.get("routing_audit"),
                "amount_pending": line.get("amount_pending"),
            })

        # 按 row_index 排序（R4..R19）
        rows.sort(key=lambda r: r["row_index"])
        return rows, cells

    # ─── 辅助 ───

    def _row_index(self, group: Optional[str], status: Optional[str]) -> Optional[int]:
        """按 (group, status) 查 TREND_ROWS 行号；合计/共计行特殊处理。"""
        if group is None or status is None:
            return None
        if status == "新签预计确收率":
            return 19
        if status == "合计":
            if group == "递延":
                return 10
            if group == "新签":
                return 17
            if group == "全部":
                return 18
            return None
        for idx, (g, s) in TREND_ROWS.items():
            if g == group and s == status:
                return idx
        return None

    def _note(self, line: dict) -> Optional[str]:
        """note_unplan/note_planned 合并为单条 note（DB 单列）。"""
        parts = []
        for key in ("note_unplan", "note_planned"):
            v = line.get(key)
            if v:
                parts.append(str(v))
        return "；".join(parts) if parts else None
