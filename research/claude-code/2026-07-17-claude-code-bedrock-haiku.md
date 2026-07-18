# Claude Code x Claude Haiku 4.5 on Amazon Bedrock - floor passes 3/3

*2026-07-17. Operator: the orchestration agent on the orchestration VM.
The first attempt localized an account-level Marketplace blocker. After an AWS
administrator enabled the Haiku 4.5 product and removed the temporary bootstrap
policy, the same STS flow reached inference. The canonical Claude Code harness
then passed the exact-file floor check 3/3 and read the image fixture correctly.*

## Final result

The pair clears the pre-gauntlet floor in this exact configuration:

```bash
claude -p --model us.anthropic.claude-haiku-4-5-20251001-v1:0 \
  --effort high --allowedTools Write
```

- Text inference: exact `bedrock-haiku-ok` response, 2.0 seconds, $0.001501.
- Tool-use floor: PASS 3/3. Each fresh run created `muse-smoke.txt` with the
  exact seven bytes `factory`, used two turns, and finished in 3.6-3.7 seconds.
- Image input: content PASS. With only the Read tool available, the model read
  the sanitized dropdown PNG and returned the correct first four visible labels
  in order: `Test User Delta`, `QA Example Tango`, `Sample Pilot Juliet`, and
  `User Zulu 42`.
- Image strict-output caveat: the prompt requested only a JSON array, but the
  model wrapped the correct array in a Markdown `json` fence. The visual content
  is qualified; exact structured formatting is not qualified by this run.

The three canonical floor runs cost $0.03575525, $0.03575265, and $0.03572265.
Their mean was $0.03574352/run. The image run cost $0.01938720 and took 5.4
seconds. All calls made during the successful retest and configuration
comparison cost $0.13325475 total.

## Boundary audit - 2026-07-18

The 3/3 floor qualification ran Claude Code directly on the orchestration host.
Bedrock selected the temporary standard AWS credential triple, but the child
process also inherited the supervisor's nonstandard `AWS_BEDROCK_*` variables
and the rest of the wrapper-injected environment. The earlier statement that
only STS credentials were exposed to that process was too strong. Those runs
qualified model/harness behavior, not the worker secret boundary.

Two follow-ups separated the concerns:

1. Removing only the `AWS_BEDROCK_*` variables still left unrelated
   orchestration secrets inherited. The exact-file probe passed, but this was
   not accepted as a credential-free-worker check. Cost: $0.03540145.
2. The final launcher built the child environment from an allowlist, gave it a
   new empty `HOME` and isolated `CLAUDE_CONFIG_DIR`, and then ran the canonical
   `Write` probe. It passed with the exact seven-byte file in 3.9 seconds for
   $0.01957815.

The final child contained exactly these environment names:

```text
ANTHROPIC_MODEL
AWS_ACCESS_KEY_ID
AWS_DEFAULT_REGION
AWS_REGION
AWS_SECRET_ACCESS_KEY
AWS_SESSION_TOKEN
CLAUDE_CODE_USE_BEDROCK
CLAUDE_CONFIG_DIR
HOME
LANG
LOGNAME
PATH
SHELL
USER
```

No static Bedrock credential or other orchestration secret was present in that
child environment. This validates the process-spawn contract only. The factory
has not yet built or tested Firecracker/Podman isolation, filesystem
containment, or Bedrock-only egress. Total model spend across the original
qualification and this audit was $0.18823435.

## Configuration discriminator

A preliminary minimal-mode variant failed 0/3:

```bash
claude -p --bare --tools Write --allowedTools Write \
  --permission-mode acceptEdits ...
```

Each response printed an `echo` command and falsely said the file had been
created, but made no tool call and wrote no file. This does not overturn the
canonical 3/3 result; it proves the harness configuration is part of the
qualified identity. Do not use the minimal variant for this seat unless a
future isolated retest qualifies it.

## Configuration exercised

- Harness: Claude Code 2.1.212, headless print mode, isolated config directory.
- Provider switch: `CLAUDE_CODE_USE_BEDROCK=1`.
- Region: `AWS_REGION=us-east-1` and `AWS_DEFAULT_REGION=us-east-1`.
- Model: `us.anthropic.claude-haiku-4-5-20251001-v1:0`.
- Effort request: `high`.
- Static supervisor inputs: the prefixed `AWS_BEDROCK_*` values injected from
  1Password. These were never renamed globally because the orchestration
  process's standard AWS variables belong to the separate Route 53 identity.
- Bedrock authentication inputs: one 15-minute STS credential triple under the
  standard AWS SDK variable names. Anthropic API credentials and `AWS_PROFILE`
  were unset.

No standing credential was written to disk or included in the captured
evidence. The final environment-allowlisted child received no standing
credential; see the boundary audit above for the correction to the initial
direct-host runs.

Claude Code also attempted `bedrock:ListInferenceProfiles`, which the narrow
role does not allow. The CLI logged that denial and correctly fell back to its
hardcoded model catalog before making the pinned-model invocation, so that
permission is not required for this pinned configuration.

## Initial blocker - resolved

The first attempt reached the correct Bedrock endpoint but received HTTP 403
before inference because Haiku 4.5 Marketplace product `prod-xdkflymybwmvi`
had not been enabled for the account. No tokens or model cost were incurred.

An administrator enabled it with temporary Marketplace subscription authority
and then removed that authority. The successful retest proves the subscription
persists and the existing `factory-bedrock-invoke` role needs only its scoped
invoke permissions. Marketplace permissions remain absent from the worker role.

References:

- [AWS: Request access to models](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html)
- [AWS: Claude Haiku 4.5 model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-4-5.html)
- [Anthropic: Claude Code on Amazon Bedrock](https://docs.anthropic.com/en/docs/claude-code/amazon-bedrock)
