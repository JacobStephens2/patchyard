# Patchyard Factory → Amazon Bedrock (Claude Haiku 4.5) — Server Agent Guide

**Audience:** the orchestration agent (supervisor) on the orchestration VM
(`/srv/orchestration/patchyard/`).
**Purpose:** how to authenticate to AWS Bedrock and invoke Claude Haiku 4.5
(with reasoning / extended thinking) from the lane-A implement worker, without
ever placing standing credentials inside the untrusted worker.
**Set up:** 2026-07-17. AWS account `000000000000` (Educational Travel
Adventures), region `us-east-1`.

---

## 1. Model

| Field | Value |
|---|---|
| Provider | Amazon Bedrock (serverless, on-demand) |
| Foundation-model ID | `anthropic.claude-haiku-4-5-20251001-v1:0` |
| Inference-profile ID (use this) | `us.anthropic.claude-haiku-4-5-20251001-v1:0` |
| Region | `us-east-1` |
| Routing scope | US geographic cross-Region inference |
| Reasoning | Claude Code `--effort high`; raw Messages requests can use `thinking: { type: "enabled", budget_tokens: N }` |

Bedrock runs the model on AWS infra. Nothing is downloaded or hosted locally —
the server only makes authenticated HTTPS calls. The one-time Anthropic use-case
form and AWS Marketplace product enablement are complete. The live 2026-07-17
retest passed text inference, the exact-file floor check 3/3, and image reading.

## Current boundary - read before using

The model/provider/harness pair is qualified, but the factory runtime is not
built. The tests ran on the orchestration VM, not on A57's dedicated worker
droplet or inside Firecracker/Podman there.

| Layer | Status |
|---|---|
| AWS account, Anthropic use-case form, Marketplace product | Complete |
| `factory-supervisor` → 15-minute `factory-bedrock-invoke` STS flow | Verified live |
| Claude Code 2.1.212 → pinned Haiku 4.5 inference profile | Verified live |
| Standard Claude Code exact-file floor | PASS 3/3 |
| Image reading through Claude Code `Read` | Content pass; strict JSON-format miss |
| Child-process environment allowlist | PASS once on 2026-07-18; only temporary AWS credentials plus runtime basics |
| OpenTofu + Ansible secret-free worker droplet (A57) | **Phase-1 scope; not built** |
| Firecracker/Podman isolation and Bedrock-only network egress | **Not built or tested** |
| Unattended per-run/aggregate spend enforcement | **Not built** |
| Full fixture gauntlet and shadow mode | **Not run** |

The allowlisted child-process check proves the launcher can remove the
orchestration process's standing secrets before `claude` starts. It does not
prove VM escape containment, filesystem containment, or egress enforcement.

## 2. Identities created (the two-tier credential design)

This deliberately mirrors the factory trust architecture: the supervisor holds
standing keys; the worker only ever receives short-lived, role-scoped creds.

**Tier 1 — assuming identity (supervisor only):**
- IAM user: `factory-supervisor`
  - ARN: `arn:aws:iam::000000000000:user/factory-supervisor`
  - Inline policy `AssumeFactoryBedrockInvoke`: allows **only**
    `sts:AssumeRole` on the Tier-2 role. No Bedrock, no anything else.
  - Access key ID and secret: **1Password** (do not hardcode or log).

**Tier 2 — role that actually invokes Bedrock:**
- IAM role: `factory-bedrock-invoke`
  - ARN: `arn:aws:iam::000000000000:role/factory-bedrock-invoke`
  - Trust policy: only `factory-supervisor` may assume it.
  - Inline policy `factory-bedrock-invokePolicy`:
    `bedrock:InvokeModel` + `bedrock:InvokeModelWithResponseStream`
    scoped to the Haiku 4.5 foundation-model + `us.` inference-profile ARNs.

## 3. Credential flow (per run)

Target phase-1 runtime (A57; not built yet):

```
factory-supervisor (static keys, 1Password, supervisor env ONLY)
      │  sts:AssumeRole  (DurationSeconds=900)
      ▼
factory-bedrock-invoke  → temporary {AccessKeyId, SecretAccessKey, SessionToken}
      │  delivered per run to tmpfs/env inside the remote execution boundary
      ▼
secret-free worker droplet → Firecracker/Podman → invokes Haiku 4.5
```

Rules:

- The supervisor alone receives the static `factory-supervisor` keys.
- The launcher mints a new STS triple for every run and constructs the child
  environment from an allowlist; inheriting the supervisor environment is a
  boundary failure.
