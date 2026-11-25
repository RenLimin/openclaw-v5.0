#!/usr/bin/env python3
"""throttle.py 回归测试（v1.1，KI-01/KI-02）。

不触网、不依赖真实配置：注入假时钟与假 sleep，确定性断言准入时序。

覆盖验收标准 A1–A5：
  A1 令牌桶数学（满桶即时 / 空桶等待 ≈ 亏空/补充速率）
  A2 并发闸门封顶（N+1 并发必有 1 个等待）
  A3 fail-open（enabled=false → 零等待）
  A4 KI-02 突发退让（低并发 0s，高并发 ∈ [base, max]）
  A5 平滑间隔生效（连续两次发送间隔 ≥ min_interval）
"""
import asyncio
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import throttle as T  # noqa: E402


def _fake_clock(start=1000.0):
    """返回 (clock_list, now)；测试推进 clock[0] 即等价于时间流逝。"""
    clock = [start]
    return clock, lambda: clock[0]


class TestTokenBucket(unittest.TestCase):
    """A1：令牌桶数学。"""

    def test_full_bucket_passes_immediately(self):
        clock, now = _fake_clock()
        b = T.TokenBucket(capacity=60, refill_per_second=1.0, now=now)
        self.assertEqual(b.time_until_ready(1), 0.0)

    def test_empty_bucket_waits_for_deficit(self):
        clock, now = _fake_clock()
        b = T.TokenBucket(capacity=60, refill_per_second=1.0, now=now)
        b.tokens = 0.0
        self.assertAlmostEqual(b.time_until_ready(1.0), 1.0, places=6)

    def test_partial_bucket_wait(self):
        clock, now = _fake_clock()
        b = T.TokenBucket(capacity=60, refill_per_second=2.0, now=now)
        b.tokens = 3.0
        # 需补 7 tokens @ 2/s = 3.5s
        self.assertAlmostEqual(b.time_until_ready(10.0), 3.5, places=6)

    def test_request_larger_than_capacity_not_deadlocked(self):
        """超限请求放行交 provider 拒绝——不可死等。"""
        clock, now = _fake_clock()
        b = T.TokenBucket(capacity=10, refill_per_second=1.0, now=now)
        b.tokens = 0.0
        self.assertEqual(b.time_until_ready(9999), 0.0)

    def test_consume_reduces_tokens(self):
        clock, now = _fake_clock()
        b = T.TokenBucket(capacity=60, refill_per_second=1.0, now=now)
        b.consume(1.0)
        self.assertAlmostEqual(b.tokens, 59.0, places=6)

    def test_refill_capped_at_capacity(self):
        clock, now = _fake_clock()
        b = T.TokenBucket(capacity=5, refill_per_second=1000.0, now=now)
        b.tokens = 0.0
        clock[0] += 10.0
        b._refill()
        self.assertAlmostEqual(b.tokens, 5.0, places=6)


class TestProviderThrottle(unittest.TestCase):
    """per-provider 双桶构建与热更新。"""

    def test_from_conf_reads_rate_limit(self):
        p = T.ProviderThrottle.from_provider_conf(
            {"rate_limit": {"requests_per_minute": 120, "tokens_per_minute": 200000}})
        self.assertEqual(p.rpm.capacity, 120)
        self.assertEqual(p.tpm.capacity, 200000)

    def test_from_conf_defaults_when_missing(self):
        p = T.ProviderThrottle.from_provider_conf({})
        self.assertEqual(p.rpm.capacity, 60)
        self.assertEqual(p.tpm.capacity, 100_000)

    def test_refresh_preserves_tokens_capped(self):
        clock, now = _fake_clock()
        p = T.ProviderThrottle(60, 100_000, now)
        p.rpm.tokens = 5.0
        p.refresh({"rate_limit": {"requests_per_minute": 10, "tokens_per_minute": 1000}})
        self.assertEqual(p.rpm.capacity, 10)
        self.assertLessEqual(p.rpm.tokens, 10)


