# A115 spend run-root repair

Status: **M1/M2 repair and plan review passed; exact replacement applied and
converged; A101 private-VPC qualification timed out; sequence stopped**

This is the requirement-2 work record for Jacob's explicit authorization of
the bounded repair after the first successor operational attempt. It is an
operational grant under A115, not a new numbered ruling. A119 remains reserved.

## Bounded Console readback

Jacob opened the Patchyard Factory workspace and organization limit pages without
changing either limit. The control plane bracketed his readback in UTC and
stored only the credential-free observations in a root-owned volatile file:

| Field | Observed value |
| --- | --- |
| capture start | `2026-07-30T18:46:35Z` |
| capture end | `2026-07-30T18:46:55Z` |
| workspace | `Patchyard Factory` / `wrkspc_000000000000000000000000` |
| displayed workspace state | `$7.68 of $50.00`, resets 1 Aug 2026 |
| organization | `aaadc747-869a-42d2-af51-58a5be8e3b7f` |
| displayed organization state | `$500.00` monthly limit, `$72.27` spent, 14% used |

The 20-second bracket satisfies the five-minute bound. The workspace was
already at the reviewed `$50.00` operational cap, and the organization limit
remained `$500.00`; no Console mutation was made. On the control plane,
`/run/patchyard-anthropic` is `root:root 0700` and its
`cap-readbacks.json` is `root:root 0600`. The temporary file contains no
credential.

## First operational attempt and stop

At technical source
`673b89fbfad5c287f79f9d6b7d046c35f1881cee`, preflight confirmed the exact
installed revision, active control services, idle backup operation,
`paused=false`, `full_stop=false`, `active_work=0`, and an absent target
artifact directory. The runner invoked exactly one operational-acceptance
phase:

```text
run ID: anthropic-s2-operational-20260730-e7b0d43df8
worker start: 2026-07-30T18:48:57Z
failure/taint: 2026-07-30T18:49:05Z
runner exit: 1
diagnostic: anthropic-spend-provider-transport-failed-23
failure stage: provider-one-shot-transport
launcher line: 525
```

Curl status 23 is a local write-path failure, not a provider response. The run
produced no sanitized provider observation and no control-plane artifact
directory. It therefore proves neither provider acceptance nor refusal, and it
does not establish whether Anthropic received the attempted transfer or
whether any incremental spend settled. No HTTP status, request ID, provider
error, usage figure, denial figure, or overshoot figure is claimed from this
attempt.

The launcher cleanup removed the run tmpfs, source stage, input stage, provider
namespace, provider veth, provider nftables table, and worker process. The
worker nevertheless correctly made itself ineligible because a
provider-qualification run failed:

```text
run=anthropic-s2-operational-20260730-e7b0d43df8 reason=containment-qualification-failed stage=provider-one-shot-transport line=525 detected_at=2026-07-30T18:49:05Z
```

The marker is `/var/lib/patchyard-worker/BOUNDARY_TAINTED`, mode
`root:root 0600`. An initial manual residue probe mistakenly checked the
control-plane prefix `/var/lib/patchyard/BOUNDARY_TAINTED` and reported it
absent. A direct check of the worker's canonical path corrected that error.
The marker will not be cleared and worker `588778422` will not be reused.

The post-attempt worker qualifier exited nonzero at its intentional taint-file
guard. A separate read-only `e2fsck -fn` completed successfully and the rootfs
digest remained exact; the failed qualifier is evidence of quarantine, not a
rootfs-corruption diagnosis.

## A77 diagnosis - concede

The source defect is conceded. The launcher created `$RUN_TMPFS` as
`root:root 0700`, then created the provider directory as
`root:factory-worker 0710` and its raw directory as
`factory-worker:factory-worker 0700`. The one-shot helper launches the network
client as `factory-worker`. POSIX path traversal fails at the root-owned
`0700` ancestor before the child can use its narrowly owned files.

A no-network disposable filesystem experiment reproduced the mismatch on the
worker: the `factory-worker` identity could neither traverse the parent nor
write the nested raw path (`factory_worker_parent_traverse_rc=1`,
`factory_worker_nested_write_rc=1`). The experiment removed its temporary
paths at `2026-07-30T18:50:17Z`. SELinux was enforcing and recorded no related
AVC, so the ordinary mode bits are sufficient to explain the result.

## Bounded source repair

