"""End-to-end orchestration: prefilter -> concurrent extraction -> lifecycle -> prioritization."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Sequence
from datetime import datetime

from chief_of_staff.extraction.service import ExtractionService, MessageExtraction
from chief_of_staff.lifecycle import apply_completions, deduplicate
from chief_of_staff.models import Digest, Message, RunStats, SkippedMessage, Status
from chief_of_staff.prefilter import skip_reason
from chief_of_staff.prioritization import Prioritizer
from chief_of_staff.tracing import percentile

ProgressCallback = Callable[[int, int], None]
_PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def partition(
    messages: Sequence[Message], *, enabled: bool = True
) -> tuple[list[Message], list[SkippedMessage]]:
    """Split messages into extraction candidates and prefiltered noise."""
    candidates: list[Message] = []
    skipped: list[SkippedMessage] = []
    seen: set[str] = set()
    for message in messages:
        if message.id in seen:
            skipped.append(SkippedMessage(message_id=message.id, reason="duplicate_id"))
            continue
        seen.add(message.id)
        reason = skip_reason(message) if enabled else None
        if reason is None:
            candidates.append(message)
        else:
            skipped.append(SkippedMessage(message_id=message.id, reason=reason))
    return candidates, skipped


def build_digest(
    messages: Sequence[Message],
    extractions: Sequence[MessageExtraction],
    skipped: Sequence[SkippedMessage],
    prioritizer: Prioritizer,
    *,
    as_of: datetime | None,
    wall_time_ms: float,
) -> Digest:
    """Combine per-message extractions into a prioritized, deduplicated digest."""
    reference = (
        as_of or max((m.timestamp for m in messages), default=None) or datetime.now().astimezone()
    )
    today = reference.date()

    texts = {message.id: message.text for message in messages}
    failed = [e for e in extractions if e.error is not None]
    all_items = [item for e in extractions for item in e.items]
    tasks, unmatched, completions_matched = apply_completions(all_items)
    scored = [prioritizer.score(item, today, texts.get(item.message_id, "")) for item in tasks]
    merged, duplicates = deduplicate(scored)
    rescored = [prioritizer.score(item, today, texts.get(item.message_id, "")) for item in merged]
    rescored.sort(
        key=lambda i: (
            _PRIORITY_ORDER[i.priority.value if i.priority else "P3"],
            -(i.score or 0.0),
            i.due_date.toordinal() if i.due_date else 10**7,
            i.timestamp,
        )
    )

    traces = [e.trace for e in extractions]
    latencies = [t.latency_ms for t in traces]
    costs = [t.cost_usd for t in traces if t.cost_usd is not None]
    stats = RunStats(
        messages_total=len(messages),
        messages_skipped=len(skipped),
        messages_failed=len(failed),
        llm_calls=sum(t.attempts for t in traces),
        cache_hits=sum(t.cache_hit for t in traces),
        fallbacks=sum(t.fallback for t in traces),
        escalations=sum(t.escalated for t in traces),
        items_extracted=len(all_items),
        items_dropped_ungrounded=sum(t.dropped_ungrounded for t in traces),
        items_dropped_injection=sum(t.dropped_injection for t in traces),
        owners_cleared=sum(t.owners_cleared for t in traces),
        duplicates_merged=duplicates,
        completions_matched=completions_matched,
        input_tokens=sum(t.input_tokens for t in traces),
        output_tokens=sum(t.output_tokens for t in traces),
        cost_usd=round(sum(costs), 6) if costs else None,
        latency_ms_p50=round(percentile(latencies, 50), 2),
        latency_ms_p95=round(percentile(latencies, 95), 2),
        wall_time_ms=round(wall_time_ms, 2),
    )
    return Digest(
        as_of=reference,
        open_items=[i for i in rescored if i.status is Status.OPEN],
        resolved_items=[i for i in rescored if i.status is Status.DONE],
        unmatched_completions=unmatched,
        skipped=[
            *skipped,
            *(SkippedMessage(message_id=e.message.id, reason=f"failed: {e.error}") for e in failed),
        ],
        stats=stats,
    )


class Pipeline:
    def __init__(
        self,
        service: ExtractionService,
        prioritizer: Prioritizer | None = None,
        *,
        prefilter: bool = True,
    ) -> None:
        self.service = service
        self.prioritizer = prioritizer or Prioritizer()
        self.prefilter = prefilter

    async def run(
        self,
        messages: Sequence[Message],
        *,
        as_of: datetime | None = None,
        progress: ProgressCallback | None = None,
    ) -> Digest:
        started = time.perf_counter()
        candidates, skipped = partition(messages, enabled=self.prefilter)
        done = 0

        async def extract(message: Message) -> MessageExtraction:
            nonlocal done
            result = await self.service.extract_message(message)
            done += 1
            if progress is not None:
                progress(done, len(candidates))
            return result

        extractions = await asyncio.gather(*(extract(m) for m in candidates))
        return build_digest(
            messages,
            extractions,
            skipped,
            self.prioritizer,
            as_of=as_of,
            wall_time_ms=(time.perf_counter() - started) * 1000,
        )
