from __future__ import annotations

import json
import tomllib
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from chief_of_staff.cli import app
from chief_of_staff.config import Settings, list_prices
from chief_of_staff.errors import ConfigurationError
from chief_of_staff.evaluation.runner import evaluate, load_split
from chief_of_staff.extraction.base import ExtractionError
from chief_of_staff.extraction.cache import ExtractionCache
from chief_of_staff.extraction.factory import build_service
from chief_of_staff.extraction.openai_compat_backend import OpenAICompatExtractor
from chief_of_staff.extraction.prompt import SYSTEM_PROMPT, WIRE_SCHEMA
from chief_of_staff.extraction.resilience import classify_error
from chief_of_staff.extraction.service import Backend, ExtractionService
from helpers import ROOT, item, make_message

TEXT = "Ravi, can you rotate the staging keys by Friday?"
MESSAGE = make_message(TEXT)
GOOD = item(TEXT, owner="Ravi", deadline_text="by Friday")
MODEL = "deepseek-ai/deepseek-v4.1-flash"


def completion(content: str, tokens: tuple[int, int] = (900, 100)) -> dict[str, object]:
    return {
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": tokens[0], "completion_tokens": tokens[1]},
    }


def client(
    *responses: httpx.Response | dict[str, object],
) -> tuple[httpx.AsyncClient, list[dict[str, object]]]:
    """A real httpx client whose transport replays ``responses`` and records request bodies."""
    sent: list[dict[str, object]] = []
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        reply = queue.pop(0) if len(queue) > 1 else queue[0]
        return reply if isinstance(reply, httpx.Response) else httpx.Response(200, json=reply)

    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport, base_url="https://nim.test/v1"), sent