Spend mode now creates only its exact run root as
`root:factory-worker 0710`. Group execute permits traversal but group read and
write remain absent. Non-spend runs explicitly retain `root:root 0700`.
Capability material remains `root:root 0600`; the provider directory remains
`root:factory-worker 0710`; and the raw request/response directory remains
`factory-worker:factory-worker 0700`.

The spend checker binds the exact conditional staging block, its location
between runtime staging and capability creation, and the complete launcher
digest. The focused suite includes a direct source-contract test and three new
real-checker mutations:

1. remove the spend-mode group traversal grant;
2. expand spend-mode group access from `0710` to `0770`; and
3. expand the non-spend run root from `root:root 0700` to the spend-mode
   ownership and mode.

All three mutations fail, as do the existing twenty-six source mutations. The
focused suite passes 25 of 25 tests, and the unmodified checker reports the
A115 successor preflight pass while retaining the historical failure records.

The repaired launcher SHA-256 is
`5e69e5f99389bbbcc7796d1623fc0cefa1912ae4050b14eb2c47cb3772b697d5`.
A live read-only parent-path check also confirmed that
`/run/patchyard-worker` is `factory-worker:factory-worker 0700`, so the new
child run root is the only missing traversal grant; no broader ancestor mode
change is needed.

## Pre-review gates

The complete application wrapper passed, including 39 browser-control tests
(one Docker-only integration skip), every Rust unit and integration test,
reproducible release verification, dependency and advisory checks, model
checks, and the byte-exact codebase projection. OpenTofu initialized and
validated all three roots. All four Ansible production lint profiles and all
four playbook syntax checks passed. ShellCheck passed, the spend checker passed,
and 139 of the 140 Ansible unit tests passed.

The only red gate is the intentional live-evidence dependency created by the
repair: requirement 1 records host-contract SHA-256
`bd36018284041c4ed12f2bea19248ec5f855cfa06f9d4823670a6d87d86d8e2f`,
while the repaired host contract is
`2b7a904489e9fa4886c5677a9221fc66978f31e492edf740e7c4ea6b35c37d5b`.
Both the issuance checker and its unit test reject the stale live fixture.
That failure must remain visible until the reviewed repair is installed on a
clean replacement worker and requirement 1 is rerun; changing the evidence
without a live rerun would be false proof.

## A78 review and A77 adjudication

A78 reviewed exact commit
`8cdfeef955ba3d574030e21aff65549219642b86` with Opus 5 at requested effort
`xhigh` in plan/read-only mode. The review returned FAIL on two medium material
findings:

1. the new checker ordering anchors can raise uncontrolled `ValueError` and
   suppress every accumulated diagnostic; and
2. the launcher does not read back the realized directory mode or test
   traversal as `factory-worker` before capability creation.

The build seat reproduced both. Three independent anchor mutations each
produced the bare traceback and no controlled checker diagnostic. Source
inspection and a disposable `install -d` experiment confirmed the missing
readback and the dependence on realized filesystem state. Both findings and
their severity are conceded under A77. The six nonblocking observations are
individually adjudicated in
`2026-07-30-a77-spend-run-root-repair-adjudication.md`.

The exact A78 review is recorded in
`2026-07-30-a78-spend-run-root-repair-review.md`. Because the authorized
repair reached a failed adversarial review, A9 stops another implicit source
iteration. A separately authorized bounded M1/M2 repair and new A78 review are
required before any replacement plan.

## Boundary after review

No repaired source has been installed, no worker has been replaced, no taint
marker has been cleared, and no further capability or provider request has
been made. A clean-worker replacement is blocked. Behavioral acceptance,
requirement 3, and all provider qualification flags remain untouched.

## Further bounded M1/M2 authorization

At `2026-07-30T19:45:20Z`, Jacob explicitly authorized the repair, its tests
and source-mutation checks, and a new A78 review. This operational grant is
recorded here under the standing A115 policy rather than minted as A119 or any
new numbered decision. Its scope is only the two conceded findings above. It
does not authorize a worker replacement, taint clearing, credential issuance,
provider request, Console limit action, behavioral acceptance, requirement 3,
or a qualification-flag change.

## Further bounded repair

