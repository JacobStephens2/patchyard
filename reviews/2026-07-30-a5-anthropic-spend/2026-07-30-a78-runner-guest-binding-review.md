# A78 runner, guest, and install-task binding review

## Review identity

- Exact commit: `62d2502be0fab15c7e5740390d7824077a995e4e`
- Seat: A78
- Pairing: Opus 5 [max] via Claude Code on Anthropic
- Requested effort: `max`
- Actual effort: Claude Code exposed no actual-effort value; the reviewer
  confirmed the request but did not claim an unobservable realized setting.
- Isolation: fresh detached worktree; no files under `reviews/` read; all
  mutations in disposable `/tmp` copies; worktree clean before and after.
- External effects: none. No credential access, provider call, worker action,
  or external-state change occurred.

## Verdict

**PASS. Both target findings are closed. No material finding remains.**

## Target 1: runner and installed writers

The reviewer independently verified that the checker binds the complete
issuance runner at SHA-256
`45ff683fdd9c9226e6fa07c5ea1de52bb7581f77eb231c42ea6c05c256feaa87`
and the complete worker install-task source at SHA-256
`110cbffc6db188aafa1364e88901249290653134b7f0adc559152abf3f35df40`.
The focused test recomputes both digests and pins the checker at SHA-256
`231676da8fb3ca579556b9b78e63374ae206003e7cfdaa150668297aaf8a5815`.

Five novel runner bypasses all made the real checker exit nonzero with the
complete-runner diagnostic:

1. append `|| true` to the installed-launcher comparison;
2. relax the installed-path hash-record expression;
3. derive the expected launcher digest from the installed launcher;
4. place the transport comparison block behind an always-false requirement
   guard; and
5. change `CHECKOUT_ROOT` to `/var/tmp/patchyard`.

Two novel worker-task destination spellings were rejected by the complete task
digest. A direct checker weakening that dead-coded the IPv6 literal check made
the checker itself exit zero but failed the focused test on its pinned checker
digest.

The reviewer also verified the containment chain. The installed runner compares
the installed launcher and one-shot client to checkout source before bearer
minting. An overwrite of either installed executable therefore fails closed
unless the complete, pinned runner is also changed.

## Target 2: spend-guest assertions

The checker binds the complete spend guest at SHA-256
`229346fb350297b298c1b752188c0f7762ef9d5de77572156843070fecfcc654`,
and the focused test recomputes the same digest. Three novel guest weakenings -
a negated credential-drive assertion, `|| true` on a receipt assertion, and an
injected early exit - were all rejected.

The reviewer counted twenty-six real-checker mutation cases and confirmed all
24 focused tests and the unmutated checker pass.

## Defense-in-depth observations

### A78-D1: guest execution path is not a hard-coded source binding

The complete guest source is pinned, but `build-parity-image` and the guest
systemd unit are not pinned by reviewed constants. Adding a builder command
that removes the credential-drive assertion from the installed rootfs guest,
then updating the self-consistent recipe pin, left worker-runtime,
worker-qualification, the spend checker, and all 24 focused tests green. An
equivalent systemd `ExecStartPre` substitution behaved the same way.

This is not material to the target closure. The complete pinned launcher
independently omits the credential drive, provides an empty provider-hosts file,
and byte-compares the guest outputs with host-generated inputs. The complete
pinned runner reasserts the receipt fields. A subverted guest can suppress its
duplicated assertions but cannot make the host transport spend twice or forge a
qualifying result.

The retained documentation sentence, "The guest image recipe remains a
complete binding of the guest surface," is inaccurate in this preflight state:
the recipe digest binds live evidence to current repository bytes, but is not a
reviewed hard-coded source binding against coordinated source and pin changes.

### A78-D2: singular-writer check is literal-string defense in depth

After coordinately updating the task and checker pins, an added duplicate
literal destination still failed the singular-writer check. Three alternate
spellings passed under the same coordinated re-pin: a templated loop
destination, an `install` command, and a Jinja-composed one-shot destination.
The complete task digest rejects every such change at the reviewed commit; the
literal check is an additional readable tripwire, not the primary binding.

### A78-D3: later writers can live outside the pinned task file

A handler appended to `roles/worker/handlers/main.yml` under the already
notified worker-egress listener, or a new later role in `site.yml`, is outside
the task-file digest. An appended launcher-overwrite handler left the checker
and all 24 focused tests green. The pinned runner's installed-vs-checkout
comparison contains the effect before bearer minting.

### A78-D4: the terminal test file is not pinned

A coordinated edit can weaken guest source, update source constants in checker
and test, then update the checker constant in the test; the test file itself is
not pinned. A demonstrated coordinated weakening of two guest delivery
assertions left the checker and all 24 tests green. This requires changing the
test and every reviewed constant together rather than weakening a bound source
alone.

### A78-D5: gate wiring is not itself bound

Deleting the spend-checker invocation from `tools/check-infra.sh` leaves the
focused 24-test suite green. The independent focused digest assertions remain,
so a composite unwiring plus guest weakening still fails the focused suite.

### A78-D6: complete-file pins add change friction

Unrelated changes anywhere in the 410-line worker task source or 667-line
general-purpose guest now require coordinated Anthropic-spend constant updates;
guest changes also update the image recipe. This is the coupling cost of the
authorized complete-boundary design, not a correctness defect.

## Regression check

The parent and reviewed commits produced the same expected repository result:
127 of 129 Ansible tests passed, with only the disclosed requirement-1 live
image-recipe and host-contract evidence stale. Earlier additional failures in
`.git`-less disposable copies were identified as experiment artifacts, not
repository regressions.

The reviewer attempted eleven novel in-bound source mutations, three
singular-destination evasions under coordinated re-pin, two outside-task
writer locations, two guest execution-path substitutions, one checker
weakening, one gate unwiring, one composite, and three coordinated re-pin
variants.

**Final verdict: PASS. No live or provider action occurred.**
