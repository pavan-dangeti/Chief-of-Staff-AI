# Pricing used for cost estimates

**Prices checked on 2026-09-30.** USD per 1 million tokens.

The evaluation runs for this project were made on free tiers (the Gemini free tier and the
NVIDIA API Catalog), so they cost nothing. The cost figures in the README are **list-price
estimates**: the input and output tokens each model actually reported during the run, multiplied
by the price a named provider publishes for the same model.

| Model ID sent by this project | Input | Output | Provider whose price is used | Source |
|---|---|---|---|---|
| `gemini-3.5-flash-lite` | $0.30 | $2.50 | Google Gemini Developer API, paid Standard tier | [ai.google.dev/gemini-api/docs/pricing](https://ai.google.dev/gemini-api/docs/pricing) |
| `deepseek-ai/deepseek-v4.1-flash` | $0.30 | $1.20 | DeepSeek API, peak-hour rate | [api-docs.deepseek.com/quick_start/pricing](https://api-docs.deepseek.com/quick_start/pricing) |
| `z-ai/glm-5.3-flash` | $0.15 | $0.50 | Z.ai API | [docs.z.ai/guides/overview/pricing](https://docs.z.ai/guides/overview/pricing) |
| `nvidia/nemotron-3-super-120b-a12b` | $0.085 | $0.40 | DeepInfra | [deepinfra.com](https://deepinfra.com/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B) |

## How the estimate is computed

```
cost per 1,000 messages = sum over answered messages of
                          (input_tokens × input_price + output_tokens × output_price) / 1e6
                          ÷ messages in the split × 1,000
```

- Tokens come from the provider's `usage` field on each response and are stored with the cached
  answer, so a run resumed after a rate limit still counts every answer exactly once.
- Messages the prefilter skips are counted in the denominator at zero cost, because in real use
  they are ingested but never sent to a model.
- A repair retry (when the first answer fails schema validation) is included in the tokens.

## Caveats

- **Estimates, not bills.** The models were served by free tiers; the prices are from providers
  that sell the same model. Hosts can wrap prompts in slightly different chat templates, so the
  token counts a paid provider bills may differ a little from those measured here.
- **DeepSeek has an off-peak rate at half price** (outside 01:00–04:00 and 06:00–10:00 UTC on
  weekdays). The table uses the peak rate, so that estimate is an upper bound.
- **Prompt-cache discounts are ignored.** Every provider above discounts repeated prompt
  prefixes, and the system prompt is identical on every call, so real bills would be lower.
- **Latency is not priced in.** Free endpoints are shared, so their latency is not what a paid
  deployment would see; the README reports it as measured and says so.

## Updating

Edit `src/chief_of_staff/pricing.toml` and this table together (a test checks they match), then
regenerate the comparison with the commands in the README. `COS_PRICES_PER_MTOK` overrides the
bundled table at runtime.
