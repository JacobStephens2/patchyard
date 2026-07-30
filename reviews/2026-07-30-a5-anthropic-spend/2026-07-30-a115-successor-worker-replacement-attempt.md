# A115 successor worker-replacement attempt

Status: **replacement and convergence passed; first A101 qualification timed
out; separately authorized continuation passed through requirement-1 refresh;
no requirement-2 provider request**

This is the operational record for Jacob's authorization: "I authorize the
repair, its review, and a new sequence." It is recorded under A115 rather than
as a new numbered ruling. A119 remains reserved.

## Reviewed boundary

| Field | Value |
| --- | --- |
| apply source | `673b89fbfad5c287f79f9d6b7d046c35f1881cee` |
| bootstrap repair | `cec58db1ccf20dbf05e80445cd6845186a6ea379` |
| saved plan SHA-256 | `944f8af406006cee8c92ec377e374fd697ba53d472290b42b565846f20dec550` |
| rendered plan SHA-256 | `2bf7b41af785b8e9eb40b159e01be0274c0f553993c3abcefb967b91c584ee66` |
| A78 verdict | PASS, no material finding |
| old worker | `588761785`, public `64.225.18.250`, private `10.132.0.11` |
| new worker | `588778422`, public `159.203.171.240`, private `10.132.0.15` |
| pre-apply state | `paused=0,full_stop=0,active=0`; backup service inactive |
| cap/provider state | no cap action and no provider request |

The plan directory was mode 0700 and both plan files were mode 0600. The
GitHub App key and dashboard account roster were materialized in a separate
mode-0700 directory as mode-0600 files. The private-key and input-shape
preflight returned `converge_inputs_valid`. The production-tag firewall check
passed immediately before apply.

## Exact apply and repaired bootstrap proof

OpenTofu applied exactly `1 added, 1 changed, 1 destroyed`:

- created worker `588778422` from the stock Rocky Linux 9 image;
- attached firewall `01af87da-4951-4441-a1c8-ddfc0214811b` to it; and
- destroyed failed worker `588761785`.

The new host completed `cloud-init status --wait`. The exact repaired bootstrap
installed `firewalld`, `python3`, and `sudo` using the coherent `--nobest`
transaction, asserted all three RPMs, and enabled firewalld. The Rocky base
assertions passed. This is the live proof that the immutable-bootstrap repair
closed the earlier split-version failure on a fresh provider image.

First convergence passed:

```text
factory-control.example.com : ok=221 changed=14 failed=0
factory-worker.example.com  : ok=94  changed=71 failed=0
```

The fresh worker built the production parity root filesystem, installed the
pinned Firecracker and PHP/PHPUnit artifacts, installed the A115 one-shot
provider transport and A114 teardown operation, and enabled the private-egress
policy. No bearer was minted and no provider request was made.

Second convergence was fully idempotent:

```text
factory-control.example.com : ok=216 changed=0 failed=0
factory-worker.example.com  : ok=84  changed=0 failed=0
```

The standalone control and worker qualifications then passed.

## A101 stop

The first complete `qualify.sh` stopped at its first control-to-worker private
VPC probe:

```text
qualifying A101 private-VPC management transport
ssh: connect to host 10.132.0.15 port 22: Connection timed out
wrapper exit status: 1
```

The isolation probe, post-probe qualification, and every Anthropic phase did
not run. The worker was not tainted because the provider transport and
Firecracker isolation probe were never entered.

Read-only diagnosis made no host, firewall, cloud, cap, or provider change. At
`2026-07-30T18:02:24Z`, the exact installed control-plane operation
`patchyard-management-ssh worker probe` succeeded to the same
`10.132.0.15:22`. Worker SSH logs recorded the `factory-manager` public-key
acceptance from control private IP `10.132.0.17`. Worker `sshd` and `firewalld`
were active; its host firewall admitted SSH only from `10.132.0.17/32` and
orchestration break glass `142.93.121.94/32`. The worker had both declared
addresses and listened on port 22.

DigitalOcean then reported firewall
`01af87da-4951-4441-a1c8-ddfc0214811b` as `succeeded`, with no pending changes
and only droplet `588778422` attached. The droplet was active in NYC3. Because
provider firewall status was not sampled at the instant of timeout, the record
does not claim a directly observed pending state. The no-change transition
from timeout to success, plus healthy host state, is consistent with the known
DigitalOcean attachment-propagation interval and the prior Session 16 example;
that causal label remains an inference.

## Stop boundary

The later read-only probe does not rewrite the failed qualification into a
pass. No qualification retry, isolation probe, requirement-1 refresh, workspace
cap change, bearer mint, Anthropic request, acceptance case, requirement-3
work, or provider qualification flag change followed. Continuing requires a
new bounded sequence authorization; it does not presently require a source or
host repair.

## Authorized continuation

Jacob subsequently answered, "I authorize the continuation." That operational
authorization is recorded under A115 rather than as a new numbered ruling;
A119 remains reserved. It covered one fresh qualifier, one production isolation
probe, a post-probe qualifier, one requirement-1 refresh, a final qualifier,
and assessment of the remaining cap and provider prerequisites. It authorized
no source or host repair, Console mutation, behavioral acceptance,
requirement-3 work, or provider qualification-flag change.

