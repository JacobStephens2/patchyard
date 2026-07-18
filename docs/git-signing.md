# Git commit signing (JacobStephens2)

Factory commits from this checkout are authored as **Jacob Stephens**
`<jacob@stephens.page>` and **SSH-signed** so GitHub can show them as
**Verified** for [JacobStephens2](https://github.com/JacobStephens2).

## What is configured on this host

In the factory clone (`/srv/orchestration/patchyard/`), local git config:

| Setting | Value |
| :-- | :-- |
| `user.name` | Jacob Stephens |
| `user.email` | jacob@stephens.page |
| `gpg.format` | ssh |
| `user.signingkey` | `/var/lib/conductor/.ssh/id_ed25519_github_signing` |
| `commit.gpgsign` | true |
| `tag.gpgsign` | true |

The private key never leaves this host. Local signature checking uses
`/var/lib/conductor/.ssh/allowed_signers`.

## One-time GitHub steps (Jacob)

Until these are done, signed commits still show **Unverified** on GitHub
(reason: key not associated with the account).

1. **Add the public key as an SSH signing key** (not an authentication key):
   - Open https://github.com/settings/ssh/new
   - **Key type:** Signing Key
   - **Title:** e.g. `orchestration factory signing`
   - **Key:** contents of
     `/var/lib/conductor/.ssh/id_ed25519_github_signing.pub` on this VM
     (or run `cat` on that path).
2. **Confirm the author email is verified** on
   https://github.com/settings/emails:
   - `jacob@stephens.page` must be listed and verified, **or**
   - change `user.email` in this repo to your GitHub noreply address
     (`{id}+JacobStephens2@users.noreply.github.com` /
     `JacobStephens2@users.noreply.github.com`).
3. **Optional:** prefer verified merges only - branch protection can require
   signed commits later; do not enable that until the key is registered and a
   sample signed commit shows Verified.

## Check after a new commit

```bash
cd /srv/orchestration/patchyard
git log -1 --show-signature
gh api repos/JacobStephens2/patchyard/commits/$(git rev-parse HEAD) \
  --jq '.commit.verification'
```

Expect `"verified": true` and `"reason": "valid"`.

## What this does not do

- It does **not** rewrite past unsigned commits (history stays as-is).
- It does **not** sign commits in other repos unless the same local config is
  applied there.
- Merge commits created by the **GitHub UI** are already verified as GitHub;
  agent-authored commits need this SSH signing path.

## Token note

The orchestrator's `GH_TOKEN` can push as JacobStephens2 but lacks the
`admin:ssh_signing_key` scope, so the public key cannot be uploaded via API
from this host - the web UI step above is required once.
