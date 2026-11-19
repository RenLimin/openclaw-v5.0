"""OA 单据解析（只读）— 从已捕获的 OA XHR 原始数据提取主字段与分项明细。

数据源：``oa_workflow_ones.py --capture <rid>`` 落盘的 ``xhrs.json``：
  - ``loadForm``     → maindata（最终用户 / 合同甲方 / 概算名称 billid / 概算流程 requestid）
  - ``detailData``   → detail_1.rowDatas（产品分项）

字段语义经 2026-11-18 单据 886377 实测确认；标签缺失处按 fieldname 推断并标注 inferred。
本模块只读本地 JSON，不发起网络请求。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---- 字段映射（实测 886377；见 DESIGN-DETAIL §3.1）----
F_END_USER = "field10433"          # 最终用户名称（文本）
F_END_USER_OBJ = "field10873"      # 最终用户（浏览框）
F_CONTRACT_PARTY_A = "field10430"  # 合同甲方
F_CONTRACT_NAME = "field10431"     # 合同名称
F_ESTIMATE_NAME = "field26675"     # 销售合同概算名称（billid）
F_ESTIMATE_FLOW = "field29422"     # 概算流程（requestid）

F_ITEM_CODE = "field10644"         # 产品服务编码
F_ITEM_NAME = "field29757"         # 产品名称
F_ITEM_AMOUNT = "field10451"       # 本单金额
F_ITEM_STD = "field26701"          # 标准价
F_ITEM_DISCOUNT = "field26698"     # 折扣
F_ITEM_QTY = "field10655"          # 数量
F_ITEM_EST_BILLID = "field32828"   # 概算卡片 billid

_DETAIL_TABLE = "detail_1"


class OrderFormError(ValueError):
    """单据解析失败（缺文件 / 结构异常）。"""


def _dec(value: Any) -> Optional[Decimal]:
    """宽松十进制解析；空/异常返回 None。"""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _value(node: Any) -> str:
    """取节点标量值。

    浏览框/选择型字段：``value`` 常为 id，显示名在 ``specialobj[0].name`` → **优先 name**。
    纯文本/数值字段：无 specialobj → 取 ``value``。
    """
    if not isinstance(node, dict):
        return ""
    objs = node.get("specialobj") or []
    if objs and isinstance(objs[0], dict):
        name = objs[0].get("name")
        if name not in (None, ""):
            return str(name).strip()
    raw = node.get("value")
    if raw not in (None, ""):
        return str(raw).strip()
    if objs and isinstance(objs[0], dict) and objs[0].get("id"):
        return str(objs[0]["id"]).strip()
    return ""


def _billid(node: Any) -> str:
    """取浏览框 billid（优先 specialobj[0].id）。"""
    if not isinstance(node, dict):
        return ""
    objs = node.get("specialobj") or []
    if objs and isinstance(objs[0], dict) and objs[0].get("id"):
        return str(objs[0]["id"]).strip()
    return _value(node)


def _find_xhr(xhrs: List[Dict[str, Any]], keyword: str) -> Optional[str]:
    for item in xhrs:
        url = str(item.get("url") or "")
        if keyword in url:
            body = item.get("body")
            if isinstance(body, str) and body.strip():
                return body
    return None


def _load_json_body(raw: Optional[str]) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # 宽松 JSON（裸数字键）：仅作兜底，失败即报错不静默
        return None


@dataclass
class OrderItem:
    """本单产品分项（R2 输入）。"""

    keyid: str = ""
    product_code: str = ""
    product_name: str = ""
    amount: Optional[Decimal] = None
    std_price: Optional[Decimal] = None
    discount: Optional[Decimal] = None
    qty: Optional[Decimal] = None
    estimate_billid: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "keyid": self.keyid,
            "product_code": self.product_code,
            "product_name": self.product_name,
            "amount": str(self.amount) if self.amount is not None else None,
            "std_price": str(self.std_price) if self.std_price is not None else None,
            "discount": str(self.discount) if self.discount is not None else None,
            "qty": str(self.qty) if self.qty is not None else None,
            "estimate_billid": self.estimate_billid,
        }


@dataclass
class OrderForm:
    """OA 单据解析结果（R1/R2 共同输入）。"""

    request_id: str = ""
    end_user: str = ""
    contract_party_a: str = ""
    contract_name: str = ""
    estimate_billid: str = ""
    estimate_flow_requestid: str = ""
    items: List[OrderItem] = field(default_factory=list)
    field_semantics: Dict[str, str] = field(default_factory=dict)

    @property
    def product_codes(self) -> List[str]:
        return [i.product_code for i in self.items if i.product_code]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "end_user": self.end_user,
            "contract_party_a": self.contract_party_a,
            "contract_name": self.contract_name,
            "estimate_billid": self.estimate_billid,
            "estimate_flow_requestid": self.estimate_flow_requestid,
            "items": [i.to_dict() for i in self.items],
            "field_semantics": dict(self.field_semantics),
        }


def _parse_main_fields(obj: Any) -> Dict[str, str]:
    main = (obj or {}).get("maindata") or {}
    return {
        "end_user": _value(main.get(F_END_USER)) or _value(main.get(F_END_USER_OBJ)),
        "contract_party_a": _value(main.get(F_CONTRACT_PARTY_A)),
        "contract_name": _value(main.get(F_CONTRACT_NAME)),
        "estimate_billid": _billid(main.get(F_ESTIMATE_NAME)),
        "estimate_flow_requestid": _billid(main.get(F_ESTIMATE_FLOW)),
    }


def _parse_items(obj: Any) -> List[OrderItem]:
    detail = (obj or {}).get(_DETAIL_TABLE) or {}
    rows = (detail.get("rowDatas") or {})
    items: List[OrderItem] = []
    for key in sorted(rows.keys()):
        row = rows.get(key) or {}
        items.append(
            OrderItem(
                keyid=str(row.get("keyid") or key),
                product_code=_value(row.get(F_ITEM_CODE)),
                product_name=_value(row.get(F_ITEM_NAME)),
                amount=_dec(_value(row.get(F_ITEM_AMOUNT))),
                std_price=_dec(_value(row.get(F_ITEM_STD))),
                discount=_dec(_value(row.get(F_ITEM_DISCOUNT))),
                qty=_dec(_value(row.get(F_ITEM_QTY))),
                estimate_billid=_billid(row.get(F_ITEM_EST_BILLID)),
            )
        )
    return items


def parse_order_form(raw_dir: Path, request_id: str) -> OrderForm:
    """解析已捕获的 OA 单据 XHR 原始目录。

    Args:
        raw_dir: ``oa_workflow_ones.py --capture`` 的 raw 根目录（其下 ``<rid>/xhrs.json``）。
        request_id: OA requestid。

    Raises:
        OrderFormError: 缺 xhrs.json / 结构异常（fail-closed，不伪造）。
    """
    path = Path(raw_dir) / request_id / "xhrs.json"
    if not path.exists():
        raise OrderFormError("未找到单据原始数据: %s" % path)
    try:
        xhrs = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise OrderFormError("xhrs.json 解析失败: %s" % exc) from exc

    main_raw = _load_json_body(_find_xhr(xhrs, "loadForm"))
    detail_raw = _load_json_body(_find_xhr(xhrs, "detailData"))
    if main_raw is None:
        raise OrderFormError("缺 loadForm 响应")

    form = OrderForm(request_id=request_id)
    form.__dict__.update(_parse_main_fields(main_raw))
    if detail_raw is not None:
        form.items = _parse_items(detail_raw)
    form.field_semantics = {
        "amount": "field10451（实测值推断）",
        "estimate_billid": "field32828（实测值推断）",
        "inferred": "label 缺失字段按实测值语义推断，非卡片显式标签",
    }
    return form
