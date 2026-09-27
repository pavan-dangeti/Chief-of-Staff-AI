"""Per-message extraction: redact, call backends with caching, fallback and escalation, verify."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass, field

from chief_of_staff.dates import DateOrder
from chief_of_staff.extraction.base import Extractor
from chief_of_staff.extraction.cache import ExtractionCache
from chief_of_staff.extraction.prompt import render_message
from chief_of_staff.extraction.resilience import (
    CircuitBreaker,
    RateLimiter,
    RetryPolicy,
    call_with_retry,
    classify_error,
)
from chief_of_staff.extraction.verify import verify_items
from chief_of_staff.models import ActionItem, Message, RawExtraction
from chief_of_staff.redaction import NoopRedactor, Redactor
from chief_of_staff.tracing import Tracer, TraceRecord, cost_usd

logger = logging.getLogger(__name__)


@dataclass
class Backend:
    """An extractor plus its operational policy (rate limit, retries, circuit breaker, caching)."""

    extractor: Extractor
    limiter: RateLimiter | None = None
    retry: RetryPolicy | None = None
    breaker: CircuitBreaker | None = None
    cacheable: bool = True
    remote: bool = True

    @property
    def label(self) -> str:
        return f"{self.extractor.name}:{self.extractor.model}"

    async def call(self, message: Message, body: str) -> tuple[RawExtraction, int]:
        async def attempt() -> RawExtraction:
            if self.breaker is not None:
                self.breaker.check()
            if self.limiter is not None:
                await self.limiter.acquire()
            try:
                result = await self.extractor.extract(message, body)
            except Exception as exc:
                if self.breaker is not None and classify_error(exc).retryable:
                    self.breaker.record_failure()
                raise
            if self.breaker is not None:
                self.breaker.record_success()
            return result

        if self.retry is None:
            return await attempt(), 1
        outcome = await call_with_retry(attempt, self.retry)
        return outcome.value, outcome.attempts


@dataclass
class MessageExtraction:
    message: Message
    items: list[ActionItem]
    trace: TraceRecord
    error: str | None = None


@dataclass
class _CallResult:
    raw: RawExtraction
    attempts: int = 0
    cache_hit: bool = False


@dataclass
class ExtractionService:
    chain: Sequence[Backend]
    escalation: Backend | None = None
    cache: ExtractionCache | None = None
    tracer: Tracer = field(default_factory=Tracer)
    redactor: Redactor = field(default_factory=NoopRedactor)
    max_concurrency: int = 8
    escalation_threshold: float = 0.55
    date_order: DateOrder = "DMY"
    prices: dict[str, tuple[float, float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.chain:
            raise ValueError("ExtractionService needs at least one backend")
        self._semaphore = asyncio.Semaphore(self.max_concurrency)

    def close(self) -> None:
        if self.cache is not None:
            self.cache.close()

    @property
    def primary_label(self) -> str:
        return self.chain[0].label

    async def extract_message(self, message: Message) -> MessageExtraction:
        async with self._semaphore:
            return await self._extract(message)

    async def _extract(self, message: Message) -> MessageExtraction:
        started = time.perf_counter()
        trace = TraceRecord(run_id=self.tracer.run_id, message_id=message.id)
        redacted = self.redactor.redact(message.text)
        result, error = await self._run_chain(message, redacted.text, trace)
        if result is None:
            trace.error = error
            trace.latency_ms = _elapsed_ms(started)
            self.tracer.record(trace)
            return MessageExtraction(message=message, items=[], trace=trace, error=error)

        raw = result.raw
        if self._should_escalate(raw):
            raw = await self._escalate(message, redacted.text, raw, trace)

        items, stats = verify_items(raw, message, redacted, date_order=self.date_order)
        trace.backend, trace.model = raw.backend, raw.model
        trace.items = len(items)
        trace.dropped_ungrounded = stats.dropped_ungrounded
        trace.dropped_injection = stats.dropped_injection
        trace.owners_cleared = stats.owners_cleared
        trace.cost_usd = cost_usd(raw.model, trace.input_tokens, trace.output_tokens, self.prices)
        trace.latency_ms = _elapsed_ms(started)
        self.tracer.record(trace)
        return MessageExtraction(message=message, items=items, trace=trace)

    async def _run_chain(
        self, message: Message, body: str, trace: TraceRecord
    ) -> tuple[_CallResult | None, str | None]:
        last_error: str | None = None
        for position, backend in enumerate(self.chain):
            try:
                result = await self._call(backend, message, body, trace)
            except Exception as exc:
                last_error = f"{backend.label}: {type(exc).__name__}: {exc}"[:500]
                logger.warning("backend failed for %s -> %s", message.id, last_error)
                continue
            trace.fallback = position > 0
            return result, None
        return None, last_error

    async def _call(
        self, backend: Backend, message: Message, body: str, trace: TraceRecord
    ) -> _CallResult:
        key = None
        if self.cache is not None and backend.cacheable:
            key = self.cache.key(
                backend.extractor.name, backend.extractor.model, render_message(message, body)
            )
            cached = self.cache.get(key)
            if cached is not None:
                trace.cache_hit = True
                return _CallResult(raw=cached, cache_hit=True)
        raw, attempts = await backend.call(message, body)
        if backend.remote:
            trace.attempts += attempts
        trace.input_tokens += raw.usage.input_tokens
        trace.output_tokens += raw.usage.output_tokens
        if key is not None and self.cache is not None:
            self.cache.put(key, raw)
        return _CallResult(raw=raw, attempts=attempts)

    def _should_escalate(self, raw: RawExtraction) -> bool:
        return (
            self.escalation is not None
            and raw.backend == self.chain[0].extractor.name
            and any(item.confidence < self.escalation_threshold for item in raw.items)
        )

    async def _escalate(
        self, message: Message, body: str, raw: RawExtraction, trace: TraceRecord
    ) -> RawExtraction:
        assert self.escalation is not None
        try:
            result = await self._call(self.escalation, message, body, trace)
        except Exception as exc:
            logger.warning("escalation failed for %s: %s", message.id, exc)
            return raw
        trace.escalated = True
        return result.raw


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)
