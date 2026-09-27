from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from chief_of_staff.ingest.email_text import clean_email_body, html_to_text, strip_quoted_reply
from chief_of_staff.ingest.files import load_messages
from chief_of_staff.ingest.gmail import fetch_messages, is_automated, parse_gmail_message
from chief_of_staff.ingest.slack import SlackClient, load_slack_export
from chief_of_staff.models import Source


def test_loads_v1_format_json_with_subject_and_rfc2822_dates(tmp_path: Path) -> None:
    path = tmp_path / "emails.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "e1",
                    "sender": "Omar",
                    "sender_role": "customer",
                    "subject": "Renewal",
                    "timestamp": "Mon, 21 Sep 2026 18:00:00 +0530",
                    "text": "Please sign.\n> old quote",
                    "recipients": "Sofia, Arjun",
                }
            ]
        )
    )
    [message] = load_messages(path, source=Source.EMAIL)
    assert (message.channel, message.recipients, message.text) == (
        "Renewal",
        ("Sofia", "Arjun"),
        "Please sign.",
    )
    assert message.timestamp.utcoffset() is not None


def test_loads_jsonl_and_requires_a_source(tmp_path: Path) -> None:
    path = tmp_path / "slack.jsonl"
    path.write_text(
        '{"id": "s1", "source": "slack", "sender": "Leo", "timestamp": 1790000000, "text": "hi"}\n\n'
    )
    assert load_messages(path)[0].timestamp.tzinfo is not None
    path.write_text(
        '{"id": "s1", "sender": "Leo", "timestamp": "2026-09-21T10:00:00Z", "text": "hi"}\n'
    )
    with pytest.raises(ValueError, match="no 'source'"):
        load_messages(path)


def test_email_cleaning_strips_html_quotes_and_signatures() -> None:
    html = "<html><style>p{}</style><p>Please&nbsp;sign&zwnj; the form.</p><br>Thanks</html>"
    assert html_to_text(html) == "Please sign the form.\nThanks"
    reply = "Done, paid it.\n\nOn Mon, Sep 21, 2026 at 5:10 PM Priya wrote:\n> can you pay it?"
    assert strip_quoted_reply(reply) == "Done, paid it."
    assert (
        clean_email_body("Ship it Friday.\n--\nSam | CTO\nSent from my phone") == "Ship it Friday."
    )
    assert clean_email_body("x" * 5000, max_chars=100) == "x" * 100


def test_slack_export_resolves_mentions_threads_and_drops_noise(tmp_path: Path) -> None:
    (tmp_path / "users.json").write_text(
        json.dumps(
            [
                {"id": "U1", "name": "leo", "profile": {"display_name": "Leo"}},
                {"id": "U2", "real_name": "Arjun Rao", "profile": {}},
            ]
        )
    )
    channel = tmp_path / "eng"
    channel.mkdir()
    (channel / "2026-09-21.json").write_text(
        json.dumps(
            [
                {
                    "type": "message",
                    "user": "U1",
                    "ts": "1790000100.0001",
                    "text": "<@U2> please revert <https://git.io/pr|the PR>",
                },
                {
                    "type": "message",
                    "subtype": "channel_join",
                    "user": "U2",
                    "ts": "1790000000.0",
                    "text": "joined",
                },
                {
                    "type": "message",
                    "user": "U2",
                    "ts": "1790000200.0",
                    "thread_ts": "1790000100.0001",
                    "text": "done",
                },
                {
                    "type": "message",
                    "subtype": "bot_message",
                    "bot_id": "B1",
                    "username": "CI",
                    "ts": "1790000300.0",
                    "text": "build failed",
                },
            ]
        )
    )
    messages = load_slack_export(tmp_path, roles={"Leo": "engineer"})
    assert [m.text for m in messages] == ["@Arjun Rao please revert the PR", "done", "build failed"]
    assert messages[0].sender_role == "engineer" and messages[0].channel == "#eng"
    assert messages[1].thread_id == "slack:eng:1790000100.0001"
    assert messages[2].is_automated and messages[2].sender == "CI"


def _slack_transport(
    pages: list[dict[str, Any]], rate_limited_once: bool = True
) -> httpx.MockTransport:
    state = {"limited": not rate_limited_once}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer xoxb-test"
        if request.url.path.endswith("users.list"):
            return httpx.Response(200, json={"ok": True, "members": [{"id": "U1", "name": "leo"}]})
        if not state["limited"]:
            state["limited"] = True
            return httpx.Response(429, headers={"Retry-After": "2"})
        cursor = request.url.params.get("cursor")
        return httpx.Response(200, json=pages[1] if cursor == "next" else pages[0])

    return httpx.MockTransport(handler)


