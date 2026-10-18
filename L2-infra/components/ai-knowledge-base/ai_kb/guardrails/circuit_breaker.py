"""
Circuit breaker for system protection
"""
import time
from typing import Optional
from dataclasses import dataclass


@dataclass
class CircuitBreakerStats:
    failures: int
    total_requests: int
    error_rate: float
    state: str
    last_failure_time: Optional[float]


class CircuitBreaker:
    """
    Simple circuit breaker implementation.
    States:
    - closed: normal operation, requests pass through
    - open: service is unhealthy, all requests are blocked
    - half-open: after cooldown, allow one request to test
    """

    STATE_CLOSED = "closed"
    STATE_OPEN = "open"
    STATE_HALF_OPEN = "half-open"

    def __init__(self,
                 error_rate_threshold: float = 0.3,
                 cooldown_seconds: float = 300,
                 minimum_requests: int = 10):
        self.error_rate_threshold = error_rate_threshold
        self.cooldown_seconds = cooldown_seconds
        self.minimum_requests = minimum_requests

        self.state = self.STATE_CLOSED
        self.failures = 0
        self.total_requests = 0
        self.last_failure_time: Optional[float] = None
        self.opened_at: Optional[float] = None

    def allow_request(self) -> bool:
        """Check if a request is allowed"""
        if self.state == self.STATE_OPEN:
            # Check if cooldown has passed
            if time.time() - self.opened_at >= self.cooldown_seconds:
                self.state = self.STATE_HALF_OPEN
                return True
            return False
        return True

    def record_success(self):
        """Record a successful request"""
        if self.state == self.STATE_HALF_OPEN:
            # Recovered, close the circuit
            self.reset()
        self.total_requests += 1

    def record_failure(self):
        """Record a failed request"""
        self.failures += 1
        self.total_requests += 1
        self.last_failure_time = time.time()

        if self.state == self.STATE_HALF_OPEN:
            # Failed again in half-open, go back to open
            self.state = self.STATE_OPEN
            self.opened_at = time.time()
            return

        if self.state != self.STATE_OPEN and self.total_requests >= self.minimum_requests:
            error_rate = self.failures / self.total_requests
            if error_rate >= self.error_rate_threshold:
                self.state = self.STATE_OPEN
                self.opened_at = time.time()

    def reset(self):
        """Reset the circuit breaker to closed state"""
        self.state = self.STATE_CLOSED
        self.failures = 0
        self.total_requests = 0
        self.opened_at = None

    def get_stats(self) -> CircuitBreakerStats:
        """Get current stats"""
        error_rate = self.failures / max(1, self.total_requests)
        return CircuitBreakerStats(
            failures=self.failures,
            total_requests=self.total_requests,
            error_rate=error_rate,
            state=self.state,
            last_failure_time=self.last_failure_time
        )
