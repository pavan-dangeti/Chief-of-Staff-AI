from __future__ import annotations

import json
import mailbox
import re
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from chief_of_staff.cli import app
from chief_of_staff.config import Settings
from chief_of_staff.extraction.factory import build_service
from chief_of_staff.ingest.files import load_messages
from chief_of_staff.ingest.mbox import load_mbox
from chief_of_staff.models import Digest, Message, Source
from chief_of_staff.pilot import (
    PilotExport,
    PilotItem,
    PilotRun,
    load_exports,
    pilot_report,
    review_page,
    wilson,
)
from chief_of_staff.pipeline import Pipeline
from helpers import ROOT, make_message

SAMPLES = ROOT / "datasets" / "samples"
NOW = datetime(2026, 9, 21, 10, 0, tzinfo=UTC)


def _mail(box: mailbox.mbox, sent: datetime | None, body: str, **headers: str) -> None:
    message = EmailMessage()
    message["From"] = "Ritu Shah <ritu@example.com>"
    message["To"] = "Pavan <pavan@example.com>, sam@example.com"
    message["Subject"] = headers.pop("Subject", "Invoice")
    if sent is not None:
        message["Date"] = sent.strftime("%a, %d %b %Y %H:%M:%S +0000")
    for name, value in headers.items():
        message[name.replace("_", "-")] = value
    message.set_content(body, subtype="html" if body.startswith("<") else "plain")
    box.add(message)


def test_mbox_import_cleans_bodies_flags_bulk_mail_and_applies_the_window(tmp_path: Path) -> None:
    path = tmp_path / "all.mbox"
    box = mailbox.mbox(path)
    _mail(box, NOW, "Pavan, please approve the invoice by Friday.\n\nOn Mon, Sam wrote:\n> old ask")
    _mail(box, NOW + timedelta(hours=1), "<p>Can you <b>review</b> the SOW?</p>", Subject="SOW")
    _mail(box, NOW, "Our spring sale starts now.", List_Unsubscribe="<mailto:x@example.com>")
    _mail(box, NOW - timedelta(days=30), "An old request outside the window.")
    _mail(box, None, "No date header, so it cannot be placed in the window.")
    box.close()

    messages = load_mbox(path, since=NOW - timedelta(days=14))
    assert [m.channel for m in messages] == ["Invoice", "Invoice", "SOW"]
    first = next(m for m in messages if not m.is_automated)
    assert first.source is Source.EMAIL and first.sender == "Ritu Shah"
    assert first.text == "Pavan, please approve the invoice by Friday."  # quoted reply removed
    assert first.recipients == ("Pavan", "sam@example.com")
    assert sum(m.is_automated for m in messages) == 1
    assert messages[-1].text == "Can you review the SOW?"
    assert len(load_mbox(path)) == 4  # no window: only the undated mail is skipped


async def _digest(messages: list[Message]) -> tuple[Digest, PilotRun]:
    settings = Settings(backend="heuristic", cache_enabled=False, trace_path=None, _env_file=None)
    digest = await Pipeline(build_service(settings)).run(messages)
    run = PilotRun(
        participant="P1",
        run_id="r1",
        backend="heuristic:rules-v2",
        window_days=14,
        messages_scanned=len(messages),
        messages_extracted=len(messages),
    )
    return digest, run


def _page_data(page: str) -> dict[str, Any]:
    block = re.search(r'<script type="application/json" id="pilot-data">(.*?)</script>', page, re.S)
    assert block is not None
    data: dict[str, Any] = json.loads(block.group(1))
    return data


async def test_review_page_keeps_text_out_of_the_export_record_and_script_safe() -> None:
    hostile = make_message(
        "Leo, please send the </script><script>alert(1)</script> deck by Friday."
    )
    messages = [*load_messages(SAMPLES / "email.json", source=Source.EMAIL), hostile]
    digest, run = await _digest(messages)
    page = review_page(digest, run)
    assert page.count("</script>") == 2  # the data block and the app script; nothing injected
    data = _page_data(page)
    assert data["run"]["participant"] == "P1" and data["items"]
    words = {word for m in messages for word in m.text.split() if len(word) > 6}
    for entry in data["items"]:
        record = entry["export"]
        assert set(record) == set(PilotItem.model_fields)
        assert entry["display"]["evidence"]  # shown to the participant, on their machine only
        assert not any(word in json.dumps(record) for word in words)


def _export(data: dict[str, Any], labels: list[str | None], **extra: Any) -> dict[str, Any]:
    """What the page's Save button builds (see pilot_review.html)."""
    items = [
        {**entry["export"], "label": label}
        for entry, label in zip(data["items"], labels, strict=True)
    ]
    return {**data["run"], "exported_on": "2026-09-30", "items": items, "missed": [], **extra}


async def test_exports_validate_strictly_and_reject_anything_extra() -> None:
    digest, run = await _digest(load_messages(SAMPLES / "email.json", source=Source.EMAIL))
    data = _page_data(review_page(digest, run))
    labels: list[str | None] = ["correct"] * len(data["items"])
    missed = [{"kind": "request", "source": "email"}]
    PilotExport.model_validate(_export(data, labels, missed=missed))
    with pytest.raises(ValidationError):
        PilotExport.model_validate(_export(data, labels, note="my private note"))
    with pytest.raises(ValidationError):
        PilotExport.model_validate(_export(data, labels, missed=[{**missed[0], "note": "x"}]))
    leaked = _export(data, labels)
    leaked["items"][0]["evidence"] = "Please approve the invoice"
    with pytest.raises(ValidationError):
        PilotExport.model_validate(leaked)
    with pytest.raises(ValidationError):
        PilotExport.model_validate({**_export(data, labels), "participant": "Pavan Dangeti"})


