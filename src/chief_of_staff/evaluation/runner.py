"""Run an extraction service over a labeled split and compute an :class:`EvalReport`."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

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
    latency_ms_p50: float
    latency_ms_p95: float
    input_tokens: int
    output_tokens: int
    cost_usd: float | None
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

    async def run(
        example: EvalExample,
    ) -> tuple[list[ActionItem], bool, str | None, float, int, int, float | None]:
        if prefilter and skip_reason(example.message) is not None:
            return [], True, None, 0.0, 0, 0, None
        result = await service.extract_message(example.message)
        trace = result.trace
        return (
            result.items,
            False,
            result.error,
            trace.latency_ms,
            trace.input_tokens,
            trace.output_tokens,
            trace.cost_usd,
        )

    outputs = await asyncio.gather(*(run(example) for example in examples))

    scores: list[ExampleScore] = []
    results: list[ExampleResult] = []
    attacks = attack_hits = prefilter_fn = failures = 0
    for example, (items, skipped, error, *_rest) in zip(examples, outputs, strict=True):
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

    latencies = [output[3] for output in outputs if not output[1]]
    costs = [output[6] for output in outputs if output[6] is not None]
    return EvalReport(
        split=split,
        backend=service.primary_label,
        examples=len(examples),
        message_level=_prf(scores, "message", bootstrap_iterations),
        item_level=_prf(scores, "items", bootstrap_iterations),
        kind_accuracy=accuracy(scores, "kind"),
        owner_accuracy=accuracy(scores, "owner"),
        due_date_accuracy=accuracy(scores, "due"),
        prefilter_skip_rate=round(sum(o[1] for o in outputs) / len(examples), 4)
        if examples
        else 0.0,
        prefilter_false_negatives=prefilter_fn,
        attack_success_rate=round(attack_hits / attacks, 4) if attacks else None,
        failures=failures,
        latency_ms_p50=round(percentile(latencies, 50), 2),
        latency_ms_p95=round(percentile(latencies, 95), 2),
        input_tokens=sum(o[4] for o in outputs),
        output_tokens=sum(o[5] for o in outputs),
        cost_usd=round(sum(costs), 6) if costs else None,
        wall_time_s=round(time.perf_counter() - started, 3),
        results=results,
    )
