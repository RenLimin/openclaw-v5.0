"""六类产物 IR + 状态的 Pydantic 契约（Schema-First）。

事实类字段必须带 sourceUri / clauseRefs，无来源 → 校验 BLOCK（数据来源铁律）。
"""
from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Optional, Literal
from pydantic import BaseModel, Field


# ---------- 枚举 ----------
class Audience(str, Enum):
    internal = "internal"
    external = "external"


class PhaseStatus(str, Enum):
    in_progress = "in_progress"
    done = "done"
    blocked = "blocked"


class Health(str, Enum):
    green = "green"
    yellow = "yellow"
    red = "red"


class AcceptanceStatus(str, Enum):
    not_started = "not_started"
    in_progress = "in_progress"
    initial_pass = "initial_pass"
    final_pass = "final_pass"
    failed = "failed"


class PaymentNodeStatus(str, Enum):
    not_invoiced = "not_invoiced"
    invoiced = "invoiced"
    partial_paid = "partial_paid"
    paid = "paid"
    overdue = "overdue"


class Conclusion(str, Enum):
    pass_ = "pass"
    fail = "fail"
    conditional_pass = "conditional_pass"


class FinalConclusion(str, Enum):
    qualified = "qualified"
    needs_rectification = "needs_rectification"
    unqualified = "unqualified"


# ---------- 溯源 mixin ----------
class Sourced(BaseModel):
    """所有事实字段必须可溯源（铁律）。"""
    sourceUri: str = Field(..., description="原始系统记录 URI：ones:// 或 oa://")


class ClauseSourced(Sourced):
    clauseRefs: list[str] = Field(default_factory=list, description="合同条款号外键")
    clauseText: Optional[str] = None


# ---------- P2 签约项目汇总（核心事实源） ----------
class ScopeClause(BaseModel):
    deliverables: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    techSpecRef: Optional[str] = None
    sourceUri: str


class Milestone(BaseModel):
    id: str
    name: str
    deliverables: list[str] = Field(default_factory=list)
    dueDate: Optional[str] = None
    deliveryForm: Optional[str] = None
    sourceUri: str
    clauseRefs: list[str] = Field(default_factory=list)


class AcceptanceStage(BaseModel):
    criteria: Optional[str] = None
    process: Optional[str] = None
    documentsRequired: list[str] = Field(default_factory=list)
    disputeResolution: Optional[str] = None
    sourceUri: str
    clauseRefs: list[str] = Field(default_factory=list)


class AcceptanceClause(BaseModel):
    method: Literal["initial_and_final", "one_time"]
    initialAcceptance: Optional[AcceptanceStage] = None
    finalAcceptance: Optional[AcceptanceStage] = None


class PaymentNode(BaseModel):
    node: str
    ratio: float = Field(ge=0, le=1)
    amount: float = Field(ge=0)
    triggerCondition: Optional[str] = None
    daysAfterTrigger: Optional[int] = None
    sourceUri: str
    clauseRefs: list[str] = Field(default_factory=list)


class PaymentClause(BaseModel):
    schedule: list[PaymentNode]
    invoiceRequirements: Optional[str] = None
    overdueClause: Optional[str] = None
    sourceUri: str


class WarrantyClause(BaseModel):
    startFrom: Optional[str] = None
    durationMonths: Optional[int] = None
    scope: Optional[str] = None
    finalAcceptanceOnExpiry: bool = False
    sourceUri: str
    clauseRefs: list[str] = Field(default_factory=list)


class IpAndDataClause(BaseModel):
    ownership: Optional[str] = None
    license: Optional[str] = None
    dataIsolation: Optional[str] = None
    sourceUri: str
    clauseRefs: list[str] = Field(default_factory=list)


class BreachClause(BaseModel):
    delayPenalty: Optional[str] = None
    terminationForCause: Optional[str] = None
    sourceUri: str
    clauseRefs: list[str] = Field(default_factory=list)


class ClauseExtract(BaseModel):
    clauseNo: str = Field(..., min_length=1)
    text: str
    sourceFile: str
    page: Optional[int] = None


class ContractRegister(BaseModel):
    """P2 签约项目汇总 —— 下游唯一事实源。"""
    contractNo: str = Field(..., min_length=1)
    officialName: Optional[str] = None
    signDate: Optional[str] = None
    contractType: Literal["fixed_price", "time_materials", "framework"]
    amount: float = Field(..., description="合同净额；终止/冲销协议可为负")
    taxRate: Optional[float] = Field(None, ge=0, le=1)
    currency: str = "CNY"
    partyA: str
    partyB: str
    customerContractNo: Optional[str] = None
    scope: ScopeClause
    milestones: list[Milestone] = Field(default_factory=list)
    acceptance: AcceptanceClause
    payment: PaymentClause
    warranty: Optional[WarrantyClause] = None
    ipAndData: Optional[IpAndDataClause] = None
    breach: Optional[BreachClause] = None
    complianceRefs: list[str] = Field(default_factory=list)
    clauseExtracts: list[ClauseExtract] = Field(default_factory=list)
    sourceFileUri: str
    extractedAt: str
    extractionConfidence: float = Field(0.0, ge=0, le=1)
    reviewStatus: Literal["auto", "human_reviewed", "needs_human"] = "auto"
    extractionErrors: list[str] = Field(default_factory=list)


