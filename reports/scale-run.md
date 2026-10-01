## Scale run

chief-of-staff-ai 2.1.0, Python 3.12.13, Darwin arm64, 10 CPUs. Corpus: the 183 synthetic dataset messages repeated with unique ids, one minute apart (repetitive text, so many items merge: a deduplication stress test).

### Offline pipeline (rules, in process)

| Messages | Wall time | Messages/s | Items before dedupe | Open items | Merged | Peak memory |
|---|---|---|---|---|---|---|
| 1,000 | 0.3 s | 3,176 | 594 | 84 | 409 | 57 MiB |
| 2,500 | 1.3 s | 1,994 | 1,474 | 84 | 1,148 | 69 MiB |
| 5,000 | 4.3 s | 1,175 | 2,954 | 96 | 2,384 | 88 MiB |
| 10,000 | 15.8 s | 633 | 5,902 | 112 | 4,849 | 125 MiB |

Peak memory is the process maximum so far, so each row includes the rows above it. Deduplication compares every pair of items, so time grows with the square of the item count.

### Ledger (SQLite) for the 10,000-message digest

- First sync: 123 added in 0.82 s.
- Repeat sync of the same digest: 0 added, 124 updated in 0.65 s.

### 10,000 messages through the hosted-model path

Installed `cos` CLI, real Anthropic SDK over HTTP, provider simulator with 350 ms latency, 8% HTTP 429 and 2% HTTP 529, 64 messages in flight. The simulator answers with the rules engine, so this measures the system around the model, not model quality.

| Wall time | Messages/s | Model calls | Retries | Failed | Faults injected | Call p50 / p95 | CLI peak memory |
|---|---|---|---|---|---|---|---|
| 97 s | 103 | 11,280 | 1,112 | 0 | 897 × 429, 215 × 529 | 363 / 591 ms | 197 MiB |
