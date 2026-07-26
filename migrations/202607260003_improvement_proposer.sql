CREATE TYPE factory.proposer_state AS ENUM (
    'queued',
    'reporting',
    'proposing',
    'reviewing',
    'publishing',
    'idea_appended',
    'ready_for_review',
    'open_pr_cap_reached',
    'report_failed',
    'report_too_large',
    'proposer_contract_failed',
    'evidence_citation_failed',
    'authority_surface_failed',
    'adversarial_review_failed',
    'publication_failed',
    'cleanup_failed',
    'killed'
);

CREATE TABLE factory.proposer_runs (
    id uuid PRIMARY KEY,
    state factory.proposer_state NOT NULL DEFAULT 'queued',
    base_sha character(40) NOT NULL,
    report_sha256 bytea NOT NULL,
    report_max_event_id bigint NOT NULL,
    prompt_bundle_sha256 bytea NOT NULL,
    branch text,
    patch_sha256 bytea,
    reviewed_sha character(40),
    pr_title text,
    pr_body text,
    review_artifact jsonb,
    disposition_artifact jsonb,
    pr_number integer,
    pr_url text,
    failure_code text,
    queued_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    started_at timestamptz,
    finished_at timestamptz,
    CONSTRAINT proposer_runs_base_sha CHECK (base_sha ~ '^[0-9a-f]{40}$'),
    CONSTRAINT proposer_runs_report_sha CHECK (octet_length(report_sha256) = 32),
    CONSTRAINT proposer_runs_prompt_sha CHECK (octet_length(prompt_bundle_sha256) = 32),
    CONSTRAINT proposer_runs_patch_sha CHECK (
        patch_sha256 IS NULL OR octet_length(patch_sha256) = 32
    ),
    CONSTRAINT proposer_runs_reviewed_sha CHECK (
        reviewed_sha IS NULL OR reviewed_sha ~ '^[0-9a-f]{40}$'
    ),
    CONSTRAINT proposer_runs_candidate_shape CHECK (
        (branch IS NULL AND patch_sha256 IS NULL AND reviewed_sha IS NULL
          AND pr_title IS NULL AND pr_body IS NULL)
        OR
        (btrim(branch) <> '' AND patch_sha256 IS NOT NULL
          AND reviewed_sha IS NOT NULL AND btrim(pr_title) <> ''
          AND btrim(pr_body) <> '')
    ),
    CONSTRAINT proposer_runs_event_snapshot CHECK (report_max_event_id >= 0),
    CONSTRAINT proposer_runs_terminal_shape CHECK (
        (state IN ('queued', 'reporting', 'proposing', 'reviewing', 'publishing')
          AND finished_at IS NULL)
        OR
        (state NOT IN ('queued', 'reporting', 'proposing', 'reviewing', 'publishing')
          AND finished_at IS NOT NULL)
    ),
    CONSTRAINT proposer_runs_pr_shape CHECK (
        (pr_number IS NULL AND pr_url IS NULL)
        OR (pr_number > 0 AND btrim(pr_url) <> '')
    )
);

CREATE TABLE factory.proposer_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    proposer_run_id uuid NOT NULL REFERENCES factory.proposer_runs(id),
    event_type text NOT NULL,
    from_state factory.proposer_state,
    to_state factory.proposer_state NOT NULL,
    reason_code text NOT NULL,
    facts jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT proposer_events_type_not_blank CHECK (btrim(event_type) <> ''),
    CONSTRAINT proposer_events_reason_not_blank CHECK (btrim(reason_code) <> '')
);

CREATE TABLE factory.proposer_artifacts (
    id uuid PRIMARY KEY,
    proposer_run_id uuid NOT NULL REFERENCES factory.proposer_runs(id),
    stage text NOT NULL CHECK (stage IN (
        'proposer-author', 'proposer-reviewer', 'proposer-disposition'
    )),
    path text NOT NULL UNIQUE,
    sha256 bytea NOT NULL CHECK (octet_length(sha256) = 32),
    kind text NOT NULL CHECK (kind = 'agent-transcript'),
    bytes bigint NOT NULL CHECK (bytes >= 0 AND bytes <= 8388608),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    expires_at timestamptz,
    deleted_at timestamptz,
    UNIQUE (proposer_run_id, stage)
);

CREATE TABLE factory.proposer_publisher_lease (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    holder text,
    fencing_token bigint NOT NULL DEFAULT 0 CHECK (fencing_token >= 0),
    acquired_at timestamptz,
    expires_at timestamptz,
    released_at timestamptz,
    CONSTRAINT proposer_lease_shape CHECK (
        (holder IS NULL AND acquired_at IS NULL AND expires_at IS NULL)
        OR (btrim(holder) <> '' AND acquired_at IS NOT NULL AND expires_at > acquired_at)
    )
);

INSERT INTO factory.proposer_publisher_lease (singleton) VALUES (true);

CREATE INDEX proposer_runs_state_queued_idx
    ON factory.proposer_runs(state, queued_at, id);
CREATE UNIQUE INDEX proposer_runs_single_active_idx
    ON factory.proposer_runs ((true))
    WHERE state IN ('queued','reporting','proposing','reviewing','publishing');
CREATE INDEX proposer_events_run_idx
    ON factory.proposer_events(proposer_run_id, id);
CREATE INDEX proposer_artifacts_retention_idx
    ON factory.proposer_artifacts(expires_at, deleted_at)
    WHERE deleted_at IS NULL;

COMMENT ON TABLE factory.proposer_runs IS
    'A86 proposer-specific lifecycle; never part of production run metrics';
COMMENT ON TABLE factory.proposer_events IS
    'Append-only typed proposer transitions and finite reason codes';
COMMENT ON TABLE factory.proposer_artifacts IS
    'A83 private proposer/reviewer transcripts; never input to another seat';
