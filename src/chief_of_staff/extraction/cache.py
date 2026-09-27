"""Content-addressed response cache keyed by prompt version, backend, model and prompt."""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Self

from chief_of_staff.extraction.prompt import PROMPT_VERSION
from chief_of_staff.models import RawExtraction


class ExtractionCache:
    def __init__(self, path: Path | str) -> None:
        target = str(path)
        if target != ":memory:":
            Path(target).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(target, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock, self._conn:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS extractions ("
                "key TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL)"
            )

    @staticmethod
    def key(backend: str, model: str, prompt: str) -> str:
        material = "\x1f".join((PROMPT_VERSION, backend, model, prompt))
        return hashlib.sha256(material.encode()).hexdigest()

    def get(self, key: str) -> RawExtraction | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM extractions WHERE key = ?", (key,)
            ).fetchone()
        return RawExtraction.model_validate_json(row[0]) if row else None

    def put(self, key: str, value: RawExtraction) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO extractions (key, payload, created_at) VALUES (?, ?, ?)",
                (key, value.model_dump_json(), datetime.now(UTC).isoformat()),
            )

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
