from __future__ import annotations

from datetime import timedelta

from chief_of_staff.lifecycle import apply_completions, deduplicate, is_duplicate
from chief_of_staff.models import Priority, Status
from chief_of_staff.prioritization import Prioritizer
from helpers import MONDAY, make_action_item

LATER = MONDAY + timedelta(hours=2)


def test_same_task_across_slack_and_email_is_a_duplicate() -> None:
    slack = make_action_item(
        "can someone put together the board deck by friday?",
        id="s:0",
        action="Put together the board deck by friday",
        owner=None,
        due="2026-09-18",
    )
    email = make_action_item(
        "We will need the board deck 24 hours before",
        id="e:0",
        action="Need the board deck 24 hours before",
        owner=None,
        due="2026-09-17",
    )
    assert is_duplicate(slack, email)


def test_duplicates_require_compatible_owner_due_and_distinct_messages() -> None:
    base = make_action_item("Review the Acme contract", id="a:0", owner="Sam", due="2026-09-18")
    assert not is_duplicate(
        base, make_action_item("Review the Acme contract", id="b:0", owner="Arun")
    )
    assert not is_duplicate(
        base, make_action_item("Review the Acme contract", id="b:0", due="2026-09-30")
    )
    assert not is_duplicate(base, make_action_item("Review the Acme contract", id="a:1"))


def test_completion_in_same_thread_closes_the_task() -> None:
    task = make_action_item(
        "someone should revert the hotfix if checkout breaks", id="t:0", thread="th"
    )
    done = make_action_item(
        "I reverted Arjun's hotfix, payments are healthy",
        id="c:0",
        kind="completion",
        when=LATER,
        thread="th",
    )
    tasks, unmatched, matched = apply_completions([task, done])
    assert (matched, unmatched) == (1, [])
    assert tasks[0].status is Status.DONE and tasks[0].resolved_by == "c"


def test_completion_cannot_close_a_later_task() -> None:
    done = make_action_item("I reverted the hotfix", id="c:0", kind="completion")
    task = make_action_item("please revert the hotfix", id="t:0", when=LATER)
    tasks, unmatched, matched = apply_completions([done, task])
    assert matched == 0 and tasks[0].status is Status.OPEN and len(unmatched) == 1


def test_unrelated_completion_stays_unmatched() -> None:
    task = make_action_item("Review the Acme security questionnaire", id="t:0")
    done = make_action_item("Paid the Brightline invoice", id="c:0", kind="completion", when=LATER)
    _, unmatched, matched = apply_completions([task, done])
    assert matched == 0 and [u.id for u in unmatched] == ["c:0"]


def test_deduplicate_keeps_best_representative_and_merges_fields() -> None:
    ranker = Prioritizer()
    low = ranker.score(
        make_action_item(
            "Send the board deck", id="a:0", owner=None, role="internal", due="2026-09-18"
        ),
        MONDAY.date(),
    )
    high = ranker.score(
        make_action_item(
            "Send the board deck", id="b:0", owner="Priya", role="ceo", due="2026-09-17"
        ),
        MONDAY.date(),
    )
    merged, count = deduplicate([low, high])
    assert count == 1 and len(merged) == 1
    assert merged[0].id == "b:0"
    assert merged[0].related_message_ids == ["a"]
    assert str(merged[0].due_date) == "2026-09-17"
    assert merged[0].priority in {Priority.P1, Priority.P2}


def test_open_and_done_items_are_never_merged() -> None:
    open_item = make_action_item("Send the board deck", id="a:0")
    done_item = make_action_item("Send the board deck", id="b:0").model_copy(
        update={"status": Status.DONE}
    )
    merged, count = deduplicate([open_item, done_item])
    assert count == 0 and len(merged) == 2
