"""Render an :class:`EvalReport` as Markdown for READMEs and pull requests."""

from __future__ import annotations

from chief_of_staff.evaluation.runner import PRF, EvalReport


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def _row(name: str, prf: PRF) -> str:
    low, high = prf.f1_ci95
    return (
        f"| {name} | {prf.precision:.3f} | {prf.recall:.3f} | **{prf.f1:.3f}** "
        f"| [{low:.3f}, {high:.3f}] | {prf.tp} | {prf.fp} | {prf.fn} |"
    )


def to_markdown(report: EvalReport, *, max_errors: int = 15) -> str:
    latency = (
        f"{report.latency_ms_p50:.1f} / {report.latency_ms_p95:.1f} ms"
        if report.live_calls
        else "n/a (all answers cached)"
    )
    call_time = (
        f"{report.call_ms_p50:.0f} / {report.call_ms_p95:.0f} ms" if report.timed_calls else "n/a"
    )
    per_1k = (
        "n/a (no price configured)"
        if report.list_cost_per_1k_messages_usd is None
        else f"${report.list_cost_per_1k_messages_usd:.4f} (see docs/pricing.md)"
    )
    lines = [
        f"## Evaluation: `{report.split}` split, backend `{report.backend}`",
        "",
        f"{report.examples} examples, prompt v{report.prompt_version}, "
        f"run {report.created_at:%Y-%m-%d %H:%M} UTC in {report.wall_time_s:.2f}s.",
        "",
        "| Level | Precision | Recall | F1 | F1 95% CI | TP | FP | FN |",
        "|---|---|---|---|---|---|---|---|",
        _row("Message (has any item)", report.message_level),
        _row("Item (one-to-one match)", report.item_level),
        "",
        "| Field accuracy on matched items | Value |",
        "|---|---|",
        f"| Kind (request / commitment / completion) | {_pct(report.kind_accuracy)} |",
        f"| Owner (excl. completions) | {_pct(report.owner_accuracy)} |",
        f"| Due date, exact day (excl. completions) | {_pct(report.due_date_accuracy)} |",
        "",
        "| Operational | Value |",
        "|---|---|",
        f"| Prefilter skip rate | {_pct(report.prefilter_skip_rate)} |",
        f"| Gold items lost to prefilter | {report.prefilter_false_negatives} |",
        f"| Extraction failures | {report.failures} |",
        f"| Answers from live calls / from cache | {report.live_calls} / {report.cache_hits} |",
        f"| Latency p50 / p95, live calls only | {latency} |",
        f"| Tokens in / out | {report.input_tokens:,} / {report.output_tokens:,} |",
        f"| Cost | {'n/a' if report.cost_usd is None else f'${report.cost_usd:.4f}'} |",
        f"| Provider call time p50 / p95 ({report.timed_calls} timed answers) | {call_time} |",
        f"| Recorded tokens in / out, all answers | {report.recorded_input_tokens:,} / "
        f"{report.recorded_output_tokens:,} |",
        f"| List-price estimate per 1,000 messages | {per_1k} |",
    ]
    if report.attack_success_rate is not None:
        lines.append(
            f"| Prompt-injection attack success rate | {_pct(report.attack_success_rate)} |"
        )
    errors = [
        r
        for r in report.results
        if r.matched != r.expected or len(r.predicted) != r.matched or r.attack_succeeded
    ]
    if errors:
        lines += [
            "",
            f"### Error analysis ({len(errors)} examples, first {min(len(errors), max_errors)})",
            "",
        ]
        for result in errors[:max_errors]:
            predicted = "; ".join(result.predicted) or "(none)"
            flag = " **attack succeeded**" if result.attack_succeeded else ""
            lines.append(
                f"- `{result.id}` {','.join(result.tags)}: expected {result.expected}, "
                f"matched {result.matched}{flag}. Predicted: {predicted}"
            )
    return "\n".join(lines) + "\n"
