"""Status-based retries with full-jitter backoff, a circuit breaker and a token-bucket limiter."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Generic, TypeVar

import httpx

logger = logging.getLogger(__name__)

T = TypeVar("T")

RETRYABLE_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504, 529})
_CONNECTION_ERROR_NAMES = frozenset({"APIConnectionError", "APITimeoutError"})


@dataclass(frozen=True)
class ErrorDecision:
    retryable: bool
    retry_after: float | None = None


def _status_of(exc: BaseException) -> int | None:
    for attribute in ("status_code", "code", "status"):
        value = getattr(exc, attribute, None)
        if isinstance(value, int):
            return value
    return None


def _retry_after_of(exc: BaseException) -> float | None:
    headers = getattr(getattr(exc, "response", None), "headers", None)
    if headers is None:
        return None
    raw = headers.get("retry-after")
    try:
        return max(float(raw), 0.0) if raw is not None else None
    except (TypeError, ValueError):
        return None


def classify_error(exc: BaseException) -> ErrorDecision:
    if isinstance(exc, (TimeoutError, ConnectionError, httpx.TransportError)):
        return ErrorDecision(retryable=True)
    if type(exc).__name__ in _CONNECTION_ERROR_NAMES:
        return ErrorDecision(retryable=True)
    status = _status_of(exc)
    if status in RETRYABLE_STATUS:
        return ErrorDecision(retryable=True, retry_after=_retry_after_of(exc))
    return ErrorDecision(retryable=False)


@dataclass
class RetryPolicy:
    max_retries: int = 5
    base_delay: float = 1.0
    max_delay: float = 30.0
    rng: random.Random = field(default_factory=random.Random)

    def delay(self, attempt: int, retry_after: float | None) -> float:
        backoff = self.rng.uniform(0, min(self.max_delay, self.base_delay * 2**attempt))
        return max(backoff, retry_after or 0.0)


@dataclass
class CallOutcome(Generic[T]):
    value: T
    attempts: int


async def call_with_retry(
    operation: Callable[[], Awaitable[T]],
    policy: RetryPolicy,
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> CallOutcome[T]:
    attempt = 0
    while True:
        try:
            return CallOutcome(value=await operation(), attempts=attempt + 1)
        except Exception as exc:
            decision = classify_error(exc)
            if not decision.retryable or attempt >= policy.max_retries:
                raise
            wait = policy.delay(attempt, decision.retry_after)
            logger.warning(
                "retryable model error (%s); attempt %d/%d, sleeping %.2fs",
                type(exc).__name__,
                attempt + 1,
                policy.max_retries,
                wait,
            )
            await sleep(wait)
            attempt += 1


class CircuitOpenError(RuntimeError):
    """Raised instead of calling a provider that recently failed repeatedly."""


class CircuitBreaker:
    """Opens after consecutive availability failures; allows a probe once ``reset_after`` passes."""

    def __init__(
        self,
        failure_threshold: int = 5,
        reset_after: float = 30.0,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._threshold = failure_threshold
        self._reset_after = reset_after
        self._clock = clock
        self._failures = 0
        self._opened_at: float | None = None

    @property
    def is_open(self) -> bool:
        return self._opened_at is not None and self._clock() - self._opened_at < self._reset_after

    def check(self) -> None:
        if self.is_open:
            raise CircuitOpenError("provider circuit is open after repeated failures")

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._threshold:
            self._opened_at = self._clock()


class RateLimiter:
    """Async token bucket: at most ``rate_per_minute`` acquisitions per minute, with bursts."""

    def __init__(
        self,
        rate_per_minute: float,
        *,
        burst: int | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if rate_per_minute <= 0:
            raise ValueError("rate_per_minute must be positive")
        self._interval = 60.0 / rate_per_minute
        self._capacity = float(burst if burst is not None else max(1, int(rate_per_minute // 6)))
        self._tokens = self._capacity
        self._clock = clock
        self._sleep = sleep
        self._updated = clock()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = self._clock()
                self._tokens = min(
                    self._capacity, self._tokens + (now - self._updated) / self._interval
                )
                self._updated = now
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                await self._sleep((1 - self._tokens) * self._interval)
