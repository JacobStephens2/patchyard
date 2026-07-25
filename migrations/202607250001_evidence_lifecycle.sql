ALTER TYPE factory.run_state ADD VALUE IF NOT EXISTS 'awaiting_ci';
ALTER TYPE factory.run_state ADD VALUE IF NOT EXISTS 'capturing_evidence';
ALTER TYPE factory.run_state ADD VALUE IF NOT EXISTS 'finalizing_pr';

ALTER TYPE factory.run_state ADD VALUE IF NOT EXISTS 'ci_failed';
ALTER TYPE factory.run_state ADD VALUE IF NOT EXISTS 'ci_cancelled';
ALTER TYPE factory.run_state ADD VALUE IF NOT EXISTS 'ci_job_timed_out';
ALTER TYPE factory.run_state ADD VALUE IF NOT EXISTS 'ci_action_required';
ALTER TYPE factory.run_state ADD VALUE IF NOT EXISTS 'ci_neutral';
ALTER TYPE factory.run_state ADD VALUE IF NOT EXISTS 'ci_skipped';
ALTER TYPE factory.run_state ADD VALUE IF NOT EXISTS 'ci_stale';
ALTER TYPE factory.run_state ADD VALUE IF NOT EXISTS 'ci_startup_failed';
ALTER TYPE factory.run_state ADD VALUE IF NOT EXISTS 'ci_wait_timed_out';
ALTER TYPE factory.run_state ADD VALUE IF NOT EXISTS 'ci_observation_failed';
ALTER TYPE factory.run_state ADD VALUE IF NOT EXISTS 'preview_failed';
ALTER TYPE factory.run_state ADD VALUE IF NOT EXISTS 'preview_timed_out';
ALTER TYPE factory.run_state ADD VALUE IF NOT EXISTS 'preview_sha_changed';
ALTER TYPE factory.run_state ADD VALUE IF NOT EXISTS 'evidence_failed';
ALTER TYPE factory.run_state ADD VALUE IF NOT EXISTS 'secret_scan_failed';
ALTER TYPE factory.run_state ADD VALUE IF NOT EXISTS 'lease_cleanup_failed';
ALTER TYPE factory.run_state ADD VALUE IF NOT EXISTS 'pr_contract_failed';

COMMENT ON COLUMN factory.pr_state.ci_state IS
    'Session 14 bounded GitHub check-run wait state at the exact PR head';
COMMENT ON COLUMN factory.pr_state.review_state IS
    'Session 14 draft, finalizing, ready-for-review, or fail-closed review state';
