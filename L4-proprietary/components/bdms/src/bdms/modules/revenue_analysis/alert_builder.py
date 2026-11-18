"""alert_builder — Q4 预警清单（新签消失等，纯函数，无副作用）。

契约：DESIGN-DETAIL-REVENUE-ANALYSIS-v1.1 §5（Rex 2026-11-12 确认）。

预警类型：
  1. new_sign_disappear：分类=新签 且 AP/AQ(消失金额)≠0
     → 上下文 = AR(消失备注) + 底稿 N 列备注（含「汇率」等关键词显著标注）
     → 该金额不进《履约汇总记录》（与 202606 黄金一致：新签消失=0）
  2. attribution_pending：归因留空待人工（Q1 未命中硬规则的触发行）
  3. trend_unassigned：趋势分桶异常（stat 行无法归桶）——预留，当前不产生

🔒 NO_TOKEN — 纯代码，零 AI 依赖。
"""

from __future__ import annotations

from typing import Any

_DISAPPEAR_KEYWORDS = ("汇率", "终止", "异常", "调整")


def _num(v: Any) -> float:
    try:
        return float(v) if v not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def build_alerts(rows: list[dict],
                 attribution: dict[str, Any] | None = None) -> list[dict]:
    """构建 Q4 预警清单。

    Args:
        rows: 预算执行表行集（202606 宽表含扩展键 AP/AQ/AR）
        attribution: compute_attribution() 输出（含 pending 行）
    Returns:
        [{"alert_type", "perf_id", "contract_no", "amount", "context"}]
    """
    out: list[dict] = []

    # 1. 新签消失
    for r in rows:
        if r.get("A") != "新签":
            continue
        ap = _num(r.get("AP"))
        aq = _num(r.get("AQ"))
        if ap == 0 and aq == 0:
            continue
        note = r.get("AR") or ""
        keywords = [k for k in _DISAPPEAR_KEYWORDS if k in str(note)]
        out.append({
            "alert_type": "new_sign_disappear",
            "perf_id": r.get("E"),
            "contract_no": r.get("B"),
            "amount": ap or aq,
            "context": {
                "AP": ap, "AQ": aq, "AR": note,
                "keywords": keywords,
                "note": (f"新签消失 {ap or aq:g} 元，不进《履约汇总记录》"
                         f"（202606 黄金口径）；备注={note or '空'}"),
            },
        })

    # 2. 归因留空待人工
    if attribution:
        for x in attribution.get("rows", []):
            if x.get("auto_filled"):
                continue
            out.append({
                "alert_type": "attribution_pending",
                "perf_id": x.get("perf_id"),
                "contract_no": x.get("contract_no"),
                "amount": None,
                "context": {
                    "trigger_reason": x.get("trigger_reason"),
                    "category": x.get("category"),
                    "features": x.get("context", {}),
                    "note": "触发行未命中硬规则 → BK/BL 留空，待人工校验",
                },
            })

    return out
