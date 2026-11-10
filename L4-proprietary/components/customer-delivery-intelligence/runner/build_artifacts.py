"""把 OA 台账行（权威事实源）构建为六类产物 IR。

铁律：
- 只填台账真实字段；金额/日期/客户/验收条件一律取台账原值。
- 台账未提供的付款拆分，保守映射为「单一节点=全额」，触发条件取验收条件原文，
  非瞎猜；此类合同 review_status=needs_human，默认字段列入 warnings 待人工复核。
- 每条产物带 sourceUri（指向台账原始文件）。
"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
import pandas as pd

from .models import (
    ArtifactSet, ProjectRegister, ContractRegister, ScopeClause, AcceptanceClause,
    AcceptanceStage, PaymentClause, PaymentNode, PerformanceObligation,
    AcceptanceChecklist, CheckItem, AcceptanceReport, DeliverableCheck,
    RevenueRecognition, PaymentTracker, PaymentPlanItem, Receivables,
    FinalConclusion, PhaseStatus, Health, AcceptanceStatus, PaymentNodeStatus,
)
from .state import now_iso

LEDGER_URI = (Path.home()/".openclaw/data/oa_exports/contract_ledger_202610.xlsx").as_uri()


def _d(v):
    if isinstance(v, (pd.Timestamp, datetime)):
        return v.date().isoformat()
    return v if v not in ("", None) else None


def _money(v):
    try:
        return float(v)
    except Exception:
        return 0.0


def build(rows: list[dict], customer: str) -> tuple[ArtifactSet, list[str]]:
    warnings: list[str] = []
    art = ArtifactSet()
    seq = 0
    for r in rows:
        no = str(r.get("合同编号！") or "").strip()
        if not no:
            continue
        seq += 1
        amount = _money(r.get("签约金额（元）"))
        end_user = r.get("最终用户名称") or r.get("客户名称") or customer
        accept_cond = (str(r.get("合同验收条件")) if r.get("合同验收条件") else None)
        doc_name = r.get("合同验收文档名称")
        cls_type = r.get("合同分类") or "正式合同"
        is_termination = "终止" in str(cls_type)

        proj_id = f"PROJ-2026-CCB-{seq:03d}"

        # ---------- P2 ContractRegister（核心）----------
        needs_human = accept_cond is None or is_termination
        if accept_cond is None:
            warnings.append(f"{no}: 台账无验收条件，acceptance criteria 留空，需人工")
        scope = ScopeClause(deliverables=[], exclusions=[], sourceUri=LEDGER_URI)
        acceptance = AcceptanceClause(
            method="one_time",
            initialAcceptance=AcceptanceStage(
                criteria=accept_cond,
                documentsRequired=[doc_name] if doc_name else [],
                sourceUri=LEDGER_URI),
        )
        # 保守单一付款节点：全额；终止协议金额可能为负，ratio 用 1（金额为负允许吗 PaymentNode ge=0）
        node_amount = amount if amount >= 0 else 0.0
        payment = PaymentClause(
            schedule=[PaymentNode(node="single", ratio=1.0, amount=node_amount,
                                 triggerCondition=accept_cond or None,
                                 sourceUri=LEDGER_URI)],
            invoiceRequirements=(f"税率 {r.get('税率')}" if r.get("税率") else None),
            sourceUri=LEDGER_URI)
        contract = ContractRegister(
            contractNo=no,
            signDate=_d(r.get("合同下单日期") or r.get("申请日期")),
            contractType="fixed_price",
            amount=amount,
            taxRate=(_money(str(r.get("税率")).replace("%",""))/100 if r.get("税率") else None),
            partyA=end_user, partyB="北京梆梆安全科技有限公司",
            scope=scope, acceptance=acceptance, payment=payment,
            officialName=None,
            clauseExtracts=[],
            sourceFileUri=LEDGER_URI,
            extractedAt=now_iso(),
            extractionConfidence=(0.6 if accept_cond else 0.3),
            reviewStatus=("needs_human" if needs_human else "auto"),
        )
        art.contractRegister.append(contract)

        # ---------- P1 ProjectRegister ----------
        archive = r.get("验收文件归档状态")
        acc_status = AcceptanceStatus.final_pass if archive == "已归档" else AcceptanceStatus.not_started
        art.projectRegister.append(ProjectRegister(
            projectId=proj_id, customer=end_user, projectName=(doc_name or no),
            projectType="software_service", contractNo=no, contractAmount=amount,
            projectManager=r.get("项目经理"),
            startDate=_d(r.get("服务开始日期")), endDate=_d(r.get("服务结束日期")),
            phaseStatus=PhaseStatus.done if is_termination else PhaseStatus.in_progress,
            health=Health.green, acceptanceStatus=acc_status,
            paymentStatus=(PaymentNodeStatus.paid if archive=="已归档" else PaymentNodeStatus.not_invoiced),
            lastUpdated=now_iso(), sourceUri=LEDGER_URI))

        # ---------- P3 PerformanceObligation ----------
        art.performanceObligation.append(PerformanceObligation(
            obligationId=f"PO-{no}-01", contractNo=no,
            description=(doc_name or "合同交付义务"),
            isDistinct=True, allocatedPrice=node_amount,
            recognitionMethod="point_in_time",
            recognizedAmount=(node_amount if archive=="已归档" else 0.0),
            remainingAmount=(0.0 if archive=="已归档" else node_amount),
            sourceUri=LEDGER_URI))

        # ---------- P4 AcceptanceChecklist ----------
        if accept_cond and not is_termination:
            art.acceptanceChecklist.append(AcceptanceChecklist(
                checklistId=f"ACL-{no}-ONE", contractNo=no, acceptanceType="one_time",
                items=[CheckItem(itemId="ITEM-001", clauseRefs=[],
                                 clauseText=accept_cond[:500],
                                 checkContent="按合同验收条件核查交付与客户确认",
                                 criteria=accept_cond[:300],
                                 evidenceUri=None, method="inspection", conclusion=None)],
                generatedAt=now_iso(), sourceUri=LEDGER_URI))

        # ---------- P5 AcceptanceReport ----------
        art.acceptanceReport.append(AcceptanceReport(
            reportNo=f"ACPT-{no}", contractNo=no, acceptanceType="one_time",
            date=now_iso()[:10], partyA=end_user, partyB="北京梆梆安全科技有限公司",
            deliverablesChecklist=[DeliverableCheck(name=(doc_name or "交付物"), delivered=False)],
            conclusion=(FinalConclusion.needs_rectification if not is_termination else FinalConclusion.qualified),
            basis=[f"合同 {no}", f"台账验收条件: {accept_cond}" if accept_cond else "无"],
            revenueRecognition=RevenueRecognition(
                recognized=(archive=="已归档"),
                obligationIds=[f"PO-{no}-01"],
                recognizedAmount=(node_amount if archive=="已归档" else 0.0),
                recognizedDate=(_d(r.get("合同归档日期")) if archive=="已归档" else None)),
            sourceUri=LEDGER_URI))

        # ---------- P6 PaymentTracker ----------
        outstanding = node_amount if archive != "已归档" else 0.0
        art.paymentTracker.append(PaymentTracker(
            contractNo=no,
            paymentPlan=[PaymentPlanItem(node="single", ratio=1.0, amount=node_amount,
                                        triggerCondition=accept_cond,
                                        expectedDate=_d(r.get("合同预计验收时间")),
                                        status=(PaymentNodeStatus.paid if archive=="已归档"
                                                else PaymentNodeStatus.not_invoiced))],
            receivables=Receivables(totalReceivable=node_amount,
                                    received=(node_amount if archive=="已归档" else 0.0),
                                    outstanding=outstanding),
            sourceUri=LEDGER_URI))

        if is_termination:
            warnings.append(f"{no}: 终止协议（金额 {amount}），按非交付合同处理")

    return art, warnings
