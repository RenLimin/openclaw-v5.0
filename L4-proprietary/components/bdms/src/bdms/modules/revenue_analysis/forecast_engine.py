"""forecast_engine — 预测模型（DESIGN-DETAIL v1.1 §8.3 / IMPLEMENTATION-PLAN §10 P7）。

输入（全部为既有单一事实源，不自造聚合）：
  - 双口径：`CaliberBuilder.build`（与 ra_caliber 快照同源）；
  - future 桶：`ra_bucket.budget_fill='未来可确收'`（仅已落库行）；
  - 实际达成：`_build_summary_analysis` A 块 r19「合计」实际列；
  - 年度目标：`ra_annual_target`（DB 优先）→ `SUMMARY_TARGET_CONTRACT` 回退；
  - 信号/消失证据：`load_bucket_signals`、`AR='合同终止'`。

单位红线：CaliberBuilder 与 ra_caliber 为**元**；本模块对外统一**万元**，
换算只在边界做一次。内部不提前舍入（容差 abs 0.01 万元）。

风险清单 fail-closed：只报证据（计数 + 样本），不做业务推断、不伪造。

🔒 NO_TOKEN — 纯代码，零 AI 依赖。
"""

from __future__ import annotations

from typing import Any, Optional

from bdms.core import db as _db
from bdms.modules.base import ImportError_

from .config import (
    CATEGORIES,
    CATEGORY_DEFERRED,
    CATEGORY_NEW,
    SHEET_MONTHLY_RECORD,
    SUMMARY_TARGET_CONTRACT,
)

CALIBER_GAP_THRESHOLD = 0.01          # ±1%（§8.3 默认）
RISK_SAMPLE_LIMIT = 10

# future 桶金额列（与 compute_budget_trend 金额路由同源）：
#   递延 → K（2026年及以后计划确收）；新签 → Q_adj（截止20251231未确收金额（调整））。
# 202609 布局无 Q_adj 键 → 回退 K，保证两期均可算（不硬编码物理列位）。
FUTURE_AMOUNT_COL = {CATEGORY_DEFERRED: "K", CATEGORY_NEW: "Q_adj"}
FUTURE_AMOUNT_FALLBACK = "K"

FUTURE_BUCKET = "未来可确收"


def _wan(yuan: float) -> float:
    """元 → 万元（内部不提前舍入，仅边界换算）。"""
    return round(float(yuan) / 10000.0, 6)


