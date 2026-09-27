"""Runtime configuration, loaded from environment variables (prefix ``COS_``) or ``.env``."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BackendName = Literal["auto", "heuristic", "anthropic", "gemini"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="COS_", env_file=".env", extra="ignore")

    backend: BackendName = "auto"

    anthropic_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("COS_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY")
    )
    gemini_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("COS_GEMINI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"),
    )

    anthropic_model: str = "claude-haiku-4-5-20251001"
    anthropic_escalation_model: str | None = "claude-sonnet-5"
    anthropic_rpm: float = 50.0

    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_escalation_model: str | None = None
    gemini_temperature: float | None = None
    gemini_rpm: float = 15.0

    max_concurrency: int = Field(default=8, ge=1)
    max_retries: int = Field(default=5, ge=0)
    circuit_failure_threshold: int = Field(default=5, ge=1)
    circuit_reset_s: float = Field(default=30.0, gt=0)
    request_timeout_s: float = Field(default=45.0, gt=0)
    escalation_threshold: float = Field(default=0.55, ge=0, le=1)
    review_threshold: float = Field(default=0.6, ge=0, le=1)
    fallback_to_heuristic: bool = True

    redact_pii: bool = True
    prefilter: bool = True
    date_order: Literal["DMY", "MDY"] = "DMY"

    cache_enabled: bool = True
    cache_path: Path = Path(".cos/cache.sqlite")
    trace_path: Path | None = Path(".cos/traces.jsonl")

    prices_per_mtok: dict[str, tuple[float, float]] = Field(default_factory=dict)

    def resolved_backend(self) -> Literal["heuristic", "anthropic", "gemini"]:
        if self.backend != "auto":
            return self.backend
        if self.anthropic_api_key:
            return "anthropic"
        if self.gemini_api_key:
            return "gemini"
        return "heuristic"
