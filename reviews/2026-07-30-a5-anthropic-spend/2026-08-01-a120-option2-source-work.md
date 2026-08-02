# A120 Option 2 self-seeded baseline - source work record

Date: 2026-08-01

Status: source complete; awaiting A78 review before any worker mutation or
provider request

Base: `b0ecbf512c853575eb3f9d960fa43136eff1715b`

## Result

A120 is implemented as a transport-only runtime change. The issuance runner,
Firecracker launcher, complete guest image, policy values, and evidence
finalizer are byte-identical to the qualified base. Requirement 1's two-file
host contract therefore remains
`eef6e16e54b6c0945f3874dae71063e8ef2248fea470f2fe4b2579ce22d52977`;
this work neither stales nor refreshes its fixture.

The supporting non-runtime changes are the A120 checker, focused tests,
documentation, generated codebase metrics, and the two resulting SHA updates
inside the existing A101 trust-root chain plus its resulting workflow root pin.
No runner, launcher, guest, finalizer, policy, fixture, or installed-worker
source changed.

The transport constructs one deterministic 800,306-byte Messages body with
SHA-256
`b3751a164cde71cbca2fe5de05d3fc8a836649e46114c616cdaf4a210bdfccf4`.
The same source path constructs that byte sequence in every phase. Its only
output allowance remains `max_tokens: 1`.

## Reviewed uncached-input floor

The source reuses the exact 400,083-byte synthetic prompt from the July failed
attempt as a calibration unit. The retained Anthropic Usage Report records:

- eight accepted byte-identical `claude-opus-5` requests;
- 1,536,296 uncached input tokens in total;
- zero cache-read input tokens and zero cache-creation input tokens; and
- eight output tokens.

Identical requests under one model tokenize identically, so the observed unit
is `1,536,296 / 8 = 192,037` uncached input tokens. The A120 body places two
copies of that exact text in independently delimited text blocks, for a
pre-computed 384,074-token projection. The enforced conservative floor is
300,000 tokens, an 84,074-token or 21.89% haircut from the calibrated
projection. At A119's recorded $5 per million input tokens:

```text
300,000 * $5 / 1,000,000 = $1.50
$1.50 - $1.00 = $0.50 margin
```

The floor depends on no output token. The first accepted response must report
at least 300,000 ordinary input tokens. A lower count is a stop after the one
fixed request, never a signal to resize or retry. The 384,074-token projection
fits beneath Opus 5's documented default 1-million-token context window without
a beta header:
<https://platform.claude.com/docs/en/about-claude/models/choosing-a-model>.

No Token Count API or Messages request was made to choose this size. The
calculation uses the retained same-model provider observation, and the size is
fixed in reviewed source before a live call. Anthropic documents the Token
Count API as an estimate whose result can differ slightly from actual message
usage, so the runtime check is against billed response usage and is only a
postcondition; it is not a discovery loop:
<https://platform.claude.com/docs/en/build-with-claude/token-counting>.

## Prompt caching exclusion

Anthropic documents two prompt-caching opt-ins: top-level automatic
`cache_control` and explicit content-block `cache_control`:
<https://platform.claude.com/docs/en/build-with-claude/prompt-caching>.
The digest-bound body has exactly the top-level keys `max_tokens`, `messages`,
and `model`; each text block has exactly `text` and `type`. The header-only
curl configuration is also exact. There is no cache opt-in, tool, or server
tool. In addition, an expected positive-control response fails unless both
`cache_creation_input_tokens` and `cache_read_input_tokens` are exactly zero.
Thus a cache hit cannot silently lower billable input beneath the floor. This
postcondition applies to the two expected positive controls. An unexpected
valid acceptance in `temporary_refusal` is first classified as A120's terminal
qualified negative because provider acceptance itself decides the
workspace-scope question; no surprising usage shape can turn it into a retry.

## Stops and unchanged bindings

- The attended procedure waits at least 10,260 seconds after the first
  acceptance. If settled workspace spend is $1.00 or less, it stops before the
  cap change and authorizes no second or larger acceptance.
