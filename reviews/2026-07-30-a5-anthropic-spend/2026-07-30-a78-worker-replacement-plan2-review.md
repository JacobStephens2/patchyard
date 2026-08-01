# A78 successor worker-replacement plan review

Review target:

- source revision: `673b89fbfad5c287f79f9d6b7d046c35f1881cee`;
- saved binary plan SHA-256:
  `944f8af406006cee8c92ec377e374fd697ba53d472290b42b565846f20dec550`;
- rendered plan SHA-256:
  `2bf7b41af785b8e9eb40b159e01be0274c0f553993c3abcefb967b91c584ee66`;
- failed replacement target: DigitalOcean droplet `588761785`;
- replacement reason: prove immutable-bootstrap repair `cec58db` on a fresh
  worker, without reusing the failed host.

A78 ran Claude Code with Opus 5 at requested effort `max` in a detached
read-only worktree. The review session was
`4e92fc86-84fd-491a-a9f8-cb9b0339d716`. Claude Code exposed no realized-effort
field, so this record claims the requested setting only. The reviewer neither
regenerated nor applied the plan, accessed DigitalOcean, connected to either
host, changed a provider cap, nor made a provider request.

## Verdict - PASS

A78 independently verified both hashes and owner-only modes, decoded the saved
plan without network access, and found exactly two acting resources:

- `digitalocean_droplet.worker`: `["create","delete"]`, replacing droplet
  `588761785` from the stock Rocky Linux 9 image;
- `digitalocean_firewall.worker`: `["update"]`, changing only its attached
  droplet while retaining the reviewed rules.

The other seven resources were no-op. The restore-drill resource was absent.
Only the worker address outputs changed. The worker's planned `user_data` SHA-1
was `bc402dfdc683c7b582aaab68b6e0ca30b359952d`, byte-identical to an independent
render from current source and containing the exact repaired `bash -ceu`,
`dnf -y --nobest`, RPM assertion, and firewalld enable sequence. The before
value bound the failed worker's old template. The SSH surface was unchanged.
The apply wrapper bound the exact plan digest, exact revision, preflight, action
shape, and post-preflight digest recheck. A78 returned **PASS** with no material
finding.

## Defense-in-depth observations

A78 reported nine non-blocking observations:

1. the action-shape gate does not inspect every changed attribute;
2. output changes are not separately gated;
3. the production-tag firewall check is point-in-time;
4. create-before-destroy has an unavoidable attachment-propagation interval;
5. plan inspection obtains the existing broad state-backend credential;
6. input preflight cannot prove that a later build will complete;
7. one actor controls the short check-to-apply interval;
8. the earlier quarantined worker should be proved absent; and
9. account droplet headroom and NYC3 size availability should be proved before
   apply.

A78's mutations B1-B8, covering out-of-scope resource actions, failed the
shape gate. Mutations B9 and B10 showed that benign output-only changes and
foreign/snapshot-like worker attributes can pass the broad action gate. They do
not describe the reviewed bytes, which were pinned by digest and inspected in
full.

Before apply, the build seat proved old worker `588590370` returned HTTP 404,
the production-tagged droplet list contained no orphan Factory worker, the
account used 19 of its 500-droplet limit, and `s-8vcpu-16gb` was available in
NYC3. The production-tag firewall check passed immediately before apply.
