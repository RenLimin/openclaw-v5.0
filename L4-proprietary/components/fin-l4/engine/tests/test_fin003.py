"""
FIN-003 保险产品核算测试
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from decimal import Decimal
from datetime import date
from fin003_insurance import (
    InsuranceEngine, InsuranceType, PolicyStatus,
    DIVIDEND_RATES, DISCLAIMER,
)


def test_create_whole_life_policy():
    """测试创建终身寿险保单"""
    engine = InsuranceEngine()
    policy = engine.create_policy(
        policy_type=InsuranceType.WHOLE_LIFE,
        product_name="金享人生终身寿险",
        sum_assured=500000,
        annual_premium=10000,
        term_years=99,
        payment_years=20,
        insured_age=30,
        insured_gender="M",
    )

    assert policy.id.startswith("POL-")
    assert policy.policy_type == InsuranceType.WHOLE_LIFE
    assert policy.sum_assured == Decimal("500000.00")
    assert policy.annual_premium == Decimal("10000.00")
    assert policy.supports_cash_value is True
    assert policy.supports_irr is True
    print(f"✅ test_create_whole_life_policy passed (id={policy.id})")


def test_create_term_life_policy():
    """测试定期寿险（无现金价值）"""
    engine = InsuranceEngine()
    policy = engine.create_policy(
        policy_type=InsuranceType.TERM_LIFE,
        product_name="定期寿险",
        sum_assured=1000000,
        annual_premium=2000,
        term_years=30,
        payment_years=30,
        insured_age=35,
    )

    assert policy.supports_cash_value is False
    assert policy.supports_surrender is False
    assert policy.supports_irr is False

    # 尝试计算现金价值应报错
    try:
        engine.calculate_cash_value(policy.id, 5)
        assert False, "应抛出异常"
    except ValueError as e:
        assert "不支持" in str(e)

    print("✅ test_create_term_life_policy passed")


def test_cash_value_whole_life():
    """测试终身寿险现金价值"""
    engine = InsuranceEngine()
    policy = engine.create_policy(
        policy_type=InsuranceType.WHOLE_LIFE,
        product_name="金享人生",
        sum_assured=500000,
        annual_premium=10000,
        term_years=99,
        payment_years=20,
        insured_age=30,
    )

    cv_5 = engine.calculate_cash_value(policy.id, 5)
    cv_10 = engine.calculate_cash_value(policy.id, 10)
    cv_20 = engine.calculate_cash_value(policy.id, 20)

    # 现金价值应递增
    assert cv_5.total_cv < cv_10.total_cv < cv_20.total_cv

    # 保证现金价值 < 非保证（中档）
    assert cv_10.guaranteed_cv <= cv_10.non_guaranteed_cv

    # 含免责声明
    assert "⚠️" in cv_10.disclaimer

    print(f"✅ test_cash_value_whole_life passed (5年={cv_5.total_cv}, 10年={cv_10.total_cv}, 20年={cv_20.total_cv})")


def test_cash_value_scenarios():
    """测试三档演示"""
    engine = InsuranceEngine()
    policy = engine.create_policy(
        policy_type=InsuranceType.WHOLE_LIFE,
        product_name="金享人生",
        sum_assured=500000,
        annual_premium=10000,
        term_years=99,
        payment_years=20,
        insured_age=30,
    )

    low = engine.calculate_cash_value(policy.id, 10, "low")
    mid = engine.calculate_cash_value(policy.id, 10, "mid")
    high = engine.calculate_cash_value(policy.id, 10, "high")

    # 低 < 中 < 高
    assert low.total_cv < mid.total_cv < high.total_cv

    # 三档都有值
    assert len(mid.dividend_details) == 3
    assert "low" in mid.dividend_details
    assert "mid" in mid.dividend_details
    assert "high" in mid.dividend_details

    print(f"✅ test_cash_value_scenarios passed (低={low.total_cv}, 中={mid.total_cv}, 高={high.total_cv})")


def test_surrender_value():
    """测试退保价值"""
    engine = InsuranceEngine()
    policy = engine.create_policy(
        policy_type=InsuranceType.WHOLE_LIFE,
        product_name="金享人生",
        sum_assured=500000,
        annual_premium=10000,
        term_years=99,
        payment_years=20,
        insured_age=30,
    )

    sv_1 = engine.calculate_surrender_value(policy.id, 1)
    sv_3 = engine.calculate_surrender_value(policy.id, 3)
    sv_10 = engine.calculate_surrender_value(policy.id, 10)

    # 首年退保手续费 5%
    assert sv_1.surrender_fee_rate == Decimal("0.05")
    assert sv_1.surrender_value < sv_1.cash_value

    # 第 3 年手续费 3%
    assert sv_3.surrender_fee_rate == Decimal("0.03")

    # 10 年后无手续费
    assert sv_10.surrender_fee_rate == Decimal("0")
    assert sv_10.surrender_value == sv_10.cash_value

    print(f"✅ test_surrender_value passed (1年={sv_1.surrender_value}, 3年={sv_3.surrender_value}, 10年={sv_10.surrender_value})")


def test_irr_convergence():
    """测试 IRR 收敛"""
    engine = InsuranceEngine()
    policy = engine.create_policy(
        policy_type=InsuranceType.WHOLE_LIFE,
        product_name="金享人生",
        sum_assured=500000,
        annual_premium=10000,
        term_years=99,
        payment_years=20,
        insured_age=30,
    )

    irr_result = engine.calculate_irr(policy.id, 20)

    assert irr_result.converged is True
    assert irr_result.iterations < 200
    assert irr_result.calculation_method == "newton"
    assert irr_result.irr > 0  # IRR 应为正

    print(f"✅ test_irr_convergence passed (IRR={irr_result.irr}%, 迭代={irr_result.iterations}次)")


def test_irr_endowment():
    """测试两全保险 IRR"""
    engine = InsuranceEngine()
    policy = engine.create_policy(
        policy_type=InsuranceType.ENDOWMENT,
        product_name="两全保险",
        sum_assured=200000,
        annual_premium=15000,
        term_years=30,
        payment_years=10,
        insured_age=25,
    )

    irr_result = engine.calculate_irr(policy.id, 30)
    assert irr_result.converged is True
    assert irr_result.irr > 0

    print(f"✅ test_irr_endowment passed (IRR={irr_result.irr}%)")


def test_dividend_projection():
    """测试红利演示"""
    engine = InsuranceEngine()
    policy = engine.create_policy(
        policy_type=InsuranceType.WHOLE_LIFE,
        product_name="金享人生",
        sum_assured=500000,
        annual_premium=10000,
        term_years=99,
        payment_years=20,
        insured_age=30,
    )

    proj = engine.project_dividend(policy.id, 10, "mid")

    assert proj.scenario == "mid"
    assert proj.dividend_rate == DIVIDEND_RATES["mid"]
    assert proj.annual_dividend >= 0
    assert proj.cumulative_dividend >= 0
    assert proj.total_cv > 0

    print(f"✅ test_dividend_projection passed (年红利={proj.annual_dividend}, 累计={proj.cumulative_dividend})")


def test_medical_no_cash_value():
    """测试医疗险（消费型，无现金价值）"""
    engine = InsuranceEngine()
    policy = engine.create_policy(
        policy_type=InsuranceType.MEDICAL,
        product_name="百万医疗",
        sum_assured=600000,
        annual_premium=500,
        term_years=1,
        payment_years=1,
        insured_age=30,
    )

    assert policy.supports_cash_value is False

    try:
        engine.calculate_cash_value(policy.id, 1)
        assert False, "应抛出异常"
    except ValueError:
        pass

    print("✅ test_medical_no_cash_value passed")


def test_project_all_scenarios():
    """测试三档汇总"""
    engine = InsuranceEngine()
    policy = engine.create_policy(
        policy_type=InsuranceType.WHOLE_LIFE,
        product_name="金享人生",
        sum_assured=500000,
        annual_premium=10000,
        term_years=99,
        payment_years=20,
        insured_age=30,
    )

    results = engine.project_all_scenarios(policy.id, 15)
    assert len(results) == 3
    assert results["low"].total_cv < results["mid"].total_cv < results["high"].total_cv

    print(f"✅ test_project_all_scenarios passed (低={results['low'].total_cv}, 中={results['mid'].total_cv}, 高={results['high'].total_cv})")


if __name__ == "__main__":
    test_create_whole_life_policy()
    test_create_term_life_policy()
    test_cash_value_whole_life()
    test_cash_value_scenarios()
    test_surrender_value()
    test_irr_convergence()
    test_irr_endowment()
    test_dividend_projection()
    test_medical_no_cash_value()
    test_project_all_scenarios()
    print("\n🎉 FIN-003 全部测试通过!")
