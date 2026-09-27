"""Human-facing renderings of a digest: a terminal table and Markdown (Slack/email ready)."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from chief_of_staff.models import ActionItem, Digest

_STYLE = {"P0": "bold red", "P1": "bold yellow", "P2": "cyan", "P3": "dim"}


def _due(item: ActionItem) -> str:
    return item.due_date.strftime("%a %d %b") if item.due_date else "-"


def _source(item: ActionItem) -> str:
    extra = f" +{len(item.related_message_ids)}" if item.related_message_ids else ""
    return f"{item.source.value}:{item.channel or item.sender}{extra}"


def render_table(digest: Digest, console: Console) -> None:
    table = Table(title=f"Action items as of {digest.as_of:%a %d %b %Y}", show_lines=False)
    for column in ("Pri", "Action", "Owner", "Due", "Source", "Why"):
        table.add_column(column, overflow="fold")
    for item in digest.open_items:
        priority = item.priority.value if item.priority else "P3"
        flag = " [magenta](review)[/]" if item.needs_review else ""
        table.add_row(
            f"[{_STYLE[priority]}]{priority}[/]",
            item.action + flag,
            item.owner or "[red]unassigned[/]",
            _due(item),
            _source(item),
            "; ".join(item.reasons[1:]) or item.reasons[0],
        )
    console.print(table)
    for item in digest.resolved_items:
        console.print(f"[green]✓ resolved[/] {item.action} [dim](closed by {item.resolved_by})[/]")
    stats = digest.stats
    console.print(
        f"[dim]{stats.messages_total} messages, {stats.messages_skipped} skipped, "
        f"{stats.llm_calls} model calls, {stats.cache_hits} cache hits, "
        f"{stats.duplicates_merged} duplicates merged, {stats.completions_matched} closed, "
        f"{stats.wall_time_ms:.0f} ms[/]"
    )


def render_markdown(digest: Digest) -> str:
    lines = [f"# Action items as of {digest.as_of:%A %d %B %Y}", ""]
    if not digest.open_items:
        lines.append("Nothing needs attention.")
    for item in digest.open_items:
        priority = item.priority.value if item.priority else "P3"
        review = " _(needs review)_" if item.needs_review else ""
        lines.append(
            f"- **{priority}** {item.action}{review} | owner: {item.owner or '**unassigned**'}"
            f" | due: {_due(item)} | {_source(item)}"
        )
        lines.append(f"  - > {item.evidence}")
    if digest.resolved_items:
        lines += ["", "## Resolved in this batch", ""]
        lines += [f"- ~~{i.action}~~ (closed by `{i.resolved_by}`)" for i in digest.resolved_items]
    return "\n".join(lines) + "\n"
