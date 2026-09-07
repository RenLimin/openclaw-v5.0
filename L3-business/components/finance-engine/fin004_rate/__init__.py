"""
FIN-004 利率服务

功能:
- LPR 利率查询（1年期 / 5年期+）
- 央行基准利率查询
- 利率历史数据
- 利率转换（年↔月↔日，复利 / 简单除法）
- 本地缓存（TTL=24h）

数据源优先级:
1. API Ninjas（免费额度 10K/月）
2. Trading Economics（付费有免费层）
3. 央行/银行官网（爬虫兜底）

注意: 网络请求是 FIN-xxx 中唯一允许副作用的组件
"""

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Dict
from datetime import date, datetime, timedelta
import json
import os
import uuid


# ========== 常量 ==========

# 缓存 TTL（24 小时）
CACHE_TTL_HOURS = 24

# 缓存目录
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".openclaw", "cache", "fin004_rate")

# 默认 LPR 参考值（2026-09 最新）
DEFAULT_LPR_1Y = Decimal("0.0300")   # 3.00%
DEFAULT_LPR_5Y = Decimal("0.0350")   # 3.50%

# 央行基准利率（简化参考值）
CENTRAL_BANK_RATES = {
    "CN": {
        "deposit_overnight": Decimal("0.0010"),
        "deposit_3m": Decimal("0.0110"),
        "deposit_6m": Decimal("0.0130"),
        "deposit_1y": Decimal("0.0150"),
        "deposit_2y": Decimal("0.0210"),
        "deposit_3y": Decimal("0.0275"),
        "deposit_5y": Decimal("0.0275"),
        "loan_6m": Decimal("0.0435"),
        "loan_1y": Decimal("0.0435"),
        "loan_1_3y": Decimal("0.0475"),
        "loan_3_5y": Decimal("0.0490"),
        "loan_5y_plus": Decimal("0.0490"),
    }
}


# ========== 数据模型 ==========

