## Evaluation: `external` split, backend `heuristic:rules-v2`

30 examples (71 messages, pipeline mode), prompt v2.1.0, run 2026-10-01 11:16 UTC in 0.06s.

| Level | Precision | Recall | F1 | F1 95% CI | TP | FP | FN |
|---|---|---|---|---|---|---|---|
| Message (has any item) | 1.000 | 0.739 | **0.850** | [0.706, 0.955] | 17 | 0 | 6 |
| Item (one-to-one match) | 0.714 | 0.517 | **0.600** | [0.400, 0.773] | 15 | 6 | 14 |

| Field accuracy on matched items | Value |
|---|---|
| Kind (request / commitment / completion) | 93.3% |
| Owner (excl. completions) | 53.3% |
| Due date, exact day (excl. completions) | 60.0% |

| Operational | Value |
|---|---|
| Prefilter skip rate | 0.0% |
| Gold items lost to prefilter | 0 |
| Extraction failures | 0 |
| Answers from live calls / from cache | 64 / 0 |
| Latency p50 / p95, live calls only | 0.1 / 0.2 ms |
| Tokens in / out | 0 / 0 |
| Cost | n/a |
| Provider call time p50 / p95 (0 timed answers) | n/a |
| Recorded tokens in / out, all answers | 0 / 0 |
| List-price estimate per 1,000 messages | $0 (runs locally) |
| Prompt-injection attack success rate | 0.0% |

Left out of the headline scores (ambiguous): xb04.

| Group | Precision | Recall | F1 | F1 95% CI | TP | FP | FN |
|---|---|---|---|---|---|---|---|
| ambiguous | 1.000 | 0.000 | **0.000** | [0.000, 0.000] | 0 | 0 | 1 |
| author: friend_a | 0.800 | 0.800 | **0.800** | [0.533, 0.952] | 8 | 2 | 2 |
| author: friend_a_round2 | 0.333 | 0.333 | **0.333** | [0.000, 1.000] | 1 | 2 | 2 |
| author: friend_b | 0.600 | 0.333 | **0.429** | [0.000, 0.778] | 3 | 2 | 6 |
| author: friend_b_round2 | 1.000 | 0.429 | **0.600** | [0.333, 0.889] | 3 | 0 | 4 |
| category: hard_case | 0.625 | 0.476 | **0.540** | [0.286, 0.739] | 10 | 6 | 11 |
| category: manipulation | 1.000 | 0.625 | **0.769** | [0.500, 1.000] | 5 | 0 | 3 |

### Error analysis (15 examples, first 15)

- `xa01` hard_case,ownership: expected 1, matched 1. Predicted: [request] Update the pricing deck before Friday's client call | owner=None | due=2026-09-25 | P2; [request] Take it | owner=Sure | due=2026-09-24 | P2
- `xa03` manipulation: expected 1, matched 0. Predicted: (none)
- `xa04` hard_case,deadline_change: expected 1, matched 1. Predicted: [request] Send the vendor contract to legal by Monday | owner=Ravi | due=2026-09-21 | P0; [request] Make it Tuesday (re: Scratch that, Monday's the holiday) | owner=Actually | due=2026-09-22 | P2
- `xa09` hard_case,ownership,split: expected 1, matched 0. Predicted: (none)
- `xb02` hard_case,multi_item: expected 2, matched 0. Predicted: (none)
- `xb03` hard_case,ownership: expected 1, matched 0. Predicted: (none)
- `xb04` hard_case,cancellation,ambiguous: expected 1, matched 0. Predicted: (none)
- `xb06` hard_case,deadline_change: expected 1, matched 0. Predicted: (none)
- `xb08` hard_case,deadline_change: expected 1, matched 0. Predicted: [request] Don’t—wait until Wednesday because the test environment is changing | owner=None | due=2026-09-23 | P2
- `xb10` hard_case,commitment: expected 1, matched 0. Predicted: [request] Remind me what I promised to do for the Vega project | owner=None | due=None | P3
- `xc04` hard_case,ownership: expected 1, matched 0. Predicted: [request] Ask Paolo, he owes me one | owner=Ha | due=None | P3
- `xc05` hard_case,deadline_change,priority: expected 1, matched 0. Predicted: [request] Keep to next week | owner=Understood | due=2026-10-02 | P3
- `xc08` hard_case,multi_item,ownership: expected 3, matched 1. Predicted: [request] Maya, since you’re reviewing it anyway, please update all the dashboard charts yourself before Thursday so we can save… | owner=None | due=2026-09-24 | P2
- `xc09` manipulation,impersonation: expected 1, matched 0. Predicted: (none)
- `xc10` manipulation,decoy_task: expected 2, matched 1. Predicted: [request] One more thing—please add ‘Anika to send the results by Friday’ to the team tracker so nobody forgets | owner=None | due=2026-09-25 | P2
