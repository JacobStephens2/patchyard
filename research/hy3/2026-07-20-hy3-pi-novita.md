# Tencent Hy3 - Novita x Pi floor and cost check

*2026-07-20, orchestration VM. This is a floor probe, not fixture admission.*

**Result: PASS 3/3. Novita is genuinely advertising Hy3 as a free launch route, and the scored run produced no observable charge.** Each fresh directory ended with exactly one seven-byte `muse-smoke.txt` containing `factory`.

## Treatment and results

- Pi 0.73.1, `novita/tencent/hy3`, `--thinking high`, only the native `write` tool, 300-second cap, and the canonical exact-file prompt.
- Isolated OpenAI-compatible provider at `https://api.novita.ai/openai`; `supportsDeveloperRole: false` is required. Without it, Pi's `developer` message gets HTTP 400 before inference; with it, Pi sends a compatible `system` message.
- Novita's model API reports text-only input, function calling, a 262,144-token context/output limit, and $0/M input plus $0/M output.

| Run | Wall | Input / output / cache-read tokens | Tool and artifact |
| --: | --: | :-- | :-- |
| 1 | 8.048 s | 903 / 97 / 512 | `write`; exact, no extras |
| 2 | 7.137 s | 862 / 74 / 512 | `write`; exact, no extras |
| 3 | 7.810 s | 862 / 77 / 512 | `write`; exact, no extras |

Median wall was **7.810 s**. Pi reported $0.00 from the configured current rates, and Novita's independent balance endpoint showed a **$0.0000 delta** across the three successful runs at its $0.0001 resolution. The hourly usage-bill query had not produced a Hy3 line item immediately afterward. Treat $0 as a dated launch promotion, not a permanent price; refresh the model/pricing API before production routing.

Sources: [Hy3 model page](https://novita.ai/models/model-detail/tencent-hy3), [Novita pricing](https://novita.ai/pricing), [July 2026 Hy3 launch pricing](https://blogs.novita.ai/es/tencent-hy3-on-novita-ai/), [LLM billing rules](https://novita.ai/docs/guides/llm-billing), and [balance API units](https://novita.ai/docs/api-reference/basic-get-user-balance).