def test_wilson_interval_matches_known_values() -> None:
    interval = wilson(8, 10)
    assert interval is not None
    assert (round(interval[0], 3), round(interval[1], 3)) == (0.49, 0.943)
    assert wilson(0, 0) is None
    full = wilson(10, 10)
    assert full is not None and full[1] == 1.0


def _write(tmp_path: Path, name: str, export: dict[str, Any]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(export), encoding="utf-8")
    return path


def _synthetic(
    participant: str, run_id: str, labels: list[str | None], missed: int, day: str
) -> dict[str, Any]:
    item = {
        "kind": "request",
        "source": "email",
        "has_owner": True,
        "has_due_date": False,
        "priority": "P2",
        "confidence": 0.8,
        "needs_review": False,
    }
    return {
        "format": 1,
        "participant": participant,
        "run_id": run_id,
        "tool_version": "2.0.2",
        "prompt_version": "2.1.0",
        "backend": "heuristic:rules-v2",
        "window_days": 14,
        "messages_scanned": 50,
        "messages_extracted": 30,
        "exported_on": day,
        "items": [{**item, "item": f"{run_id}-{n}", "label": lab} for n, lab in enumerate(labels)],
        "missed": [{"kind": "request", "source": "email"}] * missed,
    }


def test_report_pools_participants_keeps_the_latest_export_and_estimates_recall(
    tmp_path: Path,
) -> None:
    six_right = ["correct"] * 6 + ["not_a_task"] * 2
    files = [
        _write(tmp_path, "a-old.json", _synthetic("P1", "r1", ["correct"] * 2, 0, "2026-09-20")),
        _write(tmp_path, "a.json", _synthetic("P1", "r1", six_right, 2, "2026-09-28")),
        _write(
            tmp_path,
            "b.json",
            _synthetic("P2", "r9", ["wrong_details", "correct", None], 1, "2026-09-29"),
        ),
    ]
    exports = load_exports(files)
    assert sorted((e.participant, len(e.items)) for e in exports) == [("P1", 8), ("P2", 3)]
    report = pilot_report(exports)
    rows = {line.split(" | ")[0]: line for line in report.splitlines() if line.startswith("| ")}
    assert "| 8 of 8 | 0.75 (" in rows["| P1"]  # 6 real tasks out of 8 reviewed
    assert "| 2 of 3 | 1.00 (" in rows["| P2"]  # the unreviewed item is left out
    total = rows["| **All**"]
    assert "10 of 11" in total and "| 3 |" in total  # 3 missed tasks added in all
    assert total.endswith("| 0.73 (0.43–0.90) |")  # recall estimate: 8 real of 8 + 3 missed
    assert "upper bound" in report


def test_pilot_cli_writes_a_review_page_and_a_report(tmp_path: Path) -> None:
    runner = CliRunner()
    out = tmp_path / "pilot"
    args = ["pilot", "run", "--participant", "P7", "--email", str(SAMPLES / "email.json")]
    result = runner.invoke(app, [*args, "--days", "100000", "--out", str(out)])
    assert result.exit_code == 0, result.output
    page = next(out.glob("review-P7-*.html"))
    data = _page_data(page.read_text(encoding="utf-8"))
    assert data["run"]["backend"] == "heuristic:rules-v2" and data["items"]

    export = _write(tmp_path, "p7.json", _export(data, ["correct"] * len(data["items"])))
    report = runner.invoke(app, ["pilot", "report", str(export), "--output", str(tmp_path / "r")])
    assert report.exit_code == 0 and "| P7 | 1 |" in (tmp_path / "r").read_text()

    bad = _write(tmp_path, "bad.json", {"participant": "P7"})
    assert runner.invoke(app, ["pilot", "report", str(bad)]).exit_code == 1
    empty = runner.invoke(app, [*args, "--days", "1"])
    assert empty.exit_code != 0 and "no messages from the last 1 days" in empty.output


def test_cos_run_reads_an_mbox(tmp_path: Path) -> None:
    path = tmp_path / "in.mbox"
    box = mailbox.mbox(path)
    _mail(box, NOW, "Pavan, please approve the invoice by Friday.")
    box.close()
    args = ["run", "--mbox", str(path), "--backend", "heuristic", "--format", "json"]
    result = CliRunner().invoke(app, [*args, "--as-of", "2026-09-21T12:00:00"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["open_items"][0]["owner"] == "Pavan"


def test_mbox_survives_unknown_charsets_and_mail_without_a_text_body(tmp_path: Path) -> None:
    path = tmp_path / "odd.mbox"
    box = mailbox.mbox(path)
    box.add(
        "From: Ops <ops@example.com>\nDate: Mon, 21 Sep 2026 10:00:00 +0000\nSubject: Rota\n"
        "Content-Type: text/plain; charset=x-unknown-charset\n\nPlease cover Friday's on-call.\n"
    )
    attachment_only = EmailMessage()
    attachment_only["From"] = "Scanner <scan@example.com>"
    attachment_only["Date"] = "Mon, 21 Sep 2026 11:00:00 +0000"
    attachment_only.add_attachment(b"%PDF-1.4", maintype="application", subtype="pdf")
    box.add(attachment_only)
    box.close()
    messages = load_mbox(path)
    assert [m.text for m in messages] == ["Please cover Friday's on-call."]
