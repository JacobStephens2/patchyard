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
    factory.side_effects,
    factory.publisher_leases,
    factory.github_state,
    factory.reconcile_requests,
    factory.proposer_runs,
    factory.proposer_events,
    factory.proposer_artifacts,
    factory.proposer_publisher_lease
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
    base_tree_hash,
    lifecycle_attempts
) ON factory.runs TO patchyard_supervisor;
GRANT INSERT ON factory.events TO patchyard_supervisor;
GRANT USAGE, SELECT ON SEQUENCE factory.events_id_seq TO patchyard_supervisor;
GRANT INSERT ON factory.artifacts TO patchyard_supervisor;
GRANT UPDATE (expires_at, deleted_at) ON factory.artifacts TO patchyard_supervisor;
GRANT INSERT ON factory.pr_state TO patchyard_supervisor;
GRANT UPDATE (
    request_id,
    run_id,
    head_sha,
    ci_state,
    review_state,
    reconciled_at,
    merged_at,
    deployed_sha,
    branch,
    state,
    is_draft,
    author_login,
    html_url,
    merge_commit_sha,
    merged_by,
    github_updated_at,
    admin_bypassed,
    passing_run,
    reconcile_error
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
GRANT INSERT, UPDATE (
    request_id, run_id, holder, fencing_token, acquired_at, expires_at, released_at
) ON factory.publisher_leases TO patchyard_supervisor;
GRANT INSERT, UPDATE (
    observed_at, failed_at, last_error, open_pr_count
) ON factory.github_state TO patchyard_supervisor;
GRANT UPDATE (
    status, claim_token, claimed_at, executed_at, outcome
) ON factory.reconcile_requests TO patchyard_supervisor;
GRANT INSERT, UPDATE (
    state, report_sha256, report_max_event_id, prompt_bundle_sha256,
    branch, patch_sha256, reviewed_sha, pr_title, pr_body,
    review_artifact, disposition_artifact, abort_requested,
    pr_number, pr_url, failure_code,
    started_at, finished_at
) ON factory.proposer_runs TO patchyard_supervisor;
GRANT INSERT ON factory.proposer_events TO patchyard_supervisor;
GRANT USAGE, SELECT ON SEQUENCE factory.proposer_events_id_seq
TO patchyard_supervisor;
GRANT INSERT ON factory.proposer_artifacts TO patchyard_supervisor;
GRANT UPDATE (expires_at, deleted_at)
ON factory.proposer_artifacts TO patchyard_supervisor;
GRANT UPDATE (
    holder, fencing_token, acquired_at, expires_at, released_at
) ON factory.proposer_publisher_lease TO patchyard_supervisor;

GRANT SELECT ON
    factory.requests,
    factory.runs,
    factory.events,
    factory.artifacts,
    factory.pr_state,
    factory.leases,
    factory.supervisor_state,
    factory.controls,
    factory.users,
    factory.sessions,
    factory.login_challenges,
    factory.login_attempts,
    factory.audit_events,
    factory.upload_admissions,
    factory.reconcile_requests
TO patchyard_dashboard;
GRANT INSERT (id, fingerprint, source, body, trace_id) ON factory.requests
TO patchyard_dashboard;
GRANT INSERT (id, command, target_run_id, requested_by, reason)
ON factory.controls TO patchyard_dashboard;
GRANT INSERT (
    token_hash, csrf_hash, expires_at
) ON factory.login_challenges TO patchyard_dashboard;
GRANT UPDATE (used_at) ON factory.login_challenges TO patchyard_dashboard;
GRANT INSERT (
    token_hash, user_id, csrf_hash, session_version,
    idle_expires_at, absolute_expires_at
) ON factory.sessions TO patchyard_dashboard;
GRANT UPDATE (
    last_seen_at, idle_expires_at, revoked_at
) ON factory.sessions TO patchyard_dashboard;
GRANT INSERT (username, client_key, succeeded)
ON factory.login_attempts TO patchyard_dashboard;
GRANT INSERT (user_id, action, subject, client_key, metadata)
ON factory.audit_events TO patchyard_dashboard;
GRANT INSERT (
    id, user_id, state, content_length, reserved_bytes, expires_at,
    finished_at, reason
) ON factory.upload_admissions TO patchyard_dashboard;
GRANT UPDATE (
    request_id, state, reserved_bytes, actual_bytes, reason, finished_at
) ON factory.upload_admissions TO patchyard_dashboard;
GRANT INSERT (id, request_id, run_id, path, sha256, kind)
ON factory.artifacts TO patchyard_dashboard;
GRANT INSERT (id, request_id, requested_by)
ON factory.reconcile_requests TO patchyard_dashboard;
GRANT USAGE, SELECT ON SEQUENCE
    factory.login_attempts_id_seq,
    factory.audit_events_id_seq
TO patchyard_dashboard;
GRANT EXECUTE ON FUNCTION factory.schema_relation_counts()
TO patchyard_dashboard;

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
    eval_scores,
    run_class
) ON factory.grafana_run_metrics TO grafana_ro;

ALTER DEFAULT PRIVILEGES FOR ROLE patchyard_owner IN SCHEMA factory
    REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE patchyard_owner IN SCHEMA factory
    REVOKE ALL ON SEQUENCES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE patchyard_owner IN SCHEMA factory
    REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
