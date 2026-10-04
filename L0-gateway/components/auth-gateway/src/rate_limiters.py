"""Token Bucket Rate Limiter — 令牌桶限流器实现."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Optional

from auth_provider import RateLimiter


@dataclass
class _Bucket:
    """令牌桶内部状态."""
    tokens: float
    last_refill: float  # timestamp
    lock: threading.Lock = field(default_factory=threading.Lock)


class TokenBucketRateLimiter(RateLimiter):
    """令牌桶限流器 — 支持突发流量.
    
    参数:
        rate: 每秒填充的令牌数
        capacity: 桶容量（最大突发量）
    """

    def __init__(self, rate: float = 10.0, capacity: int = 100) -> None:
        self._rate = rate
        self._capacity = capacity
        self._buckets: Dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def _get_bucket(self, key: str) -> _Bucket:
        """获取或创建桶."""
        if key not in self._buckets:
            with self._lock:
                if key not in self._buckets:
                    self._buckets[key] = _Bucket(
                        tokens=float(self._capacity),
                        last_refill=time.monotonic(),
                    )
        return self._buckets[key]

    def _refill(self, bucket: _Bucket) -> None:
        """按需填充令牌."""
        now = time.monotonic()
        elapsed = now - bucket.last_refill
        new_tokens = elapsed * self._rate
        bucket.tokens = min(self._capacity, bucket.tokens + new_tokens)
        bucket.last_refill = now

    def allow(self, key: str, tokens: int = 1) -> bool:
        """尝试消费令牌."""
        bucket = self._get_bucket(key)
        with bucket.lock:
            self._refill(bucket)
            if bucket.tokens >= tokens:
                bucket.tokens -= tokens
                return True
            return False

    def remaining(self, key: str) -> int:
        """查询剩余令牌."""
        bucket = self._get_bucket(key)
        with bucket.lock:
            self._refill(bucket)
            return int(bucket.tokens)

    def reset_at(self, key: str) -> datetime:
        """查询下次重置时间."""
        bucket = self._get_bucket(key)
        with bucket.lock:
            self._refill(bucket)
            if bucket.tokens >= self._capacity:
                return datetime.now()
            needed = self._capacity - bucket.tokens
            seconds = needed / self._rate
            return datetime.now() + timedelta(seconds=seconds)

    def reset(self, key: str) -> None:
        """重置限流状态."""
        with self._lock:
            if key in self._buckets:
                del self._buckets[key]


class SlidingWindowLimiter(RateLimiter):
    """滑动窗口限流器 — 更精确的限流.
    
    参数:
        max_requests: 窗口内最大请求数
        window_seconds: 窗口大小（秒）
    """

    def __init__(self, max_requests: int = 60, window_seconds: int = 60) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._requests: Dict[str, list] = {}
        self._lock = threading.Lock()

    def _clean(self, key: str, now: float) -> None:
        """清理过期时间戳."""
        cutoff = now - self._window_seconds
        timestamps = self._requests.get(key, [])
        self._requests[key] = [t for t in timestamps if t > cutoff]

    def allow(self, key: str, tokens: int = 1) -> bool:
        """检查是否允许."""
        now = time.monotonic()
        with self._lock:
            self._clean(key, now)
            timestamps = self._requests.get(key, [])
            if len(timestamps) + tokens <= self._max_requests:
                timestamps.extend([now] * tokens)
                self._requests[key] = timestamps
                return True
            return False

    def remaining(self, key: str) -> int:
        """查询剩余配额."""
        now = time.monotonic()
        with self._lock:
            self._clean(key, now)
            return self._max_requests - len(self._requests.get(key, []))

    def reset_at(self, key: str) -> datetime:
        """查询下次重置时间."""
        now = time.monotonic()
        with self._lock:
            self._clean(key, now)
            timestamps = self._requests.get(key, [])
            if not timestamps:
                return datetime.now()
            oldest = min(timestamps)
            reset_time = oldest + self._window_seconds
            return datetime.fromtimestamp(reset_time)

    def reset(self, key: str) -> None:
        """重置."""
        with self._lock:
            if key in self._requests:
                del self._requests[key]
