# A115 A101 private-VPC SSH read-only diagnosis

Status: **the historical A101 timeout is not reproduced now; ICMP fails while
TCP/22 succeeds; current zone mismatch and recycled-IP misdirection are
excluded; the historical cause remains unknown; no repair was made**

This is the record of Jacob's read-only diagnostic authorization for worker
`589089036`. The authorization ended at diagnosis. It did not authorize a
replacement, repair, convergence, qualification, Ansible run, firewall,
systemd, network, cloud, fixture, credential, provider, Console, or
qualification-flag mutation.

## Exact boundary

| Field | Value |
| --- | --- |
| diagnostic source | `76f5ea5d661456816da2c560f8405032b3bfb4e6` |
| `origin/master` | `43303c95b217f4da9f097d5ab4367bf52d3b0218` |
| shared checkout | clean on `master` at `43303c95b217f4da9f097d5ab4367bf52d3b0218` |
| prior apply-record review | PASS, no record finding ([A78 review](https://github.com/JacobStephens2/patchyard/pull/79#issuecomment-5148341814)) |
| worker | `589089036`, public `167.172.239.1`, private `10.132.0.11` |
| control plane | public `209.97.148.52`, private `10.132.0.17` |
| diagnostic interval | `2026-08-01T01:25:28Z` through `2026-08-01T01:27:03Z` |
| transcript | `/tmp/patchyard-a101-readonly-diagnosis-20260801T012528Z.log` |
| transcript mode and size | `conductor:conductor 0600`, 13,374 bytes |
| transcript SHA-256 | `9c25b2e9d8bcc4837f4cd7d251d7ee908c98da713063fb68746ebfea6ccbd62f` |

Every worker read used `167.172.239.1`, the public break-glass address. No
diagnostic shell was opened through the private path. The only private-path
actions were the authorized control-plane network probes targeting
`10.132.0.11`.

## Discriminator result

The observed result is a third case, not either of the two predicted branches:

- ICMP: **FAIL** - three packets sent, none received, exit `1`;
- prescribed `nc` TCP probe: **UNAVAILABLE** - `nc` is not installed, so exit
  `127` is not a network result;
- bounded read-only TCP equivalent: **PASS** - opening
  `/dev/tcp/10.132.0.11/22` completed inside five seconds with exit `0`; and
- independent worker-side confirmation: `sshd` recorded `Connection closed by
  10.132.0.17` at `2026-08-01T01:25:49Z`, the connection created by that probe.

Therefore the plain observed case is **ICMP fails but TCP/22 works**. It is not
"ICMP works but TCP does not" and it is not "neither works." The private SSH
transport failure seen at `2026-07-31T22:45:58Z` was not present during this
diagnostic snapshot. This is a TCP-connect observation only: no A101 probe,
qualification, authentication test, or repair was run, and the observation
does not retroactively convert the recorded A101 timeout into a pass.

## Hypothesis disposition

### H1 - zone mismatch

**Excluded as a current or persistent condition; not established or excluded
historically.** Worker `eth1` was `UP` with `10.132.0.11/16`. Active zone
`public` owned both `eth1` and `eth0`; `public` was also the default zone. The
full `public` zone carried the rich rule allowing SSH from `10.132.0.17/32`.
Thus the private interface and the qualifier-observed rule were in the same
zone at observation time. This snapshot cannot establish whether a transient
zone mismatch existed when A101 failed more than two and a half hours earlier.

### H2 - recycled-IP residue

**Excluded as a current control-plane neighbour or VPC-delivery condition; not
established or excluded historically.** The control-plane route selected
`eth1` with source `10.132.0.17`. Its neighbour entry for `10.132.0.11` was
`REACHABLE` at MAC `e6:48:95:45:6e:f4`, exactly the MAC reported by the live
worker's `eth1`. The TCP connection then arrived at this worker's `sshd` from
`10.132.0.17`. This excludes current delivery to the destroyed predecessor,
but a snapshot cannot prove which mapping existed at the earlier failure.

The evidence therefore supports **neither H1 nor H2** as a condition present
during diagnosis. It also excludes a current missing listener: `sshd` PID
`20730` listened on `0.0.0.0:22` and `[::]:22`. The ICMP loss is consistent
with the active zone's `DROP` target and absence of an ICMP allow rule, but no
packet trace or counter was taken and this record assigns no cause to that
loss.

## What remains unknown

No read taken after the fact establishes what silently dropped the A101 TCP
connection at `2026-07-31T22:45:58Z`, or what changed between that failure and
the successful TCP probe at `2026-08-01T01:25:49Z`. The current snapshot rules
out the persistent forms of the two proposed hypotheses; it does not rule out
their transient historical forms or establish any alternative cause. The root
cause remains unknown.

## Exact command transcript

The following is the complete owner-only transcript. Bracketed exit-status
lines were emitted locally immediately after each remote command.

```text
diagnostic transcript started: 2026-08-01T01:25:28Z
execution origin: orchestration host 142.93.121.94
control-plane access path: conductor@209.97.148.52 (public management path)
worker diagnostic target: 10.132.0.11 (private VPC)

$ ssh -T -i /var/lib/conductor/.ssh/id_ed25519 -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 conductor@209.97.148.52 -- 'ping -c3 -W2 10.132.0.11'
PING 10.132.0.11 (10.132.0.11) 56(84) bytes of data.

--- 10.132.0.11 ping statistics ---
3 packets transmitted, 0 received, 100% packet loss, time 2026ms

[local ssh/remote command exit status: 1]

$ ssh -T -i /var/lib/conductor/.ssh/id_ed25519 -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 conductor@209.97.148.52 -- 'timeout 5 nc -vz 10.132.0.11 22'
timeout: failed to run command ‘nc’: No such file or directory
[local ssh/remote command exit status: 127]

$ ssh -T -i /var/lib/conductor/.ssh/id_ed25519 -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 conductor@209.97.148.52 -- 'timeout 5 bash -c "exec 3<>/dev/tcp/10.132.0.11/22"'
[local ssh/remote command exit status: 0]

$ ssh -T -i /var/lib/conductor/.ssh/id_ed25519 -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 conductor@209.97.148.52 -- 'ip route get 10.132.0.11'
10.132.0.11 dev eth1 src 10.132.0.17 uid 1000
    cache
[local ssh/remote command exit status: 0]

$ ssh -T -i /var/lib/conductor/.ssh/id_ed25519 -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 conductor@209.97.148.52 -- 'ip neigh show 10.132.0.11'
10.132.0.11 dev eth1 lladdr e6:48:95:45:6e:f4 REACHABLE
[local ssh/remote command exit status: 0]

worker access path: conductor@167.172.239.1 (PUBLIC break-glass path)

$ ssh -T -i /var/lib/conductor/.ssh/id_ed25519 -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 conductor@167.172.239.1 -- 'ip -br addr'
lo               UNKNOWN        127.0.0.1/8 ::1/128
eth0             UP             167.172.239.1/20 10.17.0.14/16 fe80::7cb7:b8ff:fe1b:db1b/64
eth1             UP             10.132.0.11/16 fe80::e448:95ff:fe45:6ef4/64
[local ssh/remote command exit status: 0]

$ ssh -T -i /var/lib/conductor/.ssh/id_ed25519 -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 conductor@167.172.239.1 -- 'ip -br link'
lo               UNKNOWN        00:00:00:00:00:00 <LOOPBACK,UP,LOWER_UP>
eth0             UP             7e:b7:b8:1b:db:1b <BROADCAST,MULTICAST,UP,LOWER_UP>
eth1             UP             e6:48:95:45:6e:f4 <BROADCAST,MULTICAST,UP,LOWER_UP>
[local ssh/remote command exit status: 0]

$ ssh -T -i /var/lib/conductor/.ssh/id_ed25519 -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 conductor@167.172.239.1 -- 'firewall-cmd --get-active-zones'
public
  interfaces: eth1 eth0
[local ssh/remote command exit status: 0]

$ ssh -T -i /var/lib/conductor/.ssh/id_ed25519 -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 conductor@167.172.239.1 -- 'firewall-cmd --get-default-zone'
public
[local ssh/remote command exit status: 0]

$ ssh -T -i /var/lib/conductor/.ssh/id_ed25519 -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 conductor@167.172.239.1 -- 'firewall-cmd --info-zone=public'
Authorization failed.
    Make sure polkit agent is running or run the application as superuser.
[local ssh/remote command exit status: 253]

$ ssh -T -i /var/lib/conductor/.ssh/id_ed25519 -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 conductor@167.172.239.1 -- 'firewall-cmd --list-rich-rules'
Authorization failed.
    Make sure polkit agent is running or run the application as superuser.
[local ssh/remote command exit status: 253]

$ ssh -T -i /var/lib/conductor/.ssh/id_ed25519 -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 conductor@167.172.239.1 -- 'ss -lntp | grep -w 22'
LISTEN 0      128          0.0.0.0:22        0.0.0.0:*
LISTEN 0      128             [::]:22           [::]:*
[local ssh/remote command exit status: 0]

$ ssh -T -i /var/lib/conductor/.ssh/id_ed25519 -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 conductor@167.172.239.1 -- 'journalctl -u sshd --no-pager -n 50'
Jul 31 22:11:30 factory-worker.example.com systemd[1]: Starting OpenSSH server daemon...
Jul 31 22:11:30 factory-worker.example.com sshd[1102]: Server listening on 0.0.0.0 port 22.
Jul 31 22:11:30 factory-worker.example.com sshd[1102]: Server listening on :: port 22.
Jul 31 22:11:30 factory-worker.example.com systemd[1]: Started OpenSSH server daemon.
Jul 31 22:14:44 factory-worker.example.com sshd-session[16197]: Accepted publickey for conductor from 142.93.121.94 port 60548 ssh2: ED25519 SHA256:AaLUxQYjAVXt8fsPz8BorgfG/vHpQRjZi6DMs95SzdU
Jul 31 22:14:44 factory-worker.example.com sshd-session[16197]: pam_unix(sshd:session): session opened for user conductor(uid=1000) by conductor(uid=0)
Jul 31 22:15:56 factory-worker.example.com systemd[1]: Stopping OpenSSH server daemon...
Jul 31 22:15:56 factory-worker.example.com sshd[1102]: Received signal 15; terminating.
Jul 31 22:15:56 factory-worker.example.com systemd[1]: sshd.service: Deactivated successfully.
Jul 31 22:15:56 factory-worker.example.com systemd[1]: Stopped OpenSSH server daemon.
Jul 31 22:15:56 factory-worker.example.com systemd[1]: Starting OpenSSH server daemon...
Jul 31 22:15:56 factory-worker.example.com sshd[20730]: Server listening on 0.0.0.0 port 22.
Jul 31 22:15:56 factory-worker.example.com sshd[20730]: Server listening on :: port 22.
Jul 31 22:15:56 factory-worker.example.com systemd[1]: Started OpenSSH server daemon.
Jul 31 22:26:45 factory-worker.example.com sshd-session[20960]: Accepted publickey for conductor from 142.93.121.94 port 53716 ssh2: ED25519 SHA256:AaLUxQYjAVXt8fsPz8BorgfG/vHpQRjZi6DMs95SzdU
Jul 31 22:26:45 factory-worker.example.com sshd-session[20960]: pam_unix(sshd:session): session opened for user conductor(uid=1000) by conductor(uid=0)
Jul 31 22:33:31 factory-worker.example.com sshd-session[28389]: Accepted publickey for conductor from 142.93.121.94 port 43590 ssh2: ED25519 SHA256:AaLUxQYjAVXt8fsPz8BorgfG/vHpQRjZi6DMs95SzdU
Jul 31 22:33:31 factory-worker.example.com sshd-session[28389]: pam_unix(sshd:session): session opened for user conductor(uid=1000) by conductor(uid=0)
Jul 31 22:44:03 factory-worker.example.com sshd-session[30508]: Accepted publickey for conductor from 142.93.121.94 port 60612 ssh2: ED25519 SHA256:AaLUxQYjAVXt8fsPz8BorgfG/vHpQRjZi6DMs95SzdU
Jul 31 22:44:03 factory-worker.example.com sshd-session[30508]: pam_unix(sshd:session): session opened for user conductor(uid=1000) by conductor(uid=0)
Jul 31 22:45:40 factory-worker.example.com sshd-session[34873]: Accepted publickey for conductor from 142.93.121.94 port 55446 ssh2: ED25519 SHA256:AaLUxQYjAVXt8fsPz8BorgfG/vHpQRjZi6DMs95SzdU
Jul 31 22:45:40 factory-worker.example.com sshd-session[34873]: pam_unix(sshd:session): session opened for user conductor(uid=1000) by conductor(uid=0)
Jul 31 22:47:28 factory-worker.example.com sshd-session[34990]: Accepted publickey for conductor from 142.93.121.94 port 42832 ssh2: ED25519 SHA256:AaLUxQYjAVXt8fsPz8BorgfG/vHpQRjZi6DMs95SzdU
Jul 31 22:47:28 factory-worker.example.com sshd-session[34990]: pam_unix(sshd:session): session opened for user conductor(uid=1000) by conductor(uid=0)
Jul 31 22:47:29 factory-worker.example.com sshd-session[34990]: pam_unix(sshd:session): session closed for user conductor
Aug 01 01:25:49 factory-worker.example.com sshd-session[35265]: Connection closed by 10.132.0.17 port 33962
Aug 01 01:26:18 factory-worker.example.com sshd-session[35266]: Accepted publickey for conductor from 142.93.121.94 port 56164 ssh2: ED25519 SHA256:AaLUxQYjAVXt8fsPz8BorgfG/vHpQRjZi6DMs95SzdU
Aug 01 01:26:18 factory-worker.example.com sshd-session[35266]: pam_unix(sshd:session): session opened for user conductor(uid=1000) by conductor(uid=0)
Aug 01 01:26:18 factory-worker.example.com sshd-session[35266]: pam_unix(sshd:session): session closed for user conductor
Aug 01 01:26:19 factory-worker.example.com sshd-session[35306]: Accepted publickey for conductor from 142.93.121.94 port 56174 ssh2: ED25519 SHA256:AaLUxQYjAVXt8fsPz8BorgfG/vHpQRjZi6DMs95SzdU
Aug 01 01:26:19 factory-worker.example.com sshd-session[35306]: pam_unix(sshd:session): session opened for user conductor(uid=1000) by conductor(uid=0)
Aug 01 01:26:19 factory-worker.example.com sshd-session[35306]: pam_unix(sshd:session): session closed for user conductor
Aug 01 01:26:19 factory-worker.example.com sshd-session[35334]: Accepted publickey for conductor from 142.93.121.94 port 56178 ssh2: ED25519 SHA256:AaLUxQYjAVXt8fsPz8BorgfG/vHpQRjZi6DMs95SzdU
Aug 01 01:26:19 factory-worker.example.com sshd-session[35334]: pam_unix(sshd:session): session opened for user conductor(uid=1000) by conductor(uid=0)
Aug 01 01:26:20 factory-worker.example.com sshd-session[35334]: pam_unix(sshd:session): session closed for user conductor
Aug 01 01:26:20 factory-worker.example.com sshd-session[35372]: Accepted publickey for conductor from 142.93.121.94 port 56192 ssh2: ED25519 SHA256:AaLUxQYjAVXt8fsPz8BorgfG/vHpQRjZi6DMs95SzdU
Aug 01 01:26:20 factory-worker.example.com sshd-session[35372]: pam_unix(sshd:session): session opened for user conductor(uid=1000) by conductor(uid=0)
Aug 01 01:26:40 factory-worker.example.com sshd-session[35413]: Accepted publickey for conductor from 142.93.121.94 port 54960 ssh2: ED25519 SHA256:AaLUxQYjAVXt8fsPz8BorgfG/vHpQRjZi6DMs95SzdU
Aug 01 01:26:41 factory-worker.example.com sshd-session[35413]: pam_unix(sshd:session): session opened for user conductor(uid=1000) by conductor(uid=0)
Aug 01 01:26:41 factory-worker.example.com sshd-session[35413]: pam_unix(sshd:session): session closed for user conductor
Aug 01 01:26:41 factory-worker.example.com sshd-session[35463]: Accepted publickey for conductor from 142.93.121.94 port 54970 ssh2: ED25519 SHA256:AaLUxQYjAVXt8fsPz8BorgfG/vHpQRjZi6DMs95SzdU
Aug 01 01:26:41 factory-worker.example.com sshd-session[35463]: pam_unix(sshd:session): session opened for user conductor(uid=1000) by conductor(uid=0)
Aug 01 01:26:42 factory-worker.example.com sshd-session[35463]: pam_unix(sshd:session): session closed for user conductor
Aug 01 01:26:42 factory-worker.example.com sshd-session[35508]: Accepted publickey for conductor from 142.93.121.94 port 54984 ssh2: ED25519 SHA256:AaLUxQYjAVXt8fsPz8BorgfG/vHpQRjZi6DMs95SzdU
Aug 01 01:26:43 factory-worker.example.com sshd-session[35508]: pam_unix(sshd:session): session opened for user conductor(uid=1000) by conductor(uid=0)
Aug 01 01:26:43 factory-worker.example.com sshd-session[35508]: pam_unix(sshd:session): session closed for user conductor
Aug 01 01:26:43 factory-worker.example.com sshd-session[35537]: Accepted publickey for conductor from 142.93.121.94 port 54994 ssh2: ED25519 SHA256:AaLUxQYjAVXt8fsPz8BorgfG/vHpQRjZi6DMs95SzdU
Aug 01 01:26:43 factory-worker.example.com sshd-session[35537]: pam_unix(sshd:session): session opened for user conductor(uid=1000) by conductor(uid=0)
[local ssh/remote command exit status: 0]

diagnostic transcript ended: 2026-08-01T01:26:43Z

privileged read-only supplement (existing sudo authorization; no configuration action)

$ ssh -T -i /var/lib/conductor/.ssh/id_ed25519 -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 conductor@167.172.239.1 -- 'sudo -n firewall-cmd --info-zone=public'
public (active)
  target: DROP
  icmp-block-inversion: no
  interfaces: eth0 eth1
  sources:
  services: cockpit dhcpv6-client
  ports:
  protocols:
  forward: yes
  masquerade: no
  forward-ports:
  source-ports:
  icmp-blocks:
  rich rules:
	rule family="ipv4" source address="10.132.0.14/32" port port="9100" protocol="tcp" accept
	rule family="ipv4" source address="10.132.0.17/32" service name="ssh" accept
	rule family="ipv4" source address="10.132.0.14/32" port port="9187" protocol="tcp" accept
	rule family="ipv4" source address="142.93.121.94/32" service name="ssh" accept
[local ssh/remote command exit status: 0]

$ ssh -T -i /var/lib/conductor/.ssh/id_ed25519 -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 conductor@167.172.239.1 -- 'sudo -n firewall-cmd --list-rich-rules'
rule family="ipv4" source address="10.132.0.14/32" port port="9100" protocol="tcp" accept
rule family="ipv4" source address="10.132.0.17/32" service name="ssh" accept
rule family="ipv4" source address="10.132.0.14/32" port port="9187" protocol="tcp" accept
rule family="ipv4" source address="142.93.121.94/32" service name="ssh" accept
[local ssh/remote command exit status: 0]

$ ssh -T -i /var/lib/conductor/.ssh/id_ed25519 -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 conductor@167.172.239.1 -- 'sudo -n ss -lntp | grep -w 22'
LISTEN 0      128          0.0.0.0:22        0.0.0.0:*    users:(("sshd",pid=20730,fd=7))
LISTEN 0      128             [::]:22           [::]:*    users:(("sshd",pid=20730,fd=8))
[local ssh/remote command exit status: 0]

diagnostic transcript supplement ended: 2026-08-01T01:27:03Z
```

The first unprivileged firewalld detail reads were retained exactly. Their
polkit denial was not repaired or bypassed by changing policy; the same
read-only queries were repeated under the existing non-interactive sudo grant.
The elevated `ss` repeat exposed the owning process without changing it.

## Negative scope and stop boundary

No worker was destroyed, replaced, retried, repaired, rebooted, converged, or
qualified. `infra/replace-worker.sh`, Ansible, the qualifiers, and the
production isolation probe were not run. No command was run to mutate a
firewall, systemd unit, address, route, neighbour, nftables state, host file, or
cloud resource. Worker `589089036` remains operationally quarantined; the
successful one-time TCP connection does not authorize its reuse and does not
make Factory qualified.

The deliberately stale Anthropic issuance fixture was not refreshed. No
Anthropic credential was issued, no provider or Console request was made, no
paid inference occurred, neither limit changed, and requirement-2 spend work
did not resume. No requirement-1 behavioral acceptance or fixture refresh,
requirement-3 work, credential rotation, or provider qualification change
occurred. The policy still contains 13 providers and all 13
`credential_qualified` values are `false`.

## A78 diagnostic-record review request

A78 should review this exact record head from a fresh detached worktree and,
using read-only access only:

1. recompute the transcript byte count and SHA-256 and compare its exact
   commands, outputs, timestamps, and exit statuses with this record;
2. verify that `nc` absence is not reported as a failed TCP connection and that
   the successful bounded `/dev/tcp` probe is corroborated by the worker SSH
   journal;
3. verify the route, exact neighbour-to-worker MAC match, interface state,
   active/default zone identity, rich rule, and listener conclusions;
4. confirm that H1 and H2 are excluded only as current persistent conditions,
   no historical cause is assigned, and the prior A101 failure is not
   relabelled as a pass; and
5. confirm the no-repair stop, operational quarantine, negative scope,
   deliberately stale fixture, and all 13 false qualification flags.

A78 should return PASS or material findings without rerunning a transport
probe, qualifying or repairing the worker, changing live state, contacting a
provider or Console, refreshing a fixture, or issuing a credential.
