"""Load messages from JSON or JSONL files (including the v1 mock-data format)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from chief_of_staff.ingest.email_text import clean_email_body
from chief_of_staff.models import Message, Source


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=UTC)
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return parsedate_to_datetime(text)


def _coerce(record: dict[str, Any], default_source: Source | None) -> Message:
    data = dict(record)
    if "source" not in data:
        if default_source is None:
            raise ValueError(f"message {data.get('id')!r} has no 'source' and none was given")
        data["source"] = default_source
    if "channel" not in data and "subject" in data:
        data["channel"] = data.pop("subject")
    data["timestamp"] = _parse_timestamp(data["timestamp"])
    if Source(data["source"]) is Source.EMAIL:
        data["text"] = clean_email_body(str(data.get("text", "")))
    if isinstance(data.get("recipients"), str):
        data["recipients"] = [
            part.strip() for part in data["recipients"].split(",") if part.strip()
        ]
    return Message.model_validate(data)


def load_messages(path: Path, *, source: Source | None = None) -> list[Message]:
    raw = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        records = [json.loads(line) for line in raw.splitlines() if line.strip()]
    else:
        parsed = json.loads(raw)
        records = parsed if isinstance(parsed, list) else parsed.get("messages", [])
    return [_coerce(record, source) for record in records]
