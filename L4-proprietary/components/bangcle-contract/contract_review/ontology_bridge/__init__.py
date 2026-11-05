"""ontology_bridge — Contract Ontology Bridge（L4 → L2 运营本体桥）。

依据 DESIGN-OUTLINE-contract-ontology-bridge-v1.0：
- registry.py   ContractRegistry：合同登记为 L2 运营对象（P1）
- connector.py  ContractWritebackConnector / NotifyConnector：真写回 + 补偿（P2）
- bridge.py     ContractOntologyBridge：propose→validate→review→commit 编排（P2）

依赖方向严格 L4 → L3/L2 单向；本包顶层不导入 L2/L3 模块，
运行时由 bridge/registry 方法内注入 sys.path（与 contract_service._load_l3 同模式）。
"""

__version__ = "1.0.0"

from .registry import ContractRegistry, canonical_contract_no
from .connector import ContractWritebackConnector, NotifyConnector
from .bridge import ContractOntologyBridge
from .assemble import assemble

__all__ = [
    "ContractRegistry",
    "canonical_contract_no",
    "ContractWritebackConnector",
    "NotifyConnector",
    "ContractOntologyBridge",
    "assemble",
]
