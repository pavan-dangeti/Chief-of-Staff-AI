"""Real-user pilot: a local review page, a text-free label export, and a combined report.

Participants run extraction on their own export, open the generated page in a browser, mark each
item and add the ones the tool missed. The page downloads a JSON file holding labels and coarse
metadata only; message text, names, subjects and channels stay on the participant's machine.
"""

from __future__ import annotations

import json
import math
import uuid
from collections.abc import Iterable, Sequence
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from chief_of_staff import __version__
from chief_of_staff.extraction.prompt import PROMPT_VERSION
from chief_of_staff.models import ActionItem, Digest, ItemKind, Priority, Source

Label = Literal["correct", "wrong_details", "not_a_task"]
_TEMPLATE = Path(__file__).with_name("pilot_review.html")


class PilotItem(BaseModel):
    """One extracted item as exported: no text, names or identifiers from the messages."""

    model_config = ConfigDict(extra="forbid")

    item: str
    kind: ItemKind
    source: Source
    has_owner: bool
    has_due_date: bool
    priority: Priority | None
    confidence: float
    needs_review: bool
    label: Label | None = None


class MissedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ItemKind | None = None
    source: Source | None = None


class PilotRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal[1] = 1
    participant: str = Field(pattern=r"^[A-Za-z0-9_-]{1,32}$")
    run_id: str
    tool_version: str = __version__
    prompt_version: str = PROMPT_VERSION
    backend: str
    window_days: int
    messages_scanned: int
    messages_extracted: int


class PilotExport(PilotRun):
    exported_on: date
    items: list[PilotItem]
    missed: list[MissedItem] = Field(default_factory=list)


def _export_record(item: ActionItem) -> PilotItem:
    return PilotItem(
        item=uuid.uuid4().hex[:12],  # random: cannot be traced back to a message
        kind=item.kind,
        source=item.source,
        has_owner=item.owner is not None,
        has_due_date=item.due_date is not None,
        priority=item.priority,
        confidence=round(item.confidence, 1),
        needs_review=item.needs_review,
    )


def _display(item: ActionItem, status: str) -> dict[str, object]:
    return {
        "action": item.action,
        "owner": item.owner,
        "due": item.due_date.isoformat() if item.due_date else None,
        "evidence": item.evidence,
        "sender": item.sender,
        "where": item.channel,
        "when": item.timestamp.strftime("%d %b %Y %H:%M"),
        "priority": item.priority.value if item.priority else None,
        "status": status,
    }


def review_page(digest: Digest, run: PilotRun) -> str:
    """A self-contained HTML page; it makes no network requests and runs from a local file."""
    groups = (
        (digest.open_items, "open"),
        (digest.resolved_items, "done"),
        (digest.unmatched_completions, "reported done"),
    )
    items = [
        {"export": _export_record(item).model_dump(mode="json"), "display": _display(item, status)}
        for group, status in groups
        for item in group
    ]
    payload = json.dumps({"run": run.model_dump(mode="json"), "items": items}, ensure_ascii=False)
    # Message text can contain "</script>"; escaping "<" keeps it inside the JSON block.
    return _TEMPLATE.read_text(encoding="utf-8").replace(
        "__PILOT_DATA__", payload.replace("<", "\\u003c")
    )


def load_exports(paths: Iterable[Path]) -> list[PilotExport]:
    """Validate every file; for a participant's run exported more than once, keep the last."""
    latest: dict[tuple[str, str], PilotExport] = {}
    for path in paths:
        export = PilotExport.model_validate_json(path.read_text(encoding="utf-8"))
        key = (export.participant, export.run_id)
        if key not in latest or export.exported_on >= latest[key].exported_on:
            latest[key] = export
    return list(latest.values())


def wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float] | None:
    """95% Wilson score interval for a proportion; ``None`` when there is no data."""
    if total == 0:
        return None
    p = successes / total
    centre = (p + z * z / (2 * total)) / (1 + z * z / total)
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return max(0.0, centre - half), min(1.0, centre + half)


class _Tally(BaseModel):
    runs: int = 0
    items: int = 0
    correct: int = 0
    wrong_details: int = 0
    not_a_task: int = 0
    missed: int = 0

    def add(self, export: PilotExport) -> None:
        self.runs += 1
        self.items += len(export.items)
        for item in export.items:
            if item.label is not None:
                setattr(self, item.label, getattr(self, item.label) + 1)
        self.missed += len(export.missed)

    @property
    def real(self) -> int:
        return self.correct + self.wrong_details

    @property
    def reviewed(self) -> int:
        return self.real + self.not_a_task


def _rate(successes: int, total: int) -> str:
    interval = wilson(successes, total)
    if interval is None:
        return "n/a"
    low, high = interval
    return f"{successes / total:.2f} ({low:.2f}–{high:.2f})"


def _row(name: str, tally: _Tally) -> str:
    return (
        f"| {name} | {tally.runs} | {tally.reviewed} of {tally.items} "
        f"| {_rate(tally.real, tally.reviewed)} | {_rate(tally.correct, tally.real)} "
        f"| {tally.missed} | {_rate(tally.real, tally.real + tally.missed)} |"
    )


def pilot_report(exports: Sequence[PilotExport]) -> str:
    per_person: dict[str, _Tally] = {}
    total = _Tally()
    for export in sorted(exports, key=lambda e: e.participant):
        per_person.setdefault(export.participant, _Tally()).add(export)
        total.add(export)
    backends = sorted({export.backend for export in exports})
    lines = [
        "## Real-user pilot",
        "",
        f"Participants: {len(per_person)}. Runs: {total.runs}. Backends: "
        f"{', '.join(backends) or 'none'}. Rates show the 95% Wilson interval.",
        "",
        "| Participant | Runs | Items reviewed | Precision | Details right | Missed items added "
        "| Recall estimate |",
        "|---|---|---|---|---|---|---|",
        *(_row(name, tally) for name, tally in per_person.items()),
        _row("**All**", total),
        "",
        "- **Precision**: items marked a real task (details right or wrong) out of items reviewed.",
        "- **Details right**: of the real tasks, the share with owner and due date also right.",
        "- **Recall estimate**: real tasks found out of those plus the missed tasks participants "
        "added. People only add the misses they notice, so this is an upper bound.",
        "- Items from one person are not independent, so the pooled intervals are too narrow; "
        "the per-participant rows show the spread.",
    ]
    return "\n".join(lines) + "\n"
