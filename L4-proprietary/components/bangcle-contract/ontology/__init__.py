"""ontology — 泛微 Cube 合同卡片 ↔ L3 Contract 领域模型的只读映射桥（P1）。

纯映射，无网络/DB/会话副作用；依赖方向 L4 → L3（不修改 L3）。
设计契约：docs/architecture/DESIGN-DETAIL-contract-ontology-bridge-v1.0.md §2.1。
"""

from .mapper import (
    FIELD_ALIASES,
    map_card_to_contract,
    map_contract_to_card,
    map_oa_status,
    parse_amount,
)

__all__ = [
    "FIELD_ALIASES",
    "map_card_to_contract",
    "map_contract_to_card",
    "map_oa_status",
    "parse_amount",
]
