"""Read-only Gmail ingestion. Requires the ``gmail`` extra."""

from __future__ import annotations

import base64
import re
from collections.abc import Iterator
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from pathlib import Path
from typing import Any

from chief_of_staff.errors import require_extra
from chief_of_staff.ingest.email_text import clean_email_body
from chief_of_staff.models import Message, Source

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
_NOREPLY = re.compile(r"no-?reply|do-?not-?reply|notifications?@|mailer|newsletter|digest", re.I)


def header(headers: list[dict[str, str]], name: str) -> str:
    return next((h["value"] for h in headers if h["name"].lower() == name.lower()), "")


def is_automated(headers: list[dict[str, str]]) -> bool:
    if header(headers, "List-Unsubscribe") or header(headers, "List-Id"):
        return True
    if header(headers, "Precedence").lower() in {"bulk", "list", "junk"}:
        return True
    if header(headers, "Auto-Submitted").lower() not in {"", "no"}:
        return True
    return bool(_NOREPLY.search(parseaddr(header(headers, "From"))[1]))


def _walk(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield payload
    for part in payload.get("parts", []):
        yield from _walk(part)


def extract_body(payload: dict[str, Any]) -> str:
    plain = html_part = None
    for part in _walk(payload):
        data = part.get("body", {}).get("data")
        if not data:
            continue
        decoded = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "ignore")
        mime = part.get("mimeType", "")
        if mime == "text/plain" and plain is None:
            plain = decoded
        elif mime == "text/html" and html_part is None:
            html_part = decoded
    chosen = plain if plain and plain.strip() else html_part or ""
    return clean_email_body(chosen)


def parse_gmail_message(message: dict[str, Any], roles: dict[str, str] | None = None) -> Message:
    payload = message["payload"]
    headers = payload.get("headers", [])
    sender_name, sender_address = parseaddr(header(headers, "From"))
    recipients = tuple(
        name or address for name, address in getaddresses([header(headers, "To")]) if address
    )
    automated = is_automated(headers)
    return Message(
        id=f"gmail:{message['id']}",
        source=Source.EMAIL,
        sender=sender_name or sender_address,
        sender_role=(roles or {}).get(
            sender_address.lower(), "automated" if automated else "unknown"
        ),
        channel=header(headers, "Subject") or None,
        thread_id=f"gmail:{message['threadId']}" if message.get("threadId") else None,
        timestamp=parsedate_to_datetime(header(headers, "Date")),
        text=extract_body(payload),
        recipients=recipients,
        is_automated=automated,
    )


def gmail_service(credentials_path: Path, token_path: Path) -> Any:
    transport = require_extra("google.auth.transport.requests", "gmail")
    credentials = require_extra("google.oauth2.credentials", "gmail")
    oauth_flow = require_extra("google_auth_oauthlib.flow", "gmail")
    discovery = require_extra("googleapiclient.discovery", "gmail")

    creds = (
        credentials.Credentials.from_authorized_user_file(str(token_path), SCOPES)
        if token_path.exists()
        else None
    )
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(transport.Request())
        else:
            flow = oauth_flow.InstalledAppFlow.from_client_secrets_file(
                str(credentials_path), SCOPES
            )
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())
    return discovery.build("gmail", "v1", credentials=creds, cache_discovery=False)


def fetch_messages(
    service: Any,
    *,
    query: str = "newer_than:7d",
    limit: int = 100,
    roles: dict[str, str] | None = None,
) -> list[Message]:
    refs: list[dict[str, Any]] = []
    page_token = None
    while len(refs) < limit:
        response = (
            service.users()
            .messages()
            .list(
                userId="me", q=query, maxResults=min(100, limit - len(refs)), pageToken=page_token
            )
            .execute()
        )
        refs.extend(response.get("messages", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return [
        parse_gmail_message(
            service.users().messages().get(userId="me", id=ref["id"], format="full").execute(),
            roles,
        )
        for ref in refs[:limit]
    ]
