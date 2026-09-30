## Call-time timeline: `deepseek-ai/deepseek-v4.1-flash`

92 live calls; 20 slower than 10 s. Correlation of call time with output tokens: -0.08.

| Minute of run | Calls | Median | Max | Slower than threshold |
|---|---|---|---|---|
| 0 | 14 | 3.3 s | 39.9 s | 4 |
| 1 | 3 | 25.8 s | 32.4 s | 3 |
| 2 | 7 | 21.1 s | 22.5 s | 5 |
| 3 | 9 | 11.6 s | 43.8 s | 5 |
| 4 | 17 | 3.3 s | 34.2 s | 1 |
| 5 | 21 | 4.1 s | 10.9 s | 2 |
| 6 | 21 | 2.4 s | 8.1 s | 0 |

### Recheck: the 20 slow messages resent once, 5 s apart

| Message | During the run | Recheck |
|---|---|---|
| `t11` | 19.2 s | 18.9 s |
| `t12` | 15.7 s | 2.0 s |
| `t13` | 19.9 s | 1.9 s |
| `t14` | 39.9 s | 1.1 s |
| `t15` | 13.0 s | 8.4 s |
| `t17` | 32.4 s | 2.2 s |
| `t18` | 25.8 s | 3.2 s |
| `t19` | 21.2 s | 2.2 s |
| `t20` | 12.6 s | 7.7 s |
| `t23` | 21.1 s | 1.5 s |
| `t24` | 21.4 s | 6.7 s |
| `t25` | 22.5 s | 0.5 s |
| `t26` | 20.9 s | 0.6 s |
| `t27` | 11.6 s | 2.2 s |
| `t28` | 15.2 s | 2.4 s |
| `t29` | 43.8 s | 1.5 s |
| `t34` | 14.9 s | 3.2 s |
| `t38` | 34.2 s | 0.9 s |
| `t56` | 10.9 s | 11.0 s |
| `t61` | 10.2 s | 2.3 s |

20 of 20 rechecks succeeded. Median during the run 20.4 s, on recheck 2.2 s.
