\set ON_ERROR_STOP on

DO $$
BEGIN
    EXECUTE format('REVOKE ALL ON DATABASE %I FROM PUBLIC', current_database());
    EXECUTE format(
        'GRANT CONNECT ON DATABASE %I TO patchyard_migrator, patchyard_supervisor, patchyard_dashboard, grafana_ro, patchyard_exporter',
        current_database()
    );
END
$$;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA factory FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA factory FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA factory FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA factory FROM PUBLIC;

GRANT USAGE ON SCHEMA factory TO
    patchyard_supervisor,
    patchyard_dashboard,
    grafana_ro;

GRANT SELECT ON
    factory.requests,
    factory.runs,
    factory.events,
    factory.artifacts,
    factory.pr_state,
    factory.leases,
    factory.supervisor_state,
    factory.controls,
    factory.side_effects
TO patchyard_supervisor;
GRANT INSERT (id, fingerprint, source, body, trace_id) ON factory.requests
TO patchyard_supervisor;
GRANT UPDATE (status, closed_at) ON factory.requests TO patchyard_supervisor;
GRANT INSERT ON factory.runs TO patchyard_supervisor;
GRANT UPDATE (
    state,
    started_at,
    finished_at,
    input_tokens,
    output_tokens,
    turns,
    eval_scores,
    model_id,
    cli_version,
    harness,
    provider,
    effort,
    routing_config_version,
    model_id_hash,
    cli_version_hash,
    constitution_hash,
    rubric_hash,
    skill_hash,
    prompt_template_hash,
    verifier_binary_hash,
    base_tree_hash
) ON factory.runs TO patchyard_supervisor;
GRANT INSERT ON factory.events TO patchyard_supervisor;
GRANT USAGE, SELECT ON SEQUENCE factory.events_id_seq TO patchyard_supervisor;
GRANT INSERT ON factory.artifacts TO patchyard_supervisor;
GRANT UPDATE (expires_at, deleted_at) ON factory.artifacts TO patchyard_supervisor;
GRANT INSERT ON factory.pr_state TO patchyard_supervisor;
GRANT UPDATE (
    head_sha,
    ci_state,
    review_state,
    reconciled_at,
    merged_at,
    deployed_sha
) ON factory.pr_state TO patchyard_supervisor;
GRANT INSERT ON factory.leases TO patchyard_supervisor;
GRANT UPDATE (
    holder,
    fencing_token,
    acquired_at,
    expires_at,
    released_at
) ON factory.leases TO patchyard_supervisor;
GRANT UPDATE (paused, full_stop, updated_at, updated_by)
ON factory.supervisor_state TO patchyard_supervisor;
GRANT INSERT, UPDATE (status, executed_at, outcome)
ON factory.controls TO patchyard_supervisor;
GRANT INSERT, UPDATE (
    status, external_ref, facts, started_at, finished_at
) ON factory.side_effects TO patchyard_supervisor;

GRANT SELECT ON
    factory.requests,
    factory.runs,
    factory.events,
    factory.artifacts,
    factory.pr_state,
    factory.leases,
    factory.supervisor_state,
    factory.controls
TO patchyard_dashboard;
GRANT INSERT (id, fingerprint, source, body, trace_id) ON factory.requests
TO patchyard_dashboard;
GRANT INSERT (id, command, target_run_id, requested_by, reason)
ON factory.controls TO patchyard_dashboard;

GRANT SELECT (
    request_id,
    source,
    received_at,
    status,
    run_count,
    event_count,
    latest_event_at
) ON factory.grafana_request_summary TO grafana_ro;
GRANT SELECT (
    run_id,
    request_id,
    lane,
    skill,
    state,
    queued_at,
    started_at,
    finished_at,
    input_tokens,
    output_tokens,
    turns,
    eval_scores
) ON factory.grafana_run_metrics TO grafana_ro;

ALTER DEFAULT PRIVILEGES FOR ROLE patchyard_owner IN SCHEMA factory
    REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE patchyard_owner IN SCHEMA factory
    REVOKE ALL ON SEQUENCES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE patchyard_owner IN SCHEMA factory
    REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
