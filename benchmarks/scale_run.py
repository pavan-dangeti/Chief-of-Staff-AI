"""Scale run: up to 10,000 messages through the offline pipeline, the ledger, and the hosted-model
path (installed CLI and real Anthropic SDK against the provider simulator).

The corpus repeats the 183 synthetic messages from the datasets with unique ids and timestamps one
minute apart, so its text is highly repetitive: many items merge as duplicates. That makes it a
stress test for deduplication, not a realistic inbox.

    python benchmarks/scale_run.py --report reports/scale-run.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import resource
import subprocess
import sys
import tempfile
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx

from chief_of_staff import __version__
from chief_of_staff.config import Settings
from chief_of_staff.extraction.factory import build_service
from chief_of_staff.ledger import Ledger
from chief_of_staff.models import Digest, Message
from chief_of_staff.pipeline import Pipeline
from production_run import ROOT, SIM_ENV, build_corpus, free_port, pct, process, retries

SIZES = (1_000, 2_500, 5_000, 10_000)
# ru_maxrss is in bytes on macOS and kilobytes on Linux.
_RSS_UNIT = 1 if sys.platform == "darwin" else 1024


def corpus(base: list[dict[str, Any]], size: int) -> list[Message]:
    messages = []
    for index in range(size):
        message = Message.model_validate(base[index % len(base)])
        messages.append(
            message.model_copy(
                update={
                    "id": f"{message.id}-{index}",
                    "timestamp": message.timestamp + timedelta(minutes=index),
                }
            )
        )
    return messages


def offline(messages: list[Message]) -> tuple[float, Digest]:
    settings = Settings(backend="heuristic", cache_enabled=False, trace_path=None, _env_file=None)
    service = build_service(settings)
    started = time.perf_counter()
    digest = asyncio.run(Pipeline(service).run(messages))
    return time.perf_counter() - started, digest


def peak_mib(who: int) -> float:
    return resource.getrusage(who).ru_maxrss * _RSS_UNIT / 2**20


def hosted(base: list[dict[str, Any]], work: Path, size: int) -> dict[str, Any]:
    inbox = work / "inbox.json"
    inbox.write_text(json.dumps([m.model_dump(mode="json") for m in corpus(base, size)]))
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    traces = work / "traces.jsonl"
    env = {
        **os.environ,
        **SIM_ENV,
        "ANTHROPIC_API_KEY": "sk-simulated",
        "ANTHROPIC_BASE_URL": url,
        "COS_BACKEND": "anthropic",
        "COS_ANTHROPIC_RPM": "60000",
        "COS_MAX_CONCURRENCY": "64",
        "COS_CACHE_PATH": str(work / "cache.sqlite"),
        "COS_TRACE_PATH": str(traces),
    }
    simulator = [
        sys.executable, "-m", "uvicorn", "provider_simulator:app",
        "--app-dir", str(ROOT / "benchmarks"), "--port", str(port), "--log-level", "warning",
    ]  # fmt: skip
    output = work / "digest.json"
    with process(simulator, env, f"{url}/stats"):
        started = time.perf_counter()
        subprocess.run(
            ["cos", "run", "--slack", str(inbox), "--format", "json", "--output", str(output)],
            env=env,
            check=True,
            capture_output=True,
        )
        elapsed = time.perf_counter() - started
        injected = httpx.get(f"{url}/stats").json()
    stats = json.loads(output.read_text())["stats"]
    calls = [json.loads(line) for line in traces.read_text().splitlines()]
    call_ms = [c["call_ms"] for c in calls if c["call_ms"] > 0]
    return {
        "elapsed": elapsed,
        "stats": stats,
        "retries": retries(traces, 0),
        "injected": injected,
        "call_p50": pct(call_ms, 50),
        "call_p95": pct(call_ms, 95),
        "cli_peak_mib": peak_mib(resource.RUSAGE_CHILDREN),
    }


def main(report: Path) -> None:
    work = Path(tempfile.mkdtemp(prefix="cos-scale-"))
    base = build_corpus(work / "base.json")
    growth = []
    for size in SIZES:
        elapsed, digest = offline(corpus(base, size))
        growth.append((size, elapsed, digest, peak_mib(resource.RUSAGE_SELF)))
    _, _, largest, _ = growth[-1]
    with Ledger(work / "ledger.sqlite") as ledger:
        started = time.perf_counter()
        first = ledger.sync(largest)
        first_s = time.perf_counter() - started
        started = time.perf_counter()
        again = ledger.sync(largest)
        again_s = time.perf_counter() - started
    run = hosted(base, work, SIZES[-1])

    lines = [
        "## Scale run",
        "",
        f"chief-of-staff-ai {__version__}, Python {platform.python_version()}, "
        f"{platform.system()} {platform.machine()}, {os.cpu_count()} CPUs. "
        f"Corpus: the {len(base)} synthetic dataset messages repeated with unique ids, one "
        "minute apart (repetitive text, so many items merge: a deduplication stress test).",
        "",
        "### Offline pipeline (rules, in process)",
        "",
        "| Messages | Wall time | Messages/s | Items before dedupe | Open items | Merged | "
        "Peak memory |",
        "|---|---|---|---|---|---|---|",
    ]
    for size, elapsed, digest, mib in growth:
        stats = digest.stats
        lines.append(
            f"| {size:,} | {elapsed:.1f} s | {size / elapsed:,.0f} | {stats.items_extracted:,} "
            f"| {len(digest.open_items):,} | {stats.duplicates_merged:,} | {mib:,.0f} MiB |"
        )
    stats = run["stats"]
    lines += [
        "",
        "Peak memory is the process maximum so far, so each row includes the rows above it. "
        "Deduplication compares every pair of items, so time grows with the square of the "
        "item count.",
        "",
        "### Ledger (SQLite) for the 10,000-message digest",
        "",
        f"- First sync: {first.added:,} added in {first_s:.2f} s.",
        f"- Repeat sync of the same digest: {again.added} added, {again.updated:,} updated in "
        f"{again_s:.2f} s.",
        "",
        "### 10,000 messages through the hosted-model path",
        "",
        "Installed `cos` CLI, real Anthropic SDK over HTTP, provider simulator with "
        f"{SIM_ENV['SIM_LATENCY_MS']} ms latency, {float(SIM_ENV['SIM_RATE_429']):.0%} HTTP 429 "
        f"and {float(SIM_ENV['SIM_RATE_529']):.0%} HTTP 529, 64 messages in flight. The "
        "simulator answers with the rules engine, so this measures the system around the "
        "model, not model quality.",
        "",
        "| Wall time | Messages/s | Model calls | Retries | Failed | Faults injected "
        "| Call p50 / p95 | CLI peak memory |",
        "|---|---|---|---|---|---|---|---|",
        f"| {run['elapsed']:.0f} s | {SIZES[-1] / run['elapsed']:.0f} | {stats['llm_calls']:,} "
        f"| {run['retries']:,} | {stats['messages_failed']} "
        f"| {run['injected'].get('http_429', 0)} × 429, {run['injected'].get('http_529', 0)} × 529 "
        f"| {run['call_p50']:.0f} / {run['call_p95']:.0f} ms | {run['cli_peak_mib']:,.0f} MiB |",
    ]
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(report.read_text())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--report", type=Path, default=ROOT / "reports" / "scale-run.md")
    main(parser.parse_args().report)
