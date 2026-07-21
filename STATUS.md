# Session 0 build status

Updated 2026-07-21 for session restart. This is a handoff record, not evidence
that PLAN Session 0 has exited.

## Resume location

- Isolated worktree: `/srv/orchestration/patchyard-s0`
- Branch: `session-0-bootstrap`
- Draft PR: <https://github.com/JacobStephens2/patchyard/pull/10>
- Last implementation commit before this handoff: `9acdc43`
- Hosted CI run: <https://github.com/JacobStephens2/patchyard/actions/runs/29816740938>
  (`success`, 1m13s)

Do not work from `/srv/orchestration/patchyard`; that shared checkout belongs
to the orchestration agent. Reuse the existing isolated worktree and branch.

## Completed

- OpenTofu 1.12.0 is installed on the orchestration host and pinned in desired
  state. AWS CLI 2.33.0 is also installed.
- Exact provider locks exist for DigitalOcean 2.95.0, AWS 6.55.0, and GitHub
  6.13.0.
- The A96 S3 backend, native lockfiles, SSE-S3, and enforced client-side
  PBKDF2/AES-GCM encryption are encoded for all three OpenTofu roots.
- DigitalOcean desired state encodes the two Rocky 9 hosts, existing-VPC
  placement, attachment to reviewed existing Patchyard tags, SSH identity, cloud
  firewalls, and state-derived Ansible inventory.
- AWS desired state encodes the hand-created backend resources, unmanaged access
  key exception, Route 53 policy replacement, attachment migration, and
  `factory.example.com` A record.
- GitHub desired state encodes repository settings and protected `master`.
- Ansible desired state encodes base hardening, exporters on both hosts,
  control-plane prerequisites/credential-free checkout, the secret-free worker,
  private-network egress rejection, transient paths, qualification, convergence,
  and clean replacement.
- Hosted infrastructure CI uses `ubuntu-latest` and a Rust cache action. No
  self-hosted runner, Tempo/OTLP collector, or Session 3 runtime choice exists.
- `tools/check-infra.sh`, `tools/check-ansible.sh`, stack exclusions,
  independence structure, `git diff --check`, and the credential-shape scan pass.

The draft PR body contains PLAN Session 0's checklist, evidence for every item,
Escalations, and the no-buffer statement.

## Live state and blockers

No cloud resource was created, imported, changed, or deleted during the session.

### DigitalOcean

The process that created the PR still held the old token: read requests to
`/v2/tags` and `/v2/firewalls` both returned HTTP 403. The newly created
`conductor-v3` token had not entered that process. Never print or persist either
token; restart through the normal conductor secret-injection path.

The browser-reported v3 scopes remain insufficient for the Session 0 contract:
OpenTofu owns the cloud firewalls and clean worker replacement, so the token
also needs firewall create/update/delete and droplet delete. Tags are existing
Patchyard tags, not resources for this root to invent or create. Their canonical names
are not in the repository and must come from a reviewed live tag listing. Supply
them as a JSON list in `TF_VAR_existing_eta_tag_names` for plan/apply. If the
DigitalOcean API requires tag write authority merely to attach/detach existing
tags, escalate that exact requirement rather than widening by assumption.

The live `factory.example.com` Route 53 record count was `0`.

### AWS A96 adoption

`infra/import-a96.sh` initializes the encrypted S3 backend successfully, then
fails closed before import because the Route 53 provider identity cannot read
the hand-created IAM/bucket resources. The state user can use state objects but
cannot read/manage bucket configuration. A temporary, narrowly scoped operator
identity with the required IAM and S3 configuration lifecycle authority is
needed. The backend access key must remain unmanaged and must not be used as the
operator credential.

### GitHub adoption

`infra/import-github.sh` fails closed before import because the injected PAT
receives HTTP 403 from the branch-protection API. Repository settings and
classic branch protection need a provider credential with repository
administration authority.

### A68 exit interpretation

The structural independence check passes. Full serve/authenticate/run evidence
cannot exist yet: PLAN's ground rule forbids end-to-end claims before
dependencies exist, while Sessions 1-14 build the supervisor, PostgreSQL,
service identities, dashboard/auth, publisher, and cutover. This is recorded as
an Escalation in PR #10 for Jacob to rule; do not pull those sessions into
Session 0 without that ruling.

The fleet Prometheus `file_sd` entries remain an external-repository handoff
after both private host addresses exist.

## Safe restart sequence

```bash
cd /srv/orchestration/patchyard-s0
git status --short --branch

# Confirm the relaunched process can read the required DO collections without
# displaying the token. Expected after correct injection: 200 and 200.
curl -sS -o /dev/null -w 'tags=%{http_code}\n' \
  -H "Authorization: Bearer $DO_API_TOKEN" \
  'https://api.digitalocean.com/v2/tags?per_page=1'
curl -sS -o /dev/null -w 'firewalls=%{http_code}\n' \
  -H "Authorization: Bearer $DO_API_TOKEN" \
  'https://api.digitalocean.com/v2/firewalls?per_page=1'

./tools/check-infra.sh
PATH="$PWD/infra/ansible/.venv/bin:$PATH" ./tools/check-ansible.sh
```

After reviewing the live tag names and confirming all required DigitalOcean
write/delete scopes, set `TF_VAR_existing_eta_tag_names`, create a fresh absolute
plan directory, and run `infra/plan.sh digitalocean "$PLAN_DIR"`. Do not apply
until the human-readable plan has been reviewed. Continue with the staged
operations in `infra/README.md`; update PR #10 with command evidence and keep it
draft until every unresolved exit item is genuinely met.

Do not delete `conductor-v2` merely because the new token was created. Delete it
only after the relaunched process has verified v3 and a reviewed DigitalOcean
plan proves the required access path.
