"""健康风险评估模块测试。"""

from datetime import datetime, timedelta

from risk_assessment.models import (
    RiskAssessment,
    RiskLevel,
    RiskType,
    RiskFactor,
    RiskRecommendation,
)
from risk_assessment.repository import RiskAssessmentRepository


def test_create_assessment_full():
    factors = [
        RiskFactor(name="高血压", weight=30, value="140/90", is_positive=False, description="收缩压偏高"),
        RiskFactor(name="吸烟", weight=20, value="20年", is_positive=False),
        RiskFactor(name="规律运动", weight=-10, value="每周3次", is_positive=True, description="保护性因素"),
        RiskFactor(name="高血脂", weight=25, value="TC 6.2", is_positive=False),
    ]
    recs = [
        RiskRecommendation(
            category="饮食",
            priority=1,
            title="低盐低脂饮食",
            description="每日盐摄入<5g，减少饱和脂肪酸",
            target="盐<5g/天",
            timeline="立即执行",
        ),
        RiskRecommendation(
            category="运动",
            priority=2,
            title="中等强度有氧运动",
            description="每周150分钟中等强度有氧运动",
            target="150分钟/周",
            timeline="3个月内养成习惯",
        ),
    ]
    a = RiskAssessmentRepository.create(
        profile_id="P001",
        risk_type=RiskType.CARDIOVASCULAR,
        risk_level=RiskLevel.MODERATE,
        score=55.0,
        score_max=100.0,
        risk_percentage=12.5,
        reference_group="中国成年男性",
        algorithm="Framingham Risk Score",
        algorithm_version="2.0",
        risk_factors=factors,
        recommendations=recs,
        summary="心血管疾病中度风险，主要危险因素为高血压和吸烟",
        severity_note="10年心血管事件风险约12.5%",
        next_review_date=datetime(2027, 1, 1),
    )
    assert a.risk_type == RiskType.CARDIOVASCULAR
    assert a.risk_level == RiskLevel.MODERATE
    assert a.score == 55.0
    assert abs(a.score_ratio - 0.55) < 0.001
    assert len(a.risk_factors) == 4
    assert len(a.recommendations) == 2


def test_score_ratio():
    a = RiskAssessment(
        profile_id="P001",
        risk_type=RiskType.DIABETES,
        risk_level=RiskLevel.LOW,
        score=15,
        score_max=100,
    )
    assert a.score_ratio == 0.15

    a2 = RiskAssessment(
        profile_id="P001",
        risk_type=RiskType.DIABETES,
        risk_level=RiskLevel.LOW,
        score=0,
        score_max=0,
    )
    assert a2.score_ratio == 0.0


def test_top_risk_factors():
    factors = [
        RiskFactor(name="A", weight=10, is_positive=False),
        RiskFactor(name="B", weight=30, is_positive=False),
        RiskFactor(name="C", weight=20, is_positive=False),
        RiskFactor(name="D", weight=15, is_positive=True),  # 保护性，排除
    ]
    a = RiskAssessment(
        profile_id="P001",
        risk_type=RiskType.HYPERTENSION,
        risk_level=RiskLevel.MILD,
        risk_factors=factors,
    )
    top = a.top_risk_factors
    assert len(top) == 3
    assert top[0].name == "B"  # 权重最高


def test_top_recommendations():
    recs = [
        RiskRecommendation(category="a", priority=3, title="C"),
        RiskRecommendation(category="b", priority=1, title="A"),
        RiskRecommendation(category="c", priority=2, title="B"),
    ]
    a = RiskAssessment(
        profile_id="P001",
        risk_type=RiskType.OBESITY,
        risk_level=RiskLevel.MILD,
        recommendations=recs,
    )
    top = a.top_recommendations
    assert len(top) == 3
    assert top[0].priority == 1


def test_factor_summary():
    factors = [
        RiskFactor(name="a", weight=10, is_positive=False),
        RiskFactor(name="b", weight=10, is_positive=False),
        RiskFactor(name="c", weight=10, is_positive=True),
    ]
    a = RiskAssessment(
        profile_id="P001",
        risk_type=RiskType.STROKE,
        risk_level=RiskLevel.LOW,
        risk_factors=factors,
    )
    summary = a.factor_summary()
    assert summary["total"] == 3
    assert summary["risk_count"] == 2
    assert summary["protective_count"] == 1


def test_repository_latest_and_history():
    for i in range(5):
        RiskAssessmentRepository.create(
            profile_id="P001",
            risk_type=RiskType.CARDIOVASCULAR,
            risk_level=RiskLevel.MODERATE,
            score=50 + i * 5,
            assessment_date=datetime(2026, 1, 1) + timedelta(days=i * 30),
        )
    latest = RiskAssessmentRepository.latest("P001", RiskType.CARDIOVASCULAR)
    assert latest is not None
    assert latest.score == 70.0  # 最新一条

    history = RiskAssessmentRepository.history_trend(
        "P001", RiskType.CARDIOVASCULAR, limit=5
    )
    assert len(history) == 5
    assert history[0].score == 50.0  # 最早的在前
    assert history[-1].score == 70.0


def test_repository_list_high_risk():
    RiskAssessmentRepository.create(
        profile_id="P001",
        risk_type=RiskType.DIABETES,
        risk_level=RiskLevel.LOW,
        score=10,
    )
    RiskAssessmentRepository.create(
        profile_id="P001",
        risk_type=RiskType.CARDIOVASCULAR,
        risk_level=RiskLevel.HIGH,
        score=80,
    )
    RiskAssessmentRepository.create(
        profile_id="P001",
        risk_type=RiskType.STROKE,
        risk_level=RiskLevel.VERY_HIGH,
        score=95,
    )
    high = RiskAssessmentRepository.list_high_risk("P001")
    assert len(high) == 2
    types = {r.risk_type for r in high}
    assert RiskType.CARDIOVASCULAR in types
    assert RiskType.STROKE in types
