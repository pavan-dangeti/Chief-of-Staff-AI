"""Is slow model latency the model, or the endpoint's queue? Analyse one live evaluation run.

Reads the JSONL traces written during ``make eval-llm`` (set ``COS_TRACE_PATH``) and reports
provider call time per minute of the run and its correlation with output length. Generation
time grows with output tokens; queueing does not. ``--recheck`` resends the slow messages once,
one at a time and spaced out, with no cache, to see whether they are still slow.

    python benchmarks/latency_timeline.py .cos/runs/traces.jsonl \
        --model deepseek-ai/deepseek-v4.1-flash --recheck
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any

from chief_of_staff.config import Settings
from chief_of_staff.evaluation.runner import load_split
from chief_of_staff.extraction.factory import build_service

ROOT = Path(__file__).resolve().parents[1]


def load_calls(path: Path, model: str) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    live = [r for r in rows if r["model"] == model and not r["cache_hit"] and r["call_ms"] > 0]
    return sorted(live, key=lambda r: r["timestamp"])


def timeline(calls: list[dict[str, Any]], slow_ms: float) -> list[str]:
    start = datetime.fromisoformat(calls[0]["timestamp"])
    minutes: dict[int, list[float]] = {}
    for call in calls:
        offset = (datetime.fromisoformat(call["timestamp"]) - start).total_seconds()
        minutes.setdefault(int(offset // 60), []).append(call["call_ms"] / 1000)
    lines = ["| Minute of run | Calls | Median | Max | Slower than threshold |"]
    lines.append("|---|---|---|---|---|")
    for minute, values in sorted(minutes.items()):
        slow = sum(value * 1000 > slow_ms for value in values)
        lines.append(
            f"| {minute} | {len(values)} | {statistics.median(values):.1f} s "
            f"| {max(values):.1f} s | {slow} |"
        )
    return lines


async def recheck(model: str, message_ids: list[str], spacing_s: float) -> dict[str, float]:
    examples = {
        example.id: example
        for split in ("test", "injection")
        for example in load_split(ROOT / "datasets" / "eval" / f"{split}.jsonl")
    }
    backend = "gemini" if model.startswith("gemini") else "nvidia"
    settings = Settings(backend=backend, cache_enabled=False, trace_path=None, max_concurrency=1)
    service = build_service(settings.model_copy(update={f"{backend}_model": model}), fallback=False)
    times: dict[str, float] = {}
    try:
        for message_id in message_ids:
            result = await service.extract_message(examples[message_id].message)
            if result.error is None:
                times[message_id] = result.trace.call_ms / 1000
            await asyncio.sleep(spacing_s)
    finally:
        service.close()
    return times


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("traces", type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--slow-ms", type=float, default=10_000)
    parser.add_argument("--recheck", action="store_true", help="resend the slow messages once")
    parser.add_argument("--spacing", type=float, default=5.0, help="seconds between rechecks")
    args = parser.parse_args()

    calls = load_calls(args.traces, args.model)
    times = [call["call_ms"] for call in calls]
    outputs = [call["recorded_output_tokens"] for call in calls]
    slow = [call for call in calls if call["call_ms"] > args.slow_ms]
    lines = [
        f"## Call-time timeline: `{args.model}`",
        "",
        f"{len(calls)} live calls; {len(slow)} slower than {args.slow_ms / 1000:.0f} s. "
        f"Correlation of call time with output tokens: "
        f"{statistics.correlation(outputs, times):.2f}.",
        "",
        *timeline(calls, args.slow_ms),
    ]
    if args.recheck and slow:
        before = {call["message_id"]: call["call_ms"] / 1000 for call in slow}
        again = asyncio.run(recheck(args.model, list(before), args.spacing))
        lines += [
            "",
            f"### Recheck: the {len(before)} slow messages resent once, {args.spacing:.0f} s apart",
            "",
            "| Message | During the run | Recheck |",
            "|---|---|---|",
            *(f"| `{m}` | {before[m]:.1f} s | {again[m]:.1f} s |" for m in before if m in again),
            "",
            f"{len(again)} of {len(before)} rechecks succeeded. Median during the run "
            f"{statistics.median(before.values()):.1f} s"
            + (f", on recheck {statistics.median(again.values()):.1f} s." if again else "."),
        ]
    print("\n".join(lines))


if __name__ == "__main__":
    main()
