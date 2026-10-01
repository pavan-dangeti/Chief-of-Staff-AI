from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta

import pytest

from chief_of_staff.ledger import Ledger
from chief_of_staff.models import Digest, RunStats, Status
from helpers import MONDAY, make_action_item


@pytest.fixture
def ledger() -> Iterator[Ledger]:
    with Ledger(":memory:") as store:
        yield store


def digest(open_items: list = (), resolved: list = (), completions: list = ()) -> Digest:  # type: ignore[assignment,type-arg]
    return Digest(
        as_of=MONDAY,
        open_items=list(open_items),
        resolved_items=list(resolved),
        unmatched_completions=list(completions),
        skipped=[],
        stats=RunStats(),
    )


def test_sync_is_idempotent_for_the_same_messages(ledger: Ledger) -> None:
    task = make_action_item("Pay the Brightline invoice", id="a:0", due="2026-09-18")
    assert ledger.sync(digest([task])).added == 1
    again = ledger.sync(digest([task]))
    assert (again.added, again.updated) == (0, 1)
    assert len(ledger.items()) == 1


def test_rephrased_duplicate_links_to_the_open_item(ledger: Ledger) -> None:
    ledger.sync(digest([make_action_item("Send the board deck", id="a:0", owner=None)]))
    ledger.sync(digest([make_action_item("Send the board deck to members", id="b:0", owner=None)]))
    [item] = ledger.items()
    assert item.related_message_ids == ["b"]


def test_completion_in_a_later_run_closes_the_item(ledger: Ledger) -> None:
    ledger.sync(digest([make_action_item("Pay the Brightline Q3 invoice", id="a:0")]))
    later = MONDAY + timedelta(days=1)
    done = make_action_item(
        "I've paid the Q3 invoice from Brightline", id="b:0", kind="completion", when=later
    )
    assert ledger.sync(digest(completions=[done])).closed == 1
    assert ledger.items(Status.OPEN) == []
    assert ledger.items(Status.DONE)[0].resolved_by == "b"


def test_resolved_items_close_their_open_counterpart(ledger: Ledger) -> None:
    task = make_action_item("Revert the hotfix", id="a:0")
    ledger.sync(digest([task]))
    result = ledger.sync(digest(resolved=[task.model_copy(update={"status": Status.DONE})]))
    assert result.closed == 1


def test_overdue_and_persistence(tmp_path: object) -> None:
    path = tmp_path / "ledger.sqlite"  # type: ignore[operator]
    ledger = Ledger(path)
    ledger.sync(
        digest(
            [
                make_action_item("Ship it", id="a:0", due="2026-09-15"),
                make_action_item("Plan offsite", id="b:0", due="2026-10-15"),
            ]
        )
    )
    ledger.close()
    with Ledger(path) as reopened:
        assert [i.id for i in reopened.overdue(date(2026, 9, 20))] == ["a:0"]


def test_resyncing_a_digest_with_an_open_item_and_its_done_duplicate_adds_nothing(
    ledger: Ledger,
) -> None:
    """Found by the 10,000-message scale run: the second sync used to add the done copy."""
    asked = make_action_item("Send the board deck", id="a:0", message_id="a", owner=None)
    done = make_action_item(
        "Send the board deck to members", id="b:0", message_id="b", owner=None
    ).model_copy(update={"status": Status.DONE})
    same = digest([asked], resolved=[done])
    first = ledger.sync(same)
    assert (first.added, first.updated) == (1, 1)
    again = ledger.sync(same)
    assert (again.added, again.updated) == (0, 2)
    assert len(ledger.items()) == 1
