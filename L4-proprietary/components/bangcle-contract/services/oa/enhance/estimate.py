"""R2 — 概算一致性核查（只读）。

数据源：OA Cube 卡片（Playwright storage_state，只读）。
口径（Rex 2026-11-18 拍板）：**允许销售额超概算，超出仅提醒**（over_budget_warn，不构成退回项）。

卡片参数（实测 billid 9955）：modeId=340 / formId=-673 / layoutid=1335
明细表：uf_xssjxmbbtzb_dt1（detail_1）
字段（实测）：field26645=产品服务编码 / field26658=预计签约价 / field26656=标准价
           field26628=折扣 / field26655=数量
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ..cube import CubeClient, CubeAuthError, CubePermissionError, CubeError

# 概算卡片建模参数（实测 9955）
EST_MODE_ID = "340"
EST_FORM_ID = "-673"
EST_LAYOUTID = "1335"
EST_TABLE = "uf_xssjxmbbtzb_dt1"
EST_GROUPID = 0

F_EST_CODE = "field26645"
F_EST_NAME = "field29781"
F_EST_AMOUNT = "field26658"
F_EST_STD = "field26656"
F_EST_DISCOUNT = "field26628"
F_EST_QTY = "field26655"


class EstimateError(RuntimeError):
    """R2 核查失败（显式报错，不静默伪造）。"""


@dataclass
class EstimateRow:
    """逐项比对行。"""

    product_code: str
    product_name: str = ""
    estimate_amount: Optional[Decimal] = None
    actual_amount: Optional[Decimal] = None
    diff: Optional[Decimal] = None
    verdict: str = "未知"   # 一致 / over_budget_warn / 缺项 / 未知

    def to_dict(self) -> Dict[str, Any]:
        return {
            "product_code": self.product_code,
            "product_name": self.product_name,
            "estimate_amount": str(self.estimate_amount) if self.estimate_amount is not None else None,
            "actual_amount": str(self.actual_amount) if self.actual_amount is not None else None,
            "diff": str(self.diff) if self.diff is not None else None,
            "verdict": self.verdict,
        }


@dataclass
class R2Result:
    billid: str = ""
    rows: List[EstimateRow] = field(default_factory=list)
    total_estimate: Optional[Decimal] = None
    total_actual: Optional[Decimal] = None
    verdict: str = "未知"
    skipped: Optional[str] = None   # no_permission / 等
    missing: List[str] = field(default_factory=list)
    field_semantics: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "billid": self.billid,
            "rows": [r.to_dict() for r in self.rows],
            "total_estimate": str(self.total_estimate) if self.total_estimate is not None else None,
            "total_actual": str(self.total_actual) if self.total_actual is not None else None,
            "verdict": self.verdict,
            "skipped": self.skipped,
            "missing": list(self.missing),
            "field_semantics": dict(self.field_semantics),
        }


def _dec(value: Any) -> Optional[Decimal]:
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
    """取字段显示值。

    两种实测形态：
      A. dict：{value, specialobj:[{name,id}]}（主字段/选择型）
      B. list：[{name,id,...}]（概算明细行，字段直接是对象数组）
    """
    if isinstance(node, list):
        if node and isinstance(node[0], dict):
            name = node[0].get("name")
            if name not in (None, ""):
                return str(name).strip()
            if node[0].get("id") not in (None, ""):
                return str(node[0]["id"]).strip()
        return str(node[0]).strip() if node else ""
    if not isinstance(node, dict):
        # 纯标量（如 field26658="20000.00"）
        return "" if node in (None, "") else str(node).strip()
    objs = node.get("specialobj") or []
    if objs and isinstance(objs[0], dict):
        name = objs[0].get("name")
        if name not in (None, ""):
            return str(name).strip()
    raw = node.get("value")
    if raw not in (None, ""):
        return str(raw).strip()
    return ""


def _read_estimate_rows(client: CubeClient, billid: str) -> List[Dict[str, Any]]:
    """读概算明细表（detail_1）原始行。"""
    nonces = client._new_nonces()
    base = client._card_query(billid, nonces)
    query = {
        **base,
        "tablename": EST_TABLE,
        "groupid": str(EST_GROUPID),
        "iseasy": "0",
    }
    data = client._get_json("/api/cube/new/card/getDetailFields", query)
    rows = data.get("datas") if isinstance(data, dict) else None
    return rows if isinstance(rows, list) else []


def _parse_estimate_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "code": _value(row.get(F_EST_CODE)),
        "name": _value(row.get(F_EST_NAME)),
        "amount": _dec(_value(row.get(F_EST_AMOUNT))),
        "std": _dec(_value(row.get(F_EST_STD))),
        "discount": _dec(_value(row.get(F_EST_DISCOUNT))),
        "qty": _dec(_value(row.get(F_EST_QTY))),
    }


def check_estimate(
    *,
    billid: str,
    items: Sequence[Any],
    storage_state: Optional[Path] = None,
) -> R2Result:
    """R2 主入口：读概算卡片并与本单分项逐项比对。

    Args:
        billid: 概算卡片 billid（如 9955）。
        items: 本单分项（``OrderItem`` 或含 product_code/amount 的 dict）。
        storage_state: Playwright storage_state（None 用默认侦察路径）。
    """
    result = R2Result(billid=str(billid))
    result.field_semantics = {
        "amount": "field26658（实测值推断）",
        "code": "field26645（实测值推断）",
        "inferred": "label 缺失字段按实测值语义推断，非卡片显式标签",
    }

    client = CubeClient(
        storage_state=storage_state,
        layoutid=EST_LAYOUTID,
        mode_id=EST_MODE_ID,
        form_id=EST_FORM_ID,
    )
    try:
        raw_rows = _read_estimate_rows(client, str(billid))
    except CubePermissionError as exc:
        result.skipped = "no_permission"
        result.missing.append(str(exc))
        result.verdict = "未知"
        return result
    except CubeAuthError as exc:
        result.skipped = "session_expired"
        result.missing.append(str(exc))
        result.verdict = "未知"
        return result
    except CubeError as exc:
        result.skipped = "read_failed"
        result.missing.append(str(exc))
        result.verdict = "未知"
        return result

    # fail-closed：空数据不可判为「缺项」（无法区分无权限/不存在/空卡片）
    if not raw_rows:
        result.skipped = "no_data"
        result.missing.append("estimate_card_empty: billid=%s（无权限/不存在/空卡片）" % billid)
        result.verdict = "未知"
        return result

    est_rows = [_parse_estimate_row(r) for r in raw_rows]
    est_by_code = {r["code"]: r for r in est_rows if r["code"]}
    est_by_name = {r["name"]: r for r in est_rows if r["name"]}

    total_est = Decimal("0")
    total_act = Decimal("0")
    for item in items:
        code = getattr(item, "product_code", None) or (
            item.get("product_code") if isinstance(item, dict) else ""
        )
        name = getattr(item, "product_name", None) or (
            item.get("product_name") if isinstance(item, dict) else ""
        )
        amount = getattr(item, "amount", None)
        if amount is None and isinstance(item, dict):
            amount = _dec(item.get("amount"))
        amount = _dec(amount)

        est = est_by_code.get(code) or est_by_name.get(name)
        row = EstimateRow(product_code=code or "【缺失】", product_name=name)
        if est is None:
            row.verdict = "缺项"
            result.missing.append("estimate_missing_code:%s" % (code or name))
            if amount is not None:
                total_act += amount
            result.rows.append(row)
            continue

        row.estimate_amount = est["amount"]
        row.actual_amount = amount
        if est["amount"] is not None and amount is not None:
            row.diff = amount - est["amount"]
            total_est += est["amount"]
            total_act += amount
            row.verdict = "over_budget_warn" if row.diff > 0 else "一致"
        else:
            row.verdict = "未知"
        result.rows.append(row)

    result.total_estimate = total_est if total_est != 0 else None
    result.total_actual = total_act if total_act != 0 else None

    verdicts = {r.verdict for r in result.rows}
    if "over_budget_warn" in verdicts:
        result.verdict = "超概算（提醒级）"
    elif verdicts <= {"一致"}:
        result.verdict = "一致"
    elif "缺项" in verdicts:
        result.verdict = "存在缺项"
    else:
        result.verdict = "未知"
    return result
