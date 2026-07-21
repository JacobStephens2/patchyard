# Workflows

`infrastructure.yml` and `application.yml` are thin wrappers over repository
scripts. Both use GitHub-hosted `ubuntu-latest` runners and immutable action
SHAs; the application job restores the Rust build/tool cache.
