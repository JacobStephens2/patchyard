CREATE SCHEMA factory;

CREATE TYPE factory.request_status AS ENUM (
    'queued',
    'claimed',
    'closed',
    'failed',
    'killed'
);

CREATE TYPE factory.run_state AS ENUM (
    'queued',
    'triaging',
    'implementing',
    'verifying',
    'publishing',
    'ready_for_review',
    'failed',
    'killed',
    'closed'
);

CREATE TABLE factory.requests (
    id uuid PRIMARY KEY,
    fingerprint bytea NOT NULL UNIQUE,
    source text NOT NULL,
    body text NOT NULL,
    trace_id character(32) NOT NULL,
    received_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    status factory.request_status NOT NULL DEFAULT 'queued',
    closed_at timestamptz,
    CONSTRAINT requests_fingerprint_sha256 CHECK (octet_length(fingerprint) = 32),
    CONSTRAINT requests_source_not_blank CHECK (btrim(source) <> ''),
    CONSTRAINT requests_body_not_blank CHECK (btrim(body) <> ''),
    CONSTRAINT requests_trace_id_w3c CHECK (
        trace_id ~ '^[0-9a-f]{32}$'
        AND trace_id <> '00000000000000000000000000000000'
    ),
    CONSTRAINT requests_closed_state_consistent CHECK (
        (status = 'closed' AND closed_at IS NOT NULL)
        OR (status <> 'closed' AND closed_at IS NULL)
    )
);

CREATE TABLE factory.runs (
    id uuid PRIMARY KEY,
    request_id uuid NOT NULL REFERENCES factory.requests(id),
    base_sha character(40) NOT NULL,
    branch text NOT NULL UNIQUE,
    lane text NOT NULL,
    skill text NOT NULL,
    state factory.run_state NOT NULL DEFAULT 'queued',
    queued_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    started_at timestamptz,
    finished_at timestamptz,
    input_tokens bigint NOT NULL DEFAULT 0,
    output_tokens bigint NOT NULL DEFAULT 0,
    turns integer NOT NULL DEFAULT 0,
    eval_scores jsonb NOT NULL DEFAULT '{}'::jsonb,
    model_id_hash bytea,
    cli_version_hash bytea,
    constitution_hash bytea,
    rubric_hash bytea,
    skill_hash bytea,
    prompt_template_hash bytea,
    verifier_binary_hash bytea,
    base_tree_hash bytea,
    CONSTRAINT runs_base_sha_git CHECK (base_sha ~ '^[0-9a-f]{40}$'),
    CONSTRAINT runs_branch_not_blank CHECK (btrim(branch) <> ''),
    CONSTRAINT runs_lane_not_blank CHECK (btrim(lane) <> ''),
    CONSTRAINT runs_skill_not_blank CHECK (btrim(skill) <> ''),
    CONSTRAINT runs_usage_nonnegative CHECK (
        input_tokens >= 0 AND output_tokens >= 0 AND turns >= 0
    ),
    CONSTRAINT runs_times_ordered CHECK (
        (started_at IS NULL OR started_at >= queued_at)
        AND (finished_at IS NULL OR started_at IS NOT NULL)
        AND (finished_at IS NULL OR finished_at >= started_at)
    ),
    CONSTRAINT runs_model_id_hash_sha256 CHECK (
        model_id_hash IS NULL OR octet_length(model_id_hash) = 32
    ),
    CONSTRAINT runs_cli_version_hash_sha256 CHECK (
        cli_version_hash IS NULL OR octet_length(cli_version_hash) = 32
    ),
    CONSTRAINT runs_constitution_hash_sha256 CHECK (
        constitution_hash IS NULL OR octet_length(constitution_hash) = 32
    ),
    CONSTRAINT runs_rubric_hash_sha256 CHECK (
        rubric_hash IS NULL OR octet_length(rubric_hash) = 32
    ),
    CONSTRAINT runs_skill_hash_sha256 CHECK (
        skill_hash IS NULL OR octet_length(skill_hash) = 32
    ),
    CONSTRAINT runs_prompt_template_hash_sha256 CHECK (
        prompt_template_hash IS NULL OR octet_length(prompt_template_hash) = 32
    ),
    CONSTRAINT runs_verifier_binary_hash_sha256 CHECK (
        verifier_binary_hash IS NULL OR octet_length(verifier_binary_hash) = 32
    ),
    CONSTRAINT runs_base_tree_hash_sha256 CHECK (
        base_tree_hash IS NULL OR octet_length(base_tree_hash) = 32
    )
);

CREATE TABLE factory.events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id uuid NOT NULL REFERENCES factory.requests(id),
    run_id uuid REFERENCES factory.runs(id),
    event_type text NOT NULL,
    from_state text,
    to_state text,
    trace_id character(32) NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT events_type_not_blank CHECK (btrim(event_type) <> ''),
    CONSTRAINT events_trace_id_w3c CHECK (
        trace_id ~ '^[0-9a-f]{32}$'
        AND trace_id <> '00000000000000000000000000000000'
    )
);

