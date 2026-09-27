"""Shared builders and fakes for the test suite."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from chief_of_staff.extraction.prompt import TOOL_NAME
from chief_of_staff.models import Message, Source

ROOT = Path(__file__).resolve().parents[1]
IST = timezone(timedelta(hours=5, minutes=30))
MONDAY = datetime(2026, 9, 14, 10, 0, tzinfo=IST)


def make_message(
    text: str,
    *,
    id: str = "m1",
    source: Source = Source.SLACK,
    sender: str = "Priya",
    role: str = "manager",
    channel: str | None = "#eng",
    when: datetime = MONDAY,
    recipients: tuple[str, ...] = (),
    automated: bool = False,
    thread: str | None = None,
) -> Message:
    return Message(
        id=id,
        source=source,
        sender=sender,
        sender_role=role,
        channel=channel,
        timestamp=when,
        text=text,
        recipients=recipients,
        is_automated=automated,
        thread_id=thread,
    )


def item(
    evidence: str,
    *,
    kind: str = "request",
    action: str | None = None,
    owner: str | None = None,
    requester: str | None = None,
    deadline_text: str | None = None,
    due_date: str | None = None,
    confidence: float = 0.9,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "action": action or evidence,
        "owner": owner,
        "requester": requester,
        "deadline_text": deadline_text,
        "due_date": due_date,
        "evidence": evidence,
        "confidence": confidence,
    }


class StatusError(Exception):
    """Mimics an SDK HTTP error: ``status_code`` plus a response carrying headers."""

    def __init__(self, status: int, retry_after: float | None = None) -> None:
        super().__init__(f"HTTP {status}")
        self.status_code = status
        headers = {"retry-after": str(retry_after)} if retry_after is not None else {}
        self.response = SimpleNamespace(headers=headers)


def anthropic_response(items: list[dict[str, Any]], tokens: tuple[int, int] = (120, 30)) -> Any:
    return SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="Recording items."),
            SimpleNamespace(type="tool_use", name=TOOL_NAME, input={"items": items}),
        ],
        usage=SimpleNamespace(input_tokens=tokens[0], output_tokens=tokens[1]),
    )


class FakeAnthropic:
    """Scripted stand-in for ``AsyncAnthropic``: ``client.messages.create(**kwargs)``."""

    def __init__(self, *responses: Any) -> None:
        self.calls: list[dict[str, Any]] = []
        self._responses = list(responses)
        self.messages = self

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        response = self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]
        if isinstance(response, BaseException):
            raise response
        return response


def gemini_response(payload: Any, tokens: tuple[int, int] | None = (90, 25)) -> Any:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    usage = (
        SimpleNamespace(prompt_token_count=tokens[0], candidates_token_count=tokens[1])
        if tokens
        else None
    )
    return SimpleNamespace(text=text, usage_metadata=usage)


class FakeGemini:
    """Scripted stand-in for ``genai.Client``: ``client.aio.models.generate_content(...)``."""

    def __init__(self, *responses: Any) -> None:
        self.calls: list[dict[str, Any]] = []
        self._responses = list(responses)
        self.aio = SimpleNamespace(models=self)

    async def generate_content(self, *, model: str, contents: str, config: Any) -> Any:
        self.calls.append({"model": model, "contents": contents, "config": config})
        response = self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]
        if isinstance(response, BaseException):
            raise response
        return response


def make_action_item(
    evidence: str,
    *,
    id: str = "m1:0",
    message_id: str | None = None,
    action: str | None = None,
    kind: str = "request",
    owner: str | None = "Sam",
    role: str = "engineer",
    due: str | None = None,
    confidence: float = 0.9,
    channel: str | None = "#eng",
    when: datetime = MONDAY,
    thread: str | None = None,
    source: Source = Source.SLACK,
) -> Any:
    from datetime import date

    from chief_of_staff.models import ActionItem, ItemKind

    return ActionItem(
        id=id,
        kind=ItemKind(kind),
        action=action or evidence,
        owner=owner,
        requester=None,
        deadline_text=None,
        due_date=date.fromisoformat(due) if due else None,
        evidence=evidence,
        confidence=confidence,
        message_id=message_id or id.split(":", maxsplit=1)[0],
        source=source,
        channel=channel,
        sender="Priya",
        sender_role=role,
        timestamp=when,
        thread_id=thread,
        backend="test",
        model="test",
    )


def dataset_examples() -> list[Any]:
    from chief_of_staff.evaluation.runner import load_split

    return [
        example
        for split in ("dev", "test", "injection")
        for example in load_split(ROOT / "datasets" / "eval" / f"{split}.jsonl")
    ]
