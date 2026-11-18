"""attribution_engine — Q1 偏差状态/原因自动归因（纯函数，无副作用）。

契约：DESIGN-DETAIL-REVENUE-ANALYSIS-v1.1 §2（Rex 2026-11-12 确认）。

触发条件（唯一写入门槛）：
  AK(滞后未完成) > 0  或  AI(确收) < 0
  → 202606/202609 规范键：AF > 0  或  AD < 0

硬规则（仅两条，其余一律留空 + 人工校验清单）：
  1. AR(消失备注) = "合同终止"        → BL = 客户原因-终止
  2. BF(履约项统计状态) = "3：交付异常" → BK = 差异确收（异常项目）
                                        + BL = 综合原因-项目异常

校验：BK 非空 ⇔ BL 非空（成对填写）。

202606 实测（2026-11-17）：
  - 触发行 109（AF>0 或 AD<0）；设计文档 §2.4/§12.4 记 106，为早期快照口径
  - 规则 1 命中 6 行（XSZS2408090582-5 的 6 个履约项），与 golden BL 一致
  - 规则 2 命中 0 行（触发行中无 BF="3：交付异常"；golden 的 5 行异常项目
    BF 实为 "2：应交未交"/"1：正常交付"）→ 规则 2 在当前源表不触发
  - 其余 103 行留空入人工清单

🔒 NO_TOKEN — 纯代码，零 AI 依赖。
"""

from __future__ import annotations

from typing import Any, Callable

# 硬规则常量
REASON_TERMINATED = "客户原因-终止"
STATUS_NON_ELIMINABLE = "差异确收（当年不可消除）"
STATUS_EXCEPTION = "差异确收（异常项目）"
REASON_PROJECT_EXCEPTION = "综合原因-项目异常"
BF_DELIVERY_EXCEPTION = "3：交付异常"
NOTE_TERMINATED = "合同终止"

# 上下文特征键（canonical 键优先，202606 扩展键兜底）
_CONTEXT_KEYS = (
    "B", "E", "A", "AF", "AD", "AP", "AQ", "AR", "AS",
    "BF", "BG", "BQ", "BU", "BV", "BO", "AT",
)


def _num(v: Any) -> float:
    try:
        return float(v) if v not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def _get(row: dict, key: str) -> Any:
    """规范键优先；202606 扩展键（BQ/BU/BV/BF/BG/BO）原样可读。"""
    return row.get(key)


def trigger_reason(row: dict) -> str | None:
    """触发条件命中说明；未命中返回 None。"""
    lag = _num(_get(row, "AF"))
    actual = _num(_get(row, "AD"))
    if lag > 0:
        return f"AF(滞后未完成)={lag:g}>0"
    if actual < 0:
        return f"AD(确收)={actual:g}<0"
    return None


def apply_rules(row: dict) -> tuple[str | None, str | None, list[str]]:
    """应用两条硬规则。返回 (status, reason, 命中说明列表)。"""
    hits: list[str] = []
    status: str | None = None
    reason: str | None = None

    # 规则 2（优先，状态+原因成对）：BF = 3：交付异常
    if _get(row, "BF") == BF_DELIVERY_EXCEPTION:
        status = STATUS_EXCEPTION
        reason = REASON_PROJECT_EXCEPTION
        hits.append(f"BF={BF_DELIVERY_EXCEPTION} → 状态=异常项目 + 原因=项目异常")

    # 规则 1：AR = 合同终止 → 状态 + 原因成对（202606 golden 实证：
    # 25 行 BL=客户原因-终止 全部 BK=差异确收（当年不可消除））
    if _get(row, "AR") == NOTE_TERMINATED and reason is None:
        status = STATUS_NON_ELIMINABLE
        reason = REASON_TERMINATED
        hits.append(f"AR={NOTE_TERMINATED} → 状态=当年不可消除 + 原因=客户原因-终止")

    return status, reason, hits


def compute_attribution(rows: list[dict]) -> dict[str, Any]:
    """对预算执行表行集执行 Q1 归因。

    Returns:
        {
          "triggered": int,          # 触发行数
          "auto_filled": int,        # 自动填写行数（status 或 reason 非空）
          "pending": int,            # 留空待人工行数
          "rule_hits": {"rule1_terminate": int, "rule2_exception": int},
          "pair_violations": int,    # BK 非空 ⇔ BL 非空 违反数
          "rows": [                  # 触发行明细
             {"perf_id", "contract_no", "category", "trigger_reason",
              "status", "reason", "auto_filled", "context"}
          ],
        }
    """
    out_rows: list[dict] = []
    rule1 = rule2 = pair_violations = 0
    skipped_agg = 0

    for r in rows:
        # 聚合行（B="合计"）无履约明细，AF/AD 为全表汇总，不参与 Q1 归因
        if str(r.get("B") or "").strip() == "合计" or not _get(r, "E"):
            skipped_agg += 1
            continue
        tr = trigger_reason(r)
        if tr is None:
            continue
        status, reason, hits = apply_rules(r)
        if "AR=" in "".join(hits):
            rule1 += 1
        if "BF=" in "".join(hits):
            rule2 += 1
        # 成对校验：任一非空而另一为空 → 违反
        if bool(status) != bool(reason):
            pair_violations += 1
        ctx = {k: _get(r, k) for k in _CONTEXT_KEYS if _get(r, k) is not None}
        out_rows.append({
            "perf_id": _get(r, "E"),
            "contract_no": _get(r, "B"),
            "category": _get(r, "A"),
            "trigger_reason": tr,
            "status": status,
            "reason": reason,
            "auto_filled": 1 if (status or reason) else 0,
            "context": ctx,
        })

    auto_filled = sum(1 for x in out_rows if x["auto_filled"])
    return {
        "triggered": len(out_rows),
        "auto_filled": auto_filled,
        "pending": len(out_rows) - auto_filled,
        "rule_hits": {"rule1_terminate": rule1, "rule2_exception": rule2},
        "pair_violations": pair_violations,
        "skipped_aggregate_rows": skipped_agg,
        "rows": out_rows,
    }
