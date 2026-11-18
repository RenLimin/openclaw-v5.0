"""增强核查结果 → Markdown 片段渲染（纯函数，无网络）。

遵循 ADR-035 应答契约：结论带【已验证 日期|来源】，降级/快照带 ⚠️ 标注。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from .oa_form import OrderForm
from .ones_obigation import R1Result
from .estimate import R2Result

_DATE = datetime.now().strftime("%Y-%m-%d")


def _table(headers: List[str], rows: List[List[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def render_r1(r1: R1Result) -> str:
    """渲染 R1 履约义务（ONES 实时）。"""
    lines = [
        "### R1 履约义务（ONES 实时）",
        "",
        "**判定：%s**　【已验证 %s｜ONES GraphQL 实时】" % (r1.verdict, _DATE),
        "",
        "> 数据源：%s；查询时点 %s" % (r1.data_source, r1.queried_at),
    ]
    if r1.missing:
        lines += ["", "> ⚠️ 降级/缺失：" + "；".join(r1.missing)]
    lines.append("")
    for p in r1.projects:
        lines.append("#### %s %s" % (p.project_code, p.project_name))
        lines.append("")
        lines.append("项目状态：%s　履约义务判定：**%s**" % (p.project_status or "【缺失】", p.verdict))
        lines.append("")
        if p.records:
            rows = [[r.task_number, r.task_name, r.status, r.owner or "-"] for r in p.records]
            lines.append(_table(["任务号", "任务", "实时状态", "负责人"], rows))
        else:
            lines.append("> 无「项目履约义务」任务记录（可能为其它 issueType，见 ONES 项目）。")
        lines.append("")
    for n in r1.notes:
        lines.append("- %s" % n)
    if not r1.projects:
        lines.append("> ⚠️ 未取到 ONES 实时数据（见上方降级说明），不伪造。")
    return "\n".join(lines)


def render_r2(r2: R2Result) -> str:
    """渲染 R2 概算一致性。"""
    lines = [
        "### R2 概算一致性",
        "",
        "**判定：%s**　【已验证 %s｜OA 卡片 billid %s 只读】" % (r2.verdict, _DATE, r2.billid),
        "",
    ]
    if r2.skipped:
        lines.append("> ⚠️ 已跳过（%s）：%s" % (r2.skipped, "；".join(r2.missing) or "无"))
        return "\n".join(lines)
    rows = []
    for row in r2.rows:
        rows.append([
            row.product_code, row.product_name or "-",
            row.estimate_amount if row.estimate_amount is not None else "-",
            row.actual_amount if row.actual_amount is not None else "-",
            ("%+s" % row.diff) if row.diff is not None else "-",
            row.verdict,
        ])
    lines.append(_table(["产品编码", "名称", "概算", "本单", "差异", "判定"], rows))
    lines.append("")
    te = r2.total_estimate if r2.total_estimate is not None else "-"
    ta = r2.total_actual if r2.total_actual is not None else "-"
    lines.append("合计：概算 %s　本单 %s" % (te, ta))
    lines += ["", "> 口径：**允许销售额超概算，超出仅提醒**（不构成退回项）。"]
    if r2.missing:
        lines += ["", "> ⚠️ 缺项：" + "；".join(r2.missing)]
    return "\n".join(lines)


def render_enhance(form: OrderForm, r1: R1Result, r2: R2Result) -> str:
    """完整「增强核查」章节（并入审查报告）。"""
    out = [
        "## 增强核查（履约义务 / 概算一致性）",
        "",
        "> 单据：OA requestid %s　workflowid 757（销售合同审核流程）" % form.request_id,
        "> 最终用户：%s　合同甲方：%s　概算卡片：%s" % (
            form.end_user or "【缺失】",
            form.contract_party_a or "【缺失/留空】",
            form.estimate_billid or "【缺失】",
        ),
        "",
        render_r1(r1),
        "",
        render_r2(r2),
        "",
        "> ⚠️ 数据源为查询时点快照（ONES 实时 / BDMS 202606 / OA 卡片），可能过期。",
    ]
    return "\n".join(out)
