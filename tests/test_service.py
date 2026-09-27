from __future__ import annotations

import asyncio

import pytest

from chief_of_staff.extraction.anthropic_backend import AnthropicExtractor
from chief_of_staff.extraction.cache import ExtractionCache
from chief_of_staff.extraction.heuristic import HeuristicExtractor
from chief_of_staff.extraction.resilience import CircuitBreaker, RetryPolicy
from chief_of_staff.extraction.service import Backend, ExtractionService
from chief_of_staff.models import Message, RawExtraction
from chief_of_staff.redaction import Redactor
from helpers import FakeAnthropic, StatusError, anthropic_response, item, make_message

TEXT = "Ravi, can you rotate the staging keys by Friday?"
MESSAGE = make_message(TEXT)
GOOD = item(TEXT, owner="Ravi", deadline_text="by Friday")


def remote(client: FakeAnthropic, model: str = "haiku", retries: int = 0) -> Backend:
    return Backend(
        AnthropicExtractor(client, model), retry=RetryPolicy(max_retries=retries, base_delay=0.001)
    )


def offline() -> Backend:
    return Backend(HeuristicExtractor(), cacheable=False, remote=False)


async def test_happy_path_records_a_trace() -> None:
    service = ExtractionService(chain=[remote(FakeAnthropic(anthropic_response([GOOD])))])
    result = await service.extract_message(MESSAGE)
    assert [i.owner for i in result.items] == ["Ravi"]
    assert str(result.items[0].due_date) == "2026-09-18"
    trace = result.trace
    assert (trace.backend, trace.attempts, trace.input_tokens, trace.fallback) == (
        "anthropic",
        1,
        120,
        False,
    )
    assert service.tracer.records == [trace]


async def test_transient_errors_are_retried() -> None:
    client = FakeAnthropic(StatusError(503), anthropic_response([GOOD]))
    result = await ExtractionService(chain=[remote(client, retries=2)]).extract_message(MESSAGE)
    assert result.trace.attempts == 2 and len(result.items) == 1


async def test_falls_back_when_primary_fails() -> None:
    service = ExtractionService(chain=[remote(FakeAnthropic(StatusError(400))), offline()])
    result = await service.extract_message(MESSAGE)
    assert result.trace.fallback and result.trace.backend == "heuristic"
    assert result.items[0].owner == "Ravi"


async def test_total_failure_is_reported_not_raised() -> None:
    service = ExtractionService(chain=[remote(FakeAnthropic(StatusError(401)))])
    result = await service.extract_message(MESSAGE)
    assert result.items == []
    assert result.error is not None and "anthropic:haiku" in result.error


async def test_cache_serves_repeat_messages_without_a_call() -> None:
    client = FakeAnthropic(anthropic_response([GOOD]))
    with ExtractionCache(":memory:") as cache:
        service = ExtractionService(chain=[remote(client)], cache=cache)
        first = await service.extract_message(MESSAGE)
        second = await service.extract_message(MESSAGE)
    assert len(client.calls) == 1
    assert second.trace.cache_hit and not first.trace.cache_hit
    assert second.items == first.items


async def test_low_confidence_escalates_to_stronger_model() -> None:
    weak = FakeAnthropic(anthropic_response([{**GOOD, "confidence": 0.3}]))
    strong = FakeAnthropic(anthropic_response([{**GOOD, "confidence": 0.95}]))
    service = ExtractionService(chain=[remote(weak)], escalation=remote(strong, model="sonnet"))
    result = await service.extract_message(MESSAGE)
    assert result.trace.escalated and result.trace.model == "sonnet"
    assert result.items[0].confidence == 0.95
    assert result.trace.input_tokens == 240


async def test_failed_escalation_keeps_the_primary_answer() -> None:
    weak = FakeAnthropic(anthropic_response([{**GOOD, "confidence": 0.3}]))
    service = ExtractionService(
        chain=[remote(weak)], escalation=remote(FakeAnthropic(StatusError(400)))
    )
    result = await service.extract_message(MESSAGE)
    assert not result.trace.escalated and result.items[0].confidence == 0.3


async def test_pii_never_reaches_the_provider_but_is_restored_locally() -> None:
    text = "Please email priya@acme.io the signed contract by Friday."
    client = FakeAnthropic(
        anthropic_response([item("Please email [EMAIL_1] the signed contract by Friday.")])
    )
    service = ExtractionService(chain=[remote(client)], redactor=Redactor())
    result = await service.extract_message(make_message(text))
    assert "priya@acme.io" not in client.calls[0]["messages"][0]["content"]
    assert result.items[0].evidence == text


async def test_hallucinated_items_are_dropped_and_counted() -> None:
    client = FakeAnthropic(anthropic_response([GOOD, item("Wire $40k to the vendor")]))
    result = await ExtractionService(chain=[remote(client)]).extract_message(MESSAGE)
    assert len(result.items) == 1 and result.trace.dropped_ungrounded == 1


async def test_cost_is_computed_from_configured_prices() -> None:
    service = ExtractionService(
        chain=[remote(FakeAnthropic(anthropic_response([GOOD])))], prices={"haiku": (1.0, 5.0)}
    )
    result = await service.extract_message(MESSAGE)
    assert result.trace.cost_usd == pytest.approx((120 * 1.0 + 30 * 5.0) / 1_000_000)


async def test_concurrency_is_bounded() -> None:
    in_flight = peak = 0

    class Slow:
        name, model = "slow", "slow"

        async def extract(self, message: Message, body: str) -> RawExtraction:
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0.01)
            in_flight -= 1
            return RawExtraction(items=[], backend=self.name, model=self.model)

    service = ExtractionService(chain=[Backend(Slow())], max_concurrency=3)
    messages = [make_message(TEXT, id=f"m{i}") for i in range(12)]
    await asyncio.gather(*(service.extract_message(m) for m in messages))
    assert peak == 3


async def test_open_circuit_skips_a_dead_provider_without_waiting_on_retries() -> None:
    client = FakeAnthropic(StatusError(503))
    breaker = CircuitBreaker(failure_threshold=2, reset_after=60)
    dead = Backend(
        AnthropicExtractor(client, "haiku"),
        retry=RetryPolicy(max_retries=1, base_delay=0.001),
        breaker=breaker,
    )
    service = ExtractionService(chain=[dead, offline()])
    first = await service.extract_message(MESSAGE)
    second = await service.extract_message(make_message(TEXT, id="m2"))
    assert breaker.is_open and len(client.calls) == 2
    assert first.trace.fallback and second.trace.fallback
    assert second.items[0].owner == "Ravi"


async def test_invalid_output_does_not_trip_the_breaker() -> None:
    breaker = CircuitBreaker(failure_threshold=1)
    client = FakeAnthropic(anthropic_response([{"kind": "banana"}]))
    backend = Backend(AnthropicExtractor(client, "haiku"), breaker=breaker)
    await ExtractionService(chain=[backend, offline()]).extract_message(MESSAGE)
    assert not breaker.is_open


def test_service_requires_a_backend() -> None:
    with pytest.raises(ValueError, match="at least one"):
        ExtractionService(chain=[])
