"""services.oa.enhance — OA 销售合同审查增强层（只读）。

R1 客户/最终用户履约义务核查（ONES 实时）
R2 概算一致性核查（OA Cube 卡片只读）

落点：L4 bangcle-contract/services/oa/enhance/（DESIGN-DETAIL v1.0 §2）。
红线：全程只读，不做任何 OA/ONES/BDMS 写操作。
"""

from .oa_form import OrderForm, OrderItem, parse_order_form
from .ones_obigation import ObligationRecord, R1Result, check_obligations
from .todo import TodoItem, OaSessionExpired, discover_todos
from .checks import CheckResult, parse_body_fields, run_fixed_checks
from .remark import derive_verdict, render_remark

__all__ = [
    "OrderForm",
    "OrderItem",
    "parse_order_form",
    "ObligationRecord",
    "R1Result",
    "check_obligations",
    "TodoItem",
    "OaSessionExpired",
    "discover_todos",
    "CheckResult",
    "parse_body_fields",
    "run_fixed_checks",
    "derive_verdict",
    "render_remark",
]
