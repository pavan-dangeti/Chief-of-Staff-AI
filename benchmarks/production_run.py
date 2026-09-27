"""Production-style run of the installed ``cos`` CLI and API against the provider simulator.

Scenarios: cold run with injected 429/529s, warm re-run from cache, full provider outage,
HTTP load test (cold and warm), and an evaluation through the real SDK path.

    python benchmarks/production_run.py --report reports/production-run.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx

from chief_of_staff import __version__

ROOT = Path(__file__).resolve().parents[1]
SIM_ENV = {
    "SIM_LATENCY_MS": "350",
    "SIM_RATE_429": "0.08",
    "SIM_RATE_529": "0.02",
    "SIM_LOW_CONFIDENCE": "0.1",
    "SIM_SEED": "7",
}
RPM = "1200"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_until_up(url: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if httpx.get(url, timeout=1).status_code < 500:
                return
        except httpx.TransportError:
            time.sleep(0.2)
    raise RuntimeError(f"{url} did not come up")


@contextmanager
def process(args: list[str], env: dict[str, str], health_url: str) -> Iterator[None]:
    proc = subprocess.Popen(args, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_until_up(health_url)
        yield
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def build_corpus(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for split in ("dev", "test", "injection"):
        lines = (ROOT / "datasets" / "eval" / f"{split}.jsonl").read_text().splitlines()
        records += [json.loads(line)["message"] for line in lines if line.strip()]
    for sample in ("slack.json", "email.json"):
        records += json.loads((ROOT / "datasets" / "samples" / sample).read_text())
    path.write_text(json.dumps(records))
    return records


def run_cli(args: list[str], env: dict[str, str]) -> float:
    started = time.perf_counter()
    subprocess.run(["cos", *args], env=env, check=True, capture_output=True)
    return time.perf_counter() - started


def retries(trace_path: Path, since: int) -> int:
    lines = trace_path.read_text().splitlines()[since:] if trace_path.exists() else []
    traces = [json.loads(line) for line in lines]
    return sum(
        max(t["attempts"] - 1 - int(t["escalated"]), 0) for t in traces if not t["cache_hit"]
    )


def line_count(path: Path) -> int:
    return len(path.read_text().splitlines()) if path.exists() else 0


def pct(values: list[float], q: int) -> float:
    return (
        statistics.quantiles(values, n=100, method="inclusive")[q - 1] if len(values) > 1 else 0.0
    )


async def load_test(
    base: str, messages: list[dict[str, Any]], concurrency: int
) -> dict[str, float]:
    semaphore = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    errors = 0

    async with httpx.AsyncClient(base_url=base, timeout=120) as client:

        async def one(message: dict[str, Any]) -> None:
            nonlocal errors
            async with semaphore:
                started = time.perf_counter()
                response = await client.post("/v1/extract", json=message)
                latencies.append((time.perf_counter() - started) * 1000)
                errors += response.status_code != 200

        started = time.perf_counter()
        await asyncio.gather(*(one(m) for m in messages))
        elapsed = time.perf_counter() - started
    return {
        "requests": len(messages),
        "errors": errors,
        "p50": pct(latencies, 50),
        "p95": pct(latencies, 95),
        "p99": pct(latencies, 99),
        "rps": len(messages) / elapsed,
    }


def eval_f1(split: str, backend: str, env: dict[str, str], out: Path) -> float:
    run_cli(
        [
            "eval",
            "--split",
            split,
            "--backend",
            backend,
            "--no-cache",
            "--bootstrap",
            "200",
            "--data-dir",
            str(ROOT / "datasets" / "eval"),
            "--json",
            str(out),
        ],
        env,
    )
    return float(json.loads(out.read_text())["item_level"]["f1"])


def main(report: Path) -> None:
    if shutil.which("cos") is None:
        sys.exit("install the package first: pip install '.[anthropic,api]'")
    work = Path(tempfile.mkdtemp(prefix="cos-prod-"))
    corpus_path, outage_path = work / "inbox.json", work / "outage.json"
    corpus = build_corpus(corpus_path)
    outage_path.write_text(json.dumps(corpus[:32]))
    sim_port, api_port = free_port(), free_port()
    sim_url, api_url = f"http://127.0.0.1:{sim_port}", f"http://127.0.0.1:{api_port}"
    trace_path = work / "traces.jsonl"
    env = {
        **os.environ,
        **SIM_ENV,
        "ANTHROPIC_API_KEY": "sk-simulated",
        "ANTHROPIC_BASE_URL": sim_url,
        "COS_BACKEND": "anthropic",
        "COS_ANTHROPIC_RPM": RPM,
        "COS_MAX_CONCURRENCY": "16",
        "COS_CACHE_PATH": str(work / "cache.sqlite"),
        "COS_TRACE_PATH": str(trace_path),
    }
    simulator = [
        sys.executable,
        "-m",
        "uvicorn",
        "provider_simulator:app",
        "--app-dir",
        str(ROOT / "benchmarks"),
        "--port",
        str(sim_port),
        "--log-level",
        "warning",
    ]
    rows: list[tuple[str, float, dict[str, Any], int]] = []

    def scenario(name: str, inbox: Path, extra: list[str], overrides: dict[str, str]) -> None:
        output = work / f"{len(rows)}.json"
        since = line_count(trace_path)
        args = ["run", "--slack", str(inbox), "--format", "json", "--output", str(output), *extra]
        elapsed = run_cli(args, {**env, **overrides})
        stats = json.loads(output.read_text())["stats"]
        rows.append((name, elapsed, stats, retries(trace_path, since)))

    with process(simulator, env, f"{sim_url}/stats"):
        scenario("Cold run with injected 429/529s", corpus_path, [], {})
        scenario("Warm re-run of the same inbox", corpus_path, [], {})
        sim = httpx.get(f"{sim_url}/stats").json()
    breaker_off = {"COS_CIRCUIT_FAILURE_THRESHOLD": "1000000"}
    scenario("Provider down, circuit breaker off", outage_path, ["--no-cache"], breaker_off)
    scenario("Provider down, circuit breaker on", outage_path, ["--no-cache"], {})

    api_env = {**env, "COS_CACHE_PATH": str(work / "api-cache.sqlite")}
    api = ["cos", "serve", "--port", str(api_port)]
    with process(simulator, env, f"{sim_url}/stats"), process(api, api_env, f"{api_url}/healthz"):
        cold = asyncio.run(load_test(api_url, corpus, concurrency=32))
        warm = asyncio.run(load_test(api_url, corpus, concurrency=32))
        sdk_f1 = eval_f1("test", "anthropic", env, work / "eval-sdk.json")
    direct_f1 = eval_f1("test", "heuristic", env, work / "eval-direct.json")

    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        render(
            corpus, rows=rows, sim=sim, cold=cold, warm=warm, sdk_f1=sdk_f1, direct_f1=direct_f1
        ),
        encoding="utf-8",
    )
    print(report.read_text())
    shutil.rmtree(work, ignore_errors=True)


def render(
    corpus: list[dict[str, Any]],
    *,
    rows: list[tuple[str, float, dict[str, Any], int]],
    sim: dict[str, int],
    cold: dict[str, float],
    warm: dict[str, float],
    sdk_f1: float,
    direct_f1: float,
) -> str:
    failed = sum(stats["messages_failed"] for _, _, stats, _ in rows)
    off, on = rows[2][1], rows[3][1]
    lines = [
        "## Production-style run",
        "",
        f"`chief-of-staff-ai` {__version__} installed from its wheel on Python "
        f"{platform.python_version()}; {len(corpus)} messages (all dataset splits and the demo "
        "inbox). The real Anthropic SDK calls "
        "[`provider_simulator.py`](../benchmarks/provider_simulator.py) over HTTP with "
        f"{SIM_ENV['SIM_LATENCY_MS']} ms mean latency, 8% HTTP 429 (`Retry-After: 1`), 2% HTTP "
        f"529 and 10% low-confidence answers, under a client-side limit of {RPM} requests per "
        "minute. This measures the system around the model, not model quality.",
        "",
        "| Scenario | Messages | Wall time | Model calls | Retries | Cache hits | Escalations "
        "| Fallbacks | Failed |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, elapsed, stats, retried in rows:
        lines.append(
            f"| {name} | {stats['messages_total']} | {elapsed:.1f} s | {stats['llm_calls']} "
            f"| {retried} | {stats['cache_hits']} | {stats['escalations']} | {stats['fallbacks']} "
            f"| {stats['messages_failed']} |"
        )
    lines += [
        "",
        f"The simulator answered {sim.get('requests', 0)} requests: {sim.get('http_429', 0)} with "
        f"429 and {sim.get('http_529', 0)} with 529. Messages failed across all scenarios: "
        f"{failed}. With the provider down, the circuit breaker cut the time to serve the same "
        f"inbox from the offline fallback from {off:.1f} s to {on:.1f} s. Wall times include "
        "process start-up.",
        "",
        "| `POST /v1/extract`, 32 concurrent clients | Requests | Errors | p50 | p95 | p99 "
        "| Throughput |",
        "|---|---|---|---|---|---|---|",
    ]
    for label, result in (
        ("Cold: every request reaches the provider", cold),
        ("Warm: same messages, served from cache", warm),
    ):
        lines.append(
            f"| {label} | {result['requests']:.0f} | {result['errors']:.0f} "
            f"| {result['p50']:.0f} ms | {result['p95']:.0f} ms | {result['p99']:.0f} ms "
            f"| {result['rps']:.0f} req/s |"
        )
    verdict = "identical" if abs(sdk_f1 - direct_f1) < 1e-9 else "different"
    lines += [
        "",
        f"Evaluation parity on the test split: item F1 {direct_f1:.3f} calling the rules "
        f"directly and {sdk_f1:.3f} through redaction, the SDK, HTTP, injected faults, retries, "
        f"escalation and verification ({verdict}).",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=ROOT / "reports" / "production-run.md")
    main(parser.parse_args().report)
