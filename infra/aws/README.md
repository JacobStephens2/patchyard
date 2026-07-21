# AWS desired state

This root adopts the hand-created A96 S3 backend and IAM resources, then owns
the `factory.example.com` Route 53 record. Its own encrypted state is at
`factory/aws/tofu.tfstate` in the bucket it manages.

Run `../import-a96.sh` before the first plan. The backend access key is
deliberately absent from configuration and state. `../tofu.sh` keeps the S3
credentials, Route 53/IAM provider credentials, and state passphrase in
separate process-environment channels.

The current injected identities can use the state objects and Route 53 records,
but neither can read IAM or bucket configuration. A credential with the exact
bucket/IAM read-management permissions is therefore required to complete the
mandated imports and the reviewed policy-description replacement.