- The phase-1 worker receives only the short-lived STS triple, never the
  prefixed supervisor variables or any other orchestration secret.
- The phase-1 worker execution boundary's egress must be restricted to
  `bedrock-runtime.us-east-1.amazonaws.com`. That restriction is not present in
  the current direct-host qualification topology.

Qualification topology: the supervisor minted STS credentials and launched
Claude Code as a child process on this VM. The final boundary audit used a new
empty `HOME`, an isolated `CLAUDE_CONFIG_DIR`, and an explicit environment-name
allowlist. See the [dated evidence](../research/claude-code/2026-07-17-claude-code-bedrock-haiku.md).

## 4. Environment / config

**Supervisor env (from 1Password — supervisor process only):**
```
AWS_BEDROCK_ACCESS_KEY  = op://example-vault/aws-factory-supervisor/access-key
AWS_BEDROCK_SECRET_ACCESS_KEY = op://example-vault/aws-factory-supervisor/secret-access-key
AWS_BEDROCK_IAM_USER_NAME = op://example-vault/aws-factory-supervisor/iam-user
AWS_BEDROCK_IAM_USER_ARN = op://example-vault/aws-factory-supervisor/iam-user-arn
AWS_BEDROCK_IAM_ROLE     = op://example-vault/aws-factory-supervisor/iam-role
AWS_BEDROCK_IAM_ROLE_ARN = op://example-vault/aws-factory-supervisor/iam-role-arn
AWS_BEDROCK_IAM_ROLE_TRUST_POLICY = op://example-vault/aws-factory-supervisor/iam-role-trust-policy
```
The canonical mapping is `/srv/orchestration/env.tpl`; the
`claude-orchestrator` wrapper resolves it from 1Password at process start.
Changes to that template require a new wrapper-launched session. The access
key, secret, and role ARN are required at runtime. The other values are
recovery/audit metadata.

If any required `AWS_BEDROCK_*` variable is empty, stop: the wrapper was not
used or injection failed. Do not ask a user to paste the credential.

The prefixed names are intentional. This process's standard
`AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` belong to the separate Route 53
identity. Never overwrite those globally or let an SDK silently select them for
the STS call.

**Worker env (injected per run, short-lived only):**
```
AWS_ACCESS_KEY_ID       = <from STS>
AWS_SECRET_ACCESS_KEY   = <from STS>
AWS_SESSION_TOKEN       = <from STS>
AWS_REGION              = us-east-1
AWS_DEFAULT_REGION      = us-east-1
CLAUDE_CODE_USE_BEDROCK = 1
ANTHROPIC_MODEL         = us.anthropic.claude-haiku-4-5-20251001-v1:0
```

## 5. Network egress required

Allowlist (HTTPS/443):
- `sts.us-east-1.amazonaws.com` — supervisor only, to mint each STS session.
- `bedrock-runtime.us-east-1.amazonaws.com` — worker inference.
- `bedrock.us-east-1.amazonaws.com` — control-plane/list only; optional.

Also required: outbound TLS with current CA roots, working DNS, NTP-synced clock
(SigV4 fails on >5 min skew). No inbound ports. No static bearer token in headers —
Bedrock uses SigV4-signed requests.

## 6. Code

**Future supervisor implementation — mint short-lived creds (TS):**
```ts
import { STSClient, AssumeRoleCommand } from "@aws-sdk/client-sts";

const sts = new STSClient({
  region: "us-east-1",
  credentials: {
    accessKeyId: process.env.AWS_BEDROCK_ACCESS_KEY!,
    secretAccessKey: process.env.AWS_BEDROCK_SECRET_ACCESS_KEY!,
  },
});
const { Credentials } = await sts.send(new AssumeRoleCommand({
  RoleArn: process.env.AWS_BEDROCK_IAM_ROLE_ARN,
  RoleSessionName: `factory-run-${runId}`,
  DurationSeconds: 900,
}));
// inject Credentials.{AccessKeyId, SecretAccessKey, SessionToken} into the worker
```

**Worker — invoke Haiku 4.5 through Claude Code:**
```bash
export CLAUDE_CODE_USE_BEDROCK=1
export AWS_REGION=us-east-1
export AWS_DEFAULT_REGION=us-east-1
export ANTHROPIC_MODEL=us.anthropic.claude-haiku-4-5-20251001-v1:0

claude -p --model "$ANTHROPIC_MODEL" --effort high --output-format json \
  "<task>"
```