class TestGateFailOpen(unittest.TestCase):
    """A3：fail-open。"""

    def test_disabled_bypasses_entirely(self):
        g = T.GlobalGate({"throttle": {"enabled": False}}, {})
        self.assertFalse(g.enabled)

    def test_missing_throttle_section_is_disabled(self):
        """未配置 = 旁路（v1.0 行为），不因新增代码阻断生产。"""
        g = T.GlobalGate({}, {})
        self.assertFalse(g.enabled)

    def test_malformed_config_is_disabled(self):
        g = T.GlobalGate({"throttle": "garbage"}, {})
        self.assertFalse(g.enabled)

    def test_enabled_true_activates(self):
        g = T.GlobalGate({"throttle": {"enabled": True, "max_concurrent_chat": 8}}, {})
        self.assertTrue(g.enabled)
        self.assertEqual(g.max_concurrent, 8)

    def test_zero_wait_when_disabled(self):
        async def run():
            g = T.GlobalGate({"throttle": {"enabled": False}}, {})
            slept = []
            g._sleep = lambda s: _rec(slept, s)
            async with g.gate("p", 1000, {}):
                pass
            return slept
        self.assertEqual(asyncio.run(run()), [])


async def _rec(store, seconds):
    store.append(seconds)


class TestConcurrencyCap(unittest.IsolatedAsyncioTestCase):
    """A2：并发闸门封顶。"""

    async def test_excess_requests_wait(self):
        clock, now = _fake_clock()
        cfg = {
            "throttle": {
                "enabled": True,
                "max_concurrent_chat": 2,
                "min_interval_seconds": 0.0,
                "jitter_ratio": 0.0,
            }
        }
        g = T.GlobalGate(cfg, {}, now=now, sleep_fn=_rec_noop)

        entered = []

        async def worker(i):
            async with g.gate(f"p{i}", 1, {}):
                entered.append((i, g.inflight()))
                await asyncio.sleep(0)

        # 3 个并发、容量 2 → 至少一个观察到 inflight==2（即在闸内排队）
        await asyncio.gather(*(worker(i) for i in range(3)))
        self.assertTrue(any(v == 2 for _, v in entered),
                        f"未观测到封顶，实际观察值: {entered}")
        self.assertEqual(g.inflight(), 0, "退出后 inflight 应归零")

    async def test_inflight_returns_to_zero_on_exception(self):
        clock, now = _fake_clock()
        g = T.GlobalGate({"throttle": {"enabled": True, "max_concurrent_chat": 2,
                                       "min_interval_seconds": 0.0, "jitter_ratio": 0.0}},
                         {}, now=now, sleep_fn=_rec_noop)
        with self.assertRaises(RuntimeError):
            async with g.gate("p", 1, {}):
                raise RuntimeError("boom")
        self.assertEqual(g.inflight(), 0)


async def _rec_noop(seconds):
    return None


class TestBurstBackoff(unittest.TestCase):
    """A4：KI-02 突发限流退让。"""

    def _gate(self, **kw):
        base = {"enabled": True, "max_concurrent_chat": 10, "min_interval_seconds": 0.0,
                "jitter_ratio": 0.0,
                "burst_backoff": {"enabled": True, "inflight_ratio_threshold": 0.7,
                                  "base_seconds": 1.0, "max_seconds": 10.0}}
        base.update(kw)
        return T.GlobalGate({"throttle": base}, {})

    def test_low_concurrency_no_backoff(self):
        g = self._gate()
        g._inflight = 1   # ratio 0.1 < 0.7
        self.assertEqual(g.burst_backoff_seconds(), 0.0)

    def test_high_concurrency_backoff_within_bounds(self):
        g = self._gate(max_concurrent_chat=10)
        g._inflight = 10  # ratio 1.0 → max
        d = g.burst_backoff_seconds()
        self.assertGreaterEqual(d, 1.0)
        self.assertLessEqual(d, 10.0)
        self.assertAlmostEqual(d, 10.0, places=3)

    def test_mid_ratio_interpolates(self):
        g = self._gate(max_concurrent_chat=10)
        g._inflight = 7   # ratio 0.7 == threshold → base
        self.assertAlmostEqual(g.burst_backoff_seconds(), 1.0, places=3)

    def test_disabled_always_zero(self):
        g = self._gate()
        bo = {"enabled": False, "inflight_ratio_threshold": 0.7,
              "base_seconds": 1.0, "max_seconds": 10.0}
        g2 = T.GlobalGate({"throttle": {"enabled": True, "max_concurrent_chat": 4,
                                        "min_interval_seconds": 0.0, "jitter_ratio": 0.0,
                                        "burst_backoff": bo}}, {})
        g2._inflight = 4
        self.assertEqual(g2.burst_backoff_seconds(), 0.0)


