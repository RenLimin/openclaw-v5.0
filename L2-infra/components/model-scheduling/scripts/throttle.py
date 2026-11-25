#!/usr/bin/env python3
"""跨会话错峰与突发限流治理 — model-scheduling v1.1。

背景：KNOWN-ISSUES.md KI-01（chat 无并发闸门）/ KI-02（突发限流就地继续放大并发）。
设计：DESIGN-DETAIL-v1.1-throttle.md。

业界共识（Alibaba Cloud Model Studio / LiteLLM / Spheron 一致）：
    估算输入 tokens → 双重准入(RPM & TPM) → 并发锁 → 流量整形 → 发送 → 结算输出
单一手段不足：RPM 桶（吞吐）+ TPM 桶（大 prompt）+ 全局信号量（并发）+ 平滑 jitter。

失败开放（fail-open）：配置缺失/关闭/解析失败 → 整体旁路，行为退回 v1.0。
"""
from __future__ import annotations

import asyncio
import random
import threading
import time
from contextlib import asynccontextmanager
from typing import Callable, Optional


class TokenBucket:
    """令牌桶。所有时间由注入的 `now` 提供（默认单调时钟），保证可确定性测试。"""

    def __init__(self, capacity: float, refill_per_second: float,
                 now: Callable[[], float] = time.monotonic):
        self.capacity = float(capacity)
        self.refill_per_second = float(refill_per_second)
        self.tokens = float(capacity)
        self.last_refill = now()
        self._now = now

    def _refill(self) -> None:
        t = self._now()
        elapsed = t - self.last_refill
        if elapsed <= 0:
            return
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_second)
        self.last_refill = t

    def time_until_ready(self, amount: float) -> float:
        """返回需要等待的秒数（不扣减）。充足时返回 0。"""
        if amount > self.capacity:
            # 永远无法满足的超限请求：放行，交由 provider 拒绝（避免死等）
            return 0.0
        self._refill()
        if self.tokens >= amount:
            return 0.0
        return (amount - self.tokens) / self.refill_per_second

    def consume(self, amount: float) -> None:
        """扣减；调用前应已等待（本模块内保证）。"""
        self._refill()
        self.tokens = max(0.0, self.tokens - amount)


class ProviderThrottle:
    """per-provider RPM/TPM 双桶。参数来自 providers.yaml 的 rate_limit。"""

    def __init__(self, requests_per_minute: float, tokens_per_minute: float,
                 now: Callable[[], float] = time.monotonic):
        self.rpm = TokenBucket(requests_per_minute, requests_per_minute / 60.0, now)
        self.tpm = TokenBucket(tokens_per_minute, tokens_per_minute / 60.0, now)

    @classmethod
    def from_provider_conf(cls, conf: dict, now: Callable[[], float] = time.monotonic) -> "ProviderThrottle":
        rl = (conf or {}).get("rate_limit", {}) or {}
        rpm = rl.get("requests_per_minute")
        tpm = rl.get("tokens_per_minute")
        # 缺省保守值：两个维度都设上限，宁紧勿松（v1.0 未启用，无从观测真实余量）
        return cls(float(rpm or 60.0), float(tpm or 100_000.0), now)

    def refresh(self, conf: dict) -> None:
        """热更新后重建桶，保留已积累 token（取 min，防止新容量更小时超发）。"""
        rl = (conf or {}).get("rate_limit", {}) or {}
        rpm = float(rl.get("requests_per_minute") or 60.0)
        tpm = float(rl.get("tokens_per_minute") or 100_000.0)
        new_rpm = TokenBucket(rpm, rpm / 60.0, self.rpm._now)
        new_tpm = TokenBucket(tpm, tpm / 60.0, self.tpm._now)
        new_rpm.tokens = min(self.rpm.tokens, new_rpm.capacity)
        new_tpm.tokens = min(self.tpm.tokens, new_tpm.capacity)
        self.rpm = new_rpm
        self.tpm = new_tpm

    def time_until_ready(self, est_tokens: float) -> float:
        return max(
            self.rpm.time_until_ready(1.0),
            self.tpm.time_until_ready(max(1.0, float(est_tokens))),
        )

    def consume(self, est_tokens: float) -> None:
        self.rpm.consume(1.0)
        self.tpm.consume(max(1.0, float(est_tokens)))


