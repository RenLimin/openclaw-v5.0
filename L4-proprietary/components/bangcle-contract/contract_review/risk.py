"""风险编排（risk）— 调用 L3 scan_text。

按 DESIGN-DETAIL-v1.0 §1/§3、PRD §9.2：
- 风险规则与法条依据**只**来自 L3 受控规则库（CHECK_RULES），
  L4 不重写、不注入任何 LLM 自由生成的法条。
- 本期语义轨关闭：仅跑 L3 阈值/确定性规则。
- 依赖方向 L4→L3：通过 sys.path 注入 L3 组件根（不修改 L3）。
- 合同原文仅在本地传给 L3 纯函数，不发起网络调用。
"""

from __future__ import annotations

import os
from typing import Optional

from .digitize import DigitizedText

# L3 规则库版本（与 L3 组件保持一致的受控标识）
RULE_SET_VERSION = "L3-contract-management-v1.0"


def _default_l3_component_root() -> str:
    component_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(component_root)))
    return os.path.join(repo_root, "L3-business", "components", "contract-management")


def load_l3(l3_component_root: Optional[str] = None):
    """注入 L3 组件根到 sys.path 并返回 (scan_text, CHECK_RULES)。"""
    root = l3_component_root or _default_l3_component_root()
    if not os.path.isdir(root):
        raise RuntimeError(f"L3 contract-management 组件不存在: {root}")

    import sys

    if root not in sys.path:
        sys.path.insert(0, root)

    from contract_management.risk_engine import scan_text, CHECK_RULES

    return scan_text, CHECK_RULES


def run_risk(
    digitized: DigitizedText,
    l3_component_root: Optional[str] = None,
) -> dict:
    """对数字化文本执行 L3 风险扫描，返回 RiskReport.to_dict()。

    保证每条 finding 的 law 仅取自 L3 CHECK_RULES；
    返回 dict 额外附带受控的 rule_set_version。
    """
    scan_text, check_rules = load_l3(l3_component_root)

    report = scan_text(digitized.full_text)
    data = report.to_dict()

    # 安全断言：findings 数量与规则库一致，且法条全部可回溯到受控库
    controlled_laws = {rule.law for rule in check_rules}
    if len(data["findings"]) != len(check_rules):
        raise RuntimeError("风险 finding 数量与 L3 受控规则库不一致")
    for finding in data["findings"]:
        if finding["law"] not in controlled_laws:
            raise RuntimeError(
                f"发现非受控法条依据: {finding['law']!r}（红线：法条仅来自 L3 规则库）"
            )

    data["rule_set_version"] = RULE_SET_VERSION
    return data
