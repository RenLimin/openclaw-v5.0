"""健康风险评估领域模型。

支持多种风险评估类型：心血管、糖尿病、癌症、综合健康风险等。
每次评估生成一条记录，包含评分、等级、风险因子、建议。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from repository.base import TenantModel


class RiskLevel(str, Enum):
    """风险等级。"""
    LOW = "low"           # 低风险
    MILD = "mild"         # 轻度风险
    MODERATE = "moderate"  # 中度风险
    HIGH = "high"         # 高风险
    VERY_HIGH = "very_high"  # 极高风险


class RiskType(str, Enum):
    """风险类型。"""
    CARDIOVASCULAR = "cardiovascular"   # 心血管疾病风险
    DIABETES = "diabetes"               # 糖尿病风险
    HYPERTENSION = "hypertension"       # 高血压风险
    OBESITY = "obesity"                 # 肥胖风险
    STROKE = "stroke"                   # 脑卒中风险
    CANCER_GENERAL = "cancer_general"   # 癌症综合风险
    RESPIRATORY = "respiratory"         # 呼吸系统风险
    KIDNEY = "kidney"                   # 肾脏疾病风险
    LIVER = "liver"                     # 肝脏疾病风险
    MENTAL = "mental"                   # 心理健康风险
    OSTEOPOROSIS = "osteoporosis"       # 骨质疏松风险
    METABOLIC_SYNDROME = "metabolic_syndrome"  # 代谢综合征
    COMPREHENSIVE = "comprehensive"     # 综合健康风险


class RiskFactor(BaseModel):
    """风险因子。"""

    name: str                       # 因子名称
    weight: float = 0.0             # 权重/贡献分
    value: Optional[str] = None     # 当前值
    is_positive: bool = False       # True = 保护性因素，False = 危险因素
    description: str = ""           # 描述
    evidence: Optional[str] = None  # 证据来源


class RiskRecommendation(BaseModel):
    """风险干预建议。"""

    category: str           # 分类：饮食/运动/用药/体检/生活方式
    priority: int = 3       # 优先级 1-5（1 最高）
    title: str
    description: str = ""
    target: Optional[str] = None     # 目标值
    timeline: Optional[str] = None   # 建议时间线
    references: List[str] = Field(default_factory=list)


class RiskAssessment(TenantModel):
    """健康风险评估记录。"""

    profile_id: str
    risk_type: RiskType
    risk_level: RiskLevel

    # ── 评分 ────────────────────────────────────────────────────
    score: float = 0.0              # 原始得分
    score_max: float = 100.0        # 满分
    risk_percentage: Optional[float] = None  # 患病概率百分比
    reference_group: Optional[str] = None   # 参考人群

    # ── 算法 ────────────────────────────────────────────────────
    algorithm: str = ""             # 使用的评估算法/模型名称
    algorithm_version: str = "1.0"  # 算法版本
    assessment_date: datetime = Field(default_factory=datetime.utcnow)

    # ── 风险因子 ────────────────────────────────────────────────
    risk_factors: List[RiskFactor] = Field(default_factory=list)

    # ── 建议 ────────────────────────────────────────────────────
    recommendations: List[RiskRecommendation] = Field(default_factory=list)

    # ── 对比 ────────────────────────────────────────────────────
    previous_assessment_id: Optional[str] = None
    change_from_previous: Optional[str] = None  # improved / worsened / stable

    # ── 补充 ────────────────────────────────────────────────────
    summary: str = ""               # 评估结论摘要
    severity_note: str = ""         # 风险等级解释
    next_review_date: Optional[datetime] = None

    tags: List[str] = Field(default_factory=list)
    notes: str = ""

    @property
    def score_ratio(self) -> float:
        """得分率 0-1。"""
        if self.score_max <= 0:
            return 0.0
        return round(self.score / self.score_max, 4)

    @property
    def top_risk_factors(self, n: int = 5) -> List[RiskFactor]:
        """权重最高的前 N 个风险因子（排除保护性因素）。"""
        factors = [f for f in self.risk_factors if not f.is_positive]
        factors.sort(key=lambda x: x.weight, reverse=True)
        return factors[:n]

    @property
    def top_recommendations(self, n: int = 3) -> List[RiskRecommendation]:
        """优先级最高的前 N 条建议。"""
        recs = sorted(self.recommendations, key=lambda x: x.priority)
        return recs[:n]

    def factor_summary(self) -> Dict[str, int]:
        """返回 {危险因素数, 保护因素数, 总数}。"""
        risk = sum(1 for f in self.risk_factors if not f.is_positive)
        protective = sum(1 for f in self.risk_factors if f.is_positive)
        return {
            "total": len(self.risk_factors),
            "risk_count": risk,
            "protective_count": protective,
        }
