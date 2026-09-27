"""Chief-of-Staff AI: turn Slack and email into a verified, prioritized commitment ledger."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.progress import Progress

from chief_of_staff.config import Settings
from chief_of_staff.extraction.factory import (
    ConfigurationError,
    build_prioritizer,
    build_service,
)
from chief_of_staff.ingest.files import load_messages
from chief_of_staff.ingest.slack import SlackClient, load_slack_export
from chief_of_staff.ledger import Ledger
from chief_of_staff.models import Digest, Message, Source, Status
from chief_of_staff.pipeline import Pipeline
from chief_of_staff.prioritization import Prioritizer
from chief_of_staff.render import render_markdown, render_table

app = typer.Typer(add_completion=False, no_args_is_help=True, help=__doc__)
ledger_app = typer.Typer(no_args_is_help=True, help="Inspect the persistent commitment ledger.")
gmail_app = typer.Typer(no_args_is_help=True, help="Pull mail from Gmail (needs the gmail extra).")
slack_app = typer.Typer(no_args_is_help=True, help="Pull channel history from the Slack Web API.")
app.add_typer(ledger_app, name="ledger")
app.add_typer(gmail_app, name="gmail")
app.add_typer(slack_app, name="slack")
console = Console()


class OutputFormat(StrEnum):
    TABLE = "table"
    MARKDOWN = "markdown"
    JSON = "json"


class Backend(StrEnum):
    AUTO = "auto"
    HEURISTIC = "heuristic"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


def _settings(backend: Backend, no_cache: bool) -> Settings:
    overrides: dict[str, Any] = {"backend": backend.value}
    if no_cache:
        overrides["cache_enabled"] = False
    return Settings(**overrides)


@app.callback()
def main(verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False) -> None:
    logging.basicConfig(level=logging.INFO if verbose else logging.WARNING, format="%(message)s")


@app.command()
def run(
    slack: Annotated[list[Path] | None, typer.Option(help="Slack messages JSON/JSONL.")] = None,
    email: Annotated[list[Path] | None, typer.Option(help="Email messages JSON/JSONL.")] = None,
    slack_export: Annotated[
        Path | None, typer.Option(help="Slack workspace export directory.")
    ] = None,
    backend: Annotated[Backend, typer.Option(help="Extraction backend.")] = Backend.AUTO,
    output_format: Annotated[OutputFormat, typer.Option("--format")] = OutputFormat.TABLE,
    output: Annotated[Path | None, typer.Option(help="Write the digest to a file.")] = None,
    as_of: Annotated[datetime | None, typer.Option(help="Reference time for due dates.")] = None,
    ledger: Annotated[
        Path | None, typer.Option(help="Merge results into this SQLite ledger.")
    ] = None,
    policy: Annotated[Path | None, typer.Option(help="Priority policy TOML overrides.")] = None,
    graph: Annotated[bool, typer.Option(help="Run through the LangGraph orchestrator.")] = False,
    no_cache: Annotated[bool, typer.Option("--no-cache")] = False,
) -> None:
    """Extract, verify, deduplicate and prioritize action items."""
    messages: list[Message] = []
    for path in slack or []:
        messages += load_messages(path, source=Source.SLACK)
    for path in email or []:
        messages += load_messages(path, source=Source.EMAIL)
    if slack_export:
        messages += load_slack_export(slack_export)
    if not messages:
        raise typer.BadParameter("provide at least one of --slack, --email or --slack-export")

    settings = _settings(backend, no_cache)
    try:
        service = build_service(settings)
    except ConfigurationError as exc:
        raise typer.BadParameter(str(exc)) from exc
    prioritizer = build_prioritizer(settings, policy)
    digest = asyncio.run(_run(service, prioritizer, messages, as_of, graph, settings.prefilter))

    if ledger:
        result = Ledger(ledger).sync(digest)
        console.print(
            f"[dim]ledger: +{result.added} new, {result.updated} updated, {result.closed} closed[/]"
        )
    _emit(digest, output_format, output)


async def _run(
    service: Any,
    prioritizer: Prioritizer,
    messages: list[Message],
    as_of: datetime | None,
    graph: bool,
    prefilter: bool,
) -> Digest:
    if graph:
        from chief_of_staff.graph import build_graph, run_graph

        compiled = build_graph(service, prioritizer, prefilter=prefilter)
        return await run_graph(compiled, messages, as_of=as_of)
    with Progress(console=console, transient=True) as progress:
        task = progress.add_task("Extracting", total=None)

        def update(done: int, total: int) -> None:
            progress.update(task, completed=done, total=total)

        return await Pipeline(service, prioritizer, prefilter=prefilter).run(
            messages, as_of=as_of, progress=update
        )


def _emit(digest: Digest, output_format: OutputFormat, output: Path | None) -> None:
    if output_format is OutputFormat.TABLE and output is None:
        render_table(digest, console)
        return
    text = (
        digest.model_dump_json(indent=2)
        if output_format is OutputFormat.JSON
        else render_markdown(digest)
    )
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        console.print(f"wrote {output}")
    else:
        typer.echo(text)


@app.command("eval")
def evaluate_command(
    split: Annotated[str, typer.Option(help="dev, test or injection.")] = "test",
    backend: Annotated[Backend, typer.Option()] = Backend.AUTO,
    data_dir: Annotated[Path, typer.Option()] = Path("datasets/eval"),
    report: Annotated[Path | None, typer.Option(help="Write a Markdown report here.")] = None,
    json_out: Annotated[
        Path | None, typer.Option("--json", help="Write the full JSON report.")
    ] = None,
    bootstrap: Annotated[int, typer.Option(help="Bootstrap resamples for CIs.")] = 1000,
    no_cache: Annotated[bool, typer.Option("--no-cache")] = False,
) -> None:
    """Score a backend on a labeled split with bootstrap confidence intervals."""
    from chief_of_staff.evaluation.report import to_markdown
    from chief_of_staff.evaluation.runner import evaluate, load_split

    settings = _settings(backend, no_cache)
    try:
        service = build_service(settings)
    except ConfigurationError as exc:
        raise typer.BadParameter(str(exc)) from exc
    examples = load_split(data_dir / f"{split}.jsonl")
    result = asyncio.run(
        evaluate(
            examples,
            service,
            split=split,
            prefilter=settings.prefilter,
            bootstrap_iterations=bootstrap,
        )
    )
    markdown = to_markdown(result)
    if report:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(markdown, encoding="utf-8")
    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    console.print(Markdown(markdown))


@ledger_app.command("show")
def ledger_show(
    path: Annotated[Path, typer.Option()] = Path(".cos/ledger.sqlite"),
    status: Annotated[str, typer.Option(help="open, done or all.")] = "open",
    output_format: Annotated[OutputFormat, typer.Option("--format")] = OutputFormat.TABLE,
) -> None:
    """List items tracked across runs."""
    if not path.exists():
        raise typer.BadParameter(f"no ledger at {path}")
    selected = None if status == "all" else Status(status)
    ledger = Ledger(path)
    items = ledger.items(selected)
    if output_format is OutputFormat.JSON:
        typer.echo("[" + ",".join(item.model_dump_json() for item in items) + "]")
        return
    overdue = {item.id for item in ledger.overdue(datetime.now().astimezone().date())}
    for item in items:
        marker = "[red]OVERDUE[/] " if item.id in overdue else ""
        details = (
            f"owner={item.owner or 'unassigned'} due={item.due_date or '-'} status={item.status}"
        )
        console.print(f"{marker}[bold]{item.priority or '-'}[/] {item.action} [dim]{details}[/]")


@gmail_app.command("pull")
def gmail_pull(
    out: Annotated[Path, typer.Option()] = Path("data/private/inbox.json"),
    query: Annotated[str, typer.Option()] = "newer_than:7d -category:promotions",
    limit: Annotated[int, typer.Option()] = 100,
    credentials: Annotated[Path, typer.Option()] = Path("credentials.json"),
    token: Annotated[Path, typer.Option()] = Path("token.json"),
) -> None:
    """Fetch recent mail into a local, git-ignored JSON file."""
    from chief_of_staff.ingest.gmail import fetch_messages, gmail_service

    _save(fetch_messages(gmail_service(credentials, token), query=query, limit=limit), out)


@slack_app.command("pull")
def slack_pull(
    channel: Annotated[list[str], typer.Option(help="CHANNEL_ID:name, repeatable.")],
    out: Annotated[Path, typer.Option()] = Path("data/private/slack.json"),
    days: Annotated[int, typer.Option(min=1)] = 7,
) -> None:
    """Fetch recent channel history (needs SLACK_BOT_TOKEN with channels:history, users:read)."""
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        raise typer.BadParameter("set SLACK_BOT_TOKEN to a bot token")
    client = SlackClient(token)
    oldest = time.time() - days * 86_400
    messages: list[Message] = []
    for spec in channel:
        channel_id, _, name = spec.partition(":")
        messages += client.channel_messages(channel_id, name or channel_id, oldest=oldest)
    _save(messages, out)


def _save(messages: Sequence[Message], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("[" + ",\n".join(m.model_dump_json() for m in messages) + "]", encoding="utf-8")
    console.print(f"saved {len(messages)} messages to {out} (keep this file out of git)")


@app.command()
def serve(
    host: Annotated[str, typer.Option()] = "127.0.0.1",
    port: Annotated[int, typer.Option()] = 8000,
) -> None:
    """Serve the HTTP API (needs the api extra)."""
    import uvicorn

    from chief_of_staff.api import create_app

    uvicorn.run(create_app(), host=host, port=port)
