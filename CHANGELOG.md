# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- NVIDIA API Catalog backend (any OpenAI-compatible chat completions endpoint), with its own
  model, escalation model, rate limit and request options; no extra install needed.
- Live comparison of four hosted models on the held-out test split. GLM 5.3 Flash scores item
  F1 0.981 (95% CI 0.950–1.000), Gemini 3.5 Flash-Lite 0.931, DeepSeek V4.1 Flash 0.902 and
  Nemotron 3 Super 0.863, against 0.848 for the offline rules. `cos compare` builds the table
  from saved reports.
- Provider call time and a list-price cost estimate per 1,000 messages in every evaluation
  report, from token counts recorded with each answer and a dated price table
  (`docs/pricing.md`).
- Resumable live evaluations: `cos eval --cache` keeps a per-run cache, answers keep their
  measured tokens and latency, and a run with failed messages writes no report.
- `benchmarks/latency_timeline.py` separates endpoint queueing from generation time.
- 30 externally written held-out examples (`datasets/eval/external.jsonl`), thread examples,
  deadline and priority attack types, and labelling rules for sender identity and attack success.

### Changed

- The NVIDIA backend defaults to GLM 5.3 Flash, and `auto` prefers it over Gemini.

### Fixed

- HTTP 429 and 5xx responses from httpx-based providers are now retried with `Retry-After`;
  their status code was previously not read.
- Evaluation latency no longer includes time spent waiting for the client-side rate limiter.

## [2.0.2] - 2026-09-27

### Added

- First live LLM evaluation: Gemini 3.5 Flash-Lite scores item F1 0.932 (95% CI 0.878–0.973)
  on the held-out test split, against 0.848 for the offline rules. The injection suite shows
  one successful suppression attack, documented in the README.
- Evaluation reports separate live calls from cached answers and compute latency from live
  calls only.

### Fixed

- `cos eval` now scores only the requested backend. Previously, if an LLM backend failed, the
  fallback chain could answer with the offline rules while the report still carried the LLM's
  name; failures are now counted instead of masked.
- A missing optional extra (`anthropic`, `gemini`, `graph`, `api`, `gmail`) now produces a
  one-line install hint and exit code 1 instead of a Python traceback. The message is printed
  unwrapped and unstyled so the `pip install` command can be copied as-is.

### Changed

- `ConfigurationError` lives in `chief_of_staff.errors`; `build_service(..., fallback=False)`
  pins the chain to the primary backend.
- Gemini requests disable automatic function calling, which the pipeline never uses, removing
  an SDK warning from every run.

## [2.0.1] - 2026-09-27

### Added

- Python 3.14 support, verified in CI alongside 3.11 to 3.13.
- `Ledger` and `ExtractionCache` are context managers; `ExtractionService.close()` releases the cache.

### Fixed

- SQLite connections are now closed deterministically by the CLI, the HTTP API (on shutdown)
  and the test suite. Python 3.13+ reported them as unclosed via `ResourceWarning`.
- The test suite fails on any leaked resource, so this cannot regress.

## [2.0.0] - 2026-09-27

A ground-up rebuild of the v1 prototype into an evaluated, production-ready pipeline.

### Added

- Claude and Gemini backends with schema-constrained output, a versioned prompt and one
  automatic repair attempt; low-confidence answers escalate to a stronger model.
- Verification layer: evidence quotes must be grounded in the source message, owners must be
  named, sender or recipient, and text addressed to an AI is discarded.
- Deterministic deadline resolution from the send time, including relative offsets, ordinal
  days, DMY/MDY dates and Hindi-English phrases.
- Explainable priority scoring outside the model, with per-company TOML overrides.
- Cross-message lifecycle: duplicates merged across Slack and email, completions close earlier
  tasks, and a SQLite ledger tracks commitments across runs.
- Resilience: token-bucket rate limiting, status-based retries honoring `Retry-After`, a
  circuit breaker, provider fallback and a content-addressed response cache.
- Reversible masking of PII and secrets before any API call.
- Ingestion from Slack exports, the Slack Web API, Gmail (read-only) and JSON/JSONL files.
- `cos` CLI (`run`, `eval`, `ledger`, `slack`, `gmail`, `serve`), an HTTP API with OpenAPI docs,
  a LangGraph orchestration with parity to the asyncio pipeline, and a Docker image.
- Evaluation harness: 165 labeled examples across dev, held-out test and prompt-injection
  splits, item-level metrics, bootstrap confidence intervals and Markdown reports.
- Production-style run against a fault-injecting provider simulator, a latency benchmark,
  CI on Python 3.11 to 3.13, and 277 tests at 97% coverage.

### Changed

- Reported accuracy now comes from a held-out test split scored once after tuning froze
  (item F1 0.848 for the offline rules), replacing v1's F1 1.00 measured on its tuning data.
- Keyword signals use word boundaries, so "product" no longer matches "prod" and "download"
  no longer matches "down".
- Messages are processed concurrently instead of sequentially with a fixed 1.5 s sleep:
  100 messages at 400 ms per call take 3.1 s instead of 190 s.

### Security

- Removed the real mailbox export that v1 shipped as sample data; all bundled data is synthetic.
- Private exports and OAuth credentials are git-ignored.

## [1.0.0]

- Initial prototype: LangGraph pipeline with a regex mock extractor and a 17-message test set.
