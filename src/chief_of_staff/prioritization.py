"""Explainable priority scoring, computed outside the model so text cannot manipulate it."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from chief_of_staff.models import ActionItem, ItemKind, Priority

_DEFAULT_ROLE_WEIGHTS = {
    "ceo": 3.0,
    "founder": 3.0,
    "board_member": 3.0,
    "customer": 3.0,
    "cofounder": 2.5,
    "cto": 2.5,
    "external_partner": 2.5,
    "investor": 2.0,
    "coo": 2.0,
    "cfo": 2.0,
    "manager": 2.0,
    "engineer": 1.5,
    "internal": 1.0,
    "unknown": 1.0,
    "automated": 0.5,
}


def _words(*alternatives: str) -> str:
    return rf"\b(?:{'|'.join(alternatives)})\b"


_DEFAULT_SIGNALS: tuple[tuple[str, str, float], ...] = (
    (
        "outage",
        _words(
            "outages?",
            "downtime",
            "(?:is|are|went|was|goes|going) down",
            "sev ?[01]",
            "p0",
            "incidents?",
        ),
        3.0,
    ),
    (
        "security",
        _words(
            "security (?:incident|breach|issue|hole|bug)",
            "breach(?:ed)?",
            "vulnerabilit(?:y|ies)",
            "leaked",
            "exposed (?:keys|credentials|data)",
            "compromised",
            r"cve-\d+",
        ),
        3.0,
    ),
    (
        "production",
        _words("prod", "production", "live site", "customers? (?:are|can't|cannot)"),
        2.0,
    ),
    (
        "breakage",
        _words(
            "broke",
            "broken",
            "failing",
            "failed",
            "crash(?:es|ing)?",
            "revert",
            "rollback",
            "leak(?:s|ing)?",
            "data loss",
        ),
        2.0,
    ),
    ("urgency", _words("urgent", "asap", "immediately", "critical", "right away"), 2.0),
    ("blocker", _words("blocker", "blocking", "blocked"), 1.5),
    (
        "money",
        _words(
            "payments?",
            "billing",
            "invoice",
            "payroll",
            "refund",
            "revenue",
            "churn",
            "contract",
            "renewal",
        ),
        1.0,
    ),
    ("legal", _words("legal", "compliance", "gdpr", "audit", "nda", "lawsuit", "regulator"), 1.5),
    ("customer", _words("customer", "client", "enterprise", "pilot", "escalat(?:e|ion)"), 1.0),
)


@dataclass(frozen=True)
class PriorityPolicy:
    role_weights: dict[str, float] = field(default_factory=lambda: dict(_DEFAULT_ROLE_WEIGHTS))
    signals: tuple[tuple[str, str, float], ...] = _DEFAULT_SIGNALS
    signal_cap: float = 6.0
    context_weight: float = 0.5
    unassigned_bonus: float = 0.5
    thresholds: tuple[float, float, float] = (7.0, 4.5, 2.5)
    review_threshold: float = 0.6

    @classmethod
    def from_toml(cls, path: Path) -> PriorityPolicy:
        """Load overrides such as ``[role_weights] sales_lead = 2.5`` from a TOML file."""
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        base = cls()
        roles = {**base.role_weights, **data.get("role_weights", {})}
        signals = base.signals + tuple(
            (name, spec["pattern"], float(spec["weight"]))
            for name, spec in data.get("signals", {}).items()
        )
        thresholds = data.get("thresholds", {})
        return cls(
            role_weights=roles,
            signals=signals,
            thresholds=(
                float(thresholds.get("p0", base.thresholds[0])),
                float(thresholds.get("p1", base.thresholds[1])),
                float(thresholds.get("p2", base.thresholds[2])),
            ),
            review_threshold=float(data.get("review_threshold", base.review_threshold)),
        )

    def compiled_signals(self) -> list[tuple[str, re.Pattern[str], float]]:
        return [(name, re.compile(pattern, re.IGNORECASE), w) for name, pattern, w in self.signals]


def _deadline_points(due: date | None, as_of: date) -> tuple[float, str | None]:
    if due is None:
        return 0.0, None
    days = (due - as_of).days
    if days < 0:
        return 4.0, f"overdue by {-days}d (+4)"
    if days == 0:
        return 3.5, "due today (+3.5)"
    if days == 1:
        return 3.0, "due tomorrow (+3)"
    if days <= 3:
        return 2.0, f"due in {days}d (+2)"
    if days <= 7:
        return 1.0, f"due in {days}d (+1)"
    return 0.5, f"due in {days}d (+0.5)"


class Prioritizer:
    def __init__(self, policy: PriorityPolicy | None = None) -> None:
        self.policy = policy or PriorityPolicy()
        self._signals = self.policy.compiled_signals()

    def score(self, item: ActionItem, as_of: date, context: str = "") -> ActionItem:
        """Score ``item``; ``context`` (surrounding message text) counts at reduced weight."""
        if item.kind is ItemKind.COMPLETION:
            return item
        policy = self.policy
        role = item.sender_role.casefold()
        role_points = policy.role_weights.get(role, policy.role_weights["unknown"])
        reasons = [f"sender role '{role}' (+{role_points:g})"]
        score = role_points

        own_text = f"{item.evidence}\n{item.action}\n{item.channel or ''}"
        surrounding = context
        own = [(name, w) for name, rx, w in self._signals if rx.search(own_text)]
        nearby = [
            (name, w * policy.context_weight)
            for name, rx, w in self._signals
            if not rx.search(own_text) and rx.search(surrounding)
        ]
        matched = own + nearby
        if matched:
            signal_points = min(sum(weight for _, weight in matched), policy.signal_cap)
            score += signal_points
            names = ", ".join(name for name, _ in own)
            nearby_names = ", ".join(name for name, _ in nearby)
            label = "; ".join(
                part
                for part in (
                    names and f"signals: {names}",
                    nearby_names and f"context: {nearby_names}",
                )
                if part
            )
            reasons.append(f"{label} (+{signal_points:g})")

        deadline_points, deadline_reason = _deadline_points(item.due_date, as_of)
        if deadline_reason:
            score += deadline_points
            reasons.append(deadline_reason)

        if item.owner is None and item.kind is ItemKind.REQUEST:
            score += policy.unassigned_bonus
            reasons.append(f"no owner named (+{policy.unassigned_bonus:g})")

        ladder = zip((Priority.P0, Priority.P1, Priority.P2), policy.thresholds, strict=True)
        priority = next((p for p, threshold in ladder if score >= threshold), Priority.P3)
        return item.model_copy(
            update={
                "priority": priority,
                "score": round(score, 2),
                "reasons": reasons,
                "needs_review": item.confidence < policy.review_threshold,
            }
        )
