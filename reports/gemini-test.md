## Evaluation: `test` split, backend `gemini:gemini-3.5-flash-lite`

80 examples, prompt v2.1.0, run 2026-09-27 11:41 UTC in 0.05s.

| Level | Precision | Recall | F1 | F1 95% CI | TP | FP | FN |
|---|---|---|---|---|---|---|---|
| Message (has any item) | 1.000 | 0.920 | **0.958** | [0.909, 0.990] | 46 | 0 | 4 |
| Item (one-to-one match) | 0.941 | 0.923 | **0.932** | [0.878, 0.973] | 48 | 3 | 4 |

| Field accuracy on matched items | Value |
|---|---|
| Kind (request / commitment / completion) | 100.0% |
| Owner (excl. completions) | 95.0% |
| Due date, exact day (excl. completions) | 92.5% |

| Operational | Value |
|---|---|
| Prefilter skip rate | 2.5% |
| Gold items lost to prefilter | 0 |
| Extraction failures | 0 |
| Answers from live calls / from cache | 0 / 78 |
| Latency p50 / p95, live calls only | n/a (all answers cached) |
| Tokens in / out | 0 / 0 |
| Cost | n/a |

### Error analysis (7 examples, first 7)

- `t15` automated_action: expected 1, matched 0. Predicted: (none)
- `t24` owner,urgent: expected 1, matched 1. Predicted: [request] Rotate the exposed AWS key | owner=Divya | due=2026-09-23; [request] Check CloudTrail for misuse | owner=Divya | due=None
- `t25` completion: expected 1, matched 0. Predicted: (none)
- `t39` completion: expected 1, matched 0. Predicted: (none)
- `t48` email,overdue: expected 1, matched 1. Predicted: [request] Process payment for invoice INV-2291 | owner=Ritu | due=None; [request] Share the remittance advice for invoice INV-2291 | owner=Ritu | due=None
- `t52` email,deadline: expected 1, matched 1. Predicted: [request] Confirm speaker slot for DevScale 2026 | owner=Ananya | due=2026-09-28; [request] Send a short bio | owner=Ananya | due=None
- `t74` automated_action,deadline: expected 1, matched 0. Predicted: (none)
