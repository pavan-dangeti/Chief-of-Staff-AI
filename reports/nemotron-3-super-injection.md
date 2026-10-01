## Evaluation: `injection` split, backend `nvidia:nvidia/nemotron-3-super-120b-a12b`

15 examples (15 messages, extraction mode), prompt v2.1.0, run 2026-10-01 11:27 UTC in 0.01s.

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
| Answers from live calls / from cache | 0 / 14 |
| Latency p50 / p95, live calls only | n/a (all answers cached) |
| Tokens in / out | 0 / 0 |
| Cost | $0.0000 |
| Provider call time p50 / p95 (14 timed answers) | 1078 / 3278 ms |
| Recorded tokens in / out, all answers | 13,288 / 771 |
| List-price estimate per 1,000 messages | $0.0959 (see docs/pricing.md) |
| Prompt-injection attack success rate | 0.0% |
