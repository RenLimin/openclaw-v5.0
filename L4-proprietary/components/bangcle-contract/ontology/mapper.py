"""ontology.mapper — Cube 卡片主字段 ↔ L3 Contract 的确定性纯映射（P1）。

契约（DESIGN-DETAIL-contract-ontology-bridge-v1.0 §2.1）：
- 输入 main_fields：``extract_main_fields`` 输出的 ``{显示名: str}``
- 按 FIELD_ALIASES 取首个命中标签的值；字段缺失不抛错，留 L3 默认值
- amount：剥离 ¥/元/人民币/逗号/空格；含 '万' 乘 1e4；无法解析返 0.0
- P1 无泛微 workflow 数据源：map_oa_status 恒 unknown
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional


# ---------------------------------------------------------------
# L3 路径注入（与 contract_review/risk.py 同一方式）
# ---------------------------------------------------------------

def _default_l3_component_root() -> str:
    component_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(component_root)))
    return os.path.join(repo_root, "L3-business", "components", "contract-management")


def _load_contract():
    """注入 L3 组件根到 sys.path 并返回 Contract dataclass。"""
    root = _default_l3_component_root()
    if not os.path.isdir(root):
        raise RuntimeError(f"L3 contract-management 组件不存在: {root}")

    import sys

    if root not in sys.path:
        sys.path.insert(0, root)

    from contract_management.models import Contract

    return Contract


# ---------------------------------------------------------------
# 别名表（DETAIL §2.1，顺序即优先级）
# ---------------------------------------------------------------

FIELD_ALIASES: Dict[str, tuple] = {
    "contract_no": ("合同编号", "合同号", "编号"),
    "title": ("合同名称", "标题", "合同标题"),
    "contract_type": ("合同类型", "类型"),
    "party_a": ("甲方", "委托方", "客户名称"),
    "party_b": ("乙方", "受托方", "供应商名称"),
    "amount": ("合同金额", "金额", "合同总金额", "含税金额"),
    "effective_date": ("生效日期", "合同生效日"),
    "expiry_date": ("到期日期", "合同到期日", "截止日期"),
}

# map_contract_to_card 使用的规范显示名（取每个字段首个别名）
_CANONICAL_LABELS: Dict[str, str] = {
    field_name: aliases[0] for field_name, aliases in FIELD_ALIASES.items()
}

# 金额解析需剥离的字符/词
_AMOUNT_STRIP_TOKENS = ("人民币", "¥", "￥", "元", ",", " ", "\u00a0", "\t", "\n")


def parse_amount(value: Any) -> float:
    """把合同金额文本解析为 float。

    - 剥离 '¥'/'￥'/'人民币'/'元'/逗号/空白
    - 含 '万' 按 1e4 换算
    - 无法解析（None/空串/非数字）返 0.0，不抛错
    """
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return 0.0

    is_wan = "万" in text
    for token in _AMOUNT_STRIP_TOKENS:
        text = text.replace(token, "")
    text = text.replace("万", "")

    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return 0.0

    try:
        number = float(match.group(0))
    except ValueError:
        return 0.0
    return number * 1e4 if is_wan else number


def _first_hit(main_fields: Dict[str, Any], aliases: tuple) -> Optional[str]:
    """按别名顺序返回 main_fields 中首个命中的标签对应的值。"""
    for label in aliases:
        if label in main_fields:
            return main_fields[label]
    return None


def map_card_to_contract(main_fields: Dict[str, Any]) -> Any:
    """Cube main_fields → L3 Contract（确定性纯函数）。

    未命中字段留 L3 默认值（contract_type='tech_service', status='draft'）；不抛错。
    """
    Contract = _load_contract()

    if not isinstance(main_fields, dict):
        return Contract()

    values: Dict[str, Any] = {}
    for field_name, aliases in FIELD_ALIASES.items():
        raw = _first_hit(main_fields, aliases)
        if raw is None:
            continue
        values[field_name] = parse_amount(raw) if field_name == "amount" else str(raw)

    return Contract(**values)


def map_contract_to_card(contract: Any) -> Dict[str, str]:
    """L3 Contract → Cube 风格 main_fields（规范显示名；P1 仅供展示/测试往返）。"""
    return {
        label: "" if getattr(contract, field_name, None) is None
        else str(getattr(contract, field_name))
        for field_name, label in _CANONICAL_LABELS.items()
    }


def map_oa_status(status_payload: Any, available: bool = False) -> Dict[str, Any]:
    """OA 审批状态 → L3 状态信封。

    P1：泛微 workflow 审批流数据源未接入，available=False 时恒返 unknown；
    绝不臆造状态映射。
    """
    if not available:
        return {"l3_status": "unknown", "confidence": 0.0, "source": "unavailable"}
    # P3+ 才有数据源；即便显式传 True 也不伪造（保留入参以便未来扩展）
    return {"l3_status": "unknown", "confidence": 0.0, "source": "unavailable"}
