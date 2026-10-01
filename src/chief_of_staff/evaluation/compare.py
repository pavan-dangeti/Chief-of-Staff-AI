"""One comparison table across backends, built from saved ``cos eval --json`` reports."""

from __future__ import annotations

from pathlib import Path

from chief_of_staff.evaluation.runner import EvalReport


def load_report(path: Path) -> EvalReport:
    return EvalReport.model_validate_json(path.read_text(encoding="utf-8"))


def _seconds(ms: float) -> str:
    return f"{ms / 1000:.1f} s"


def _cost(report: EvalReport) -> str:
    if report.list_cost_per_1k_messages_usd is not None:
        return f"${report.list_cost_per_1k_messages_usd:.3f}"
    return "$0 (runs locally)" if report.backend.startswith("heuristic") else "n/a (no price)"


def comparison_table(runs: list[tuple[EvalReport, EvalReport]]) -> str:
    """``runs`` pairs each backend's held-out test report with its injection report."""
    lines = [
        "| Backend | Item F1 (95% CI) | Precision | Recall | Attacks succeeded "
        "| Call time p50 / p95 | List-price estimate per 1,000 messages |",
        "|---|---|---|---|---|---|---|",
    ]
    for test, injection in runs:
        if (test.split, injection.split) != ("test", "injection"):
            raise ValueError(f"expected a test and an injection report for {test.backend}")
        if test.backend != injection.backend:
            raise ValueError(f"reports differ in backend: {test.backend}, {injection.backend}")
        if test.failures or injection.failures:
            raise ValueError(f"{test.backend} has failed messages; rerun it to completion")
        item = test.item_level
        low, high = item.f1_ci95
        attacks = sum(r.attack_succeeded is not None for r in injection.results)
        hits = sum(bool(r.attack_succeeded) for r in injection.results)
        latency = (
            f"{_seconds(test.call_ms_p50)} / {_seconds(test.call_ms_p95)}"
            if test.timed_calls
            else f"{test.latency_ms_p50:.1f} / {test.latency_ms_p95:.1f} ms, local"
        )
        lines.append(
            f"| `{test.backend}` | **{item.f1:.3f}** ({low:.3f}–{high:.3f}) "
            f"| {item.precision:.3f} | {item.recall:.3f} | {hits} of {attacks} "
            f"| {latency} | {_cost(test)} |"
        )
    return "\n".join(lines) + "\n"


def _f1(report: EvalReport) -> str:
    low, high = report.item_level.f1_ci95
    return f"{report.item_level.f1:.3f} ({low:.3f}–{high:.3f})"


def _attacks(report: EvalReport) -> str:
    attacks = sum(r.attack_succeeded is not None for r in report.results)
    return f"{sum(bool(r.attack_succeeded) for r in report.results)} of {attacks}"


def external_table(runs: list[tuple[EvalReport, EvalReport, EvalReport]]) -> str:
    """``runs`` holds (held-out test, external before the defences, external now) per backend."""
    lines = [
        "| Backend | Held-out test F1 | External F1, before defences | Change from held-out "
        "| External F1, now | Attacks succeeded, before → now |",
        "|---|---|---|---|---|---|",
    ]
    for test, before, now in runs:
        if (test.split, before.split, now.split) != ("test", "external", "external"):
            raise ValueError(f"expected a test and two external reports for {test.backend}")
        if len({test.backend, before.backend, now.backend}) != 1:
            raise ValueError(f"reports are for different backends: {test.backend}")
        if test.failures or before.failures or now.failures:
            raise ValueError(f"{test.backend} has failed messages; rerun it to completion")
        # Neither the held-out split nor "before" informed the defences, so compare those two;
        # "now" was measured after defences designed on this set and is optimistic.
        change = before.item_level.f1 - test.item_level.f1
        lines.append(
            f"| `{test.backend}` | {_f1(test)} | {_f1(before)} | **{change:+.3f}** "
            f"| {_f1(now)} | {_attacks(before)} → {_attacks(now)} |"
        )
    return "\n".join(lines) + "\n"
