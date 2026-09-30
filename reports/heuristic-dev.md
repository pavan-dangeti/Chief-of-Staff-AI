## Evaluation: `dev` split, backend `heuristic:rules-v2`

70 examples, prompt v2.1.0, run 2026-09-29 20:39 UTC in 0.07s.

| Level | Precision | Recall | F1 | F1 95% CI | TP | FP | FN |
|---|---|---|---|---|---|---|---|
| Message (has any item) | 0.978 | 1.000 | **0.989** | [0.962, 1.000] | 44 | 1 | 0 |
| Item (one-to-one match) | 0.979 | 0.979 | **0.979** | [0.942, 1.000] | 46 | 1 | 1 |

| Field accuracy on matched items | Value |
|---|---|
| Kind (request / commitment / completion) | 100.0% |
| Owner (excl. completions) | 100.0% |
| Due date, exact day (excl. completions) | 100.0% |

| Operational | Value |
|---|---|
| Prefilter skip rate | 2.9% |
| Gold items lost to prefilter | 0 |
| Extraction failures | 0 |
| Answers from live calls / from cache | 68 / 0 |
| Latency p50 / p95, live calls only | 0.1 / 0.2 ms |
| Tokens in / out | 0 / 0 |
| Cost | n/a |
| Provider call time p50 / p95 (0 timed answers) | n/a |
| Recorded tokens in / out, all answers | 0 / 0 |
| List-price estimate per 1,000 messages | n/a (no price configured) |

### Error analysis (2 examples, first 2)

- `d25` multi_item,completion: expected 2, matched 1. Predicted: [request] Postmortem for the login incident is up in the wiki, pls review when you get a chance | owner=None | due=None
- `d69` negative,chatter,hard: expected 0, matched 0. Predicted: [request] Guys stop leaving dishes in the sink 🙃 | owner=None | due=None
