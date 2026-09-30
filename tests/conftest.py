from __future__ import annotations

import gc
import sys
import warnings

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
        "NVIDIA_API_KEY",
        "COS_NVIDIA_API_KEY",
        "COS_BACKEND",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def offline_settings() -> Settings:
    return Settings(backend="heuristic", cache_enabled=False, trace_path=None, _env_file=None)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Fail the run if any test left a database or file unclosed."""
    leaks: list[str] = []
    previous_hook = sys.unraisablehook
    sys.unraisablehook = lambda unraisable: leaks.append(str(unraisable.exc_value))
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", ResourceWarning)
            gc.collect()
    finally:
        sys.unraisablehook = previous_hook
    if leaks:
        print(f"\n{len(leaks)} leaked resource(s): {leaks[0]}", file=sys.stderr)
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
