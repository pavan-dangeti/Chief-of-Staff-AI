| Scenario (100 messages, 400 ms per model call) | Wall time |
|---|---|
| v1 sequential loop + 1.5 s sleep (modelled) | 190.0 s |
| v2 concurrent, cold cache (concurrency 16) | 3.06 s |
| v2 re-run, warm cache | 160 ms |

Speed-up cold: 62x, warm: 1190x