For tool-using workers, retain the standard Claude Code prompt and expose the
specific tools with `--allowedTools`. The qualified floor command used
`--allowedTools Write`. A minimal-mode variant using `--bare --tools Write`
returned prose that claimed to write the file but made no tool call in 3/3
runs; do not substitute that variant without a separate qualification.

### Manual end-to-end smoke on this VM (tested, no AWS CLI)

Run this only from a wrapper-launched shell. It sends the static credential to
`curl` over stdin rather than placing it in process arguments, keeps the STS
response in shell memory, and starts Claude from an environment-name allowlist.
Never enable shell tracing (`set -x`) around this flow.

```bash
set +x
set -euo pipefail

for required in AWS_BEDROCK_ACCESS_KEY AWS_BEDROCK_SECRET_ACCESS_KEY AWS_BEDROCK_IAM_ROLE_ARN; do
  if [ -z "${!required:-}" ]; then
    printf 'missing required injected variable: %s\n' "$required" >&2
    exit 1
  fi
done

sts_xml=$(
  {
    printf 'aws-sigv4 = "aws:amz:us-east-1:sts"\n'
    printf 'user = "%s:%s"\n' "$AWS_BEDROCK_ACCESS_KEY" "$AWS_BEDROCK_SECRET_ACCESS_KEY"
    printf 'header = "Content-Type: application/x-www-form-urlencoded; charset=utf-8"\n'
    printf 'data-urlencode = "Action=AssumeRole"\n'
    printf 'data-urlencode = "Version=2011-06-15"\n'
    printf 'data-urlencode = "RoleArn=%s"\n' "$AWS_BEDROCK_IAM_ROLE_ARN"
    printf 'data-urlencode = "RoleSessionName=factory-haiku-manual-smoke"\n'
    printf 'data-urlencode = "DurationSeconds=900"\n'
  } | curl --fail --silent --show-error --config - \
      'https://sts.us-east-1.amazonaws.com/'
)

read -r temp_access temp_secret temp_token expiration < <(
  python3 -c 'import sys, xml.etree.ElementTree as ET
root = ET.fromstring(sys.stdin.read())
ns = {"s": "https://sts.amazonaws.com/doc/2011-06-15/"}
c = root.find(".//s:Credentials", ns)
print(c.findtext("s:AccessKeyId", namespaces=ns),
      c.findtext("s:SecretAccessKey", namespaces=ns),
      c.findtext("s:SessionToken", namespaces=ns),
      c.findtext("s:Expiration", namespaces=ns))' <<< "$sts_xml"
)

run_dir=$(mktemp -d /tmp/claude-bedrock-haiku-smoke.XXXXXX)
worker_home=$(mktemp -d /tmp/claude-bedrock-haiku-home.XXXXXX)
worker_config=$(mktemp -d /tmp/claude-bedrock-haiku-config.XXXXXX)

(
  cd "$run_dir"

  export PATH=/var/lib/conductor/.local/bin:/usr/local/bin:/usr/bin:/bin
  export HOME="$worker_home" USER=conductor LOGNAME=conductor
  export SHELL=/bin/bash LANG=C.UTF-8
  export AWS_ACCESS_KEY_ID="$temp_access"
  export AWS_SECRET_ACCESS_KEY="$temp_secret"
  export AWS_SESSION_TOKEN="$temp_token"
  export AWS_REGION=us-east-1 AWS_DEFAULT_REGION=us-east-1
  export CLAUDE_CODE_USE_BEDROCK=1 CLAUDE_CONFIG_DIR="$worker_config"
  export ANTHROPIC_MODEL=us.anthropic.claude-haiku-4-5-20251001-v1:0

  for env_name in $(compgen -e); do
    case "$env_name" in
      PATH|HOME|USER|LOGNAME|SHELL|LANG|AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY|AWS_SESSION_TOKEN|AWS_REGION|AWS_DEFAULT_REGION|CLAUDE_CODE_USE_BEDROCK|CLAUDE_CONFIG_DIR|ANTHROPIC_MODEL) ;;
      *) unset "$env_name" ;;
    esac
  done

  claude -p --model "$ANTHROPIC_MODEL" --effort high \
    --allowedTools Write --output-format json --max-budget-usd 0.10 \
    'Create a file named muse-smoke.txt in the current directory containing exactly the word: factory'
)

test "$(wc -c < "$run_dir/muse-smoke.txt")" -eq 7
cmp -s "$run_dir/muse-smoke.txt" <(printf factory)
printf 'PASS; artifacts: %s; STS expires: %s\n' "$run_dir" "$expiration"

unset temp_access temp_secret temp_token expiration sts_xml
```

