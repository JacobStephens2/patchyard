# Production cutover: the resident daemon against real Fieldbook

Issue
[#207](https://github.com/JacobStephens2/patchyard/issues/207)
flips the resident supervisor from the synthetic Session 9 dry-run loop to
production against real Fieldbook. This file is the change boundary, the
blocking preconditions, and the safety checklist the ticket names — written
down so the operator reads a list rather than reconstructing one.

## What the flip is

`pre_publish` is this codebase's production mode. There is no third mode: the
supervisor accepts `dry_run` or `pre_publish` and nothing else, and the Trello-
era wording "FACTORY_RUN_MODE=production" means this one. It implements against
real Fieldbook at `FACTORY_BASE_SHA` and stops at a **draft pull request**, which
is hard rule 1 — the one human gate. Nothing in this change merges anything.

Four lines of `patchyard-supervisor.env.j2` carry it:

| Variable | Before | After |
| --- | --- | --- |
| `FACTORY_RUN_MODE` | `dry_run` | `pre_publish` |
| `FACTORY_VERIFIER_PROGRAM` | `fixtures/pipeline/bin/verifier-stub` | `/usr/local/sbin/patchyard-run-verifier` |
| `FACTORY_VERIFY_TESTS` | unset | `tests/Unit/AlphabetizeSalespeopleTest.php` |
| `FACTORY_TARGET_REPOSITORY` | the pipeline's repository | inert |

The ticket asks for `FACTORY_TARGET_REPOSITORY` to be repointed at the real
Fieldbook checkout. In `pre_publish` there is nothing to repoint: the variable is
read only in `dry_run`, and the pipeline's repository becomes the publisher's
own bare Fieldbook clone under `FACTORY_PUBLISHER_WORKTREE_ROOT`, which the
publisher creates from the GitHub App token and verifies the recorded base
commit inside. The variable and its `FACTORY_DRY_RUN_BASE_SHA` companion stay
wired, under a comment saying so, because that makes a rollback to the fixture
loop one line in that file rather than a code change.

The worker, triage, and disposition programs were already the real ones
(#206, #181). The verifier was the last fixture in the daemon's environment.

## The verifier that production now names

`worker/runtime/patchyard-run-verifier` ran the targeted PHPUnit slice on the
secret-free worker, but it rejected patches by dying inside `jq -e`. Under the
rejection contract in [`factory-verify.md`](factory-verify.md) that is a
breach: the supervisor synthesizes `verifier_reason_missing`, spends no repair
attempt, and the ledger records a failure that states nothing. The fixture stub
it replaces did state its assertions, so pointing production at the real runner
unchanged would have been a regression in what a failed run can be read to
mean.

It now collects named assertions and always writes `evidence.json`. Its gates
run fail-closed in order, and each names the subject it rejects:

| Gate | Assertions | `rejects` |
| --- | --- | --- |
| `verifier-inputs` | absolute paths, 40-hex base SHA, the patch and implement evidence exist, the base SHA is a commit in the repository, the PHPUnit pin is 64 hex, every targeted test exists at the base SHA | `task` |
| `implement-teardown` | `host_teardown` run directories, processes, taps, nftables tables, credential files are each `0` | `task` |
| `worker-runtime-transport` | the worker runtime ran and returned its evidence | `task` |
| `worker-runtime-isolation` | `verifier_identity`, `clean_environment`, `agent_worker_terminated_before_verify` | `task` |
| `targeted-phpunit` | `tree_hash_equal`, `phpunit_exit_code` | `patch` |

`patch` is the only subject a repair attempt can answer, and it is spent only
on the last gate. Everything above it is a verify environment that could not
reach a verdict: no patch the task can produce would pass while that is true,
so the run ends and escalates instead of buying a second provider bill for a
failure the model was never shown. `infra/ansible/tests/test_production_cutover.py`
executes the rendered runner against mocked hosts and proves every row.

## Blocking preconditions

None is satisfied by this change. Issue 208 dispositioned the first and third;
[`demonstration-run.md`](demonstration-run.md) carries what replaced them.

1. ~~**`tests/Unit/AlphabetizeSalespeopleTest.php` must exist on Fieldbook
   `master`.**~~ **Superseded by issue 208; see
   [`demonstration-run.md`](demonstration-run.md).** The gate is real — the
   lane-A caps forbid the patch from adding its own test, so the verifier
   rejects the absence by name (`targeted_test_exists_at_base`,
   `rejects: task`) rather than reporting a PHPUnit transcript from the far
   side of an SSH hop — but `master` was the wrong place to satisfy it. The
   verifier resolves targeted tests at `FACTORY_BASE_SHA`, not at `master`, and
   the test is red until the patch exists while the demonstration pull request
   is never merged. The test now lives on a dedicated base branch that is
   `master` plus that one file.
2. **The implement guest's production-parity path turns on with the flip.**
   `patchyard-invoke-worker` computes `parity_required` as `not dry_run`, so
   `pre_publish` is the first mode in which the guest initializes MySQL from
   `FACTORY_SNAPSHOT`, loads `fieldbook_training`, mounts the webroot, and serves
   the app before the model writes a line. Every live implement run so far ran
   with parity off. Confirm the snapshot at
   `/var/lib/patchyard/snapshots/current` is present and current, and that
   the worker's implement image is at the pinned recipe, before the first
   production claim - a parity failure surfaces as
   `implement-mysql-prepare-failed`, not as a verifier rejection.
3. ~~**Decide whether `factory_fieldbook_base_sha` advances.**~~ **Decided by
   issue 208: it advanced**, to the demonstration base branch off `master` at
   2026-08-24. The caveat that deferred it still holds and became precondition
   3 of [`demonstration-run.md`](demonstration-run.md): the preview host serves
   a checkout, so preview parity has to be re-checked against the new base
   before the run rather than discovered after a successful patch.

## Safety checklist before merge and converge

Run in this order on `factory-control.example.com`. Every step is an
operator action; none of it happened as part of authoring this change.

1. **Daily caps are the ruled production pair.** `FACTORY_DAILY_PER_SUBMITTER=5`
   and `FACTORY_DAILY_GLOBAL=25`, asserted by the gate. Confirm the running
   unit's environment matches after converge:

   ```
   systemctl show factory-supervisor -p Environment | tr ' ' '\n' | grep FACTORY_DAILY
   ```

2. **`factoryctl pause` verified.** Queue a pause, confirm the control row
   reaches `completed`, and confirm a claim is refused with `ClaimingPaused`
   while it holds. Then `factoryctl resume`. Recall from
   [`runbook-v0.md`](runbook-v0.md) that a pause is not a substitute for
   stopping the unit before a foreground run.

3. **Kill switch drilled.** Follow the attended kill drill in
   [`runbook-v0.md`](runbook-v0.md) § Kill and full stop: submit through
   `/new` under the declared qualification manifest and budget, wait until the
   run owns a worker lifecycle, then use the dashboard `Kill` button. Confirm
   the control completes, the run and request become `killed`, the lease is
   released, and worker and child no-residue qualification passes afterwards.
   The kill's own outcome answers the lease question: every kill records
   `lease_release` in `factory.controls.outcome` (`released`, `none_held`, or
   `outstanding`), so the step is answerable from the control row alone.
   **The drill runs against the dry-run target, not Fieldbook.** The 2026-08-18
   route authorization explicitly keeps the kill of a live Fieldbook run outside
   the grant; a dry-run or non-Fieldbook kill is inside it.

   **This step was waived once, for issue 208 only.** With the daemon at
   `pre_publish` there is no dry-run target to drill against without four
   converges, so Jacob ruled on 2026-08-25 that the drill is satisfied for that
   run on condition it is attended with `Full stop` reachable. The reasoning,
   what it does not evidence, and the open questions it left behind are in
   [`demonstration-run.md`](demonstration-run.md)
   § Step 3 was ruled satisfied, not re-drilled. Outside issue 208 this step
   stands as written; do not read the waiver as a general one.

4. **Publisher branch hygiene against real Fieldbook.** The publisher opens
   `factory/<request-id>-change` off `FACTORY_GITHUB_BASE_BRANCH` — since issue
   208 that is `factory/alphabetize/staging`, not `master` — and refuses a
   branch it does not own. Three branches now appear in the listing below and
   none collides: the two Session 7 leftovers,
   `factory/session-7-alphabetize-base` and
   `factory/session-7-alphabetize-candidate`, and the demonstration base
   itself, which is a base rather than a stale published branch. Confirm before
   converge that nothing matching the production pattern is present, and that
   the open-PR cap of two (`PublisherConfig::max_open_prs`) has room:

   ```
   gh api repos/example-org/fieldbook/git/matching-refs/heads/factory --jq '.[].ref'
   ```

5. **Converge, then qualify.** `infra/ansible/converge.sh` followed by
   `infra/ansible/qualify.sh`, with the supervisor running before you start;
   both ordering traps are in [`runbook-v0.md`](runbook-v0.md).

## Rollback

Set `FACTORY_RUN_MODE=dry_run` in
`roles/control_plane/templates/patchyard-supervisor.env.j2` and converge. The
fixture target and its base SHA are still wired, so the daemon returns to the
Session 9 loop with no other edit. For an in-flight emergency, the dashboard
`Full stop` blocks claims and requests termination of active work; recovery is
a deliberate `Resume` after the external facts and the ledger have been
reconciled.

## Not in this change

- **`factory-verify postconditions` is still unwired.** It needs baseline and
  candidate preview DOM, which exist only after publication, so it belongs in
  the evidence lifecycle rather than the verify stage. Session 7 ran it by
  hand; nothing runs it in the pipeline today, in `dry_run` or `pre_publish`.
- **No converge, no drill, and no live run was performed.** This change is the
  repository half of the ticket.
