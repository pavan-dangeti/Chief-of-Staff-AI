## Evaluation: `test` split, backend `nvidia:nvidia/nemotron-3-super-120b-a12b`

80 examples, prompt v2.1.0, run 2026-09-29 20:33 UTC in 250.33s.

| Level | Precision | Recall | F1 | F1 95% CI | TP | FP | FN |
|---|---|---|---|---|---|---|---|
| Message (has any item) | 1.000 | 0.780 | **0.876** | [0.800, 0.943] | 39 | 0 | 11 |
| Item (one-to-one match) | 0.954 | 0.788 | **0.863** | [0.786, 0.927] | 41 | 2 | 11 |

| Field accuracy on matched items | Value |
|---|---|
| Kind (request / commitment / completion) | 100.0% |
| Owner (excl. completions) | 97.4% |
| Due date, exact day (excl. completions) | 92.3% |

| Operational | Value |
|---|---|
| Prefilter skip rate | 2.5% |
| Gold items lost to prefilter | 0 |
| Extraction failures | 0 |
| Answers from live calls / from cache | 78 / 0 |
| Latency p50 / p95, live calls only | 5934.6 / 12159.4 ms |
| Tokens in / out | 72,773 / 4,209 |
| Cost | $0.0079 |
| Provider call time p50 / p95 (78 timed answers) | 924 / 3184 ms |
| Recorded tokens in / out, all answers | 72,773 / 4,209 |
| List-price estimate per 1,000 messages | $0.0984 (see docs/pricing.md) |

### Error analysis (13 examples, first 13)

- `t11` completion: expected 1, matched 0. Predicted: (none)
- `t15` automated_action: expected 1, matched 0. Predicted: (none)
- `t24` owner,urgent: expected 1, matched 1. Predicted: [request] Rotate the exposed AWS key | owner=Divya | due=2026-09-23; [request] Check CloudTrail for misuse of the exposed AWS key | owner=Divya | due=2026-09-23
- `t25` completion: expected 1, matched 0. Predicted: (none)
- `t32` code_mixed,completion: expected 1, matched 0. Predicted: (none)
- `t39` completion: expected 1, matched 0. Predicted: (none)
- `t44` completion: expected 1, matched 0. Predicted: (none)
- `t46` commitment: expected 1, matched 0. Predicted: (none)
- `t47` completion: expected 1, matched 0. Predicted: (none)
- `t52` email,deadline: expected 1, matched 1. Predicted: [request] Confirm speaking slot for DevScale 2026 | owner=Ananya | due=2026-09-28; [request] Send a short bio for DevScale 2026 | owner=Ananya | due=2026-09-28
- `t62` completion: expected 1, matched 0. Predicted: (none)
- `t69` completion: expected 1, matched 0. Predicted: (none)
- `t74` automated_action,deadline: expected 1, matched 0. Predicted: (none)
