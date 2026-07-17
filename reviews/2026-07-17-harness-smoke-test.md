# Harness smoke test - exact-instruction floor check across candidate pairs

*2026-07-17. Operator: the orchestration agent, on the orchestration VM.
Subject: the worker-seat candidate pairs from `docs/ideas.md` plus
same-day additions from Jacob. This is a pre-gauntlet floor probe, not
admission: it checks one behavior (exact-instruction adherence in a
headless agentic run), k=3 per pair. Admission remains the full fixture
gauntlet + shadow mode (D6).*

## Method

One probe, identical for every pair, three runs each in a fresh
directory:

> Create a file named muse-smoke.txt in the current directory containing
> exactly the word: factory

Pass = `muse-smoke.txt` exists with content `factory`, three for three
(pass^k, k=3, per the acceptance discipline). The probe began as a
mechanical exec-mode check and became a behavioral test when the first
candidate failed it in an unexpected way (below).

Harness versions (pin these when re-running - harness churn is real):
Claude Code 2.1.211 · codex-cli 0.144.4 · Grok Build 0.2.101 ·
OpenCode 1.18.3 · pi 0.73.1 (`@mariozechner/pi-coding-agent`) ·
Gemini CLI 0.51.0 · OpenHands 1.11.0 (V1 SDK). Model access: native
APIs for Anthropic/OpenAI/xAI/Google; Fireworks AI serverless for GLM
5.2 (`accounts/fireworks/models/glm-5p2`), MiniMax-M3 (`.../minimax-m3`,
unlisted on the account but served), Kimi K2.6 (`.../kimi-k2p6`).

## Results

| Harness × Model | Result | Invocation notes |
| :-- | :-- | :-- |
| Claude Code × Fable 5 | PASS 3/3 | `claude -p --allowedTools Write` |
| Codex × GPT-5.6 Sol (xhigh) | PASS 3/3 | `codex exec --skip-git-repo-check -s workspace-write -c model_reasoning_effort="xhigh"` |
| Grok Build × Grok 4.5 (high) | PASS 3/3 | `grok -p --permission-mode bypassPermissions --reasoning-effort high` |
| OpenCode × Muse Spark 1.1 (xhigh) | **FAIL 0/4** | see finding below |
| OpenCode × GLM 5.2 | PASS 3/3 | custom provider block, `--auto` |
| OpenCode × MiniMax-M3 | PASS 3/3 | same provider block |
| Pi × GLM 5.2 | PASS 3/3 | `pi --provider fireworks --model <id> --api-key ... -p` |
| Gemini CLI × Gemini 3.5 Flash | PASS 3/3 | needs `GEMINI_CLI_TRUST_WORKSPACE=true` + `--approval-mode yolo` |
| Gemini CLI × Gemini 3.1 Pro (preview) | PASS 3/3 | same; no CLI flag to pin thinking level yet |
| OpenHands × Kimi K2.6 | PASS 3/3 | no CLI executable in 1.11.0 - driven via a ~15-line SDK script (`uv run --python 3.12 --with openhands-ai`), LiteLLM `fireworks_ai/` prefix |

Not scored: OpenCode's first run per new provider timed out at 300s
(one-time provider-package download); retries were immediate and clean.

## Finding: Muse Spark × OpenCode rewrites "muse-*" filenames

The pair created `claude-smoke.txt` (correct content, wrong name) four
out of four times, plus a fifth run that half-corrected after first
writing the wrong name. Isolation matrix:

| Probe | Outcome |
| :-- | :-- |
| `muse-smoke.txt` via OpenCode | wrote `claude-smoke.txt` (4/4) |
| `muse-note.txt` via OpenCode | wrote `claude-note.txt` first, half-corrected |
| `zebra-note.txt` via OpenCode | correct |
| `test-smoke.txt` via OpenCode | correct |
| neutral cwd (no "claude" in path) | still wrong - path is not the trigger |
| `muse-smoke.txt` question via direct Meta API, no harness | correct |

So the defect needs both the OpenCode context and a `muse-*` name; the
model alone answers correctly. Working hypothesis: OpenCode's prompt
lineage is Claude-Code-derived (its binary carries ~156 `claude`
strings) and Muse Spark treats "muse"-prefixed names as references to
itself, substituting the identity it infers from context. The runs also
showed weaker tool discipline (raw `echo` redirects instead of the
write tool, gratuitous verification commands).

Factory relevance: wrong-filename behavior is wrong-target-file
behavior. `factory-verify`'s caps check would reject the patch
deterministically - the gates are the containment - but the pair starts
any shadow-mode audition with a strike, and the trigger (a token no one
would have guessed) is the argument for odd-corner fixtures over
benchmark trust. Note both public indices rank this pair top-11; neither
measures this floor.

## Not runnable, and why

- **Claude Code × GLM 5.2**: Fireworks does expose an
  Anthropic-compatible `/inference/v1/messages` (verified live), but the
  claude CLI rejects non-Claude model names (`--model` and
  `ANTHROPIC_MODEL` both refused). Needs a name-translating proxy
  (claude-code-router / LiteLLM) if this pairing is ever wanted.
- **Cursor CLI × Composer 2.5**: no Cursor credentials on this VM. Add a
  key to the example vault + `env.tpl` to unblock.
- **MiniMax Code × MiniMax-M3**: desktop app (macOS/Windows) only, and
  no MiniMax platform key here. M3 itself is covered via
  OpenCode × Fireworks. Its headline "Agent Teams" feature is the
  pattern R21 standing-rejects.
- **OpenSymphony**: an orchestrator (Linear issues → OpenHands/Codex
  backends), not a harness - i.e. a control plane, which R11 rules the
  factory builds rather than buys.

## Implications for seat assignment

1. The floor check discriminates pairs, not models or harnesses alone:
   GLM and MiniMax pass in the same OpenCode harness where Muse Spark
   fails, and Muse Spark passes with no harness at all. Evals must bind
   to (model × harness × effort), matching the run-provenance schema.
2. Image-input coverage (the multimodal-in requirement): Fable 5, Sol,
   Grok 4.5, Kimi K2.6, MiniMax-M3, and both Geminis take images; GLM
   5.2 is text-only and cannot fill a screenshot-reading seat despite
   passing.
3. Every qualified pair ran headlessly with env-var auth and no TTY -
   the worker-box contract holds across nine pairs, so seat rotation is
   an operational choice, not a porting project.

Tooling from this exercise persists on the VM (`opencode`, `pi`,
`gemini`, `uv` under `~/.local/bin`; provider wiring recorded in the
orchestration agent's memory). Re-running the matrix after a harness
upgrade is ~30 minutes.
