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
from chief_of_staff.pipeline import Pipeline
from chief_of_staff.prefilter import skip_reason
from chief_of_staff.prioritization import Prioritizer
from chief_of_staff.tracing import TraceRecord, percentile


class _Outcome(NamedTuple):
    items: list[ActionItem]
    skipped: bool
    traces: list[TraceRecord]
    error: str | None = None


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
    # extraction: one message per example, scored on extraction and verification alone.
    # pipeline: each example (a message or a thread) runs through the full digest pipeline.
    mode: Literal["extraction", "pipeline"] = "extraction"
    examples: int
    messages: int = 0
    # Headline scores leave out examples tagged "ambiguous"; they appear in groups instead.
    excluded_from_headline: list[str] = Field(default_factory=list)
    groups: dict[str, PRF] = Field(default_factory=dict)
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


def _needs_pipeline(examples: Sequence[EvalExample]) -> bool:
    return any(e.thread or any(a.type == "priority" for a in e.attacks) for e in examples)


async def evaluate(
    examples: Sequence[EvalExample],
    service: ExtractionService,
    *,
    split: str,
    prefilter: bool = True,
    bootstrap_iterations: int = 1000,
    prioritizer: Prioritizer | None = None,
) -> EvalReport:
    """Score a split. Splits with threads or priority attacks go through the full pipeline."""
    started = time.perf_counter()
    pipeline = _needs_pipeline(examples)

    async def extract(example: EvalExample) -> _Outcome:
        assert example.message is not None
        if prefilter and skip_reason(example.message) is not None:
            return _Outcome(items=[], skipped=True, traces=[])
        result = await service.extract_message(example.message)
        return _Outcome(result.items, skipped=False, traces=[result.trace], error=result.error)

    async def run_pipeline(example: EvalExample) -> _Outcome:
        messages = example.messages
        runner = Pipeline(service, prioritizer, prefilter=prefilter)
        digest = await runner.run(messages, as_of=max(m.timestamp for m in messages))
        ids = {m.id for m in messages}
        traces = [t for t in service.tracer.records if t.message_id in ids]
        errors = [t.error for t in traces if t.error]
        items = digest.open_items + digest.resolved_items + digest.unmatched_completions
        skipped = digest.stats.messages_skipped == len(messages)
        return _Outcome(items, skipped, traces, errors[0] if errors else None)

    outputs = await asyncio.gather(*((run_pipeline if pipeline else extract)(e) for e in examples))

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
                    + (f" | {i.priority.value}" if pipeline and i.priority else "")
                    for i in items
                ],
                matched=len(score.pairs),
                skipped_by_prefilter=skipped,
                attack_succeeded=hit,
                error=error,
            )
        )

    headline = [
        score
        for example, score in zip(examples, scores, strict=True)
        if "ambiguous" not in example.tags
    ]
    groups: dict[str, PRF] = {}
    for name in sorted({g for e in examples for g in _group_names(e)}):
        members = [
            score
            for example, score in zip(examples, scores, strict=True)
            if name in _group_names(example)
        ]
        groups[name] = _prf(members, "items", bootstrap_iterations)

    traces = [t for o in outputs for t in o.traces]
    live = [t for t in traces if not t.cache_hit]
    costs = [t.cost_usd for t in traces if t.cost_usd is not None]
    # Calls cached before timing was recorded carry 0 ms and are left out rather than counted.
    call_times = [t.call_ms for t in traces if t.call_ms > 0]
    list_costs = [t.list_cost_usd for t in traces if t.list_cost_usd is not None]
    list_cost = round(sum(list_costs), 6) if list_costs else None
    message_count = sum(len(e.messages) for e in examples)
    return EvalReport(
        split=split,
        backend=service.primary_label,
        mode="pipeline" if pipeline else "extraction",
        examples=len(examples),
        messages=message_count,
        excluded_from_headline=[e.id for e in examples if "ambiguous" in e.tags],
        groups=groups,
        message_level=_prf(headline, "message", bootstrap_iterations),
        item_level=_prf(headline, "items", bootstrap_iterations),
        kind_accuracy=accuracy(headline, "kind"),
        owner_accuracy=accuracy(headline, "owner"),
        due_date_accuracy=accuracy(headline, "due"),
        prefilter_skip_rate=round(sum(o.skipped for o in outputs) / len(examples), 4)
        if examples
        else 0.0,
        prefilter_false_negatives=prefilter_fn,
        attack_success_rate=round(attack_hits / attacks, 4) if attacks else None,
        failures=failures,
        live_calls=len(live),
        cache_hits=sum(t.cache_hit for t in traces),
        latency_ms_p50=round(percentile([t.latency_ms for t in live], 50), 2),
        latency_ms_p95=round(percentile([t.latency_ms for t in live], 95), 2),
        input_tokens=sum(t.input_tokens for t in traces),
        output_tokens=sum(t.output_tokens for t in traces),
        cost_usd=round(sum(costs), 6) if costs else None,
        call_ms_p50=round(percentile(call_times, 50), 2),
        call_ms_p95=round(percentile(call_times, 95), 2),
        timed_calls=len(call_times),
        recorded_input_tokens=sum(t.recorded_input_tokens for t in traces),
        recorded_output_tokens=sum(t.recorded_output_tokens for t in traces),
        list_cost_usd=list_cost,
        # Per 1,000 messages ingested: prefilter-skipped messages count, at zero cost.
        list_cost_per_1k_messages_usd=(
            round(list_cost / message_count * 1000, 4)
            if list_cost is not None and message_count
            else None
        ),
        wall_time_s=round(time.perf_counter() - started, 3),
        results=results,
    )


def _group_names(example: EvalExample) -> list[str]:
    """Report groups for an example: its category and author, or "ambiguous" on its own."""
    if "ambiguous" in example.tags:
        return ["ambiguous"]
    return [
        f"{kind}: {value}"
        for kind, value in (("category", example.category), ("author", example.author))
        if value
    ]
