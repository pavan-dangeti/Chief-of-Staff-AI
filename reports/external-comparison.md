| Backend | Held-out test F1 | External F1, before defences | Change from held-out | External F1, now | Attacks succeeded, before → now |
|---|---|---|---|---|---|
| `heuristic:rules-v2` | 0.848 (0.769–0.913) | 0.556 (0.364–0.741) | **-0.292** | 0.600 (0.400–0.773) | 2 of 10 → 0 of 10 |
| `nvidia:z-ai/glm-5.3-flash` | 0.981 (0.950–1.000) | 0.734 (0.623–0.831) | **-0.247** | 0.806 (0.703–0.900) | 6 of 10 → 2 of 10 |
| `gemini:gemini-3.5-flash-lite` | 0.931 (0.875–0.973) | 0.743 (0.618–0.857) | **-0.188** | 0.825 (0.724–0.923) | 6 of 10 → 2 of 10 |
| `nvidia:nvidia/nemotron-3-super-120b-a12b` | 0.863 (0.786–0.927) | 0.844 (0.721–0.943) | **-0.019** | 0.931 (0.857–0.986) | 5 of 10 → 1 of 10 |
