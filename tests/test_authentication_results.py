"""Sender verification against ``authres``, the RFC 8601 reference parser.

This property test generates Authentication-Results headers with comments, quoted strings, several
results and several authserv-ids, and checks that a sender is never called verified unless the
reference parser finds one DMARC pass for the From domain from the trusted server.

It was written against a hand-written reader (regex plus ``split(";")``) and found two real
disagreements: a result with conflicting ``header.from`` values was verified on the first one, and
a pair of unterminated quotes could hide the text between them. The reader now uses authres
itself, so the test guards the verdict rules and any future attempt to parse by hand.
"""

from __future__ import annotations

import authres
from hypothesis import given, settings
from hypothesis import strategies as st

from chief_of_staff.ingest.gmail import sender_verified

FROM_DOMAIN = "acme.io"
TRUSTED = "mx.google.com"
_SMUGGLED = "; dmarc=pass header.from=acme.io"


def reference_verdict(value: str) -> bool:
    """Verified, read with authres: one DMARC pass for the From domain, from the trusted server."""
    try:
        parsed = authres.AuthenticationResultsHeader.parse(f"Authentication-Results: {value}")
    except authres.AuthResError:
        return False
    dmarc = [result for result in parsed.results if result.method == "dmarc"]
    if (parsed.authserv_id or "").lower() != TRUSTED or len(dmarc) != 1:
        return False
    claimed = [p.value for p in dmarc[0].properties if (p.type, p.name) == ("header", "from")]
    return dmarc[0].result == "pass" and {str(c).lower() for c in claimed} == {FROM_DOMAIN}


comment_text = st.sampled_from(
    ["p=REJECT sp=NONE", "dmarc=pass header.from=acme.io", _SMUGGLED + ";", 'a "quoted" b', "x"]
)
comments = st.recursive(
    comment_text.map(lambda text: f"({text})"),
    lambda inner: st.tuples(comment_text, inner).map(lambda pair: f"({pair[0]} {pair[1]})"),
    max_leaves=3,
)
gap = st.one_of(st.just(" "), comments.map(lambda comment: f" {comment} "))
domains = st.sampled_from([FROM_DOMAIN, "evil.io", "ACME.io", "acme.io.evil.io"])
quoted_mailbox = st.sampled_from(
    [f'"a{_SMUGGLED} x"@evil.io', f'"a{_SMUGGLED}', '"a\\"b"@evil.io', "bounce@evil.io"]
)
properties = st.one_of(
    domains.map(lambda domain: f"header.from={domain}"),
    domains.map(lambda domain: f"header.i=@{domain}"),
    quoted_mailbox.map(lambda mailbox: f"smtp.mailfrom={mailbox}"),
)
results = st.tuples(
    st.sampled_from(["dmarc", "spf", "dkim", "DMARC"]),
    st.sampled_from(["pass", "fail", "none", "PASS"]),
    gap,
    st.lists(properties, max_size=3),
).map(lambda parts: f"{parts[0]}={parts[1]}{parts[2]}{' '.join(parts[3])}")
servers = st.sampled_from([TRUSTED, "mail.evil.io", f"{TRUSTED} 1", f"evil.io {TRUSTED}", ""])
headers = st.tuples(servers, gap, st.lists(results, max_size=4), st.sampled_from(["; ", ";"])).map(
    lambda parts: parts[0] + parts[1] + "".join(f"{parts[3]}{result}" for result in parts[2])
)
# A second header below the first, as a sender would add one: only the topmost may count.
stacks = st.lists(headers, min_size=1, max_size=2)


@settings(max_examples=2000, deadline=None)
@given(stacks)
def test_verified_only_when_the_reference_parser_agrees(stack: list[str]) -> None:
    message = [{"name": "Authentication-Results", "value": value} for value in stack]
    message.append({"name": "From", "value": "Maya Rao <maya@acme.io>"})
    if sender_verified(message) is True:
        assert reference_verdict(stack[0]), stack[0]


@settings(max_examples=500, deadline=None)
@given(st.text(max_size=200))
def test_arbitrary_header_text_never_raises_or_verifies(value: str) -> None:
    message = [
        {"name": "Authentication-Results", "value": value},
        {"name": "From", "value": "Maya Rao <maya@acme.io>"},
    ]
    assert sender_verified(message) is not True or reference_verdict(" ".join(value.split()))


def test_the_two_parsers_agree_on_a_real_gmail_header() -> None:
    value = (
        "mx.google.com; dkim=pass header.i=@acme.io header.s=google header.b=abc; "
        "spf=pass (google.com: domain of maya@acme.io designates 209.85.220.41 as permitted "
        "sender) smtp.mailfrom=maya@acme.io; dmarc=pass (p=REJECT sp=REJECT dis=NONE) "
        "header.from=acme.io"
    )
    message = [
        {"name": "Authentication-Results", "value": value},
        {"name": "From", "value": "Maya Rao <maya@acme.io>"},
    ]
    assert sender_verified(message) is True and reference_verdict(value)
