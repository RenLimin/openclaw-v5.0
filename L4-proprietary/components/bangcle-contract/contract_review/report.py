"""《合同智能审查报告》生成 — DETAIL §5 / PRD。

汇总：风险（L3 RiskReport.to_dict）+ product-kb 满足度（KbReview），
产出 Markdown 与 Excel 两种报告。

安全契约：
- 法条依据仅来自 L3 受控规则库（finding.law），报告不自行造法条
- 固定免责声明：决策由人做出、低置信需人工复核
- 报告只写本地文件路径，不对外发送
"""

from __future__ import annotations

import csv
import io
import os
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional

from .kb_match import KbReview

DISCLAIMER = (
    "免责声明：本报告由程序自动生成，仅提供合同条款的解析、比对与风险提示，"
    "不构成法律意见。审批、签署、驳回等最终决策须由授权人员作出；"
    "语义判断类结果需人工复核。法条依据来自受控规则库，供参考。"
)

SATISFACTION_LABEL = {
    "satisfied": "满足（标的均在售且在折扣红线内）",
    "partial": "部分满足（存在低置信/待人工确认项）",
    "unsatisfied": "不满足（存在未匹配/停售/低于红线项）",
}


def _risk_table_md(findings: List[Dict[str, Any]]) -> str:
    if not findings:
        return "（无风险项）\n"
    lines = [
        "| 编号 | 类别 | 检查项 | 状态 | 风险 | 法条 |",
        "|---|---|---|---|---|---|",
    ]
    status_label = {"pass": "通过", "warning": "提示", "fail": "不通过"}
    for f in findings:
        lines.append(
            "| %s | %s | %s | %s | %s | %s |"
            % (f.get("id", ""), f.get("category", ""), f.get("item", ""),
               status_label.get(f.get("status", ""), f.get("status", "")),
               f.get("risk", ""), f.get("law", ""))
        )
    return "\n".join(lines) + "\n"


def _kb_table_md(kb: KbReview) -> str:
    if not kb.referenced:
        return "> ⚠️ 未做产品参照（product-kb 不可达），满足度无法判定。\n"
    if not kb.items:
        return "> ⚠️ 未从合同提取到可参照标的，满足度无法判定，需人工核对。\n"
    lines = [
        "| 标的 | 匹配 | 得分 | 产品 | SKU | 提示 |",
        "|---|---|---|---|---|---|",
    ]
    for r in kb.items:
        lines.append(
            "| %s | %s | %.2f | %s | %s | %s |"
            % (r.input_name, "✅" if r.matched else "❌", r.score,
               r.product or "—", r.sku or "—", r.alert or "")
        )
    return "\n".join(lines) + "\n"


def build_markdown(*, contract_ref: str, source: str,
                   risk: Dict[str, Any], kb: KbReview,
                   ocr_method: Optional[str] = None,
                   ocr_confidence: Optional[float] = None) -> str:
    """构建 Markdown 报告全文（纯函数，返回字符串）。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    md = [
        "# 合同智能审查报告",
        "",
        "| 项 | 值 |",
        "|---|---|",
        "| 合同引用 | %s |" % contract_ref,
        "| 来源 | %s |" % source,
        "| 生成时间 | %s |" % now,
        "| 综合风险 | **%s** |" % str(risk.get("overall_risk", "unknown")),
        "| 产品满足度 | **%s** |" % SATISFACTION_LABEL.get(kb.satisfaction, kb.satisfaction),
        "",
        "## 一、风险扫描",
        "",
        "扫描规则：受控规则库（%d 条）。" % len(risk.get("findings", [])) if isinstance(risk.get("findings"), list) else "",
        "",
    ]
    if ocr_method:
        md += ["数字化方式：%s" % ocr_method, ""]
        if ocr_confidence is not None:
            md += ["OCR 置信度：%.2f" % ocr_confidence, ""]
    md += [_risk_table_md(risk.get("findings", [])), ""]
    md += ["## 二、产品/服务参照", "", _kb_table_md(kb), ""]
    md += ["## 三、免责声明", "", DISCLAIMER, ""]
    return "\n".join(md)


def build_excel(*, contract_ref: str, source: str,
                risk: Dict[str, Any], kb: KbReview, out_path: str) -> str:
    """生成 Excel 报告（openpyxl），返回落盘路径。

    结构：Sheet1 概览；Sheet2 风险明细；Sheet3 KB 匹配。
    openpyxl 不可用时抛 ImportError（由 CLI 层转为清晰错误）。
    """
    import openpyxl
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "概览"
    bold = Font(bold=True)
    rows = [
        ("合同智能审查报告", ""),
        ("合同引用", contract_ref),
        ("来源", source),
        ("生成时间", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        ("综合风险", risk.get("overall_risk", "")),
        ("产品满足度", SATISFACTION_LABEL.get(kb.satisfaction, kb.satisfaction)),
        ("数字化方式", ""),
        ("免责声明", DISCLAIMER),
    ]
    for i, (k, v) in enumerate(rows, start=1):
        c1, c2 = ws.cell(row=i, column=1, value=k), ws.cell(row=i, column=2, value=v)
        c1.font = bold
    ws.column_dimensions[get_column_letter(1)].width = 18
    ws.column_dimensions[get_column_letter(2)].width = 80

    ws2 = wb.create_sheet("风险明细")
    ws2.append(["编号", "类别", "检查项", "状态", "风险", "法条"])
    for f in risk.get("findings", []):
        ws2.append([f.get("id", ""), f.get("category", ""), f.get("item", ""),
                    f.get("status", ""), f.get("risk", ""), f.get("law", "")])
    for col in range(1, 7):
        ws2.cell(row=1, column=col).font = bold

    ws3 = wb.create_sheet("KB匹配")
    ws3.append(["标的", "匹配", "得分", "产品", "SKU", "提示"])
    if kb.referenced:
        for r in kb.items:
            ws3.append([r.input_name, "是" if r.matched else "否",
                        r.score, r.product or "", r.sku or "", r.alert or ""])
    else:
        ws3.append(["", "", "", "", "", "未做参照（product-kb 不可达）"])
    for col in range(1, 7):
        ws3.cell(row=1, column=col).font = bold

    out_path = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    wb.save(out_path)
    return out_path


def write_markdown(*, contract_ref: str, source: str,
                   risk: Dict[str, Any], kb: KbReview, out_path: str,
                   ocr_method: Optional[str] = None,
                   ocr_confidence: Optional[float] = None) -> str:
    """写 Markdown 报告到文件，返回落盘路径。"""
    md = build_markdown(contract_ref=contract_ref, source=source,
                        risk=risk, kb=kb, ocr_method=ocr_method,
                        ocr_confidence=ocr_confidence)
    out_path = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(md)
    return out_path
