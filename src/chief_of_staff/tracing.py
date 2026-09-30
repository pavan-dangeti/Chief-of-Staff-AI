"""Per-message traces (tokens, cost, latency, outcomes) written as JSON lines, no message text."""

from __future__ import annotations

import statistics
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from chief_of_staff.extraction.prompt import PROMPT_VERSION


class TraceRecord(BaseModel):
    run_id: str
    message_id: str
    backend: str | None = None
    model: str | None = None
    prompt_version: str = PROMPT_VERSION
    cache_hit: bool = False
    attempts: int = 0
    fallback: bool = False
    escalated: bool = False
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None
    # Measured when each answer was produced, so resumed runs keep them for cached answers too.
    call_ms: float = 0.0
    recorded_input_tokens: int = 0
    recorded_output_tokens: int = 0
    list_cost_usd: float | None = None
    items: int = 0
    dropped_ungrounded: int = 0
    dropped_injection: int = 0
    owners_cleared: int = 0
    error: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Tracer:
    def __init__(self, path: Path | None = None, run_id: str | None = None) -> None:
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.records: list[TraceRecord] = []
        self._path = path
        self._lock = threading.Lock()
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, record: TraceRecord) -> None:
        with self._lock:
            self.records.append(record)
            if self._path is not None:
                with self._path.open("a", encoding="utf-8") as handle:
                    handle.write(record.model_dump_json() + "\n")


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[int(pct) - 1]


def cost_usd(
    model: str, input_tokens: int, output_tokens: int, prices: dict[str, tuple[float, float]]
) -> float | None:
    if model not in prices:
        return None
    input_price, output_price = prices[model]
    return round((input_tokens * input_price + output_tokens * output_price) / 1_000_000, 6)
