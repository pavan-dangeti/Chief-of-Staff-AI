"""Read an mbox file, such as a Gmail Takeout export, into messages. Standard library only."""

from __future__ import annotations

import email
import email.policy
import mailbox
from collections.abc import Iterator
from datetime import datetime
from email.message import EmailMessage
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from pathlib import Path

from chief_of_staff.ingest.email_text import clean_email_body
from chief_of_staff.ingest.gmail import is_automated
from chief_of_staff.models import Message, Source


def _body(message: EmailMessage) -> str:
    part = message.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    try:
        content = part.get_content()
    except (LookupError, UnicodeDecodeError):  # unknown or wrong charset
        payload = part.get_payload(decode=True)
        content = payload.decode("utf-8", "ignore") if isinstance(payload, bytes) else ""
    return clean_email_body(content if isinstance(content, str) else "")


def _sent_at(message: EmailMessage) -> datetime | None:
    try:
        sent = parsedate_to_datetime(str(message["Date"]))
    except (TypeError, ValueError):
        return None
    return sent if sent.tzinfo is not None else None


def iter_mbox(path: Path, *, since: datetime | None = None) -> Iterator[Message]:
    """Yield messages sent at or after ``since``; mail without a usable date or body is skipped."""
    box = mailbox.mbox(path, create=False)
    try:
        for key in box.iterkeys():
            message = email.message_from_bytes(box.get_bytes(key), policy=email.policy.default)
            assert isinstance(message, EmailMessage)
            sent = _sent_at(message)
            if sent is None or (since is not None and sent < since):
                continue
            text = _body(message)
            if not text:
                continue
            headers = [{"name": name, "value": str(value)} for name, value in message.items()]
            sender_name, sender_address = parseaddr(str(message.get("From", "")))
            to = [str(message.get(field, "")) for field in ("To", "Cc")]
            automated = is_automated(headers)
            yield Message(
                id=f"mbox:{message.get('Message-ID') or key}",
                source=Source.EMAIL,
                sender=sender_name or sender_address or "unknown",
                sender_role="automated" if automated else "unknown",
                channel=str(message.get("Subject", "")) or None,
                thread_id=str(message.get("In-Reply-To", "")) or None,
                timestamp=sent,
                text=text,
                recipients=tuple(name or address for name, address in getaddresses(to) if address),
                is_automated=automated,
            )
    finally:
        box.close()


def load_mbox(path: Path, *, since: datetime | None = None) -> list[Message]:
    return sorted(iter_mbox(path, since=since), key=lambda m: m.timestamp)
