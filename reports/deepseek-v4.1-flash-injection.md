## Evaluation: `injection` split, backend `nvidia:deepseek-ai/deepseek-v4.1-flash`

15 examples, prompt v2.1.0, run 2026-09-29 20:28 UTC in 40.42s.

| Level | Precision | Recall | F1 | F1 95% CI | TP | FP | FN |
|---|---|---|---|---|---|---|---|
| Message (has any item) | 1.000 | 1.000 | **1.000** | [1.000, 1.000] | 7 | 0 | 0 |
| Item (one-to-one match) | 1.000 | 1.000 | **1.000** | [1.000, 1.000] | 7 | 0 | 0 |

| Field accuracy on matched items | Value |
|---|---|
| Kind (request / commitment / completion) | 100.0% |
| Owner (excl. completions) | 100.0% |
| Due date, exact day (excl. completions) | 100.0% |

| Operational | Value |
|---|---|
| Prefilter skip rate | 6.7% |
| Gold items lost to prefilter | 0 |
| Extraction failures | 0 |
| Answers from live calls / from cache | 14 / 0 |
| Latency p50 / p95, live calls only | 5307.2 / 11262.3 ms |
| Tokens in / out | 12,422 / 625 |
| Cost | $0.0045 |
| Provider call time p50 / p95 (14 timed answers) | 2215 / 6958 ms |
| Recorded tokens in / out, all answers | 12,422 / 625 |
| List-price estimate per 1,000 messages | $0.2985 (see docs/pricing.md) |
| Prompt-injection attack success rate | 0.0% |
