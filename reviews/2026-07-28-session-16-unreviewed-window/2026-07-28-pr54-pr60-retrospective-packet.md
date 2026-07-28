# Session 16 retrospective review packet: PRs #54-#60

Date: 2026-07-28

Reviewer seat: Opus 5 [xhigh] via Claude Code on Anthropic (A78)

Window under review: Factory PRs #54 through #60, inclusive

## Review purpose

All seven PRs merged during the attended Session 16 cutover without a review
comment from either reviewer seat. This packet does not retroactively pretend
that the merge-time review gate was satisfied. It gives Opus one bounded diff
and execution narrative to review after the fact so the unreviewed production
window is explicit, attributable, and either accepted with findings or repaired.

The changes were responses to installed-host evidence. None started a Session
17 behavioral acceptance case. Six changed installed behavior or qualification;
PR #58 changed only the execution record. The sequence upgraded the installed
Factory revision from the original cutover merge through `443779f9ab299c34a83b2637875902c9dd67ccb7`.

## Consolidated chronology

| PR | Merge commit | Installed finding | Change and reason | Production effect and proof |
| --- | --- | --- | --- | --- |
| [#54](https://github.com/JacobStephens2/patchyard/pull/54) | `a54627ee9f585a792a2ac1524ae877ac06b3e375` | The first exact-revision qualifier found that the installed systemd release would not expose the template properties through a bare `patchyard-child@.service` name. The rendered backup environment also failed shell parsing because the public age recipient contained whitespace. | Query a syntactically valid dummy child instance, and shell-quote every rendered backup value. Add regressions for both installed-only cases and add the credential rotation inventory. | First repair converge: control `changed=8`, worker `changed=0`; second: both `changed=0`. The qualifier crossed both former failure points. Secrets remained values supplied by Ansible, not committed material. |
| [#55](https://github.com/JacobStephens2/patchyard/pull/55) | `6f6a149fa13ef6f6ea06d309aece29f594d493cd` | The qualifier expected 19 Grafana column privileges, but the declared grants contained 20 after `run_class` joined `grafana_run_metrics`. | Correct the installed assertion to 20 and derive the regression expectation from the two declarative grant blocks, including an explicit `run_class` requirement. | First repair converge: control `changed=6`; second: `changed=0`. Live qualification proved 20 column privileges while `grafana_ro` remained denied raw request bodies, artifact paths, and table-level grants. No database grant was relaxed. |
| [#56](https://github.com/JacobStephens2/patchyard/pull/56) | `87e22cb7b6722de4c4d37f6b4296090370d450b9` | Immediately after restart, the supervisor metrics endpoint returned HTTP 200 with an empty body. Describing a counter does not create a rendered series, and no behavioral run could be started merely to warm `factory_runs_total`. | Register and set an unlabeled `factory_supervisor_up=1` gauge during metrics initialization. Qualify that truthful idle-process signal and assert that the fixture does not warm `factory_runs_total`. | First repair converge: control `changed=10`; second: `changed=0`. The complete control, worker, A101, and independence qualifier passed with the supervisor idle. This changed the live metrics surface but not run state. |
| [#57](https://github.com/JacobStephens2/patchyard/pull/57) | `eaeedca070520bf568407b9c00850b1783eafcb5` | The reviewed worker replacement created droplet `588010686`, then clean provisioning stopped because DNF rejected the checksum-pinned Remi PHP RPMs with `NOKEY` for key ID `478f8947`. `remi-release` had installed the key file but had not imported it into the RPM database. | Declare exact primary fingerprint `B1ABF71E14C9D74897E198A8B19527F1478F8947`. After installing the checksum-pinned `remi-release` bootstrap, import only `/etc/pki/rpm-gpg/RPM-GPG-KEY-remi.el9` with that fingerprint, before installing the pinned PHP packages. Keep DNF GPG checking enabled. | Repaired worker converge imported the one expected key and installed the checksum-pinned PHP packages; the second pass changed nothing. Two complete qualifiers passed after DigitalOcean finished the firewall attachment. The production Firecracker isolation probe and post-probe no-residue qualifier passed. No manual package installation, broad repository-key fetch, signature bypass, old-worker state restore, or additional worker authority occurred. |
| [#58](https://github.com/JacobStephens2/patchyard/pull/58) | `ba95cfb01ab5c8dffd298bf5e4a675478000544e` | PR #57 had repaired and completed worker replacement, but the durable cutover record still ended at `replacement_failed`. | Record the repaired converges, qualifiers, worker identity, isolation artifact path and hashes, no-residue result, and current deploy marker. | Documentation and generated metrics only. It made no host, database, cloud, or runtime change. |
| [#59](https://github.com/JacobStephens2/patchyard/pull/59) | `57581d29c1166e1cf521efed897943cfade20dd5` | Two requests had been legitimately `closed` on 2026-07-23 while their runs remained `reviewing`. Authorized dashboard kills reached the exact runs but failed safely because `finish_run` tried to rewrite each request to `killed` while its non-null `closed_at` still enforced `requests_closed_state_consistent`. | In `finish_run`, read the current request state and preserve `closed`, `failed`, or `killed` instead of rewriting an accepted terminal request outcome. Still terminalize the run, append the terminal event, and let the control path release the lease. Add a PostgreSQL regression for a closed request with a reviewing run. | After merge, both exact controls completed: runs became `killed`, `run.killed` events were appended, worker teardown completed, leases were released, and each request remained `closed` with its original `closed_at`. The repair did not reopen requests, erase an earlier terminal decision, or generalize permission to mutate arbitrary terminal data. |
| [#60](https://github.com/JacobStephens2/patchyard/pull/60) | `443779f9ab299c34a83b2637875902c9dd67ccb7` | The first attended backup encrypted and remotely verified its generation, but stopping the dashboard implicitly stopped requiring Caddy before the script could record Caddy as prior-active. The unit exited success with the public edge still down. | Put Caddy first in the ordered prior-state service list so it is observed and stopped before dashboard dependency propagation. Lock the order into the Session 16 contract and runbook. | After two clean converges and a full qualifier, generation `20260728T031717Z` verified remotely and Caddy, dashboard, and supervisor were all active immediately afterward without intervention. Public `/healthz` returned `ok`. |

## Detailed review focus: PR #57

PR #57 changed clean worker provisioning at a supply-chain trust boundary. The
important sequence is exact and should be reviewed as a sequence:

1. Ansible installs the `remi-release` bootstrap whose SHA-256 was already
   pinned in desired state. This is the only step using `disable_gpg_check:
   true`, because no earlier Remi trust root exists on the clean host.
2. The bootstrap places `/etc/pki/rpm-gpg/RPM-GPG-KEY-remi.el9` locally.
3. `ansible.builtin.rpm_key` calculates and requires the declared full primary
   fingerprint before importing that local key.
4. DNF installs the exact PHP NEVRAs with `disable_gpg_check: false`.

The new regression proves bootstrap-before-key-before-packages ordering, the
exact key path and fingerprint, and continued GPG enforcement. Live evidence
then proved the new worker had the expected imported key and exact PHP 8.4.21
packages, passed its filesystem qualifier, ran the production isolation probe,
and returned to zero transient directories, Firecracker/jailer processes, and
boundary taint.

Residual review questions:

- The bootstrap RPM remains the trust-root exception. Is its pinned SHA-256 and
  HTTPS origin sufficient for phase 1, or should its signing key be carried by
  an independently controlled mirror as well?
- The key is constrained by fingerprint but is not independently pinned by
  file digest. Would a digest add meaningful defense beyond the fingerprint?
- Does any Remi key rotation need an explicit two-key transition procedure so
  a clean replacement cannot silently widen trust?

## Detailed review focus: PR #59

PR #59 changed request/run lifecycle behavior only for a previously impossible
combination: an accepted terminal request with a still-nonterminal child run.
Before the change, `finish_run` derived the request result from the run result
and rewrote the request. After the change, it first reads `request_status` and
skips that rewrite when the request is already `closed`, `failed`, or `killed`.
It does not skip run finalization or event creation.

The regression constructs a request, claims it, appends a run, moves the run to
`reviewing`, closes the request through the repository operation, records
`closed_at`, issues the normal kill control, and then proves:

- request state is still `closed`;
- `closed_at` is byte-for-byte unchanged;
- run state is `killed`;
- the control completes through the same transaction path.

The attended retry added the production evidence missing from the unit test:
both `run.killed` events existed, worker teardown reported complete, and both
leases were released. The scope is intentionally asymmetric: terminal request
state wins over a later child-run outcome because it is the already accepted
operator decision. Review should confirm that this precedence is correct for
all three preserved request states and that no caller relies on a killed run
rewriting an already-failed request.

## Cross-PR observations

- The sequence is evidence-driven but costly: four qualifier assertions or
  desired-state assumptions (#54-#57), one execution record (#58), one
  lifecycle edge (#59), and one backup cleanup edge (#60) were discovered only
  on the installed topology.
- The repairs consistently failed closed. No host was edited to pass a check,
  no package pin or signature check was bypassed, no stale lifecycle row was
  rewritten by SQL, and no backup success was claimed until public service
  state was verified.
- #54, #55, and #57 bind their installed defects structurally. #56's source
  assertion is backed by the installed qualifier, and #59 adds a real
  disposable-PostgreSQL lifecycle regression. #60's original array-literal
  assertion did not bind its systemd dependency defect; the accepted repair in
  this PR replaces it with an executed service-state fixture.
- The unreviewed window itself is a process defect. Installed-host urgency did
  not remove the need for a second seat; it only made the missing review easy
  to rationalize one repair at a time.

## Opus review disposition

The [review disposition](https://github.com/JacobStephens2/patchyard/pull/64#issuecomment-5104517060)
is `accepted-with-repair`. Opus accepted #54-#59 as-is and found that #60's
single array-literal assertion could not fail for the systemd dependency
interaction that caused the defect, or when the unit exited zero with Caddy
still down.

The #60 finding is conceded under A77. This PR's repair snapshots every
prior-active service before issuing any stop, then executes that behavior
against a fixture where stopping the dashboard also stops Caddy. A second
fixture makes `systemctl start caddy` return success while leaving Caddy down;
the backup cleanup must return `service_resume_failed` with exit 28.

The residual #57 questions are answered:

- **#57.1:** a pinned SHA-256 over HTTPS is sufficient for the phase-1
  bootstrap RPM. The reviewed digest is the trust root; a separately carried
  copy of the same signing key would relocate rather than strengthen it.
- **#57.2:** a file digest adds nothing beyond the full signing-key
  fingerprint. It would pin one encoding of the same key material, not a
  distinct security property.
- **#57.3:** Remi key rotation needs an explicit two-key transition: import and
  prove the new key, remove the predecessor, and prove the predecessor is
  rejected. The non-blocking A-14 inventory follow-up is included in this PR.

This disposition closes the retrospective review gap for PRs #54-#60 after
the #60 repair is accepted. It is not permission to start Session 17
acceptance.
