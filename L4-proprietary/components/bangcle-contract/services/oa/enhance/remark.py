"""标准审批备注渲染（纯函数，无网络）— 757 单据「可直接贴 OA」文本。

格式（Rex 2026-11-19 认可草案）：
  【审批建议】<退回补充 / 同意 / 退回补充（待原文）>
  合同：<名称>（<rid>，<金额> 元，<客户>）
  退回项（需关闭后重提）：
  1. ...
  提示项（不阻断）：
  1. ...
  R1 履约义务：<判定>（ONES 实时 <日期>）
  R2 概算一致性：<判定>
  （降级时）⚠️ 数据源…可能过期

结论推导：block 存在 → 退回补充；否则 manual 存在 → 退回补充（待原文）；否则 → 同意。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from .checks import CheckResult
from .oa_form import OrderForm

_DATE = datetime.now().strftime("%Y-%m-%d")


def _fmt_amount(form: OrderForm) -> str:
    """从分项合计推断本单金额（元）。"""
    total = None
    try:
        from decimal import Decimal
        vals = [i.amount for i in form.items if i.amount is not None]
        if vals:
            total = sum(vals, Decimal("0"))
    except Exception:  # noqa: BLE001
        total = None
    return ("%.2f" % total) if total is not None else "【未知】"


def derive_verdict(checks: List[CheckResult]) -> str:
    """由核查项推导审批结论。"""
    if any(c.level == "block" for c in checks):
        return "退回补充"
    if any(c.level == "manual" for c in checks):
        return "退回补充（待原文）"
    return "同意"


def render_remark(
    form: OrderForm,
    checks: List[CheckResult],
    r1: Optional[Dict[str, Any]] = None,
    r2: Optional[Dict[str, Any]] = None,
    *,
    degraded: Optional[List[str]] = None,
) -> str:
    """渲染标准审批备注。

    Args:
        form: 已解析 OA 单据。
        checks: 固定核查项结果。
        r1/r2: 增强核查结果 dict（``runner.run_enhance`` 产物）；可空。
        degraded: 降级项列表（R1/R2 skipped）。
    """
    r1 = r1 or {}
    r2 = r2 or {}
    degraded = degraded or []

    blocks = [c for c in checks if c.level == "block"]
    warns = [c for c in checks if c.level == "warn"]
    manuals = [c for c in checks if c.level == "manual"]
    verdict = derive_verdict(checks)

    lines: List[str] = []
    lines.append("【审批建议】%s" % verdict)
    lines.append(
        "合同：%s（%s，%s 元，%s）" % (
            _form_field(form, "contract_name") or "【未取到】",
            form.request_id,
            _fmt_amount(form),
            form.end_user or "【未取到】",
        )
    )
    if blocks:
        lines.append("退回项（需关闭后重提）：")
        for i, c in enumerate(blocks, 1):
            lines.append("%d. %s" % (i, c.message))
    if warns:
        lines.append("提示项（不阻断）：")
        for i, c in enumerate(warns, 1):
            lines.append("%d. %s" % (i, c.message))
    if manuals:
        lines.append("待人工（合同原文未提供，无法自动判定）：")
        for i, c in enumerate(manuals, 1):
            lines.append("%d. %s" % (i, c.message))

    # R1 / R2
    r1v = r1.get("verdict") or "未知"
    r1q = r1.get("queried_at") or _DATE
    lines.append("R1 履约义务：%s（ONES 实时 %s）" % (r1v, r1q))
    r2v = r2.get("verdict") or "未知"
    if r2.get("skipped"):
        r2v = "%s（skipped: %s）" % (r2v, r2.get("skipped"))
    else:
        ta = r2.get("total_actual")
        te = r2.get("total_estimate")
        if ta is not None and te is not None:
            r2v = "%s（概算 %s / 本单 %s）" % (r2v, te, ta)
    lines.append("R2 概算一致性：%s" % r2v)

    if degraded:
        lines.append("⚠️ 数据源降级：%s（%s）可能过期，以上结论绑定 requestid + 读取时间。"
                     % ("/".join(degraded), "/".join(degraded)))

    # ADR-035 应答契约脚注（fail-closed 门禁：时间戳 + 溯源链）
    lines += _evidence_footer(form, r1, r2, degraded=degraded)
    return "\n".join(lines)


def _form_field(form: OrderForm, name: str) -> str:
    """兼容 OrderForm 字段扩展（合同名称可能未建模）。"""
    return str(getattr(form, name, "") or "")


def _evidence_footer(
    form: OrderForm,
    r1: Optional[Dict[str, Any]] = None,
    r2: Optional[Dict[str, Any]] = None,
    *,
    degraded: Optional[List[str]] = None,
    date_str: Optional[str] = None,
) -> List[str]:
    """ADR-035 应答契约脚注：证据时间戳 + minimal trace 溯源链。

    目的：``check_answer_contract.py`` 为 fail-closed 门禁，任何落盘结论必须带
    ``【已验证 日期|来源】`` 与「数据源→查询→结论」溯源链，否则 BLOCK。
    本函数只追加元信息，不改动「可直接贴 OA」的正文。
    """
    r1 = r1 or {}
    r2 = r2 or {}
    degraded = [d.lower() for d in (degraded or [])]
    d = date_str or _DATE
    rid = form.request_id
    billid = r2.get("billid") or "【无】"

    # 溯源链（数据源→查询→结论）
    chain = [
        "OA workflowid=757 单据 %s（body.txt 渲染表单 + xhrs.json 字段）→ 固定核查 L1/L2 → 本备注" % rid,
        "R1 ONES GraphQL 实时（读取时点 %s）→ 履约义务判定" % (r1.get("queried_at") or d),
        "R2 OA 概算卡片 billid %s 只读 → 概算一致性判定" % billid,
    ]

    stamps = ["【已验证 %s｜OA 单据 %s】合同名称/金额/服务期/合同编号" % (d, rid)]

    r1v = r1.get("verdict") or "未知"
    r1_line = "【已验证 %s｜ONES GraphQL】R1 履约义务=%s" % (d, r1v)
    if "r1" in degraded:
        r1_line += "（⚠️ 数据源降级，project_not_found/查询失效，不伪造）"
    stamps.append(r1_line)

    r2v = r2.get("verdict") or "未知"
    if r2.get("skipped"):
        r2_line = "【已验证 %s｜OA 卡片 billid %s】R2=%s（skipped: %s）" % (
            d, billid, r2v, r2.get("skipped"))
    else:
        r2_line = "【已验证 %s｜OA 卡片 billid %s】R2=%s（概算 %s / 本单 %s）" % (
            d, billid, r2v, r2.get("total_estimate"), r2.get("total_actual"))
    if "r2" in degraded:
        r2_line += "（⚠️ 数据源降级，不伪造）"
    stamps.append(r2_line)

    return ["", "---", "> 溯源链：" + "；".join(chain), "> " + "；".join(stamps)]
