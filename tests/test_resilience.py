from __future__ import annotations

import random
from types import SimpleNamespace

import httpx
import pytest

from chief_of_staff.extraction.resilience import (
    CircuitBreaker,
    CircuitOpenError,
    RateLimiter,
    RetryPolicy,
    call_with_retry,
    classify_error,
)
from helpers import StatusError


@pytest.mark.parametrize(
    ("error", "retryable", "retry_after"),
    [
        (StatusError(429, retry_after=3), True, 3.0),
        (StatusError(500), True, None),
        (StatusError(529), True, None),
        (StatusError(400), False, None),
        (StatusError(401), False, None),
        (TimeoutError(), True, None),
        (ConnectionResetError(), True, None),
        (httpx.ConnectError("refused"), True, None),
        (type("APIConnectionError", (Exception,), {})(), True, None),
        (type("ServerError", (Exception,), {"code": 503})(), True, None),
        (ValueError("bad input"), False, None),
    ],
)
def test_classifies_errors_by_status(
    error: Exception, retryable: bool, retry_after: float | None
) -> None:
    decision = classify_error(error)
    assert (decision.retryable, decision.retry_after) == (retryable, retry_after)


def test_malformed_retry_after_is_ignored() -> None:
    error = StatusError(429)
    error.response = SimpleNamespace(headers={"retry-after": "soon"})
    assert classify_error(error).retry_after is None


class Flaky:
    def __init__(self, *errors: Exception) -> None:
        self.errors = list(errors)
        self.calls = 0

    async def __call__(self) -> str:
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return "ok"


async def _no_sleep(recorded: list[float], seconds: float) -> None:
    recorded.append(seconds)


async def test_retries_transient_errors_then_succeeds() -> None:
    slept: list[float] = []
    operation = Flaky(StatusError(503), StatusError(429, retry_after=2))
    outcome = await call_with_retry(
        operation, RetryPolicy(max_retries=3), sleep=lambda s: _no_sleep(slept, s)
    )
    assert (outcome.value, outcome.attempts, operation.calls) == ("ok", 3, 3)
    assert slept[1] >= 2.0


async def test_non_retryable_errors_fail_fast() -> None:
    operation = Flaky(StatusError(400))
    with pytest.raises(StatusError):
        await call_with_retry(
            operation, RetryPolicy(max_retries=5), sleep=lambda s: _no_sleep([], s)
        )
    assert operation.calls == 1


async def test_gives_up_after_max_retries() -> None:
    operation = Flaky(*[StatusError(429) for _ in range(10)])
    with pytest.raises(StatusError):
        await call_with_retry(
            operation, RetryPolicy(max_retries=2), sleep=lambda s: _no_sleep([], s)
        )
    assert operation.calls == 3


def test_backoff_is_jittered_and_capped() -> None:
    policy = RetryPolicy(base_delay=1.0, max_delay=4.0, rng=random.Random(0))
    delays = [policy.delay(attempt, None) for attempt in range(12)]
    assert all(0 <= d <= 4.0 for d in delays)
    assert policy.delay(0, retry_after=20) >= 20


async def test_rate_limiter_spaces_requests_after_burst() -> None:
    now = [0.0]
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)
        now[0] += seconds

    limiter = RateLimiter(60, burst=1, clock=lambda: now[0], sleep=fake_sleep)
    for _ in range(4):
        await limiter.acquire()
    assert sum(slept) == pytest.approx(3.0)


def test_rate_limiter_rejects_non_positive_rate() -> None:
    with pytest.raises(ValueError, match="positive"):
        RateLimiter(0)


def test_circuit_breaker_opens_then_allows_a_probe_after_cooldown() -> None:
    now = [0.0]
    breaker = CircuitBreaker(failure_threshold=2, reset_after=10, clock=lambda: now[0])
    breaker.record_failure()
    breaker.check()
    breaker.record_failure()
    with pytest.raises(CircuitOpenError):
        breaker.check()
    now[0] = 11
    breaker.check()
    breaker.record_success()
    assert not breaker.is_open
