# CI (session 0-1)

Workflow YAML lands in `workflows/` at session 0-1, staying thin wrappers over repo scripts (`make check` and friends) so any CI backend swap is an afternoon: fmt/clippy/test/audit/deny, model byte-identical regeneration (`model/check-model.sh`), bench check (`tools/check-bench.py`), `tofu validate`, `ansible-lint`. R4 boundary: this CI verifies what the repo is, never executes what the factory does.

**Known blocker, discovered 2026-07-20**: the conductor PAT lacks the `workflow` permission - GitHub rejects pushes touching `.github/workflows/` entirely (even non-YAML). Before session 0, grant the fine-grained PAT "Workflows: read and write" on this repo, or the CI definitions cannot land.
