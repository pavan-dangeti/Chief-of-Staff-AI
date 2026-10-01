"""Runtime configuration, loaded from environment variables (prefix ``COS_``) or ``.env``."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BackendName = Literal["auto", "heuristic", "anthropic", "gemini", "nvidia"]


def list_prices() -> dict[str, tuple[float, float]]:
    """Dated list prices bundled with the package (see docs/pricing.md)."""
    table = tomllib.loads((Path(__file__).parent / "pricing.toml").read_text(encoding="utf-8"))
    return {model: (row["input"], row["output"]) for model, row in table["models"].items()}


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

    nvidia_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("COS_NVIDIA_API_KEY", "NVIDIA_API_KEY")
    )
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    # Highest held-out recall in reports/comparison.md; see the README for the external set.
    nvidia_model: str = "z-ai/glm-5.3-flash"
    nvidia_escalation_model: str | None = None
    # Free keys are shared and rate limited; stay well under the catalog's per-key limit.
    nvidia_rpm: float = 20.0
    # Extraction does not need chain-of-thought: switching it off cuts tokens and latency.
    # Each chat template reads its own key and ignores the other.
    nvidia_extra_body: dict[str, Any] = Field(
        default_factory=lambda: {
            "chat_template_kwargs": {"thinking": False, "enable_thinking": False}
        }
    )

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

    prices_per_mtok: dict[str, tuple[float, float]] = Field(default_factory=list_prices)

    def resolved_backend(self) -> Literal["heuristic", "anthropic", "gemini", "nvidia"]:
        if self.backend != "auto":
            return self.backend
        if self.anthropic_api_key:
            return "anthropic"
        if self.nvidia_api_key:
            return "nvidia"
        if self.gemini_api_key:
            return "gemini"
        return "heuristic"
