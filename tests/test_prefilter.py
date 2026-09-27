from __future__ import annotations

import pytest

from chief_of_staff.prefilter import skip_reason
from helpers import dataset_examples, make_message


@pytest.mark.parametrize(
    ("text", "automated", "reason"),
    [
        ("   ", False, "empty"),
        ("Arun has joined the channel", False, "system_event"),
        ("thanks!", False, "chatter"),
        ("lol", False, "chatter"),
        ("+1", False, "chatter"),
        ("Top 10 growth hacks. Read our newsletter.", True, "automated_no_action"),
        ("Big savings: 30% off everything. Unsubscribe here.", False, "automated_no_action"),
    ],
)
def test_skips_obvious_noise(text: str, automated: bool, reason: str) -> None:
    assert skip_reason(make_message(text, automated=automated)) == reason


@pytest.mark.parametrize(
    ("text", "automated"),
    [
        ("Please verify your email within 48 hours.", True),
        ("Your credits expire on 30 September. Unsubscribe from marketing email.", True),
        ("@Kiran can you review the PR?", False),
        ("that demo was hilarious haha", False),
    ],
)
def test_keeps_anything_that_might_be_actionable(text: str, automated: bool) -> None:
    assert skip_reason(make_message(text, automated=automated)) is None


def test_marketing_with_a_deadline_is_kept_because_recall_beats_cost() -> None:
    message = make_message("Sale ends this week, 30% off. Unsubscribe here.", automated=True)
    assert skip_reason(message) is None


def test_never_skips_a_labeled_action_item() -> None:
    lost = [e.id for e in dataset_examples() if e.expected and skip_reason(e.message) is not None]
    assert lost == []
