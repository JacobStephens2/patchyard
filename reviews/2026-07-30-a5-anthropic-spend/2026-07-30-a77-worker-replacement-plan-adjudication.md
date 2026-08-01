# A77 adjudication - clean-worker replacement plan

The build seat adjudicated A78's plan findings against the exact saved plan and
technical repair commit `6c161e91ea0107f6c9d8bb9dac4eb88a27450213`.

## M1 - Concede

The original apply arm checked only a literal yes flag and a broad resource
shape. It did not compare the saved plan with the digest A78 reviewed. The
repair mirrors the established restore-drill content binding and checks the
digest again after input preflight. A mismatched-plan experiment exits 2 before
preflight or apply. A source-only weakening of the comparison fails the suite.

## M2 - Concede the absent binding; refute merged-only as absolute

The original wrapper did not bind the source revision or distinguish ordinary
merged operation from A115's one-time successor workflow. That is conceded.

The claim that this exact successor must already be merged is refuted by the
more specific authorization. A115 authorizes one reviewed successor
implementation and qualification attempt, whose live proof must exist before
the deliverable PR can merge. Jacob then explicitly authorized the plan and
said: "I also authorize replacing the worker and or making the provider request
if useful." The normal merged-only rule remains. An exact unmerged source now
needs both its full reviewed commit ID and the literal A115 exception flag.

Experiments show a wrong revision exits 2, an unmerged revision without the
A115 flag exits 2, and the same exact revision with the flag reaches the mocked
preflight and apply in that order. Weakening either revision comparison or the
merged-or-A115 branch fails the suite.

## M3 - Concede

The original wrapper first validated converge inputs only when the post-cloud
converge began. An unset accounts-file experiment reproduced the failure. The
repair calls the existing non-mutating `--check-inputs` mode before apply. A
mocked failure reaches only the `preflight` event, never `apply`; removing the
preflight fails the suite.

## Action-shape observation - Concede

Destroy-before-create and firewall no-op did not describe the reviewed plan and
were unnecessary allowances. Both were removed. Mutating either allowance back
in fails the executable tests.

## Re-review findings and observations

A78's stale-runbook finding is conceded but non-blocking because the installed
operator fails closed with actionable missing-variable errors. Changing it
after the one repair and PASS would stale the exact source review, so it is
recorded for a separately authorized later repair.

The two requirement-1 digest failures are conceded and already known. The A115
procedure requires requirement 1 to be rerun after shared source changes; no
historical evidence is rewritten before that live rerun.

The seven defense-in-depth observations are accepted. None changes the PASS:
the exact plan and revision were human-authorized, the A115 flag is deliberately
narrow and should later be removed, tool/build failures remain recoverable and
fail the wrapper, the plan sits in a mode-0700 directory as a mode-0600 file,
the same operator controls the local remote-tracking ref and explicit flag,
mutation tests bind the second digest call, and A78 independently proved the
Terraform tree identical across both commits.

No second repair followed the PASS.
