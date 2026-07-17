# Claude Code x Claude Haiku 4.5 on Amazon Bedrock - blocked before inference

*2026-07-17. Operator: the orchestration agent on the orchestration VM.
This is a configuration and trust-boundary probe, not a floor result. No
model completion was returned, so the exact-instruction and image-input
fixtures remain unrun.*

## Result

The intended credential boundary works, but the AWS account has not completed
the one-time AWS Marketplace enablement for Claude Haiku 4.5:

1. The supervisor's static `factory-supervisor` credentials successfully
   assumed `factory-bedrock-invoke` for a 900-second session.
2. Only the returned `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and
   `AWS_SESSION_TOKEN` were exposed to Claude Code.
3. Claude Code 2.1.212 selected Amazon Bedrock and dispatched to
   `us.anthropic.claude-haiku-4-5-20251001-v1:0` in `us-east-1`.
4. Bedrock rejected both the main request and Claude Code's session-title
   request with HTTP 403. AWS reported that model access could not be enabled
   because the role lacks `aws-marketplace:ViewSubscriptions` and
   `aws-marketplace:Subscribe`.

The run consumed zero input tokens, zero output tokens, and recorded no model
cost. It therefore says nothing yet about instruction adherence, tool use,
image input, latency, or reasoning quality.

Claude Code also attempted `bedrock:ListInferenceProfiles`, which the narrow
role does not allow. The CLI logged that denial and correctly fell back to its
hardcoded model catalog before making the pinned-model invocation, so that
permission is not the present blocker.

## Configuration exercised

- Harness: Claude Code 2.1.212, headless print mode, isolated config directory.
- Provider switch: `CLAUDE_CODE_USE_BEDROCK=1`.
- Region: `AWS_REGION=us-east-1` and `AWS_DEFAULT_REGION=us-east-1`.
- Model: `us.anthropic.claude-haiku-4-5-20251001-v1:0`.
- Effort request: `high`.
- Static supervisor inputs: the prefixed `AWS_BEDROCK_*` values injected from
  1Password. These were never renamed globally because the orchestration
  process's standard AWS variables belong to the separate Route 53 identity.
- Worker inputs: one 15-minute STS credential triple under the standard AWS
  SDK variable names. Anthropic API credentials and `AWS_PROFILE` were unset.

No standing credential was written to disk or included in the captured
evidence.

## Exact unblock

AWS documents Marketplace enablement as a one-time account step. An AWS
administrator must enable the Haiku 4.5 product, `prod-xdkflymybwmvi`, using a
principal that has the Marketplace subscription permissions. Once the product
is enabled for the account, the existing `factory-bedrock-invoke` role should
invoke it without retaining Marketplace permissions.

Keep Marketplace permissions out of the long-lived worker role. Use a
temporary bootstrap principal or the Bedrock console, enable only this product,
then rerun the same probe. After the first successful text request, run the
existing `muse-smoke.txt` floor check three fresh times and then an image-input
fixture before assigning the pair a bench seat.

References:

- [AWS: Request access to models](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html)
- [AWS: Claude Haiku 4.5 model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-4-5.html)
- [Anthropic: Claude Code on Amazon Bedrock](https://docs.anthropic.com/en/docs/claude-code/amazon-bedrock)
