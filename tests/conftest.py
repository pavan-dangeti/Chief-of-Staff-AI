from __future__ import annotations

import pytest

from chief_of_staff.config import Settings


@pytest.fixture(autouse=True)
def _isolated_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
) -> None:
    """Keep real API keys and a developer's .env out of every test."""
    for name in (
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "COS_ANTHROPIC_API_KEY",
        "COS_GEMINI_API_KEY",
        "COS_BACKEND",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def offline_settings() -> Settings:
    return Settings(backend="heuristic", cache_enabled=False, trace_path=None, _env_file=None)
