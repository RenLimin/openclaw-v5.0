"""固定核查项（只读，纯函数 + 本地文件）— 757 单据审批前置检查。

分层（fail-closed）：
  L1 表单层：始终判定（数据源 = ``body.txt`` 渲染表单）。
    - contract_no_missing  合同编号缺失 → **warn（不阻断）**
      口径（Rex 2026-11-27）：合同编号于**合同归档时生成**，OA 销售合同
      审核流程中该字段默认为空属正常态，不得作为退回理由。
    - service_period       服务期未明确起止 → warn
  L2 原文层：调用方提供合同原文（显式 ``--contract-file`` 或编排层自动从 OA
  表单附件下载，见 ``attachment.fetch_contract_text``）时判定，否则 ``manual``
  （**不伪造**）。
    - party_a_email        甲方官方邮箱留空 → block
    - end_user_table       最终用户信息表声明为附件但未随附 → block
    - version_desc         流程分项版本描述 vs 合同正文不一致 → warn

口径修正（Rex 2026-11-27 实测）：旧注释称「757 附件 REST 下载无权限」系
**会话过期误判**——未登录时 ``FileDownload`` 返回的是登录跳转 HTML（235B
``<script>...login</script>``），并非权限文案。会话有效时 ``loadlink`` 可
直接下载真实文档（886502 docx=PK/25339B；888194/888171/888166 doc=OLE2）。
因此 L2 **会**在编排层自动取原文后判定；仍拿不到时才 ``manual`` 转人工。
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


_CONTRACT_NO_RE = re.compile(r"(XSZS\d{8}\d+(?:[A-Z0-9-]*)?)")


def extract_contract_no(body_text: str, contract_name: str = "") -> tuple:
    """提取合同编号：表单字段优先，合同名称回退。

    返回 ``(值, 来源)``；来源 ∈ {form, contract_name, none}。

    背景（P3）：实测 887756 表单「合同编号！」为空，但合同名称含
    `20261106-01KP` 类编号 —— 仅凭表单判缺失会产生误报。回退命中须在
    evidence 注明来源（可审计）。
    """
    fields = parse_body_fields(body_text)
    v = (fields.get("合同编号！") or fields.get("合同编号") or "").strip()
    if v and v not in ("【空】", "-", "/"):
        return v, "form"
    name = (contract_name or "").strip()
    m = _CONTRACT_NO_RE.search(name or "")
    if not m:
        # 非 XSZS 前缀的松散编号（如「…-01KP-…」）也记录，但标来源为 name_loose
        m2 = re.search(r"(\d{8}-[A-Z0-9]{2,})", name or "")
        if m2:
            return m2.group(1), "contract_name_loose"
        return "", "none"
    return m.group(1), "contract_name"


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_BANGGLE_DOMAIN = "@bangcle.com"


def _manual(check_id: str, message: str, evidence: str = "") -> CheckResult:
    """转人工项。``evidence`` 必须如实反映当前数据源状态。

    注意（2026-11-27）：旧实现恒定写「未提供合同原文」，在自动下载附件后
    该文案与事实不符（有原文但未检索到条款）→ 会误导人工复核方向。
    """
    return CheckResult(check_id=check_id, level="manual", message=message,
                       evidence=evidence or "未提供合同原文", source="none")


def _party_a_email_windows(text: str) -> List[str]:
    """收集「向甲方…邮箱」相关上下文窗口（供甲方官方邮箱判定）。"""
    wins: List[str] = []
    for m in re.finditer(r"向甲方", text):
        wins.append(text[m.start(): m.start() + 160])
    for m in re.finditer(r"甲方[^。\n]{0,50}?邮箱（官方邮箱）", text):
        wins.append(text[max(0, m.start() - 120): m.end() + 40])
    return wins


def _external_emails(window: str) -> List[str]:
    """窗口内的非乙方域名邮箱（甲方官方邮箱）。"""
    return [e for e in _EMAIL_RE.findall(window)
            if not e.lower().endswith(_BANGGLE_DOMAIN)]


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

    # ---- L1-a 合同编号（表单优先，合同名回退；来源入 evidence）----
    contract_no, cn_source = extract_contract_no(
        body_text, getattr(form, "contract_name", "") or "")
    if contract_no:
        label = {"form": "表单", "contract_name": "合同名称回退",
                 "contract_name_loose": "合同名称（松散编号）"}.get(cn_source, cn_source)
        results.append(CheckResult(
            "contract_no_missing", "pass",
            "合同编号已明确（来源：%s）" % label,
            evidence="%s=%s（来源 %s）" % (
                "合同编号", contract_no, cn_source),
            source=cn_source))
    else:
        # Rex 2026-11-27：合同编号在合同归档时生成，OA 销售合同审核流程默认为空
        # → 提示级（warn），不阻断审批，也不作为「退回补充」依据。
        results.append(CheckResult(
            "contract_no_missing", "warn",
            "合同编号暂缺（归档时生成，非阻断项）",
            evidence="合同编号！=【空】且合同名称无编号；口径：归档环节生成，"
                     "OA 审核阶段允许为空（2026-11-27 Rex 规则）", source="none"))

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

    # L2-a 甲方官方邮箱（交付/验收条款）
    # 口径（2026-11-27 实测修正）：旧版只看「甲方指定授权…邮箱」单处，
    # 漏检了「向甲方 <外部邮箱> 邮箱（官方邮箱）」形态（888194/888171/888166
    # 均有真实甲方邮箱却报 manual）。现扫描全部相关窗口：
    #   · 存在非 @bangcle.com 邮箱 → 甲方官方邮箱已明确（pass）
    #   · 仅有乙方域名邮箱/占位符（"/"）→ 甲方官方邮箱未明确（block）
    #   · 全文无邮箱痕迹 → manual（不臆断）
    wins = _party_a_email_windows(text)
    ext = sorted({e for w in wins for e in _external_emails(w)})
    if ext:
        # evidence 取命中邮箱的局部上下文（±窗口），避免拿无关句充证据
        e0 = ext[0]
        i = text.find(e0)
        ev = text[max(0, i - 80): i + 40].replace("\n", " ").strip()
        results.append(CheckResult(
            "party_a_email", "pass", "甲方官方邮箱已明确",
            evidence="%s → %s" % (ev[-60:], e0),
            source="contract_text"))
    elif wins:
        results.append(CheckResult(
            "party_a_email", "block",
            "合同交付/验收条款未见甲方官方邮箱（仅有乙方邮箱/占位符）",
            evidence=wins[0].replace("\n", " ")[:100], source="contract_text"))
    else:
        results.append(_manual(
            "party_a_email", "未检索到甲方授权邮箱条款，转人工",
            evidence="已有合同原文，全文未检出「向甲方…邮箱」等授权邮箱条款"))

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
        results.append(_manual(
            "end_user_table", "未检索到最终用户信息表条款，转人工",
            evidence="已有合同原文，全文未检出「最终用户信息表」表述"))

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