The launcher now reads back the spend run root as exactly
`root:factory-worker:710` and runs `/usr/bin/test -x` on that path through
`/usr/sbin/runuser -u factory-worker` before capability creation. The
non-spend branch independently reads back exactly `root:root:700`. Because the
existing `ERR` trap records `FAILURE_STAGE=runtime-staging`, either a realized
metadata mismatch or an identity-specific traversal failure stops before any
bearer is read and produces the controlled launcher failure record.

The spend checker now guards all three surrounding ordering anchors with
`try`/`except ValueError`. A missing anchor and a misordered block both append
`A115 spend run-root traversal is outside runtime staging`; neither can
suppress the complete-source digest diagnostic or the checker's accumulated
failure report.

The focused test retains the exact block and ordering contract. Seven new
real-checker mutations bring the permanent total from 29 to 36: spend readback
mode broadening, substitution of root for the consuming identity, substitution
of existence for traversal, non-spend readback broadening, and removal or
rewriting of each of the three ordering anchors. Every mutation must begin
with `Anthropic spend check: failed` and include its controlled M1/M2
diagnostic. The 25 focused tests, all 36 mutations, the unmodified spend
checker, Python compilation, Bash parsing, and ShellCheck pass.

The further-repaired launcher SHA-256 is
`60b71fb24ce3c47b9b62bdece7166dd0c622a1830fb21d673db8830acf133e3f`.
The further-repaired checker SHA-256 is
`d2d32fc90ec15acdefee8eb126f66f99fa85cf8bd82d71927548c4170b471e09`.
The resulting requirement-1 host-contract SHA-256 is
`eef6e16e54b6c0945f3874dae71063e8ef2248fea470f2fe4b2579ce22d52977`;
the prior live fixture remains bound to
`bd36018284041c4ed12f2bea19248ec5f855cfa06f9d4823670a6d87d86d8e2f`.

The complete application wrapper passed with the pinned Rust tool directory:
39 browser-control tests passed with one Docker-only integration skip; all
Rust unit, integration, property, fixture, and database tests passed; the
release binary reproduced byte-for-byte; dependency, advisory, model, and
generated-projection checks passed. An initial invocation without the pinned
Rust directory stopped after the browser suite because `cargo` was absent from
the shell's default `PATH`; that environment-only stop is retained here rather
than represented as a source failure.

The infrastructure wrapper initialized and validated all three OpenTofu roots
and passed its stack, independence, worker-runtime, and worker-qualification
checks before stopping at the intentionally stale requirement-1 live fixture.
Full Ansible discovery passed 139 of 140 tests; its sole failure was the same
exact host-contract mismatch above. All four production Ansible lint profiles,
all four playbook syntax checks, direct ShellCheck on the changed launcher, the
spend checker, and the preview checker passed independently. The stale live
fixture is not altered: requirement 1 must be rerun on the eventual reviewed
clean replacement.

At commit time, a new A78 review of the exact repair remained required. No
repaired source had been installed and the quarantined worker remained
ineligible for reuse.

## Further-repair A78 result and A77 adjudication

A78 reviewed exact commit
`520663f25cbaf862d252067e9ca5d933b00b0e9b` with Claude Code 2.1.220 and
`claude-opus-5` at requested effort `xhigh` in plan/read-only mode. Session
`b5da2aa3-17aa-4e06-ab0b-ebd9ffa7f81c` completed in 756,150 API ms and
1,122,617 wall ms with no permission denials, web use, subagents, repository
edits, live actions, or infrastructure mutations. The prompt contained a
mistyped long object ID; the reviewer explicitly resolved the unique short ID,
HEAD, parent, and full commit above before reviewing.

A78 returned **PASS with no material findings**. It ran seven novel M1
anchor/order mutations and twelve novel M2 readback/identity/bypass mutations;
all failed with controlled diagnostics. It confirmed 25 focused tests, 36
authored mutations, both complete-source hashes, the honest stale
requirement-1 binding, all 13 false qualification flags, and clean credential
naming. It found the repair fit only for a separately reviewed clean-worker
replacement plan; the PASS authorizes no replacement or provider action.

A78's most useful nonblocking observation reproduced curl status 23 from
unreadable config/request/output paths and noted that narrower one-shot file
readability and writability checks remain possible future hardening. The build
seat independently reproduced the same offline behavior: curl warned that it
could not read the config or request, described an empty POST, failed to open
the header output, returned `000`, and exited 23. This corroborates the
run-root diagnosis but does not prove historical provider receipt or absence.
The narrower preflight opportunity predates this repair and is outside the
authorized M1/M2 scope.

