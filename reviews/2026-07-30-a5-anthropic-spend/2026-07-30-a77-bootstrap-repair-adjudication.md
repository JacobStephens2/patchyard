# A77 adjudication - immutable-bootstrap repair

The build seat adjudicated every A78 observation against exact commit
`cec58db1ccf20dbf05e80445cd6845186a6ea379`.

## Defense-in-depth 1 - Concede

In-memory mutations adding `bootcmd`, `write_files`, or `yum_repos` each passed
`validated_bootstrap_command`. The focused contract binds this repair, not the
entire cloud-init attack surface. No such key exists in current source, so this
does not defeat the reviewed command or permit a source-only weakening of it.
A future whole-document allowlist would be defense in depth and is outside the
one repaired failure.

## Defense-in-depth 2 - Concede the hard-coded execution; preserve the binding

The functional test invokes `/bin/bash -ceu` directly rather than reusing the
parsed argv. An independent source-only mutation of the template to `bash -cu`
nevertheless raised `ValueError`: exact structural validation binds the outer
argv before the functional test runs. A78's coordinated template-and-validator
mutation was also rejected by the mutation no-op assertion. The test could be
clearer, but the checkable source-only contract remains effective.

## Defense-in-depth 3 - Concede

Changing `ssh_pwauth` to true and removing `disable_root` passed the focused
bootstrap validator. Those lines are byte-identical to the parent, so this is a
pre-existing coverage boundary rather than a regression or a bypass of the
package repair. Expanding the repair into a complete credential-surface binding
would exceed its authorized cause.

## Defense-in-depth 4 - Concede

Source projection confirmed `ignore_changes = [user_data]` on the control and
worker droplets and its absence on `restore_drill`. The README sentence is too
general when a drill exists. The drill defaults absent, the live failed worker
sequence has no drill, and both ordinary and worker-only plan guards reject an
unexpected drill action. This does not block the fresh worker plan; that plan
must still prove only worker replacement plus firewall update and visibly carry
the repaired user-data command.

## Disposition

A78 returned PASS with no material finding, and all four checkable observations
are reproduced and nonblocking. No second source repair follows the PASS. The
authorized next gate is generation and adversarial review of a fresh exact
worker-only plan. No cap or provider action is opened by this adjudication.
