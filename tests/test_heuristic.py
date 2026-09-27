from __future__ import annotations

from datetime import date

import pytest

from chief_of_staff.dates import resolve_deadline
from chief_of_staff.extraction.heuristic import HeuristicExtractor
from chief_of_staff.extraction.verify import is_grounded
from chief_of_staff.models import ExtractedItem, ItemKind, Source
from helpers import MONDAY, dataset_examples, make_message

extractor = HeuristicExtractor()


def extract(text: str, **kwargs: object) -> list[ExtractedItem]:
    message = make_message(text, **kwargs)  # type: ignore[arg-type]
    return extractor.extract_items(message, message.text)


@pytest.mark.parametrize(
    ("text", "kind", "owner", "deadline"),
    [
        (
            "@Kiran can you bump the redis client before tomorrow's release?",
            "request",
            "Kiran",
            "before tomorrow",
        ),
        (
            "Farhan, please renew the domain before it lapses on the 20th.",
            "request",
            "Farhan",
            "on the 20th",
        ),
        ("I'll fix the flaky checkout test tonight", "commitment", "Sam", "tonight"),
        ("Arun will own the Kafka upgrade next sprint.", "commitment", "Arun", None),
        ("rolling back the deploy now", "commitment", "Sam", None),
        ("Bumped the redis client to 5.0.3 and redeployed staging.", "completion", "Sam", None),
        (
            "shipped the retry middleware, thanks for the quick review Maya",
            "completion",
            "Sam",
            None,
        ),
        ("We'll need to rotate the Stripe keys before Friday.", "request", None, "before Friday"),
        ("Riya, Karan, can one of you run the survey analysis?", "request", None, None),
        ("bhai @Maya kal tak staging ka DB backup le lena", "request", "Maya", "kal tak"),
    ],
)
def test_single_item_messages(
    text: str, kind: str, owner: str | None, deadline: str | None
) -> None:
    items = extract(text, sender="Sam")
    assert len(items) == 1
    assert items[0].kind is ItemKind(kind)
    assert items[0].owner == owner
    assert items[0].deadline_text == deadline


@pytest.mark.parametrize(
    "text",
    [
        "No need to update the deck, Sam already did.",
        "would be nice to redo the onboarding flow someday",
        "anyone want to grab lunch at the dosa place?",
        "does anyone know where the deploy docs live now?",
        "great work on the launch everyone",
        "Please find the invoice attached.",
        "Office will be closed on Thursday for the holiday.",
        "never mind on the mocks, Riya already shared them",
    ],
)
def test_hard_negatives_yield_nothing(text: str) -> None:
    assert extract(text) == []


def test_multiple_owners_in_one_message() -> None:
    items = extract("Sam, can you write the postmortem by Thursday? Arun, please add a 5xx alert.")
    assert [(i.owner, i.deadline_text) for i in items] == [("Sam", "by Thursday"), ("Arun", None)]


def test_single_recipient_email_inherits_owner() -> None:
    items = extract(
        "Our invoice is 15 days overdue. Please arrange payment by Friday.",
        source=Source.EMAIL,
        recipients=("Farhan",),
    )
    assert items[0].owner == "Farhan"


def test_pronoun_reference_pulls_in_previous_sentence() -> None:
    items = extract("found a memory leak in the worker. need someone to look at this before prod.")
    assert "(re: Found a memory leak" in items[0].action
    assert items[0].evidence.startswith("found a memory leak")


def test_dangling_offset_is_anchored_to_a_date_elsewhere_in_the_message() -> None:
    items = extract(
        "Priya, the board meeting is Friday at 2pm. We will need the deck 24 hours before "
        "so members can review."
    )
    assert resolve_deadline(items[0].deadline_text, MONDAY) == date(2026, 9, 17)


def test_automated_mail_yields_one_imperative_item() -> None:
    items = extract(
        "Your credits expire on 30 September. Redeem them from the console to keep your balance.",
        automated=True,
    )
    assert len(items) == 1
    assert items[0].action.startswith("Redeem")
    assert resolve_deadline(items[0].deadline_text, MONDAY) == date(2026, 9, 30)


async def test_async_interface_reports_backend() -> None:
    message = make_message("Sam, please ship it")
    raw = await extractor.extract(message, message.text)
    assert (raw.backend, raw.model, len(raw.items)) == ("heuristic", "rules-v2", 1)


def test_every_heuristic_quote_is_grounded_across_all_datasets() -> None:
    for example in dataset_examples():
        for extracted in extractor.extract_items(example.message, example.message.text):
            assert is_grounded(extracted.evidence, example.message.text), example.id