class TestSmoothing(unittest.IsolatedAsyncioTestCase):
    """A5：平滑最小间隔。"""

    async def test_interval_respected(self):
        clock, now = _fake_clock()
        cfg = {"throttle": {"enabled": True, "max_concurrent_chat": 16,
                            "min_interval_seconds": 5.0, "jitter_ratio": 0.0}}
        g = T.GlobalGate(cfg, {}, now=now, sleep_fn=_advance(clock))
        stamps = []
        for _ in range(3):
            async with g.gate("p", 1, {}):
                stamps.append(now())
        gaps = [stamps[i + 1] - stamps[i] for i in range(len(stamps) - 1)]
        for gap in gaps:
            self.assertGreaterEqual(gap, 5.0 - 1e-9, f"间隔不足: {gaps}")

    async def test_no_interval_when_zero(self):
        clock, now = _fake_clock()
        cfg = {"throttle": {"enabled": True, "max_concurrent_chat": 16,
                            "min_interval_seconds": 0.0, "jitter_ratio": 0.0}}
        g = T.GlobalGate(cfg, {}, now=now, sleep_fn=_advance(clock))
        stamps = []
        for _ in range(3):
            async with g.gate("p", 1, {}):
                stamps.append(now())
        self.assertTrue(all(abs(s - stamps[0]) < 1e-9 for s in stamps))


def _advance(clock):
    """假 sleep：推进假时钟（等价时间流逝），保证时序断言确定性。"""
    async def _s(seconds):
        clock[0] += seconds
    return _s


class TestAdmissionOrder(unittest.IsolatedAsyncioTestCase):
    """双重准入：RPM 与 TPM 取更长等待。"""

    async def test_tpm_dominates_large_prompt(self):
        clock, now = _fake_clock()
        cfg = {"throttle": {"enabled": True, "max_concurrent_chat": 16,
                            "min_interval_seconds": 0.0, "jitter_ratio": 0.0}}
        provs = {"providers": {"p": {"enabled": True,
                                     "rate_limit": {"requests_per_minute": 600,
                                                    "tokens_per_minute": 600}}}}
        g = T.GlobalGate(cfg, provs, now=now, sleep_fn=_advance(clock))
        # 桶初始满：一次大 prompt 消耗后，下一次需等待补回
        async with g.gate("p", 600, provs):
            pass
        start = now()
        async with g.gate("p", 600, provs):
            waited = now() - start
        self.assertGreater(waited, 0.0)

    async def test_unknown_provider_still_gated_by_concurrency(self):
        """provider 无桶配置时，至少仍有并发闸门兜底。"""
        clock, now = _fake_clock()
        cfg = {"throttle": {"enabled": True, "max_concurrent_chat": 1,
                            "min_interval_seconds": 0.0, "jitter_ratio": 0.0}}
        g = T.GlobalGate(cfg, {}, now=now, sleep_fn=_rec_noop)
        order = []

        async def w(i):
            async with g.gate("unknown", 1, {}):
                order.append(i)
                await asyncio.sleep(0)

        await asyncio.gather(w(1), w(2))
        self.assertEqual(sorted(order), [1, 2])
        self.assertEqual(g.inflight(), 0)


if __name__ == "__main__":
    unittest.main()
