"""风险判定（纯函数，无网络无时钟）。

风险码与文本模板见 DESIGN-DETAIL §7。触发口径全部来自实测批注反推：
- 886404「不允许同最终用户同产品/服务存在多个未关联签约合同的提前实施项目」
- 886362「立项前，请与营销侧明确合同预计归档日期，以及是否追认提前实施交付内容」
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from .order import ProjectOrder
from .ones_refs import RefProject


@dataclass
class Risk:
    code: str
    level: str          # 必注 / 提示
    text: str

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


_RISK_ORDER = (
    "pm_unassigned",
    "multi_project_same_product",
    "approval_risk",
    "approval_no_permission",
    "archive_date",
    "retroactive",
)


def _dedup(items: Sequence[str]) -> List[str]:
    out: List[str] = []
    for i in items:
        if i and i not in out:
            out.append(i)
    return out


def assess(
    order: ProjectOrder,
    refs: Sequence[RefProject],
    notes: Optional[Any] = None,
) -> List[Risk]:
    """评估风险注。notes 为 ApprovalNotes（P4 接入；可为 None）。"""
    risks: List[Risk] = []

    # 1) 待分配 PM
    if not (order.pm or "").strip():
        risks.append(Risk(
            "pm_unassigned", "必注",
            "待分配项目经理（OA 项目经理字段为空，需项目管理部指派）",
        ))

    # 2) 多项目隔离（同最终用户 + 同产品/服务 ≥2 项目）
    if len(refs) >= 2:
        codes = _dedup([r.code for r in refs])
        if len(codes) >= 2:
            shared = _shared_products(refs)
            scope = "提前实施项目" if order.workflow_id == "wf_815" else "项目"
            if shared:
                detail = "（同产品/服务：%s）" % "、".join(shared)
            else:
                detail = ""
            risks.append(Risk(
                "multi_project_same_product", "必注",
                "不允许同最终用户同产品/服务存在多个未关联签约合同的%s%s；"
                "请责任销售明确本申请与已有项目的区别（如增购等）"
                % (scope, detail),
            ))

    # 3) 757 异常备注 / 无权限（P4）
    if notes is not None:
        degraded = getattr(notes, "degraded", None)
        if degraded:
            # 无权限用固定口径文案（DESIGN-DETAIL §7），不拼接底层异常原文；
            # 其余读取失败（会话/签名拦截等）保留原因便于人工定位。
            if "无权限" in degraded:
                risks.append(Risk(
                    "approval_no_permission", "提示",
                    "合同审批流程（%s）无权限读取，需人工查看（链接见单据）"
                    % (order.approval_flow or order.approval_flow_rid),
                ))
            else:
                risks.append(Risk(
                    "approval_no_permission", "提示",
                    "合同审批流程（%s）无法读取：%s，需人工查看" % (
                        order.approval_flow or order.approval_flow_rid, degraded),
                ))
        else:
            levels = getattr(notes, "risk_levels", None) or []
            hint = getattr(notes, "verdict_hint", "") or ""
            if any(lv in ("重点复核", "需补充", "退回") for lv in levels):
                risks.append(Risk(
                    "approval_risk", "必注",
                    "合同审批流程存在异常备注（%s%s），请立项前复核"
                    % ("/".join(_dedup(levels)), ("；总体建议：" + hint) if hint else ""),
                ))

    # 4) 合同归档日期未明确（815/916）
    if order.workflow_id in ("wf_815", "wf_916") and not (order.archive_time or "").strip():
        risks.append(Risk(
            "archive_date", "提示",
            "立项前，请与营销侧明确合同预计归档日期",
        ))

    # 5) 是否追认提前实施（815）
    if order.workflow_id == "wf_815":
        risks.append(Risk(
            "retroactive", "提示",
            "是否追认提前实施交付内容",
        ))

    # 稳定排序（按 _RISK_ORDER）
    rank = {c: i for i, c in enumerate(_RISK_ORDER)}
    risks.sort(key=lambda r: rank.get(r.code, 99))
    return risks


def _shared_products(refs: Sequence[RefProject]) -> List[str]:
    """多个项目共同出现的产品编码/名称（用于隔离提示）。"""
    if len(refs) < 2:
        return []
    sets = []
    for r in refs:
        s = set(r.matched_products or [])
        # 无命中时退化为项目状态特征，避免误报同产品
        if not s:
            s = {r.status_label}
        sets.append(s)
    common = set.intersection(*sets) if sets else set()
    return sorted(x for x in common if x)


def render_risks(risks: Sequence[Risk]) -> str:
    """风险注文本（多条换行；无则空串）。"""
    return "\n".join("%s：%s" % (r.level, r.text) for r in risks)
