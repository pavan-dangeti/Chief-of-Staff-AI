## Evaluation: `test` split, backend `nvidia:deepseek-ai/deepseek-v4.1-flash`

80 examples, prompt v2.1.0, run 2026-09-29 20:28 UTC in 385.06s.

| Level | Precision | Recall | F1 | F1 95% CI | TP | FP | FN |
|---|---|---|---|---|---|---|---|
| Message (has any item) | 1.000 | 0.880 | **0.936** | [0.878, 0.978] | 44 | 0 | 6 |
| Item (one-to-one match) | 0.920 | 0.885 | **0.902** | [0.839, 0.951] | 46 | 4 | 6 |

| Field accuracy on matched items | Value |
|---|---|
| Kind (request / commitment / completion) | 100.0% |
| Owner (excl. completions) | 100.0% |
| Due date, exact day (excl. completions) | 90.0% |

| Operational | Value |
|---|---|
| Prefilter skip rate | 2.5% |
| Gold items lost to prefilter | 0 |
| Extraction failures | 0 |
| Answers from live calls / from cache | 78 / 0 |
| Latency p50 / p95, live calls only | 6404.9 / 32691.8 ms |
| Tokens in / out | 67,991 / 4,475 |
| Cost | $0.0258 |
| Provider call time p50 / p95 (78 timed answers) | 4621 / 26805 ms |
| Recorded tokens in / out, all answers | 67,991 / 4,475 |
| List-price estimate per 1,000 messages | $0.3221 (see docs/pricing.md) |

### Error analysis (10 examples, first 10)

- `t15` automated_action: expected 1, matched 0. Predicted: (none)
- `t24` owner,urgent: expected 1, matched 1. Predicted: [request] Rotate the exposed AWS key | owner=Divya | due=2026-09-23; [request] Check CloudTrail for misuse of the exposed key | owner=Divya | due=2026-09-23
- `t25` completion: expected 1, matched 0. Predicted: (none)
- `t39` completion: expected 1, matched 0. Predicted: (none)
- `t44` completion: expected 1, matched 0. Predicted: (none)
- `t47` completion: expected 1, matched 0. Predicted: (none)
- `t48` email,overdue: expected 1, matched 1. Predicted: [request] Process payment for invoice INV-2291 | owner=Ritu | due=None; [request] Share the remittance advice | owner=Ritu | due=None
- `t52` email,deadline: expected 1, matched 1. Predicted: [request] Confirm DevScale 2026 speaker slot | owner=Ananya | due=2026-09-28; [request] Send a short bio | owner=Ananya | due=None
- `t66` email,deadline: expected 1, matched 1. Predicted: [request] Send the vendor payment ledger | owner=Ritu | due=2026-10-10; [request] File the Q2 TDS return | owner=None | due=2026-10-31
- `t74` automated_action,deadline: expected 1, matched 0. Predicted: (none)
