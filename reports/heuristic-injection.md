## Evaluation: `injection` split, backend `heuristic:rules-v2`

15 examples, prompt v2.1.0, run 2026-09-26 23:51 UTC in 0.04s.

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
| Latency p50 / p95 | 0.4 / 0.6 ms |
| Tokens in / out | 0 / 0 |
| Cost | n/a |
| Prompt-injection attack success rate | 0.0% |
