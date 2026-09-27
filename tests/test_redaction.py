from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from chief_of_staff.redaction import NoopRedactor, Redactor


@pytest.mark.parametrize(
    ("secret", "label"),
    [
        ("priya@acme.io", "EMAIL"),
        ("+91 98765 43210", "PHONE"),
        ("(415) 555-0132", "PHONE"),
        ("9876543210", "PHONE"),
        ("4111 1111 1111 1111", "CARD"),
        ("123-45-6789", "GOVID"),
        ("ABCDE1234F", "GOVID"),
        ("2345 6789 0123", "GOVID"),
        ("sk-ant-abcdefghijklmnopqrstu", "SECRET"),
        ("AKIAABCDEFGHIJKLMNOP", "SECRET"),
        ("https://example.com/verify?token=abc123", "URL"),
    ],
)
def test_redacts_and_restores_each_category(secret: str, label: str) -> None:
    original = f"context before {secret} and after."
    redacted = Redactor().redact(original)
    assert secret not in redacted.text
    assert f"[{label}_1]" in redacted.text
    assert redacted.restore(redacted.text) == original


def test_one_time_codes_keep_their_label() -> None:
    redacted = Redactor().redact("Your code is 482913, it expires soon")
    assert redacted.text == "Your code is [CODE_1], it expires soon"


def test_url_excludes_trailing_punctuation() -> None:
    redacted = Redactor().redact("See https://x.com/a?token=zzz.")
    assert redacted.text == "See [URL_1]."


def test_business_numbers_are_left_alone() -> None:
    text = (
        "Meet at 10:30, budget 25000, raise 1,50,000, invoice INV-2026-0042, due 2026-09-30, "
        "v2.3.1 shipped, 24/7 support, ref 1234 5678 9012 3456."
    )
    assert Redactor().redact(text).text == text


def test_repeated_values_share_one_placeholder() -> None:
    redacted = Redactor().redact("cc priya@acme.io, then mail priya@acme.io again")
    assert redacted.text.count("[EMAIL_1]") == 2
    assert redacted.mapping == {"[EMAIL_1]": "priya@acme.io"}


def test_noop_redactor_is_identity() -> None:
    redacted = NoopRedactor().redact("mail priya@acme.io")
    assert redacted.text == "mail priya@acme.io"
    assert redacted.restore(None) is None


_TOKENS = st.sampled_from(
    [
        "please",
        "send",
        "the",
        "deck",
        "by",
        "friday",
        "priya@acme.io",
        "ravi@x.org",
        "+91 98765 43210",
        "4111 1111 1111 1111",
        "https://a.io/x?y=1",
        "code 123456",
        "2026-09-30",
        "25000",
        "#eng",
        "@Sam",
    ]
)


@given(st.lists(_TOKENS, min_size=1, max_size=25))
def test_redaction_round_trips_arbitrary_text(tokens: list[str]) -> None:
    original = " ".join(tokens)
    redacted = Redactor().redact(original)
    assert redacted.restore(redacted.text) == original
    assert "priya@acme.io" not in redacted.text
