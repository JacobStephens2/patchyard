# GitHub desired state

This root owns repository settings and classic branch protection for
`JacobStephens2/patchyard`. It uses the encrypted
`factory/github/tofu.tfstate` backend key. The branch rule requires a human PR
approval, the infrastructure check, current-branch checks, and resolved review
threads; it permits no force push, deletion, or bypass.

The repository and existing branch rule must be imported before apply. The
current PAT can push workflow files but receives HTTP 403 from the branch
protection API, so an admin-scoped provider credential is a prerequisite for
the import and apply.
