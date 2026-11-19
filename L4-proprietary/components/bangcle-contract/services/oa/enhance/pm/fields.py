"""三流程字段映射（权威标签，取自 OA loadForm.tableInfo.*.fieldinfomap）。

实测单据：916=886453、815=886362、820=886314（2026-11-19）。
字段 id 以 OA 返回的 ``fieldinfomap`` 为准，**禁止**凭 fieldname 猜。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

WF_SALES_ORDER = "wf_916"        # 销售合同下单流程（数据审核触发）
WF_ADVANCE = "wf_815"            # 提前实施需求申请流程
WF_POC = "wf_820"                # PoC需求申请流程

# 「合同审批流程→」仅 916 有；815/820 实测无此字段
APPROVAL_FLOW_FIELD = "field13682"


@dataclass(frozen=True)
class FieldMap:
    workflow_id: str
    label: str
    applicant: str
    apply_time: str
    urgency: str
    project_code: str
    customer: str
    final_user: str
    final_user_text: str
    pm: str
    region_manager: str = ""          # 项目管理部区域经理（815/820）
    approval_flow: str = ""           # 916 独有
    contract_name: str = ""
    contract_no: str = ""
    estimate_name: str = ""
    service_start: str = ""
    service_end: str = ""
    amount: str = ""
    archive_time: str = ""            # 合同归档时间（916）
    expect_sign_date: str = ""        # 预计合同签约日期（815/820）
    item_table: str = "detail_1"
    item_category: str = ""           # 产品服务类别
    item_type: str = ""               # 类别
    item_name: str = ""               # 最终产品或服务名称
    item_code: str = ""               # 产品服务编码
    item_qty: str = ""
    item_unit: str = ""
    item_amount: str = ""
    item_std_price: str = ""
    item_discount: str = ""
    item_sow: str = ""                # 标准实施内容
    item_custom: str = ""             # 是否定制
    field_semantics: Dict[str, str] = field(default_factory=dict)


_MAPS: Dict[str, FieldMap] = {
    WF_SALES_ORDER: FieldMap(
        workflow_id=WF_SALES_ORDER, label="销售合同下单流程（数据审核触发）",
        applicant="field13637", apply_time="field13638", urgency="field29631",
        project_code="field29561", customer="field13668", final_user="field29612",
        final_user_text="field13678", pm="field13673",
        approval_flow=APPROVAL_FLOW_FIELD,
        contract_name="field13643", contract_no="field13652",
        estimate_name="field31030", service_start="field20270", service_end="field20271",
        amount="field13648", archive_time="field13653",
        item_category="field29773", item_type="field29774", item_name="field29775",
        item_code="field13675", item_qty="field13665", item_unit="field13657",
        item_amount="field13667", item_std_price="field26783", item_discount="field26780",
        item_sow="field26781", item_custom="field13666",
    ),
    WF_ADVANCE: FieldMap(
        workflow_id=WF_ADVANCE, label="提前实施需求申请流程",
        applicant="field12968", apply_time="field12971", urgency="field29630",
        project_code="field29560", customer="field12978", final_user="field29609",
        final_user_text="field32754", pm="field13220", region_manager="field13219",
        estimate_name="field26674", expect_sign_date="field12977",
        item_category="field29770", item_type="field29771", item_name="field29953",
        item_code="field13255", item_qty="field12984", item_unit="field26903",
        item_sow="field26905", item_custom="field26904",
    ),
    WF_POC: FieldMap(
        workflow_id=WF_POC, label="PoC需求申请流程",
        applicant="field13057", apply_time="field13060", urgency="field29629",
        project_code="field29562", customer="field13062", final_user="field29608",
        final_user_text="field32752", pm="field13102", region_manager="field13101",
        amount="field13086", expect_sign_date="field13085",
        item_category="field29767", item_type="field29768", item_name="field29954",
        item_code="field13136", item_qty="field13098", item_unit="field26932",
        item_sow="field26934", item_custom="field26933",
    ),
}

# 流程标题关键词 → workflow_id（用于从 OA 标题推断，标题口径见 KB EXP-20261112-001）
_TITLE_HINTS: Tuple[Tuple[str, str], ...] = (
    ("销售合同下单", WF_SALES_ORDER),
    ("提前实施需求", WF_ADVANCE),
    ("PoC需求申请", WF_POC),
)


class FieldMapError(ValueError):
    """未知流程。"""


def resolve(workflow_id: str) -> FieldMap:
    """按 workflow_id 取字段映射；未知抛错（fail-closed，不猜）。"""
    try:
        return _MAPS[workflow_id]
    except KeyError:
        raise FieldMapError(
            "未知流程 %r（支持：%s）" % (workflow_id, ", ".join(sorted(_MAPS)))
        ) from None


def infer_from_title(title: str) -> Optional[str]:
    """从 OA 单据标题推断 workflow_id；无法推断返回 None。"""
    for hint, wf in _TITLE_HINTS:
        if hint in (title or ""):
            return wf
    return None
