"""Slack ingestion from a workspace export or the Web API, with shared normalization."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from chief_of_staff.models import Message, Source

_MENTION = re.compile(r"<@([A-Z0-9]+)(?:\|[^>]+)?>")
_LINK = re.compile(r"<(https?://[^|>]+)(?:\|([^>]+))?>")
_CHANNEL_REF = re.compile(r"<#[A-Z0-9]+\|([^>]+)>")
_SKIP_SUBTYPES = frozenset(
    {
        "channel_join",
        "channel_leave",
        "channel_topic",
        "channel_purpose",
        "channel_name",
        "pinned_item",
        "message_deleted",
    }
)
_AUTOMATED_SUBTYPES = frozenset({"bot_message", "reminder_add"})


def user_directory(users: Iterable[dict[str, Any]]) -> dict[str, str]:
    directory: dict[str, str] = {}
    for user in users:
        profile = user.get("profile", {})
        directory[user["id"]] = (
            profile.get("display_name")
            or user.get("real_name")
            or profile.get("real_name")
            or user.get("name")
            or user["id"]
        )
    return directory


def _render_text(text: str, users: dict[str, str]) -> str:
    text = _MENTION.sub(lambda m: f"@{users.get(m.group(1), m.group(1))}", text)
    text = _LINK.sub(lambda m: m.group(2) or m.group(1), text)
    text = _CHANNEL_REF.sub(lambda m: f"#{m.group(1)}", text)
    return text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def normalize_slack_message(
    raw: dict[str, Any], channel: str, users: dict[str, str], roles: dict[str, str] | None = None
) -> Message | None:
    subtype = raw.get("subtype")
    text = raw.get("text", "")
    if subtype in _SKIP_SUBTYPES or not text.strip():
        return None
    user_id = raw.get("user", "")
    sender = users.get(user_id, raw.get("username") or user_id or "unknown")
    automated = subtype in _AUTOMATED_SUBTYPES or "bot_id" in raw
    # A user ID is stable; a display name can be copied. Unknown without a directory or for bots.
    verified = None if automated or not users or not user_id else user_id in users
    thread_ts = raw.get("thread_ts")
    return Message(
        id=f"slack:{channel}:{raw['ts']}",
        source=Source.SLACK,
        sender=sender,
        sender_role=(roles or {}).get(sender, "automated" if automated else "unknown"),
        channel=f"#{channel}",
        thread_id=f"slack:{channel}:{thread_ts}" if thread_ts else None,
        timestamp=datetime.fromtimestamp(float(raw["ts"]), tz=UTC),
        text=_render_text(text, users),
        is_automated=automated,
        sender_verified=verified,
    )


def load_slack_export(directory: Path, roles: dict[str, str] | None = None) -> list[Message]:
    """Read a standard Slack export: ``users.json`` plus ``<channel>/<YYYY-MM-DD>.json`` files."""
    users_file = directory / "users.json"
    users = user_directory(json.loads(users_file.read_text())) if users_file.exists() else {}
    messages: list[Message] = []
    for channel_dir in sorted(path for path in directory.iterdir() if path.is_dir()):
        for day_file in sorted(channel_dir.glob("*.json")):
            for raw in json.loads(day_file.read_text()):
                message = normalize_slack_message(raw, channel_dir.name, users, roles)
                if message is not None:
                    messages.append(message)
    return sorted(messages, key=lambda m: m.timestamp)


class SlackClient:
    """Minimal Slack Web API reader with cursor pagination and 429 handling."""

    def __init__(
        self,
        token: str,
        *,
        client: httpx.Client | None = None,
        max_retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client or httpx.Client(base_url="https://slack.com/api", timeout=30)
        self._headers = {"Authorization": f"Bearer {token}"}
        self._max_retries = max_retries
        self._sleep = sleep
        self._users: dict[str, str] | None = None

    def _get(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        for _ in range(self._max_retries + 1):
            response = self._client.get(f"/{method}", params=params, headers=self._headers)
            if response.status_code == 429:
                self._sleep(float(response.headers.get("Retry-After", "1")))
                continue
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
            if not payload.get("ok"):
                raise RuntimeError(f"Slack API {method} failed: {payload.get('error')}")
            return payload
        raise RuntimeError(f"Slack API {method} still rate limited after retries")

    def _paginate(self, method: str, key: str, params: dict[str, Any]) -> Iterator[dict[str, Any]]:
        cursor = None
        while True:
            payload = self._get(method, {**params, **({"cursor": cursor} if cursor else {})})
            yield from payload.get(key, [])
            cursor = payload.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                return

    def users(self) -> dict[str, str]:
        if self._users is None:
            self._users = user_directory(self._paginate("users.list", "members", {"limit": 200}))
        return self._users

    def channel_messages(
        self,
        channel_id: str,
        channel_name: str,
        *,
        oldest: float = 0.0,
        roles: dict[str, str] | None = None,
    ) -> list[Message]:
        users = self.users()
        params = {"channel": channel_id, "oldest": oldest, "limit": 200}
        messages = [
            message
            for raw in self._paginate("conversations.history", "messages", params)
            if (message := normalize_slack_message(raw, channel_name, users, roles)) is not None
        ]
        return sorted(messages, key=lambda m: m.timestamp)