@dataclass
class RateSnapshot:
    """利率快照"""
    rate_type: str              # "lpr_1y" / "lpr_5y" / "central_bank_cn" / ...
    rate: Decimal               # 利率值（小数，如 0.035 = 3.5%）
    effective_date: date        # 生效日期
    source: str                 # 数据来源
    fetched_at: datetime        # 获取时间
    is_cached: bool = False     # 是否来自缓存
    is_expired: bool = False    # 是否过期
    metadata: dict = field(default_factory=dict)

    @property
    def rate_pct(self) -> Decimal:
        """返回百分比值"""
        return (self.rate * Decimal("100")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


@dataclass
class RateHistory:
    """利率历史"""
    rate_type: str
    rates: List[RateSnapshot]
    start_date: date
    end_date: date


# ========== 缓存管理 ==========

class RateCache:
    """本地文件缓存"""

    def __init__(self, cache_dir: str = CACHE_DIR):
        self._cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def _cache_path(self, rate_type: str) -> str:
        return os.path.join(self._cache_dir, f"{rate_type}.json")

    def get(self, rate_type: str) -> Optional[RateSnapshot]:
        """获取缓存"""
        path = self._cache_path(rate_type)
        if not os.path.exists(path):
            return None

        try:
            with open(path, 'r') as f:
                data = json.load(f)

            fetched_at = datetime.fromisoformat(data["fetched_at"])
            age = datetime.now() - fetched_at
            is_expired = age > timedelta(hours=CACHE_TTL_HOURS)

            return RateSnapshot(
                rate_type=data["rate_type"],
                rate=Decimal(data["rate"]),
                effective_date=date.fromisoformat(data["effective_date"]),
                source=data["source"],
                fetched_at=fetched_at,
                is_cached=True,
                is_expired=is_expired,
                metadata=data.get("metadata", {}),
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            return None

    def set(self, snapshot: RateSnapshot):
        """写入缓存"""
        path = self._cache_path(snapshot.rate_type)
        data = {
            "rate_type": snapshot.rate_type,
            "rate": str(snapshot.rate),
            "effective_date": snapshot.effective_date.isoformat(),
            "source": snapshot.source,
            "fetched_at": snapshot.fetched_at.isoformat(),
            "metadata": snapshot.metadata,
        }
        with open(path, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def clear(self):
        """清除所有缓存"""
        if os.path.exists(self._cache_dir):
            for f in os.listdir(self._cache_dir):
                if f.endswith('.json'):
                    os.remove(os.path.join(self._cache_dir, f))


# ========== 利率转换 ==========

def convert_annual_to_monthly(annual_rate, method: str = "compound") -> Decimal:
    """
    年利率 → 月利率

    method="compound": r_monthly = (1 + r_annual)^(1/12) - 1
    method="simple":   r_monthly = r_annual / 12
    """
    r = Decimal(str(annual_rate))
    if method == "simple":
        return (r / Decimal("12")).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    else:
        # 复利换算（用 float 做幂运算再转回 Decimal）
        import math
        r_float = float(r)
        monthly = (1 + r_float) ** (1.0 / 12.0) - 1.0
        return Decimal(str(monthly)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def convert_annual_to_daily(annual_rate, method: str = "compound") -> Decimal:
    """
    年利率 → 日利率

    method="compound": r_daily = (1 + r_annual)^(1/365) - 1
    method="simple":   r_daily = r_annual / 365
    """
    r = Decimal(str(annual_rate))
    if method == "simple":
        return (r / Decimal("365")).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    else:
        import math
        r_float = float(r)
        daily = (1 + r_float) ** (1.0 / 365.0) - 1.0
        return Decimal(str(daily)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def convert_monthly_to_annual(monthly_rate, method: str = "compound") -> Decimal:
    """
    月利率 → 年利率

    method="compound": r_annual = (1 + r_monthly)^12 - 1
    method="simple":   r_annual = r_monthly × 12
    """
    r = Decimal(str(monthly_rate))
    if method == "simple":
        return (r * Decimal("12")).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    else:
        import math
        r_float = float(r)
        annual = (1 + r_float) ** 12 - 1.0
        return Decimal(str(annual)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def convert_daily_to_annual(daily_rate, method: str = "compound") -> Decimal:
    """
    日利率 → 年利率

    method="compound": r_annual = (1 + r_daily)^365 - 1
    method="simple":   r_annual = r_daily × 365
    """
    r = Decimal(str(daily_rate))
    if method == "simple":
        return (r * Decimal("365")).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    else:
        import math
        r_float = float(r)
        annual = (1 + r_float) ** 365 - 1.0
        return Decimal(str(annual)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def convert_rate(annual_rate, from_period: str = "annual", to_period: str = "monthly",
                 method: str = "compound") -> Decimal:
    """
    通用利率转换

    from_period / to_period: "annual" / "monthly" / "daily"
    method: "compound" / "simple"
    """
    r = Decimal(str(annual_rate))

    if from_period == to_period:
        return r.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    # 先转到年
    if from_period == "monthly":
        r = convert_monthly_to_annual(r, method)
    elif from_period == "daily":
        r = convert_daily_to_annual(r, method)

    # 再转到目标
    if to_period == "monthly":
        return convert_annual_to_monthly(r, method)
    elif to_period == "daily":
        return convert_annual_to_daily(r, method)
    else:
        return r.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


# ========== 引擎 ==========

class RateEngine:
    """利率服务引擎"""

    def __init__(self, cache: Optional[RateCache] = None):
        self._cache = cache or RateCache()

    # ---------- LPR ----------

    def get_current_lpr(self, term: str = "5y") -> RateSnapshot:
        """
        获取当前 LPR

        term: "1y" / "5y"
        """
        rate_type = f"lpr_{term}"
        cached = self._cache.get(rate_type)

        if cached and not cached.is_expired:
            return cached

        # 缓存未命中或过期，使用默认值（实际场景调用 API）
        if term == "1y":
            rate = DEFAULT_LPR_1Y
        else:
            rate = DEFAULT_LPR_5Y

        snapshot = RateSnapshot(
            rate_type=rate_type,
            rate=rate,
            effective_date=date.today(),
            source="default_reference",
            fetched_at=datetime.now(),
            is_cached=False,
            metadata={"note": "默认参考值，实际使用需配置 API Ninjas"},
        )
        self._cache.set(snapshot)
        return snapshot

    # ---------- 央行利率 ----------

    def get_central_bank_rate(self, country: str = "CN", rate_key: str = "loan_1y") -> RateSnapshot:
        """获取央行基准利率"""
        rate_type = f"central_bank_{country.lower()}_{rate_key}"
        cached = self._cache.get(rate_type)

        if cached and not cached.is_expired:
            return cached

        country_rates = CENTRAL_BANK_RATES.get(country, {})
        rate = country_rates.get(rate_key, Decimal("0.0435"))  # 默认 1 年期贷款基准

        snapshot = RateSnapshot(
            rate_type=rate_type,
            rate=rate,
            effective_date=date.today(),
            source="pboc_reference",
            fetched_at=datetime.now(),
            metadata={"country": country, "rate_key": rate_key},
        )
        self._cache.set(snapshot)
        return snapshot

    # ---------- 利率历史（模拟） ----------

    def get_rate_history(
        self,
        rate_type: str,
        start_date: date,
        end_date: date,
    ) -> RateHistory:
        """
        获取利率历史（模拟数据）

        实际场景应从 API 或数据库获取，这里返回基于默认值的模拟序列
        """
        rates: List[RateSnapshot] = []
        current = start_date

        # 模拟：基于默认值 ±0.25% 的波动
        import random
        random.seed(hash(rate_type) + start_date.year)

        base_rate = DEFAULT_LPR_5Y if "5y" in rate_type else DEFAULT_LPR_1Y

        while current <= end_date:
            # 每季度一个数据点
            if current.month in (3, 6, 9, 12) and current.day == 1:
                noise = Decimal(str(random.uniform(-0.0025, 0.0025)))
                rate = base_rate + noise
                rate = rate.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

                rates.append(RateSnapshot(
                    rate_type=rate_type,
                    rate=rate,
                    effective_date=current,
                    source="simulated",
                    fetched_at=datetime.now(),
                ))

            # 下一天
            if current.month == 12:
                current = date(current.year + 1, 1, 1)
            else:
                current = date(current.year, current.month + 1, 1)

        return RateHistory(
            rate_type=rate_type,
            rates=rates,
            start_date=start_date,
            end_date=end_date,
        )

    # ---------- 利率转换（便捷方法） ----------

    def convert(
        self,
        rate_value,
        from_period: str = "annual",
        to_period: str = "monthly",
        method: str = "compound",
    ) -> Decimal:
        """利率转换便捷方法"""
        return convert_rate(rate_value, from_period, to_period, method)

    # ---------- 批量获取 ----------

    def get_multiple_rates(self, rate_types: List[str]) -> Dict[str, RateSnapshot]:
        """批量获取多种利率"""
        results = {}
        for rt in rate_types:
            if rt.startswith("lpr_"):
                term = rt.split("_")[1] if "_" in rt else "5y"
                results[rt] = self.get_current_lpr(term)
            elif rt.startswith("central_bank_"):
                parts = rt.split("_", 2)
                country = parts[2].split("_")[0] if len(parts) > 2 else "CN"
                rate_key = "_".join(parts[2].split("_")[1:]) if len(parts) > 2 else "loan_1y"
                results[rt] = self.get_central_bank_rate(country, rate_key)
            else:
                results[rt] = self.get_current_lpr("5y")
        return results
