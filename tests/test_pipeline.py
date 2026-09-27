from __future__ import annotations

import asyncio
import time
from datetime import UTC, date, datetime, timedelta

import pytest

from chief_of_staff.config import Settings
from chief_of_staff.extraction.factory import build_service
from chief_of_staff.extraction.heuristic import HeuristicExtractor
from chief_of_staff.extraction.service import Backend, ExtractionService
from chief_of_staff.graph import build_graph, run_graph
from chief_of_staff.ingest.files import load_messages
from chief_of_staff.models import Message, Priority, RawExtraction, Source
from chief_of_staff.pipeline import Pipeline, partition
from helpers import ROOT, FakeAnthropic, StatusError, make_message

SAMPLES = ROOT / "datasets" / "samples"
PRIORITY_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def sample_messages() -> list[Message]:
    return load_messages(SAMPLES / "slack.json", source=Source.SLACK) + load_messages(
        SAMPLES / "email.json", source=Source.EMAIL
    )


@pytest.fixture
def pipeline(offline_settings: Settings) -> Pipeline:
    return Pipeline(build_service(offline_settings))


async def test_sample_inbox_end_to_end(pipeline: Pipeline) -> None:
    digest = await pipeline.run(sample_messages())
    p0 = [i.action for i in digest.open_items if i.priority is Priority.P0]
    assert any("memory leak" in action for action in p0)
    assert any("Roll back the gateway" in action for action in p0)

    deck = next(i for i in digest.open_items if "board deck" in i.action.lower())
    assert deck.related_message_ids and deck.due_date == date(2026, 9, 24)

    assert [i.resolved_by for i in digest.resolved_items] == ["slk-007"]
    assert [c.message_id for c in digest.unmatched_completions] == ["slk-004", "eml-005"]
    assert {s.message_id: s.reason for s in digest.skipped} == {
        "slk-012": "chatter",
        "eml-002": "automated_no_action",
    }
    assert not any("can you pay" in i.evidence for i in digest.open_items)
    ranks = [PRIORITY_RANK[i.priority.value] for i in digest.open_items if i.priority]
    assert ranks == sorted(ranks)
    stats = digest.stats
    assert (stats.messages_total, stats.duplicates_merged, stats.completions_matched) == (18, 1, 1)


async def test_as_of_defaults_to_latest_message_and_can_be_overridden(pipeline: Pipeline) -> None:
    messages = sample_messages()
    assert (await pipeline.run(messages)).as_of == max(m.timestamp for m in messages)
    later = datetime(2026, 10, 1, tzinfo=UTC)
    digest = await pipeline.run(messages, as_of=later)
    assert digest.as_of == later
    assert any("overdue" in " ".join(i.reasons) for i in digest.open_items)


def test_partition_drops_duplicate_ids_and_noise() -> None:
    messages = [
        make_message("thanks!", id="a"),
        make_message("Sam, ship it", id="b"),
        make_message("Sam, ship it", id="b"),
    ]
    candidates, skipped = partition(messages)
    assert [m.id for m in candidates] == ["b"]
    assert {(s.message_id, s.reason) for s in skipped} == {("a", "chatter"), ("b", "duplicate_id")}
    assert [m.id for m in partition(messages, enabled=False)[0]] == ["a", "b"]


async def test_progress_callback_reports_every_message(pipeline: Pipeline) -> None:
    calls: list[tuple[int, int]] = []
    await pipeline.run(sample_messages(), progress=lambda done, total: calls.append((done, total)))
    assert calls[-1] == (16, 16) and len(calls) == 16


async def test_failed_messages_are_surfaced_not_swallowed() -> None:
    from chief_of_staff.extraction.anthropic_backend import AnthropicExtractor

    failing = Backend(AnthropicExtractor(FakeAnthropic(StatusError(401)), "m"))
    digest = await Pipeline(ExtractionService(chain=[failing])).run([make_message("Sam, ship it")])
    assert digest.stats.messages_failed == 1
    assert digest.skipped[0].reason.startswith("failed:")


async def test_empty_input_yields_empty_digest(pipeline: Pipeline) -> None:
    digest = await pipeline.run([])
    assert digest.open_items == [] and digest.stats.messages_total == 0


@pytest.mark.perf
async def test_extraction_runs_concurrently() -> None:
    class Slow:
        name, model = "slow", "slow"

        async def extract(self, message: Message, body: str) -> RawExtraction:
            await asyncio.sleep(0.05)
            return await HeuristicExtractor().extract(message, body)

    start = datetime(2026, 9, 14, tzinfo=UTC)
    messages = [
        make_message(
            f"Sam, please review PR {i} by Friday", id=f"m{i}", when=start + timedelta(minutes=i)
        )
        for i in range(60)
    ]
    service = ExtractionService(chain=[Backend(Slow())], max_concurrency=20)
    started = time.perf_counter()
    digest = await Pipeline(service).run(messages)
    elapsed = time.perf_counter() - started
    assert elapsed < 1.0, f"60 x 50 ms calls took {elapsed:.2f}s; sequential would take 3s"
    assert digest.stats.items_extracted == 60


async def test_langgraph_orchestration_matches_the_pipeline(offline_settings: Settings) -> None:
    service = build_service(offline_settings)
    messages = sample_messages()
    expected = await Pipeline(service).run(messages)
    actual = await run_graph(build_graph(service), messages)

    def key(items: list) -> list:  # type: ignore[type-arg]
        return [
            (i.id, i.priority, i.score, i.owner, i.due_date, i.related_message_ids) for i in items
        ]

    assert key(actual.open_items) == key(expected.open_items)
    assert key(actual.resolved_items) == key(expected.resolved_items)
    assert actual.skipped == expected.skipped


async def test_langgraph_handles_all_noise_and_checkpointing(offline_settings: Settings) -> None:
    from langgraph.checkpoint.memory import InMemorySaver

    graph = build_graph(build_service(offline_settings), checkpointer=InMemorySaver())
    digest = await run_graph(
        graph, [make_message("thanks!"), make_message("lol", id="m2")], thread_id="noise"
    )
    assert digest.open_items == [] and digest.stats.messages_skipped == 2
