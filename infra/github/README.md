# GitHub desired state

This root owns repository settings and classic branch protection for
`JacobStephens2/patchyard`, plus the protected Fieldbook deploy
marker branch `refs/heads/deploy/production`. It uses the encrypted
`factory/github/tofu.tfstate` backend key. The branch rule requires a PR,
current application and infrastructure checks, and resolved review threads; it
permits no force push, deletion, or bypass. The platform approval count remains
zero under A111: Jacob or Engineer Two may merge any code or policy PR alone after
its required checks and adversarial review. The Factory App can propose but
cannot merge or update protected `master`.

The repository and existing branch rule must be imported before apply. The
admin-scoped provider credential enters only as `GH_FACTORY_ADMIN_PAT`; the
ordinary workflow/push PAT remains separate. Session 16 widens that PAT's
repository selection to include `example-org/fieldbook` with
Administration read/write so OpenTofu can own the marker rule; the secret is
still supplied only through process environment and is not installed on a
Factory host. If `master` has no protection rule,
the import script adopts the repository and leaves the reviewed OpenTofu apply
to create the rule rather than confusing absence with missing authority.

The Fieldbook marker protection permits creation and direct updates only by
Jacob Stephens or Engineer Two, blocks deletion, permits their forced
rollback move, and grants no Factory App bypass. The App reads the marker with
a per-mint `contents:read` token. The
production deploy flow advances this marker only after the deployed checkout
has been verified at the target SHA.
