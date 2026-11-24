"""条款拆解（clause extraction）— 复用 L3 `contract_parser`。

需求来源：Rex 2026-11-24「增加合同管理资产中拆解合同条款的能力」。

设计要点：
- **不重写**：L3 已有 24+ 提取器 / 28 类条款（含法条·原文·摘要·问题·建议），
  本模块只做编排与结构化输出（避免重复建设，遵守 AGENTS.md 铁律）。
- **缺失检测**：`CLAUSE_CATEGORIES` 中 `required=True` 且提取器存在、但未抽出条款
  的类别 → `missing_required`。这是 L3 `risk_engine` 22 条规则**没有**的维度
  （风险引擎只判「文本中存在性」，整条缺失不会报）。
- **诚实标注**：L3 的 `_extract_all_clauses` 并非覆盖全部 28 类；无提取器的类别
  进入 `unsupported_categories`，**不参与缺失判定**（漏抽 ≠ 真缺失）。
- 纯本地：只把文本传给 L3 纯函数，不发网络（数据安全红线）。
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


def _default_l3_component_root() -> str:
    component_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(component_root)))
    return os.path.join(repo_root, "L3-business", "components", "contract-management")


class ClauseExtractError(RuntimeError):
    """L3 组件不可用（显式报错，不静默伪造）。"""


def load_l3(l3_component_root: Optional[str] = None):
    """注入 L3 组件根并返回 (parse_contract, CLAUSE_CATEGORIES, 模块对象)。"""
    root = l3_component_root or _default_l3_component_root()
    if not os.path.isdir(root):
        raise ClauseExtractError("L3 contract-management 组件不存在: %s" % root)

    import sys

    if root not in sys.path:
        sys.path.insert(0, root)

    try:
        from contract_management.contract_parser import parse_contract, CLAUSE_CATEGORIES
        import contract_management.contract_parser as cp_mod
    except Exception as exc:  # noqa: BLE001
        raise ClauseExtractError("L3 条款解析器加载失败: %s" % exc) from exc

    return parse_contract, CLAUSE_CATEGORIES, cp_mod


def _has_extractor(cp_mod: Any, category: str) -> bool:
    """该类别是否有对应提取器（无提取器 → 永不判缺失）。"""
    return hasattr(cp_mod, "_extract_clause_%s" % category)


def _clause_to_dict(clause: Any, *, max_text: int = 600) -> Dict[str, Any]:
    text = (getattr(clause, "original_text", "") or "").replace("\n", " ").strip()
    return {
        "category": getattr(clause, "category", ""),
        "law": getattr(clause, "law_article", ""),
        "summary": (getattr(clause, "summary", "") or "").strip(),
        "original_text": text[:max_text],
        "key_terms": dict(getattr(clause, "key_terms", {}) or {}),
        "issues": list(getattr(clause, "issues", []) or []),
        "suggestions": list(getattr(clause, "suggestions", []) or []),
    }


def extract_clauses(
    text: str,
    *,
    l3_component_root: Optional[str] = None,
) -> Dict[str, Any]:
    """对合同全文做条款拆解（只读纯计算）。

    Returns:
        {
          "title": str,
          "party_a": {...}, "party_b": {...},
          "clauses": [ {...} ],              # 已抽出的条款
          "missing_required": [ {"category","law","description"} ],
          "unsupported_categories": [ ... ], # 无提取器，不参与缺失判定
          "stats": {"categories_total","extracted","required_total","missing_required"},
        }
    """
    parse_contract, categories, cp_mod = load_l3(l3_component_root)
    parsed = parse_contract(text or "")

    clauses = [_clause_to_dict(c) for c in (parsed.clauses or [])]
    got = {c["category"] for c in clauses}

    missing: List[Dict[str, Any]] = []
    unsupported: List[str] = []
    for cat, meta in categories.items():
        if cat in got:
            continue
        if not _has_extractor(cp_mod, cat):
            unsupported.append(cat)
            continue
        if meta.get("required"):
            missing.append({
                "category": cat,
                "law": meta.get("law", ""),
                "description": meta.get("description", ""),
            })

    required_total = sum(1 for m in categories.values() if m.get("required"))
    return {
        "title": (parsed.title or "").strip(),
        "party_a": dict(parsed.party_a or {}),
        "party_b": dict(parsed.party_b or {}),
        "clauses": clauses,
        "missing_required": missing,
        "unsupported_categories": unsupported,
        "stats": {
            "categories_total": len(categories),
            "extracted": len(clauses),
            "required_total": required_total,
            "missing_required": len(missing),
        },
    }
