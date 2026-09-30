"""Build the public demo: the bundled sample inbox, the digest the offline rules make from it,
the backend comparison and a copy of the pilot review page. Static and read-only.

    python docs/build_site.py [--out site]
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
from datetime import datetime
from html import escape
from pathlib import Path

from chief_of_staff.config import Settings
from chief_of_staff.evaluation.compare import comparison_table, load_report
from chief_of_staff.extraction.factory import build_prioritizer, build_service
from chief_of_staff.ingest.files import load_messages
from chief_of_staff.models import ActionItem, Digest, Message, Source
from chief_of_staff.pilot import PilotRun, review_page
from chief_of_staff.pipeline import Pipeline

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "datasets" / "samples"
REPO = "https://github.com/pavan-dangeti/Chief-of-Staff-AI"
AS_OF = datetime.fromisoformat("2026-09-22T18:00:00+05:30")
BACKENDS = ["heuristic", "glm-5.3-flash", "gemini", "deepseek-v4.1-flash", "nemotron-3-super"]


def inbox() -> list[Message]:
    slack = load_messages(SAMPLES / "slack.json", source=Source.SLACK)
    return slack + load_messages(SAMPLES / "email.json", source=Source.EMAIL)


def digest_of(messages: list[Message]) -> Digest:
    settings = Settings(backend="heuristic", cache_enabled=False, trace_path=None, _env_file=None)
    service = build_service(settings)
    try:
        pipeline = Pipeline(service, build_prioritizer(settings))
        return asyncio.run(pipeline.run(messages, as_of=AS_OF))
    finally:
        service.close()


def _when(value: datetime) -> str:
    return value.astimezone(AS_OF.tzinfo).strftime("%a %d %b, %H:%M")


def _item(item: ActionItem) -> str:
    priority = item.priority.value if item.priority else "-"
    due = item.due_date.strftime("%a %d %b") if item.due_date else "no due date"
    flags = ""
    if item.due_date is not None and item.due_date < AS_OF.date():
        flags += ' <span class="flag late">overdue</span>'
    if item.needs_review:
        flags += ' <span class="flag">needs review</span>'
    where = f" in {escape(item.channel)}" if item.channel else ""
    reasons = "".join(f"<li>{escape(reason)}</li>" for reason in item.reasons)
    return f"""
<article class="item">
  <p class="head"><span class="badge {escape(priority)}">{escape(priority)}</span>
    <strong>{escape(item.action)}</strong></p>
  <p class="meta">Owner: {escape(item.owner or "unassigned")} · Due: {escape(due)}{flags}</p>
  <blockquote>{escape(item.evidence)}</blockquote>
  <p class="meta">From <a href="#{escape(item.message_id)}">{escape(item.sender)}{where}</a></p>
  <details><summary>Why this priority</summary><ul>{reasons}</ul></details>
</article>"""


def _message(message: Message, outcome: str) -> str:
    return f"""
<article class="msg" id="{escape(message.id)}">
  <p class="meta"><strong>{escape(message.sender)}</strong> · {escape(message.channel or "")}
    · {escape(_when(message.timestamp))}</p>
  <p>{escape(message.text)}</p>
  <p class="outcome">{escape(outcome)}</p>
</article>"""


def _outcomes(digest: Digest) -> dict[str, str]:
    """What happened to each message, in words; one message can lead to several outcomes."""
    notes: dict[str, list[str]] = {}

    def note(message_id: str, text: str) -> None:
        notes.setdefault(message_id, []).append(text)

    for item in digest.open_items:
        note(item.message_id, f"open item, {item.priority.value if item.priority else ''}")
    for item in [*digest.open_items, *digest.resolved_items]:
        for related in item.related_message_ids:
            if related != item.message_id:
                note(related, "same task as another message, merged into one item")
    for item in digest.resolved_items:
        note(item.message_id, "item, closed by a later message")
        if item.resolved_by:
            note(item.resolved_by, "reports work done, closing an earlier item")
    for completion in digest.unmatched_completions:
        note(completion.message_id, "reports work done")
    for skipped in digest.skipped:
        reason = skipped.reason.replace("_", " ")
        note(skipped.message_id, f"skipped without a model call: {reason}")
    return {message_id: "→ " + "; ".join(texts) for message_id, texts in notes.items()}


def _markdown_table(markdown: str) -> str:
    rows = [line.strip("|").split("|") for line in markdown.strip().splitlines()]

    def cell(text: str) -> str:
        return escape(text.strip().replace("**", "").replace("`", ""))

    head = "".join(f'<th scope="col">{cell(c)}</th>' for c in rows[0])
    body = "".join("<tr>" + "".join(f"<td>{cell(c)}</td>" for c in r) + "</tr>" for r in rows[2:])
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def page(messages: list[Message], digest: Digest, table: str, commit: str) -> str:
    outcomes = _outcomes(digest)
    stats = digest.stats
    summary = (
        f"{stats.messages_total} messages · {stats.messages_skipped} skipped before any model call "
        f"· {len(digest.open_items)} open items · duplicates merged: {stats.duplicates_merged} "
        f"· closed by a later message: {stats.completions_matched}"
    )
    fills = {
        "INBOX": "".join(
            _message(m, outcomes.get(m.id, "no action item"))
            for m in sorted(messages, key=lambda m: m.timestamp)
        ),
        "OPEN": "".join(_item(i) for i in digest.open_items),
        "DONE": "".join(_item(i) for i in digest.resolved_items) or '<p class="meta">None.</p>',
        "TABLE": table,
        "REPO": REPO,
        "COMMIT": escape(commit),
        "SUMMARY": escape(summary),
        "AS_OF": escape(AS_OF.strftime("%A %d %B %Y, %H:%M IST")),
    }
    html = (ROOT / "docs" / "site.html").read_text(encoding="utf-8")
    for key, value in fills.items():
        html = html.replace("{{" + key + "}}", value)
    return html


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "site")
    out: Path = parser.parse_args().out
    commit = (
        os.environ.get("GITHUB_SHA")
        or subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
        ).stdout.strip()
    )
    messages = inbox()
    digest = digest_of(messages)
    reports = ROOT / "reports"
    runs = [
        (load_report(reports / f"{tag}-test.json"), load_report(reports / f"{tag}-injection.json"))
        for tag in BACKENDS
    ]
    out.mkdir(parents=True, exist_ok=True)
    table = _markdown_table(comparison_table(runs))
    (out / "index.html").write_text(page(messages, digest, table, commit[:7]), encoding="utf-8")
    run = PilotRun(
        participant="DEMO",
        run_id="sample",
        backend="heuristic:rules-v2",
        window_days=14,
        messages_scanned=len(messages),
        messages_extracted=digest.stats.messages_total - digest.stats.messages_skipped,
    )
    (out / "review.html").write_text(review_page(digest, run), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    print(f"wrote {out / 'index.html'} and {out / 'review.html'}")


if __name__ == "__main__":
    main()