The exact review and adjudication are recorded in
`2026-07-30-a78-spend-run-root-verification-review.md` and
`2026-07-30-a77-spend-run-root-verification-adjudication.md`. No repaired
source has been installed, worker `588778422` remains quarantined and
ineligible, and no credential, provider request, cap action, behavioral
acceptance, requirement-3 work, or qualification-flag change has occurred.

## Clean-worker plan authorization

Jacob then explicitly answered, "I authorize the plan." This operational
grant authorizes preparation of a mechanically pinned clean-worker replacement
plan and its separate A78 review. It does not authorize applying that plan,
modifying or reusing worker `588778422`, clearing its taint marker, issuing a
credential, making a provider request, changing either Anthropic limit,
starting behavioral acceptance or requirement 3, or changing a provider
qualification flag. The authorization is recorded here under A115 rather than
as a new decision-log ruling; A119 remains reserved.

The generated plan and its non-executing boundary are recorded in
`2026-07-30-a115-m1m2-clean-worker-replacement-plan.md`. At the time of this
record, the plan was saved and mechanically inspected but not applied; a fresh
A78 review remained required.

## Clean-worker plan review result

A78 reviewed plan-record commit
`5a5ba96f7030214e0fe022369a3361e496b3b738`, operational source
`bc496e47bfeb703876495e80b011d88e10c7c232`, binary plan digest
`a87568c6707f7d1e5bf581072d70584be117d01e785d1e12ff64ee3665415a59`,
and rendered-plan digest
`d5c222e7b353e67eead2ff391fad1800e2537fe2e8bfedadd471cf3202649891`.
The reviewer returned **PASS with no material findings** after an offline plan
decode, the focused suites, and an independent 34-case mutation harness.

Five nonblocking observations and their A77 dispositions are recorded in
`2026-07-30-a78-m1m2-clean-worker-replacement-plan-review.md` and
`2026-07-30-a77-m1m2-clean-worker-replacement-plan-adjudication.md`. They cover
the broad action-shape gate, one potentially ambiguous record sentence, the
unchecked GitHub App key mode, the plan-only tag-firewall guard, and one benign
provider-drift entry. None changes the exact-plan PASS. No repair or plan
regeneration followed.

At the close of plan review, the plan remained unapplied and worker
`588778422` remained quarantined and ineligible. No credential, provider
request, Console action, behavioral acceptance, requirement-3 work, or
qualification-flag change was authorized by the review result.

## Clean-worker apply authorization and stop

Jacob subsequently answered, "I approve the plan." This authorized applying
only the exact reviewed plan and allowing its wrapper to run the built-in
convergence, qualification, and credential-free isolation gates. It did not
authorize an Anthropic credential or request, Console mutation, requirement-1
refresh, behavioral acceptance, requirement 3, or a qualification-flag change.

OpenTofu created worker `588826948`, updated only its firewall attachment, and
destroyed quarantined worker `588778422`. Both convergence passes succeeded;
the second reported `changed=0,failed=0` on both hosts. The standalone control
and worker qualifications passed. The wrapper then stopped with exit 1 because
the first A101 private-VPC management probe timed out to replacement private IP
`10.132.0.11:22`. No isolation or provider phase ran.

A read-only invocation of the exact installed management probe succeeded at
`2026-07-30T22:04:17Z` without a state change. DigitalOcean reported the worker
active and its firewall `succeeded`, with no pending changes and only the new
worker attached. Firewall attachment propagation is a supported inference, not
a directly observed cause at the timeout instant, and the sequence remains
failed rather than retried. The exact apply, convergence recaps, failure log,
post-stop state, and operational quarantine are recorded in
`2026-07-30-a115-m1m2-clean-worker-replacement-attempt.md`.

No qualifier retry, requirement-1 refresh, provider request, cap action,
behavioral acceptance, requirement-3 work, or qualification-flag change
followed. Continuing requires a new explicit bounded sequence and cannot reuse
replacement worker `588826948` under the reviewed plan's failed-successor
boundary.

## Quarantined-successor plan authorization

