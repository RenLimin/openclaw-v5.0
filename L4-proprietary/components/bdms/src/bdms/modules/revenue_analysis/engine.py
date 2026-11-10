"""engine — 确收分析核心计算引擎。

以 DESIGN-DETAIL-REVENUE-ANALYSIS-v1.0 §4/§5/§6 为契约：
  - compute() → 10 Sheet 结构化数据（纯函数）
  - compute_budget_trend() → 19 行预算趋势交叉表
  - compute_dual_caliber() → 锁定/动态双口径

金额红线（2026-11-10 实测，待 Rex 拍板 A/B/C）：
  - 202609 J/K/L 全 0，预算趋势分析的「已确收/未确收/异常」金额取数
    在拍板前一律输出 None + 标注字段（amount_pending="A/B/C 待拍板"），不硬摊不造假。
  - 双口径不受影响：锁定取 202609 自身 AB 列，动态取底稿 AQ 列（均为权威列）。

🔒 NO_TOKEN — 纯代码，零 AI 依赖。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional
import datetime

from bdms.core import db as _db
from bdms.core.db import load_sheet_rows, save_sheet_rows
from bdms.modules.base import BaseEngine, ImportError_

from .config import (
    SHEET_BUDGET, SHEET_DRAFT, SHEET_SUMMARY, SHEET_SUMMARY_ANALYSIS,
    SHEET_TREND, SHEET_DIFF, SHEET_RESTRUCTURE, SHEET_LEGEND,
    SHEET_MONTHLY_RECORD, SHEET_PERF_RECORD,
    CATEGORIES, FILL_STATUS, TREND_STATUS, TREND_CATEGORY_MAP,
    PLAN_MONTHS, ACTUAL_MONTHS, TREND_ROWS,
    AMOUNT_UNIT_TREND,
)
from .importer import RevenueAnalysisImporter
from .validator import RevenueAnalysisValidator
from .caliber_builder import CaliberBuilder
from .trend_builder import TrendBuilder

PREFIX = "rr"

# 汇总 sheet 列定义（设计 §4.3）
SUMMARY_HEADERS = [
    "", "期间", "新签合同额", "新签-预计确收合同额", "新签-实际确收合同额",
    "新签-完成率", "递延-预计确收合同额", "递延-实际确收合同额",
    "递延-完成率", "合计-预计确收合同额", "合计-实际确收合同额",
    "合计-完成率", "校验",
]


class RevenueAnalysisEngine(BaseEngine):
    """确收分析引擎。"""

    module_name = "revenue_analysis"

    def __init__(self, db_path: Optional[Path] = None):
        super().__init__(db_path)
        # 幂等建表：显式 db_path（测试/临时库）也保证 ra_* schema 存在
        _db.init_db(self.db_path)
        self.importer = RevenueAnalysisImporter(self.db_path)
        self.validator = RevenueAnalysisValidator(self.db_path)
        self.caliber_builder = CaliberBuilder()
        self.trend_builder = TrendBuilder()

    # ─── 数据源 ───

    def check_sources(self, period: str) -> dict:
        conn = _db.get_connection(self.db_path)
        try:
            sheets = _db.list_sheets(conn, period, prefix=PREFIX)
            return {
                "period": period,
                "sheets": sheets,
                "has_budget": SHEET_BUDGET in sheets,
                "has_draft": SHEET_DRAFT in sheets,
            }
        finally:
            conn.close()

    def sources_available(self, period: str) -> bool:
        src = self.check_sources(period)
        return src["has_budget"] and src["has_draft"]

    def import_source(self, period: str, excel_path: Optional[Path] = None) -> dict:
        if excel_path is None:
            raise ImportError_("确收分析需显式提供源文件路径")
        return self.importer.import_all(Path(excel_path), period)

    # ─── 内部读取 ───

    def _load_budget_rows(self, period: str) -> list[dict]:
        conn = _db.get_connection(self.db_path)
        try:
            _, rows = load_sheet_rows(conn, period, SHEET_BUDGET, prefix=PREFIX)
            return rows
        finally:
            conn.close()

    def _load_draft_rows(self, period: str) -> list[dict]:
        conn = _db.get_connection(self.db_path)
        try:
            _, rows = load_sheet_rows(conn, period, SHEET_DRAFT, prefix=PREFIX)
            return rows
        finally:
            conn.close()

    @staticmethod
    def _num(v: Any) -> float:
        try:
            return float(v) if v not in (None, "") else 0.0
        except (TypeError, ValueError):
            return 0.0

    # ─── compute: 10 Sheet ───

    def compute(self, period: str) -> dict:
        """构建 10 Sheet 结构化数据。纯函数，无副作用。"""
        budget_rows = self._load_budget_rows(period)
        draft_rows = self._load_draft_rows(period)
        if not budget_rows or not draft_rows:
            raise ImportError_(
                f"{period} 宽表数据缺失: 预算执行表={len(budget_rows)} 底稿={len(draft_rows)}"
            )

        data: dict[str, Any] = {
            SHEET_BUDGET: budget_rows,
            SHEET_DRAFT: draft_rows,
            SHEET_SUMMARY: self._build_summary(budget_rows),
            SHEET_SUMMARY_ANALYSIS: self._build_summary_analysis(budget_rows),
            SHEET_TREND: self.compute_budget_trend(period),
            SHEET_DIFF: self._build_diff(budget_rows),
            SHEET_RESTRUCTURE: self._build_restructure(budget_rows),
            SHEET_LEGEND: self._build_legend(),
            SHEET_MONTHLY_RECORD: self._build_monthly_record(budget_rows),
            SHEET_PERF_RECORD: self._build_perf_record(budget_rows),
        }
        return data

    # ─── Sheet 3: 汇总 ───

    def _build_summary(self, rows: list[dict]) -> list[list[Any]]:
        """汇总（31 行 × 13 列）。设计 §4.3。"""
        out: list[list[Any]] = []
        out.append([None] * 13)                                   # R1 留空
        out.append(["", "期间", "新签合同额", "预计确收合同额", "实际确收合同额",
                    "完成率", "预计确收合同额", "实际确收合同额", "完成率",
                    "预计确收合同额", "实际确收合同额", "完成率", "校验"])  # R2 分组标题
        out.append(["", "", "新签合同", "", "", "", "递延合同", "", "",
                    "合计", "", "", ""])                          # R3 子表头

        # 按分类归档月聚合
        by_category = {c: {} for c in CATEGORIES}
        for r in rows:
            cat = r.get("A") or ""
            if cat not in by_category:
                continue
            am = str(r.get("D") or "")
            bucket = by_category[cat].setdefault(am, {
                "contract": 0.0, "plan": 0.0, "actual": 0.0,
            })
            bucket["contract"] += self._num(r.get("I"))
            bucket["plan"] += sum(self._num(r.get(L)) for L in ["P","Q","R","S","T","U","V","W","X","Y","Z","AA"])
            bucket["actual"] += sum(self._num(r.get(L)) for L in ["AG","AH","AI","AJ","AK","AL","AM","AN","AO"])

        for m in PLAN_MONTHS:
            new = by_category.get("新签", {}).get(m, {})
            def_ = by_category.get("递延", {}).get(m, {})
            plan_new = new.get("plan", 0.0)
            plan_def = def_.get("plan", 0.0)
            act_new = new.get("actual", 0.0)
            act_def = def_.get("actual", 0.0)
            out.append([
                "", m,
                round(new.get("contract", 0.0), 2),
                round(plan_new, 2), round(act_new, 2),
                round(act_new / plan_new, 6) if plan_new else 0,
                round(plan_def, 2), round(act_def, 2),
                round(act_def / plan_def, 6) if plan_def else 0,
                round(plan_new + plan_def, 2), round(act_new + act_def, 2),
                round((act_new + act_def) / (plan_new + plan_def), 6)
                if (plan_new + plan_def) else 0,
                0,
            ])

        # R16 上半年小计 / R17 全年合计（行 4-15 聚合）
        def _agg(rng: range) -> list[Any]:
            row = ["", "小计" if rng == range(0, 6) else "合计", 0.0, 0.0, 0.0, 0.0,
                   0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0]
            for i in rng:
                src = out[3 + i]  # R4 起
                for c in [2, 3, 4, 6, 7, 9, 10]:
                    row[c] += src[c] or 0
            row[5] = round(row[4] / row[3], 6) if row[3] else 0
            row[8] = round(row[7] / row[6], 6) if row[6] else 0
            row[11] = round(row[10] / row[9], 6) if row[9] else 0
            return row
        out.append(_agg(range(0, 6)))
        out.append(_agg(range(0, 12)))
        out.append(["", "说明1", "递延合同截止2026年09月实际比预计完成情况见差异分析。"])
        out.append(["", "说明2", "新签合同截止2026年09月实际比预计完成情况见差异分析。"])
        # R20-R28 履约维度
        out.append(["", "履约维度："])
        out.append(["", "类别", "新签", "递延", "合计"])
        budget_done = sum(self._num(r.get("AB")) for r in rows)
        actual_done = sum(self._num(r.get("AD")) for r in rows)
        new_budget = sum(self._num(r.get("AB")) for r in rows if r.get("A") == "新签")
        def_budget = sum(self._num(r.get("AB")) for r in rows if r.get("A") == "递延")
        out.append(["", "预算完成", round(new_budget, 2), round(def_budget, 2),
                    round(budget_done, 2)])
        out.append(["", "实际完成", "", "", round(actual_done, 2)])
        out.append(["", "预算-实际", "", "", round(budget_done - actual_done, 2)])
        out.append(["", "其中：提前完成", "", "", ""])
        out.append(["", "滞后未完成", "", "", ""])
        out.append(["", "消失", "", "", ""])
        out.append(["", "校验", "", "", 0])
        out.append([None] * 13)
        out.append([None] * 13)
        out.append([None] * 13)
        return out

    # ─── Sheet 4: 汇总分析（基础版）───

    def _build_summary_analysis(self, rows: list[dict]) -> list[list[Any]]:
        """汇总分析。设计 §4.4；先按月份×分类聚合核心块。"""
        out: list[list[Any]] = []
        out.append(["筛选：", "全部团队", "全部产线", "全部项目经理"])
        out.append([])
        out.append(["", "期间", "新签合同额", "新签-预计", "新签-实际", "新签-完成率",
                    "递延-预计", "递延-实际", "递延-完成率",
                    "合计-预计", "合计-实际", "合计-完成率"])
        by = {c: {} for c in CATEGORIES}
        for r in rows:
            cat = r.get("A") or ""
            if cat not in by:
                continue
            am = str(r.get("D") or "")
            b = by[cat].setdefault(am, {"contract": 0.0, "plan": 0.0, "actual": 0.0})
            b["contract"] += self._num(r.get("I"))
            b["plan"] += sum(self._num(r.get(L)) for L in ["P","Q","R","S","T","U","V","W","X","Y","Z","AA"])
            b["actual"] += sum(self._num(r.get(L)) for L in ["AG","AH","AI","AJ","AK","AL","AM","AN","AO"])
        for m in PLAN_MONTHS:
            n = by.get("新签", {}).get(m, {})
            d = by.get("递延", {}).get(m, {})
            pn, an, pd_, ad_ = n.get("plan", 0.0), n.get("actual", 0.0), d.get("plan", 0.0), d.get("actual", 0.0)
            out.append(["", m, round(n.get("contract", 0.0), 2), round(pn, 2), round(an, 2),
                        round(an / pn, 6) if pn else 0,
                        round(pd_, 2), round(ad_, 2), round(ad_ / pd_, 6) if pd_ else 0,
                        round(pn + pd_, 2), round(an + ad_, 2),
                        round((an + ad_) / (pn + pd_), 6) if (pn + pd_) else 0])
        return out

    # ─── Sheet 5: 预算趋势分析（19 行）───

    def compute_budget_trend(self, period: str) -> list[dict]:
        """预算趋势分析 19 行交叉表（单次路由版）。

        复刻 DESIGN-DETAIL §5.3-5.5 的 202606 口径：
          行口径 = AV 状态分组（递延 6 行 + 新签 5 行）；
          每行内 = AX 交付分类（本年正常交付 / 异常中 / 合同消失 / 未来交付）。

        路由规则（每行恰好落一个桶，保证守恒可审计）：
          1. AV 为标准状态        → 直接按 (A, AV) 归行，列桶由 AX 决定；
          2. AV="合同消失"        → 不独立成行，随同合同号主履约行（AV=本年度正常可确收）
                                    的状态归到该行「合同消失」桶（§5.5）；无主行则审计留痕；
          3. AV 空（未填报）      → 保守归 (A, 本年度正常可确收)「异常中」桶，
                                    note 显式标注未填报行数（待人工重分类，非权威状态）。
          表尾 B="合计" 的聚合行 → 不入明细计数，审计留痕。

        金额列受 202609 J/K/L 全 0 红线影响 → 一律 None + amount_pending，不硬摊不造假。
        """
        rows = self._load_budget_rows(period)
        stat = [r for r in rows
                if r.get("AU") == "统计" and r.get("A") in ("递延", "新签")]
        detail = [r for r in stat if str(r.get("B") or "").strip() != "合计"]
        excluded_total_row = len(stat) - len(detail)

        DEFERRED_STATUSES = [
            "已归档但未下单", "已下单但无法交付", "已交付但无法确收",
            "本年度正常可确收", "未来可确收", "之前年度已确收",
        ]
        NEW_STATUSES = [
            "已归档但未下单", "已下单但无法交付", "已交付但无法确收",
            "本年度正常可确收", "未来可确收",
        ]
        VALID = {"递延": set(DEFERRED_STATUSES), "新签": set(NEW_STATUSES)}

        # 主履约行状态映射（按合同号），供合同消失行随主行归桶
        main_status: dict[tuple, str] = {}
        for r in detail:
            if r.get("AV") == "本年度正常可确收":
                main_status.setdefault((r.get("A"), r.get("B")),
                                       "本年度正常可确收")

        def empty_bucket() -> dict:
            return {"normal": 0, "exception": 0, "disappear": 0,
                    "future": 0, "unfilled": 0}

        buckets: dict[tuple, dict] = {}
        for g, sts in (("递延", DEFERRED_STATUSES), ("新签", NEW_STATUSES)):
            for s in sts:
                buckets[(g, s)] = empty_bucket()

        audit = {
            "excluded_total_row": excluded_total_row,
            "disappear_routed": 0,
            "unfilled": 0,
            "unmatched_disappear": [],
        }

        def ax_to_bucket(ax: str) -> str:
            if ax == "本年正常交付":
                return "normal"
            if ax == "合同消失":
                return "disappear"
            if ax == "未来交付":
                return "future"
            return "exception"  # 异常中 / AX 空

        for r in detail:
            g = r.get("A")
            av = r.get("AV") or ""
            ax = r.get("AX") or ""

            if av in VALID[g]:
                target = av
                bucket = ax_to_bucket(ax)
            elif av == "合同消失":
                ms = main_status.get((g, r.get("B")))
                if ms is not None and (g, ms) in buckets:
                    target = ms
                    bucket = "disappear"
                    audit["disappear_routed"] += 1
                else:
                    # 无主行可随：递延归 R9，新签保守归 R15 的消失桶，并留痕
                    target = ("之前年度已确收" if g == "递延"
                              else "本年度正常可确收")
                    bucket = "disappear"
                    audit["unmatched_disappear"].append(
                        {"contract": r.get("B"), "perf": r.get("E")})
            else:
                # AV 空 = 未填报，保守归异常并标注
                target = "本年度正常可确收"
                bucket = "exception"
                buckets[(g, target)]["unfilled"] += 1
                audit["unfilled"] += 1

            buckets[(g, target)][bucket] += 1

        def make_line(g: str, status: str) -> dict:
            b = buckets[(g, status)]
            init = b["normal"] + b["exception"] + b["disappear"] + b["future"]
            note = None
            if b["unfilled"]:
                note = (f"含 AV 未填报 {b['unfilled']} 行，保守计入异常，"
                        f"待人工重分类（非权威状态）")
            return {
                "row_label": status, "group": g,
                "init_count": init, "init_amount_wan": None,
                "normal_count": b["normal"], "normal_amount_wan": None,
                "exception_count": b["exception"], "exception_amount_wan": None,
                "disappear_count": b["disappear"], "disappear_amount_wan": None,
                "future_count": b["future"], "future_amount_wan": None,
                "check_count": init, "check_amount": None,
                "note_unplan": note, "note_planned": None,
            }

        def_lines = [make_line("递延", s) for s in DEFERRED_STATUSES]
        new_lines = [make_line("新签", s) for s in NEW_STATUSES]

        lines: list[dict] = []
        lines.extend(def_lines)
        lines.append(self._trend_total("递延", def_lines))
        lines.extend(new_lines)
        lines.append(self._trend_total("新签", new_lines))
        # R18 递延+新签共计
        lines.append(self._trend_total("全部", def_lines + new_lines))
        # R19 新签预计确收率（数量口径；金额口径待拍板）
        new_total = lines[-2]
        rate = (new_total["normal_count"] / new_total["init_count"]
                if new_total["init_count"] else None)
        lines.append({
            "row_label": "新签预计确收率", "group": "新签",
            "init_count": new_total["init_count"], "init_amount_wan": None,
            "normal_count": new_total["normal_count"], "normal_amount_wan": None,
            "exception_count": new_total["exception_count"], "exception_amount_wan": None,
            "disappear_count": new_total["disappear_count"], "disappear_amount_wan": None,
            "future_count": new_total["future_count"], "future_amount_wan": None,
            "check_count": new_total["check_count"], "check_amount": None,
            "note_unplan": None, "note_planned": None,
            "recognize_rate_count": rate,
            "recognize_rate_amount": None,
        })

        # 审计 + 金额红线标注
        for line in lines:
            line["amount_unit"] = AMOUNT_UNIT_TREND
            line["amount_pending"] = "A/B/C 待拍板（202609 J/K/L 全 0，不得硬摊）"
            line["routing_audit"] = dict(audit)

        return lines
    def _trend_total(self, group: str, lines: list[dict]) -> dict:
        total: dict[str, Any] = {
            "row_label": "合计", "group": group,
            "init_count": sum(l["init_count"] for l in lines),
            "init_amount_wan": None,
            "normal_count": sum(l["normal_count"] for l in lines),
            "normal_amount_wan": None,
            "exception_count": sum(l["exception_count"] for l in lines),
            "exception_amount_wan": None,
            "disappear_count": sum(l["disappear_count"] for l in lines),
            "disappear_amount_wan": None,
            "future_count": sum(l["future_count"] for l in lines),
            "future_amount_wan": None,
            "check_count": sum(l["check_count"] for l in lines),
            "check_amount": None,
            "note_unplan": None, "note_planned": None,
        }
        return total

    # ─── Sheet 6: 确收差异分析 ───

    def _build_diff(self, rows: list[dict]) -> list[list[Any]]:
        out: list[list[Any]] = []
        out.append(["筛选：", "全部项目经理", "全部团队", ""])
        out.append(["", "消失备注", "重拆履约"])
        out.append([])
        out.append(["", "求和项:202601-09滞后未完成"])
        out.append(["", "行标签", "递延", "新签", "总计"])
        # 按 AR 消失备注聚合 AF(滞后) 金额
        agg: dict[str, dict[str, float]] = {}
        for r in rows:
            note = str(r.get("AR") or "(空白)")
            cat = r.get("A") or ""
            if cat not in ("递延", "新签"):
                continue
            v = self._num(r.get("AF"))
            agg.setdefault(note, {"递延": 0.0, "新签": 0.0})[cat] += v
        for note, vals in sorted(agg.items(), key=lambda kv: -sum(kv[1].values())):
            out.append(["", note, round(vals["递延"], 2), round(vals["新签"], 2),
                        round(vals["递延"] + vals["新签"], 2)])
        t_def = sum(v["递延"] for v in agg.values())
        t_new = sum(v["新签"] for v in agg.values())
        out.append(["", "总计", round(t_def, 2), round(t_new, 2), round(t_def + t_new, 2)])
        return out

    # ─── Sheet 7: 重拆履约 ───

    def _build_restructure(self, rows: list[dict]) -> list[list[Any]]:
        out: list[list[Any]] = []
        out.append([])
        out.append(["", "合同编号", "提前完成", "滞后未完成"])
        agg: dict[str, dict[str, float]] = {}
        for r in rows:
            no = str(r.get("B") or "")
            if not no:
                continue
            ahead = self._num(r.get("AE"))
            behind = self._num(r.get("AF"))
            if ahead or behind:
                agg.setdefault(no, {"提前": 0.0, "滞后": 0.0})
                agg[no]["提前"] += ahead
                agg[no]["滞后"] += behind
        for no, vals in sorted(agg.items(), key=lambda kv: -abs(kv[1]["提前"] + kv[1]["滞后"])):
            out.append(["", no, round(vals["提前"], 2), round(vals["滞后"], 2)])
        out.append(["", "总计",
                    round(sum(v["提前"] for v in agg.values()), 2),
                    round(sum(v["滞后"] for v in agg.values()), 2)])
        return out

    # ─── Sheet 8: 图例 ───

    def _build_legend(self) -> list[list[Any]]:
        out: list[list[Any]] = []
        out.append(["项目经理", "部门", "备注", "", "偏差-状态/趋势", "偏差-原因类别",
                    "偏差-原因类别说明", "", "滞后验收原因", "滞后验收处置措施", "",
                    "预算执行进度", "预算执行进度类别", "", "团队", "产线"])
        # 预算执行进度图例（L:M）
        for status in TREND_STATUS:
            out.append(["", "", "", "", "", "", "", "", "", "", "",
                        status, TREND_CATEGORY_MAP.get(status, ""), "", "", ""])
        return out

    # ─── Sheet 9: 月度汇总记录 ───

    def _build_monthly_record(self, rows: list[dict]) -> list[list[Any]]:
        out: list[list[Any]] = []
        out.append(["统计期间", "合同期间", "新签合同额(万)", "新签-预计(万)",
                    "新签-实际(万)", "递延-预计(万)", "递延-实际(万)",
                    "合计-预计(万)", "合计-实际(万)", "合计校准(预计)", "合计校准(实际)"])
        for r in rows:
            am = str(r.get("D") or "")
            cat = r.get("A") or ""
            plan = sum(self._num(r.get(L)) for L in ["P","Q","R","S","T","U","V","W","X","Y","Z","AA"]) / 10000
            actual = sum(self._num(r.get(L)) for L in ["AG","AH","AI","AJ","AK","AL","AM","AN","AO"]) / 10000
            out.append([
                "202609", am,
                round(self._num(r.get("I")) / 10000, 4),
                round(plan if cat == "新签" else 0, 4),
                round(actual if cat == "新签" else 0, 4),
                round(plan if cat == "递延" else 0, 4),
                round(actual if cat == "递延" else 0, 4),
                round(plan, 4), round(actual, 4), 0, 0,
            ])
        return out

    # ─── Sheet 10: 履约汇总记录 ───

    def _build_perf_record(self, rows: list[dict]) -> list[list[Any]]:
        out: list[list[Any]] = []
        out.append(["统计期间", "类别", "新签", "递延", "合计", "备注"])
        budget_new = sum(self._num(r.get("AB")) for r in rows if r.get("A") == "新签")
        budget_def = sum(self._num(r.get("AB")) for r in rows if r.get("A") == "递延")
        actual_new = sum(self._num(r.get("AD")) for r in rows if r.get("A") == "新签")
        actual_def = sum(self._num(r.get("AD")) for r in rows if r.get("A") == "递延")
        out.append(["202609", "预算完成", round(budget_new, 2), round(budget_def, 2),
                    round(budget_new + budget_def, 2), ""])
        out.append(["202609", "实际完成", round(actual_new, 2), round(actual_def, 2),
                    round(actual_new + actual_def, 2), ""])
        out.append(["202609", "预算-实际",
                    round(budget_new - actual_new, 2), round(budget_def - actual_def, 2),
                    round(budget_new + budget_def - actual_new - actual_def, 2), ""])
        out.append(["202609", "其中：提前完成", "", "", "", ""])
        out.append(["202609", "滞后未完成", "", "", "", ""])
        out.append(["202609", "消失", "", "", "", ""])
        return out

    # ─── 双口径 ───

    def compute_dual_caliber(self, period: str) -> dict:
        """锁定/动态双口径（设计 §6）。

        委托 CaliberBuilder（单一事实源）：
          - 锁定 = 预算执行表 AB「2026年预计」按 A 分类求和；
          - 动态 = 底稿 AQ 按 C 列权威分类（classifier 归一化版），
            DUE_2026 归月、IN_PIPELINE 独立桶、by_group 经 履约ID 关联预算表。
        """
        budget_rows = self._load_budget_rows(period)
        draft_rows = self._load_draft_rows(period)
        cal = self.caliber_builder.build(budget_rows, draft_rows)
        locked = cal["period_locked"]
        dynamic = cal["period_dynamic"]
        return {
            "period": period,
            "locked": {
                **locked["by_group"],
                "合计": locked["total"],
            },
            "dynamic": {
                "DUE_2026": dynamic["due_total"],
                "IN_PIPELINE": dynamic["pipeline"],
                "OTHER_2027plus": dynamic["other_2027plus"],
                "MISSING": dynamic["missing_amount"],
                "合计": dynamic["total"],
            },
            "difference": cal["difference"],
            "note": cal["note"],
        }

    # ─── load / persist / has_data ───

    def load(self, period: str) -> dict:
        conn = _db.get_connection(self.db_path)
        try:
            data: dict[str, Any] = {}
            for sheet in [SHEET_BUDGET, SHEET_DRAFT, SHEET_SUMMARY,
                          SHEET_SUMMARY_ANALYSIS, SHEET_TREND, SHEET_DIFF,
                          SHEET_RESTRUCTURE, SHEET_LEGEND, SHEET_MONTHLY_RECORD,
                          SHEET_PERF_RECORD]:
                cols, rows = load_sheet_rows(conn, period, sheet, prefix=PREFIX)
                if rows:
                    data[sheet] = rows
            return data
        finally:
            conn.close()

    def persist(self, period: str, data: dict, overwrite: bool = True) -> dict:
        conn = _db.get_connection(self.db_path)
        try:
            counts: dict[str, int] = {}
            for sheet, rows in data.items():
                if sheet == SHEET_TREND:
                    # 趋势行是 dict 列表，转成列结构
                    fields = [k for k in rows[0].keys()] if rows else []
                    n = save_sheet_rows(conn, period, sheet, fields, rows,
                                        prefix=PREFIX, overwrite=overwrite)
                    counts[sheet] = n
                elif rows and isinstance(rows[0], list):
                    # 汇总类 sheet 是 list[list]，转 dict（键为列索引字符串）
                    width = max(len(r) for r in rows)
                    fields = [str(i) for i in range(width)]
                    dict_rows = [
                        {str(i): v for i, v in enumerate(r)} for r in rows
                    ]
                    n = save_sheet_rows(conn, period, sheet, fields, dict_rows,
                                        prefix=PREFIX, overwrite=overwrite)
                    counts[sheet] = n
                elif rows:
                    # 宽表 dict 行（预算执行表/底稿）：列名取首行键，保 meta
                    fields = [k for k in rows[0].keys()]
                    n = save_sheet_rows(conn, period, sheet, fields, rows,
                                        prefix=PREFIX, overwrite=overwrite)
                    counts[sheet] = n
                else:
                    n = save_sheet_rows(conn, period, sheet, [], rows,
                                        prefix=PREFIX, overwrite=overwrite)
                    counts[sheet] = n

            # ra_* 结构化快照（P3）：双口径 + 趋势行/单元格 + 账期登记
            self._persist_caliber(conn, period, overwrite, counts)
            self._persist_trend(conn, period, data.get(SHEET_TREND) or [],
                                overwrite, counts)
            self._persist_period(conn, period, counts)
            conn.commit()
            return counts
        finally:
            conn.close()

    def _persist_caliber(self, conn, period: str, overwrite: bool,
                         counts: dict) -> None:
        """双口径快照：ra_caliber 两行（locked/dynamic）。"""
        budget_rows, draft_rows = self._load_rows_same_conn(conn, period)
        cal = self.caliber_builder.build(budget_rows, draft_rows)
        if overwrite:
            conn.execute("DELETE FROM ra_caliber WHERE period = ?", (period,))
        for caliber, snap in (("locked", cal["period_locked"]),
                              ("dynamic", cal["period_dynamic"])):
            by_group = snap["by_group"]
            if caliber == "dynamic":
                # 扩展键：分类桶（DUE/PIPE/OTHER/MISSING），供 caliber() 读快照同构
                by_group = {
                    **by_group,
                    "DUE_2026": snap["due_total"],
                    "IN_PIPELINE": snap["pipeline"],
                    "OTHER_2027plus": snap["other_2027plus"],
                    "MISSING": snap["missing_amount"],
                }
            conn.execute(
                """INSERT INTO ra_caliber
                   (period, caliber, total, by_group, by_month, created_at)
                   VALUES (?, ?, ?, ?, ?, datetime('now','localtime'))""",
                (period, caliber, snap["total"],
                 json.dumps(by_group, ensure_ascii=False),
                 json.dumps(snap["by_month"], ensure_ascii=False)),
            )
        counts["ra_caliber"] = 2
        counts["ra_caliber_diff"] = cal["difference"]
        counts["ra_caliber_note"] = cal["note"]

    def _load_rows_same_conn(self, conn, period: str):
        """用已有连接读宽表行，避免嵌套连接与写锁冲突。"""
        _, budget_rows = load_sheet_rows(conn, period, SHEET_BUDGET,
                                         prefix=PREFIX)
        _, draft_rows = load_sheet_rows(conn, period, SHEET_DRAFT,
                                        prefix=PREFIX)
        return budget_rows, draft_rows

    def _persist_trend(self, conn, period: str, lines: list[dict],
                       overwrite: bool, counts: dict) -> None:
        """趋势分析：ra_trend_row + ra_trend_cell。"""
        if not lines:
            counts["ra_trend_row"] = 0
            counts["ra_trend_cell"] = 0
            return
        rows, cells = self.trend_builder.build(lines)
        if overwrite:
            conn.execute("DELETE FROM ra_trend_row WHERE period = ?", (period,))
            conn.execute("DELETE FROM ra_trend_cell WHERE period = ?", (period,))
        for r in rows:
            conn.execute(
                """INSERT INTO ra_trend_row
                   (period, row_index, category_group, status,
                    init_count, init_amount_wan,
                    normal_count, normal_amount_wan,
                    exception_count, exception_amount_wan,
                    disappear_count, disappear_amount_wan,
                    future_count, future_amount_wan,
                    check_count, check_amount,
                    note, routing_audit, amount_pending)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (period, r["row_index"], r["category_group"], r["status"],
                 r["init_count"], r["init_amount_wan"],
                 r["normal_count"], r["normal_amount_wan"],
                 r["exception_count"], r["exception_amount_wan"],
                 r["disappear_count"], r["disappear_amount_wan"],
                 r["future_count"], r["future_amount_wan"],
                 r["check_count"], r["check_amount"],
                 r["note"],
                 json.dumps(r["routing_audit"], ensure_ascii=False)
                 if r.get("routing_audit") else None,
                 r.get("amount_pending")),
            )
        for c in cells:
            conn.execute(
                """INSERT INTO ra_trend_cell (period, row_index, col_index, value)
                   VALUES (?,?,?,?)""",
                (period, c["row_index"], c["col_index"], c["value"]),
            )
        counts["ra_trend_row"] = len(rows)
        counts["ra_trend_cell"] = len(cells)

    def _persist_period(self, conn, period: str, counts: dict) -> None:
        """账期登记：ra_period upsert。"""
        sheet_counts = {k: v for k, v in counts.items()
                        if isinstance(v, int)}
        existing = conn.execute(
            "SELECT id FROM ra_period WHERE period = ?", (period,)
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE ra_period SET source_path = ?, generated_at = ?,
                       row_counts = ?, extra = ? WHERE period = ?""",
                (self.importer.db_path and str(self.importer.db_path) or "",
                 datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 json.dumps(sheet_counts, ensure_ascii=False),
                 json.dumps({"note": counts.get("ra_caliber_note")},
                            ensure_ascii=False),
                 period),
            )
        else:
            conn.execute(
                """INSERT INTO ra_period
                   (period, source_path, generated_at, row_counts, extra)
                   VALUES (?, ?, ?, ?, ?)""",
                (period, "", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 json.dumps(sheet_counts, ensure_ascii=False),
                 json.dumps({"note": counts.get("ra_caliber_note")},
                            ensure_ascii=False)),
            )

    def has_data(self, period: str) -> bool:
        conn = _db.get_connection(self.db_path)
        try:
            sheets = _db.list_sheets(conn, period, prefix=PREFIX)
            return SHEET_BUDGET in sheets and SHEET_DRAFT in sheets
        finally:
            conn.close()
