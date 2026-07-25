ALTER TABLE factory.runs
    ADD COLUMN lifecycle_attempts smallint NOT NULL DEFAULT 0,
    ADD CONSTRAINT runs_lifecycle_attempts_bounded CHECK (
        lifecycle_attempts BETWEEN 0 AND 3
    );

ALTER TABLE factory.pr_state
    ADD CONSTRAINT pr_state_ci_state_known CHECK (
        ci_state IN (
            'pending',
            'unknown',
            'waiting',
            'success',
            'deployed',
            'not_passing'
        )
    ),
    ADD CONSTRAINT pr_state_review_state_known CHECK (
        review_state IN (
            'unknown',
            'pending',
            'draft',
            'finalizing',
            'ready_for_review',
            'approved',
            'admin_bypassed'
        )
    );

COMMENT ON COLUMN factory.runs.lifecycle_attempts IS
    'Bounded Session 14 lifecycle entries: one initial attempt plus at most two resumptions';
