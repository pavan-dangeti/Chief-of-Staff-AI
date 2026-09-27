"""Latency benchmark: v1's sequential loop vs v2's concurrent, cached pipeline.

Uses a simulated backend with a fixed per-call latency so the numbers measure orchestration,
not a provider's mood. v1 slept 1.5 s after every call regardless of backend; that cost is
modelled explicitly.

    python benchmarks/bench_latency.py --messages 100 --latency 0.4
"""

from __future__ import annotations

import argparse
import asyncio
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from chief_of_staff.extraction.cache import ExtractionCache
from chief_of_staff.extraction.heuristic import HeuristicExtractor
from chief_of_staff.extraction.service import Backend, ExtractionService
from chief_of_staff.models import Message, RawExtraction, Source
from chief_of_staff.pipeline import Pipeline
from chief_of_staff.tracing import Tracer

V1_SLEEP_S = 1.5


class SimulatedLLM:
    name = "simulated"
    model = "fixed-latency"

    def __init__(self, latency_s: float) -> None:
        self.latency_s = latency_s
        self._rules = HeuristicExtractor()

    async def extract(self, message: Message, body: str) -> RawExtraction:
        await asyncio.sleep(self.latency_s)
        raw = await self._rules.extract(message, body)
        return raw.model_copy(update={"backend": self.name, "model": self.model})


def corpus(size: int) -> list[Message]:
    start = datetime(2026, 9, 21, 9, tzinfo=UTC)
    return [
        Message(
            id=f"m{i}",
            source=Source.SLACK,
            sender=f"user{i % 7}",
            sender_role="engineer",
            channel="#eng",
            timestamp=start + timedelta(minutes=i),
            text=f"@Divya can you review PR #{i} for the billing service by Friday?",
        )
        for i in range(size)
    ]


async def timed(pipeline: Pipeline, messages: list[Message]) -> float:
    started = time.perf_counter()
    await pipeline.run(messages)
    return time.perf_counter() - started


async def main(count: int, latency: float, concurrency: int) -> None:
    messages = corpus(count)
    with tempfile.TemporaryDirectory() as tmp:
        cache = ExtractionCache(Path(tmp) / "cache.sqlite")
        service = ExtractionService(
            chain=[Backend(SimulatedLLM(latency))],
            cache=cache,
            tracer=Tracer(),
            max_concurrency=concurrency,
        )
        pipeline = Pipeline(service)
        cold = await timed(pipeline, messages)
        warm = await timed(pipeline, messages)
        cache.close()
    v1 = count * (latency + V1_SLEEP_S)
    print(f"| Scenario ({count} messages, {latency * 1000:.0f} ms per model call) | Wall time |")
    print("|---|---|")
    print(f"| v1 sequential loop + 1.5 s sleep (modelled) | {v1:.1f} s |")
    print(f"| v2 concurrent, cold cache (concurrency {concurrency}) | {cold:.2f} s |")
    print(f"| v2 re-run, warm cache | {warm * 1000:.0f} ms |")
    print(f"\nSpeed-up cold: {v1 / cold:.0f}x, warm: {v1 / warm:.0f}x")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--messages", type=int, default=100)
    parser.add_argument("--latency", type=float, default=0.4)
    parser.add_argument("--concurrency", type=int, default=16)
    args = parser.parse_args()
    asyncio.run(main(args.messages, args.latency, args.concurrency))
