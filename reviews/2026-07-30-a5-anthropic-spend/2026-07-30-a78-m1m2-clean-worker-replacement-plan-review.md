# A78 adversarial review - A115 M1/M2 clean-worker replacement plan

## Review identity

| Field | Value |
| --- | --- |
| plan-record commit | `5a5ba96f7030214e0fe022369a3361e496b3b738` |
| operational source | `bc496e47bfeb703876495e80b011d88e10c7c232` |
| reviewed technical repair | `520663f25cbaf862d252067e9ca5d933b00b0e9b` |
| binary plan SHA-256 | `a87568c6707f7d1e5bf581072d70584be117d01e785d1e12ff64ee3665415a59` |
| rendered plan SHA-256 | `d5c222e7b353e67eead2ff391fad1800e2537fe2e8bfedadd471cf3202649891` |
| replacement target | worker `588778422` |
| reviewer seat | A78 |
| harness and model | Claude Code 2.1.220, `claude-opus-5` |
| requested effort | `xhigh`; no separate realized-effort field was exposed |
| permission mode | plan/read-only |
| session | `be754346-1582-4607-b167-c68f6c151307` |
| API duration | 934,510 ms |
| wall duration | 1,094,539 ms |

The review ran in a fresh detached worktree at the exact plan-record commit.
The worktree was clean before and after. The session completed with no
permission denials, repository edits, commits, pushes, PR operations,
subagents, web searches, web fetches, Console or host access, infrastructure
mutation, credential flow, cap action, or provider request. Disposable
mutation copies under `/tmp` were removed. Both saved plan artifacts remained
byte-exact.

## Verdict

**PASS with no material findings.** The exact saved plan and exact operational
source are fit only for a separately authorized apply. PASS does not authorize
applying the plan, modifying a worker, clearing taint, issuing a credential,
making a provider request, changing a cap, starting behavioral acceptance or
requirement 3, or changing a provider qualification flag.

## Offline decode and plan integrity

A78 verified both hashes and the owner-only directory/file modes. The binary
was an encrypted OpenTofu plan. A78 decoded it under an empty environment with
all proxy variables pointed at a dead loopback endpoint and no cloud
credentials. `tofu show -json` still exited zero, demonstrating that decode
needed no network. Mutating disposable working-directory copies of
`variables.tf` and `main.tf` left the decoded JSON byte-identical, proving that
the decode used the plan's embedded configuration snapshot. Re-rendering the
plan reproduced the saved text byte-for-byte without publishing sensitive
no-op state values.

The plan contains nine resource changes: seven no-op and exactly two acting
resources:

- `digitalocean_droplet.worker` is `["create","delete"]` with
  `replace_by_request`, replacing worker `588778422`; and
- `digitalocean_firewall.worker` is `["update"]`, with only its droplet binding
  changing on firewall `01af87da-4951-4441-a1c8-ddfc0214811b`.

The control-plane resources, backup bucket, both Spaces keys, management SSH
key, and backup recovery key are no-op. No restore-drill instance, volume,
snapshot, foreign image, or provisioner surface exists. Only
`ansible_inventory`, `worker_ipv4`, and `worker_private_ipv4` act among the
outputs. The plan binds the stock Rocky Linux image, region and size, Factory
VPC and key, production tag, disabled backups and IPv6, enabled monitoring and
agent, and no variable overrides. An independent cloud-init render reproduced
planned `user_data` identity
`bc402dfdc683c7b582aaab68b6e0ca30b359952d`.

## Source and policy bindings

A78 verified that operational source `bc496e4` differs from technical repair
`520663f` only by generated metrics and three review/evidence records. The
`infra/`, `worker/`, `tools/`, `policy/`, and
`research/isolation/results/` tree objects are identical. All five complete
spend-source digests and the checker digest match their pins. All 13 provider
qualification flags remain false, and every Anthropic credential-pattern hit
is a deny-list marker, absence assertion, environment scrub, or validation
expression rather than a bare credential.

## Tests and mutations

A78 passed the seven focused replacement tests and all 25 focused Anthropic
spend tests. Its independent 34-case harness established this apply order:

```text
clean checkout -> literal approval -> exact revision -> digest #1 ->
action shape -> plan display -> converge input preflight -> digest #2 -> apply
```

Eleven plan-shape attacks were refused before any converge or apply event:
reversed action order, delete only, in-place worker update, firewall no-op,
firewall delete, acting control-plane droplet, acting Spaces bucket, acting
restore-drill, acting SSH key, duplicate worker, and empty resource changes.

Source mutations showed every apply guard was load-bearing. Weakening or
removing the digest comparison or either digest call, revision comparison,
revision gate, literal A115 exception, input preflight, clean-checkout gate, or
plan-shape call reached the mocked apply. The A115 exception accepted only the
literal value `yes`. Swapping the plan during input preflight was refused by
the second digest check; removing that second check allowed the swapped file to
reach mocked apply.

The reviewer also reproduced the known semantic limit: target substitution,
foreign worker attributes, and output-only changes pass the broad action-shape
gate. They remain bound for these exact bytes by the independently inspected
plan digest. Flipping one base64 byte changed the SHA-256 and caused AES-GCM
authentication failure.

The current operator shell has neither file-valued converge input. A78 proved
that `converge.sh --check-inputs` exits nonzero in that state, so the recorded
apply blocker is genuine.

## Nonblocking observations

1. **N1 - semantic shape is broader than the exact review.** The wrapper checks
   actions, not the old target ID, all attributes, or all outputs. Full-plan
   inspection plus the twice-checked digest binds this artifact. A newly
   generated artifact would require another full review.
2. **N2 - one sentence can be read too broadly.** The plan record's statement
   that an independent projection rejected a different old worker describes
   the review-time projection, not `verify_worker_plan` itself.
3. **N3 - GitHub App key mode is not checked.** The input preflight rejects a
   group/world-accessible account roster but accepts a mode-0644 GitHub App key.
   The proposed operator sequence compensates by requiring both inputs in a
   mode-0700 directory as mode-0600 files.
4. **N4 - tag-firewall safety is plan-time only in the wrapper.** The apply arm
   does not rerun `check-do-tag-firewalls.sh`. The proposed apply bracket
   requires a new manual readback immediately before invoking the wrapper.
5. **N5 - the plan contains benign provider drift.** One `resource_drift` entry
   records the worker firewall moving from `waiting` with two pending changes
   to `succeeded` with none while its droplet binding remained unchanged. This
   corroborates the later settled-firewall readback but was not named in the
   original plan record.
