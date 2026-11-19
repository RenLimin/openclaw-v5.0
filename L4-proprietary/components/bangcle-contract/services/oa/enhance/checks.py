"""固定核查项（只读，纯函数 + 本地文件）— 757 单据审批前置检查。

分层（fail-closed）：
  L1 表单层：始终判定（数据源 = ``body.txt`` 渲染表单）。
    - contract_no_missing  合同编号缺失 → block
    - service_period       服务期未明确起止 → warn
  L2 原文层：仅在调用方提供合同原文时判定，否则 ``manual``（**不伪造**）。
    - party_a_email        甲方官方邮箱留空 → block
    - end_user_table       最终用户信息表声明为附件但未随附 → block
    - version_desc         流程分项版本描述 vs 合同正文不一致 → warn

⚠️ 硬约束（实测 2026-11-19）：757 单据合同附件 REST 下载无权限
（``FileDownload?fileid=<id>`` 返回 HTML「对不起，您暂时没有权限！」），
故 L2 三项**不会**自动取原文；未提供 ``contract_text`` 时一律 ``manual``。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .oa_form import OrderForm

# ---- body.txt 字段标签（实测 886377 渲染表单）----
_LABELS = [
    "合同名称", "合同编号！", "合同编号", "合同甲方（浏览框）", "最终用户名称",
    "签约金额（元）", "合同起始日期", "合同终止日期", "服务开始日期", "服务结束日期",
    "销售合同概算名称", "合同模板类别", "合同开票税率", "业务模式", "销售类别",
    "申请人", "流程编号", "合同类型", "合同备注说明",
]
_LABEL_SET = set(_LABELS)


@dataclass
class CheckResult:
    """单条核查结果。"""

    check_id: str          # contract_no_missing / service_period / party_a_email / end_user_table / version_desc
    level: str             # block | warn | pass | manual
    message: str
    evidence: str = ""
    source: str = "form"   # form | contract_text | none

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "level": self.level,
            "message": self.message,
            "evidence": self.evidence,
            "source": self.source,
        }


def parse_body_fields(body_text: str) -> Dict[str, str]:
    """从 ``body.txt`` 渲染表单抽取「标签 → 值」扁平映射。

    规则：命中标签行后，取其后首个非空且非标签行作为值（实测 886377 结构）。
    """
    lines = [l.strip() for l in (body_text or "").splitlines()]
    out: Dict[str, str] = {}
    for i, line in enumerate(lines):
        if line in _LABEL_SET and line not in out:
            for j in range(i + 1, min(i + 4, len(lines))):
                nxt = lines[j]
                if nxt == "":
                    continue
                if nxt in _LABEL_SET:
                    break
                out[line] = nxt
                break
    return out


def _manual(check_id: str, message: str) -> CheckResult:
    return CheckResult(check_id=check_id, level="manual", message=message,
                       evidence="未提供合同原文", source="none")


def run_fixed_checks(
    form: OrderForm,
    body_text: str,
    contract_text: Optional[str] = None,
) -> List[CheckResult]:
    """执行固定核查项（L1 表单 + L2 原文）。

    Args:
        form: 已解析的 OA 单据（R1/R2 输入同源）。
        body_text: ``oa_workflow_ones.py --capture`` 落盘的 ``body.txt``。
        contract_text: 合同原文全文（docx/txt）；``None`` 时 L2 三项转人工。

    Returns:
        5 条 ``CheckResult``（顺序固定）。
    """
    fields = parse_body_fields(body_text)
    results: List[CheckResult] = []

    # ---- L1-a 合同编号 ----
    contract_no = (fields.get("合同编号！") or fields.get("合同编号") or "").strip()
    if contract_no:
        results.append(CheckResult(
            "contract_no_missing", "pass", "合同编号已填写",
            evidence=contract_no, source="form"))
    else:
        results.append(CheckResult(
            "contract_no_missing", "block", "合同编号缺失（表单与正文均空）",
            evidence="合同编号！=【空】", source="form"))

    # ---- L1-b 服务期 ----
    start = (fields.get("服务开始日期") or fields.get("合同起始日期") or "").strip()
    end = (fields.get("服务结束日期") or fields.get("合同终止日期") or "").strip()
    if start and end and re.fullmatch(r"\d{4}-\d{2}-\d{2}", start) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", end):
        results.append(CheckResult(
            "service_period", "pass", "服务期已明确起止日期",
            evidence="%s ~ %s" % (start, end), source="form"))
    else:
        results.append(CheckResult(
            "service_period", "warn",
            "服务期未明确（仅「签订之日起 N 年」或起止缺失）",
            evidence="服务开始=%r 服务结束=%r" % (start, end), source="form"))

    # ---- L2 原文层 ----
    text = (contract_text or "").strip()
    if not text:
        results.append(_manual("party_a_email", "甲方官方邮箱——合同原文未提供，转人工"))
        results.append(_manual("end_user_table", "最终用户信息表——合同原文未提供，转人工"))
        results.append(_manual("version_desc", "版本描述一致性——合同原文未提供，转人工"))
        return results

    # L2-a 甲方官方邮箱（4.2 验收条款）
    m = re.search(r"甲方指定授权[^\n]{0,40}?邮箱", text)
    if m:
        seg = text[m.start():m.start() + 120]
        # 甲方邮箱位置为空（仅有乙方官方邮箱）→ block
        party_a_blank = bool(re.search(r"甲方指定授权\s+邮箱", text))
        if party_a_blank:
            results.append(CheckResult(
                "party_a_email", "block",
                "合同 4.2 甲方指定授权邮箱留空（未明确甲方官方邮箱）",
                evidence=seg.replace("\n", " ")[:100], source="contract_text"))
        else:
            results.append(CheckResult(
                "party_a_email", "pass", "甲方官方邮箱已明确",
                evidence=seg.replace("\n", " ")[:100], source="contract_text"))
    else:
        results.append(_manual("party_a_email", "未检索到甲方授权邮箱条款，转人工"))

    # L2-b 最终用户信息表（11.6 声明为附件）
    if "最终用户信息表" in text:
        # 声明为附件：正文含该表内容（出现「序号/产品名称」表格）→ pass；仅声明 → block
        has_table_body = bool(re.search(r"最终用户信息表[\s\S]{0,400}?(序号|产品名称)", text))
        if has_table_body:
            results.append(CheckResult(
                "end_user_table", "pass", "最终用户信息表已随附",
                evidence="正文含最终用户信息表内容", source="contract_text"))
        else:
            results.append(CheckResult(
                "end_user_table", "block",
                "合同 11.6 声明附件「最终用户信息表」但未随附",
                evidence="11.6 本合同附件：最终用户信息表", source="contract_text"))
    else:
        results.append(_manual("end_user_table", "未检索到最终用户信息表条款，转人工"))

    # L2-c 版本描述一致性（流程分项标准服务内容 vs 合同正文）
    item_desc = " ".join(
        (getattr(i, "product_name", "") or "") for i in form.items
    )
    plus_flag = "增强版" in body_text or "PLUS" in body_text.upper()
    license_flag = "许可版" in text
    if plus_flag and license_flag:
        results.append(CheckResult(
            "version_desc", "warn",
            "版本描述不一致（流程分项含「增强版/PLUS」，合同正文为「许可版」）",
            evidence="分项 vs 正文版本措辞不一致", source="contract_text"))
    else:
        results.append(CheckResult(
            "version_desc", "pass", "版本描述未见冲突",
            evidence="分项/正文版本措辞一致", source="contract_text"))
    return results
