"""SQLite ledger that tracks commitments across runs until a completion closes them."""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from chief_of_staff.lifecycle import completion_score, is_duplicate
from chief_of_staff.models import ActionItem, Digest, Status

_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    priority TEXT,
    due_date TEXT,
    owner TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS items_status ON items(status);
"""


@dataclass(frozen=True)
class SyncResult:
    added: int = 0
    updated: int = 0
    closed: int = 0


class Ledger:
    def __init__(self, path: Path | str) -> None:
        target = str(path)
        if target != ":memory:":
            Path(target).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(target, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock, self._conn:
            self._conn.executescript(_SCHEMA)

    def items(self, status: Status | None = None) -> list[ActionItem]:
        query, params = "SELECT payload FROM items", tuple[str, ...]()
        if status is not None:
            query, params = f"{query} WHERE status = ?", (status.value,)
        with self._lock:
            rows = self._conn.execute(f"{query} ORDER BY priority, due_date", params).fetchall()
        return [ActionItem.model_validate_json(row[0]) for row in rows]

    def overdue(self, as_of: date) -> list[ActionItem]:
        return [i for i in self.items(Status.OPEN) if i.due_date is not None and i.due_date < as_of]

    def sync(self, digest: Digest) -> SyncResult:
        now = datetime.now(UTC).isoformat()
        added = updated = closed = 0
        known = {item.id: item for item in self.items()}
        open_items = [item for item in known.values() if item.status is Status.OPEN]

        def find_existing(item: ActionItem) -> ActionItem | None:
            if item.id in known:
                return known[item.id]
            return next((o for o in open_items if is_duplicate(o, item)), None)

        with self._lock, self._conn:
            for item in [*digest.open_items, *digest.resolved_items]:
                existing = find_existing(item)
                if existing is None:
                    self._upsert(item, now, first_seen=now)
                    known[item.id] = item
                    if item.status is Status.OPEN:
                        open_items.append(item)
                    added += 1
                    continue
                merged = (
                    item
                    if existing.id == item.id
                    else existing.model_copy(
                        update={
                            "related_message_ids": sorted(
                                {*existing.related_message_ids, item.message_id}
                            ),
                            "status": item.status,
                            "resolved_by": item.resolved_by or existing.resolved_by,
                        }
                    )
                )
                closed += existing.status is Status.OPEN and merged.status is Status.DONE
                updated += 1
                self._upsert(merged, now)
            for completion in digest.unmatched_completions:
                candidates = [
                    (completion_score(completion, item), item) for item in self._open(known)
                ]
                score, target = max(candidates, key=lambda pair: pair[0], default=(0.0, None))
                if target is not None and score > 0:
                    done = target.model_copy(
                        update={"status": Status.DONE, "resolved_by": completion.message_id}
                    )
                    known[done.id] = done
                    self._upsert(done, now)
                    closed += 1
        return SyncResult(added=added, updated=updated, closed=closed)

    @staticmethod
    def _open(known: dict[str, ActionItem]) -> list[ActionItem]:
        return [item for item in known.values() if item.status is Status.OPEN]

    def _upsert(self, item: ActionItem, now: str, first_seen: str | None = None) -> None:
        self._conn.execute(
            "INSERT INTO items"
            " (id, status, priority, due_date, owner, first_seen, last_seen, payload)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET status = excluded.status, priority = excluded.priority,"
            " due_date = excluded.due_date, owner = excluded.owner, last_seen = excluded.last_seen,"
            " payload = excluded.payload",
            (
                item.id,
                item.status.value,
                item.priority.value if item.priority else None,
                item.due_date.isoformat() if item.due_date else None,
                item.owner,
                first_seen or now,
                now,
                item.model_dump_json(),
            ),
        )

    def close(self) -> None:
        with self._lock:
            self._conn.close()
