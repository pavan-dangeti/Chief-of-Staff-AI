from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from chief_of_staff.models import Priority
from chief_of_staff.prioritization import Prioritizer, PriorityPolicy
from helpers import make_action_item

TODAY = date(2026, 9, 14)
ranker = Prioritizer()


@pytest.mark.parametrize(
    "text",
    [
        "Update the product roadmap",
        "Download the Q3 report",
        "Fix the markdown export",
        "Review the security questionnaire",
        "Send the contract downloads page",
    ],
)
def test_substring_regression_no_false_signals(text: str) -> None:
    scored = ranker.score(make_action_item(text), TODAY)
    joined = " ".join(scored.reasons)
    assert "production" not in joined and "outage" not in joined and "security" not in joined


def test_outage_with_immediate_deadline_is_p0() -> None:
    scored = ranker.score(
        make_action_item("EU API is down, roll back the gateway asap", due="2026-09-14"), TODAY
    )
    assert scored.priority is Priority.P0
    assert "outage" in scored.reasons[1]


@pytest.mark.parametrize(
    ("days", "reason"),
    [
        (-2, "overdue by 2d (+4)"),
        (0, "due today (+3.5)"),
        (1, "due tomorrow (+3)"),
        (3, "due in 3d (+2)"),
        (6, "due in 6d (+1)"),
        (20, "due in 20d (+0.5)"),
    ],
)
def test_deadline_bands(days: int, reason: str) -> None:
    due = (TODAY + timedelta(days=days)).isoformat()
    assert reason in ranker.score(make_action_item("Ship the fix", due=due), TODAY).reasons


def test_sender_role_is_weighted() -> None:
    ceo = ranker.score(make_action_item("Ship the fix", role="ceo"), TODAY)
    intern = ranker.score(make_action_item("Ship the fix", role="internal"), TODAY)
    assert ceo.score is not None and intern.score is not None
    assert ceo.score - intern.score == pytest.approx(2.0)


def test_unassigned_requests_get_a_bump_but_commitments_do_not() -> None:
    request = ranker.score(make_action_item("Ship the fix", owner=None), TODAY)
    commitment = ranker.score(
        make_action_item("Ship the fix", owner=None, kind="commitment"), TODAY
    )
    assert "no owner named (+0.5)" in request.reasons
    assert "no owner named (+0.5)" not in commitment.reasons


def test_low_confidence_is_flagged_for_review_without_changing_score() -> None:
    confident = ranker.score(make_action_item("Ship the fix", confidence=0.9), TODAY)
    unsure = ranker.score(make_action_item("Ship the fix", confidence=0.4), TODAY)
    assert unsure.needs_review and not confident.needs_review
    assert unsure.score == confident.score


def test_surrounding_context_counts_at_half_weight() -> None:
    scored = ranker.score(
        make_action_item("Roll back the config", channel=None),
        TODAY,
        context="The site is down for everyone.",
    )
    assert scored.score == pytest.approx(1.5 + 1.5)
    assert "context: outage" in scored.reasons[1]


def test_completions_are_not_prioritized() -> None:
    assert ranker.score(make_action_item("Reverted it", kind="completion"), TODAY).priority is None


def test_policy_loads_company_overrides_from_toml(tmp_path: Path) -> None:
    path = tmp_path / "policy.toml"
    path.write_text(
        "review_threshold = 0.8\n[role_weights]\nsales_lead = 2.5\n"
        '[signals.enterprise]\npattern = "\\\\bfortune 500\\\\b"\nweight = 2.0\n'
        "[thresholds]\np0 = 9.0\n"
    )
    policy = PriorityPolicy.from_toml(path)
    assert policy.role_weights["sales_lead"] == 2.5
    assert policy.thresholds[0] == 9.0
    assert policy.review_threshold == 0.8
    scored = Prioritizer(policy).score(
        make_action_item("Call the Fortune 500 prospect", role="sales_lead"), TODAY
    )
    assert "enterprise" in scored.reasons[1]


def test_scoring_is_deterministic() -> None:
    item = make_action_item("Payroll failed in prod, fix asap", due="2026-09-15")
    assert ranker.score(item, TODAY) == ranker.score(item, TODAY)