Jacob then explicitly authorized "a new clean-worker replacement plan plus A78
review." This operational grant is recorded here under A115 and does not mint
a new decision-log ruling; A119 is already taken. It authorizes generation and
fresh read-only review of a plan that replaces operationally quarantined worker
`588826948`. It does not authorize applying the plan, modifying or reusing the
current worker, requirement-1 refresh, an Anthropic credential or request,
either Console-limit action, behavioral acceptance, requirement 3, or a
qualification-flag change.

The resulting owner-only plan was generated from clean operational source
`d8b2955c4de050a67d932d763fd58f2509f34df5`. Its binary SHA-256 is
`62adfcaac371203a5c9127ed307f29fdbd1593e2f2a466ae22836551e9fd91c3` and
its rendered-plan SHA-256 is
`b77a32f12f3480e08496d6b8ff83fb38dc6c2b300999649ff0b9ad94169cafae`.
It replaces only worker `588826948`, updates only firewall
`01af87da-4951-4441-a1c8-ddfc0214811b`, and leaves seven resources as no-op.
The exact projection, live bracket, external registry retry, SQL-probe
corrections, operational-quarantine binding, and non-executing sequence are
recorded in
`2026-07-30-a115-m1m2-quarantined-successor-replacement-plan.md`. At this
point the plan remains unapplied and a fresh A78 review is required.

## Quarantined-successor plan review result

A78 reviewed exact plan-record commit
`9c40b086a3c59a5955ebd484f942319e02786c68`, binary plan
`62adfcaac371203a5c9127ed307f29fdbd1593e2f2a466ae22836551e9fd91c3`,
and rendered plan
`b77a32f12f3480e08496d6b8ff83fb38dc6c2b300999649ff0b9ad94169cafae`.
The reviewer returned **PASS with no material findings** after offline decode,
the complete focused gates, 17 plan mutations, and a corrected independent
31-case wrapper harness. The build seat adjudicated every observation under
A77 and sustained the PASS. The full review and adjudication are recorded in
`2026-07-30-a78-quarantined-successor-replacement-plan-review.md` and
`2026-07-30-a77-quarantined-successor-replacement-plan-adjudication.md`.

No repair or plan regeneration followed the PASS.

## Quarantined-successor apply authorization and stop

Jacob subsequently answered, `AUTHORIZE APPLY`. This operational grant applied
only the exact reviewed plan and its built-in wrapper sequence. OpenTofu
created successor worker `588858421`, moved only the reviewed worker-firewall
attachment, and destroyed operationally quarantined worker `588826948`. Both
convergence passes passed, and the second reported zero changes on both hosts.
The standalone control and worker qualifications passed.

The wrapper then stopped nonzero when the first A101 control-to-worker
private-VPC management probe timed out to `10.132.0.15:22`. The probe was not
retried, and no isolation or provider phase ran. The provider later reported
the exact firewall settled with zero pending changes and only successor
`588858421` attached, but that later readback does not establish the timeout's
cause. Successor `588858421` is operationally quarantined and ineligible for
repair or reuse under the reviewed failed-successor rule.

No requirement-1 refresh, credential, provider request, Console action,
behavioral acceptance, requirement-3 work, credential rotation, or
qualification-flag change followed. The complete record is
`2026-07-31-a115-m1m2-quarantined-successor-replacement-attempt.md`.

## A101 firewall-readiness source authorization and A9 stop

After A78 passed the stopped operational record and A77 adjudicated its
forward-looking finding, Jacob authorized a bounded source-only provider
firewall readiness precondition before A101, its tests and source mutations,
the full gates, and another A78 review. No live action or replacement plan was
authorized.

The candidate binds the exact post-apply OpenTofu worker and firewall IDs and
requires DigitalOcean to report that same firewall as `succeeded`, with zero
pending changes, exactly that worker attached, and no tags, before the wrapper
enters qualification. A101 itself remains one-shot and terminal.

The first focused test run failed on Python 3.9 annotation compatibility. The
one authorized repair corrected only that test compatibility issue. The
repeated focused suite then failed on three test-harness defects: numeric
counter interpretation, invalid-ID fixture construction, and a
prefix-sensitive attempt-count mutation assertion. Under A9 the build seat
stopped without a second repair. The candidate is preserved on the draft PR
only as a stopped failure artifact; full gates and A78 review did not begin.

The exact candidate boundary and failure log are recorded in
`2026-07-31-a115-a101-firewall-readiness-repair.md`. Further work requires a
new bounded authorization recorded here rather than as a new numbered ruling.

