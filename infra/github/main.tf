resource "github_repository" "factory" {
  name                   = "factory"
  description            = "Patchyard Software Factory"
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
    dismiss_stale_reviews           = true
    require_code_owner_reviews      = false
    required_approving_review_count = 1
    require_last_push_approval      = true
  }
}
