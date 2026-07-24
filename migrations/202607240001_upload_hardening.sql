CREATE TYPE factory.upload_admission_state AS ENUM (
    'admitted',
    'completed',
    'rejected'
);

CREATE TABLE factory.upload_admissions (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES factory.users(id),
    request_id uuid REFERENCES factory.requests(id),
    state factory.upload_admission_state NOT NULL,
    content_length bigint NOT NULL,
    reserved_bytes bigint NOT NULL,
    actual_bytes bigint,
    reason text,
    admitted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    expires_at timestamptz NOT NULL,
    finished_at timestamptz,
    CONSTRAINT upload_admissions_content_length_positive CHECK (
        content_length > 0
    ),
    CONSTRAINT upload_admissions_bytes_nonnegative CHECK (
        reserved_bytes >= 0
        AND (actual_bytes IS NULL OR actual_bytes >= 0)
    ),
    CONSTRAINT upload_admissions_reason_bounded CHECK (
        reason IS NULL OR (
            btrim(reason) <> '' AND octet_length(reason) <= 64
        )
    ),
    CONSTRAINT upload_admissions_expiry_ordered CHECK (
        expires_at > admitted_at
    ),
    CONSTRAINT upload_admissions_state_shape CHECK (
        (
            state = 'admitted'
            AND request_id IS NULL
            AND actual_bytes IS NULL
            AND reason IS NULL
            AND finished_at IS NULL
        )
        OR (
            state = 'completed'
            AND request_id IS NOT NULL
            AND actual_bytes IS NOT NULL
            AND reserved_bytes = actual_bytes
            AND reason IS NULL
            AND finished_at IS NOT NULL
        )
        OR (
            state = 'rejected'
            AND request_id IS NULL
            AND actual_bytes IS NULL
            AND reserved_bytes = 0
            AND reason IS NOT NULL
            AND finished_at IS NOT NULL
        )
    )
);

CREATE INDEX upload_admissions_user_time_idx
    ON factory.upload_admissions(user_id, admitted_at DESC);

CREATE INDEX upload_admissions_pending_expiry_idx
    ON factory.upload_admissions(expires_at)
    WHERE state = 'admitted';

CREATE UNIQUE INDEX artifacts_one_request_screenshot_idx
    ON factory.artifacts(request_id)
    WHERE run_id IS NULL
      AND kind IN ('request-screenshot-png', 'request-screenshot-jpeg');

COMMENT ON TABLE factory.upload_admissions IS
    'Transactional pre-body upload quota/rate reservations; intake bookkeeping under A53';
