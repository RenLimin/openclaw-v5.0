"""BDMS v2.1 — Contract Management 模块。

🔒 NO_TOKEN — 纯代码，零 AI 依赖。

导出：
  - ContractManagementEngine
  - ContractManagementService
  - ContractExporter
  - ContractOCRImporter
  - 数据模型（Contract, ContractDocument, ContractClause, RiskScanResult, ApprovalNode）
"""

from .engine import ContractManagementEngine
from .service import ContractManagementService
from .exporter import ContractExporter
from .ocr_importer import ContractOCRImporter
from .models import (
    Contract,
    ContractDocument,
    ContractClause,
    RiskScanResult,
    ApprovalNode,
)

__all__ = [
    "ContractManagementEngine",
    "ContractManagementService",
    "ContractExporter",
    "ContractOCRImporter",
    "Contract",
    "ContractDocument",
    "ContractClause",
    "RiskScanResult",
    "ApprovalNode",
]
