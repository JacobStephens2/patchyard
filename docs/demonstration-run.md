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

No run has been performed. Everything under **The run** is Jacob's.

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

What is standing in for the drill, besides attendance: exactly one commit has
touched `lifecycle.rs` or `child.rs` since the last drill on 2026-07-28
(`047b802`), so the teardown code is substantially the code that was drilled.
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