# ---------- P1 项目汇总 ----------
class ProjectRegister(BaseModel):
    projectId: str
    customer: str
    projectName: str
    projectType: Literal["software_service", "consulting", "saas", "delivery"]
    contractNo: Optional[str] = None
    contractAmount: float = 0.0
    currency: str = "CNY"
    projectManager: Optional[str] = None
    startDate: Optional[str] = None
    endDate: Optional[str] = None
    phaseStatus: PhaseStatus
    health: Health
    acceptanceStatus: AcceptanceStatus
    paymentStatus: PaymentNodeStatus
    lastUpdated: str
    sourceUri: str


# ---------- P3 履约义务 ----------
class PerformanceObligation(BaseModel):
    obligationId: str
    contractNo: str
    description: str
    isDistinct: bool
    allocatedPrice: float = Field(ge=0)
    recognitionMethod: Literal["point_in_time", "over_time"]
    acceptanceMilestoneId: Optional[str] = None
    recognizedAmount: float = Field(0.0, ge=0)
    remainingAmount: float = Field(0.0, ge=0)
    recognizedAt: Optional[str] = None
    sourceUri: str
    clauseRefs: list[str] = Field(default_factory=list)


# ---------- P4 验收条件核查表 ----------
class CheckItem(BaseModel):
    itemId: str
    clauseRefs: list[str]
    clauseText: Optional[str] = None
    checkContent: str
    criteria: str
    evidenceUri: Optional[str] = None
    method: Literal["test", "inspection", "review", "demo", "walkthrough"]
    conclusion: Optional[Conclusion] = None
    outstandingIssues: list[str] = Field(default_factory=list)
    reviewedBy: Optional[str] = None
    reviewedAt: Optional[str] = None


class AcceptanceChecklist(BaseModel):
    checklistId: str
    contractNo: str
    acceptanceType: Literal["initial", "final", "one_time"]
    items: list[CheckItem]
    summaryConclusion: Optional[Conclusion] = None
    generatedAt: str
    sourceUri: str


# ---------- P5 验收单 / 交付说明 ----------
class DeliverableCheck(BaseModel):
    name: str
    delivered: bool
    version: Optional[str] = None
    remark: Optional[str] = None


class SignatureBlock(BaseModel):
    signed: bool = False
    name: Optional[str] = None
    date: Optional[str] = None


class Signatures(BaseModel):
    acceptanceTeam: SignatureBlock = Field(default_factory=SignatureBlock)
    partyARep: SignatureBlock = Field(default_factory=SignatureBlock)
    partyBRep: SignatureBlock = Field(default_factory=SignatureBlock)


class RevenueRecognition(BaseModel):
    recognized: bool = False
    obligationIds: list[str] = Field(default_factory=list)
    recognizedAmount: float = 0.0
    recognizedDate: Optional[str] = None


class AcceptanceReport(BaseModel):
    reportNo: str
    contractNo: str
    acceptanceType: Literal["initial", "final", "one_time"]
    date: str
    location: Optional[str] = None
    partyA: str
    partyB: str
    deliverablesChecklist: list[DeliverableCheck]
    conclusion: FinalConclusion
    outstandingList: list[str] = Field(default_factory=list)
    basis: list[str] = Field(default_factory=list)
    signatures: Signatures = Field(default_factory=Signatures)
    attachments: list[str] = Field(default_factory=list)
    revenueRecognition: RevenueRecognition = Field(default_factory=RevenueRecognition)
    sourceUri: str


# ---------- P6 回款跟踪 ----------
class PaymentPlanItem(BaseModel):
    node: str
    ratio: float = Field(ge=0, le=1)
    amount: float = Field(ge=0)
    triggerCondition: Optional[str] = None
    triggerDate: Optional[str] = None
    expectedDate: Optional[str] = None
    status: PaymentNodeStatus


class AcceptanceTrigger(BaseModel):
    milestoneId: str
    paymentNode: str
    amount: float
    triggered: bool = False


class Invoice(BaseModel):
    invoiceNo: str
    date: str
    amount: float
    status: str


class Receivables(BaseModel):
    totalReceivable: float = 0
    received: float = 0
    outstanding: float = 0


class Aging(BaseModel):
    current: float = 0
    days0_30: float = 0
    days31_60: float = 0
    days61_90: float = 0
    days90_plus: float = 0


class OverdueItem(BaseModel):
    paymentNode: str
    amount: float
    overdueDays: int
    collectionStatus: str


class PaymentTracker(BaseModel):
    contractNo: str
    paymentPlan: list[PaymentPlanItem]
    acceptanceTriggers: list[AcceptanceTrigger] = Field(default_factory=list)
    invoices: list[Invoice] = Field(default_factory=list)
    receivables: Receivables = Field(default_factory=Receivables)
    aging: Aging = Field(default_factory=Aging)
    overdueItems: list[OverdueItem] = Field(default_factory=list)
    writeOffs: list[dict] = Field(default_factory=list)
    sourceUri: str


# ---------- 六类产物容器 ----------
class ArtifactSet(BaseModel):
    projectRegister: list[ProjectRegister] = Field(default_factory=list)
    contractRegister: list[ContractRegister] = Field(default_factory=list)
    performanceObligation: list[PerformanceObligation] = Field(default_factory=list)
    acceptanceChecklist: list[AcceptanceChecklist] = Field(default_factory=list)
    acceptanceReport: list[AcceptanceReport] = Field(default_factory=list)
    paymentTracker: list[PaymentTracker] = Field(default_factory=list)
