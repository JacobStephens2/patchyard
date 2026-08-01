# A78 adversarial review - quarantined-successor replacement plan

## Review identity

| Field | Value |
| --- | --- |
| plan-record commit | `9c40b086a3c59a5955ebd484f942319e02786c68` |
| operational plan source | `d8b2955c4de050a67d932d763fd58f2509f34df5` |
| reviewed technical repair | `520663f25cbaf862d252067e9ca5d933b00b0e9b` |
| binary plan SHA-256 | `62adfcaac371203a5c9127ed307f29fdbd1593e2f2a466ae22836551e9fd91c3` |
| rendered-plan SHA-256 | `b77a32f12f3480e08496d6b8ff83fb38dc6c2b300999649ff0b9ad94169cafae` |
| replacement target | operationally quarantined worker `588826948` |
| reviewer seat | A78 |
| harness and model | Claude Code 2.1.220, `claude-opus-5` |
| requested effort | `xhigh`; no separate realized-effort field was exposed |
| session | `f7af3ad1-ae29-4105-ab40-82ad1acd25d8` |
| three-part API duration | 1,669,957 ms |
| three-part wall duration | 1,802,474 ms |

A78 ran in a fresh detached worktree at the exact plan-record commit. The
first part used plan/read-only mode for the complete offline decode. That mode
blocked the requested executable tests and scratch mutations. A continuation
with edit acceptance remained blocked by Claude Code's filesystem and command
allowlists and produced 15 permission denials but no test or mutation result.
The final continuation used an explicitly allowed mode-0700 scratch root and
permission bypass solely for the already-authorized local tests and disposable
mock mutations. All writes remained inside the removed scratch root or the
repository checkers' self-cleaning `/tmp` paths. The review checkout and saved
plan were read-only and clean throughout.

Claude Code reported a 23-output-token Haiku helper in the first invocation's
model-usage metadata in addition to the Opus reviewer. No subagent was invoked,
and every substantive review result and final verdict came from the continuing
Opus session.

## Verdict

**PASS with no material findings.** The exact saved bytes replace, rather than
repair or reuse, operationally quarantined worker `588826948`. PASS is fit only
for a separately authorized worker-only apply. It does not authorize applying
the plan, modifying a worker, issuing a credential, making a provider request,
changing a cap, refreshing requirement 1, starting behavioral acceptance or
requirement 3, or changing a provider qualification flag.

## Offline decode and exact plan

A78 independently verified both artifact hashes and the owner-only directory
and file modes. It decoded the encrypted OpenTofu plan entirely in memory,
offline, without a backend, provider, host, or network call. The default
no-color rendered plan reconciled byte-for-byte with the decoded acting facts.
The plan's embedded root-module configuration and lockfile were byte-identical
to `infra/digitalocean/` at plan source `d8b2955`; no external module or
variable value was embedded.

The plan contains nine resources, seven exact no-ops, and exactly two acting
resources:

- `digitalocean_droplet.worker` is `["create","delete"]` with
  `replace_by_request`, replacing `before.id=588826948`; and
- `digitalocean_firewall.worker` is `["update"]`, changing only the droplet
  binding on firewall `01af87da-4951-4441-a1c8-ddfc0214811b`.

The control plane, backup bucket, both Spaces keys, management SSH key, and
backup recovery key are no-op. No restore-drill resource exists. Exactly
`ansible_inventory`, `worker_ipv4`, and `worker_private_ipv4` act among 16
outputs. The inventory change is limited to the worker's public and private
address leaves. Every sensitive backup output is no-op.

A78 bound the stock `rockylinux-9-x64` image, `nyc3`, `s-8vcpu-16gb`, existing
Factory VPC and one existing management key, `production` tag, disabled backups
and IPv6, enabled monitoring and droplet agent, no configured volume, no
snapshot, no restored state, and no provisioner. The plan computes
`volume_ids` at apply rather than asserting the successor's final list. The
worker firewall remains ID-targeted rather than tag-targeted, and its three
inbound and three outbound rules are byte-identical before and after.

An independent template render using the plan-bound public key, without
displaying it in the final report, reproduced `user_data` SHA-1
`bc402dfdc683c7b582aaab68b6e0ca30b359952d`. The complete bootstrap contains
only the declared conductor identity, locked password and SSH policy, and the
reviewed coherent firewalld/Python/sudo transaction; it carries no state from
the quarantined worker.

The sole `resource_drift` entry moves the worker firewall from `waiting` with
the prior worker removal and new worker attachment pending to `succeeded` with
zero pending changes. Its droplet attachment is `588826948` on both sides, and
the drift `after` is byte-equal to the planned change's `before`. A78 therefore
confirmed the record's classification as a settled refresh, not another action.

## Source, wrapper, and policy bindings

A78 verified identical git tree objects between technical repair `520663f` and
plan source `d8b2955` across `infra/`, `worker/`, `tools/`, `policy/`, and
`research/isolation/results/`. The plan-record commit changes only generated
metrics and review/evidence records relative to the plan source. All 13
`credential_qualified` flags remain false, and every technical-tree occurrence
of the bare Anthropic credential name is a denylist, scrub, or absence check.

Static inspection and the later mock harness established the apply order:

```text
clean checkout -> literal approval -> exact revision and A115 exception ->
digest #1 -> action shape -> plan display -> converge input preflight ->
digest #2 -> apply the exact saved path
```