For real work, the supervisor exports the recorded base SHA without a Git
remote, sends it plus the read-only request inputs to a fresh directory on the
worker droplet, and derives tools and `--max-budget-usd` from factory policy.
The launcher constructs the same minimal environment inside the selected
Firecracker/Podman boundary rather than copying the supervisor's environment
and deleting a few known secrets. The STS triple exists only in memory/tmpfs
for that run and expires or is revoked at teardown.

**Optional raw API smoke (requires AWS CLI v2, which is not currently installed
on the orchestration VM):**
```bash
aws bedrock-runtime invoke-model \
  --model-id us.anthropic.claude-haiku-4-5-20251001-v1:0 \
  --region us-east-1 \
  --body '{"anthropic_version":"bedrock-2023-05-31","max_tokens":64,"messages":[{"role":"user","content":"ping"}]}' \
  --cli-binary-format raw-in-base64-out \
  /tmp/out.json && cat /tmp/out.json
```

## 7. Spend / rate controls (do not skip)

IAM grants no dollar limit. Neither AWS Service Quotas nor a normal AWS Budget
is a hard dollar cap: Service Quotas accepts increase requests, and budget data
and alerts can lag. Enforce per-run and aggregate limits in the factory before
granting unattended use:

- Use Claude Code's `--max-budget-usd` for each headless run.
- Apply the factory's own request/token concurrency limiter before invocation.
- Add an AWS Budget for delayed defense-in-depth alerting. A budget action can
  apply a deny policy, but it is not an instantaneous cutoff.
- Treat the account's existing Bedrock quotas as an outer ceiling, not a
  configurable low spend cap.

Record chosen limits in `docs/decision-log.md`.

## 8. Rotation / hygiene

- Rotate `factory-supervisor` keys periodically; secret lives only in 1Password.
- Prefer short `DurationSeconds` (15 min) for worker creds.
- Upgrade path to zero static keys: **IAM Roles Anywhere** (X.509 trust anchor +
  per-run cert). Migrate the supervisor to this when convenient; the Tier-2 role
  and worker flow stay unchanged.

## 9. Failure modes to handle

- Marketplace access denial on the first invoke → an AWS administrator must
  enable Haiku 4.5 product `prod-xdkflymybwmvi` once. Do not leave Marketplace
  subscription permissions on the worker role.
- Other `AccessDeniedException` on invoke → wrong identity/creds in worker, or
  model ARN mismatch. Confirm the STS creds (not supervisor keys) are present.
- `ThrottlingException` → hit a Service Quota; back off / raise quota.
- SigV4 signature errors → clock skew (check NTP) or missing `AWS_SESSION_TOKEN`.
- Egress blocked → confirm `bedrock-runtime.us-east-1.amazonaws.com` allowlisted.

## 10. Recovery checklist

1. Confirm `/srv/orchestration/env.tpl` still points at the
   `example-vault/aws-factory-supervisor` 1Password item; never copy values into
   this repository.
2. Confirm the IAM user can only assume `factory-bedrock-invoke`.
3. Confirm the role trust policy names only the `factory-supervisor` user.
4. Confirm the role has `bedrock:InvokeModel` and
   `bedrock:InvokeModelWithResponseStream` for the pinned US inference profile
   and all foundation-model Regions that profile can route to. AWS requires
   both resource classes for inference-profile invocation.
5. Confirm Marketplace product `prod-xdkflymybwmvi` is active. Marketplace
   subscription permission is a temporary bootstrap permission, not a worker
   permission.
6. Re-run the allowlisted manual smoke, then the canonical floor 3/3 and image
   fixture after any credential rotation, IAM-policy change, Claude Code
   upgrade, model/profile change, or worker-launcher change.

## 11. References

- [Anthropic: Claude Code on Amazon Bedrock](https://docs.anthropic.com/en/docs/claude-code/amazon-bedrock)
- [AWS: Claude Haiku 4.5 model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-4-5.html)
- [AWS: Request access to models](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html)
- [AWS: Inference-profile prerequisites](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-prereq.html)
- [AWS: Cross-Region inference](https://docs.aws.amazon.com/bedrock/latest/userguide/cross-region-inference.html)
