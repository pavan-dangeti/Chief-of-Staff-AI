"""Model-independent verification: grounding, owner checks, injection guard, deadline resolution."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

from rapidfuzz import fuzz

from chief_of_staff.dates import DateOrder, resolve_deadline
from chief_of_staff.models import ActionItem, ExtractedItem, ItemKind, Message, RawExtraction
from chief_of_staff.redaction import RedactedText
from chief_of_staff.text import first_name, normalize

_UNASSIGNED = frozenset(
    {
        "someone",
        "anyone",
        "somebody",
        "anybody",
        "team",
        "the team",
        "everyone",
        "all",
        "unknown",
        "unassigned",
        "tbd",
        "n/a",
        "we",
        "us",
        "they",
    }
)
_SELF = frozenset({"i", "me", "myself", "sender", "author", "the sender", "the author"})
_AI_DIRECTED = re.compile(
    r"\b(?:ignore (?:all )?(?:previous|prior|above) instructions|system (?:note|instruction|prompt)"
    r"|(?:ai|llm) (?:assistant|agent|model|screening)s?|(?:to|for) (?:the|any|all) (?:ai|bots?|"
    r"assistants?|summari[sz]ation bot)|assistant\s*[:,]|\bai\s*:|you are now|jailbreak)",
    re.IGNORECASE,
)
_MIN_FUZZY_LENGTH = 16
_FUZZY_THRESHOLD = 90.0


@dataclass(frozen=True)
class VerificationStats:
    dropped_ungrounded: int = 0
    dropped_injection: int = 0
    owners_cleared: int = 0


def is_ai_directed(text: str) -> bool:
    return bool(_AI_DIRECTED.search(text))


def is_grounded(evidence: str, text: str) -> bool:
    quote, haystack = normalize(evidence).strip("\"' .…"), normalize(text)
    if not quote:
        return False
    if quote in haystack:
        return True
    return (
        len(quote) >= _MIN_FUZZY_LENGTH and fuzz.partial_ratio(quote, haystack) >= _FUZZY_THRESHOLD
    )


def verify_owner(owner: str | None, message: Message, text: str) -> tuple[str | None, bool]:
    """Return ``(owner, cleared)``; ``cleared`` is True when a named owner was rejected."""
    if owner is None:
        return None, False
    lowered = owner.strip().casefold()
    if lowered in _UNASSIGNED:
        return None, False
    if lowered in _SELF:
        return message.sender, False
    token = first_name(owner)
    if not token:
        return None, True
    if token == first_name(message.sender) or any(
        token == first_name(recipient) for recipient in message.recipients
    ):
        return owner.strip().lstrip("@"), False
    if re.search(rf"(?<![\w]){re.escape(token)}(?![\w])", text.casefold()):
        return owner.strip().lstrip("@"), False
    return None, True


def _plausible(model_date: date | None, sent: date) -> date | None:
    if model_date is None:
        return None
    if sent - timedelta(days=1) <= model_date <= sent + timedelta(days=730):
        return model_date
    return None


def verify_items(
    raw: RawExtraction,
    message: Message,
    redacted: RedactedText,
    *,
    date_order: DateOrder = "DMY",
) -> tuple[list[ActionItem], VerificationStats]:
    verified: list[ActionItem] = []
    dropped = injected = cleared = 0
    for index, item in enumerate(raw.items):
        if not is_grounded(item.evidence, redacted.text):
            dropped += 1
            continue
        if is_ai_directed(item.evidence) or is_ai_directed(item.action):
            injected += 1
            continue
        owner, was_cleared = verify_owner(item.owner, message, redacted.text)
        cleared += was_cleared
        requester, _ = verify_owner(item.requester, message, redacted.text)
        verified.append(
            _to_action_item(
                item,
                index=index,
                owner=owner,
                requester=requester,
                raw=raw,
                message=message,
                redacted=redacted,
                date_order=date_order,
            )
        )
    return verified, VerificationStats(
        dropped_ungrounded=dropped, dropped_injection=injected, owners_cleared=cleared
    )


def _to_action_item(
    item: ExtractedItem,
    *,
    index: int,
    owner: str | None,
    requester: str | None,
    raw: RawExtraction,
    message: Message,
    redacted: RedactedText,
    date_order: DateOrder,
) -> ActionItem:
    deadline_text = redacted.restore(item.deadline_text)
    due = None
    if item.kind is not ItemKind.COMPLETION:
        due = resolve_deadline(
            deadline_text, message.timestamp, date_order=date_order
        ) or _plausible(item.due_date, message.timestamp.date())
    return ActionItem(
        id=f"{message.id}:{index}",
        kind=item.kind,
        action=redacted.restore(item.action) or item.action,
        owner=redacted.restore(owner),
        requester=redacted.restore(requester),
        deadline_text=deadline_text,
        due_date=due,
        evidence=redacted.restore(item.evidence) or item.evidence,
        confidence=round(item.confidence, 3),
        message_id=message.id,
        source=message.source,
        channel=message.channel,
        sender=message.sender,
        sender_role=message.sender_role,
        timestamp=message.timestamp,
        thread_id=message.thread_id,
        backend=raw.backend,
        model=raw.model,
    )
