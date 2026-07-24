# Git commit signing (JacobStephens2)

**Fleet source of truth:** [`example/git-commit-signing.md`](../../example/git-commit-signing.md).

Factory and all other fleet hosts share one SSH signing key
(`~/.ssh/eta_commit_signing_ed25519`), author
`Jacob Stephens <jacob@stephens.page>`, with `commit.gpgsign=true`.
That key is already registered on GitHub as a signing key; signed commits
show **Verified**.

Do not introduce a second per-project signing key. Enroll a new host with:

```bash
scripts/enroll-git-signing.sh <host-alias>
```
