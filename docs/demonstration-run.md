# The demonstration run

Issue [#208](https://github.com/JacobStephens2/patchyard/issues/208)
is the destination of
[MAP #176](https://github.com/JacobStephens2/patchyard/issues/176):
Jacob submits the sanitized ALPHABETIZE body at `/new`, the resident daemon
claims it with no console step, and a bot-authored draft pull request appears
on real Fieldbook carrying a model-authored patch and evidence links. It is never
merged. It is closed after inspection.

This file is the repository half of that ticket — the base the run is opened
from, and the operator script for the run itself. Performing it is not
something a commit can do.

## What changed here, and why it is not what the cutover doc said

[`production-cutover.md`](production-cutover.md) recorded precondition 1 as
"`tests/Unit/AlphabetizeSalespeopleTest.php` must exist on Fieldbook `master`".
That is unsatisfiable as written, for two independent reasons.

The first is that it does not satisfy the gate it was written for. The
production verifier resolves targeted tests **at `FACTORY_BASE_SHA`**, not at
`master` (`worker/runtime/patchyard-run-verifier`, gate `verifier-inputs`).
The pin was `4ef35181` — Fieldbook master at 2026-07-24 — so landing the test on
today's master would have left the run rejecting the task with
`targeted_test_exists_at_base` exactly as before.

The second is what landing it costs. The test is red until the ALPHABETIZE
patch exists, Fieldbook's `phpunit.xml` sweeps all of `tests/Unit`, and the
demonstration pull request is never merged. "Red until it is fixed" would have
meant red on master with no scheduled end.

So the run uses Session 7's shape instead: a dedicated Fieldbook branch that is
`master` plus the one test file.

| | Value |
| --- | --- |
| Base branch | `factory/alphabetize/staging` |
| Base SHA | `00af775db678b2877d0863cf35512874579d8407` |
| Its parent | Fieldbook `master` at `5b637332` (2026-08-24) |
| Contents | `master` + `tests/Unit/AlphabetizeSalespeopleTest.php`, one file, 29 lines |

Fieldbook `master` stays green. The pull request's diff is exactly the model's
patch — two files, three lines — because the test is already on its base. And
the red-to-green transition the request is about stops being something the
operator has to attest to: it is the pull request's own check run.

### The branch name is load-bearing

The `/staging` suffix is not decorative and must not be tidied away. Fieldbook's
`.github/workflows/phpunit.yml` filters on `[master, '**/staging']`, and GitHub
matches the `pull_request` filter against the pull request's **base**. A base
outside that list gets no checks at all — and no checks is not a pass. The
supervisor reads an empty check-run list as `checks_not_started`
(`evaluate_checks`, `crates/factory-supervisor/src/lifecycle.rs`) and keeps
waiting, so a well-named-looking branch like `factory/alphabetize-base` would
spend the full 1800-second `FACTORY_CI_WAIT_TIMEOUT_SECONDS` and end the
demonstration on `ci_wait_timed_out` with nothing to show.

`infra/ansible/tests/test_demonstration_run.py` asserts this, including that
the base branch is not `master` itself and cannot collide with the publisher's
own `factory/<request-id>-change` pattern.

### The request is still live against current master

Both target sites are still unsorted at Fieldbook `master` `5b637332`:
`get_salespeople_usernames` in `mfieldbook/common_functions.php` has no
`ORDER BY`, and `mfieldbook/leads/assign.php` orders by `listOrder ASC`. The
acceptance test was executed against that tree — red — and against the same
tree with the three-line sort applied — `OK (1 test, 4 assertions)`. The demand
the demonstration answers is real today, not a month-old artifact.

## Preconditions

1. **The base branch exists on Fieldbook.** `factory/alphabetize/staging` at
   `00af775d`, pushed and unmodified. Confirm the pin and the remote agree:

   ```
   gh api repos/example-org/fieldbook/git/ref/heads/factory/alphabetize/staging --jq .object.sha
   ```

   This replaces precondition 1 of [`production-cutover.md`](production-cutover.md).

2. **The implement guest's production-parity path.** Unchanged from
   [`production-cutover.md`](production-cutover.md) precondition 2:
   `pre_publish` is the first mode where `parity_required` is true, so the
   guest initializes MySQL from `FACTORY_SNAPSHOT`, loads `fieldbook_training`,
   mounts the webroot, and serves the app before the model writes a line.
   Confirm `/var/lib/patchyard/snapshots/current` is present and current and
   that the implement image is at the pinned recipe. A parity failure surfaces
   as `implement-mysql-prepare-failed`, not as a verifier rejection.

3. **Preview parity against the new base.** The preview host serves a checkout,
   and the base moved a month forward. `FACTORY_EVIDENCE_PREVIEW_PATH` is
   `/mfieldbook/leads/assign.php?rqst_id=96429` with selector `#sales_person_id`.
   Confirm that page still renders that selector on the preview fleet before
   the run, or the evidence capture fails after a successful patch — the most
   expensive place to discover it.

4. **The safety checklist in [`production-cutover.md`](production-cutover.md)
   § Safety checklist** — daily caps, `factoryctl pause`, the kill drill
   against the dry-run target, publisher branch hygiene, converge then qualify.
   Note that `factory/alphabetize/staging` now legitimately appears in the
   `matching-refs/heads/factory` listing that step 4 greps; it is a base, not a
   stale published branch. Step 3, the kill drill, was **not** re-performed for
   this run; it is satisfied by ruling on two conditions, one of which binds
   the run itself. Read
   [Step 3 was ruled satisfied, not re-drilled](#step-3-was-ruled-satisfied-not-re-drilled)
   before you take it as simply done.

## Before the next attempt

The 2026-08-25 attempt (recorded under
[What has and has not been performed](#what-has-and-has-not-been-performed))
left the factory under Full stop with two screenshot-less requests the daemon
will take the moment it is resumed, on a revision that retries a failing
triage stage without a ceiling. These steps undo that, in this order.

1. **Converge the control plane to master, then qualify.** Performed
   2026-08-30 with Jacob's go; see
   [The converge of 2026-08-30](#the-converge-of-2026-08-30). The daemon must run
   a revision at or after `2d46b61` — that is the claim ceiling and the `/new`
   no-screenshot confirm — and it should carry `dad92b2`, so a failing seat's
   stderr is kept, and `c35f3b4`, so the review seat can see the change to
   `mfieldbook/common_functions.php` instead of a projection of it. The path is
   `tools/deploy-control-plane.sh` from `orchestrate`, then `converge.sh` and
   `qualify.sh` as on 2026-08-25, with Jacob's go: a converge is inside the
   A148 grant, but every converge so far on this ticket has been gated by
   hand, and this one lands hours before a live run. Afterwards re-read the
   three pins in the table above from `/etc/patchyard/supervisor.env` and
   the worker's recipe marker; they survived the last converge and should
   survive this one, but the run depends on them, so look.

2. **Close both leftover rows before lifting the Full stop.** Invoke
   `factoryctl` as [`runbook-v0.md`](runbook-v0.md) § Foreground run identity
   says:

   ```
   factoryctl close 55868a0e-294b-4116-bbbf-db620c4cdead
   factoryctl close 2235d555-59a6-4d61-a329-4ba45c544b1f
   ```

   `close_request` refuses `plan_bin`, `failed` and `killed` rows and treats
   an already-`closed` one as a no-op, so it takes a stranded `claimed` row
   and a `queued` one alike, and it releases any open lease on the request
   in the same transaction. Confirm
   both read `closed`. Do this **before** Resume, not after: the sweep orders
   a `claimed` row ahead of `queued` ones, and Resume is what lets it run.

3. **Resume from the dashboard** and confirm `paused=f, full_stop=f` with no
   new `request.claimed` event. The 12:19 drill lease on `6b7c19d7` will still
   show as active; it expired on 2026-08-25 and the sweep ignores it.

4. **Re-run the readiness reads** — base ref `00af775d`, three refs under
   `heads/factory`, zero open factory pull requests, `snapshots/current`,
   recipe marker `0c3e875f` — and the pause probe under
   [`factoryctl claim` is the wrong probe for a pause](#factoryctl-claim-is-the-wrong-probe-for-a-pause)
   if the converge restarted the daemon.

5. **Submit with both PNGs attached, and look before you leave the form.**
   The 19:03 admission went in at 1,114 bytes: the body, no files. On the
   converged revision `/new` warns and asks for confirmation when no
   screenshot is attached; if you see that warning, the files did not go
   with the form — stop and attach them. The request page should list two
   attachments before triage starts.

Then **The run**, from step 0.

## The run

Everything above happens before Jacob touches the form. The run itself is:

0. **Stay at the console.** This run is attended from submission to terminal
   state, with the dashboard's `Full stop` control reachable throughout. That
   is not general caution: it is the condition the kill drill was waived on
   ([Step 3 was ruled satisfied, not re-drilled](#step-3-was-ruled-satisfied-not-re-drilled)),
   so it is the thing standing in for a drill that was not re-performed.
   `Full stop` blocks claims and requests termination of active work
   ([`runbook-v0.md`](runbook-v0.md) § Kill and full stop). Leaving the
   run unattended does not make it riskier by a little — it removes the
   compensating control the waiver was granted against.

1. **Submit.** Authenticated at `factory.example.com/new`. The body is the
   sanitized ALPHABETIZE request in
   `fixtures/acceptance/alphabetize/request.md`, with
   `simple-sales-report-unsorted.png` and
   `create-or-assign-school-unsorted.png` attached. No console step follows —
   being claimed without one is a thing the demonstration is proving.

2. **Watch.** `/request/{id}` streams from `/request/{id}/events`. The sequence
   to expect is intake → triage → implement → review → verify → publish. The
   acceptance contract the run should match is
   `fixtures/acceptance/alphabetize/expected.json`: lane A, skill
   `ui.sort-dropdown`, the two named targets, two files and at most fifty
   changed lines.

3. **Stop.** The terminal state is a **draft** pull request on Fieldbook with
   base `factory/alphabetize/staging`. Do not merge it. Do not approve it. Read
   it, confirm the patch is the model's and the evidence links resolve, and
   close it.

### What failure looks like, by stage

Read the rejecting assertion, not the transcript. Each of these ends the run
rather than buying a repair attempt, because none is a patch the model could
have written differently:

| Assertion | What is actually wrong |
| --- | --- |
| `targeted_test_exists_at_base` | The base branch is not the pin, or was rewritten |
| `implement-mysql-prepare-failed` | Precondition 2: the snapshot or the image |
| gate `implement-teardown` | The implement worker left residue; the run is not verifiable |
| gate `worker-runtime-isolation` | Verified under the wrong identity or a live agent worker |
| `ci_wait_timed_out` | Almost certainly the base branch fell outside Fieldbook's CI filter |
| `request.abandoned` | The request was claimed `FACTORY_MAX_CLAIM_ATTEMPTS` times without recording anything; read the stage stderr in the `pipeline attempt stopped` event, not the retirement ([runbook-v0.md](runbook-v0.md) § A request that cannot progress) |

Only gate `targeted-phpunit` rejects the `patch`, and only it spends the one
repair loop. [`factory-verify.md`](factory-verify.md) is the contract.

## Recording it

The ticket resolves when Jacob has watched it happen **and** the run and pull
request are recorded on the card. Comment on #208 with the request id, the run
id, the Fieldbook pull request URL, and the outcome after inspection including
that it was closed unmerged.

## After the destination

Three things are waiting on this and should be done deliberately, not
forgotten:

- The 2026-08-18 route authorization **dies here** (A148). Afterwards a named
  model no longer decides or performs map tickets without asking.
- [#242](https://github.com/JacobStephens2/patchyard/issues/242):
  turn repo auto-merge back off.
- [#261](https://github.com/JacobStephens2/patchyard/issues/261):
  re-arm the codebase metrics projection gate.

## What has and has not been performed

The base branch was pushed to Fieldbook on 2026-08-25 with Jacob's go, so
precondition 1 is satisfied: the `gh api` call above returns `00af775d`.

The converge was performed on 2026-08-25 from `orchestrate` at merged revision
`2ccc1c7`, with Jacob's go. It satisfies precondition 2 and the converge half
of precondition 4, and it is what moved the two pins the run depends on into
the running unit:

| | Before the converge | After |
| --- | --- | --- |
| `FACTORY_BASE_SHA` | `4ef35181` | `00af775d` |
| `FACTORY_GITHUB_BASE_BRANCH` | `master` | `factory/alphabetize/staging` |
| Implement image recipe | `e73098db` | `9beb2ec5` |

The first converge reported `changed=14` on the control plane and `changed=2`
on the worker; the second reported `changed=0` on both, and `qualify.sh`
passed control-plane, worker, A101 management transport, and the independence
check. No cloud plans were needed: nothing under `infra/tofu` differs between
the previously deployed revision and `2ccc1c7`.

Precondition 3 is confirmed short of an authenticated render: the selector is
in unconditional markup at the base SHA, `fieldbook_preview.tblGroupInfo` still
has `rqst_id=96429`, and eighteen rows satisfy the select's own query. A plain
GET redirects to `login.php`, so the live render belongs to the run's own
capability path rather than to a curl.

Of precondition 4, steps 1 (caps are `5`/`25` in the running config), 2
(pause verified — see below), 4 (publisher branch hygiene) and 5 (converge
then qualify) are done. Step 3, the kill drill, was not performed and was
ruled satisfied without one; the next section is that ruling and what it
costs.

Everything under **The run** was attempted once, on 2026-08-25, and did not
reach a pull request. The next section is that record and the durable state it
left behind, which is what the next attempt starts from.

### The first attended attempt, 2026-08-25, and what it left behind

Two rehearsal submissions preceded it that afternoon, both from `orchestrate`
under Jacob's dashboard identity, and each found a fault the attended attempt
then inherited or avoided:

| Time (UTC) | Request | What happened |
| --- | --- | --- |
| 14:06:47 | `4fddaa3d` | The sanitized body **without** its two screenshots (admission `rejected`, reason `no-screenshot`, 1,114 bytes). The triage seat answered prose instead of the JSON envelope, the stage exited 1, and the durable sweep re-claimed and retried it eighteen times, every one a billed provider call, until a pause at 14:09. Closed by hand at 15:08. Filed as [#324](https://github.com/JacobStephens2/patchyard/issues/324). |
| 15:16:29 | `8d2be21e` | The same body **with** the screenshots (one admission `completed`, 3,227,432 bytes). Triage classified lane A on the first attempt; the implement seat (GPT-5.6 Sol [xhigh] via Codex on OpenAI) persisted a patch at 15:23; the review seat (Claude Opus 5 [max] via Claude Code on Anthropic) raised a finding that the packet projected `mfieldbook/common_functions.php` as empty, two review rounds disputed it, and the dispute escalated to the (stubbed) arbiter seat. Run `53b831be` ended `escalated`, reason `review_dispute_requires_third_family`, at 15:28:52; the request is `failed`. The packet defect is [#322](https://github.com/JacobStephens2/patchyard/issues/322). |

The attended attempt, from Jacob's account at `/new`:

| Time (UTC) | Fact | Source |
| --- | --- | --- |
| 19:03:47.98 | Upload admission `8592f511` `rejected`, reason `no-screenshot`, `content_length` 1,114 — the body went in **without** the two PNGs, the `4fddaa3d` shape | `factory.upload_admissions` |
| 19:03:48.00 | Request `55868a0e-294b-4116-bbbf-db620c4cdead` received, source `dashboard:26c11a36` | `factory.requests` |
| 19:03:48.08 | `request.claimed`, holder `factory-supervisor`, fencing token 1, `run_class: production`. **No console step preceded it** — the claim half of the demonstration is proven. | `factory.events` |
| 19:03:54 | `pause` `ad06564e` from the dashboard, completed in 12 ms | `factory.controls` |
| 19:04:43 | Lease released cleanly (not expired; expiry was 20:03:48) | `factory.leases` |
| 19:04:46 | `pipeline attempt stopped; durable sweep will recover` — `stage triage exited with status 1` | supervisor journal |
| 19:10:07 | `pause` `6faa2813` | `factory.controls` |
| 19:10:21, 19:10:22 | `full_stop` `72bbb5b6` and `33ed1981`, both `{"full_stop": true, "active_workers": 0}` | `factory.controls` |

The stage's stderr was not kept — that is [#323](https://github.com/JacobStephens2/patchyard/issues/323), fixed on master in `dad92b2` — so the triage failure is attributed to the missing screenshots by shape, not by transcript: same body, same seat, same exit, three hours after `4fddaa3d`, and the same body with the screenshots had passed triage first time at 15:17.

What that left behind, as read from the control plane on 2026-08-30:

- `factory.supervisor_state` is `paused=t, full_stop=t`, updated 19:10:22 by `jacob@stephens.page`. **The factory has been under Full stop since.** Nothing has been claimed; the nightly backup (`patchyard-backup.timer`, 02:20 UTC; the restart landed at 02:26 on 2026-08-30) stops and restarts the daemon, and it comes back into the same state.
- `55868a0e` is still `claimed`, with no lease, no run and one event — the shape [#332](https://github.com/JacobStephens2/patchyard/issues/332) describes. Nothing on the dashboard reaches it. #332 closed on `2d46b61`, which bounds the row rather than repairs it: on the converged revision the sweep re-claims it, the seat fails again, and `request.abandoned` retires it after three billed calls. Closing it by hand costs none.
- `2235d555-59a6-4d61-a329-4ba45c544b1f` was received 2026-08-26 23:02:08 from the same account, body `Alphabetize the employee drop down lists`, no screenshots. It is `queued` behind the Full stop.
- The lease row from the 12:19 pause drill (`holder: pause-drill-208` on `6b7c19d7`, the July orphan) was never released and expired at 12:20:22. It is inert — the sweep reads expiry — but it is the one row `factory.leases` reports as active.
- No factory pull request was opened on Fieldbook; `heads/factory` still holds exactly the three refs step 4 counted, and `max_open_prs` is untouched.

#### The converge of 2026-08-30

Performed from `orchestrate` at merged revision `e816a68` (the merge of #350),
with Jacob's go, by `converge.sh` twice and then `qualify.sh`. The first pass
reported `ok=253 changed=16` on the control plane and `ok=96 changed=3` on the
worker; the second `changed=0` on both. What moved: the four reviewed binaries,
`/opt/patchyard` from `f411798` to `e816a68`, the supervisor environment
(now carrying `FACTORY_MAX_CLAIM_ATTEMPTS=3`), the triage seat and the fixed
child operations, and on the worker the implement image, rebuilt because
`dad92b2` changed `patchyard-guest-implement` and moved the pinned recipe:

| | Before | After |
| --- | --- | --- |
| `/opt/patchyard` | `f411798` | `e816a68` |
| Implement image recipe | `9beb2ec5` | `0c3e875f` |
| `FACTORY_MAX_CLAIM_ATTEMPTS` | unset (unbounded) | `3` |

`FACTORY_RUN_MODE`, `FACTORY_BASE_SHA`, `FACTORY_GITHUB_BASE_BRANCH`,
`FACTORY_VERIFY_TESTS` and the `5`/`25` caps read back unchanged, and
`snapshots/current` is still `2026-08-22-6e9437f90437`. `qualify.sh` passed
control-plane, worker, A101 management transport and the independence check.
Its first run failed the independence check on two gitignored
`__pycache__/*.pyc` files under `roles/control_plane/files/` — local
byte-compile residue from 2026-08-26/27 that embeds the `/srv/orchestration`
path — which were removed; nothing deployed was affected. Durable state after:
`paused=t, full_stop=t` unchanged since 2026-08-25 19:10:22, zero claims, and
the same four open rows. The daemon has restarted once, at 15:17:09 UTC, and
now runs `dddd2c8` and `2360251`, which is the case the waiver note above
anticipates.

Two things about the next Resume follow from the sweep's own order. `claim_next` in `crates/factory-supervisor/src/store.rs` takes a `claimed` row whose lease is gone **before** a `queued` one, so lifting the Full stop hands the daemon `55868a0e` first and `2235d555` second — both screenshot-less — before the fixture body is ever submitted. And the installed revision is the one that retried `4fddaa3d` eighteen times: `/opt/patchyard` is at `f411798` (#330, 2026-08-25), which predates `2d46b61`'s `FACTORY_MAX_CLAIM_ATTEMPTS` ceiling (default 3). Master at `acea4b7` carries ten commits the control plane does not run, and four of them answer what ended 2026-08-25: `dad92b2` ([#323](https://github.com/JacobStephens2/patchyard/issues/323), the stderr), `2d46b61` ([#324](https://github.com/JacobStephens2/patchyard/issues/324), the ceiling and the `/new` no-screenshot confirm), `c35f3b4` ([#325](https://github.com/JacobStephens2/patchyard/issues/325), a bounded window so a large file can be reviewed at all — the fix for [#322](https://github.com/JacobStephens2/patchyard/issues/322) itself, `1bc6aab`, is already installed) and `2360251` ([#321](https://github.com/JacobStephens2/patchyard/issues/321), lease disposition on kill). [Before the next attempt](#before-the-next-attempt) is the checklist that follows.

The preconditions themselves still held on 2026-08-30, read before the converge: the base ref returns `00af775d`; `FACTORY_RUN_MODE=pre_publish`, `FACTORY_BASE_SHA=00af775d`, `FACTORY_GITHUB_BASE_BRANCH=factory/alphabetize/staging` and the `5`/`25` caps are in `/etc/patchyard/supervisor.env`; `snapshots/current -> 2026-08-22-6e9437f90437`; the worker's `fieldbook-implement.recipe-sha256` read `9beb2ec5` (now `0c3e875f`, see below); Fieldbook's `phpunit.yml` still filters on `[master, '**/staging']` at master `b38f8063`.

### Step 3 was ruled satisfied, not re-drilled

Jacob ruled on 2026-08-25 that the attended kill drill is satisfied for #208
without re-performing it. The ruling is conditional on two things. The first
is an obligation on whoever runs the demonstration; the second was discharged
on the day of the ruling and is recorded here so the first is readable:

1. The demonstration is **watched live with `Full stop` available**, not left
   to run unattended. This is step 0 of **The run** above.
2. The two open questions about the kill path are filed — done, as
   [#321](https://github.com/JacobStephens2/patchyard/issues/321).
   They are an unexplained `requests_closed_state_consistent` violation on two
   dashboard kills on 2026-07-28, and the fact that no button-driven kill has
   ever recorded a lease release in its outcome. Filing them is what makes
   hitting one mid-run a known bounded thing rather than a fresh fault
   discovered against real Fieldbook.

Why it was not simply drilled: the checklist requires the drill to run
**against the dry-run target**, and `FACTORY_RUN_MODE` is a hardcoded literal
in `patchyard-supervisor.env.j2`, read once at daemon bootstrap. There is no
per-request or per-manifest override. With the daemon at `pre_publish` since
[#207](https://github.com/JacobStephens2/patchyard/issues/207), a
`/new` submission goes at real Fieldbook, and A148 keeps a live Fieldbook kill
outside the grant. Drilling as written therefore meant promoting the mode to a
variable, converging to `dry_run`, drilling, converging back, and re-verifying
all three pins in the table above — four converges against the exact
configuration the run depends on, hours before the run.

What is standing in for the drill, besides attendance: on the revision the
control plane runs (`f411798`), exactly one commit has touched `lifecycle.rs`
or `child.rs` since the last drill on 2026-07-28 (`047b802`), so the teardown
code is substantially the code that was drilled. That statement is about the
installed revision, not master: `dddd2c8` (#338) has since touched both files
and `2360251` (#337) changed the kill path in `daemon.rs` and `store.rs`, so
the converge that [Before the next attempt](#before-the-next-attempt) calls for
moves the daemon onto code the 2026-07-28 drill did not exercise. Read the
waiver again after that converge with that in front of you; it does not get
stronger by being repeated.
Read that drill as the ledger has it, not as a clean precedent: on the night
of 2026-07-28 `factory.controls` recorded **two kills that failed** on
`requests_closed_state_consistent` and then, 48 minutes later, two that
completed with `worker_teardown: complete`. Nothing between them is recorded
as a fix. That is the whole of the first question in #321.

Be exact about what this does and does not substitute for. Step 3 asks you to
confirm four things: the control completes, the run and request become
`killed`, **the lease is released**, and worker and child no-residue
qualification passes afterwards. The code-currency argument above covers the
teardown half. It does not evidence lease release — that is #321's second
question, and no button-driven kill has ever recorded it — and no no-residue
qualification has been run against this configuration. `SPEC.md` acceptance 7
("an admin kill of a live run terminates the worker, releases the lease, and
lands the killed event on the SSE stream") therefore remains unevidenced for
the production path for the duration of this run.

This waiver is scoped to #208. It is not a precedent for the next production
run, and it does not close #321 — that one closes when the constraint
violation is explained or shown unreachable and the kill outcome records lease
disposition unconditionally.

### `factoryctl claim` is the wrong probe for a pause

Step 2 asks you to confirm a claim is refused with `ClaimingPaused` while a
pause holds. Do that with `factoryctl run`, not `factoryctl claim`.

`factoryctl claim` calls `claim_request` in `crates/factory-core/src/state.rs`,
which checks terminal status, plan-bin status and lease contention and never
reads `factory.supervisor_state`. It is a low-level lease primitive and it
succeeds under a pause. The `ClaimingPaused` guard is in the supervisor's own
claim path, `crates/factory-supervisor/src/store.rs`, which is what the
resident daemon and `factoryctl run` use — as
[`runbook-v0.md`](runbook-v0.md) § Foreground run identity already says.

A claim that succeeds under a pause is therefore not a finding. On 2026-08-25
it was read as one, which cost a wrong turn; that is why it is written here.

The safe probe is `factoryctl run` against a UUID that does not exist. The
guard reads `supervisor_state ... FOR UPDATE` and returns before the request is
looked up, so a working pause answers `ClaimingPaused` and a broken one dies on
an unknown request instead of starting anything:

```
factoryctl pause  --actor <you> --reason "precondition 4 step 2"
factoryctl run    00000000-0000-4000-8000-000000000000
factoryctl resume --actor <you> --reason "precondition 4 step 2 complete"
```

The pause and resume control rows should each reach `completed` with outcomes
`{"paused": true}` and `{"paused": false, "full_stop": false}`.

Invoke `run` the way [`runbook-v0.md`](runbook-v0.md) § Foreground run identity
does. `DATABASE_URL` is set on the supervisor unit and the rest of the
environment comes from its `EnvironmentFile`, so a plain
`factoryctl run` dies on `MissingEnvironment("FACTORY_BASE_SHA")` during
bootstrap — before it reaches the guard, which reads as a broken probe rather
than a broken pause. The unit does not need stopping for this probe: that step
exists so the daemon cannot claim the row first, and a UUID with no row has
nothing to race for.

Performed 2026-08-25: pause `a2fb4cb5` completed in 13ms, `factoryctl run`
answered `Error: ClaimingPaused`, resume `157d756d` completed in 18ms, and the
factory returned to `paused=f, full_stop=f` with no lease and no run created.

### The base branch's own CI run is red, and that is the shape working

Pushing to a `**/staging` branch matches Fieldbook CI's `push` filter as well as
its `pull_request` one, so landing the base opened a run against the base
itself — and that run fails. Read it before assuming something broke:

```
gh run list --repo example-org/fieldbook --branch factory/alphabetize/staging
```

Run `32802484260` reports `Tests: 3088, Assertions: 15156, Failures: 2`, and
both of those failures are the acceptance test's single method — Fieldbook's
`phpunit.xml` sweeps it into two suites, so it executes twice per run. Nothing
else on the branch is red. That is the red half of the red-to-green
transition the demonstration pull request is about: those two assertions turn
green when the model's three-line patch lands on top, and no unrelated failure
is sitting on the base waiting to hold the pull request's check run red after
a correct patch.
