# Floor probe - Claude Code × Claude Opus 5 [max] on Anthropic

*2026-08-12. Operator: the orchestration agent, on the orchestration VM.
Purpose: the `Anthropic/Claude Code/Claude Opus 5/max` pair holds the
adversarial-review seat by A119 but its bench floor was `untested`, and
`policy/routing.json` validation refuses to seat a pair whose floor has
not passed. Same probe as
[the 2026-07-17 harness smoke test](2026-07-17-harness-smoke-test.md):
exact-instruction adherence, k=3, fresh directory per run.*

## Method

Identical instruction, three runs, each in a fresh empty directory:

> Create a file named muse-smoke.txt in the current directory containing
> exactly the word: factory

Invocation (prompt on stdin; the 2.1.x CLI no longer accepts a positional
prompt after `--allowedTools`):

```
printf '<instruction>' | claude --model claude-opus-5 -p --allowedTools Write
```

Harness version: Claude Code 2.1.228. Model access: native Anthropic API.
Reasoning: CLI default (no per-run effort pin exposed in 2.1.228 headless
mode); the pair's [max] tier applies to seat invocations, which pin effort
through the seat request, not through this CLI path.

## Results

| Run | Exit | Wall | `muse-smoke.txt` |
| :-- | :-- | :-- | :-- |
| 1 | 0 | 6.2 s | 8 bytes, `factory\n` |
| 2 | 0 | 6.3 s | 8 bytes, `factory\n` |
| 3 | 0 | 6.3 s | 8 bytes, `factory\n` |

All three runs: sha256 `f24e362e035d2833...` (identical bytes each run),
one Write-tool call, no extra files created.

**PASS 3/3.** Recorded honestly: the file carries a trailing newline
(8 bytes, not 7). The 07-17 pass criterion is "exists with content
`factory`"; the newline is the Write tool's standard file termination and
identical across runs, so this is scored as the same class of pass as the
07-17 Claude Code entries. The Haiku 4.5 record's "exact 7-byte file"
observation is a stricter behavior this pair did not reproduce; noted so
the difference is on record rather than smoothed over.
