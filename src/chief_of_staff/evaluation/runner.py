"""Run an extraction service over a labeled split and compute an :class:`EvalReport`."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, NamedTuple

from pydantic import BaseModel, Field

from chief_of_staff.evaluation.metrics import (
    EvalExample,
    ExampleScore,
    accuracy,
    attack_succeeded,
    bootstrap_ci,
    score_example,
    total,
)
from chief_of_staff.extraction.prompt import PROMPT_VERSION
from chief_of_staff.extraction.service import ExtractionService
from chief_of_staff.models import ActionItem
from chief_of_staff.prefilter import skip_reason
from chief_of_staff.tracing import percentile


class _Outcome(NamedTuple):
    items: list[ActionItem]
    skipped: bool
    error: str | None = None
    cache_hit: bool = False
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None
    call_ms: float = 0.0
    recorded_input_tokens: int = 0
    recorded_output_tokens: int = 0
    list_cost_usd: float | None = None


class PRF(BaseModel):
    precision: float
    recall: float
    f1: float
    f1_ci95: tuple[float, float]
    tp: int
    fp: int
    fn: int


class ExampleResult(BaseModel):
    id: str
    tags: list[str]
    expected: int
    predicted: list[str]
    matched: int
    skipped_by_prefilter: bool = False
    attack_succeeded: bool | None = None
    error: str | None = None


class EvalReport(BaseModel):
    split: str
    backend: str
    prompt_version: str = PROMPT_VERSION
    examples: int
    message_level: PRF
    item_level: PRF
    kind_accuracy: float | None
    owner_accuracy: float | None
    due_date_accuracy: float | None
    prefilter_skip_rate: float
    prefilter_false_negatives: int
    attack_success_rate: float | None = None
    failures: int
    live_calls: int = 0
    cache_hits: int = 0
    latency_ms_p50: float
    latency_ms_p95: float
    input_tokens: int
    output_tokens: int
    cost_usd: float | None
    # From usage recorded when each answer was produced (live or resumed from the run cache).
    call_ms_p50: float = 0.0
    call_ms_p95: float = 0.0
    timed_calls: int = 0
    recorded_input_tokens: int = 0
    recorded_output_tokens: int = 0
    list_cost_usd: float | None = None
    list_cost_per_1k_messages_usd: float | None = None
    wall_time_s: float
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    results: list[ExampleResult]


def load_split(path: Path) -> list[EvalExample]:
    examples = [
        EvalExample.model_validate(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    ids = [example.id for example in examples]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate example ids in {path}")
    return examples


def _prf(
    scores: Sequence[ExampleScore], level: Literal["message", "items"], iterations: int
) -> PRF:
    counts = total(scores, level)
    ci = bootstrap_ci(scores, lambda sample: total(sample, level).f1, iterations=iterations)
    return PRF(
        precision=round(counts.precision, 4),
        recall=round(counts.recall, 4),
        f1=round(counts.f1, 4),
        f1_ci95=ci,
        tp=counts.tp,
        fp=counts.fp,
        fn=counts.fn,
    )


async def evaluate(
    examples: Sequence[EvalExample],
    service: ExtractionService,
    *,
    split: str,
    prefilter: bool = True,
    bootstrap_iterations: int = 1000,
) -> EvalReport:
    started = time.perf_counter()
    threads = [example.id for example in examples if example.message is None]
    if threads:
        raise ValueError(f"thread examples need pipeline-level scoring: {', '.join(threads)}")

    async def run(example: EvalExample) -> _Outcome:
        assert example.message is not None
        if prefilter and skip_reason(example.message) is not None:
            return _Outcome(items=[], skipped=True)
        result = await service.extract_message(example.message)
        trace = result.trace
        return _Outcome(
            items=result.items,
            skipped=False,
            error=result.error,
            cache_hit=trace.cache_hit,
            latency_ms=trace.latency_ms,
            input_tokens=trace.input_tokens,
            output_tokens=trace.output_tokens,
            cost_usd=trace.cost_usd,
            call_ms=trace.call_ms,
            recorded_input_tokens=trace.recorded_input_tokens,
            recorded_output_tokens=trace.recorded_output_tokens,
            list_cost_usd=trace.list_cost_usd,
        )

    outputs = await asyncio.gather(*(run(example) for example in examples))

    scores: list[ExampleScore] = []
    results: list[ExampleResult] = []
    attacks = attack_hits = prefilter_fn = failures = 0
    for example, outcome in zip(examples, outputs, strict=True):
        items, skipped, error = outcome.items, outcome.skipped, outcome.error
        score = score_example(example.expected, items)
        scores.append(score)
        hit = attack_succeeded(example, items) if example.attack else None
        attacks += example.attack is not None
        attack_hits += bool(hit)
        prefilter_fn += skipped and bool(example.expected)
        failures += error is not None
        results.append(
            ExampleResult(
                id=example.id,
                tags=example.tags,
                expected=len(example.expected),
                predicted=[
                    f"[{i.kind.value}] {i.action} | owner={i.owner} | due={i.due_date}"
                    for i in items
                ],
                matched=len(score.pairs),
                skipped_by_prefilter=skipped,
                attack_succeeded=hit,
                error=error,
            )
        )

    live = [o for o in outputs if not o.skipped and not o.cache_hit]
    latencies = [o.latency_ms for o in live]
    costs = [o.cost_usd for o in outputs if o.cost_usd is not None]
    # Calls cached before timing was recorded carry 0 ms and are left out rather than counted.
    call_times = [o.call_ms for o in outputs if o.call_ms > 0]
    list_costs = [o.list_cost_usd for o in outputs if o.list_cost_usd is not None]
    list_cost = round(sum(list_costs), 6) if list_costs else None
    return EvalReport(
        split=split,
        backend=service.primary_label,
        examples=len(examples),
        message_level=_prf(scores, "message", bootstrap_iterations),
        item_level=_prf(scores, "items", bootstrap_iterations),
        kind_accuracy=accuracy(scores, "kind"),
        owner_accuracy=accuracy(scores, "owner"),
        due_date_accuracy=accuracy(scores, "due"),
        prefilter_skip_rate=round(sum(o.skipped for o in outputs) / len(examples), 4)
        if examples
        else 0.0,
        prefilter_false_negatives=prefilter_fn,
        attack_success_rate=round(attack_hits / attacks, 4) if attacks else None,
        failures=failures,
        live_calls=len(live),
        cache_hits=sum(o.cache_hit for o in outputs),
        latency_ms_p50=round(percentile(latencies, 50), 2),
        latency_ms_p95=round(percentile(latencies, 95), 2),
        input_tokens=sum(o.input_tokens for o in outputs),
        output_tokens=sum(o.output_tokens for o in outputs),
        cost_usd=round(sum(costs), 6) if costs else None,
        call_ms_p50=round(percentile(call_times, 50), 2),
        call_ms_p95=round(percentile(call_times, 95), 2),
        timed_calls=len(call_times),
        recorded_input_tokens=sum(o.recorded_input_tokens for o in outputs),
        recorded_output_tokens=sum(o.recorded_output_tokens for o in outputs),
        list_cost_usd=list_cost,
        # Per 1,000 messages ingested: prefilter-skipped messages count, at zero cost.
        list_cost_per_1k_messages_usd=(
            round(list_cost / len(examples) * 1000, 4)
            if list_cost is not None and examples
            else None
        ),
        wall_time_s=round(time.perf_counter() - started, 3),
        results=results,
    )
