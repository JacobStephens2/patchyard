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
| Reasoning | Claude Code `--effort high`; raw Messages requests can use `thinking: { type: "enabled", budget_tokens: N }` |

Bedrock runs the model on AWS infra. Nothing is downloaded or hosted locally —
the server only makes authenticated HTTPS calls. The one-time Anthropic use-case
form is submitted. AWS Marketplace product enablement is a separate account-level
step; the live 2026-07-17 probe found it is not yet complete for Haiku 4.5.

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

```
factory-supervisor (static keys, 1Password, supervisor env ONLY)
      │  sts:AssumeRole  (DurationSeconds=900)
      ▼
factory-bedrock-invoke  → temporary {AccessKeyId, SecretAccessKey, SessionToken}
      │  injected into the worker's env at spawn
      ▼
Firecracker/Podman worker → invokes us.anthropic.claude-haiku-4-5-...
```

Rules:
- The static `factory-supervisor` keys **never** enter the worker.
- The worker receives **only** the short-lived STS triple, per run.
- Worker egress is restricted to `bedrock-runtime.us-east-1.amazonaws.com`.

## 4. Environment / config

**Supervisor env (from 1Password — supervisor process only):**
```
AWS_BEDROCK_ACCESS_KEY  = op://example-vault/aws-factory-supervisor/access-key
AWS_BEDROCK_SECRET_ACCESS_KEY = op://example-vault/aws-factory-supervisor/secret-access-key
AWS_BEDROCK_IAM_ROLE_ARN = op://example-vault/aws-factory-supervisor/iam-role-arn
```
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
- `bedrock-runtime.us-east-1.amazonaws.com` — inference (worker needs this).
- `sts.amazonaws.com` — only if the worker self-assumes; not needed when the
  supervisor injects pre-minted creds (preferred).
- `bedrock.us-east-1.amazonaws.com` — control-plane/list only; optional.

Also required: outbound TLS with current CA roots, working DNS, NTP-synced clock
(SigV4 fails on >5 min skew). No inbound ports. No static bearer token in headers —
Bedrock uses SigV4-signed requests.

## 6. Code

**Supervisor — mint short-lived creds (TS):**
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
  --no-session-persistence "<task>"
```

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
