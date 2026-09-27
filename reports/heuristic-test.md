## Evaluation: `test` split, backend `heuristic:rules-v2`

80 examples, prompt v2.1.0, run 2026-09-27 11:41 UTC in 0.06s.

| Level | Precision | Recall | F1 | F1 95% CI | TP | FP | FN |
|---|---|---|---|---|---|---|---|
| Message (has any item) | 1.000 | 0.780 | **0.876** | [0.795, 0.940] | 39 | 0 | 11 |
| Item (one-to-one match) | 0.975 | 0.750 | **0.848** | [0.769, 0.913] | 39 | 1 | 13 |

| Field accuracy on matched items | Value |
|---|---|
| Kind (request / commitment / completion) | 100.0% |
| Owner (excl. completions) | 96.8% |
| Due date, exact day (excl. completions) | 90.3% |

| Operational | Value |
|---|---|
| Prefilter skip rate | 2.5% |
| Gold items lost to prefilter | 0 |
| Extraction failures | 0 |
| Answers from live calls / from cache | 78 / 0 |
| Latency p50 / p95, live calls only | 0.1 / 0.2 ms |
| Tokens in / out | 0 / 0 |
| Cost | n/a |

### Error analysis (14 examples, first 14)

- `t04` commitment: expected 1, matched 0. Predicted: (none)
- `t13` owner,deadline: expected 1, matched 0. Predicted: (none)
- `t23` owner,implicit: expected 1, matched 0. Predicted: (none)
- `t25` completion: expected 1, matched 0. Predicted: (none)
- `t34` code_mixed,owner,deadline: expected 1, matched 0. Predicted: (none)
- `t36` owner,deadline: expected 1, matched 0. Predicted: (none)
- `t37` multi_item,commitment: expected 2, matched 1. Predicted: [commitment] Nikhil will take the Helix sync issue; I'll update the customer by EOD | owner=Nikhil | due=2026-09-24
- `t39` completion: expected 1, matched 0. Predicted: (none)
- `t46` commitment: expected 1, matched 0. Predicted: (none)
- `t51` commitment,deadline: expected 1, matched 0. Predicted: (none)
- `t57` commitment,hard: expected 1, matched 0. Predicted: (none)
- `t60` multi_item,owner: expected 2, matched 1. Predicted: [request] For tomorrow: Divya please pair with Nikhil on the Helix sync fix, Amit keep the status page updated | owner=None | due=2026-09-24
- `t66` email,deadline: expected 1, matched 1. Predicted: [request] Ritu, the TDS return for Q2 must be filed by 31 October | owner=Ritu | due=2026-10-31; [request] Send the vendor payment ledger by 10th October so we have time to prepare it (re: Ritu, the TDS return for Q2 must be filed by 31 October) | owner=Ritu | due=2026-10-10
- `t74` automated_action,deadline: expected 1, matched 0. Predicted: (none)
