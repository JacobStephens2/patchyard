CREATE TABLE factory.publisher_leases (
    resource text PRIMARY KEY,
    request_id uuid NOT NULL REFERENCES factory.requests(id),
    run_id uuid NOT NULL REFERENCES factory.runs(id),
    holder text NOT NULL,
    fencing_token bigint NOT NULL,
    acquired_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    expires_at timestamptz NOT NULL,
    released_at timestamptz,
    CONSTRAINT publisher_leases_resource_not_blank CHECK (btrim(resource) <> ''),
    CONSTRAINT publisher_leases_holder_not_blank CHECK (btrim(holder) <> ''),
    CONSTRAINT publisher_leases_fencing_positive CHECK (fencing_token > 0),
    CONSTRAINT publisher_leases_expiry_ordered CHECK (expires_at > acquired_at),
    CONSTRAINT publisher_leases_release_ordered CHECK (
        released_at IS NULL OR released_at >= acquired_at
    )
);

CREATE INDEX publisher_leases_expiry_idx
    ON factory.publisher_leases(expires_at);

CREATE TABLE factory.github_state (
    repository text PRIMARY KEY,
    observed_at timestamptz,
    failed_at timestamptz,
    last_error text,
    open_pr_count integer,
    CONSTRAINT github_state_repository_not_blank CHECK (btrim(repository) <> ''),
    CONSTRAINT github_state_open_pr_count_nonnegative CHECK (
        open_pr_count IS NULL OR open_pr_count >= 0
    ),
    CONSTRAINT github_state_observation_shape CHECK (
        (observed_at IS NULL AND open_pr_count IS NULL)
        OR (observed_at IS NOT NULL AND open_pr_count IS NOT NULL)
    )
);

ALTER TABLE factory.pr_state
    ADD COLUMN branch text,
    ADD COLUMN state text,
    ADD COLUMN is_draft boolean,
    ADD COLUMN author_login text,
    ADD COLUMN html_url text,
    ADD COLUMN merge_commit_sha character(40),
    ADD COLUMN merged_by text,
    ADD COLUMN github_updated_at timestamptz,
    ADD COLUMN admin_bypassed boolean NOT NULL DEFAULT false,
    ADD COLUMN passing_run boolean NOT NULL DEFAULT false,
    ADD COLUMN reconcile_error text;

ALTER TABLE factory.pr_state
    ADD CONSTRAINT pr_state_branch_not_blank CHECK (
        branch IS NULL OR btrim(branch) <> ''
    ),
    ADD CONSTRAINT pr_state_state_known CHECK (
        state IS NULL OR state IN ('open', 'closed')
    ),
    ADD CONSTRAINT pr_state_author_not_blank CHECK (
        author_login IS NULL OR btrim(author_login) <> ''
    ),
    ADD CONSTRAINT pr_state_merge_sha_git CHECK (
        merge_commit_sha IS NULL OR merge_commit_sha ~ '^[0-9a-f]{40}$'
    ),
    ADD CONSTRAINT pr_state_passing_shape CHECK (
        NOT passing_run
        OR (
            state = 'closed'
            AND merged_at IS NOT NULL
            AND deployed_sha = merge_commit_sha
            AND NOT admin_bypassed
        )
    );

COMMENT ON TABLE factory.publisher_leases IS
    'Global, fenced publisher serialization; GitHub cap checks and PR creation run while held';
COMMENT ON TABLE factory.github_state IS
    'Last bounded GitHub observation; stale or failed state never authorizes publication';