def test_slack_client_paginates_and_honors_rate_limits() -> None:
    pages = [
        {
            "ok": True,
            "messages": [{"user": "U1", "ts": "1790000000.0", "text": "first"}],
            "response_metadata": {"next_cursor": "next"},
        },
        {"ok": True, "messages": [{"user": "U1", "ts": "1790000100.0", "text": "second"}]},
    ]
    slept: list[float] = []
    client = SlackClient(
        "xoxb-test",
        client=httpx.Client(base_url="https://slack.test/api", transport=_slack_transport(pages)),
        sleep=slept.append,
    )
    messages = client.channel_messages("C1", "eng")
    assert [m.text for m in messages] == ["first", "second"]
    assert slept == [2.0]


def test_slack_client_raises_on_api_errors() -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, json={"ok": False, "error": "not_authed"})
    )
    client = SlackClient(
        "xoxb-test", client=httpx.Client(base_url="https://slack.test/api", transport=transport)
    )
    with pytest.raises(RuntimeError, match="not_authed"):
        client.users()


def test_slack_user_directory_is_fetched_once_per_client() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("users.list"):
            return httpx.Response(200, json={"ok": True, "members": [{"id": "U1", "name": "leo"}]})
        return httpx.Response(200, json={"ok": True, "messages": []})

    client = SlackClient(
        "xoxb-test",
        client=httpx.Client(
            base_url="https://slack.test/api", transport=httpx.MockTransport(handler)
        ),
    )
    client.channel_messages("C1", "eng")
    client.channel_messages("C2", "ops")
    assert sum(path.endswith("users.list") for path in calls) == 1


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def _gmail(headers: dict[str, str], parts: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": "g1",
        "threadId": "t1",
        "payload": {
            "headers": [{"name": k, "value": v} for k, v in headers.items()],
            "mimeType": "multipart/alternative",
            "parts": parts,
        },
    }


def test_parses_gmail_messages_preferring_plain_text() -> None:
    raw = _gmail(
        {
            "From": "Omar Haddad <omar@acme.com>",
            "To": "Sofia <sofia@kestrel.io>, bob@kestrel.io",
            "Subject": "Renewal",
            "Date": "Mon, 21 Sep 2026 18:00:00 +0530",
        },
        [
            {"mimeType": "text/plain", "body": {"data": _b64("Could you countersign by Sept 30?")}},
            {"mimeType": "text/html", "body": {"data": _b64("<p>ignored</p>")}},
        ],
    )
    message = parse_gmail_message(raw, roles={"omar@acme.com": "customer"})
    assert (message.id, message.sender, message.sender_role) == (
        "gmail:g1",
        "Omar Haddad",
        "customer",
    )
    assert message.recipients == ("Sofia", "bob@kestrel.io")
    assert message.text == "Could you countersign by Sept 30?"
    assert message.thread_id == "gmail:t1" and not message.is_automated


def test_falls_back_to_html_body() -> None:
    raw = _gmail(
        {"From": "a@b.io", "Date": "Mon, 21 Sep 2026 18:00:00 +0000"},
        [{"mimeType": "text/html", "body": {"data": _b64("<div>Pay the invoice</div>")}}],
    )
    assert parse_gmail_message(raw).text == "Pay the invoice"


@pytest.mark.parametrize(
    ("headers", "automated"),
    [
        ({"List-Unsubscribe": "<mailto:x>"}, True),
        ({"Precedence": "bulk"}, True),
        ({"Auto-Submitted": "auto-generated"}, True),
        ({"From": "no-reply@github.com"}, True),
        ({"From": "Omar <omar@acme.com>", "Auto-Submitted": "no"}, False),
    ],
)
def test_detects_automated_mail(headers: dict[str, str], automated: bool) -> None:
    assert is_automated([{"name": k, "value": v} for k, v in headers.items()]) is automated


def test_fetch_messages_follows_page_tokens() -> None:
    raw = _gmail(
        {"From": "a@b.io", "Date": "Mon, 21 Sep 2026 18:00:00 +0000"},
        [{"mimeType": "text/plain", "body": {"data": _b64("hello")}}],
    )
    pages = iter([{"messages": [{"id": "1"}], "nextPageToken": "p2"}, {"messages": [{"id": "2"}]}])

    def execute(value: Any) -> Any:
        return SimpleNamespace(execute=lambda: value)

    messages_api = SimpleNamespace(
        list=lambda **_: execute(next(pages)), get=lambda **_: execute(raw)
    )
    service = SimpleNamespace(users=lambda: SimpleNamespace(messages=lambda: messages_api))
    assert len(fetch_messages(service, limit=5)) == 2


def test_naive_timestamps_are_treated_as_utc() -> None:
    from chief_of_staff.models import Message

    message = Message(
        id="x", source=Source.SLACK, sender="a", timestamp=datetime(2026, 9, 21), text="t"
    )
    assert message.timestamp.tzinfo is UTC
