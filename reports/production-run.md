## Production-style run

`chief-of-staff-ai` 2.0.0 installed from its wheel on Python 3.12.3; 183 messages (all dataset splits and the demo inbox). The real Anthropic SDK calls [`provider_simulator.py`](../benchmarks/provider_simulator.py) over HTTP with 350 ms mean latency, 8% HTTP 429 (`Retry-After: 1`), 2% HTTP 529 and 10% low-confidence answers, under a client-side limit of 1200 requests per minute. This measures the system around the model, not model quality.

| Scenario | Messages | Wall time | Model calls | Retries | Cache hits | Escalations | Fallbacks | Failed |
|---|---|---|---|---|---|---|---|---|
| Cold run with injected 429/529s | 183 | 8.0 s | 200 | 17 | 0 | 7 | 0 | 0 |
| Warm re-run of the same inbox | 183 | 1.3 s | 0 | 0 | 176 | 7 | 0 | 0 |
| Provider down, circuit breaker off | 32 | 44.8 s | 0 | 0 | 0 | 0 | 32 | 0 |
| Provider down, circuit breaker on | 32 | 2.2 s | 0 | 0 | 0 | 0 | 32 | 0 |

The simulator answered 200 requests: 14 with 429 and 3 with 529. Messages failed across all scenarios: 0. With the provider down, the circuit breaker cut the time to serve the same inbox from the offline fallback from 44.8 s to 2.2 s. Wall times include process start-up.

| `POST /v1/extract`, 32 concurrent clients | Requests | Errors | p50 | p95 | p99 | Throughput |
|---|---|---|---|---|---|---|
| Cold: every request reaches the provider | 183 | 0 | 888 ms | 2268 ms | 2769 ms | 17 req/s |
| Warm: same messages, served from cache | 183 | 0 | 59 ms | 71 ms | 75 ms | 500 req/s |

Evaluation parity on the test split: item F1 0.848 calling the rules directly and 0.848 through redaction, the SDK, HTTP, injected faults, retries, escalation and verification (identical).
