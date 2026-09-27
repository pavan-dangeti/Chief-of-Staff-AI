"""Build an :class:`ExtractionService` from :class:`Settings`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from chief_of_staff.config import Settings
from chief_of_staff.extraction.anthropic_backend import AnthropicExtractor, create_anthropic_client
from chief_of_staff.extraction.cache import ExtractionCache
from chief_of_staff.extraction.gemini_backend import GeminiExtractor, create_gemini_client
from chief_of_staff.extraction.heuristic import HeuristicExtractor
from chief_of_staff.extraction.resilience import CircuitBreaker, RateLimiter, RetryPolicy
from chief_of_staff.extraction.service import Backend, ExtractionService
from chief_of_staff.prioritization import Prioritizer, PriorityPolicy
from chief_of_staff.redaction import NoopRedactor, Redactor
from chief_of_staff.tracing import Tracer


class ConfigurationError(RuntimeError):
    pass


def _remote(extractor: Any, rpm: float, settings: Settings) -> Backend:
    return Backend(
        extractor=extractor,
        limiter=RateLimiter(rpm),
        retry=RetryPolicy(max_retries=settings.max_retries),
        breaker=CircuitBreaker(settings.circuit_failure_threshold, settings.circuit_reset_s),
    )


def build_service(
    settings: Settings,
    *,
    anthropic_client: Any = None,
    gemini_client: Any = None,
    tracer: Tracer | None = None,
) -> ExtractionService:
    primary = settings.resolved_backend()
    anthropic_key = (
        settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
    )
    gemini_key = settings.gemini_api_key.get_secret_value() if settings.gemini_api_key else None

    def anthropic_backend(model: str) -> Backend:
        client = anthropic_client
        if client is None:
            if anthropic_key is None:
                raise ConfigurationError("backend 'anthropic' needs ANTHROPIC_API_KEY")
            client = create_anthropic_client(anthropic_key, settings.request_timeout_s)
        extractor = AnthropicExtractor(client, model)
        return _remote(extractor, settings.anthropic_rpm, settings)

    def gemini_backend(model: str) -> Backend:
        client = gemini_client
        if client is None:
            if gemini_key is None:
                raise ConfigurationError("backend 'gemini' needs GEMINI_API_KEY")
            client = create_gemini_client(gemini_key, settings.request_timeout_s)
        extractor = GeminiExtractor(client, model, temperature=settings.gemini_temperature)
        return _remote(extractor, settings.gemini_rpm, settings)

    has_anthropic = anthropic_client is not None or anthropic_key is not None
    has_gemini = gemini_client is not None or gemini_key is not None

    chain: list[Backend] = []
    escalation: Backend | None = None
    if primary == "anthropic":
        chain.append(anthropic_backend(settings.anthropic_model))
        if settings.anthropic_escalation_model:
            escalation = anthropic_backend(settings.anthropic_escalation_model)
        if has_gemini:
            chain.append(gemini_backend(settings.gemini_model))
    elif primary == "gemini":
        chain.append(gemini_backend(settings.gemini_model))
        if settings.gemini_escalation_model:
            escalation = gemini_backend(settings.gemini_escalation_model)
        if has_anthropic:
            chain.append(anthropic_backend(settings.anthropic_model))
    if primary == "heuristic" or settings.fallback_to_heuristic:
        chain.append(Backend(extractor=HeuristicExtractor(), cacheable=False, remote=False))

    needs_cache = settings.cache_enabled and any(backend.remote for backend in chain)
    cache = ExtractionCache(settings.cache_path) if needs_cache else None
    return ExtractionService(
        chain=chain,
        escalation=escalation,
        cache=cache,
        tracer=tracer or Tracer(settings.trace_path),
        redactor=Redactor() if settings.redact_pii else NoopRedactor(),
        max_concurrency=settings.max_concurrency,
        escalation_threshold=settings.escalation_threshold,
        date_order=settings.date_order,
        prices=settings.prices_per_mtok,
    )


def build_prioritizer(settings: Settings, policy_path: Path | None = None) -> Prioritizer:
    if policy_path is not None:
        return Prioritizer(PriorityPolicy.from_toml(policy_path))
    return Prioritizer(PriorityPolicy(review_threshold=settings.review_threshold))
