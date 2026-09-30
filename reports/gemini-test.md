## Evaluation: `test` split, backend `gemini:gemini-3.5-flash-lite`

80 examples, prompt v2.1.0, run 2026-09-29 20:59 UTC in 305.93s.

| Level | Precision | Recall | F1 | F1 95% CI | TP | FP | FN |
|---|---|---|---|---|---|---|---|
| Message (has any item) | 1.000 | 0.900 | **0.947** | [0.892, 0.989] | 45 | 0 | 5 |
| Item (one-to-one match) | 0.959 | 0.904 | **0.931** | [0.875, 0.973] | 47 | 2 | 5 |

| Field accuracy on matched items | Value |
|---|---|
| Kind (request / commitment / completion) | 100.0% |
| Owner (excl. completions) | 97.4% |
| Due date, exact day (excl. completions) | 94.9% |

| Operational | Value |
|---|---|
| Prefilter skip rate | 2.5% |
| Gold items lost to prefilter | 0 |
| Extraction failures | 0 |
| Answers from live calls / from cache | 78 / 0 |
| Latency p50 / p95, live calls only | 7982.7 / 10370.1 ms |
| Tokens in / out | 74,015 / 5,469 |
| Cost | $0.0359 |
| Provider call time p50 / p95 (78 timed answers) | 1242 / 5898 ms |
| Recorded tokens in / out, all answers | 74,015 / 5,469 |
| List-price estimate per 1,000 messages | $0.4485 (see docs/pricing.md) |

### Error analysis (7 examples, first 7)

- `t15` automated_action: expected 1, matched 0. Predicted: (none)
- `t23` owner,implicit: expected 1, matched 0. Predicted: (none)
- `t24` owner,urgent: expected 1, matched 1. Predicted: [request] Rotate the exposed AWS key | owner=Divya | due=None; [request] Check CloudTrail for misuse | owner=Divya | due=None
- `t25` completion: expected 1, matched 0. Predicted: (none)
- `t39` completion: expected 1, matched 0. Predicted: (none)
- `t48` email,overdue: expected 1, matched 1. Predicted: [request] Process payment for invoice INV-2291 | owner=Ritu | due=None; [request] Share the remittance advice for invoice INV-2291 | owner=Ritu | due=None
- `t74` automated_action,deadline: expected 1, matched 0. Predicted: (none)
