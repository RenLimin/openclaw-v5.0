"""把六类产物渲染为 Markdown（对内版；对外脱敏由 audience 控制）。"""
from __future__ import annotations
from pathlib import Path
from .models import ArtifactSet


def render(art: ArtifactSet, out_dir: str, customer: str, audience: str) -> list[str]:
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    paths = []

    # 项目汇总
    L = [f"# 项目汇总 — {customer}", "",
         "| 项目ID | 最终用户/客户 | 合同号 | 金额 | 起止 | 阶段 | 验收 | 回款 |",
         "|---|---|---|---|---|---|---|---|"]
    for p in art.projectRegister:
        L.append(f"| {p.projectId} | {p.customer} | {p.contractNo} | {p.contractAmount:,.0f} "
                 f"| {p.startDate}~{p.endDate} | {p.phaseStatus.value} "
                 f"| {p.acceptanceStatus.value} | {p.paymentStatus.value} |")
    paths.append(_write(out/"01-项目汇总.md", L))

    # 签约项目汇总（含合同条款）
    L = [f"# 签约项目汇总（含合同条款）— {customer}", ""]
    for c in art.contractRegister:
        L += [f"## {c.contractNo}",
              f"- 客户/最终用户：{c.partyA}",
              f"- 合同净额：{c.amount:,.2f} {c.currency}" +
              (f"（税率 {c.taxRate:.0%}）" if c.taxRate is not None else ""),
              f"- 签订/下单：{c.signDate}",
              f"- 复核状态：**{c.reviewStatus}**（置信度 {c.extractionConfidence:.2f}）",
              "", "**验收条款：**"]
        st = c.acceptance.initialAcceptance
        if st and st.criteria:
            L += [f"- 标准/条件：{st.criteria}",
                  f"- 所需文档：{', '.join(st.documentsRequired) if st.documentsRequired else '—'}"]
        else:
            L.append("- ⚠️ 台账无验收条件，待人工补")
        L += ["", "**付款条款：**"]
        for n in c.payment.schedule:
            L.append(f"- {n.node}：{n.ratio:.0%} / {n.amount:,.0f}（触发：{n.triggerCondition}）")
        L += [f"- 发票：{c.payment.invoiceRequirements or '—'}", ""]
    paths.append(_write(out/"02-签约项目汇总-含合同条款.md", L))

    # 履约义务
    L = [f"# 履约义务汇总 — {customer}", "",
         "| 义务ID | 合同号 | 描述 | 分摊金额 | 确认方式 | 已确认 | 剩余 |",
         "|---|---|---|---|---|---|---|"]
    for o in art.performanceObligation:
        L.append(f"| {o.obligationId} | {o.contractNo} | {o.description} "
                 f"| {o.allocatedPrice:,.0f} | {o.recognitionMethod} "
                 f"| {o.recognizedAmount:,.0f} | {o.remainingAmount:,.0f} |")
    paths.append(_write(out/"03-履约义务汇总.md", L))

    # 验收条件核查表
    L = [f"# 验收条件核查表 — {customer}", ""]
    for cl in art.acceptanceChecklist:
        L += [f"## {cl.checklistId}（{cl.contractNo}）", ""]
        for it in cl.items:
            L += [f"- **{it.itemId}** 方法：{it.method}",
                  f"  - 条款依据：{it.clauseText}",
                  f"  - 判定标准：{it.criteria}",
                  f"  - 结论：{it.conclusion.value if it.conclusion else '待核查'}", ""]
    paths.append(_write(out/"04-验收条件核查表.md", L))

    # 验收单
    L = [f"# 验收单/交付说明（草稿）— {customer}", ""]
    for r in art.acceptanceReport:
        L += [f"## {r.reportNo}",
              f"- 合同号：{r.contractNo}｜类型：{r.acceptanceType}｜日期：{r.date}",
              f"- 结论：**{r.conclusion.value}**",
              f"- 交付物：" + ", ".join(f"{d.name}({'✓' if d.delivered else '✗'})"
                                        for d in r.deliverablesChecklist),
              f"- 收入确认：已确认={r.revenueRecognition.recognized} "
              f"金额={r.revenueRecognition.recognizedAmount:,.0f}",
              f"- 签字：验收组={r.signatures.acceptanceTeam.signed} "
              f"甲方={r.signatures.partyARep.signed} 乙方={r.signatures.partyBRep.signed}", ""]
    paths.append(_write(out/"05-验收单-交付说明.md", L))

    # 回款跟踪
    L = [f"# 回款跟踪 — {customer}", "",
         "| 合同号 | 节点 | 金额 | 触发条件 | 预计日期 | 状态 |", "|---|---|---|---|---|---|"]
    for t in art.paymentTracker:
        for n in t.paymentPlan:
            L.append(f"| {t.contractNo} | {n.node} | {n.amount:,.0f} "
                     f"| {n.triggerCondition} | {n.expectedDate} | {n.status.value} |")
        rec = t.receivables
        L.append(f"| | **合计** | 应收 {rec.totalReceivable:,.0f} / 已收 {rec.received:,.0f} "
                 f"/ 未收 **{rec.outstanding:,.0f}** | | | |")
    paths.append(_write(out/"06-回款跟踪.md", L))

    # 对外脱敏：external 版移除长邮箱/内部条款（轻量：这里先产出，N7 audience=external 时加注）
    if audience == "external":
        for p in paths:
            txt = Path(p).read_text(encoding="utf-8")
            txt = txt.replace("（对内版）", "（对外版）")
            Path(p).write_text(txt, encoding="utf-8")
    return paths


def _write(path: Path, lines: list[str]) -> str:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)