## A101 firewall-readiness harness repair and review handoff

Jacob authorized the three recorded test-harness repairs. The build seat
changed only numeric counter interpretation, invalid-ID fixture construction,
and exact-line mutation matching; the production helper and operator remained
byte-identical.

All 6 readiness tests and all 11 new source-only weakening mutations pass. The
combined replacement/readiness suite passes 13 of 13, all 47 Session 16 tests
pass, and all 25 spend tests plus the spend checker pass. Exact clean technical
commit `ec8f2c33b332a0fbc85c9b3709e81b4e903838df` passed the complete application
wrapper, including reproducible release, dependency, advisory, model, and
codebase-projection checks.

All three OpenTofu roots validate, all four Ansible lint profiles and syntax
checks pass, and 145 of 146 Ansible tests pass. Infrastructure and Ansible stop
only on the deliberate requirement-1 host-contract mismatch:
`bd36018284041c4ed12f2bea19248ec5f855cfa06f9d4823670a6d87d86d8e2f`
live versus
`eef6e16e54b6c0945f3874dae71063e8ef2248fea470f2fe4b2579ce22d52977`
current. No false evidence refresh follows.

The source-only repair is ready for A78 review. It authorizes no replacement
plan, host or cloud action, provider request, Console action, acceptance,
requirement-3 work, rotation, or qualification-flag change.

## A101 readiness review findings and bounded repair

A78 reviewed exact readiness record commit
`097a5b4acdf68fb27b173445f0df0ff6fb3b7e74` and returned NOT A PASS. The
helper accepted an empty or whitespace-only successful curl body because jq
1.6 exits zero when it produces no result. A78 also found unbound conditional,
state-cardinality, curl-failure, and object-type mutations, plus bearer exposure
in curl's argv.

The build seat reproduced and conceded all three findings under A77. Jacob
authorized a bounded source repair, its tests and mutations, full gates, and a
fresh A78 review. No new numbered ruling records the operational grant.

The repaired helper requires a nonempty body, jq output exactly `true`, and
HTTP status exactly 200; keeps curl HTTP failures fatal; and supplies the
validated bearer through config on standard input. Independent fixtures now
cover succeeded-with-pending, extra provider and state attachments, two state
workers, empty and whitespace bodies, a redirect with a ready body, and
malformed bearer input. The operator validator requires one direct fatal call
in the complete interval between the second converge and A101.

The focused repair suite passes 7 of 7 tests and rejects 24 source-only
weakenings. Exact clean repair commit
`69b38764a47c9de7d3e9941700d7d8bb8d06baec` passed the complete application
wrapper, including the reproducible release, dependency, advisory, model, and
codebase-projection gates.

All three OpenTofu roots validate. Stack, independence, worker-runtime, and
worker-qualification checks pass. Complete Ansible discovery passes 146 of 147
tests, and infrastructure plus Ansible stop only on the deliberately stale
requirement-1 host-contract binding. ShellCheck, all four production Ansible
lint profiles, and all four playbook syntax checks pass.

Fresh A78 source review remains pending. No live worker, DigitalOcean,
Anthropic, Console, acceptance, requirement-1, requirement-3, rotation, or
qualification-flag action occurred.

## Fresh readiness review and A9 stop

A78 reviewed exact record commit
`cdd931ec4545f426bf07bd53efd18673e140d346`. The production helper was sound
under A78's source and behavior matrix, but three additive overrides passed all
7 focused tests and all 24 shipped mutations: a last-value jq filter, later
900-second curl timeout options, and a later 600-second poll assignment.

The build seat independently reproduced each green mutant and conceded A78 F1
at medium severity under A77. The exact review and adjudication are
`2026-07-31-a78-a101-firewall-readiness-repair-source-review.md` and
`2026-07-31-a77-a101-firewall-readiness-repair-source-review-adjudication.md`.

A78 disclosed one unscoped grep that displayed review boilerplate and one
possible unauthenticated read-only DigitalOcean GET with literal placeholder
bearer `goodtoken`. Neither used a real credential or changed provider state.
Both are retained in the review record.

The authorized repair loop is exhausted. No further source or test repair was
made. A test-only repair, the complete gates, and another A78 review require a
new explicit bounded authorization under A115. No worker, cloud, Anthropic,
Console, requirement-1, acceptance, requirement-3, rotation, or
qualification-flag action followed.
