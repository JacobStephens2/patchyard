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
    contexts = ["application", "infrastructure"]
  }

  required_pull_request_reviews {
    dismiss_stale_reviews      = true
    require_code_owner_reviews = false
    # A111 makes approvals optional: one authorized human merge satisfies A1
    # for every Factory PR, including proposer-authored policy changes.
    required_approving_review_count = 0
    require_last_push_approval      = false
  }

  # A111 keeps approvals optional. A1 is enforced independently: only the two
  # authorized human mergers may update protected master; the Factory App may
  # create proposal branches and PRs but cannot merge or push its own output.
  restrict_pushes {
    blocks_creations = false
    push_allowances  = ["/JacobStephens2", "/example-teammate"]
  }
}

data "github_repository" "fieldbook" {
  full_name = "example-org/fieldbook"
}

# The moving deploy marker is a branch ref so GitHub can enforce its update
# policy. Factory runtime tokens are narrowed to contents:read; only the two
# named human deploy operators may move the ref. Deletion remains forbidden;
# force updates are required so a verified Fieldbook rollback can move the
# marker to the older commit that is actually live.
resource "github_branch_protection" "fieldbook_deploy_production" {
  repository_id       = data.github_repository.fieldbook.node_id
  pattern             = "deploy/production"
  enforce_admins      = true
  allows_deletions    = false
  allows_force_pushes = true

  restrict_pushes {
    blocks_creations = true
    push_allowances  = ["/JacobStephens2", "/example-teammate"]
  }
}
