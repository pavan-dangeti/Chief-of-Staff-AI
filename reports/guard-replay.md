# Replay of saved model answers through the current code

Run on 2026-11-12, after the injection guard was narrowed to text addressed to an AI and the
sender-verification, redaction and ledger fixes landed.

**This is a replay, not a fresh run.** The answers each hosted model gave in the original live runs
(29 September to 1 October 2026, kept in the per-run response caches) were scored again by the
current verification and pipeline code. No provider was called: every answer below came from the
cache, and a cache miss would have failed the run. It shows what the code change does to the same
model output. It does not show how the models would answer today.

| Backend | Split | Answers replayed | Item F1, before → now | Attacks succeeded, before → now | Predicted items |
|---|---|---|---|---|---|
| Gemini 3.5 Flash-Lite | test | 78 | 0.931 → 0.931 | — → — | identical |
| Gemini 3.5 Flash-Lite | injection | 14 | 0.923 → 0.923 | 1 of 15 → 1 of 15 | identical |
| Gemini 3.5 Flash-Lite | external | 64 | 0.825 → 0.825 | 2 of 10 → 2 of 10 | identical |
| GLM 5.3 Flash | test | 78 | 0.981 → 0.981 | — → — | identical |
| GLM 5.3 Flash | injection | 14 | 0.875 → 0.875 | 0 of 15 → 0 of 15 | identical |
| GLM 5.3 Flash | external | 64 | 0.806 → 0.806 | 2 of 10 → 2 of 10 | identical |
| Nemotron 3 Super | test | 78 | 0.863 → 0.863 | — → — | identical |
| Nemotron 3 Super | injection | 14 | 1.000 → 1.000 | 0 of 15 → 0 of 15 | identical |
| Nemotron 3 Super | external | 64 | 0.931 → 0.931 | 1 of 10 → 1 of 10 | identical |
| DeepSeek V4.1 Flash | test | 78 | 0.902 → 0.902 | — → — | identical |
| DeepSeek V4.1 Flash | injection | 14 | 1.000 → 1.000 | 0 of 15 → 0 of 15 | identical |
| DeepSeek V4.1 Flash | external | no saved answers | | | |

Every score and every predicted item is unchanged, so the tables in the README stand. The
committed per-backend reports are left as the original live runs, because a replay records no
latency, token or cost figures.

Reproduce, with the run caches in `.cos/runs/`:

```bash
make eval-llm BACKEND=gemini TAG=gemini
make eval-llm BACKEND=nvidia MODEL=z-ai/glm-5.3-flash TAG=glm-5.3-flash
```

Delete a cache file first for a fresh, live run.
