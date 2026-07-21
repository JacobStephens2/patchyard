# CI

Both workflows run on `ubuntu-latest` with SHA-pinned actions and a Rust cache
action (A76 as amended by A88 - no self-hosted runner on any factory host).
They are thin wrappers over `tools/check-infra.sh`, `tools/check-ansible.sh`, and
`tools/check-application.sh`: OpenTofu and Ansible hygiene plus Rust
fmt/clippy/test/audit/deny, the checked constitution, and byte-identical model
regeneration. R4's boundary holds: CI verifies what the repo is and never acts
as the factory's coding runtime.

**Resolved 2026-07-22**: the `patchyard-orchestrator-fieldbook` PAT now carries "Workflows: read and write" (granted via browser agent; token string unchanged), verified by pushing `workflows/README.md` from this host. Note: the grant spans all nine repos on that token, not just `factory` - accepted for now; when the GitHub App takes over factory operations (sessions 1/10, A45/A62), drop the Workflows grant from the broad PAT or split a factory-only token.
