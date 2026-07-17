# DeepSeek V4 x DeepClaude factory experiment - session handoff

## Objective

Evaluate **Claude Code 2.1.212 x DeepClaude x DeepInfra** in
non-interactive mode as a lower-cost Patchyard Factory implementation-worker
candidate. Test both:

- `deepseek-ai/DeepSeek-V4-Flash` at maximum reasoning effort
- `deepseek-ai/DeepSeek-V4-Pro` at maximum reasoning effort

Flash is the cheaper candidate. Pro is the capability and harness-control
comparison. This is a factory evaluation, not an interactive developer setup.

## Current state

- The benchmark matrix now lives at [`../docs/bench.md`](../docs/bench.md).
- The supplied DeepSeek harness research is
  [`2026-07-17-which harness is best for DeepSeek V4 Flash (Reaso.md`](2026-07-17-which%20harness%20is%20best%20for%20DeepSeek%20V4%20Flash%20%28Reaso.md).
- Claude Code `2.1.212` is installed.
- [`aattaran/deepclaude`](https://github.com/aattaran/deepclaude) exists,
  is MIT-licensed, and is a shell-script installation rather than an npm
  package. It has not been cloned or installed on this server.
- DeepClaude's README advertises V4 Pro and first-party DeepSeek,
  OpenRouter, and Fireworks backends. DeepInfra support must be established
  from the actual wrapper source/configuration rather than inferred from the
  fact that DeepInfra itself has an Anthropic-compatible endpoint.
- `DEEPINFRA_API_KEY=op://example-vault/deepinfra/orchestrator-api-key` is
  present in `env.tpl`, but it was added after the current agent process
  started and is therefore unset in this process.
- `GH_MUSE_SPARK_FINE_GRAINED_PAT=op://example-vault/GitHub/muse-spark-fine-grained-pat`
  was also added to `env.tpl` after launch.

Restart with `/usr/local/bin/claude-orchestrator` before doing either network
operation below. Never print either credential or paste it into the chat.

## First action after restart - publish the Muse reproduction repo

The complete local repository is at:

```text
/srv/orchestration/projects/muse-spark-identity-substitution-repro
```

It is clean on `main`; its prepared commit is:

```text
09261cc Add Muse Spark identity-substitution reproduction package
```

`origin` already points to the private repository:

```text
https://github.com/JacobStephens2/muse-spark-identity-substitution-repro.git
```

The ordinary `GH_TOKEN` cannot access that private repository. Verify that
the newly injected fine-grained token is set without displaying it, then use
it only for this operation:

```bash
test -n "$GH_MUSE_SPARK_FINE_GRAINED_PAT"
cd /srv/orchestration/projects/muse-spark-identity-substitution-repro
GH_TOKEN="$GH_MUSE_SPARK_FINE_GRAINED_PAT" gh repo view \
  JacobStephens2/muse-spark-identity-substitution-repro \
  --json nameWithOwner,visibility,url
GH_TOKEN="$GH_MUSE_SPARK_FINE_GRAINED_PAT" git push -u origin main
git status --short --branch
```

Confirm the remote is private and that remote `main` resolves to `09261cc`.
Do not alter the reproduction package unless verification reveals a concrete
problem.

## DeepClaude experiment sequence

### 1. Establish exact provenance

Clone DeepClaude into a disposable or dedicated tools directory, record its
commit SHA, and read the entire launcher before executing it. Do not install
an unreviewed moving `main` script into `/usr/local/bin`.

Record at minimum:

- DeepClaude commit SHA
- Claude Code version (`2.1.212` at handoff)
- model ID
- provider (`DeepInfra`)
- endpoint
- effort setting
- allowed tools
- wall-clock duration
- Claude Code-reported usage/cost, if exposed
- artifact and transcript result

### 2. Prove the routing treatment

Configure DeepClaude explicitly for DeepInfra's Anthropic-compatible route,
using the injected `DEEPINFRA_API_KEY`. Confirm from the wrapper source and
effective non-secret environment that the request is actually:

```text
Claude Code -> DeepClaude -> DeepInfra -> selected DeepSeek V4 model
```

Do not label a direct `ANTHROPIC_BASE_URL` shell function as DeepClaude. A
direct Claude Code x DeepInfra run can be retained as an adapter control, but
it is a different `(model x harness x adapter)` treatment.

Verify the current endpoint and exact catalog model IDs against DeepInfra's
official documentation/API before spending. The prior research suggests:

```text
https://api.deepinfra.com/anthropic
deepseek-ai/DeepSeek-V4-Flash
deepseek-ai/DeepSeek-V4-Pro
```

The prior research also suggests `CLAUDE_CODE_EFFORT_LEVEL=max`; verify that
DeepInfra actually maps the Claude-compatible request to Think Max rather
than assuming that the environment variable alone proves it.

### 3. Run isolated non-interactive floor probes

Use a fresh temporary working directory for every run. Run `claude -p` via
the reviewed DeepClaude launcher, restrict the initial probe to `Write`, use
JSON output if supported, and impose a timeout. Do not point an unqualified
model at the Patchyard Factory worktree.

Run the existing exact-instruction floor probe independently for Flash and
Pro, initially `k=3` each:

```text
Create a file named muse-smoke.txt in the current directory containing exactly the word: factory
```

For every run, inspect both the final response and the filesystem. Passing
means exactly one requested artifact with the exact filename and exact
content - not merely a plausible final message. Preserve raw JSON/transcript
evidence in a new dated research record without credentials.

If any result suggests stochastic behavior, follow the standing bench rule:
measure a rate with at least `n=10`; do not summarize it from a single run.

### 4. Compare the pair, then decide whether to advance it

For the same prompt and tool policy, compare:

- exact artifact reliability
- successful tool-loop completion
- latency
- input/output/cache tokens
- cost
- evidence that max reasoning remained intact across tool calls
- provider and infrastructure provenance
- image-input support, separately from the text-only floor probe

The floor probe is necessary but not sufficient. A pass advances the pair to
the alphabetize fixture gauntlet and later shadow mode; it does not admit the
pair directly to a factory seat.

### 5. Update canonical Patchyard Factory records

Write the complete method and evidence to a new dated file in `research/`.
Then add separate rows to [`../docs/bench.md`](../docs/bench.md) for:

- Claude Code x DeepClaude x DeepSeek V4 Flash (max) via DeepInfra
- Claude Code x DeepClaude x DeepSeek V4 Pro (max) via DeepInfra

Keep model, harness, adapter, provider, version, and effort distinct. Do not
collapse the two models or a direct DeepInfra control into one row. Commit
only the relevant Patchyard Factory and reproduction-repo changes; the parent
orchestration worktree already contains unrelated user changes that must be
preserved.
