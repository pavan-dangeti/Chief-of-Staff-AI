from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from chief_of_staff import __version__
from chief_of_staff.api import create_app
from chief_of_staff.cli import app
from chief_of_staff.config import Settings
from chief_of_staff.extraction.factory import ConfigurationError, build_service
from chief_of_staff.tracing import Tracer, cost_usd, percentile
from helpers import ROOT, FakeAnthropic, FakeGemini, make_message

SAMPLES = ROOT / "datasets" / "samples"
runner = CliRunner()


def cli(*args: str) -> str:
    result = runner.invoke(app, list(args))
    assert result.exit_code == 0, result.output
    return result.output


def test_cli_run_renders_table_json_and_markdown(tmp_path: Path) -> None:
    common = [
        "run",
        "--slack",
        str(SAMPLES / "slack.json"),
        "--email",
        str(SAMPLES / "email.json"),
        "--backend",
        "heuristic",
        "--no-cache",
    ]
    assert "Action items as of" in cli(*common)
    cli(*common, "--format", "json", "--output", str(tmp_path / "d.json"))
    assert json.loads((tmp_path / "d.json").read_text())["stats"]["messages_total"] == 18
    assert "**P0**" in cli(*common, "--format", "markdown")
    assert "Action items" in cli(*common, "--graph", "--format", "markdown")


def test_cli_run_updates_the_ledger(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.sqlite"
    output = cli(
        "run",
        "--slack",
        str(SAMPLES / "slack.json"),
        "--backend",
        "heuristic",
        "--ledger",
        str(ledger),
        "--format",
        "json",
    )
    assert "ledger: +" in output
    items = json.loads(
        cli("ledger", "show", "--path", str(ledger), "--status", "all", "--format", "json")
    )
    assert len(items) >= 5
    assert "owner=" in cli("ledger", "show", "--path", str(ledger))


def test_cli_slack_pull_writes_a_loadable_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from chief_of_staff.ingest.files import load_messages

    class FakeSlack:
        def __init__(self, token: str) -> None:
            assert token == "xoxb-test"

        def channel_messages(self, _channel_id: str, name: str, **_: float) -> list:  # type: ignore[type-arg]
            return [make_message(f"@Leo please check {name}", id=f"slack:{name}:1")]

    monkeypatch.setattr("chief_of_staff.cli.SlackClient", FakeSlack)
    out = tmp_path / "slack.json"
    assert runner.invoke(app, ["slack", "pull", "--channel", "C1:eng"]).exit_code != 0
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    cli("slack", "pull", "--channel", "C1:eng", "--channel", "C2", "--out", str(out))
    assert [m.id for m in load_messages(out)] == ["slack:eng:1", "slack:C2:1"]


def test_cli_eval_writes_reports(tmp_path: Path) -> None:
    cli(
        "eval",
        "--split",
        "injection",
        "--backend",
        "heuristic",
        "--bootstrap",
        "50",
        "--data-dir",
        str(ROOT / "datasets" / "eval"),
        "--report",
        str(tmp_path / "r.md"),
        "--json",
        str(tmp_path / "r.json"),
    )
    assert "attack success rate" in (tmp_path / "r.md").read_text()
    assert json.loads((tmp_path / "r.json").read_text())["examples"] == 15


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["run", "--backend", "heuristic"], "provide at least one"),
        (
            ["run", "--slack", str(SAMPLES / "slack.json"), "--backend", "anthropic"],
            "ANTHROPIC_API_KEY",
        ),
        (["ledger", "show", "--path", "missing.sqlite"], "no ledger"),
    ],
)
def test_cli_reports_usage_errors_cleanly(args: list[str], message: str) -> None:
    result = runner.invoke(app, args)
    assert result.exit_code != 0 and message in result.output


def test_api_endpoints(offline_settings: Settings) -> None:
    client = TestClient(create_app(offline_settings))
    assert client.get("/healthz").json() == {
        "status": "ok",
        "version": __version__,
        "backend": "heuristic:rules-v2",
    }
    message = make_message("@Leo please roll back the gateway asap, EU API is down")
    items = client.post("/v1/extract", json=json.loads(message.model_dump_json())).json()
    assert items[0]["owner"] == "Leo"
    body = {
        "messages": [json.loads(message.model_dump_json())],
        "as_of": "2026-09-14T12:00:00+00:00",
    }
    digest = client.post("/v1/digest", json=body).json()
    assert digest["open_items"][0]["priority"] == "P0"
    assert client.post("/v1/digest", json={"messages": []}).status_code == 422
    assert client.post("/v1/extract", json={"id": "x"}).status_code == 422


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({}, "heuristic"),
        ({"GEMINI_API_KEY": "g"}, "gemini"),
        ({"GOOGLE_API_KEY": "g"}, "gemini"),
        ({"ANTHROPIC_API_KEY": "a", "GEMINI_API_KEY": "g"}, "anthropic"),
        ({"ANTHROPIC_API_KEY": "a", "COS_BACKEND": "heuristic"}, "heuristic"),
    ],
)
def test_backend_auto_selection(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, str], expected: str
) -> None:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert Settings(_env_file=None).resolved_backend() == expected


def test_env_overrides_and_price_table(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COS_MAX_CONCURRENCY", "32")
    monkeypatch.setenv("COS_PRICES_PER_MTOK", '{"m": [1.0, 5.0]}')
    settings = Settings(_env_file=None)
    assert settings.max_concurrency == 32 and settings.prices_per_mtok == {"m": (1.0, 5.0)}


def test_factory_builds_fallback_chain_and_escalation() -> None:
    settings = Settings(
        backend="anthropic", cache_path=Path("c.sqlite"), trace_path=None, _env_file=None
    )
    service = build_service(
        settings, anthropic_client=FakeAnthropic(None), gemini_client=FakeGemini(None)
    )
    assert [b.label for b in service.chain] == [
        "anthropic:claude-haiku-4-5-20251001",
        "gemini:gemini-3.5-flash-lite",
        "heuristic:rules-v2",
    ]
    assert (
        service.escalation is not None and service.escalation.label == "anthropic:claude-sonnet-5"
    )
    assert service.cache is not None
    service.close()

    gemini = build_service(
        Settings(
            backend="gemini",
            fallback_to_heuristic=False,
            cache_enabled=False,
            trace_path=None,
            _env_file=None,
        ),
        gemini_client=FakeGemini(None),
    )
    assert [b.label for b in gemini.chain] == [
        "gemini:gemini-3.5-flash-lite"
    ] and gemini.escalation is None


def test_factory_offline_mode_needs_no_cache_and_missing_keys_fail_loudly() -> None:
    assert (
        build_service(Settings(backend="heuristic", trace_path=None, _env_file=None)).cache is None
    )
    with pytest.raises(ConfigurationError, match="GEMINI_API_KEY"):
        build_service(Settings(backend="gemini", _env_file=None))


def test_tracing_helpers_and_jsonl_sink(tmp_path: Path) -> None:
    assert (percentile([], 50), percentile([7.0], 95)) == (0.0, 7.0)
    assert percentile([float(v) for v in range(1, 101)], 95) == pytest.approx(95.05)
    assert cost_usd("unknown", 10, 10, {}) is None
    from chief_of_staff.tracing import TraceRecord

    tracer = Tracer(tmp_path / "t" / "traces.jsonl", run_id="r1")
    tracer.record(TraceRecord(run_id="r1", message_id="m1", input_tokens=5))
    line = json.loads((tmp_path / "t" / "traces.jsonl").read_text())
    assert (line["message_id"], line["input_tokens"]) == ("m1", 5)
