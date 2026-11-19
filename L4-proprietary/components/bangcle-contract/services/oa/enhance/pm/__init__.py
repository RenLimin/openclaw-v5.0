"""OA 项目实施管理「分配项目经理」批注建议资产（只读）。

设计：docs/PRD-oa-project-management-asset-v1.0.md 及 DESIGN-* 三份。
口径：KB EXP-20261112-001。全程 OA/ONES 只读，无写调用。
"""
from .order import ProjectOrder, OrderItem, PmAssetError, parse
from .fields import FieldMap, resolve, infer_from_title

__all__ = ["ProjectOrder", "OrderItem", "PmAssetError", "parse", "FieldMap", "resolve", "infer_from_title"]