class ForecastEngine:
    """预测引擎：包装 RevenueAnalysisEngine，产出 §8.3 预测快照。"""

    module_name = "revenue_analysis_forecast"

    def __init__(self, engine):
        self.engine = engine
        self.caliber_builder = engine.caliber_builder

    # ─── 取数 ───

    def _bucket_rows(self, period: str) -> list[dict]:
        conn = _db.get_connection(self.engine.db_path)
        try:
            return [dict(r) for r in conn.execute(
                "SELECT perf_id, budget_fill, budget_trend, bucket_source "
                "FROM ra_bucket WHERE period = ?", (period,)).fetchall()]
        finally:
            conn.close()

    def _actual_ytd_wan(self, period: str, budget_rows: list[dict]) -> float:
        """汇总分析 A 块 r19「合计」实际列（col10，万元）。

        直接复用 engine._build_summary_analysis，避免重复推导聚合（单一事实源）。
        """
        ledger = self.engine._load_sheet_rows(period, SHEET_MONTHLY_RECORD)
        analysis = self.engine._build_summary_analysis(
            budget_rows, ledger_monthly=ledger, period=period)
        row = analysis[18]
        return round(float(row[10] or 0.0), 6)

    def _future_bucket_amount(self, period: str,
                              budget_rows: list[dict]) -> dict:
        """future 桶金额 = 已落库『未来可确收』履约ID × 对应金额列。"""
        bucketed = {r["perf_id"] for r in self._bucket_rows(period)
                    if (r.get("budget_fill") or "").strip() == FUTURE_BUCKET}
        by_group = {g: 0.0 for g in CATEGORIES}
        for r in budget_rows:
            if str(r.get("G") or "") not in bucketed:
                continue
            g = r.get("A") or ""
            if g not in by_group:
                continue
            col = FUTURE_AMOUNT_COL.get(g, FUTURE_AMOUNT_FALLBACK)
            val = r.get(col)
            if val in (None, ""):
                val = r.get(FUTURE_AMOUNT_FALLBACK)
            try:
                by_group[g] += float(val) if val not in (None, "") else 0.0
            except (TypeError, ValueError):
                continue
        return {"count": len(bucketed),
                "amount_wan": _wan(sum(by_group.values())),
                "by_group_wan": {k: _wan(v) for k, v in by_group.items()}}

    # ─── 风险清单 ───

    def _risk_manual_review(self, period: str,
                            budget_rows: list[dict]) -> Optional[dict]:
        """规则未命中（留空）+ 从未落桶的履约ID → 需人工定桶。"""
        rows = self._bucket_rows(period)
        bucketed = {r["perf_id"] for r in rows
                    if (r.get("budget_fill") or "").strip()}
        blank = [r["perf_id"] for r in rows
                 if not (r.get("budget_fill") or "").strip()]
        all_pids = {str(r.get("G") or "") for r in budget_rows
                    if str(r.get("G") or "")}
        seen = {r["perf_id"] for r in rows}   # ra_bucket 已登记行
        never = sorted(all_pids - seen)       # 仅「从未落桶」算缺失
        total = len(set(blank) | set(never))
        if not total:
            return None
        return {
            "type": "manual_review",
            "count": total,
            "blank_in_bucket": len(blank),
            "never_bucketed": len(never),
            "samples": (blank + never)[:RISK_SAMPLE_LIMIT],
            "detail": "budget_fill 留空或未落桶，需人工定桶后才能计入预测",
        }

    def _risk_missing_signals(self, period: str) -> Optional[dict]:
        """OA/ONES 信号不可用或覆盖不足（禁止互推，§3.5）。"""
        try:
            sig = self.engine.load_bucket_signals(period)
        except Exception as e:
            return {"type": "missing_signals", "count": None,
                    "samples": [], "detail": f"信号装载失败: {e}"}
        cov = sig.get("coverage") or {}
        total = cov.get("budget_contracts", 0)
        known = cov.get("oa_known", 0)
        if not sig.get("available"):
            return {"type": "missing_signals", "count": total,
                    "samples": [],
                    "detail": f"信号源不可用: {sig.get('missing_sources')}",
                    "coverage": cov}
        if total and known < total:
            return {"type": "missing_signals", "count": total - known,
                    "samples": [],
                    "detail": "OA 合同下单信号覆盖不足（未知行按 fail-closed 处理）",
                    "coverage": cov}
        return None

    def _risk_contract_disappear(self, budget_rows: list[dict]) -> Optional[dict]:
        """AT（AR）= 合同终止 的消失合同。"""
        note = self.engine.DISAPPEAR_NOTE
        hits = [str(r.get("G") or "") for r in budget_rows
                if str(r.get("AR") or "").strip() == note]
        if not hits:
            return None
        return {"type": "contract_disappear", "count": len(hits),
                "samples": hits[:RISK_SAMPLE_LIMIT],
                "detail": f"消失备注=「{note}」的合同（不影响口径，需跟踪处置）"}

    def _risk_caliber_gap(self, locked_total: float,
                          dynamic_total: float) -> Optional[dict]:
        """动态 vs 锁定差异超 ±1%。"""
        if not locked_total:
            return None
        rel = abs(dynamic_total - locked_total) / abs(locked_total)
        if rel <= CALIBER_GAP_THRESHOLD:
            return None
        return {"type": "caliber_gap", "count": None, "samples": [],
                "detail": (f"动态−锁定差异 {rel * 100:.2f}% 超阈值 "
                           f"±{CALIBER_GAP_THRESHOLD * 100:.0f}%"),
                "relative_diff": round(rel, 6)}

    # ─── 主入口 ───

    def forecast(self, period: str) -> dict:
        """§8.3 预测快照。无宽表数据 → ImportError_（由 service fail-closed 转空结构）。"""
        eng = self.engine
        budget_rows = eng._load_budget_rows(period)
        draft_rows = eng._load_draft_rows(period)
        if not budget_rows or not draft_rows:
            raise ImportError_(
                f"{period} 宽表数据缺失: 预算执行表={len(budget_rows)} "
                f"底稿={len(draft_rows)}")

        cal = self.caliber_builder.build(budget_rows, draft_rows)
        locked = cal["period_locked"]
        dynamic = cal["period_dynamic"]
        locked_wan = _wan(locked["total"])
        dynamic_wan = _wan(dynamic["total"])

        actual_wan = self._actual_ytd_wan(period, budget_rows)
        future = self._future_bucket_amount(period, budget_rows)

        year = int(period[:4]) if period[:4].isdigit() else None
        target_db = eng.get_annual_target(year) if year else None
        if target_db is not None:
            target_wan, target_source = float(target_db), "db"
        else:
            target_wan, target_source = float(SUMMARY_TARGET_CONTRACT), "config"

        projection = round(actual_wan + locked_wan + future["amount_wan"], 6)
        gap = round(target_wan - projection, 6)

        risks = []
        for r in (self._risk_manual_review(period, budget_rows),
                  self._risk_missing_signals(period),
                  self._risk_contract_disappear(budget_rows),
                  self._risk_caliber_gap(locked["total"], dynamic["total"])):
            if r:
                risks.append(r)

        return {
            "period": period,
            "unit": "万元",
            "calibers": {
                "locked": {"total_wan": locked_wan,
                           "by_group_wan": {k: _wan(v) for k, v in
                                            locked["by_group"].items()}},
                "dynamic": {"total_wan": dynamic_wan,
                            "due_total_wan": _wan(dynamic["due_total"]),
                            "pipeline_wan": _wan(dynamic["pipeline"]),
                            "by_group_wan": {k: _wan(v) for k, v in
                                             dynamic["by_group"].items()}},
                "difference_wan": _wan(cal["difference"]),
            },
            "actual_ytd_wan": actual_wan,
            "future_bucket": future,
            "annual_target": {"year": year, "amount_wan": target_wan,
                              "source": target_source},
            "projection_wan": projection,
            "gap_to_target_wan": gap,
            "risks": risks,
            "note": (
                "差距 = 年度目标 −（实际达成 + 锁定口径 + future 桶）；"
                "动态口径不参与差距合计（与 §8.3 一致），差异仅作风险提示。"
            ),
        }
