# AWS desired state

This root adopts the hand-created A96 S3 backend and IAM resources, then owns
the `factory.example.com` Route 53 record. Its own encrypted state is at
`factory/aws/tofu.tfstate` in the bucket it manages.

Run `../import-a96.sh` before the first plan. The backend access key is
deliberately absent from configuration and state. `../tofu.sh` keeps the S3
backend credentials, temporary S3/IAM management operator, standing Route 53
record identity, and state passphrase in separate process-environment channels.
`AWS_FACTORY_A96_OPERATOR_ACCESS_KEY_ID` and
`AWS_FACTORY_A96_OPERATOR_SECRET_ACCESS_KEY` override only the management
provider; `orchestrator-route53` remains the aliased DNS provider. Once the
temporary operator is revoked, the standing Route 53 user's adopted-resource
read grant supports drift plans while remediating management drift requires a
new reviewed operator grant.

The current injected identities can use the state objects and Route 53 records,
but neither can read IAM or bucket configuration. A credential with the exact
bucket/IAM read-management permissions is therefore required to complete the
mandated imports and the reviewed policy-description replacement.
