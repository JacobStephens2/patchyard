# Issue tracker: GitHub Issues (wayfinder)

Wayfinding for this repo is tracked in GitHub Issues on
**`JacobStephens2/patchyard`**, driven by the `gh` CLI. No extra
credential is needed - `gh` is already authenticated in this environment.

Moved here from Trello on 2026-08-15. The Trello board (**Patchyard Factory**,
https://trello.com/b/Tdiikiov) is closed and read-only; every issue footers the
card it came from. Nothing live is left there - all 48 cards, 60 comments and
124 cross-links were migrated and repointed. Trello was adopted 2026-08-11 and
abandoned because its 16,384-character description limit stopped the map from
accepting another decision, and because it has no native blocking.

The `TRELLO_API_KEY` / `TRELLO_FACTORY_API_TOKEN` variables stay in the `va`
manifest for reading the archive; nothing writes to Trello any more.

## Wayfinding operations

Used by `/wayfinder`. The **map** is one issue; tickets are **sub-issues** of
it.

- **Current map**: [MAP: form -> daemon-claimed -> model-authored draft PR](https://github.com/JacobStephens2/patchyard/issues/176) - issue `#176`, labelled `wayfinder:map`.
- **Ticket labels**: `wayfinder:research` / `wayfinder:prototype` / `wayfinder:grilling` / `wayfinder:task`, plus `wayfinder:map` on the map itself.
- **State is computed, not filed.** There are no lists to keep in sync - an issue is closed or open, and open issues are blocked or not according to their dependency edges. This is the whole reason for the move: two tickets were sitting in Trello's `Blocked` list on 2026-08-15 whose blockers had already closed, because the list move is manual and was missed.
- **Blocking** uses GitHub's native issue dependencies, which render in the
  issue UI. A `Blocked by:` line in a body is commentary; the edge is the state.

  ```bash
  BLOCKER_ID=$(gh api repos/JacobStephens2/patchyard/issues/<blocker-number> --jq .id)
  gh api --method POST \
    repos/JacobStephens2/patchyard/issues/<blocked-number>/dependencies/blocked_by \
    -F issue_id=$BLOCKER_ID
  ```

- **Frontier query** - open, unassigned, zero open blockers:

  ```bash
  gh api graphql -f query='{repository(owner:"example-org",name:"factory"){
    issues(first:100,states:OPEN){nodes{number title assignees(first:5){totalCount}
      labels(first:10){nodes{name}}
      issueDependenciesSummary{blockedBy}}}}}' \
    --jq '.data.repository.issues.nodes[]
          | select((.labels.nodes|map(.name)|index("wayfinder:map"))|not)
          | select(.issueDependenciesSummary.blockedBy==0 and .assignees.totalCount==0)
          | "#\(.number) \(.title)"'
  ```

- **Claim**: `gh issue edit <n> --add-assignee @me` - the session's first write,
  before any work.
- **Resolve**: `gh issue comment <n> --body-file <resolution.md>`, then
  `gh issue close <n> --reason completed`, then append a one-line gist + link to
  the map's *Decisions so far*.
- **New tickets**: `gh issue create --title ... --body-file ... --label wayfinder:<type>`,
  then attach to the map and wire blockers in a second pass once numbers exist:

  ```bash
  SUB_ID=$(gh api repos/JacobStephens2/patchyard/issues/<n> --jq .id)
  gh api --method POST \
    repos/JacobStephens2/patchyard/issues/176/sub_issues -F sub_issue_id=$SUB_ID
  ```

## When a skill says "publish to the issue tracker"

Create a GitHub issue on `JacobStephens2/patchyard`, labelled and
attached to the map as above.

## When a skill says "fetch the relevant ticket"

`gh issue view <n> --json title,body,comments,assignees,labels`
