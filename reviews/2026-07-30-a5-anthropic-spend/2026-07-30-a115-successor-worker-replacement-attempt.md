# A115 successor worker-replacement attempt

Status: **replacement and convergence passed; first A101 qualification timed
out; sequence stopped; no provider request**

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
