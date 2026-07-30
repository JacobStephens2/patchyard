# A115 immutable-bootstrap repair

Status: **source repair implemented; A78 review pending**

## Authorization and boundary

After the failed clean-worker replacement, Jacob authorized the next bounded
step: "I authorize the repair, its review, and a new sequence." This is an
operational grant under A115, not a new decision-log ruling. A119 remains
reserved.

The grant covers one immutable-bootstrap source repair, its tests and mutation
checks, A78 review, and - only after a PASS - a fresh reviewed worker
replacement sequence. It does not by itself authorize reuse of failed worker
`588761785`, a cap action, a provider request before worker qualification,
behavioral acceptance, requirement 3, or a qualification-flag change.

## Reproduction

The failed worker retained the stock image's coherent installed pair:

```text
python3-3.9.25-7.el9_8.x86_64
python-unversioned-command-3.9.25-7.el9_8.noarch
```

A read-only `dnf --cacheonly --assumeno` projection reproduced the bootstrap
failure. The default best-candidate solver selected
`python3-3.9.25-7.el9_8.2` from BaseOS and returned 1 because the installed
AppStream package requires exact `python3-3.9.25-7.el9_8`.

The identical cached projection with `--nobest` resolved a transaction that
retains the coherent installed Python pair and installs firewalld plus its nine
dependencies. It proposed 10 installs, skipped only the conflicting newer
Python build, and reached the transaction prompt. `--assumeno` then aborted it;
no package or service changed during the experiment.

## Repair

The cloud-init `packages` module provides no place to select the coherent
solver behavior. The repair removes that three-package list and runs one
explicit command under `bash -ceu`:

```text
dnf -y --nobest install firewalld python3 sudo;
rpm -q firewalld python3 sudo;
systemctl enable --now firewalld
```

This does not erase dependencies or skip broken packages. The first command
must produce one satisfiable transaction; the second proves all three direct
prerequisites are installed; only then may the service be enabled. `bash -e`
makes each boundary terminal on failure. `package_update: true` remains so the
transaction uses current metadata.

## Executable contract and mutations

The focused test parses the rendered YAML structure, requires one exact
`bash -ceu` runcmd, and runs the command against instrumented `dnf`, `rpm`, and
`systemctl` executables. Success must visit all three boundaries in order.
Injected failure at each boundary must return nonzero and prevent every later
boundary.

Six source-only weakenings are permanent mutation subcases and all fail the
contract:

1. remove `--nobest` and restore best-only solving;
2. replace it with dependency-erasing `--allowerasing`;
3. remove the shell's fail-fast `-e`;
4. remove the RPM presence assertion;
5. enable firewalld before the assertion; and
6. restore the inflexible cloud-init `packages` module.

The unmutated focused suite passes three tests. The local cloud-init schema
validator accepts the repaired template. No cloud resource, package, service,
worker state, credential, provider, or cap was changed by the repair.