The continuation used a detached exact-source worktree at technical revision
`673b89fbfad5c287f79f9d6b7d046c35f1881cee`. Its first local qualifier command
stopped before contacting a live host because that new worktree had no
initialized OpenTofu data directory. `tofu init -reconfigure` initialized only
that local ignored directory with the repository's lock-file providers. No
infrastructure or host state changed. The rerun then passed all four layers:
control, worker, A101 private-VPC management transport, and independence.

The production isolation probe passed as run
`s4-probe-20260730-70ac5dbc8d`. Its control-plane artifact directory is
`/var/lib/patchyard/artifacts/worker-replacement-continuation-20260730T181103Z`.
The sanitized artifact hashes are:

| Artifact | SHA-256 |
| --- | --- |
| `change.patch` | `435853c4d5712877b7eec91f5edeff093504c717abcc21712058185ea7822cd1` |
| `evidence.json` | `b5b6ce67c3e3578e5061835cff98f6111ff29208cc7097be7cdf3fee5cdcd083` |
| `rationale.txt` | `7a0c036d360924489a5249f1cf11caecc9c3df1a7da6ab1766ffee577115c333` |

The evidence reported zero residual processes, mounts, namespaces, veth
interfaces, and nftables state. Its provider boundary was the credential-free
OpenAI 401 isolation probe, not an Anthropic credential or paid request. The
post-isolation qualifier passed all four layers.

Requirement 1 then passed as run `anthropic-i1-20260730-399c37c157`, using a
fresh five-minute WIF bearer and `GET /v1/models?limit=1`. Anthropic returned
HTTP 200, request ID `req_011CdYhK71cBRNdQFQyZ9EUk`, and model
`claude-opus-5`. The exchange request ID was
`req_011CdYhHoJis4sYthS2CEkjP`; issuance was
`2026-07-30T18:13:16Z` through `2026-07-30T18:18:16Z`. The control-plane
artifact directory is
`/var/lib/patchyard/artifacts/anthropic-issuance-delivery-requirement2-successor-20260730T181314Z`.
Its sanitized artifact hashes are:

| Artifact | SHA-256 |
| --- | --- |
| `change.patch` | `9ad97cf0310918118c2094d26c5843e2bbeb1c2a4fbe9a8b3cc8c82a684c5cbc` |
| `evidence.json` | `b28f4218bc688ff5818f11cf0e42a97769b785ed791673d4f325b324d59c2193` |
| `rationale.txt` | `eeec98baddec78ce5584e4acd888afdff9d44824379d9a08bc8352c2c3eea67d` |

The repository copy of the sanitized requirement-1 evidence is byte-exact to
that `evidence.json`. The checker rejected the first manual transcription
because `qualification_phase: "none"` was absent; adding the observed field
made the repository hash equal the live artifact hash. Both Anthropic checkers,
the 139-test Ansible unit suite, and the secret-pattern scan then passed. A
final complete qualifier passed all four layers. Independent residue checks
found no taint marker, child process, network namespace, veth, nftables, or
runtime residue; the control services and private management probe remained
healthy.

This continuation establishes a clean, qualified successor and refreshes the
shared requirement-1 proof. It did not change either Anthropic limit, mint a
requirement-2 bearer, make a paid Messages request, start behavioral
acceptance, or change any `credential_qualified` flag. Requirement 2 still
requires a fresh bounded Console readback at the reviewed $50.00 workspace
limit before its first paid positive control.

## Continuation repository gates

The exact continuation tree passed the complete local application,
infrastructure, and Ansible wrappers. This included the 26-case spend-source
mutation harness, 139 of 139 Ansible unit tests, all OpenTofu roots, four
Ansible production lint profiles, four playbook syntax checks, reproducible
release verification, dependency and advisory checks, model checks, and the
byte-exact codebase projection. The local host has no usable Docker daemon or
PostgreSQL service, so GitHub's pinned disposable services remain authoritative
for those integration cases.

At pushed head `1ab2833`, GitHub infrastructure run `30570197052` passed. The
application run `30570197008` prepared its disposable PostgreSQL service, then
failed one of 39 preview tests: the missing-selector case observed
`child_timed_out` rather than the expected `contract_rejected` result. The
other 38 passed, including the Docker-backed Traefik boundary case. The exact
failing test then passed five consecutive local executions, each in 5.8 to 6.1
seconds. No source was changed or test weakened. The available GitHub token was
not permitted to invoke the rerun endpoint, so this audit-only record update
creates a new committed head and a second authoritative CI execution while
preserving the first failure.

## First requirement-2 operational attempt

Jacob's tightly bracketed Console readback and the first successor
operational-acceptance attempt are recorded in
`2026-07-30-a115-spend-run-root-repair.md`. The attempt stopped with local curl
status 23 before producing a provider observation. A source permission defect
is conceded, worker `588778422` is boundary-tainted and permanently ineligible
for reuse, and the bounded repair is awaiting A78 review. No second provider
request, cap mutation, or worker replacement followed.
