# GitHub desired state

This root owns repository settings and classic branch protection for
`JacobStephens2/patchyard`. It uses the encrypted
`factory/github/tofu.tfstate` backend key. The branch rule requires a PR,
current application and infrastructure checks, and resolved review threads; it
permits no force push, deletion, or bypass. The platform approval count remains
zero while the conductor identity authors build PRs because GitHub forbids
authors from approving them. It rises to one when build PR authorship moves to
the distinct `patchyard` App identity.

The repository and existing branch rule must be imported before apply. The
admin-scoped provider credential enters only as `GH_FACTORY_ADMIN_PAT`; the
ordinary workflow/push PAT remains separate. If `master` has no protection rule,
the import script adopts the repository and leaves the reviewed OpenTofu apply
to create the rule rather than confusing absence with missing authority.
