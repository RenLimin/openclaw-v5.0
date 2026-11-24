"""风险点视图（RiskPoint）— 把 L3 22 条规则结果与「条款缺失」合并为统一风险清单。

需求来源：Rex 2026-11-24「重点是需要从合同文本中识别出来合同风险点」。

设计要点：
- **主视角 = 风险点**，不是「22 条检查表」。逐条带：类别 / 级别 / 状态 / 法条 /
  证据（原文片段或「未检出」）/ 建议。
- 证据红线：`law` 只能来自 L3 受控库；条款缺失类 `law` 来自 `CLAUSE_CATEGORIES`
  （同属 L3 受控定义），L4 不自由造法条。
- 分级口径：high/medium/low 沿用 L3 `RiskRule.risk`；条款缺失一律 **low**
  （漏抽 ≠ 真缺失，避免误伤，交人工复核）。
- 去重：同一 (category, item) 只出现一次。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .digitize import DigitizedText
from . import risk as risk_mod
from .clause_extract import extract_clauses, ClauseExtractError

# 状态展示标签
STATUS_LABEL = {
    "pass": "通过",
    "warning": "提示",
    "fail": "不通过",
    "missing": "条款缺失",
}

_LEVEL_RANK = {"high": 3, "medium": 2, "low": 1}


def _snippet(text: str, keyword: str, width: int = 90) -> str:
    """取关键词附近原文片段作证据；找不到返回空串。"""
    if not text or not keyword:
        return ""
    idx = text.find(keyword)
    if idx < 0:
        # 退化：用检查项名做二次匹配
        return ""
    start = max(0, idx - width // 2)
    seg = text[start:start + width].replace("\n", " ").strip()
    return seg


def build_risk_points(
    digitized: DigitizedText,
    *,
    l3_component_root: Optional[str] = None,
) -> Dict[str, Any]:
    """构建统一风险点清单（只读纯计算）。

    Returns:
        {
          "points": [ {source,rule_id,category,item,level,status,law,evidence,suggestion} ],
          "summary": {"high","medium","low","pass","warning","fail","missing"},
          "overall_risk": high|medium|low,
          "degraded": [...],           # 如 L3 不可用 / 全文为空
          "rule_set_version": str,
        }
    """
    text = (digitized.full_text or "").strip()
    points: List[Dict[str, Any]] = []
    degraded: List[str] = []

    if not text:
        degraded.append("EMPTY_TEXT")
        return {
            "points": [], "summary": {}, "overall_risk": "unknown",
            "degraded": degraded, "rule_set_version": "",
        }

    # ---- A. L3 受控规则 22 条 ----
    rule_version = ""
    try:
        report = risk_mod.run_risk(digitized, l3_component_root)
        rule_version = report.get("rule_set_version", "")
        # 法条白名单断言：非 pass 的 finding 其 law 必须可回溯受控库
        for f in report.get("findings", []):
            if f.get("status") == "pass":
                continue
            evidence = _snippet(text, f.get("item", "")) or "未检出对应表述"
            points.append({
                "source": "L3_CHECK_RULES",
                "rule_id": f.get("id", ""),
                "category": f.get("category", ""),
                "item": f.get("item", ""),
                "level": f.get("risk", "low"),
                "status": f.get("status", "warning"),
                "law": f.get("law", ""),
                "evidence": evidence,
                "suggestion": "",
            })
    except Exception as exc:  # noqa: BLE001
        degraded.append("L3_RULES: %s" % exc)

    # ---- B. 条款缺失维度（L3 规则引擎没有的）----
    try:
        parsed = extract_clauses(text, l3_component_root=l3_component_root)
        for m in parsed["missing_required"]:
            points.append({
                "source": "CLAUSE_MISSING",
                "rule_id": "C-%s" % m["category"],
                "category": m["category"],
                "item": "必备条款未检出（%s）" % m["description"],
                "level": "low",
                "status": "missing",
                "law": m.get("law", ""),
                "evidence": "全文未检出该条款表述",
                "suggestion": "人工确认是否确缺该条款；若为 OCR/抽取漏检请补原文后复核",
            })
    except ClauseExtractError as exc:
        degraded.append("CLAUSE_EXTRACT: %s" % exc)
    except Exception as exc:  # noqa: BLE001
        degraded.append("CLAUSE_EXTRACT: %s" % exc)

    # ---- 汇总 ----
    summary = {"high": 0, "medium": 0, "low": 0,
               "pass": 0, "warning": 0, "fail": 0, "missing": 0}
    for p in points:
        if p["level"] in summary:
            summary[p["level"]] += 1
        if p["status"] in summary:
            summary[p["status"]] += 1

    if summary["high"]:
        overall = "high"
    elif summary["medium"] >= 2 or summary["fail"]:
        overall = "medium"
    else:
        overall = "low"

    return {
        "points": points,
        "summary": summary,
        "overall_risk": overall,
        "degraded": degraded,
        "rule_set_version": rule_version,
    }
