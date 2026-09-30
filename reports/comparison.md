| Backend | Item F1 (95% CI) | Precision | Recall | Attacks succeeded | Call time p50 / p95 | List-price estimate per 1,000 messages |
|---|---|---|---|---|---|---|
| `heuristic:rules-v2` | **0.848** (0.769–0.913) | 0.975 | 0.750 | 0 of 15 | 0.1 / 0.2 ms, local | $0 (runs locally) |
| `nvidia:z-ai/glm-5.3-flash` | **0.981** (0.950–1.000) | 0.981 | 0.981 | 0 of 15 | 10.3 s / 28.7 s | $0.155 |
| `gemini:gemini-3.5-flash-lite` | **0.931** (0.875–0.973) | 0.959 | 0.904 | 1 of 15 | 1.2 s / 5.9 s | $0.449 |
| `nvidia:deepseek-ai/deepseek-v4.1-flash` | **0.902** (0.839–0.951) | 0.920 | 0.885 | 0 of 15 | 4.6 s / 26.8 s | $0.322 |
| `nvidia:nvidia/nemotron-3-super-120b-a12b` | **0.863** (0.786–0.927) | 0.954 | 0.788 | 1 of 15 | 0.9 s / 3.2 s | $0.098 |
