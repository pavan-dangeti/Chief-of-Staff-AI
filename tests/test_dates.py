from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from chief_of_staff.dates import find_deadline_phrase, resolve_deadline
from helpers import IST, MONDAY

WEDNESDAY = MONDAY + timedelta(days=2)
FRIDAY = MONDAY + timedelta(days=4)


@pytest.mark.parametrize(
    ("phrase", "reference", "expected"),
    [
        ("by friday", MONDAY, "2026-09-18"),
        ("by Fri", MONDAY, "2026-09-18"),
        ("by friday", FRIDAY, "2026-09-18"),
        ("monday", WEDNESDAY, "2026-09-21"),
        ("next friday", MONDAY, "2026-09-25"),
        ("next monday", FRIDAY, "2026-09-21"),
        ("tomorrow", MONDAY, "2026-09-15"),
        ("day after tomorrow", MONDAY, "2026-09-16"),
        ("EOD", MONDAY, "2026-09-14"),
        ("tonight", MONDAY, "2026-09-14"),
        ("end of week", MONDAY, "2026-09-18"),
        ("this week", MONDAY, "2026-09-18"),
        ("next week", MONDAY, "2026-09-25"),
        ("early next week", WEDNESDAY, "2026-09-21"),
        ("before next week", MONDAY, "2026-09-18"),
        ("within 48 hours", WEDNESDAY, "2026-09-18"),
        ("in 2 hours", MONDAY, "2026-09-14"),
        ("in a few days", MONDAY, "2026-09-17"),
        ("in two weeks", MONDAY, "2026-09-28"),
        ("within 2 business days", FRIDAY, "2026-09-22"),
        ("24 hours before the friday 2pm meeting", MONDAY, "2026-09-17"),
        ("48 hours in advance of next Tuesday", WEDNESDAY, "2026-09-20"),
        ("2026-10-05", MONDAY, "2026-10-05"),
        ("Sept 30th", MONDAY, "2026-09-30"),
        ("3rd of October", MONDAY, "2026-10-03"),
        ("30/09", MONDAY, "2026-09-30"),
        ("09/30", MONDAY, "2026-09-30"),
        ("by the 20th", MONDAY, "2026-09-20"),
        ("by the 3rd", MONDAY, "2026-10-03"),
        ("by 5pm", MONDAY, "2026-09-14"),
        ("end of month", MONDAY, "2026-09-30"),
        ("end of next month", MONDAY, "2026-10-31"),
        ("end of quarter", MONDAY, "2026-09-30"),
        ("end of year", MONDAY, "2026-12-31"),
        ("over the weekend", MONDAY, "2026-09-20"),
        ("kal tak", MONDAY, "2026-09-15"),
        ("aaj", MONDAY, "2026-09-14"),
    ],
)
def test_resolves_common_deadline_phrases(phrase: str, reference: datetime, expected: str) -> None:
    assert resolve_deadline(phrase, reference) == date.fromisoformat(expected)


@pytest.mark.parametrize("phrase", [None, "", "next sprint", "sometime soon", "asap", "31/02"])
def test_unresolvable_phrases_return_none(phrase: str | None) -> None:
    assert resolve_deadline(phrase, MONDAY) is None


def test_numeric_dates_respect_configured_order() -> None:
    assert resolve_deadline("03/04", MONDAY, date_order="DMY") == date(2027, 4, 3)
    assert resolve_deadline("03/04", MONDAY, date_order="MDY") == date(2027, 3, 4)


def test_month_without_year_rolls_forward_only_when_long_past() -> None:
    assert resolve_deadline("Jan 5", MONDAY) == date(2027, 1, 5)
    assert resolve_deadline("Sept 1", MONDAY) == date(2026, 9, 1)


def test_uses_senders_local_date_not_utc() -> None:
    late_evening_ist = datetime(2026, 9, 14, 23, 30, tzinfo=IST)
    assert resolve_deadline("tomorrow", late_evening_ist) == date(2026, 9, 15)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("need someone to look at this before we push to prod tomorrow.", "tomorrow"),
        ("please send it by sat", "by sat"),
        ("we sat down and talked it through", None),
        ("pay the invoice by 30/09 pls", "by 30/09"),
        ("24/7 support is included", None),
        ("I saw this morning that the build broke", None),
        ("ship it by friday, not monday", "by friday"),
    ],
)
def test_find_deadline_phrase_requires_cues_for_ambiguous_tokens(
    text: str, expected: str | None
) -> None:
    assert find_deadline_phrase(text) == expected


@given(
    weekday=st.sampled_from(["monday", "tuesday", "wednesday", "thursday", "friday"]),
    offset=st.integers(min_value=0, max_value=365),
)
def test_weekday_rules_land_in_the_expected_window(weekday: str, offset: int) -> None:
    reference = MONDAY + timedelta(days=offset)
    plain = resolve_deadline(weekday, reference)
    following = resolve_deadline(f"next {weekday}", reference)
    assert plain is not None and following is not None
    assert 0 <= (plain - reference.date()).days <= 6
    assert 1 <= (following - reference.date()).days <= 13
    assert plain.strftime("%A").lower() == following.strftime("%A").lower() == weekday


@given(days=st.integers(min_value=1, max_value=60), offset=st.integers(min_value=0, max_value=365))
def test_relative_day_offsets_are_exact(days: int, offset: int) -> None:
    reference = MONDAY + timedelta(days=offset)
    assert resolve_deadline(f"in {days} days", reference) == reference.date() + timedelta(days=days)
