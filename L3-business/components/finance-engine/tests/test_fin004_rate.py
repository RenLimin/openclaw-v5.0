"""FIN-004 利率引擎测试 — 利率转换、LPR查询、央行利率"""

import pytest
from decimal import Decimal
from datetime import date

from fin004_rate import (
    convert_annual_to_monthly, convert_annual_to_daily,
    convert_monthly_to_annual, convert_daily_to_annual,
    convert_rate, RateEngine, RateSnapshot,
)


class TestRateConversion:
    """利率转换"""

    def test_annual_to_monthly_simple(self):
        result = convert_annual_to_monthly(Decimal("0.06"), method="simple")
        expected = Decimal("0.06") / Decimal("12")
        assert abs(result - expected.quantize(Decimal("0.000001"))) < Decimal("0.000001")

    def test_annual_to_monthly_compound(self):
        result = convert_annual_to_monthly(Decimal("0.06"), method="compound")
        # 复利换算: (1 + 0.06)^(1/12) - 1 ≈ 0.004868
        assert result > 0
        assert result < Decimal("0.06")

    def test_annual_to_daily_simple(self):
        result = convert_annual_to_daily(Decimal("0.06"), method="simple")
        expected = Decimal("0.06") / Decimal("365")
        assert abs(result - expected.quantize(Decimal("0.000001"))) < Decimal("0.000001")

    def test_monthly_to_annual_simple(self):
        result = convert_monthly_to_annual(Decimal("0.005"), method="simple")
        expected = Decimal("0.005") * Decimal("12")
        assert result == expected.quantize(Decimal("0.000001"))

    def test_daily_to_annual_simple(self):
        result = convert_daily_to_annual(Decimal("0.0001"), method="simple")
        expected = Decimal("0.0001") * Decimal("365")
        assert result == expected.quantize(Decimal("0.000001"))

    def test_convert_rate_same_period(self):
        """相同周期直接返回"""
        result = convert_rate(Decimal("0.05"), from_period="annual", to_period="annual")
        assert result == Decimal("0.05")


class TestRateEngine:
    """利率引擎"""

    def test_get_current_lpr_1y(self, tmp_path):
        from fin004_rate import RateCache
        cache = RateCache(cache_dir=str(tmp_path / "cache"))
        engine = RateEngine(cache=cache)
        snapshot = engine.get_current_lpr(term="1y")
        assert snapshot.rate > 0
        assert snapshot.rate_type == "lpr_1y"

    def test_get_current_lpr_5y(self, tmp_path):
        from fin004_rate import RateCache
        cache = RateCache(cache_dir=str(tmp_path / "cache"))
        engine = RateEngine(cache=cache)
        snapshot = engine.get_current_lpr(term="5y")
        assert snapshot.rate > 0
        assert snapshot.rate_type == "lpr_5y"

    def test_get_central_bank_rate(self, tmp_path):
        from fin004_rate import RateCache
        cache = RateCache(cache_dir=str(tmp_path / "cache"))
        engine = RateEngine(cache=cache)
        snapshot = engine.get_central_bank_rate(country="CN", rate_key="loan_1y")
        assert snapshot.rate > 0

    def test_rate_snapshot_pct(self):
        snapshot = RateSnapshot(
            rate_type="test", rate=Decimal("0.035"),
            effective_date=date.today(), source="test",
            fetched_at=__import__("datetime").datetime.now(),
        )
        assert snapshot.rate_pct == Decimal("3.5000")

    def test_convert_method(self, tmp_path):
        from fin004_rate import RateCache
        cache = RateCache(cache_dir=str(tmp_path / "cache"))
        engine = RateEngine(cache=cache)
        result = engine.convert(0.06, from_period="annual", to_period="monthly")
        assert result > 0


class TestRateCache:
    """缓存管理"""

    def test_cache_set_and_get(self, tmp_path):
        from fin004_rate import RateCache
        cache = RateCache(cache_dir=str(tmp_path / "cache"))
        snapshot = RateSnapshot(
            rate_type="test_rate", rate=Decimal("0.035"),
            effective_date=date.today(), source="test",
            fetched_at=__import__("datetime").datetime.now(),
        )
        cache.set(snapshot)
        cached = cache.get("test_rate")
        assert cached is not None
        assert cached.rate == Decimal("0.035")
        assert cached.is_cached is True

    def test_cache_nonexistent(self, tmp_path):
        from fin004_rate import RateCache
        cache = RateCache(cache_dir=str(tmp_path / "cache"))
        result = cache.get("nonexistent")
        assert result is None

    def test_cache_clear(self, tmp_path):
        from fin004_rate import RateCache
        cache = RateCache(cache_dir=str(tmp_path / "cache"))
        snapshot = RateSnapshot(
            rate_type="test_rate", rate=Decimal("0.035"),
            effective_date=date.today(), source="test",
            fetched_at=__import__("datetime").datetime.now(),
        )
        cache.set(snapshot)
        cache.clear()
        assert cache.get("test_rate") is None
