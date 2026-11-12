# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [2.3.0] - 2026-11-12

### Security

- PII in the sender, recipient and subject lines was sent to the model unmasked; only the body was
  redacted. Metadata is now masked with the body's placeholders.
- An unverified sender's message could still create items with `COS_PREFILTER=false` or through
  `POST /v1/extract`. The check now lives in the extraction service, so it holds on every path.
- Email sender verification read "dmarc=pass" anywhere in the Authentication-Results header. The
  header is now parsed with `authres` (RFC 8601), the result must name the From address's domain,
  and a pass is believed only from a trusted receiving server (`COS_TRUSTED_MAIL_SERVERS`). A
  property test compares the verdict with the reference parser on generated headers.
- Optional `COS_API_KEY`: when set, `/v1` routes require a bearer key.
- The Gmail OAuth token file is created with owner-only permissions; CI workflows declare
  read-only token permissions.

### Changed

- **New default backend order.** `auto` now prefers the providers evaluated live: NVIDIA, then
  Gemini, then Anthropic (it was Anthropic, NVIDIA, Gemini). With an Anthropic key and an NVIDIA
  or Gemini key both set, the default backend changes; set `COS_BACKEND=anthropic` to keep the old
  choice. The Anthropic backend is labelled as not verified against the live API.
- An email body cut at 4,000 characters ends in `[message truncated]`, is logged, and is counted
  in the digest (`messages_truncated`) and the table footer.
- GitHub Actions are pinned to commit SHAs.

### Added

- A `[people]` table in the priority policy gives roles to Slack user IDs and email addresses,
  applied only to senders the source system verified; `COS_POLICY_PATH` applies a policy to every command and the API.

### Fixed

- `cos run` and `cos eval` ignored `COS_BACKEND`: the `--backend` default of `auto` overrode it.
- Provider HTTP and SDK clients are closed on shutdown (CLI and API).
- The simulator benchmarks (`make production-run`, `make scale`) could call a real provider when a
  key was present in the shell or `.env`; they now blank those keys.
- The injection guard dropped ordinary tasks that mention an AI ("ship the AI agent demo", "send
  the offer letter to the assistant"). It now matches text addressed to one.
- The ledger reopened a closed item when a later run saw the task again without its completion,
  and lost its links to merged messages.
- `cos ledger show` listed items with no due date before dated ones, and crashed on an unknown
  `--status`.
- mbox threads: the first message and deeper replies now share one thread id.
- A Gmail message without a usable `Date` header no longer aborts the pull.
- The pilot notice and privacy note said names are masked before a hosted model sees them; they
  are not, and the text now says so.

## [2.2.0] - 2026-10-01

### Added

- Evaluation of conversations and priority attacks through the full pipeline, with per-category
  and per-author scores; results for four backends on the externally written set, before and
  after the defences below (`cos compare --external`).
- Sender verification from the source system: Slack user IDs missing from the workspace directory
  and mail failing DMARC mark a sender unverified, and such messages create nothing.
- A commitment someone else claims for a person ("Eli agreed to...") is dropped; the injection
  guard also catches "the assistant must..." and notes addressed to an assistant or bot.
- A 10,000-message scale run (`make scale`) and `docs/design.md`.

### Fixed

- Syncing the same digest into the ledger twice could add an item the second time.
- Duplicate detection re-tokenised both items for every compared pair; features are now computed
  once per item, with the same matching rules.
- `cos eval --json` reports now end with a newline, so regenerated reports pass the end-of-file
  check.

### Changed

- The pilot install line installs v2.2.0, which includes the manipulation defences.

## [2.1.0] - 2026-09-30

### Added

- Public demo on GitHub Pages (`docs/build_site.py`, deployed by the Demo site workflow):
  the sample inbox beside the digest the offline rules make from it, each message labelled with
  what happened to it, the backend comparison table, and a copy of the pilot review page.
- Real-user pilot kit: `cos pilot run` builds a self-contained review page from a participant's
  own Slack export, mbox or JSON (offline rules by default, the last 14 days); the page saves a
  label file with no message text; `cos pilot report` combines the files into precision, a
  recall estimate and per-participant rows with Wilson intervals. Participant guide and privacy
  and consent note in `docs/`.
- mbox import (for example Gmail Takeout), also available as `cos run --mbox`.
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