class GlobalGate:
    """全局并发闸门 + 平滑发送 + KI-02 突发退让。

    gate() 顺序（刻意对齐业界流水线，平滑放在锁内——锁外等待会在出口重新扎堆）：
        双重准入等待 → 消费 → 并发锁(+inflight) → 平滑+jitter → yield → inflight--
    """

    DEFAULTS = {
        "enabled": True,
        "max_concurrent_chat": 16,
        "min_interval_seconds": 0.2,
        "jitter_ratio": 0.25,
        "burst_backoff": {
            "enabled": True,
            "inflight_ratio_threshold": 0.7,
            "base_seconds": 1.0,
            "max_seconds": 10.0,
        },
    }

    def __init__(self, routing_config: Optional[dict] = None,
                 providers_config: Optional[dict] = None,
                 now: Callable[[], float] = time.monotonic,
                 sleep_fn: Optional[Callable[[float], object]] = None):
        self._now = now
        # 测试注入：把等待替换为「推进假时钟并记录」，从而确定性断言准入时序
        self._sleep = sleep_fn or asyncio.sleep
        self._lock = threading.Lock()          # 保护 inflight / last_send / buckets
        self._providers: dict[str, ProviderThrottle] = {}
        self._max_at_creation: Optional[int] = None

        raw_cfg = (routing_config or {}).get("throttle", {}) or {}
        # fail-open：顶层不是 dict（含 None/str/list）或显式 enabled=false → 旁路。
        # 关键：先归一为非 dict 即空，否则下方 .get() 会在畸形配置上抛异常。
        cfg = raw_cfg if isinstance(raw_cfg, dict) else {}
        self.enabled = bool(cfg.get("enabled", False))
        self.max_concurrent = int(cfg.get("max_concurrent_chat", self.DEFAULTS["max_concurrent_chat"]))
        self.min_interval = float(cfg.get("min_interval_seconds", self.DEFAULTS["min_interval_seconds"]))
        self.jitter_ratio = float(cfg.get("jitter_ratio", self.DEFAULTS["jitter_ratio"]))

        bo = (cfg.get("burst_backoff") or {}) if isinstance(cfg.get("burst_backoff"), dict) else {}
        self.burst_enabled = bool(bo.get("enabled", self.DEFAULTS["burst_backoff"]["enabled"]))
        self.burst_ratio = float(bo.get("inflight_ratio_threshold",
                                        self.DEFAULTS["burst_backoff"]["inflight_ratio_threshold"]))
        self.burst_base = float(bo.get("base_seconds", self.DEFAULTS["burst_backoff"]["base_seconds"]))
        self.burst_max = float(bo.get("max_seconds", self.DEFAULTS["burst_backoff"]["max_seconds"]))

        # 异步原语惰性创建（构造时可能没有运行中的事件循环）；
        # max_concurrent 热更新后需重建，否则闸门仍是旧容量
        self._sem: Optional[asyncio.Semaphore] = None
        self._inflight = 0
        self._last_send = 0.0

        provs = (providers_config or {}).get("providers", {}) or {}
        for pid, pconf in provs.items():
            if isinstance(pconf, dict) and pconf.get("enabled"):
                self._providers[pid] = ProviderThrottle.from_provider_conf(pconf, now)

    # ── 同步读取（线程安全） ─────────────────────────────────
    @property
    def sem(self) -> asyncio.Semaphore:
        if self._sem is None or self._max_at_creation != self.max_concurrent:
            self._sem = asyncio.Semaphore(self.max_concurrent)
            self._max_at_creation = self.max_concurrent
        return self._sem

    def inflight(self) -> int:
        with self._lock:
            return self._inflight

    def inflight_ratio(self) -> float:
        return self._inflight / self.max_concurrent if self.max_concurrent > 0 else 1.0

    def _throttle_for(self, provider_id: str, providers_config: dict) -> Optional[ProviderThrottle]:
        """取该 provider 的桶；不存在则按当前配置构建。"""
        with self._lock:
            th = self._providers.get(provider_id)
        if th is not None:
            return th
        pconf = (providers_config or {}).get("providers", {}).get(provider_id, {})
        if not pconf:
            return None
        th = ProviderThrottle.from_provider_conf(pconf, self._now)
        with self._lock:
            self._providers[provider_id] = th
        return th

    def refresh_providers(self, providers_config: dict) -> None:
        """热更新入口：刷新已知 provider 的桶参数。"""
        provs = (providers_config or {}).get("providers", {}) or {}
        for pid, pconf in provs.items():
            with self._lock:
                th = self._providers.get(pid)
            if th is not None and isinstance(pconf, dict):
                th.refresh(pconf)

    # ── KI-02：突发退让 ─────────────────────────────────────
    def burst_backoff_seconds(self) -> float:
        """429 突发限流时的退让时长。仅在高并发（inflight 高于阈值）时非 0。"""
        if not self.burst_enabled:
            return 0.0
        ratio = self.inflight_ratio()
        if ratio < self.burst_ratio:
            return 0.0
        # 线性插值：ratio=threshold→base，ratio=1.0→max
        span = max(1e-9, 1.0 - self.burst_ratio)
        frac = min(1.0, (ratio - self.burst_ratio) / span)
        return round(self.burst_base + frac * (self.burst_max - self.burst_base), 3)

    # ── 主准入 ──────────────────────────────────────────────
    @asynccontextmanager
    async def gate(self, provider_id: str, est_tokens: float, providers_config: dict):
        """包住一次真实转发尝试。fail-open：enabled=False 时直接放行。"""
        if not self.enabled:
            yield
            return

        th = self._throttle_for(provider_id, providers_config)
        if th is not None:
            wait = th.time_until_ready(est_tokens)
            if wait > 0:
                await self._sleep(wait)
            th.consume(est_tokens)

        async with self.sem:
            with self._lock:
                self._inflight += 1
                last = self._last_send
                delay = 0.0
                if self.min_interval > 0 and last > 0:
                    gap = self._now() - last
                    if gap < self.min_interval:
                        delay = self.min_interval - gap
                if delay > 0 and self.jitter_ratio > 0:
                    delay += random.uniform(0.0, self.min_interval * self.jitter_ratio)
            try:
                if delay > 0:
                    await self._sleep(delay)
                with self._lock:
                    self._last_send = self._now()
                yield
            finally:
                with self._lock:
                    self._inflight -= 1


def load_gate(watcher, now: Callable[[], float] = time.monotonic) -> GlobalGate:
    """便捷构造：从 watcher 读 routing.yaml / providers.yaml。"""
    return GlobalGate(watcher.get("routing.yaml"), watcher.get("providers.yaml"), now)
