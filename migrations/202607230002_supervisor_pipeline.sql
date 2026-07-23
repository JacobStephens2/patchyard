ALTER TYPE factory.run_state ADD VALUE IF NOT EXISTS 'reviewing' AFTER 'implementing';
ALTER TYPE factory.run_state ADD VALUE IF NOT EXISTS 'repairing' AFTER 'verifying';
ALTER TYPE factory.run_state ADD VALUE IF NOT EXISTS 'verified' AFTER 'repairing';
ALTER TYPE factory.run_state ADD VALUE IF NOT EXISTS 'dry_run_complete' AFTER 'verified';
ALTER TYPE factory.run_state ADD VALUE IF NOT EXISTS 'escalated' AFTER 'failed';

ALTER TABLE factory.runs
    ADD COLUMN model_id text,
    ADD COLUMN cli_version text,
    ADD COLUMN harness text,
    ADD COLUMN provider text,
    ADD COLUMN effort text,
    ADD COLUMN routing_config_version text;

ALTER TABLE factory.runs
    ADD CONSTRAINT runs_routing_provenance_all_or_none CHECK (
        (model_id IS NULL AND cli_version IS NULL AND harness IS NULL
            AND provider IS NULL AND effort IS NULL
            AND routing_config_version IS NULL)
        OR
        (btrim(model_id) <> '' AND btrim(cli_version) <> ''
            AND btrim(harness) <> '' AND btrim(provider) <> ''
            AND btrim(effort) <> '' AND btrim(routing_config_version) <> '')
    );

CREATE TABLE factory.supervisor_state (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    paused boolean NOT NULL DEFAULT false,
    full_stop boolean NOT NULL DEFAULT false,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_by text NOT NULL DEFAULT 'bootstrap',
    CONSTRAINT supervisor_state_actor_not_blank CHECK (btrim(updated_by) <> '')
);

INSERT INTO factory.supervisor_state (singleton) VALUES (true);

CREATE TABLE factory.controls (
    id uuid PRIMARY KEY,
    command text NOT NULL CHECK (command IN ('pause', 'resume', 'kill', 'full_stop')),
    target_run_id uuid REFERENCES factory.runs(id),
    requested_by text NOT NULL,
    reason text NOT NULL,
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'executing', 'completed', 'failed')),
    requested_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    executed_at timestamptz,
    outcome jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT controls_actor_not_blank CHECK (btrim(requested_by) <> ''),
    CONSTRAINT controls_reason_not_blank CHECK (btrim(reason) <> ''),
    CONSTRAINT controls_target_shape CHECK (
        (command = 'kill' AND target_run_id IS NOT NULL)
        OR (command <> 'kill' AND target_run_id IS NULL)
    ),
    CONSTRAINT controls_execution_shape CHECK (
        (status IN ('pending', 'executing') AND executed_at IS NULL)
        OR (status IN ('completed', 'failed') AND executed_at IS NOT NULL)
    )
);

CREATE INDEX controls_pending_idx
    ON factory.controls(requested_at, id) WHERE status IN ('pending', 'executing');

CREATE TABLE factory.side_effects (
    idempotency_key text PRIMARY KEY,
    request_id uuid NOT NULL REFERENCES factory.requests(id),
    run_id uuid REFERENCES factory.runs(id),
    effect_type text NOT NULL,
    attempt smallint NOT NULL DEFAULT 0 CHECK (attempt BETWEEN 0 AND 1),
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'completed', 'compensated', 'failed')),
    external_ref text,
    facts jsonb NOT NULL DEFAULT '{}'::jsonb,
    started_at timestamptz,
    finished_at timestamptz,
    CONSTRAINT side_effects_key_not_blank CHECK (btrim(idempotency_key) <> ''),
    CONSTRAINT side_effects_type_not_blank CHECK (btrim(effect_type) <> ''),
    CONSTRAINT side_effects_times_ordered CHECK (
        (started_at IS NULL OR status <> 'pending')
        AND (finished_at IS NULL OR started_at IS NOT NULL)
        AND (finished_at IS NULL OR finished_at >= started_at)
    )
);

CREATE INDEX side_effects_run_idx ON factory.side_effects(run_id, effect_type, attempt);

CREATE OR REPLACE FUNCTION factory.notify_durable_work()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM pg_notify(
        CASE TG_TABLE_NAME
            WHEN 'controls' THEN 'factory_control'
            ELSE 'factory_intake'
        END,
        NEW.id::text
    );
    RETURN NEW;
END;
$$;

CREATE TRIGGER requests_notify_after_insert
AFTER INSERT ON factory.requests
FOR EACH ROW EXECUTE FUNCTION factory.notify_durable_work();

CREATE TRIGGER controls_notify_after_insert
AFTER INSERT ON factory.controls
FOR EACH ROW EXECUTE FUNCTION factory.notify_durable_work();

COMMENT ON TABLE factory.controls IS
    'A70 durable control channel; rows are the audit trail and NOTIFY is wake-only';
COMMENT ON TABLE factory.side_effects IS
    'State-derived idempotency ledger for external pipeline effects';
