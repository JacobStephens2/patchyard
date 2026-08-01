# A77 adjudication - Anthropic spend enforcement PR #78

Candidate reviewed by A78: `038fd9d4f9e80f9d40b86bc58ef1481ec896eff6`.

Disposition: nine findings conceded, two refuted with evidence. The single A9 repair loop was consumed before adversarial review, so no conceded source or live-fixture finding is repaired in this PR. They are escalated with the live failure log. Requirement 2 remains unqualified, acceptance remains paused, and all 13 `credential_qualified` flags remain false.

## A78-1 - Concede

The initial nonzero provider-qualification run necessarily set `BOUNDARY_TAINTED`. The work log confirms the marker was later resolved by an approved clean worker replacement, not by clearing it:

- initial marker: run `anthropic-s2-20260729-412f8a1777`, detected `2026-07-29T22:25:26Z` at `result-filesystem-validation` line 470;
- reviewed plan binary SHA-256 `ebf3ef3de8dc8a0bbf73936193ddfbde064d49cd35ab0b42699ce1334a1c69e7`;
- reviewed plan text SHA-256 `8c8e5230aaedc17d708064ca36d8300ec81cb209dd7b7efa0d40aa9f905d7c71`;
- plan: one replacement add, one firewall update, one destroy;
- old worker `588324505` destroyed; new worker `588590370` created at `167.71.81.211`, private `10.132.0.15`, with no old state copied;
- current OpenTofu state independently reports worker `588590370`, created `2026-07-30T01:11:07Z`.

The committed initial failure record omits this containment and replacement history. That is an evidence-record defect.

## A78-2 - Concede

The operator-reported 02:05Z `$1.00` readback and 02:07Z `$50.00` restoration cannot be ordered around the journaled 02:21:34Z to 02:21:53Z run. The current record correctly refuses to use them as ordering evidence but cannot establish the cap value in force at the probe. No independent audit artifact was available to resolve the discrepancy.

## A78-3 - Concede

The `02:26:10Z` cost snapshot was only 4 minutes 17 seconds after the repaired failure, while the initial cost took about 2 hours 51 minutes to settle. A read-only A77 Cost Report observation at `2026-07-30T03:04:16Z` still returned `$7.68168`, but 42 minutes remains shorter than the observed initial settlement lag. The `$0` incremental repair-cost claim is therefore not settled evidence.

`$6.68168` is exact initial recorded spend above the displayed $1.00 cap. It is not an A113 overshoot measured at an attributable denial.

## A78-4 - Concede

Experiment: the committed jq predicate accepted the exact three-key error envelope and rejected an otherwise identical spend-attributable envelope containing one compatible extra top-level key. The exact-key checks are stricter than the value contract requires, and the exported status cannot diagnose which shape check failed.

## A78-5 - Concede

Source ordering confirms `FAILURE=anthropic-spend-denial-not-observed` remains active through request-ID equality, Date parsing, credential deletion, and directory removal. Any failure after the envelope predicate but before line 319 publishes a false provider-outcome label. This conflicts with A114's honest-record rule.

## A78-6 - Concede

The failure trap writes `/result/status` before the spend branch's success-only credential deletion on transport, 200, unexpected-response, and post-denial parsing exits. The launcher prevents host-visible evidence leakage and the VM is destroyed, but the guest does not satisfy delete-before-any-result on these failure paths.

## A78-7 - Concede

The Console evidence proves a lower workspace value was accepted and displayed. It does not prove independent server-side enforcement or its delay semantics. The initial eight accepted calls and the unbound cap-at-repair timestamp make the documentation's positive binding statement too strong. This triggers the task's stop condition rather than authorizing an engineering workaround or A113 amendment.

## A78-8 - Refute with evidence

The current mutual exclusion is the intended A9 safety lock, not a requirement defect. A9 forbids another repair or paid attempt after this terminal failure. A future qualified result therefore requires a new governance authorization and a reviewed checker/schema change; it must not become admissible merely by adding a success file beside the stop record. Exact-shape validation makes unreviewed edits fail loudly. It does not claim to independently verify Console history.

Deleting the failure record would also be a reviewed diff and is not the only technical path: a later ruling can amend the checker to retain historical failures and admit a newly authorized result. Under the current ruling, rejecting both records together is correct.

## A78-9 - Concede

Two source-only experiments resolve the claim:

- Adding `curl --retry 2` to the spend request left `check-anthropic-spend.py` passing. `check-anthropic-issuance.py` still failed because the guest image recipe changed, so the complete gate catches the source mutation indirectly, but the spend-specific one-probe checker misses it.
- Hoisting `rc=$(final_exit_status "$rc")` above residue evaluation left all ten child-launcher tests passing. The test does not bind the required ordering and can admit the A114 defect.

## A78-10 - Concede

Experiment: with `TEARDOWN_COMPLETE=true`, `STATE=completed`, and a simulated `write_terminal` return code of 1 under `set +e`, the committed `final_exit_status 0` logic returned 0. The launcher does not feed output purge, chown, chmod, terminal-write, or unlock failures into the teardown state. A successful child can therefore retain exit 0 despite one of those failures.

## A78-11 - Refute with evidence

The factual hash observation is correct: recomputation gave these mismatches:

- `105a3c6`: expected host contract `b9809d04409e1b6052c2116688fb939118c8c2f67ff66e66e8547c33937c5400`, recorded `3c3bafbce1a6c6d3945e9eddcdcf8d020d4b5dfaf91f349d7ac85745a05ca372`;
- `84bdf99`: expected `0541aacebf3a01e42fdb2ca671c7ea8ab763902bab61760a196e667d3bd0c900`, recorded `b9809d04409e1b6052c2116688fb939118c8c2f67ff66e66e8547c33937c5400`.

The finding's defect classification is refuted. Neither intermediate commit was pushed, reviewed, deployed, or proposed as a merge target. Requirement 1 was rerun after the shared source reached its final form, and PR head binds all five reproducible digests and passes the complete gate. The repository has no rule that every intermediate feature commit must be independently deployable or bisect-green.

## Escalation

No requirement 3 work begins. No additional Anthropic inference request, source repair, `BOUNDARY_TAINTED` removal, worker replacement, provider qualification flag, or behavioral acceptance case is authorized by this adjudication.

At adjudication time, the unresolved decision belonged to Jacob: amend A113 or authorize a future clean requirement 2 attempt with a new repair budget and independently timestamped cap evidence, or close the Anthropic requirement 2 path as unsatisfied. The current worker remained quarantined and required a separately reviewed replacement before any future Factory worker run. A115 below resolves that decision without changing the historical dispositions.

## A115 disposition - 2026-07-30

Jacob accepted the Anthropic causal-proof amendment and one-time reauthorization as A115. The historical A77 dispositions above are unchanged. A115 now authorizes successor requirement-2 work only after every conceded source and evidence defect is repaired and a clean-worker replacement is separately reviewed. The July 29-30 records remain unqualified, and the current worker remains quarantined and ineligible for reuse.