- A valid provider acceptance during `temporary_refusal` emits
  `anthropic-spend-provider-response-rejected-200-provider-accepted-workspace-scope-qualified-negative`
  and exits nonzero. The diagnostic itself names the validated provider
  acceptance and A120 disposition; its cap/UTC record is the qualified
  negative. The operator restores the $50.00 workspace value, makes no
  restored provider request, makes no repair request, and escalates between
  Options 4 and 6.
- The normal qualifying path remains one provider request in each of three
  phases, with one transport invocation and one admitted conntrack ID per
  phase. Principal, model, endpoint, body, $1.00 temporary value, $50.00
  operational value, and nonbinding $500.00 organization value are unchanged.
- Both 10,260-second settlement guards remain byte-bound in the unchanged
  finalizer and source-checked independently.

## Mutation results

`python3 -I tools/run-isolated-unittest.py
infra/ansible/tests/test_anthropic_spend.py` passed 31 tests, including five
fresh-copy checker mutations:

| Mutation | Required failure |
| :-- | :-- |
| Changed `PROMPT_CALIBRATION_COPIES=2` to `1`, making the constructed body fall below the reviewed two-copy floor | `A120 request body falls below or differs from the cost-floor binding` |
| Injected curl `--next` plus a second body and Messages URL into the sole transfer block | `A117 one-shot transfer permits another transfer: --next` |
| Replaced the pre-activation `10,260`-second comparison with a dead `False and ...` guard | `A120 pre-activation settlement floor guard is missing` |
| Replaced the temporary-acceptance branch's `exit 1` with `:` | `A120 provider-acceptance qualified-negative stop is missing` |
| Changed the first acceptance's settled `$1.00 or less` instruction from `stop` to `continue` | `A120 first-acceptance settled-cost stop is missing from the procedure` |

Each mutated copy exited nonzero. The unchanged focused suite also exercised
the body and prompt hashes, exact byte lengths, cache-control absence,
300,000-token pass boundary, 299,999-token failure, nonzero cache-read failure,
nonzero cache-creation failure, both settlement-floor finalizer cases, and the
one-transfer host cardinality binding. It also binds the temporary-acceptance
qualified-negative stop before the positive-control usage guard, so an
accepted refusal-phase response cannot be misclassified as a sizing failure.

## Gate results

The final full repository gate set returned zero:

- `tools/check-infra.sh` initialized and validated all three OpenTofu roots;
  A101 trust root, stack, independence, worker runtime, worker qualification,
  A120 spend, qualified Anthropic issuance, and preview checks all passed.
- `tools/check-ansible.sh` passed 168 tests in 14 isolated processes,
  ShellCheck, all four Ansible lint profiles, all four playbook syntax checks,
  and the terminal A101 trust-root recheck.
- `tools/check-application.sh` passed the constitution, preview, Rust format,
  clippy, unit, integration, property, fixture, replay, reproducible-release,
  advisory, license, vet, dependency, model, and byte-exact codebase-metrics
  gates. The one Docker-only Traefik test used its declared local skip because
  this account cannot access the host Docker daemon; hosted PR CI supplies that
  service and is the independent execution of that case.
- Direct `bash -n` and ShellCheck on the changed one-shot transport passed.
  Both isolated Anthropic checkers passed, and the focused 31-test suite above
  passed at the final source hashes.

The first pre-final infrastructure/Ansible invocation correctly refused two
stale A101 trust-root SHA entries for the changed spend checker and test. Those
two entries and the workflow's resulting root-checker pin were updated; the
final trust-root digest is
`8b9c51847f5e0603f3b9da8bca04b21cf590022f0d2bace6a0bc6435e3753421`.

## Negative-scope attestation

This work made no provider or Token Count request, minted no credential,
changed no Console limit, applied no infrastructure, converged no host,
mutated no worker, refreshed no fixture, performed no behavioral acceptance,
started no requirement-3 work, and rotated no credential. It introduced no
bare `ANTHROPIC_API_KEY`. All 13 `credential_qualified` values remain false.
