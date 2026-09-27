"""Domain models shared by every stage of the pipeline."""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Source(StrEnum):
    SLACK = "slack"
    EMAIL = "email"


class ItemKind(StrEnum):
    REQUEST = "request"
    COMMITMENT = "commitment"
    COMPLETION = "completion"


class Priority(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class Status(StrEnum):
    OPEN = "open"
    DONE = "done"


class Message(BaseModel):
    """A single normalized Slack message or email."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    source: Source
    sender: str
    sender_role: str = "unknown"
    channel: str | None = None
    thread_id: str | None = None
    timestamp: datetime
    text: str
    recipients: tuple[str, ...] = ()
    is_automated: bool = False

    @field_validator("timestamp")
    @classmethod
    def _assume_utc_when_naive(cls, value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _blank_to_none(value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped or stripped.lower() in {"null", "none", "n/a"}:
            return None
        return stripped
    return value


class ExtractedItem(BaseModel):
    """One action item exactly as an extractor reports it, before verification."""

    model_config = ConfigDict(extra="ignore")

    kind: ItemKind
    action: str = Field(min_length=1)
    owner: str | None = None
    requester: str | None = None
    deadline_text: str | None = None
    due_date: date | None = None
    evidence: str = Field(min_length=1)
    confidence: float = 0.5

    @field_validator("owner", "requester", "deadline_text", mode="before")
    @classmethod
    def _optional_text(cls, value: Any) -> Any:
        return _blank_to_none(value)

    @field_validator("action", "evidence", mode="before")
    @classmethod
    def _strip(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("due_date", mode="before")
    @classmethod
    def _lenient_date(cls, value: Any) -> Any:
        value = _blank_to_none(value)
        if isinstance(value, str):
            try:
                return date.fromisoformat(value[:10])
            except ValueError:
                return None
        return value

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_confidence(cls, value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.5
        return min(max(number, 0.0), 1.0)


class ExtractionResponse(BaseModel):
    items: list[ExtractedItem] = Field(default_factory=list)


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )


class RawExtraction(BaseModel):
    """What a backend returned for one message, plus accounting."""

    items: list[ExtractedItem]
    usage: Usage = Field(default_factory=Usage)
    backend: str
    model: str


class ActionItem(BaseModel):
    """A verified, resolved action item tied back to its source message."""

    id: str
    kind: ItemKind
    action: str
    owner: str | None
    requester: str | None
    deadline_text: str | None
    due_date: date | None
    evidence: str
    confidence: float
    message_id: str
    source: Source
    channel: str | None
    sender: str
    sender_role: str
    timestamp: datetime
    thread_id: str | None
    backend: str
    model: str
    priority: Priority | None = None
    score: float | None = None
    reasons: list[str] = Field(default_factory=list)
    needs_review: bool = False
    status: Status = Status.OPEN
    resolved_by: str | None = None
    related_message_ids: list[str] = Field(default_factory=list)


class SkippedMessage(BaseModel):
    message_id: str
    reason: str


class RunStats(BaseModel):
    messages_total: int = 0
    messages_skipped: int = 0
    messages_failed: int = 0
    llm_calls: int = 0
    cache_hits: int = 0
    fallbacks: int = 0
    escalations: int = 0
    items_extracted: int = 0
    items_dropped_ungrounded: int = 0
    items_dropped_injection: int = 0
    owners_cleared: int = 0
    duplicates_merged: int = 0
    completions_matched: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None
    latency_ms_p50: float = 0.0
    latency_ms_p95: float = 0.0
    wall_time_ms: float = 0.0


class Digest(BaseModel):
    as_of: datetime
    open_items: list[ActionItem]
    resolved_items: list[ActionItem]
    unmatched_completions: list[ActionItem]
    skipped: list[SkippedMessage]
    stats: RunStats