async def test_request_uses_the_shared_prompt_schema_and_extra_body() -> None:
    http, sent = client(completion(json.dumps({"items": [GOOD]})))
    extra = {"chat_template_kwargs": {"thinking": False}}
    async with http:
        raw = await OpenAICompatExtractor(http, MODEL, extra_body=extra).extract(MESSAGE, TEXT)
    body = sent[0]
    assert body["model"] == MODEL and body["temperature"] == 0
    assert body["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT}  # type: ignore[index]
    assert body["response_format"]["json_schema"]["schema"] == WIRE_SCHEMA  # type: ignore[index]
    assert body["chat_template_kwargs"] == {"thinking": False}
    assert (raw.backend, raw.model, raw.items[0].owner) == ("nvidia", MODEL, "Ravi")
    assert (raw.usage.input_tokens, raw.usage.output_tokens) == (900, 100)
    assert raw.usage.latency_ms > 0


@pytest.mark.parametrize(
    "wrap",
    [
        lambda s: f"<think>the user wants JSON</think>\n{s}",
        lambda s: f"```json\n{s}\n```",
    ],
)
async def test_reasoning_blocks_and_code_fences_are_stripped(wrap: Callable[[str], str]) -> None:
    http, _ = client(completion(wrap(json.dumps({"items": [GOOD]}))))
    async with http:
        raw = await OpenAICompatExtractor(http, MODEL).extract(MESSAGE, TEXT)
    assert len(raw.items) == 1


async def test_missing_message_content_is_an_extraction_error() -> None:
    http, sent = client({"choices": [], "usage": {}})
    async with http:
        with pytest.raises(ExtractionError, match="no message content"):
            await OpenAICompatExtractor(http, MODEL).extract(MESSAGE, TEXT)
    assert len(sent) == 1


async def test_rate_limit_status_is_retryable_and_honours_retry_after() -> None:
    http, _ = client(httpx.Response(429, headers={"retry-after": "7"}, json={}))
    async with http:
        with pytest.raises(httpx.HTTPStatusError) as caught:
            await OpenAICompatExtractor(http, MODEL).extract(MESSAGE, TEXT)
    decision = classify_error(caught.value)
    assert decision.retryable and decision.retry_after == 7.0


async def test_resumed_answers_keep_their_measured_tokens_latency_and_list_cost() -> None:
    http, sent = client(completion(json.dumps({"items": [GOOD]})))
    prices = {MODEL: (0.30, 1.20)}
    async with http:
        with ExtractionCache(":memory:") as cache:
            backend = Backend(OpenAICompatExtractor(http, MODEL))
            service = ExtractionService(chain=[backend], cache=cache, prices=prices)
            live = (await service.extract_message(MESSAGE)).trace
            resumed = (await service.extract_message(MESSAGE)).trace
    assert len(sent) == 1 and resumed.cache_hit
    assert (live.input_tokens, resumed.input_tokens) == (900, 0)  # spend: live calls only
    assert resumed.recorded_input_tokens == live.recorded_input_tokens == 900
    assert resumed.call_ms == live.call_ms > 0
    assert (
        resumed.list_cost_usd
        == live.list_cost_usd
        == pytest.approx((900 * 0.30 + 100 * 1.20) / 1_000_000)
    )


async def test_eval_report_prices_every_ingested_message() -> None:
    http, _ = client(completion(json.dumps({"items": []}), tokens=(1000, 0)))
    examples = load_split(ROOT / "datasets" / "eval" / "test.jsonl")[:5]
    async with http:
        service = ExtractionService(
            chain=[Backend(OpenAICompatExtractor(http, MODEL))], prices={MODEL: (1.0, 0.0)}
        )
        report = await evaluate(examples, service, split="test", bootstrap_iterations=10)
    answered = report.examples - round(report.prefilter_skip_rate * report.examples)
    assert report.timed_calls == answered and report.call_ms_p95 >= report.call_ms_p50 > 0
    assert report.list_cost_usd == pytest.approx(answered * 1000 / 1_000_000)
    assert report.list_cost_per_1k_messages_usd == pytest.approx(answered / 5)


def test_factory_builds_nvidia_with_its_own_escalation_model() -> None:
    http, _ = client(completion("{}"))
    settings = Settings(
        backend="nvidia",
        nvidia_escalation_model="z-ai/glm-5.3",
        fallback_to_heuristic=False,
        cache_enabled=False,
        trace_path=None,
        _env_file=None,
    )
    service = build_service(settings, nvidia_client=http)
    assert [b.label for b in service.chain] == ["nvidia:z-ai/glm-5.3-flash"]
    assert service.escalation is not None and service.escalation.label == "nvidia:z-ai/glm-5.3"
    with pytest.raises(ConfigurationError, match="NVIDIA_API_KEY"):
        build_service(Settings(backend="nvidia", _env_file=None))


def test_nvidia_key_selects_the_backend_automatically(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    assert Settings(_env_file=None).resolved_backend() == "nvidia"


def test_incomplete_eval_writes_no_report_and_says_how_to_resume(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    http, _ = client(httpx.Response(401, json={"error": "bad key"}))

    def failing_service(settings: Settings, **kwargs: object) -> ExtractionService:
        return build_service(settings, nvidia_client=http, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    monkeypatch.setenv("COS_NVIDIA_RPM", "60000")
    monkeypatch.setenv("COS_TRACE_PATH", str(tmp_path / "traces.jsonl"))
    monkeypatch.setattr("chief_of_staff.cli.build_service", failing_service)
    report = tmp_path / "r.md"
    args = ["eval", "--split", "injection", "--backend", "nvidia", "--model", MODEL]
    data = ["--data-dir", str(ROOT / "datasets" / "eval"), "--bootstrap", "10"]
    out = ["--report", str(report), "--cache", str(tmp_path / "run.sqlite")]
    result = CliRunner().invoke(app, [*args, *data, *out])
    assert result.exit_code == 1 and not report.exists()
    assert "Rerun the same command to resume" in result.output


def test_model_override_needs_a_hosted_backend() -> None:
    result = CliRunner().invoke(app, ["eval", "--backend", "heuristic", "--model", "x"])
    assert result.exit_code != 0 and "--model needs" in result.output


def test_bundled_price_table_matches_the_dated_pricing_doc() -> None:
    table = tomllib.loads((ROOT / "src/chief_of_staff/pricing.toml").read_text())
    doc = (ROOT / "docs" / "pricing.md").read_text()
    assert table["as_of"] in doc
    for model, prices in list_prices().items():
        row = next(line for line in doc.splitlines() if f"`{model}`" in line)
        for price in prices:
            assert f"${price:.3f}".rstrip("0") in row, (model, price)