The record accurately says `verify_worker_plan` is only a broad action-shape
gate. It does not durably inspect the old target, firewall ID, replacement
reason, attributes, restore no-op, or outputs. Those exact facts are bound by
the independently reviewed encrypted-plan digest, checked both before plan
inspection and after the potentially stateful input preflight.

## Tests and mutations

A78 passed all seven focused worker-replacement tests and all 25 focused
Anthropic spend tests with zero failures, errors, or skips. The unmodified
spend checker passed with the retained-history successor-preflight result. The
codebase projection passed after the reviewer placed the already-installed
pinned Rust tool directory on `PATH`; nothing was installed. `git diff --check`
and checkout cleanliness passed before and after.

The independent strict plan projector accepted the exact artifact and rejected
17 of 17 in-memory mutations. They covered foreign acting resources, reversed
or weakened actions, worker and firewall substitution, replacement-reason
substitution, acting and no-op restore insertion, extra acting outputs, and
missing acting outputs. A reproduction of the wrapper's broad action-shape gate
accepted seven semantic substitutions, exactly matching the limit disclosed in
the record; any such saved-plan mutation changes the reviewed digest.

A78 then built a fresh 31-case mock wrapper harness:

- all three controls behaved as expected;
- the unmodified wrapper refused all 12 attacks before mocked apply;
- 13 of 16 source mutations reached mocked apply, proving the weakened guard
  was load-bearing; and
- the other three mutations remained refused by an independent surviving
  guard, which A78 explained rather than counting as false assurance.

The cases covered digest comparison weakening, each and both digest-call
removals, revision equality and full-hex validation, checkout cleanliness,
literal approval, the literal A115 exception, input-preflight removal and
reordering, action-shape removal, and plan swapping. The decisive swap pair
showed the unmodified second digest refused bytes changed during preflight;
removing that second call let the different mocked-plan digest reach apply.
Every OpenTofu, Ansible, provider, backend, and network action in this harness
was mocked.

The first harness calibration dirtied each mock repository with the mutation,
so the clean-check refused most cases before the intended guard. A78 rejected
that run, committed each disposable mutation, corrected two other
miscalibrated cases, and reported only the recalibrated results above.

## Operational-record review

A78 accepted the live bracket as an expressly time-bounded record claim and
did not access a live system. Source corroborated that an incomplete SQL
terminal-state list can count historical runs while the canonical backup
predicate includes the complete terminal set plus active proposer states. It
also corroborated the restricted PostgreSQL socket and the init-before-plan
registry failure ordering.

The plan and both requirement-2 records explicitly say the absent host taint
marker cannot override the failed-sequence operational quarantine. The plan's
`replace_by_request` on `before.id=588826948` and stock-image creation enforce
the recorded intent: delete the ineligible worker and create a successor, with
no manual repair or reuse.

A78 independently recomputed the deliberately stale requirement-1 binding:
current host contract
`eef6e16e54b6c0945f3874dae71063e8ef2248fea470f2fe4b2579ce22d52977`
versus live fixture
`bd36018284041c4ed12f2bea19248ec5f855cfa06f9d4823670a6d87d86d8e2f`.
It agreed that refreshing the fixture before a successful replacement would
falsely claim a rerun.

## Nonblocking observations

1. A78 initially inferred from the detached branch's A118 endpoint that the
   new phrase "A119 is already taken" was wrong. After receiving the governing
   coordination fact that PR #80 allocated A119 to the reviewer-seat ruling,
   A78 withdrew that observation and its proposed edit in full. Branch-local
   absence cannot establish cross-branch numbering availability.
2. The record's phrase "no attached volume" is supported by configuration,
   but the plan represents `volume_ids=[] -> known after apply`. More exact
   wording would be "no volume configured; volume IDs computed at apply."
3. A minimal local time-of-check/time-of-use window remains between the second
   digest read and OpenTofu reopening the saved path. The owner-only directory
   and operator boundary make this defense-in-depth, not an exact-plan defect.
4. The wrapper does not itself recheck plan modes or require an outside-repo
   path. The proposed operator sequence explicitly owns both checks.
5. Apply source `d8b2955` necessarily predates the record describing its plan.
   The embedded configuration and all five technical trees prove it is the
   correct conservative source rather than the later evidence-only commit.
6. Only the names of three ephemeral sensitive variables, never their values,
   are present in the saved plan. This is an affirmative privacy property.
7. During intermediate decode, A78 printed the management SSH public key to its
   private tool transcript despite the review prompt. It is the non-secret
   public half and was neither repeated in the report nor committed or posted.
8. `verify_worker_plan` occurs in both plan and apply branches. Text mutations
   must anchor on surrounding context; A78's first action-shape-removal mutant
   hit the wrong occurrence and was discarded before the reported run.
9. A78's initial dirty-repository harness run and two miscalibrated cases were
   rejected and rerun as described above; none contributed to the reported
   mutation counts.

## Attestation

The review made no live host, cloud, backend, GitHub, web, Anthropic, credential,
cap, acceptance, requirement-1 refresh, requirement-3, or qualification action.
It did not edit the review checkout, author worktree, or saved plan. No
subagents or sibling reviews were used. The owner-only scratch root and every
review-created transient path were removed. At exit the detached checkout was
pristine, both plan hashes and all three modes remained exact, and the plan
directory still contained only the two reviewed artifacts.