CREATE OR REPLACE FUNCTION factory.reject_event_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'factory.events is append-only';
END;
$$;

CREATE TRIGGER events_append_only
BEFORE UPDATE OR DELETE ON factory.events
FOR EACH ROW EXECUTE FUNCTION factory.reject_event_mutation();

CREATE TABLE factory.artifacts (
    id uuid PRIMARY KEY,
    request_id uuid NOT NULL REFERENCES factory.requests(id),
    run_id uuid REFERENCES factory.runs(id),
    path text NOT NULL UNIQUE,
    sha256 bytea NOT NULL,
    kind text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    expires_at timestamptz,
    deleted_at timestamptz,
    CONSTRAINT artifacts_relative_path CHECK (
        path !~ '(^/|(^|/)\.\.(/|$)|(^|/)\.(/|$))'
    ),
    CONSTRAINT artifacts_sha256 CHECK (octet_length(sha256) = 32),
    CONSTRAINT artifacts_kind_not_blank CHECK (btrim(kind) <> ''),
    CONSTRAINT artifacts_expiry_ordered CHECK (
        expires_at IS NULL OR expires_at >= created_at
    ),
    CONSTRAINT artifacts_deletion_consistent CHECK (
        deleted_at IS NULL OR (expires_at IS NOT NULL AND deleted_at >= expires_at)
    )
);

CREATE TABLE factory.pr_state (
    number integer PRIMARY KEY,
    request_id uuid REFERENCES factory.requests(id),
    run_id uuid REFERENCES factory.runs(id),
    head_sha character(40) NOT NULL,
    ci_state text NOT NULL,
    review_state text NOT NULL,
    reconciled_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    merged_at timestamptz,
    deployed_sha character(40),
    CONSTRAINT pr_state_number_positive CHECK (number > 0),
    CONSTRAINT pr_state_head_sha_git CHECK (head_sha ~ '^[0-9a-f]{40}$'),
    CONSTRAINT pr_state_deployed_sha_git CHECK (
        deployed_sha IS NULL OR deployed_sha ~ '^[0-9a-f]{40}$'
    )
);

CREATE TABLE factory.leases (
    resource text PRIMARY KEY,
    request_id uuid NOT NULL UNIQUE REFERENCES factory.requests(id),
    holder text NOT NULL,
    fencing_token bigint NOT NULL,
    acquired_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    expires_at timestamptz NOT NULL,
    released_at timestamptz,
    CONSTRAINT leases_resource_not_blank CHECK (btrim(resource) <> ''),
    CONSTRAINT leases_holder_not_blank CHECK (btrim(holder) <> ''),
    CONSTRAINT leases_fencing_positive CHECK (fencing_token > 0),
    CONSTRAINT leases_expiry_ordered CHECK (expires_at > acquired_at),
    CONSTRAINT leases_release_ordered CHECK (
        released_at IS NULL OR released_at >= acquired_at
    )
);

CREATE INDEX runs_request_id_idx ON factory.runs(request_id);
CREATE INDEX events_request_id_occurred_at_idx
    ON factory.events(request_id, occurred_at, id);
CREATE INDEX events_run_id_idx ON factory.events(run_id) WHERE run_id IS NOT NULL;
CREATE INDEX artifacts_request_id_idx ON factory.artifacts(request_id);
CREATE INDEX artifacts_expiry_idx
    ON factory.artifacts(expires_at)
    WHERE expires_at IS NOT NULL AND deleted_at IS NULL;
CREATE INDEX pr_state_request_id_idx ON factory.pr_state(request_id);
CREATE INDEX leases_expires_at_idx ON factory.leases(expires_at);

CREATE VIEW factory.grafana_request_summary AS
SELECT
    requests.id AS request_id,
    requests.source,
    requests.received_at,
    requests.status::text AS status,
    count(DISTINCT runs.id)::bigint AS run_count,
    count(DISTINCT events.id)::bigint AS event_count,
    max(events.occurred_at) AS latest_event_at
FROM factory.requests
LEFT JOIN factory.runs ON runs.request_id = requests.id
LEFT JOIN factory.events ON events.request_id = requests.id
GROUP BY requests.id, requests.source, requests.received_at, requests.status;

CREATE VIEW factory.grafana_run_metrics AS
SELECT
    runs.id AS run_id,
    runs.request_id,
    runs.lane,
    runs.skill,
    runs.state::text AS state,
    runs.queued_at,
    runs.started_at,
    runs.finished_at,
    runs.input_tokens,
    runs.output_tokens,
    runs.turns,
    runs.eval_scores
FROM factory.runs;

COMMENT ON SCHEMA factory IS 'Patchyard Factory canonical state schema';
COMMENT ON TABLE factory.events IS 'Append-only transition ledger';
COMMENT ON VIEW factory.grafana_request_summary IS
    'A94-safe request metadata and aggregate counts; no request body or artifact path';
COMMENT ON VIEW factory.grafana_run_metrics IS
    'A94-safe run metadata and aggregate usage; no provenance content or artifact path';
