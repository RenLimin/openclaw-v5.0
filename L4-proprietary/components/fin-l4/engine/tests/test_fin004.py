"""
FIN-004 利率服务测试
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from decimal import Decimal
from datetime import date
from fin004_rate import (
    RateEngine, RateCache,
    convert_annual_to_monthly, convert_annual_to_daily,
    convert_monthly_to_annual, convert_daily_to_annual,
    convert_rate,
    DEFAULT_LPR_1Y, DEFAULT_LPR_5Y,
)


def test_get_lpr_1y():
    """测试获取 1 年期 LPR"""
    engine = RateEngine()
    snapshot = engine.get_current_lpr("1y")

    assert snapshot.rate_type == "lpr_1y"
    assert snapshot.rate == DEFAULT_LPR_1Y
    assert snapshot.rate_pct == Decimal("3.0000")
    print(f"✅ test_get_lpr_1y passed (LPR 1Y={snapshot.rate_pct}%)")


def test_get_lpr_5y():
    """测试获取 5 年期 LPR"""
    engine = RateEngine()
    snapshot = engine.get_current_lpr("5y")

    assert snapshot.rate_type == "lpr_5y"
    assert snapshot.rate == DEFAULT_LPR_5Y
    assert snapshot.rate_pct == Decimal("3.5000")
    print(f"✅ test_get_lpr_5y passed (LPR 5Y={snapshot.rate_pct}%)")


def test_central_bank_rate():
    """测试央行基准利率"""
    engine = RateEngine()
    snapshot = engine.get_central_bank_rate("CN", "loan_1y")

    assert snapshot.rate > 0
    assert "central_bank" in snapshot.rate_type
    print(f"✅ test_central_bank_rate passed (贷款1年={snapshot.rate_pct}%)")


def test_convert_annual_to_monthly_compound():
    """测试年→月（复利）"""
    r = convert_annual_to_monthly(0.035, "compound")
    # (1.035)^(1/12) - 1 ≈ 0.0028709
    assert r > Decimal("0.0028") and r < Decimal("0.0029")
    print(f"✅ test_convert_annual_to_monthly_compound passed (3.5% → {r})")


def test_convert_annual_to_monthly_simple():
    """测试年→月（简单除法）"""
    r = convert_annual_to_monthly(0.036, "simple")
    # 0.036 / 12 = 0.003
    assert r == Decimal("0.003000")
    print(f"✅ test_convert_annual_to_monthly_simple passed (3.6% → {r})")


def test_convert_annual_to_daily():
    """测试年→日"""
    r = convert_annual_to_daily(0.0365, "simple")
    # 0.0365 / 365 = 0.0001
    assert r == Decimal("0.000100")
    print(f"✅ test_convert_annual_to_daily passed (3.65% → {r})")


def test_convert_monthly_to_annual():
    """测试月→年"""
    r = convert_monthly_to_annual(0.003, "simple")
    # 0.003 × 12 = 0.036
    assert r == Decimal("0.036000")
    print(f"✅ test_convert_monthly_to_annual passed (0.3% → {r})")


def test_convert_round_trip():
    """测试往返转换"""
    original = Decimal("0.035")
    monthly = convert_annual_to_monthly(original, "compound")
    back = convert_monthly_to_annual(monthly, "compound")
    # 往返应近似相等
    diff = abs(back - original)
    assert diff < Decimal("0.00001"), f"往返误差过大: {diff}"
    print(f"✅ test_convert_round_trip passed (3.5% → {monthly} → {back})")


def test_convert_rate_general():
    """测试通用转换函数"""
    # 年→月
    r1 = convert_rate(0.036, "annual", "monthly", "simple")
    assert r1 == Decimal("0.003000")

    # 月→年
    r2 = convert_rate(0.003, "monthly", "annual", "simple")
    assert r2 == Decimal("0.036000")

    # 年→日
    r3 = convert_rate(0.0365, "annual", "daily", "simple")
    assert r3 == Decimal("0.000100")

    # 同周期不变
    r4 = convert_rate(0.035, "annual", "annual")
    assert r4 == Decimal("0.035000")

    print("✅ test_convert_rate_general passed")


def test_rate_cache():
    """测试缓存读写"""
    import tempfile
    cache = RateCache(cache_dir=tempfile.mkdtemp())

    from fin004_rate import RateSnapshot
    from datetime import datetime

    snapshot = RateSnapshot(
        rate_type="test_rate",
        rate=Decimal("0.035"),
        effective_date=date(2026, 1, 1),
        source="test",
        fetched_at=datetime.now(),
    )

    cache.set(snapshot)
    loaded = cache.get("test_rate")

    assert loaded is not None
    assert loaded.rate == Decimal("0.035")
    assert loaded.is_cached is True
    assert loaded.is_expired is False

    print("✅ test_rate_cache passed")


def test_rate_cache_expiry():
    """测试缓存过期"""
    import tempfile
    cache = RateCache(cache_dir=tempfile.mkdtemp())

    from fin004_rate import RateSnapshot
    from datetime import datetime, timedelta

    snapshot = RateSnapshot(
        rate_type="test_expired",
        rate=Decimal("0.035"),
        effective_date=date(2026, 1, 1),
        source="test",
        fetched_at=datetime.now() - timedelta(hours=25),  # 25 小时前
    )

    cache.set(snapshot)
    loaded = cache.get("test_expired")

    assert loaded is not None
    assert loaded.is_expired is True

    print("✅ test_rate_cache_expiry passed")


def test_rate_history():
    """测试利率历史"""
    engine = RateEngine()
    history = engine.get_rate_history(
        "lpr_5y",
        date(2024, 1, 1),
        date(2026, 9, 1),
    )

    assert history.rate_type == "lpr_5y"
    assert len(history.rates) > 0

    # 所有利率 > 0
    for r in history.rates:
        assert r.rate > 0

    print(f"✅ test_rate_history passed ({len(history.rates)} 个数据点)")


def test_get_multiple_rates():
    """测试批量获取"""
    engine = RateEngine()
    results = engine.get_multiple_rates(["lpr_1y", "lpr_5y"])

    assert "lpr_1y" in results
    assert "lpr_5y" in results
    assert results["lpr_1y"].rate == DEFAULT_LPR_1Y
    assert results["lpr_5y"].rate == DEFAULT_LPR_5Y

    print("✅ test_get_multiple_rates passed")


def test_convert_daily_to_annual():
    """测试日→年"""
    r = convert_daily_to_annual(Decimal("0.0001"), "simple")
    # 0.0001 × 365 = 0.0365
    assert r == Decimal("0.036500")
    print(f"✅ test_convert_daily_to_annual passed (0.01‰ → {r})")


if __name__ == "__main__":
    test_get_lpr_1y()
    test_get_lpr_5y()
    test_central_bank_rate()
    test_convert_annual_to_monthly_compound()
    test_convert_annual_to_monthly_simple()
    test_convert_annual_to_daily()
    test_convert_monthly_to_annual()
    test_convert_round_trip()
    test_convert_rate_general()
    test_rate_cache()
    test_rate_cache_expiry()
    test_rate_history()
    test_get_multiple_rates()
    test_convert_daily_to_annual()
    print("\n🎉 FIN-004 全部测试通过!")
