## Evaluation: `test` split, backend `nvidia:z-ai/glm-5.3-flash`

80 examples, prompt v2.1.0, run 2026-09-29 20:50 UTC in 998.55s.

| Level | Precision | Recall | F1 | F1 95% CI | TP | FP | FN |
|---|---|---|---|---|---|---|---|
| Message (has any item) | 1.000 | 0.980 | **0.990** | [0.968, 1.000] | 49 | 0 | 1 |
| Item (one-to-one match) | 0.981 | 0.981 | **0.981** | [0.950, 1.000] | 51 | 1 | 1 |

| Field accuracy on matched items | Value |
|---|---|
| Kind (request / commitment / completion) | 100.0% |
| Owner (excl. completions) | 100.0% |
| Due date, exact day (excl. completions) | 95.1% |

| Operational | Value |
|---|---|
| Prefilter skip rate | 2.5% |
| Gold items lost to prefilter | 0 |
| Extraction failures | 0 |
| Answers from live calls / from cache | 78 / 0 |
| Latency p50 / p95, live calls only | 10253.1 / 28702.3 ms |
| Tokens in / out | 67,815 / 4,510 |
| Cost | $0.0124 |
| Provider call time p50 / p95 (78 timed answers) | 10251 / 28699 ms |
| Recorded tokens in / out, all answers | 67,815 / 4,510 |
| List-price estimate per 1,000 messages | $0.1554 (see docs/pricing.md) |

### Error analysis (2 examples, first 2)

- `t24` owner,urgent: expected 1, matched 1. Predicted: [request] Rotate the exposed AWS key | owner=Divya | due=2026-09-23; [request] Check CloudTrail for misuse of the exposed key | owner=Divya | due=None
- `t74` automated_action,deadline: expected 1, matched 0. Predicted: (none)
