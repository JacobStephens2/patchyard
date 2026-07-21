resource "github_repository" "factory" {
  name                   = "factory"
  description            = "Patchyard's software factory: small staff requests in, evidenced pull requests out - one human gate, the PR. Rust control plane, skill playbooks, queue, ledger, and dashboard."
  homepage_url           = "https://factory.example.com"
  visibility             = "private"
  has_discussions        = false
  has_issues             = true
  has_projects           = true
  has_wiki               = true
  allow_merge_commit     = true
  allow_rebase_merge     = true
  allow_squash_merge     = true
  delete_branch_on_merge = false
  archive_on_destroy     = false

  lifecycle {
    prevent_destroy = true
    # GitHub's provider deprecated this API field. Preserve the imported live
    # value instead of normalizing it during the branch-protection apply.
    ignore_changes = [has_downloads]
  }
}

resource "github_branch_protection" "master" {
  repository_id                   = github_repository.factory.node_id
  pattern                         = "master"
  enforce_admins                  = true
  allows_deletions                = false
  allows_force_pushes             = false
  require_conversation_resolution = true

  required_status_checks {
    strict   = true
    contexts = ["infrastructure"]
  }

  required_pull_request_reviews {
    dismiss_stale_reviews      = true
    require_code_owner_reviews = false
    # The conductor identity authors current build PRs, and GitHub forbids an
    # author from self-approving. Raise this to 1 when build PRs are authored
    # by the patchyard App and the human approver is a distinct identity.
    required_approving_review_count = 0
    require_last_push_approval      = false
  }
}
