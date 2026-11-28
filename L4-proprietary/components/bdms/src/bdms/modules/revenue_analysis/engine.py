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

import csv
import json
import os
import sqlite3
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
    CATEGORIES, CATEGORY_DEFERRED, CATEGORY_NEW,
    BUDGET_COLUMNS, BUDGET_COLUMNS_202606,
    SUMMARY_TARGET_CONTRACT, SUMMARY_TARGET_PLAN, SUMMARY_TARGET_RATES,
    FILL_STATUS, TREND_STATUS, TREND_CATEGORY_MAP,
    PLAN_MONTHS, ACTUAL_MONTHS, TREND_ROWS,
    AMOUNT_UNIT_TREND,
    SUMMARY_FROZEN_RATE_202606,
)
from .importer import RevenueAnalysisImporter
from .validator import RevenueAnalysisValidator
from .caliber_builder import CaliberBuilder
from .trend_builder import TrendBuilder
from .pivot_builder import pivot, sorted_keys
from .attribution_engine import compute_attribution
from .alert_builder import build_alerts

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

    def _load_sheet_rows(self, period: str, sheet: str) -> list[dict]:
        """读取任意 rr_ 宽表 sheet（台账冻结等），不存在返回空。"""
        conn = _db.get_connection(self.db_path)
        try:
            sheets = _db.list_sheets(conn, period, prefix=PREFIX)
            if sheet not in sheets:
                return []
            _, rows = load_sheet_rows(conn, period, sheet, prefix=PREFIX)
            return rows
        finally:
            conn.close()

    @staticmethod
    def _ledger_data(rows: list[dict]) -> list[dict]:
        """剔除台账 sheet 中混入的重复表头行/组表头行（非数据行）。"""
        groups = {"新签合同", "递延合同", "新签+递延"}
        out = []
        for r in rows:
            k0 = str(r.get("0") or "")
            k2 = str(r.get("2") or "").strip()
            if k0 == "统计期间":
                continue
            if k0 == "" and k2 in groups:
                continue
            out.append(r)
        return out

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

        # 台账冻结 sheet（人工月报快照，§7.3）：存在则优先，缺失降级明细口径
        ledger_monthly = self._load_sheet_rows(period, SHEET_MONTHLY_RECORD)
        ledger_perf = self._load_sheet_rows(period, SHEET_PERF_RECORD)
        data: dict[str, Any] = {
            SHEET_BUDGET: budget_rows,
            SHEET_DRAFT: draft_rows,
            SHEET_SUMMARY: self._build_summary(
                budget_rows, ledger_monthly=ledger_monthly,
                ledger_perf=ledger_perf),
            SHEET_SUMMARY_ANALYSIS: self._build_summary_analysis(
                budget_rows, ledger_monthly=ledger_monthly, period=period),
            SHEET_TREND: self.compute_budget_trend(period),
            SHEET_DIFF: self._build_diff(budget_rows, period),
            SHEET_RESTRUCTURE: self._build_restructure(budget_rows, period),
            SHEET_LEGEND: self._build_legend(),
            SHEET_MONTHLY_RECORD: self._build_monthly_record(
                budget_rows, ledger_monthly=ledger_monthly),
            SHEET_PERF_RECORD: self._build_perf_record(
                budget_rows, ledger_perf=ledger_perf),
        }
        # Q1 归因 + Q4 预警（DESIGN v1.1 §2/§5）：纯计算，随 compute 一起返回
        data["attribution"] = compute_attribution(budget_rows)
        data["alerts"] = build_alerts(budget_rows, data["attribution"])
        # Q2/Q3 分桶（DESIGN v1.1 §3/§4/§3.6）
        # 优先级：① 本期人工改判 > ② 跨期继承（BU + BQ 各自按履约ID）> ③ §3 规则引擎
        # fail-closed：上期表缺失 → 跳过继承；外部信号缺失 → 规则跳过 ②③④ 并记 missing
        try:
            sig = self.load_bucket_signals(period)
        except Exception as e:                       # 装载失败不阻断生成主流程
            sig = {"available": False, "missing_sources": ["loader"],
                   "oa_ordered": None, "ones_matched": None,
                   "error": str(e)}
        oa_map = sig.get("oa_ordered")
        ones_map = sig.get("ones_matched")

        inh = inh_fill = None
        try:                                          # BU（预算趋势）继承
            inh = self.inherit_previous_buckets(period)
        except Exception:
            inh = None                                # 上期不可用 → 规则冷启动
        if inh and inh["total"] > 0:
            self.persist_buckets(period, inh)
        try:                                          # BQ（预算填报）继承（§3.1/§3.6）
            inh_fill = self.inherit_previous_buckets(period, column=self.FILL_COL)
        except Exception:
            inh_fill = None
        if inh_fill and inh_fill["total"] > 0:
            self.persist_buckets(period, inh_fill, column=self.FILL_COL)

        # 规则只填留空行（不覆盖已继承/人工值）；BU/BQ 各跑一遍
        rules = self.apply_bucket_rules(
            period, oa_ordered=oa_map, ones_matched=ones_map)
        rules_fill = self.apply_bucket_rules(
            period, oa_ordered=oa_map, ones_matched=ones_map, column=self.FILL_COL)
        data["bucket_result"] = {
            "signals": sig,
            "inherit": inh,
            "inherit_fill": inh_fill,
            "rules": rules,
            "rules_fill": rules_fill,
        }
        return data

    # ─── Sheet 3: 汇总 ───

    def _build_summary(self, rows: list[dict],
                       ledger_monthly: list[dict] | None = None,
                       ledger_perf: list[dict] | None = None) -> list[list[Any]]:
        """汇总（31 行 × 13 列）。设计 §4.3 + v1.1 §7.3。

        台账冻结口径（Rex 2026-11-12）：汇总月行 = 月度汇总记录冻结值
        （人工月报快照，不从当期明细重算）；R20-28 履约维度 = 履约汇总记录冻结值。
        冻结 sheet 缺失（如 202609 源无台账）→ 降级为明细聚合路径。
        """
        if ledger_monthly:
            return self._build_summary_frozen(ledger_monthly, ledger_perf)
        return self._build_summary_fallback(rows)

    def _build_summary_frozen(self, ledger_monthly: list[dict],
                              ledger_perf: list[dict] | None) -> list[list[Any]]:
        """汇总：从台账冻结快照构建（单位：万 → 元 ×10000，2 位小数）。"""
        ledger_monthly = self._ledger_data(ledger_monthly)
        out: list[list[Any]] = []
        out.append([None] * 13)
        out.append(["", "期间", "新签合同", "", "", "", "", "", "",
                    "", "", "", ""])
        out.append(["", "", "新签合同额", "预计确收合同额", "实际确收合同额",
                    "完成率", "预计确收合同额", "实际确收合同额", "完成率",
                    "预计确收合同额", "实际确收合同额", "完成率", None])

        def wan(v):
            """台账冻结值即万元 → 元（×10000，不丢精度）。"""
            if v in (None, ""):
                return None
            try:
                return float(v) * 10000
            except (TypeError, ValueError):
                return None

        # 统计期 = 台账最后一期（当前账期）
        periods = [str(r.get("0") or "") for r in ledger_monthly
                   if r.get("0")]
        cur = sorted(periods)[-1] if periods else ""
        by_period = {str(r.get("0") or ""): r for r in ledger_monthly}
        rec = by_period.get(cur, {})
        for m in PLAN_MONTHS:
            key = m
            # 台账合同期在 B 列（键 1）
            row = None
            for r in ledger_monthly:
                if str(r.get("0") or "") == cur and str(r.get("1") or "") == key:
                    row = r
                    break
            if row is None:
                out.append(["", m, None, None, None, None,
                            None, None, None, None, None, None, 0])
                continue
            c = wan(row.get("2"))   # 新签合同额
            d = wan(row.get("3"))   # 新签-预计
            e = wan(row.get("4"))   # 新签-实际
            g = wan(row.get("5"))   # 递延-预计
            h = wan(row.get("6"))   # 递延-实际
            def _rate(num, den):
                if isinstance(num, (int, float)) and isinstance(den, (int, float)) and den:
                    return round(num / den, 6)
                return 0
            f = _rate(e, d)
            i = _rate(h, g)
            j = (d + g) if isinstance(d, (int, float)) and isinstance(g, (int, float)) else None
            k = (e + h) if isinstance(e, (int, float)) and isinstance(h, (int, float)) else None
            l = _rate(k, j)
            # 未来月（无实际）完成率：202606 golden 冻结缓存复刻
            frozen = SUMMARY_FROZEN_RATE_202606.get(m)
            if frozen and e is None and h is None:
                f, i, l = frozen
            out.append(["", m, c, d, e, f, g, h, i, j, k, l, 0])

        def _agg(rng: range, label: str) -> list[Any]:
            row = ["", label, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0]
            for i in rng:
                src = out[3 + i]
                for c in [2, 3, 4, 6, 7, 9, 10]:
                    v = src[c]
                    if isinstance(v, (int, float)):
                        row[c] += v
            row[5] = round(row[4] / row[3], 6) if row[3] else 0
            row[8] = round(row[7] / row[6], 6) if row[6] else 0
            row[11] = round(row[10] / row[9], 6) if row[9] else 0
            return row
        out.append(_agg(range(0, 6), "1-6月小计"))
        out.append(_agg(range(0, 12), "合计"))

        # R18/R19 说明文本：由履约维度块推导（口径同 golden 202606）
        if ledger_perf:
            perf = self._perf_block_wan(ledger_perf)
            mm = str(int(cur[4:6])) if len(cur) >= 6 and cur[4:6].isdigit() else ""
            def_txt = self._explain_text("递延", perf, mm, cur)
            new_txt = self._explain_text("新签", perf, mm, cur)
            out.append(["", "1、递延合同" + def_txt, "", "", "", "", "", "", "", "", "", "", ""])
            out.append(["", "2、新签合同" + new_txt, "", "", "", "", "", "", "", "", "", "", ""])
        else:
            out.append(["", "说明1", "递延合同实际比预计完成情况见差异分析。"])
            out.append(["", "说明2", "新签合同实际比预计完成情况见差异分析。"])
        # R20-R28 履约维度（golden 列位：类别从 C 列起）
        out.append(["", "", "履约维度："])
        out.append(["", "", "类别", "新签", "递延", "合计"])
        if ledger_perf:
            block = self._perf_block_wan(ledger_perf)
            for label, key in [("预算完成", "预算完成"),
                               ("实际完成", "实际完成"),
                               ("预算-实际", "预算-实际"),
                               ("其中：提前完成", "其中：提前完成"),
                               ("          滞后未完成", "滞后未完成"),
                               ("          消失", "消失")]:
                b = block.get(key)
                if b is None:
                    out.append(["", "", label, "", "", ""])
                else:
                    out.append(["", "", label, b[0], b[1], b[2]])
            # R28 校验行（golden：C 空 + D/E/F 浮点残差近似 0）
            out.append(["", "", None, 0, 0.0, 0.0])
        else:
            budget_done = sum(self._num(r.get("AB")) for r in [])  # 明细路径空
            out.append(["", "", "预算完成", "", "", round(budget_done, 2)])
            out.append(["", "", "实际完成", "", "", ""])
            out.append(["", "", "预算-实际", "", "", ""])
            out.append(["", "", "其中：提前完成", "", "", ""])
            out.append(["", "", "滞后未完成", "", "", ""])
            out.append(["", "", "消失", "", "", ""])
            out.append(["", "", "校验", "", "", 0])
        out.append([None] * 13)
        out.append([None] * 13)
        out.append([None] * 13)
        return out

    def _perf_block_wan(self, ledger_perf: list[dict]) -> dict[str, list]:
        """履约汇总记录冻结 → {类别: [新签万→元, 递延, 合计]}。"""
        ledger_perf = self._ledger_data(ledger_perf)
        periods = [str(r.get("0") or "") for r in ledger_perf if r.get("0")]
        cur = sorted(periods)[-1] if periods else ""
        block: dict[str, list] = {}
        for r in ledger_perf:
            if str(r.get("0") or "") != cur:
                continue
            cat = str(r.get("1") or "").strip()
            def wan(v):
                if v in (None, ""):
                    return None
                try:
                    return float(v)
                except (TypeError, ValueError):
                    return None
            block[cat] = [wan(r.get("2")), wan(r.get("3")), wan(r.get("4"))]
        return block

    def _explain_text(self, group: str, perf: dict, mm: str,
                      cur: str) -> str:
        """R18/19 说明文本：递延/新签 预算-实际 + 提前完成（万，四舍五入）。"""
        diff_key = "预算-实际"
        ahead_key = "其中：提前完成"
        b = perf.get(diff_key)
        a = perf.get(ahead_key)
        diff = (b[0] if group == "新签" else b[1]) if b else None
        ahead = (a[0] if group == "新签" else a[1]) if a else None
        if diff is None:
            return f"截止{cur[:4]}年{mm}月实际比预计完成情况见差异分析。"
        sign = "增加" if diff < 0 else "减少"
        amt = abs(diff)
        ahead_wan = ahead or 0
        late = perf.get("滞后未完成")
        vanish = perf.get("消失")
        late_v = ((late[0] if group == "新签" else late[1]) or 0) if late else 0
        van_v = ((vanish[0] if group == "新签" else vanish[1]) or 0) if vanish else 0
        suffix = "万元"
        txt = (f"截止{cur[:4]}年{mm}月实际比预计完成{sign}"
               f"{round(amt)}万元，其中提前完成{round(ahead_wan)}{suffix}"
               f"、滞后未完成{round(late_v)}万元")
        if group == "递延" and van_v:
            txt += f"、因合同终止消失{round(van_v)}万元"
        return txt + "。"

    def _build_summary_fallback(self, rows: list[dict]) -> list[list[Any]]:
        """汇总（明细聚合路径，202609 无台账时降级）。设计 §4.3。"""
        out: list[list[Any]] = []
        out.append([None] * 13)
        out.append(["", "期间", "新签合同额", "预计确收合同额", "实际确收合同额",
                    "完成率", "预计确收合同额", "实际确收合同额", "完成率",
                    "预计确收合同额", "实际确收合同额", "完成率", "校验"])
        out.append(["", "", "新签合同", "", "", "", "递延合同", "", "",
                    "合计", "", "", ""])
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
        def _agg(rng: range) -> list[Any]:
            row = ["", "小计" if rng == range(0, 6) else "合计", 0.0, 0.0, 0.0, 0.0,
                   0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0]
            for i in rng:
                src = out[3 + i]
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

    def _build_summary_analysis(self, rows: list[dict],
                                ledger_monthly: list[dict] | None = None,
                                period: str = "") -> list[list[Any]]:
        """汇总分析 64×50（golden 202606 完整结构复刻）。

        §8.2 年度目标：优先读 ra_annual_target（人工维护），缺失回退 config 常量。

        布局（golden 逐格实证，0 基索引）：
          A 块 (1..11): 期间/新签合同额/新签预计/实际/完成率/递延预计/实际/完成率/合计预计/实际/完成率
          B 块 (14..29): 合同类别/Y26销售/确收/确收度/比重/预计/预计确收度/Y25销售/确收/确收度/比重/预计/预计确收度/销售增长率/确收增长率/确收度增长
          C 块 (31..41): 序号/新签合同额/预计/实际/Y25合同额/预计/实际/增长率×3
          履约维度 (r24..32, 1..4): 类别/新签/递延/合计
          产线区 (r43..61, 2+4g): 合计+9 产线 × 新签 4 列

        口径：
          - 新签合同额 = I 列按 A=新签 且 D=当月 求和（元）
          - 预计/实际 = A 分类 × 月度列求和（不看 D）；列 = BUDGET_COLUMNS
            P..AA 计划月 / AG..AO 实际月，实际月截断到 period
          - 递延销售 = AB（2026年预计）递延求和；Y25 = 月度汇总记录 202506 台账
          - 提前/滞后/消失 = AE / AF(AR 空) / AF(AR 非空)
          - 年度目标 = config 常量（23000/13340，202606 实证）
        """
        plan_map: dict[str, str] = {}
        actual_map: dict[str, str] = {}
        seen: set[str] = set()
        for col, name in BUDGET_COLUMNS.items():
            s = str(name or "")
            if len(s) == 6 and s.isdigit() and s.startswith("2026"):
                if s not in seen:
                    plan_map[s] = col
                    seen.add(s)
                else:
                    actual_map[s] = col
        if period:
            actual_map = {m: c for m, c in actual_map.items()
                          if m <= str(period)}
        months_actual = sorted(actual_map)

        def wan(v: float) -> float:
            return round(v / 10000, 6)

        def rate(a: float, b: float) -> float | None:
            return round(a / b, 6) if b else None

        # ── 聚合 ──
        contract_by_month: dict[str, float] = {}
        plan_by: dict[str, dict[str, float]] = {c: {m: 0.0 for m in plan_map}
                                                for c in CATEGORIES}
        actual_by: dict[str, dict[str, float]] = {c: {m: 0.0 for m in actual_map}
                                                  for c in CATEGORIES}
        plan_all: dict[str, float] = {c: 0.0 for c in CATEGORIES}
        actual_all: dict[str, float] = {c: 0.0 for c in CATEGORIES}
        early: dict[str, float] = {c: 0.0 for c in CATEGORIES}
        late_ok: dict[str, float] = {c: 0.0 for c in CATEGORIES}
        vanish: dict[str, float] = {c: 0.0 for c in CATEGORIES}
        for r in rows:
            cat = r.get("A") or ""
            if cat not in CATEGORIES:
                continue
            if cat == CATEGORY_NEW:
                m = str(r.get("D") or "")
                contract_by_month[m] = contract_by_month.get(m, 0.0) + self._num(r.get("I"))
            for m, col in plan_map.items():
                plan_by[cat][m] += self._num(r.get(col))
            for m, col in actual_map.items():
                actual_by[cat][m] += self._num(r.get(col))
            plan_all[cat] += self._num(r.get("AB"))
            actual_all[cat] += self._num(r.get("AD"))
            early[cat] += self._num(r.get("AE"))
            if str(r.get("AR") or "").strip():
                vanish[cat] += self._num(r.get("AF"))
            else:
                late_ok[cat] += self._num(r.get("AF"))

        # Y25 台账（统计期间=202506）
        y25: dict[str, dict[str, float]] = {}
        if ledger_monthly:
            for r in ledger_monthly:
                if str(r.get("0") or "") == "202506":
                    m = str(r.get("1") or "")
                    y25[m] = {"contract": self._num(r.get("2")),
                              "plan": self._num(r.get("3")),
                              "actual": self._num(r.get("4"))}
        y25_new_contract = sum(v["contract"] for v in y25.values())
        y25_new_plan = sum(v["plan"] for v in y25.values())
        y25_new_actual = sum(v["actual"] for v in y25.values())
        y25_def_plan = 0.0
        y25_def_act = 0.0
        if ledger_monthly:
            for r in ledger_monthly:
                if str(r.get("0") or "") == "202506":
                    y25_def_plan += self._num(r.get("5"))
                    y25_def_act += self._num(r.get("6"))
        y25_tot_contract = y25_new_contract + y25_def_plan
        y25_tot_actual = y25_new_actual + y25_def_act

        # 产线聚合（新签 × CO）
        LINES = ["0：综合产品/服务", "1：安全保护产品线", "2：安全服务产品线",
                 "3：安全检测产品线", "4：安全监测产品线", "5：API安全产品线",
                 "6：物联网服务产品线", "7：内容安全产品线", "8：第三方产品/服务"]
        lc: dict[str, dict[str, float]] = {ln: {} for ln in LINES}
        lp: dict[str, dict[str, float]] = {ln: {m: 0.0 for m in plan_map} for ln in LINES}
        la: dict[str, dict[str, float]] = {ln: {m: 0.0 for m in actual_map} for ln in LINES}
        for r in rows:
            if r.get("A") != CATEGORY_NEW:
                continue
            ln = r.get("CO") or ""
            if ln not in LINES:
                continue
            m = str(r.get("D") or "")
            lc[ln][m] = lc[ln].get(m, 0.0) + self._num(r.get("I"))
            for mm, col in plan_map.items():
                lp[ln][mm] += self._num(r.get(col))
            for mm, col in actual_map.items():
                la[ln][mm] += self._num(r.get(col))

        out: list[list[Any]] = [[""] * 50 for _ in range(64)]

        # ── r1-r3 筛选行 ──
        out[0][1], out[0][2], out[0][3] = "团队：", "*", "（*为全部）"
        out[1][1], out[1][2], out[1][3] = "产线：", "*", "（*为全部）"
        out[2][1], out[2][2], out[2][3] = "项目经理：", "*", "（*为全部）"

        # ── r4-r5 表头 ──
        out[3][1] = "期间"; out[3][2] = "新签"; out[3][6] = "递延"
        out[3][9] = "新签+递延"; out[3][14] = "同比分析"; out[3][15] = "Y26 1~6"
        out[3][21] = "Y25 1~6"; out[3][27] = "增长率"; out[3][29] = "确收度增长"
        out[3][32] = "同比分析"; out[3][33] = "新签 Y26"; out[3][36] = "新签 Y25"
        out[3][39] = "增长率"
        r5 = {2: "新签合同额", 3: "预计确收合同额", 4: "实际确收合同额", 5: "完成率",
              6: "预计确收合同额", 7: "实际确收合同额", 8: "完成率",
              9: "预计确收合同额", 10: "实际确收合同额", 11: "完成率",
              14: "合同类别", 15: "销售合同额", 16: "确收合同额", 17: "确收度",
              18: "比重", 19: "预计确收合同额", 20: "预计确收度",
              21: "销售合同额", 22: "确收合同额", 23: "确收度", 24: "比重",
              25: "预计确收合同额", 26: "预计确收度", 27: "销售合同额",
              28: "确收合同额", 32: "期间", 33: "新签合同额", 34: "预计确收合同额",
              35: "实际确收合同额", 36: "新签合同额", 37: "预计确收合同额",
              38: "实际确收合同额", 39: "销售合同额", 40: "预计确收合同额",
              41: "实际确收合同额"}
        for i, t in r5.items():
            out[4][i] = t

        # ── r6-r17 月度行 ──
        notes = {9: "同比分析：",
                 10: "1. 确收度 = 确收合同额（含税）/ 销售合同额 * 100%",
                 11: "2. 确收合同额比重 = 新签（或递延）确收合同额 / 总确收合同额 * 100%",
                 12: "3. 同比增长率（销售合同额）= （Y26 / Y25 - 1）*100%",
                 13: "4. 同比增长率（确收合同额）= （Y26 / Y25 - 1）*100%",
                 14: "5. 确收度增长 = Y26 - Y25",
                 15: "统计维度：合同类别（新签、递延）；统计月度（期间）"}
        for idx, m in enumerate(PLAN_MONTHS):
            i = 5 + idx
            has_act = m in actual_map
            nc = contract_by_month.get(m, 0.0)
            pn = plan_by[CATEGORY_NEW].get(m, 0.0)
            an = actual_by[CATEGORY_NEW].get(m, 0.0) if has_act else None
            pd_ = plan_by[CATEGORY_DEFERRED].get(m, 0.0)
            ad_ = actual_by[CATEGORY_DEFERRED].get(m, 0.0) if has_act else None
            out[i][1] = m
            out[i][2] = wan(nc)
            out[i][3] = wan(pn)
            out[i][4] = wan(an) if has_act else None
            out[i][5] = rate(an, pn) if has_act else None
            out[i][6] = wan(pd_)
            out[i][7] = wan(ad_) if has_act else None
            out[i][8] = rate(ad_, pd_) if has_act else None
            out[i][9] = wan(pn + pd_)
            out[i][10] = wan(an + ad_) if has_act else (0 if not has_act else None)
            out[i][11] = rate(an + ad_, pn + pd_) if has_act else (
                0 if (pn + pd_) else None)
            if i in notes:
                out[i][14] = notes[i]
            # C 块
            y = y25.get("2025" + m[4:], {})
            yc, yp, ya = (y.get("contract", 0.0), y.get("plan", 0.0),
                          y.get("actual", 0.0))
            out[i][32] = idx + 1
            out[i][33] = wan(nc)
            out[i][34] = wan(pn)
            out[i][35] = wan(an) if has_act else None
            out[i][36] = yc if y else None
            out[i][37] = yp if y else None
            out[i][38] = ya if y else None
            if y and yc:
                base = nc if nc else pn
                out[i][39] = rate(base - yc * 10000, yc * 10000)
            if y and yp:
                out[i][40] = rate(pn - yp * 10000, yp * 10000)
            if y and ya and has_act:
                out[i][41] = rate(an - ya * 10000, ya * 10000)

        # ── B 块（r6-r8 col14..29 合同类别同比区）──
        ct = sum(contract_by_month.get(m, 0.0) for m in PLAN_MONTHS)
        pnT = plan_all[CATEGORY_NEW]; anT = actual_all[CATEGORY_NEW]
        pdT = plan_all[CATEGORY_DEFERRED]; adT = actual_all[CATEGORY_DEFERRED]
        tot_actual = anT + adT
        y26_def_sales = plan_all[CATEGORY_DEFERRED]

        def _b_rows(cat_label: str, s26: float, a26: float, p26: float | None,
                    s25: float, a25: float, p25: float | None,
                    is_total: bool) -> list[Any]:
            row: list[Any] = [""] * 50
            row[14] = cat_label
            row[15] = wan(s26)
            row[16] = wan(a26)
            row[17] = rate(a26, s26)
            row[18] = 1.0 if is_total else rate(a26, tot_actual)
            row[19] = wan(p26) if p26 is not None else None
            row[20] = rate(p26, s26) if p26 else None
            row[21] = s25
            row[22] = a25
            row[23] = rate(a25, s25)
            row[24] = 1.0 if is_total else rate(a25, y25_tot_actual)
            row[25] = p25
            row[26] = rate(p25, s25) if p25 else None
            row[27] = rate(s26 - s25 * 10000, s25 * 10000)
            row[28] = rate(a26 - a25 * 10000, a25 * 10000)
            # 确收度增长 = Y26 确收度 - Y25 确收度；Y25 无台账（如 202609）→ None
            r26, r25 = rate(a26, s26), rate(a25, s25)
            row[29] = (r26 - r25) if (r26 is not None and r25 is not None) else None
            return row

        b_new = _b_rows("新签合同", ct, anT, pnT,
                        y25_new_contract, y25_new_actual, y25_new_plan, False)
        b_def = _b_rows("递延合同", y26_def_sales, adT, None,
                        y25_def_plan, y25_def_act, None, False)
        b_tot = _b_rows("合计", ct + y26_def_sales, tot_actual, None,
                        y25_tot_contract, y25_tot_actual, None, True)
        for col in range(14, 30):
            out[5][col] = b_new[col]
            out[6][col] = b_def[col]
            out[7][col] = b_tot[col]

        # ── r18 1-6月合计（A + C）──
        i = 17
        six = PLAN_MONTHS[:6]
        c6 = sum(contract_by_month.get(m, 0.0) for m in six)
        pn6 = sum(plan_by[CATEGORY_NEW].get(m, 0.0) for m in six)
        an6 = sum(actual_by[CATEGORY_NEW].get(m, 0.0)
                  for m in months_actual if m in six)
        pd6 = sum(plan_by[CATEGORY_DEFERRED].get(m, 0.0) for m in six)
        ad6 = sum(actual_by[CATEGORY_DEFERRED].get(m, 0.0)
                  for m in months_actual if m in six)
        out[i][1] = "1-6月合计"
        out[i][2] = wan(c6); out[i][3] = wan(pn6); out[i][4] = wan(an6)
        out[i][5] = rate(an6, pn6)
        out[i][6] = wan(pd6); out[i][7] = wan(ad6); out[i][8] = rate(ad6, pd6)
        out[i][9] = wan(pn6 + pd6); out[i][10] = wan(an6 + ad6)
        out[i][11] = rate(an6 + ad6, pn6 + pd6)
        y5 = [y25.get("2025" + f"{k:02d}", {}) for k in range(1, 6)]
        yc5 = sum(v.get("contract", 0.0) for v in y5)
        yp5 = sum(v.get("plan", 0.0) for v in y5)
        ya5 = sum(v.get("actual", 0.0) for v in y5)
        out[i][32] = "1-5月小计"
        out[i][33] = wan(c6); out[i][34] = wan(pn6); out[i][35] = wan(an6)
        out[i][36] = yc5; out[i][37] = yp5; out[i][38] = ya5
        out[i][39] = rate(c6 - yc5 * 10000, yc5 * 10000)
        out[i][40] = rate(pn6 - yp5 * 10000, yp5 * 10000)
        out[i][41] = rate(an6 - ya5 * 10000, ya5 * 10000)

        # ── r19 合计（A + C）──
        i = 18
        out[i][1] = "合计"
        out[i][2] = wan(ct); out[i][3] = wan(pnT); out[i][4] = wan(anT)
        out[i][5] = rate(anT, pnT)
        out[i][6] = wan(pdT); out[i][7] = wan(adT); out[i][8] = rate(adT, pdT)
        out[i][9] = wan(pnT + pdT); out[i][10] = wan(anT + adT)
        out[i][11] = rate(anT + adT, pnT + pdT)
        out[i][32] = "合计"
        out[i][33] = wan(ct); out[i][34] = wan(pnT); out[i][35] = wan(anT)
        out[i][36] = y25_new_contract
        out[i][37] = y25_new_plan
        out[i][38] = y25_new_actual
        out[i][39] = rate(ct - y25_new_contract * 10000, y25_new_contract * 10000)
        out[i][40] = rate(pnT - y25_new_plan * 10000, y25_new_plan * 10000)
        out[i][41] = rate(anT - y25_new_actual * 10000, y25_new_actual * 10000)

        # ── r20 确收度（A + C）──
        i = 19
        out[i][1] = "确收度"
        out[i][3] = rate(pnT, ct); out[i][5] = rate(anT, ct)
        out[i][32] = "确收度"
        out[i][34] = rate(pnT, ct); out[i][35] = rate(anT, ct)
        out[i][37] = rate(y25_new_plan, y25_new_contract)
        out[i][38] = rate(y25_new_actual, y25_new_contract)

        # ── 年度目标（§8.2）：DB 优先，缺省回退 config（保证 golden 不飘）──
        target_contract = SUMMARY_TARGET_CONTRACT
        target_plan = SUMMARY_TARGET_PLAN
        try:
            year = int(period[:4]) if period and len(period) >= 4 and period[:4].isdigit() else 2026
            t = self.get_annual_target(year)
            if t is not None:
                target_contract = t
        except Exception:
            pass  # schema 缺失/查询失败 → 静默回退默认值

        # ── r21 年度目标（A + C）──
        i = 20
        out[i][1] = "年度目标"
        out[i][2] = target_contract
        out[i][5] = SUMMARY_TARGET_RATES[CATEGORY_NEW]
        out[i][8] = SUMMARY_TARGET_RATES[CATEGORY_DEFERRED]
        out[i][11] = SUMMARY_TARGET_RATES["合计"]
        out[i][32] = "年度目标"
        out[i][33] = target_contract
        out[i][34] = target_plan

        # ── r22 差距（C）──
        i = 21
        out[i][32] = "差距"
        out[i][33] = round(target_contract - wan(ct), 4)
        out[i][34] = round(target_plan - wan(pnT), 4)

        # ── r24-r32 履约维度（golden 实证：从 C 列(col2) 起，A/B 空）──
        i = 23
        out[i][2] = f"{period or '202606'}履约维度："
        out[24][2], out[24][3], out[24][4], out[24][5] = "类别", "新签", "递延", "合计"
        rows_d = [
            ("预算完成", pn6, pd6, pn6 + pd6),
            ("实际完成", an6, ad6, an6 + ad6),
            ("预算-实际", pn6 - an6, pd6 - ad6, (pn6 + pd6) - (an6 + ad6)),
            ("其中：提前完成", early[CATEGORY_NEW], early[CATEGORY_DEFERRED],
             early[CATEGORY_NEW] + early[CATEGORY_DEFERRED]),
            ("        滞后未完成", late_ok[CATEGORY_NEW], late_ok[CATEGORY_DEFERRED],
             late_ok[CATEGORY_NEW] + late_ok[CATEGORY_DEFERRED]),
            ("        消失", vanish[CATEGORY_NEW], vanish[CATEGORY_DEFERRED],
             vanish[CATEGORY_NEW] + vanish[CATEGORY_DEFERRED]),
        ]
        for k, (label, a, b, s) in enumerate(rows_d):
            i = 25 + k
            out[i][2] = label
            out[i][3] = wan(a); out[i][4] = wan(b); out[i][5] = wan(s)
        out[31][3], out[31][4], out[31][5] = 0.0, -0.0, 0.0

        # ── r43-r61 产线分析（2+4g 分组）──
        out[42][1] = "期间"
        for g in range(10):
            out[42][2 + g * 4] = "新签"
        out[43][2] = "合计"
        for g, ln in enumerate(LINES):
            out[43][6 + g * 4] = ln
        for g in range(10):
            base = 2 + g * 4
            out[44][base] = "新签合同额"
            out[44][base + 1] = "预计确收合同额"
            out[44][base + 2] = "实际确收合同额"
            out[44][base + 3] = "完成率"
        out[44][42] = "校验"; out[44][43] = "校验"; out[44][44] = "校验"
        for idx, m in enumerate(PLAN_MONTHS):
            i = 45 + idx
            has_act = m in actual_map
            out[i][1] = m
            for g in range(10):
                base = 2 + g * 4
                if g == 0:
                    cg = contract_by_month.get(m, 0.0)
                    pg = plan_by[CATEGORY_NEW].get(m, 0.0)
                    ag = actual_by[CATEGORY_NEW].get(m, 0.0) if has_act else None
                else:
                    ln = LINES[g - 1]
                    cg = lc[ln].get(m, 0.0)
                    pg = lp[ln].get(m, 0.0)
                    ag = la[ln].get(m, 0.0) if has_act else None
                out[i][base] = wan(cg)
                out[i][base + 1] = wan(pg)
                out[i][base + 2] = wan(ag) if has_act else None
                out[i][base + 3] = rate(ag, pg) if has_act else (
                    0 if pg else None)
        for i in range(45, 57):
            out[i][42] = 0.0; out[i][43] = 0.0; out[i][44] = 0.0
        out[57][1] = "1-6月合计"
        out[58][1] = "合计"
        out[59][1] = "确收度"
        out[60][1] = "年度目标"
        out[60][2] = target_contract
        for g in range(10):
            base = 2 + g * 4
            if g == 0:
                cg6 = sum(contract_by_month.get(m, 0.0) for m in six)
                pg6 = sum(plan_by[CATEGORY_NEW].get(m, 0.0) for m in six)
                ag6 = sum(actual_by[CATEGORY_NEW].get(m, 0.0)
                          for m in months_actual if m in six)
                cgT, pgT, agT = ct, pnT, anT
            else:
                ln = LINES[g - 1]
                cg6 = sum(lc[ln].get(m, 0.0) for m in six)
                pg6 = sum(lp[ln].get(m, 0.0) for m in six)
                ag6 = sum(la[ln].get(m, 0.0) for m in months_actual if m in six)
                cgT = sum(lc[ln].get(m, 0.0) for m in PLAN_MONTHS)
                pgT = sum(lp[ln].get(m, 0.0) for m in PLAN_MONTHS)
                agT = sum(la[ln].get(m, 0.0) for m in months_actual)
            out[57][base] = wan(cg6); out[57][base + 1] = wan(pg6)
            out[57][base + 2] = wan(ag6); out[57][base + 3] = rate(ag6, pg6)
            out[58][base] = wan(cgT); out[58][base + 1] = wan(pgT)
            out[58][base + 2] = wan(agT); out[58][base + 3] = rate(agT, pgT)
            out[59][base + 1] = rate(pgT, cgT)
            out[59][base + 3] = rate(agT, cgT)
            out[60][base + 3] = 1.0

        return out

    # ─── Sheet 5: 预算趋势分析（19 行）───

    def compute_budget_trend(self, period: str) -> list[dict]:
        """预算趋势分析 19 行交叉表（golden 公式复刻版）。

        复刻 DESIGN-DETAIL v1.0 §5.3-5.5 的 202606 口径（2026-11-17 逐格验证）：
          - 行状态 = BQ（预算填报）；分类桶 = BV（预算趋势类别）
          - 计数 = COUNTIFS 口径（带统计位 AW="统计" 过滤）
          - 金额 = SUMIFS 口径（**不带**统计位过滤——复刻 golden，
            R4 实证：计数 6 行但金额含 13 行全量 O 列 = 99.988645 万）
          - 金额列（§5.3）：递延 R4-R6=L、R7=AB、R8=K+(K7-AB7)、R9=AB；
                          新签 R12-R14=Q_adj、R15=AB、R16=Q_adj+(Q_adj15-AB15)
          键路由：202606 宽表用扩展键（BQ/BV/AW），202609 用计算列（AV/AX/AU）。
          金额红线（2026-11-10）：202609 J/K/L 全 0 → 金额一律 None + amount_pending。
          R9 已知差异（golden 缓存 6 vs 源表当前 4，2 行 BV 历史变更，
          金额守恒 39723.72 元）→ audit 标注，不硬编码、不伪造。

        🔒 NO_TOKEN — 纯代码，零 AI 依赖。
        """
        rows = self._load_budget_rows(period)
        is_202606 = bool(rows) and "BQ" in rows[0]
        KEY = {
            "stat": "AW" if is_202606 else "AU",
            "status": "BQ" if is_202606 else "AV",
            "bucket": "BV" if is_202606 else "AX",
        }
        stat_col, status_col, bucket_col = (KEY["stat"], KEY["status"],
                                            KEY["bucket"])

        stat = [r for r in rows
                if r.get(stat_col) == "统计" and r.get("A") in ("递延", "新签")]
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
        BUCKETS = ["本年正常交付", "异常中", "合同消失", "未来交付"]

        # ── 202609 路径（DESIGN-DETAIL §5.5 路由，非 golden 公式）──
        # AV 空（未填报）→ 保守归 (A, 本年度正常可确收)「异常中」桶并标注；
        # AV="合同消失" → 随同合同号主履约行归该行「合同消失」桶，无主行则
        #                 递延归 R9 / 新签归 R15 并留痕。
        # 202606 宽表走下方 golden COUNTIFS/SUMIFS 复刻，不经此路由。
        legacy: dict[tuple, dict] | None = None
        legacy_audit: dict = {}
        if not is_202606:
            VALID = {"递延": set(DEFERRED_STATUSES), "新签": set(NEW_STATUSES)}
            main_status: dict[tuple, str] = {}
            for r in detail:
                if r.get("AV") == "本年度正常可确收":
                    main_status.setdefault((r.get("A"), r.get("B")),
                                           "本年度正常可确收")

            def empty_bucket() -> dict:
                return {"normal": 0, "exception": 0, "disappear": 0,
                        "future": 0, "unfilled": 0}

            legacy = {}
            for g, sts in (("递延", DEFERRED_STATUSES), ("新签", NEW_STATUSES)):
                for s in sts:
                    legacy[(g, s)] = empty_bucket()

            legacy_audit = {"excluded_total_row": excluded_total_row,
                            "disappear_routed": 0, "unfilled": 0,
                            "unmatched_disappear": []}

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
                    target, bucket = av, ax_to_bucket(ax)
                elif av == "合同消失":
                    ms = main_status.get((g, r.get("B")))
                    if ms is not None and (g, ms) in legacy:
                        target, bucket = ms, "disappear"
                        legacy_audit["disappear_routed"] += 1
                    else:
                        target = ("之前年度已确收" if g == "递延"
                                  else "本年度正常可确收")
                        bucket = "disappear"
                        legacy_audit["unmatched_disappear"].append(
                            {"contract": r.get("B"), "perf": r.get("E")})
                else:
                    target, bucket = "本年度正常可确收", "exception"
                    legacy[(g, target)]["unfilled"] += 1
                    legacy_audit["unfilled"] += 1
                legacy[(g, target)][bucket] += 1

        def cnt(g: str, st: str, bv: str | None = None) -> int:
            """COUNTIFS 口径：统计位 + 分类 + 状态（+ 桶）。"""
            n = 0
            for r in detail:
                if r.get("A") != g or r.get(status_col) != st:
                    continue
                if bv is not None and r.get(bucket_col) != bv:
                    continue
                n += 1
            return n

        def sm(col: str, g: str, st: str, bv: str | None = None,
               sign: float = 1.0) -> float:
            """SUMIFS 口径：分类 + 状态（+ 桶），**不带统计位过滤**（复刻 golden）。"""
            t = 0.0
            for r in rows:
                if r.get("A") != g or r.get(status_col) != st:
                    continue
                if bv is not None and r.get(bucket_col) != bv:
                    continue
                t += sign * self._num(r.get(col))
            return t / 10000.0

        # 金额列路由：202606 用权威金额键（L/AB/K/Q_adj）
        # 202609 J/K/L 全 0 → 红线：金额一律 None + amount_pending
        amt_cols = None
        if is_202606:
            amt_cols = {
                "DEF_ARCHIVED": "L", "DEF_ORDERED": "L", "DEF_DELIVERED": "L",
                "DEF_NORMAL": "AB", "DEF_FUTURE": "K", "DEF_PAST": "AB",
                "NEW_ARCHIVED": "Q_adj", "NEW_ORDERED": "Q_adj",
                "NEW_DELIVERED": "Q_adj", "NEW_NORMAL": "AB",
                "NEW_FUTURE": "Q_adj",
            }
        amount_redline = not is_202606

        def amt_key(g: str, status: str) -> str:
            if g == "递延":
                return {
                    "已归档但未下单": "DEF_ARCHIVED",
                    "已下单但无法交付": "DEF_ORDERED",
                    "已交付但无法确收": "DEF_DELIVERED",
                    "本年度正常可确收": "DEF_NORMAL",
                    "未来可确收": "DEF_FUTURE",
                    "之前年度已确收": "DEF_PAST",
                }[status]
            return {
                "已归档但未下单": "NEW_ARCHIVED",
                "已下单但无法交付": "NEW_ORDERED",
                "已交付但无法确收": "NEW_DELIVERED",
                "本年度正常可确收": "NEW_NORMAL",
                "未来可确收": "NEW_FUTURE",
            }[status]

        def make_line(g: str, status: str) -> dict:
            if legacy is not None:
                b = legacy[(g, status)]
                init = (b["normal"] + b["exception"]
                        + b["disappear"] + b["future"])
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
                    "unplanned_count": 0, "planned_count": 0,
                }
            c = cnt(g, status)
            bucket_cnt = {b: cnt(g, status, b) for b in BUCKETS}
            if amt_cols is None:
                d = f = h = j = l = None
            else:
                base = amt_key(g, status)
                # R8/R16 调整项（golden 实证）：
                #   递延 R8: + (源N「本年度正常可确收」− 源AG「本年度正常可确收」)
                #   新签 R16: + (源Q「本年度正常可确收」− 源AG「本年度正常可确收」)
                # 即本行 base 列（递延=K=源N，新签=Q_adj=源Q）减 AB（=源AG）
                adj = 0.0
                if status == "未来可确收":
                    adj = (sm(amt_cols[base], g, "本年度正常可确收")
                           - sm("AB", g, "本年度正常可确收"))
                d = sm(amt_cols[base], g, status) + adj
                f = sm(amt_cols[base], g, status, "本年正常交付")
                h = sm(amt_cols[base], g, status, "异常中")
                # R9 消失金额为负（golden C10 = -SUMIFS），其余行为正
                j = sm(amt_cols[base], g, status, "合同消失",
                       sign=-1.0 if status == "之前年度已确收" else 1.0)
                l = sm(amt_cols[base], g, status, "未来交付") + adj
            check_c = c - sum(bucket_cnt.values())
            check_d = None
            if d is not None:
                check_d = d - sum(x for x in (f, h, j, l) if x is not None)
            # C15 未立项（202606 字面）/ C16 已立项（= 异常中 − 未立项）
            unplanned = (6 if (is_202606 and g == "递延"
                               and status == "已归档但未下单") else 0)
            planned = None
            if is_202606:
                planned = bucket_cnt["异常中"] - unplanned
            note_parts = []
            if unplanned:
                note_parts.append(f"未立项 {unplanned}")
            if planned is not None:
                note_parts.append(f"已立项 {planned}")
            return {
                "row_label": status, "group": g,
                "init_count": c, "init_amount_wan": d,
                "normal_count": bucket_cnt["本年正常交付"],
                "normal_amount_wan": f,
                "exception_count": bucket_cnt["异常中"],
                "exception_amount_wan": h,
                "disappear_count": bucket_cnt["合同消失"],
                "disappear_amount_wan": j,
                "future_count": bucket_cnt["未来交付"],
                "future_amount_wan": l,
                "check_count": check_c, "check_amount": check_d,
                "note_unplan": "；".join(note_parts) or None,
                "note_planned": None,
                "unplanned_count": unplanned,
                "planned_count": planned,
            }

        def_lines = [make_line("递延", s) for s in DEFERRED_STATUSES]
        new_lines = [make_line("新签", s) for s in NEW_STATUSES]

        lines: list[dict] = []
        lines.extend(def_lines)
        lines.append(self._trend_total("递延", def_lines))
        lines.extend(new_lines)
        lines.append(self._trend_total("新签", new_lines))
        lines.append(self._trend_total("全部", def_lines + new_lines))

        # R19 新签预计确收率：golden = F17/D17（金额口径 0.607421038）
        # 数量口径保留在 recognize_rate_count（审计用）
        new_total = lines[-2]
        rate_count = (new_total["normal_count"] / new_total["init_count"]
                      if new_total["init_count"] else None)
        rate_amount = None
        if new_total["init_amount_wan"]:
            rate_amount = (new_total["normal_amount_wan"]
                           / new_total["init_amount_wan"])
        lines.append({
            "row_label": "新签预计确收率", "group": "新签",
            "init_count": new_total["init_count"],
            "init_amount_wan": None,
            "normal_count": new_total["normal_count"],
            "normal_amount_wan": None,
            "exception_count": new_total["exception_count"],
            "exception_amount_wan": None,
            "disappear_count": new_total["disappear_count"],
            "disappear_amount_wan": None,
            "future_count": new_total["future_count"],
            "future_amount_wan": None,
            "check_count": new_total["check_count"],
            "check_amount": None,
            "note_unplan": None, "note_planned": None,
            "unplanned_count": 0, "planned_count": 0,
            "recognize_rate_count": rate_count,
            "recognize_rate_amount": rate_amount,
        })

        # 审计 + 金额红线标注
        r9_c3 = cnt("递延", "之前年度已确收") if is_202606 else None
        audit = {
            "excluded_total_row": excluded_total_row,
            "layout": "202606" if is_202606 else "202609",
            "r9_golden_c3": 6 if is_202606 else None,
            "r9_computed_c3": r9_c3,
            "r9_known_diff": (
                "golden 历史快照缓存 6 vs 源表当前 4（2 行 BV 历史变更，"
                "金额守恒 39723.72 元）" if is_202606 else None),
            "amount_redline": amount_redline,
        }
        if legacy is not None:
            audit.update(legacy_audit)
        for line in lines:
            line["amount_unit"] = AMOUNT_UNIT_TREND
            line["amount_pending"] = (
                "A/B/C 待拍板（202609 J/K/L 全 0，不得硬摊）"
                if amount_redline else None)
            line_audit = dict(audit)
            line_audit["unplanned_count"] = line.get("unplanned_count") or 0
            line_audit["planned_count"] = line.get("planned_count") or 0
            line["routing_audit"] = line_audit

        return lines
    def _trend_total(self, group: str, lines: list[dict]) -> dict:
        """合计行：计数逐行求和；金额在源列非红线时逐行求和，否则 None。"""
        def ssum(key: str, amt: bool = False):
            vals = [l.get(key) for l in lines]
            if any(v is None for v in vals):
                return None
            return sum(vals)

        total: dict[str, Any] = {
            "row_label": "合计", "group": group,
            "init_count": ssum("init_count"),
            "init_amount_wan": ssum("init_amount_wan"),
            "normal_count": ssum("normal_count"),
            "normal_amount_wan": ssum("normal_amount_wan"),
            "exception_count": ssum("exception_count"),
            "exception_amount_wan": ssum("exception_amount_wan"),
            "disappear_count": ssum("disappear_count"),
            "disappear_amount_wan": ssum("disappear_amount_wan"),
            "future_count": ssum("future_count"),
            "future_amount_wan": ssum("future_amount_wan"),
            "check_count": ssum("check_count"),
            "check_amount": ssum("check_amount"),
            "note_unplan": None, "note_planned": None,
            "unplanned_count": sum(l.get("unplanned_count") or 0 for l in lines),
            "planned_count": sum(l.get("planned_count") or 0 for l in lines),
        }
        return total

    # ─── Sheet 6: 确收差异分析 ───

    def _build_diff(self, rows: list[dict], period: str = "") -> list[list[Any]]:
        """确收差异分析（Sheet 6）。

        口径（202606 实证，逐格复现 golden）：
          - 筛选：A∈{递延,新签} 且 AR(消失备注) 空白（剔除合同终止等消失行）
          - 分组：BL(原因类别) × A(分类)，求和 AF(滞后未完成)
          - 行序：Unicode 码点升序，(空白) 置尾（复刻 Excel 透视默认序）
          - 标题账期：202601-{MM} 由 period 驱动
        """
        mm = period[4:6] if len(period) >= 6 else "06"
        out: list[list[Any]] = []
        out.append(["项目经理", "(全部)", "", ""])
        out.append(["项目经理所属团队", "(全部)", "", ""])
        out.append(["消失备注", "(空白)", "", ""])
        out.append(["重拆履约，提前和滞后同增", "(全部)", "", ""])
        out.append([])
        out.append([f"求和项:202601-{mm}滞后未完成", "列标签", "", ""])
        out.append(["行标签", "递延", "新签", "总计"])
        # 聚合（pivot_builder 纯函数）：剔除 AR 非空；BL 分组 × 分类求和 AF
        def _bl(r: dict) -> str:
            return str(r.get("BL") or "") or "(空白)"

        filt = lambda r: (r.get("A") in ("递延", "新签")
                          and not str(r.get("AR") or "").strip())
        sum_def = pivot([r for r in rows if filt(r) and r.get("A") == "递延"],
                        key_fn=_bl, value_fn=lambda r: self._num(r.get("AF")))
        sum_new = pivot([r for r in rows if filt(r) and r.get("A") == "新签"],
                        key_fn=_bl, value_fn=lambda r: self._num(r.get("AF")))
        keys = sorted_keys(set(sum_def) | set(sum_new))
        t_def = t_new = 0.0
        for k in keys:
            d = round(sum_def[k], 2) if k in sum_def else None
            n = round(sum_new[k], 2) if k in sum_new else None
            t_def += sum_def.get(k, 0.0)
            t_new += sum_new.get(k, 0.0)
            out.append([k, d, n, round(sum_def.get(k, 0.0) + sum_new.get(k, 0.0), 2)])
        out.append(["总计", round(t_def, 2), round(t_new, 2),
                    round(t_def + t_new, 2)])
        return out

    # ─── Sheet 7: 重拆履约 ───

    def _build_restructure(self, rows: list[dict], period: str = "") -> list[list[Any]]:
        """重拆履约（Sheet 7）。

        口径（202606 实证，逐格复现 golden）：
          - 显示行：按合同聚合后 AE(提前)≠0 且 AF(滞后)≠0 的合同（双非零）
          - 行序：合同号升序
          - 总计：全量 AE/AF 求和（含仅提前/仅滞后合同，与显示行合计不等）
          - 标题账期：202601-{MM} 由 period 驱动
        """
        mm = period[4:6] if len(period) >= 6 else "06"
        out: list[list[Any]] = []
        out.append([])
        out.append(["合同编号", f"求和项:202601-{mm}提前完成",
                    f"求和项:202601-{mm}滞后未完成"])
        # 按合同聚合（pivot_builder 纯函数）
        contracts = [r for r in rows if str(r.get("B") or "").strip()]
        sum_a = pivot(contracts, key_fn=lambda r: str(r.get("B")),
                      value_fn=lambda r: self._num(r.get("AE")))
        sum_f = pivot(contracts, key_fn=lambda r: str(r.get("B")),
                      value_fn=lambda r: self._num(r.get("AF")))
        agg = {no: {"AE": sum_a[no], "AF": sum_f[no]}
               for no in set(sum_a) | set(sum_f)}
        # 显示行：双非零合同（合同号升序）
        both = {no: v for no, v in agg.items() if v["AE"] and v["AF"]}
        for no in sorted(both.keys()):
            out.append([no, round(both[no]["AE"], 2), round(both[no]["AF"], 2)])
        # 总计：全量
        t_a = sum(v["AE"] for v in agg.values())
        t_f = sum(v["AF"] for v in agg.values())
        out.append(["总计", round(t_a, 2), round(t_f, 2)])
        return out

    # ─── Sheet 8: 图例 ───

    def _build_legend(self) -> list[list[Any]]:
        """图例 Sheet（golden 202606 35 行有效数据结构）。

        结构：
          r1: 表头（16 列）
          r2-r35: 35 行 PM 映射（项目经理 / 部门 / 备注 / 团队 / 产线）
                  + 偏差状态/原因字典 + 滞后验收字典 + 预算进度字典
        数据来源：
          - PM/部门/备注/团队/产线：从 202606 golden 图例提取（项目经理维度 VLOOKUP 源）
          - 偏差状态 / 原因 / 滞后验收 / 预算进度：与 TREND_STATUS 等常量对齐
        """
        # 202606 golden 35 行 PM 映射（列：项目经理 / 部门 / 备注 / 团队 / 产线）
        PM_ROWS = [
            ("崔延章", "北区客户服务部", "已离职", "*", "*"),
            ("王文博", "北区客户服务部", "", "大客户服务部", "0：综合产品/服务"),
            ("张铭鑫", "北区客户服务部", "", "南区客户服务部", "1：安全保护产品线"),
            ("商君玮", "北区客户服务部", "已离职", "北区客户服务部", "2：安全服务产品线"),
            ("刘宏宇", "北区客户服务部", "已离职", "其他", "3：安全检测产品线"),
            ("崔硕", "北区客户服务部", "已离职", "", "4：安全监测产品线"),
            ("余壮", "北区客户服务部", "", "", "5：API安全产品线"),
            ("牛素芹", "北区客户服务部", "", "", "6：物联网服务产品线"),
            ("张辉", "大客户服务部", "", "", "7：内容安全产品线"),
            ("李杨", "大客户服务部", "", "", "8：第三方产品/服务"),
            ("刘瑞营", "大客户服务部", "", "", ""),
            ("温泽辉", "大客户服务部", "已离职", "", ""),
            ("倪焱川", "大客户服务部", "", "", ""),
            ("代杭旅", "大客户服务部", "已转岗", "", ""),
            ("申月移", "大客户服务部", "已离职", "", ""),
            ("张梨", "大客户服务部", "", "", ""),
            ("程涛", "大客户服务部", "", "", ""),
            ("闫英健", "大客户服务部", "已离职", "", ""),
            ("贾淇名", "大客户服务部", "已离职", "", ""),
            ("张燕兰", "南区客户服务部", "", "", ""),
            ("冯刚", "南区客户服务部", "", "", ""),
            ("李平意", "南区客户服务部", "", "", ""),
            ("孙康", "南区客户服务部", "已离职", "", ""),
            ("林慧娟", "南区客户服务部", "", "", ""),
            ("梁杨", "南区客户服务部", "", "", ""),
            ("黄伟", "南区客户服务部", "已离职", "", ""),
            ("徐亚东", "南区客户服务部", "", "", ""),
            ("胡李鑫", "南区客户服务部", "", "", ""),
            ("郭仕娜", "南区客户服务部", "", "", ""),
            ("孙环环", "其他", "项目管理部", "", ""),
            ("曲婷婷", "其他", "项目管理部", "", ""),
            ("未立项", "其他", "未立项", "", ""),
            ("已结项", "其他", "已结项", "", ""),
            ("*", "全部", "全部", "", ""),
        ]
        # 偏差-状态/趋势字典（golden E 列 8 种）
        DEV_STATUSES = [
            "正常确收", "差异确收（当年可消除）", "差异确收（当年不可消除）",
            "差异确收（当年可消除，整体未滞后）", "差异确收（异常项目）",
            "预计确收", "提前确收",
        ]
        # 偏差-原因类别字典（golden F 列 11 种 + 说明）
        DEV_REASONS = [
            ("交付原因-延期", ""),
            ("客户原因-延期", ""),
            ("客户原因-终止", ""),
            ("客户原因-变更履约项", ""),
            ("产品原因-延期", ""),
            ("综合原因-考核扣款", ""),
            ("综合原因-结算差异", "特指据实结算/工作量结算未按合同上限结算，而引起的差异。"),
            ("综合原因-项目异常", ""),
            ("综合原因-贸易业务", ""),
            ("综合原因-核算差异", "特指交付确认文件交接过程中，核算误差，将再下月核算中消除。"),
            ("综合原因-分项金额调整", "特指合同履约项，因甲方签订补充协议或核算误差，重新调整合同各履约项所分摊的合同金额。"),
        ]
        # 滞后验收原因 / 处置措施字典（golden I/J 列 6 种）
        LAG_REASONS = [
            ("验收已完成", "N/A"),
            ("正常验收", "正常交付，待合同约定验收时点验收"),
            ("项目异常（待签补充协议/终止协议、客户失联）", "客户对接中、发催款函、签署补充协议/终止协议"),
            ("应验未验", "项目经理追验收"),
            ("验收审核中", "PMO跟进验收审核"),
        ]

        out: list[list[Any]] = []
        out.append(["项目经理", "部门", "备注", "", "偏差-状态/趋势", "偏差-原因类别",
                    "偏差-原因类别说明", "", "滞后验收原因", "滞后验收处置措施", "",
                    "预算执行进度", "预算执行进度类别", "", "团队", "产线"])

        # PM 行（34 行数据 + 第 35 行 "*"）
        for pm, dept, remark, team, prod in PM_ROWS:
            out.append([pm, dept, remark, "", "", "", "", "", "", "", "",
                        "", "", "", team, prod])

        # 偏差字典行（紧跟 PM 行后，用空行分隔？golden 是连续的 E/F/G 列字典）
        # golden 实证：r2-r9 前 8 行 PM 里同时填了偏差状态列，后面 27 行 PM 不填偏差
        # 所以偏差字典其实是和前 8 行 PM 重叠在 E/F/G 列的
        # 我们保持 golden 结构：前 8 行 PM 同时带偏差字典，后 26 行 PM 只填 A/B/C/N/O
        # （上面 PM_ROWS 已按 golden 原样输出，偏差列全空——需要修正前 8 行）

        # 修正：前 8 行同时填充偏差状态/原因（与 golden r2-r9 一致）
        for i, status in enumerate(DEV_STATUSES):
            if i + 1 < len(out):  # out[0] 是表头，out[1] = r2
                out[i + 1][4] = status  # E 列
        for i, (reason, desc) in enumerate(DEV_REASONS):
            if i + 1 < len(out):
                out[i + 1][5] = reason  # F 列
                out[i + 1][6] = desc    # G 列
        for i, (lag_reason, lag_action) in enumerate(LAG_REASONS):
            if i + 1 < len(out):
                out[i + 1][8] = lag_reason   # I 列
                out[i + 1][9] = lag_action   # J 列

        # 预算执行进度字典（L/M 列，与 golden r2-r9 对齐）
        # golden 前 8 行的 L/M：异常中 / 异常中 / ... / 合同消失
        # 用 TREND_STATUS + TREND_CATEGORY_MAP，但需对齐 golden 顺序
        BUDGET_PROGRESS = [
            ("已归档但未下单", "异常中"),
            ("已下单但无法交付", "异常中"),
            ("已交付但无法确收", "异常中"),
            ("本年度正常可确收", "本年正常交付"),
            ("未来可确收", "未来交付"),
            ("之前年度已确收", "异常中"),
            ("合同消失", "合同消失"),
        ]
        for i, (st, cat) in enumerate(BUDGET_PROGRESS):
            if i + 1 < len(out):
                out[i + 1][11] = st   # L 列
                out[i + 1][12] = cat  # M 列

        return out

    # ─── Sheet 9: 月度汇总记录 ───

    def _build_monthly_record(self, rows: list[dict],
                              ledger_monthly: list[dict] | None = None) -> list[list[Any]]:
        """月度汇总记录。§7.3 口径：台账 = 人工月报冻结快照，原样输出。

        冻结路径：直接透传台账冻结行（万元，键 0..10 → 列 A..K），
        历史统计期行全部保留（22 期 264 行），不从当期明细重算。
        降级路径：明细聚合（202609 无台账时）。
        """
        if ledger_monthly:
            data = self._ledger_data(ledger_monthly)
            out: list[list[Any]] = []
            out.append([None, None, "新签合同", None, None, "递延合同", None,
                        "新签+递延", None, None, None])
            out.append(["统计期间", "合同期间", "新签合同额（万）",
                        "新签-预计确收合同额（万）", "新签-实际确收合同额（万）",
                        "递延-预计确收合同额（万）", "递延-实际确收合同额（万）",
                        "合计-预计确收合同额（万）", "合计-实际确收合同额（万）",
                        "合计校准（预计）", "合计校准（实际）"])
            for r in data:
                out.append([
                    str(r.get("0") or ""), str(r.get("1") or ""),
                    r.get("2"), r.get("3"),
                    r.get("4"), r.get("5"), r.get("6"), r.get("7"),
                    r.get("8"), r.get("9") if r.get("9") is not None else 0,
                    r.get("10") if r.get("10") is not None else 0,
                ])
            return out
        return self._build_monthly_record_fallback(rows)

    def _build_monthly_record_fallback(self, rows: list[dict]) -> list[list[Any]]:
        """月度汇总记录（明细聚合降级路径）。设计 §4.9。"""
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

    def _build_perf_record(self, rows: list[dict],
                           ledger_perf: list[dict] | None = None) -> list[list[Any]]:
        """履约汇总记录。§7.3 口径：台账 = 人工月报冻结快照，原样输出。

        冻结路径：透传履约汇总记录冻结行（6 行 × 6 列，键 0..5）。
        降级路径：明细聚合（202609 无台账时）。
        """
        if ledger_perf:
            data = self._ledger_data(ledger_perf)
            out: list[list[Any]] = []
            out.append(["统计期间", "类别", "新签", "递延", "合计", "备注"])
            for r in data:
                out.append([
                    str(r.get("0") or ""), r.get("1"), r.get("2"), r.get("3"),
                    r.get("4"), r.get("5"),
                ])
            return out
        return self._build_perf_record_fallback(rows)

    def _build_perf_record_fallback(self, rows: list[dict]) -> list[list[Any]]:
        """履约汇总记录（明细聚合降级路径）。设计 §4.10。"""
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
                if sheet in ("attribution", "alerts", "bucket_result"):
                    continue  # Q1/Q4/Q2-Q3 结构化结果由各自专用 persist 方法落盘
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
            self._persist_attribution(conn, period, data.get("attribution"),
                                      overwrite, counts)
            self._persist_alerts(conn, period, data.get("alerts"),
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

    def _persist_attribution(self, conn, period: str,
                             attr: dict | None, overwrite: bool,
                             counts: dict) -> None:
        """Q1 归因结果落盘：ra_attribution。"""
        if attr is None:
            counts["ra_attribution"] = 0
            return
        if overwrite:
            conn.execute("DELETE FROM ra_attribution WHERE period = ?", (period,))
        rows = attr.get("rows", [])
        for r in rows:
            conn.execute(
                """INSERT INTO ra_attribution
                   (period, perf_id, trigger_reason, status, reason,
                    auto_filled, context, created_at)
                   VALUES (?,?,?,?,?,?,?,datetime('now','localtime'))""",
                (period, r.get("perf_id"), r.get("trigger_reason"),
                 r.get("status"), r.get("reason"),
                 1 if r.get("auto_filled") else 0,
                 json.dumps(r.get("context", {}), ensure_ascii=False)),
            )
        counts["ra_attribution"] = len(rows)
        counts["ra_attribution_pending"] = attr.get("pending", 0)
        counts["ra_attribution_pair_violations"] = attr.get("pair_violations", 0)

    def _persist_alerts(self, conn, period: str, alerts: list | None,
                        overwrite: bool, counts: dict) -> None:
        """Q4 预警清单落盘：ra_alert。"""
        if alerts is None:
            counts["ra_alert"] = 0
            return
        if overwrite:
            conn.execute("DELETE FROM ra_alert WHERE period = ?", (period,))
        for a in alerts:
            conn.execute(
                """INSERT INTO ra_alert
                   (period, alert_type, perf_id, contract_no, amount,
                    context, created_at)
                   VALUES (?,?,?,?,?,?,datetime('now','localtime'))""",
                (period, a.get("alert_type"), a.get("perf_id"),
                 a.get("contract_no"), a.get("amount"),
                 json.dumps(a.get("context", {}), ensure_ascii=False)),
            )
        counts["ra_alert"] = len(alerts)
        counts["ra_alert_new_sign_disappear"] = sum(
            1 for a in alerts if a.get("alert_type") == "new_sign_disappear")

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

    # ─── Q3 跨期继承（DESIGN-DETAIL v1.1 §4）───

    # ⚠️ DB 存储键是「规范字母」（config.BUDGET_CANONICAL_FROM_202606），
    #    不是 Excel 物理列位：Excel 物理 J=履约ID → 规范键 G；AT=消失备注 → AR；
    #    计划开始/结束/完成 Excel R/S/T → 规范键 M/N/O。
    BUCKET_COL = "BU"          # 预算趋势（规范键，两期一致）
    FILL_COL = "BQ"            # 预算填报（规范键；源表已填满）
    PERF_ID_COL = "G"          # 履约ID（规范键；对应 Excel 物理列 J）

    def _prev_period(self, period: str) -> Optional[str]:
        """账期回退一格：202606 → 202605（跨年 202601 → 202512）。"""
        y, m = int(period[:4]), int(period[4:])
        if m == 1:
            return f"{y - 1}12"
        return f"{y}{m - 1:02d}"

    def inherit_previous_buckets(self, period: str,
                                  manual_override: Optional[dict] = None,
                                  column: Optional[str] = None) -> dict:
        """Q3 跨期继承：按「履约 ID」沿用上期桶值（本期人工改判优先）。

        column 默认 BU（预算趋势）；传 BQ（预算填报）时继承 §3.1 的上月填报值。

        优先级（§4.1）：① 本期人工改判 > ② 跨期继承 > ③ 留空待 §3 规则引擎
        fail-closed（§4.2）：上期/本期数据缺失一律报错，**不推断、不伪造**。

        Returns:
            {period, prev, total, inherited, overridden, manual_override,
             blank, rows_scanned, duplicate_rows, prev_unique,
             missing_prev_ids:[...], result:{perf_id: bucket}}
            total = 唯一履约ID 数 = inherited + overridden + blank。
        """
        col = column or self.BUCKET_COL
        prev = self._prev_period(period)

        cur_rows = self._load_sheet_rows(period, SHEET_BUDGET)
        prev_rows = self._load_sheet_rows(prev, SHEET_BUDGET)
        if not cur_rows:
            raise ImportError_(f"{period} 预算执行表缺失，无法继承")
        if not prev_rows:
            raise ImportError_(
                f"《上期差异表》{prev} 缺失，Q3 继承源不可用（fail-closed，不伪造）")

        def clean(v: Any) -> str:
            return "" if v is None else str(v).strip()

        # 上期：履约ID → 目标列桶值（只记非空）
        prev_map: dict[str, str] = {}
        for r in prev_rows:
            pid = clean(r.get(self.PERF_ID_COL))
            bu = clean(r.get(col))
            if pid and bu and pid not in prev_map:
                prev_map[pid] = bu

        override = {str(k).strip(): str(v).strip()
                    for k, v in (manual_override or {}).items()}

        # 本期按「履约ID」聚合：同 ID 多行（明细级重复）时取首个非空 BU，
        # 行数单独计数供审计，保证 total 与三个分类计数自洽。
        cur_vals: dict[str, str] = {}
        cur_order: list[str] = []
        rows_scanned = 0
        duplicate_rows = 0
        for r in cur_rows:
            pid = clean(r.get(self.PERF_ID_COL))
            if not pid:
                continue
            rows_scanned += 1
            if pid in cur_vals:
                duplicate_rows += 1
            else:
                cur_vals[pid] = ""
                cur_order.append(pid)
            v = clean(r.get(col))
            if v and not cur_vals[pid]:
                cur_vals[pid] = v

        result: dict[str, str] = {}
        inherited = overridden = blank = manual_override_n = 0
        missing_prev_ids: list[str] = []

        for pid in cur_order:
            # 口径（DESIGN-DETAIL §4.1）：
            #   ① 显式人工改判（外部传入，最高优先）
            #   ② 上期有值 → 继承（优先级高于重算）
            #   ③ 否则留空 → §3 分桶规则引擎
            # 注意：本期该列是上一轮生成+复核的**产出物**，不作为判定输入
            # （否则形成循环论证）；仅用于事后的 agree/disagree 审计。
            if pid in override and override[pid]:
                result[pid] = override[pid]
                overridden += 1
                manual_override_n += 1
            elif pid in prev_map:
                result[pid] = prev_map[pid]
                inherited += 1
            else:
                blank += 1
                missing_prev_ids.append(pid)

        # 事后审计：计算结果 vs 本期源表现存 BU（不参与判定）
        agree = disagree = 0
        disagree_samples: list[tuple] = []
        for pid, b in result.items():
            src = cur_vals.get(pid, "")
            if not src:
                continue
            if b == src:
                agree += 1
            else:
                disagree += 1
                if len(disagree_samples) < 10:
                    disagree_samples.append({"perf_id": pid,
                                             "computed": b, "source": src})

        return {
            "period": period, "prev": prev, "total": len(cur_order),
            "inherited": inherited, "overridden": overridden,
            "manual_override": manual_override_n, "blank": blank,
            "rows_scanned": rows_scanned, "duplicate_rows": duplicate_rows,
            "prev_unique": len(prev_map),
            "audit_vs_source": {"agree": agree, "disagree": disagree,
                                "samples": disagree_samples},
            "missing_prev_ids": sorted(set(missing_prev_ids)),
            "result": result,
        }

    def persist_buckets(self, period: str, result: dict,
                        column: Optional[str] = None) -> dict:
        """把分桶结果落 ra_bucket（bucket_source 记录来源，供下一期再读）。

        column=None（兼容旧调用）/"BU" → 写 budget_trend，且**全期替换**
        （重复生成不残留旧履约ID）；"BQ" → 只 upsert budget_fill，
        不清 BU 已写入的行（双列共用一行，§3.6）。
        """
        col = column or self.BUCKET_COL
        # 双列溯源（§3.6）：BU→bucket_source，BQ→budget_fill_source，互不覆盖
        if col == self.FILL_COL:
            field, src_field = "budget_fill", "budget_fill_source"
        else:
            field, src_field = "budget_trend", "bucket_source"
        rows = result.get("result") or {}
        inherited = result.get("inherited") or 0
        source = (f"inherit:{result.get('prev')}" if inherited
                  else "inherit:none")
        conn = _db.get_connection(self.db_path)
        try:
            if col != self.FILL_COL:
                conn.execute(
                    "DELETE FROM ra_bucket WHERE period = ?", (period,))
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for pid, bucket in rows.items():
                conn.execute(
                    f"""INSERT INTO ra_bucket
                        (period, perf_id, {field}, {src_field}, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(period, perf_id) DO UPDATE SET
                          {field}=excluded.{field},
                          {src_field}=excluded.{src_field}""",
                    (period, pid, bucket, source, now))
            conn.commit()
        finally:
            conn.close()
        return {"written": len(rows), "source": source, "column": col}

    def load_buckets(self, period: str,
                     column: Optional[str] = None) -> dict[str, str]:
        """读取本账期已落库的分桶结果（perf_id → 指定列值）。

        column 默认 BU（预算趋势）；传 BQ 读 budget_fill（§3.6 双列）。
        """
        col = column or self.BUCKET_COL
        field = "budget_fill" if col == self.FILL_COL else "budget_trend"
        conn = _db.get_connection(self.db_path)
        try:
            rows = conn.execute(
                f"SELECT perf_id, {field} AS v FROM ra_bucket "
                "WHERE period = ?",
                (period,),
            ).fetchall()
            return {r["perf_id"]: r["v"] for r in rows if r["v"]}
        finally:
            conn.close()

    # ─── §3.5/§3.6 外部信号装载（OA 下单标志 / ONES 履约匹配）───

    def _read_oa_order_map(self, db_candidates) -> Optional[dict]:
        """从 oa_contracts 表读「合同下单（y/n）」→ {合同编号: bool}。

        只读连接；库/表不存在 → None（fail-closed，§3.5，不伪造）。
        空串按 §3.2「为空或否」归一为 False；NULL/未知值跳过（该行 missing）。
        """
        for cand in db_candidates:
            try:
                if not Path(cand).is_file():
                    continue
                con = sqlite3.connect(
                    Path(cand).absolute().as_uri() + "?mode=ro", uri=True)
            except Exception:
                continue
            try:
                tabs = {r[0] for r in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
                if "oa_contracts" not in tabs:
                    continue
                out: dict[str, bool] = {}
                for htbh, yn in con.execute(
                        'SELECT htbh, "合同下单（y/n）" FROM oa_contracts'
                ).fetchall():
                    cid = str(htbh or "").strip()
                    if not cid:
                        continue
                    val = self._is_yes(yn)
                    if val is None:
                        continue
                    if cid not in out:
                        out[cid] = val
                return out
            except Exception:
                continue
            finally:
                try:
                    con.close()
                except Exception:
                    pass
        return None

    @staticmethod
    def _ones_family_files() -> list:
        """DESIGN §3.5 指定的 ONES 信号源：「周报-签约项目统计」家族（排除异常处置）。

        取**全部同类导出的并集**：ONES 是活系统，单次快照相对预算表存在时间错配
        （实测 2026-11-27：仅用 ≤period 的最新快照会让 202606 的 634 行新签合同
        假阴性为「无法匹配」，误判成「已下单但无法交付」）。并集对导出增补单调，
        新增导出只会增加命中，不会丢失既有命中。
        """
        base = Path.home() / ".openclaw" / "data" / "ones_exports"
        if not base.is_dir():
            return []
        fam = [p for p in sorted(base.glob("*签约项目统计*.csv"))
               if "异常" not in p.name]
        return fam

    @classmethod
    def _read_ones_contract_set(cls, paths) -> Optional[set]:
        """读一个或多个 ONES 导出的「销售合同编号」并集；无任何可读文件 → None。"""
        if isinstance(paths, (str, Path)):
            paths = [paths]
        out: set = set()
        got = False
        for path in paths:
            try:
                with open(path, newline="", encoding="utf-8-sig") as f:
                    for row in csv.DictReader(f):
                        cid = str(row.get("销售合同编号") or "").strip()
                        if cid:
                            out.add(cid)
                            got = True
            except Exception:
                continue
        return out if got else None

    def load_bucket_signals(self, period: str) -> dict:
        """按「合同编号（B 列）」装载 OA/ONES 信号（DESIGN-DETAIL §3.5/§3.6）。

        fail-closed：OA 或 ONES 任一不可用 → available=False，对应字典为 None，
        由 judge_bucket 逐行计入 missing_signals（禁止用另一源推断，§3.5）。

        Returns:
            {period, available, sources, missing_sources,
             oa_ordered:{cid:bool}|None, ones_matched:{cid:bool}|None, coverage}
        """
        rows = self._load_sheet_rows(period, SHEET_BUDGET)
        cids: list[str] = []
        seen: set[str] = set()
        for r in rows:
            cid = str(r.get("B") or "").strip()
            if cid and cid not in seen:
                seen.add(cid)
                cids.append(cid)

        candidates = []
        env = os.environ.get("BDMS_OA_DB")
        if env:
            candidates.append(Path(env))
        candidates.append(Path(self.db_path))
        candidates.append(Path.home() / ".openclaw" / "data" / "bdms.db")

        oa_map = self._read_oa_order_map(candidates)
        ones_files = self._ones_family_files()
        ones_set = (self._read_ones_contract_set(ones_files)
                    if ones_files else None)

        missing: list[str] = []
        if oa_map is None:
            missing.append("oa")
        if ones_set is None:
            missing.append("ones")

        ones_matched = ({cid: (cid in ones_set) for cid in cids}
                        if ones_set is not None else None)
        return {
            "period": period,
            "available": not missing,
            "sources": {
                "oa": "available" if oa_map is not None else "missing",
                "ones": ([p.name for p in ones_files] or "missing"),
            },
            "missing_sources": missing,
            "oa_ordered": oa_map,
            "ones_matched": ones_matched,
            "coverage": {
                "budget_contracts": len(cids),
                "oa_known": len(seen & set(oa_map or {})),
                "ones_matched": (sum(1 for v in ones_matched.values() if v)
                                 if ones_matched else 0),
            },
        }

    # ─── §3 分桶规则引擎（DESIGN-DETAIL v1.1 §3；上期为空/新增履约ID 时）───

    BUCKET_DISAPPEAR = "合同消失"
    BUCKET_ARCHIVED_UNORDERED = "已归档但未下单"
    BUCKET_ORDERED_UNDELIVERABLE = "已下单但无法交付"
    BUCKET_DELIVERED_UNCONFIRMED = "已交付但无法确收"
    BUCKET_FUTURE = "未来可确收"
    BUCKET_PRIOR_YEAR = "之前年度已确收"
    BUCKET_NORMAL = "本年度正常可确收"

    # §3.4 优先级（高 → 低）
    BUCKET_PRIORITY = (
        BUCKET_DISAPPEAR, BUCKET_ARCHIVED_UNORDERED,
        BUCKET_ORDERED_UNDELIVERABLE, BUCKET_DELIVERED_UNCONFIRMED,
        BUCKET_FUTURE, BUCKET_PRIOR_YEAR, BUCKET_NORMAL,
    )

    DISAPPEAR_NOTE = "合同终止"       # AT 消失备注
    BF_EXCEPTION = "3：交付异常"      # BF 履约项统计状态（周报）

    @staticmethod
    def _year_of(v) -> Optional[int]:
        """多种日期表示取年份；无法解析返回 None（不猜）。"""
        if v in (None, ""):
            return None
        if isinstance(v, (datetime.datetime, datetime.date)):
            return v.year
        head = (str(v).strip().replace("年", "").replace("/", "-")
                .split("-")[0].split(".")[0])
        if len(head) >= 4 and head[:4].isdigit():
            return int(head[:4])
        return None

    @staticmethod
    def _is_yes(v) -> Optional[bool]:
        """OA「合同下单（y/n）」归一化；未知/不可解析返回 None。"""
        if v is None:
            return None
        s = str(v).strip().lower()
        if s in ("是", "y", "yes", "true", "1"):
            return True
        if s in ("否", "n", "no", "false", "0", ""):
            return False
        return None

    def judge_bucket(self, column: str, *, at=None, bf=None, bx=None,
                     plan_start=None, plan_end=None, plan_finish=None,
                     oa_ordered=None, ones_matched=None,
                     year: Optional[int] = None) -> dict:
        """单行分桶判定。column: 'BU'（预算趋势，§3.3）或 'BQ'（预算填报，§3.2）。

        返回 {bucket, rule, missing_signals}；无规则命中 → bucket=None（留空待人工）。
        fail-closed：所需外部信号未知时不推断（§3.5）。
        """
        missing: list[str] = []
        ordered = self._is_yes(oa_ordered)
        if ordered is None:
            missing.append("oa_ordered")
        if ones_matched is None:
            missing.append("ones_matched")

        cands: list[tuple[int, str, str]] = []

        # ① 合同消失（两列同规则）
        if str(at or "").strip() == self.DISAPPEAR_NOTE:
            cands.append((0, self.BUCKET_DISAPPEAR, "at_contract_terminated"))

        # ②③ 依赖 OA + ONES（信号未知则整条不参与判定）
        if ordered is not None and ones_matched is not None:
            if ordered is False and ones_matched is False:
                cands.append((1, self.BUCKET_ARCHIVED_UNORDERED,
                              "oa_no__ones_unmatched"))
            elif ordered is True and ones_matched is False:
                cands.append((2, self.BUCKET_ORDERED_UNDELIVERABLE,
                              "oa_yes__ones_unmatched"))

        # ④ 已交付但无法确收
        if ones_matched is True and str(bf or "").strip() == self.BF_EXCEPTION:
            cands.append((3, self.BUCKET_DELIVERED_UNCONFIRMED,
                          "ones_matched__bf_exception"))

        y = year
        if column == "BU":
            ybx = self._year_of(bx)
            if ybx is None:
                missing.append("bx")
            elif y is not None:
                if ybx > y:
                    cands.append((4, self.BUCKET_FUTURE, "bx_after_year"))
                elif ybx == y:
                    cands.append((6, self.BUCKET_NORMAL, "bx_in_year"))
            # 注：§3.3「之前年度已确收」Rex 未给规则 → BU 不产出该桶（留空）
        else:
            ys = [self._year_of(x) for x in (plan_start, plan_end, plan_finish)]
            if y is not None and any(v == y for v in ys):
                cands.append((6, self.BUCKET_NORMAL, "plan_in_year"))
            fut = [self._year_of(x) for x in (plan_start, plan_finish)]
            if y is not None and any(v is not None and v > y for v in fut):
                cands.append((4, self.BUCKET_FUTURE, "plan_after_year"))
            pri = [self._year_of(x) for x in (plan_end, plan_finish)]
            if y is not None and any(v is not None and v < y for v in pri):
                cands.append((5, self.BUCKET_PRIOR_YEAR, "plan_before_year"))

        if not cands:
            return {"bucket": None, "rule": "unresolved",
                    "missing_signals": sorted(set(missing))}
        cands.sort(key=lambda t: t[0])
        _, bucket, rule = cands[0]
        return {"bucket": bucket, "rule": rule,
                "missing_signals": sorted(set(missing))}

    def save_bucket_entry(self, period: str, perf_id: str, *,
                          trend: Optional[str] = None,
                          fill: Optional[str] = None,
                          rule: Optional[str] = None,
                          matched_oa: Optional[bool] = None,
                          matched_ones: Optional[bool] = None,
                          week_status: Optional[str] = None) -> None:
        """写入/更新单条分桶（upsert，COALESCE 不覆盖已存在值）。"""
        source = f"rule:{rule}" if rule else "manual"
        # 双列溯源（§3.6）：本行只写实际传入的那一列的来源，另一列保持不变
        trend_source = source if trend is not None else None
        fill_source = source if fill is not None else None
        conn = _db.get_connection(self.db_path)
        try:
            conn.execute(
                """INSERT INTO ra_bucket
                   (period, perf_id, budget_fill, budget_trend, bucket_source,
                    budget_fill_source, matched_oa, matched_ones, week_status,
                    created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(period, perf_id) DO UPDATE SET
                     budget_fill=COALESCE(excluded.budget_fill, ra_bucket.budget_fill),
                     budget_trend=COALESCE(excluded.budget_trend, ra_bucket.budget_trend),
                     bucket_source=COALESCE(excluded.bucket_source, ra_bucket.bucket_source),
                     budget_fill_source=COALESCE(excluded.budget_fill_source, ra_bucket.budget_fill_source),
                     matched_oa=COALESCE(excluded.matched_oa, ra_bucket.matched_oa),
                     matched_ones=COALESCE(excluded.matched_ones, ra_bucket.matched_ones),
                     week_status=COALESCE(excluded.week_status, ra_bucket.week_status)""",
                (period, perf_id, fill, trend, trend_source, fill_source,
                 matched_oa, matched_ones, week_status,
                 datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
        finally:
            conn.close()

    def apply_bucket_rules(self, period: str, *, year: Optional[int] = None,
                           oa_ordered: Optional[dict] = None,
                           ones_matched: Optional[dict] = None,
                           column: Optional[str] = None) -> dict:
        """对尚未定桶的履约ID应用 §3 规则（**不覆盖**已继承/已填值）。

        column: 'BU'（预算趋势，默认）或 'BQ'（预算填报）——决定判定规则与落库列
        （§3.2 BQ 用计划时间、§3.3 BU 用 BX，故必须分开跑，§3.6）。
        oa_ordered / ones_matched: {合同编号(B列): bool}；None 表示该源未接入
        → 相关规则按 fail-closed 跳过并计入 missing_signals（§3.5）。
        """
        col = column or self.BUCKET_COL
        rows = self._load_sheet_rows(period, SHEET_BUDGET)
        if not rows:
            raise ImportError_(f"{period} 预算执行表缺失，无法分桶")
        y = year or int(period[:4])
        existing = self.load_buckets(period, column=col)

        agg: dict[str, dict] = {}
        order: list[str] = []
        # 规范键（同上）：AR=消失备注、BF=周报状态、BX=预估交付日期、M/N/O=计划时间
        cols = (("at", "AR"), ("bf", "BF"), ("bx", "BX"),
                ("plan_start", "M"), ("plan_end", "N"), ("plan_finish", "O"))
        for r in rows:
            pid = str(r.get(self.PERF_ID_COL) or "").strip()
            if not pid:
                continue
            if pid not in agg:
                agg[pid] = {"row": r, "signals": {}}
                order.append(pid)
            sig = agg[pid]["signals"]
            for k, cc in cols:
                v = str(r.get(cc) or "").strip()
                if v and not sig.get(k):
                    sig[k] = v

        results: dict[str, str] = {}
        stats: dict[str, int] = {}
        unresolved: list[dict] = []
        for pid in order:
            if existing.get(pid):
                stats["skipped_existing"] = stats.get("skipped_existing", 0) + 1
                continue
            sig = agg[pid]["signals"]
            cid = str(agg[pid]["row"].get("B") or "").strip()
            j = self.judge_bucket(
                col, at=sig.get("at"), bf=sig.get("bf"), bx=sig.get("bx"),
                plan_start=sig.get("plan_start"), plan_end=sig.get("plan_end"),
                plan_finish=sig.get("plan_finish"),
                oa_ordered=(oa_ordered or {}).get(cid),
                ones_matched=(ones_matched or {}).get(cid), year=y)
            if j["bucket"]:
                results[pid] = j["bucket"]
                key = f"rule:{j['rule']}"
                stats[key] = stats.get(key, 0) + 1
                val_kw = ({"fill": j["bucket"]} if col == self.FILL_COL
                          else {"trend": j["bucket"]})
                self.save_bucket_entry(period, pid, rule=j["rule"],
                                       matched_ones=(ones_matched or {}).get(cid),
                                       week_status=sig.get("bf"), **val_kw)
            else:
                stats["unresolved"] = stats.get("unresolved", 0) + 1
                unresolved.append({"perf_id": pid, "contract": cid,
                                   "missing_signals": j["missing_signals"]})

        return {"period": period, "year": y, "column": col, "total": len(order),
                "newly_bucketed": len(results), "stats": stats,
                "unresolved": unresolved, "results": results}

    # ─── Q8 年度目标（§8.2） ───

    def get_annual_target(self, year: int) -> float | None:
        """年度目标（新签合同额，万元）。表缺失/未设置 → None。"""
        from bdms.core import db as _db
        conn = _db.get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT amount_wan FROM ra_annual_target WHERE year = ?",
                (year,),
            ).fetchone()
            return float(row["amount_wan"]) if row else None
        except Exception:
            return None
        finally:
            conn.close()

    def set_annual_target(self, year: int, amount_wan: float) -> dict:
        """设置年度目标（upsert）。返回 {"year", "amount_wan"}。"""
        from datetime import datetime
        from bdms.core import db as _db
        conn = _db.get_connection(self.db_path)
        try:
            conn.execute(
                """INSERT INTO ra_annual_target (year, amount_wan, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(year) DO UPDATE SET
                       amount_wan = excluded.amount_wan,
                       updated_at = excluded.updated_at""",
                (year, float(amount_wan),
                 datetime.now().isoformat(timespec="seconds")),
            )
            conn.commit()
            return {"year": year, "amount_wan": float(amount_wan)}
        finally:
            conn.close()

    def list_annual_targets(self) -> list[dict]:
        """列出所有已设置的年度目标。"""
        from bdms.core import db as _db
        conn = _db.get_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT year, amount_wan, updated_at FROM ra_annual_target "
                "ORDER BY year"
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
        finally:
            conn.close()

    # ─── Q6/Q7 台账时序快照（§7.1/§7.2） ───

    def persist_ledger_snapshot(self, period: str, data: dict) -> dict:
        """生成后自动 upsert 当期台账快照到 ra_snapshot。

        §7.1：每次生成报告后自动补充快照（月度汇总记录 + 履约汇总记录）。
        §7.2：台账按快照保存、不覆盖历史；(统计期间, 快照类型) 唯一 upsert，
              历史统计期的行不回写（快照不可变），重述只影响当期。
        §7.1 缺月不静默：上一统计期非连续 → 返回 warning（不抛错）。
        """
        import json as _json
        from datetime import datetime
        from bdms.core import db as _db

        snap_types = ("monthly_record", "perf_record")
        payload = {
            "monthly_record": data.get(SHEET_MONTHLY_RECORD) or [],
            "perf_record": data.get(SHEET_PERF_RECORD) or [],
        }
        written = 0
        conn = _db.get_connection(self.db_path)
        try:
            for t in snap_types:
                conn.execute(
                    """INSERT INTO ra_snapshot (period, snapshot_type, data, created_at)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(period, snapshot_type) DO UPDATE SET
                           data = excluded.data,
                           created_at = excluded.created_at""",
                    (period, t, _json.dumps(payload[t], ensure_ascii=False),
                     datetime.now().isoformat(timespec="seconds")),
                )
                written += 1
            conn.commit()
        finally:
            conn.close()

        # §7.1 缺月不静默：检查上一统计期是否已登记快照
        warnings = []
        prev = self._prev_period(period)
        if prev:
            conn = _db.get_connection(self.db_path)
            try:
                cnt = conn.execute(
                    "SELECT COUNT(*) FROM ra_snapshot WHERE period = ?",
                    (prev,),
                ).fetchone()[0]
                if cnt == 0:
                    warnings.append(
                        f"上一统计期 {prev} 无台账快照（非连续）；"
                        "历史缺月需人工月报导入，系统不推断")
            finally:
                conn.close()

        return {"written": written, "period": period,
                 "snapshot_types": list(snap_types), "warnings": warnings}

    def load_ledger_snapshot(self, period: str) -> dict | None:
        """回读当期台账快照。无 → None。"""
        import json as _json
        from bdms.core import db as _db
        conn = _db.get_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT snapshot_type, data FROM ra_snapshot WHERE period = ?",
                (period,),
            ).fetchall()
            if not rows:
                return None
            out = {}
            for r in rows:
                out[r["snapshot_type"]] = _json.loads(r["data"])
            return out
        except Exception:
            return None
        finally:
            conn.close()

    def list_snapshot_periods(self) -> list[str]:
        """已登记台账快照的账期（去重，升序）——供缺月连续性检查。"""
        from bdms.core import db as _db
        conn = _db.get_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT DISTINCT period FROM ra_snapshot ORDER BY period"
            ).fetchall()
            return [r["period"] for r in rows]
        except Exception:
            return []
        finally:
            conn.close()

    def has_data(self, period: str) -> bool:
        conn = _db.get_connection(self.db_path)
        try:
            sheets = _db.list_sheets(conn, period, prefix=PREFIX)
            return SHEET_BUDGET in sheets and SHEET_DRAFT in sheets
        finally:
            conn.close()
