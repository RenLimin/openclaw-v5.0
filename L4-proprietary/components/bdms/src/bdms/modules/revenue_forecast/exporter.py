"""exporter — revenue_forecast Excel 多 Sheet 导出（Phase 6）。

DESIGN-DETAIL-REVENUE-FORECAST-v1.0 §5（GET /export）、§7。

职责边界：
  - 纯拼装：全部数据来自 ForecastRepository 的现有查询方法
    （get_totals / get_monthly / query_lines），不重算、不读财报；
  - 金额单位元，并附万元列；
  - 表头/正文样式复用 modules.base.BaseExporter 的统一样式。

Sheet（顺序）：
  1. 汇总        锁定/动态/实际/gap/pipeline + 新签递延拆分
  2. 锁定逐月    12 个月
  3. 动态逐月    12 个月 DUE + pipeline 一行 + 合计
  4. 履约明细    forecast_line 全部行
  5. 风险与排除  FUTURE_YEAR / EXCEPTION / TERMINATED / NOT_STARTED / MISSING_DATE
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Union

from bdms.core.paths import DB_PATH

from .repository import (
    ForecastRepository,
    BASIS_LOCKED,
    BASIS_DYNAMIC_DUE,
    BASIS_PIPELINE,
    MONTH_KEYS,
)
from bdms.modules.base import BaseExporter, ExportError

RISK_CATEGORIES = (
    "FUTURE_YEAR", "EXCEPTION", "TERMINATED", "NOT_STARTED", "MISSING_DATE",
)
WAN = 10000.0

# 明细列：(forecast_line 字段, 表头)
LINE_COLUMNS = [
    ("obligation_id", "履约义务ID"),
    ("budget_id", "预算ID"),
    ("contract_no", "合同编号"),
    ("contract_name", "合同名称"),
    ("customer", "客户"),
    ("end_user", "最终用户"),
    ("category_group", "类别组(新签/递延)"),
    ("revenue_method", "收入确认方法"),
    ("locked_year", "锁定年度金额(元)"),
    ("actual_ytd", "实际累计(元)"),
    ("raw_due", "履约日期原文"),
    ("due_date", "履约日期"),
    ("dyn_category", "动态分类"),
    ("amount_future", "未来履约金额(元)"),
    ("dyn_in_plan", "是否计入动态"),
    ("dyn_counted", "动态计入金额(元)"),
]


class ForecastExporter:
    """双口径预估 Excel 导出器（纯拼装）。"""

    module_name = "revenue_forecast"

    def __init__(self, db_path: Optional[Union[str, Path]] = None):
        self.db_path: Path = Path(db_path) if db_path else DB_PATH

    # ─── 入口 ───

    def export(
        self,
        period: str,
        out_path: Optional[Union[str, Path]] = None,
    ) -> Path:
        """导出指定 period 的预估 Excel，返回文件路径。"""
        try:
            from openpyxl import Workbook

            repo = ForecastRepository(self.db_path)
            try:
                totals = repo.get_totals(period)
                if totals is None:
                    raise ValueError(f"账期 {period} 不存在，请先上传财报")
                locked_m = repo.get_monthly(period, BASIS_LOCKED)
                dynamic_m = repo.get_monthly(period, BASIS_DYNAMIC_DUE)
                pipeline = repo.get_monthly(period, BASIS_PIPELINE)["pipeline"]
                all_lines = self._fetch_all_lines(repo, period)

                wb = Workbook()
                if wb.active:
                    wb.remove(wb.active)
                self._write_summary(wb, totals)
                self._write_locked_monthly(wb, locked_m, totals)
                self._write_dynamic_monthly(wb, dynamic_m, pipeline, totals)
                self._write_lines(wb, all_lines)
                self._write_risks(wb, all_lines)
            finally:
                repo.close()

            if out_path:
                target = Path(out_path)
            else:
                from bdms.core.paths import output_path
                target = output_path(f"收入预估_{period}.xlsx")
            target.parent.mkdir(parents=True, exist_ok=True)
            wb.save(target)
            return target
        except ExportError:
            raise
        except Exception as e:
            raise ExportError(
                f"导出失败: {e}", details={"period": period}) from e

    # ─── Sheet 1：汇总 ───

    def _write_summary(self, wb: Any, totals: dict) -> None:
        ws = wb.create_sheet("汇总")
        period = totals["period"]
        year = totals.get("forecast_year")
        ws.cell(row=1, column=1, value=f"{year}年收入预估汇总（账期 {period}）")
        ws.cell(row=1, column=1).font = self._title_font()

        headers = ["口径", "金额(元)", "金额(万元)", "说明"]
        for c, h in enumerate(headers, 1):
            cell = ws.cell(row=3, column=c, value=h)
            BaseExporter.apply_header_style(cell)

        rows = [
            ("锁定口径", totals["locked_total"], "预算执行表锁定年度确收"),
            ("动态口径", totals["dynamic_total"], "DUE 2026 逐月 + pipeline"),
            ("实际累计", totals["actual_ytd"], "财报实际确收 YTD"),
            ("差异(动态-锁定)", totals["gap"],
             "正数=动态高于锁定"),
            ("其中：pipeline", totals["dynamic_pipeline"],
             "已提交资料、无明确2026日期"),
        ]
        for i, (name, amount, note) in enumerate(rows, 4):
            ws.cell(row=i, column=1, value=name)
            ws.cell(row=i, column=2, value=float(amount or 0.0))
            ws.cell(row=i, column=3, value=float(amount or 0.0) / WAN)
            ws.cell(row=i, column=4, value=note)
            for c in range(1, 5):
                cell = ws.cell(row=i, column=c)
                BaseExporter.apply_body_style(
                    cell, BaseExporter.NUMBER_FORMAT_FLOAT if c in (2, 3) else None)

        # 新签 / 递延拆分
        start = 4 + len(rows) + 2
        sub_headers = ["类别组", "锁定(元)", "锁定(万元)",
                       "动态(元)", "动态(万元)"]
        for c, h in enumerate(sub_headers, 1):
            cell = ws.cell(row=start, column=c, value=h)
            BaseExporter.apply_header_style(cell)
        lg = totals.get("locked_by_group") or {}
        dg = totals.get("dynamic_by_group") or {}
        groups = sorted(set(lg) | set(dg)) or ["新签", "递延"]
        for i, g in enumerate(groups, start + 1):
            lv = float(lg.get(g, 0.0))
            dv = float(dg.get(g, 0.0))
            vals = [g, lv, lv / WAN, dv, dv / WAN]
            for c, v in enumerate(vals, 1):
                cell = ws.cell(row=i, column=c, value=v)
                BaseExporter.apply_body_style(
                    cell, BaseExporter.NUMBER_FORMAT_FLOAT if c in (2, 3, 4, 5) else None)

        self._autowidth(ws, widths=(18, 20, 16, 40))

    # ─── Sheet 2：锁定逐月 ───

    def _write_locked_monthly(self, wb: Any, locked_m: dict,
                              totals: dict) -> None:
        ws = wb.create_sheet("锁定逐月")
        headers = ["月份", "锁定金额(元)", "锁定金额(万元)"]
        for c, h in enumerate(headers, 1):
            BaseExporter.apply_header_style(ws.cell(row=1, column=c, value=h))
        total = 0.0
        for i, mk in enumerate(MONTH_KEYS, 2):
            amt = float(locked_m.get(mk, 0.0))
            total += amt
            vals = [f"{int(mk)}月", amt, amt / WAN]
            for c, v in enumerate(vals, 1):
                cell = ws.cell(row=i, column=c, value=v)
                BaseExporter.apply_body_style(
                    cell, BaseExporter.NUMBER_FORMAT_FLOAT if c in (2, 3) else None)
        tr = len(MONTH_KEYS) + 2
        vals = ["合计", total, total / WAN]
        for c, v in enumerate(vals, 1):
            cell = ws.cell(row=tr, column=c, value=v)
            BaseExporter.apply_body_style(
                cell, BaseExporter.NUMBER_FORMAT_FLOAT if c in (2, 3) else None)
            cell.font = self._bold_font()
        self._autowidth(ws, widths=(10, 20, 18))

    # ─── Sheet 3：动态逐月 ───

    def _write_dynamic_monthly(self, wb: Any, dynamic_m: dict,
                               pipeline: float, totals: dict) -> None:
        ws = wb.create_sheet("动态逐月")
        headers = ["月份/桶", "动态金额(元)", "动态金额(万元)", "说明"]
        for c, h in enumerate(headers, 1):
            BaseExporter.apply_header_style(ws.cell(row=1, column=c, value=h))
        due_total = 0.0
        r = 2
        for mk in MONTH_KEYS:
            amt = float(dynamic_m.get(mk, 0.0))
            due_total += amt
            vals = [f"{int(mk)}月", amt, amt / WAN, "DUE_2026"]
            for c, v in enumerate(vals, 1):
                cell = ws.cell(row=r, column=c, value=v)
                BaseExporter.apply_body_style(
                    cell, BaseExporter.NUMBER_FORMAT_FLOAT if c in (2, 3) else None)
            r += 1
        vals = ["pipeline", float(pipeline), float(pipeline) / WAN,
                "已提交资料，无明确2026日期"]
        for c, v in enumerate(vals, 1):
            cell = ws.cell(row=r, column=c, value=v)
            BaseExporter.apply_body_style(
                cell, BaseExporter.NUMBER_FORMAT_FLOAT if c in (2, 3) else None)
        r += 1
        total = due_total + float(pipeline)
        vals = ["合计", total, total / WAN, "动态口径总额"]
        for c, v in enumerate(vals, 1):
            cell = ws.cell(row=r, column=c, value=v)
            BaseExporter.apply_body_style(
                cell, BaseExporter.NUMBER_FORMAT_FLOAT if c in (2, 3) else None)
            cell.font = self._bold_font()
        self._autowidth(ws, widths=(12, 20, 18, 32))

    # ─── Sheet 4：履约明细（全部行）───

    def _write_lines(self, wb: Any, lines: list[dict]) -> None:
        ws = wb.create_sheet("履约明细")
        for c, (_, h) in enumerate(LINE_COLUMNS, 1):
            BaseExporter.apply_header_style(ws.cell(row=1, column=c, value=h))
        money_keys = {"locked_year", "actual_ytd", "amount_future", "dyn_counted"}
        for ri, line in enumerate(lines, 2):
            for c, (key, _) in enumerate(LINE_COLUMNS, 1):
                v = line.get(key, "")
                if key == "dyn_in_plan":
                    v = "是" if v else "否"
                cell = ws.cell(row=ri, column=c, value=v)
                BaseExporter.apply_body_style(
                    cell,
                    BaseExporter.NUMBER_FORMAT_FLOAT if key in money_keys else None)
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = f"A1:{ws.cell(row=1, column=len(LINE_COLUMNS)).column_letter}1"
        self._autowidth(
            ws,
            widths=(16, 16, 16, 30, 24, 24, 14, 14, 18, 16, 24, 12, 14, 18, 12, 18),
        )

    # ─── Sheet 5：风险与排除 ───

    def _write_risks(self, wb: Any, lines: list[dict]) -> None:
        ws = wb.create_sheet("风险与排除")
        ws.cell(row=1, column=1,
                value="风险与排除清单：未计入动态 2026 的履约项（按动态分类）")
        ws.cell(row=1, column=1).font = self._title_font()

        # 分类计数汇总
        headers = ["动态分类", "行数", "未来履约金额合计(元)", "合计(万元)"]
        for c, h in enumerate(headers, 1):
            BaseExporter.apply_header_style(ws.cell(row=3, column=c, value=h))
        by_cat: dict[str, dict[str, float]] = {}
        for line in lines:
            cat = line.get("dyn_category", "")
            if cat not in RISK_CATEGORIES:
                continue
            d = by_cat.setdefault(cat, {"count": 0.0, "amount": 0.0})
            d["count"] += 1
            d["amount"] += float(line.get("amount_future") or 0.0)
        r = 4
        for cat in RISK_CATEGORIES:
            d = by_cat.get(cat, {"count": 0.0, "amount": 0.0})
            vals = [cat, int(d["count"]), d["amount"], d["amount"] / WAN]
            for c, v in enumerate(vals, 1):
                cell = ws.cell(row=r, column=c, value=v)
                BaseExporter.apply_body_style(
                    cell,
                    BaseExporter.NUMBER_FORMAT_FLOAT if c in (3, 4) else None)
            r += 1

        # 明细清单
        r += 2
        detail_cols = [
            ("dyn_category", "动态分类"),
            ("obligation_id", "履约义务ID"),
            ("contract_no", "合同编号"),
            ("contract_name", "合同名称"),
            ("customer", "客户"),
            ("category_group", "类别组"),
            ("amount_future", "未来履约金额(元)"),
            ("raw_due", "履约日期原文"),
        ]
        for c, (_, h) in enumerate(detail_cols, 1):
            BaseExporter.apply_header_style(ws.cell(row=r, column=c, value=h))
        r += 1
        for line in lines:
            if line.get("dyn_category") not in RISK_CATEGORIES:
                continue
            for c, (key, _) in enumerate(detail_cols, 1):
                cell = ws.cell(row=r, column=c, value=line.get(key, ""))
                BaseExporter.apply_body_style(
                    cell,
                    BaseExporter.NUMBER_FORMAT_FLOAT
                    if key == "amount_future" else None)
            r += 1
        ws.freeze_panes = "A11"
        self._autowidth(ws, widths=(14, 16, 16, 30, 24, 12, 20, 28))

    # ─── 工具 ───

    @staticmethod
    def _fetch_all_lines(repo: ForecastRepository, period: str,
                         page_size: int = 5000) -> list[dict]:
        """分页拉全量明细（复用 repository.query_lines，不改其契约）。"""
        first = repo.query_lines(period, page=1, page_size=page_size)
        total = first["total"]
        items = list(first["items"])
        page = 2
        while len(items) < total:
            data = repo.query_lines(period, page=page, page_size=page_size)
            if not data["items"]:
                break
            items.extend(data["items"])
            page += 1
        return items

    @staticmethod
    def _title_font() -> Any:
        from openpyxl.styles import Font
        return Font(name="微软雅黑", size=13, bold=True)

    @staticmethod
    def _bold_font() -> Any:
        from openpyxl.styles import Font
        return Font(name="微软雅黑", size=10, bold=True)

    @staticmethod
    def _autowidth(ws: Any, widths: tuple[float, ...]) -> None:
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w
