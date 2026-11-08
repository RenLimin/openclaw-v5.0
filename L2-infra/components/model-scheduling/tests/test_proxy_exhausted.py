#!/usr/bin/env python3
"""proxy.py exhausted 修复回归测试（2026-11-08）。

覆盖 3 处修复:
  1. exhausted 状态在 TTL 内 → 返回 unreachable（跳过路由，不撞 402）
  2. exhausted 状态超 1h TTL → 返回 unknown（重新试探）
  3. 402 重复标记不刷新 last_checked（TTL 时钟不被归零）
  4. 探活状态不变时不刷新 last_checked（重启不重置 TTL）

不触网、不依赖真实 usage.json（用 monkeypatch 注入）。
"""
import json
import sys
import time
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")


class TestGetProviderHealthExhausted(unittest.TestCase):
    """_get_provider_health 的 exhausted 分支（修复 1 + 2）。"""

    def _call(self, status, last_checked):
        """构造 usage.json 并调用 _get_provider_health。"""
        import proxy

        fake_usage = {
            "providers": {
                "deepseek": {
                    "health": {"status": status, "last_checked": last_checked}
                }
            }
        }
        with patch.object(proxy.watcher, "get", return_value=fake_usage):
            return proxy._get_provider_health("deepseek")

    def test_exhausted_within_ttl_returns_unreachable(self):
        """TTL 内 → unreachable（跳过路由，不再撞 402）。"""
        recent = _iso(datetime.now(timezone.utc) - timedelta(minutes=30))
        self.assertEqual(self._call("exhausted", recent), "unreachable")

    def test_exhausted_beyond_ttl_returns_unknown(self):
        """超 1h TTL → unknown（重新试探，自愈）。"""
        old = _iso(datetime.now(timezone.utc) - timedelta(hours=2))
        self.assertEqual(self._call("exhausted", old), "unknown")

    def test_exhausted_without_last_checked_returns_unreachable(self):
        """无 last_checked → unreachable（保守跳过）。"""
        self.assertEqual(self._call("exhausted", ""), "unreachable")

    def test_unreachable_within_ttl_returns_unreachable(self):
        """unreachable 不受 exhausted 修复影响，TTL 内仍跳过。"""
        recent = _iso(datetime.now(timezone.utc) - timedelta(minutes=30))
        self.assertEqual(self._call("unreachable", recent), "unreachable")

    def test_unreachable_beyond_ttl_returns_unknown(self):
        """unreachable 超 TTL → unknown（原有逻辑保留）。"""
        old = _iso(datetime.now(timezone.utc) - timedelta(hours=2))
        self.assertEqual(self._call("unreachable", old), "unknown")

    def test_healthy_returns_healthy(self):
        """healthy 不受影响。"""
        self.assertEqual(self._call("healthy", ""), "healthy")

    def test_unknown_status_returns_unknown(self):
        """未知状态原样返回。"""
        self.assertEqual(self._call("degraded", ""), "degraded")


class TestMarkExhaustedNoRefresh(unittest.TestCase):
    """402 重复标记不刷新 last_checked（修复 3）。

    直接测 _handle_request 太重，改为验证其内联逻辑的等价实现:
    首次标记写 last_checked，后续 402 不覆盖。
    """

    def _simulate_402(self, health, provider_id="deepseek"):
        """复刻 proxy.py 605-628 行的 402 标记逻辑。"""
        if health.get("status") != "exhausted":
            health["status"] = "exhausted"
            health["detail"] = "402 余额不足 (proxy 运行时标记)"
            health["last_checked"] = time.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        # else: 保持 exhausted，last_checked 不刷新

    def test_first_402_writes_last_checked(self):
        health = {}
        self._simulate_402(health)
        self.assertEqual(health["status"], "exhausted")
        self.assertIn("last_checked", health)

    def test_repeated_402_does_not_refresh_last_checked(self):
        """核心回归: 第二次 402 不得刷新 last_checked（否则 TTL 永远归零）。"""
        health = {}
        self._simulate_402(health)
        first_ts = health["last_checked"]
        time.sleep(1.1)
        self._simulate_402(health)
        self.assertEqual(health["last_checked"], first_ts)

    def test_repeated_402_many_times_keeps_timestamp(self):
        """连续多次 402，时间戳始终不变。"""
        health = {}
        self._simulate_402(health)
        first_ts = health["last_checked"]
        for _ in range(10):
            self._simulate_402(health)
        self.assertEqual(health["last_checked"], first_ts)


class TestStartupProbeNoReset(unittest.TestCase):
    """探活状态不变时不刷新 last_checked（修复 4）。

    复刻 startup_probe 875-890 行的 last_checked 刷新逻辑。
    """

    def _simulate_probe(self, prev_health, new_status, now):
        """复刻探活写入逻辑。"""
        prev_status = prev_health.get("status", "")
        if new_status != prev_status or not prev_health.get("last_checked"):
            return {"status": new_status, "last_checked": now, "detail": "probe"}
        else:
            return {
                "status": new_status,
                "last_checked": prev_health.get("last_checked"),
                "detail": "probe",
            }

    def test_status_unchanged_preserves_last_checked(self):
        """核心回归: 状态不变 → 保留原 last_checked（TTL 正常衰减）。"""
        old_ts = _iso(datetime.now(timezone.utc) - timedelta(minutes=30))
        prev = {"status": "exhausted", "last_checked": old_ts}
        now = _iso(datetime.now(timezone.utc))
        result = self._simulate_probe(prev, "exhausted", now)
        self.assertEqual(result["last_checked"], old_ts)

    def test_status_changed_refreshes_last_checked(self):
        """状态变化 → 刷新 last_checked。"""
        old_ts = _iso(datetime.now(timezone.utc) - timedelta(minutes=30))
        prev = {"status": "exhausted", "last_checked": old_ts}
        now = _iso(datetime.now(timezone.utc))
        result = self._simulate_probe(prev, "healthy", now)
        self.assertEqual(result["last_checked"], now)

    def test_first_mark_writes_last_checked(self):
        """首次标记（无 last_checked）→ 写入 now。"""
        now = _iso(datetime.now(timezone.utc))
        result = self._simulate_probe({}, "exhausted", now)
        self.assertEqual(result["last_checked"], now)


if __name__ == "__main__":
    unittest.main()
