"""OA 单据解析（只读）— xhrs.json → 统一 ProjectOrder。

数据源：``oa_workflow_ones.py --capture <rid>`` 落盘的 ``xhrs.json``。
  - ``reqform/loadForm`` → maindata（最终客户/客户/合同/概算/PM/合同审批流程）
  - ``detailData``      → detail_1.rowDatas（产品分项）

实测口径（2026-11-19，886453/886362/886314）：
  - 同一单可能有多个 loadForm 响应，**必须取 body 最大**者
    （886453：402542 字节 vs injectDev/loadFormDevFileList 12 字节 0 键）。
  - rowDatas 是 dict（row_0…），非 list。
  - 浏览框/选择型字段：优先 specialobj[0].name，否则 value。
本模块只读本地 JSON，不发起网络请求。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .fields import FieldMap, infer_from_title, resolve

DETAIL_TABLE = "detail_1"


class PmAssetError(ValueError):
    """单据解析失败（缺文件 / 结构异常）；fail-closed，不伪造。"""


def _value(node: Any) -> str:
    """取节点标量值（与 oa_form._value 同语义：浏览框优先 name）。"""
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


def _dec(text: str) -> str:
    """金额归一：去千分位；无法解析返回原串（不静默变 0）。"""
    if not text:
        return ""
    t = str(text).strip().replace(",", "")
    try:
        float(t)
        return t
    except ValueError:
        return str(text).strip()


@dataclass
class OrderItem:
    """本单产品分项。"""

    keyid: str = ""
    line_category: str = ""      # 产品服务类别
    line_type: str = ""          # 类别
    product_name: str = ""       # 最终产品或服务名称
    product_code: str = ""       # 产品服务编码
    qty: str = ""
    unit: str = ""
    amount: str = ""             # 916 有
    std_price: str = ""          # 916 有
    discount: str = ""           # 916 有
    sow: str = ""                # 标准实施内容
    custom: str = ""             # 是否定制

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class ProjectOrder:
    """统一单模型（916/815/820 同构）。"""

    request_id: str = ""
    workflow_id: str = ""
    title: str = ""
    applicant: str = ""
    apply_time: str = ""
    urgency: str = ""
    project_code: str = ""
    customer: str = ""
    final_user: str = ""
    contract_no: str = ""
    contract_name: str = ""
    approval_flow: str = ""       # 916 独有：合同审批流程→ 显示名
    approval_flow_rid: str = ""   # 916 独有：specialobj id = 757 requestid
    estimate_name: str = ""
    service_start: str = ""
    service_end: str = ""
    amount: str = ""
    pm: str = ""
    region_manager: str = ""
    items: List[OrderItem] = field(default_factory=list)
    field_semantics: Dict[str, str] = field(default_factory=dict)

    @property
    def product_codes(self) -> List[str]:
        return [i.product_code for i in self.items if i.product_code]

    def to_dict(self) -> Dict[str, Any]:
        d = dict(self.__dict__)
        d["items"] = [i.to_dict() for i in self.items]
        return d


def _pick_largest(xhrs: List[Dict[str, Any]], keyword: str) -> Optional[dict]:
    """取 URL 含 keyword 且 body 最大的响应（已解析 JSON）。"""
    best: Optional[dict] = None
    best_len = -1
    for item in xhrs:
        url = str(item.get("url") or "")
        if keyword not in url:
            continue
        body = item.get("body")
        if not isinstance(body, str) or not body.strip():
            continue
        if len(body) <= best_len:
            continue
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            continue
        best, best_len = parsed, len(body)
    return best


def _maindata(obj: Optional[dict]) -> Dict[str, Any]:
    return ((obj or {}).get("maindata") or {}) if isinstance(obj, dict) else {}


def _detail(obj: Optional[dict], table: str) -> Dict[str, Any]:
    d = (obj or {}).get(table) or {}
    rows = d.get("rowDatas") or {}
    return rows if isinstance(rows, dict) else {}


def _approval_rid(node: Any) -> str:
    """合同审批流程→ 的 requestid：specialobj[0].id。"""
    if not isinstance(node, dict):
        return ""
    objs = node.get("specialobj") or []
    for o in objs:
        if isinstance(o, dict) and o.get("id"):
            return str(o["id"]).strip()
    return ""


def parse(raw_dir: Path, request_id: str, workflow_id: str,
          title: str = "") -> ProjectOrder:
    """解析已捕获的 OA 单据 XHR 原始目录。

    Args:
        raw_dir: ``oa_workflow_ones.py --capture`` 的 raw 根目录（其下 ``<rid>/xhrs.json``）。
        request_id: OA requestid。
        workflow_id: wf_916 / wf_815 / wf_820。
        title: OA 单据标题（可空；用于语义标注与推断兜底）。

    Raises:
        PmAssetError: 缺 xhrs.json / 缺 loadForm（fail-closed）。
    """
    fm: FieldMap = resolve(workflow_id)
    path = Path(raw_dir) / request_id / "xhrs.json"
    if not path.exists():
        raise PmAssetError("未找到单据原始数据: %s" % path)
    try:
        xhrs = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PmAssetError("xhrs.json 解析失败: %s" % exc) from exc

    main_raw = _pick_largest(xhrs, "reqform/loadForm")
    if main_raw is None:
        raise PmAssetError("缺 loadForm 响应: %s" % request_id)
    detail_raw = _pick_largest(xhrs, "detailData")

    md = _maindata(main_raw)
    o = ProjectOrder(request_id=request_id, workflow_id=workflow_id, title=title)

    o.applicant = _value(md.get(fm.applicant))
    o.apply_time = _value(md.get(fm.apply_time))
    o.urgency = _value(md.get(fm.urgency))
    o.project_code = _value(md.get(fm.project_code))
    o.customer = _value(md.get(fm.customer))
    o.final_user = _value(md.get(fm.final_user)) or _value(md.get(fm.final_user_text))
    o.pm = _value(md.get(fm.pm))
    o.region_manager = _value(md.get(fm.region_manager)) if fm.region_manager else ""
    if fm.contract_name:
        o.contract_name = _value(md.get(fm.contract_name))
    if fm.contract_no:
        o.contract_no = _value(md.get(fm.contract_no))
    if fm.approval_flow:
        node = md.get(fm.approval_flow)
        o.approval_flow = _value(node)
        o.approval_flow_rid = _approval_rid(node)
    if fm.estimate_name:
        o.estimate_name = _value(md.get(fm.estimate_name))
    if fm.service_start:
        o.service_start = _value(md.get(fm.service_start))
    if fm.service_end:
        o.service_end = _value(md.get(fm.service_end))
    if fm.amount:
        o.amount = _dec(_value(md.get(fm.amount)))

    rows = _detail(detail_raw, fm.item_table)
    for key in sorted(rows.keys()):
        row = rows.get(key) or {}
        o.items.append(OrderItem(
            keyid=str(row.get("keyid") or key),
            line_category=_value(row.get(fm.item_category)) if fm.item_category else "",
            line_type=_value(row.get(fm.item_type)) if fm.item_type else "",
            product_name=_value(row.get(fm.item_name)) if fm.item_name else "",
            product_code=_value(row.get(fm.item_code)) if fm.item_code else "",
            qty=_value(row.get(fm.item_qty)) if fm.item_qty else "",
            unit=_value(row.get(fm.item_unit)) if fm.item_unit else "",
            amount=_dec(_value(row.get(fm.item_amount))) if fm.item_amount else "",
            std_price=_dec(_value(row.get(fm.item_std_price))) if fm.item_std_price else "",
            discount=_value(row.get(fm.item_discount)) if fm.item_discount else "",
            sow=_value(row.get(fm.item_sow)) if fm.item_sow else "",
            custom=_value(row.get(fm.item_custom)) if fm.item_custom else "",
        ))

    o.field_semantics = {
        "source": "loadForm.maindata + detailData.%s.rowDatas（OA 只读捕获）" % fm.item_table,
        "loadForm_bytes": str(len(json.dumps(main_raw, ensure_ascii=False))),
        "approval_flow_field": fm.approval_flow or "（本流程无此字段）",
        "inferred_workflow": infer_from_title(title) or "",
    }
    return o
