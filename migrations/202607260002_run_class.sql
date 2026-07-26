CREATE TYPE factory.run_class AS ENUM ('production', 'qualification');

ALTER TABLE factory.runs
    ADD COLUMN run_class factory.run_class;

-- Session 14's operator path predates the enum but already wrote the durable
-- qualification audit fact. Preserve that evidence when the class becomes a
-- first-class run property.
UPDATE factory.runs AS run
SET run_class = 'qualification'
WHERE EXISTS (
    SELECT 1
    FROM factory.events AS event
    WHERE event.request_id = run.request_id
      AND event.event_type = 'request.claimed'
      AND event.payload @> '{"paused_qualification_bypass": true}'::jsonb
);

UPDATE factory.runs
SET run_class = 'production'
WHERE run_class IS NULL;

ALTER TABLE factory.runs
    ALTER COLUMN run_class SET NOT NULL;

CREATE OR REPLACE FUNCTION factory.enforce_run_class_from_claim()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    claimed_class factory.run_class;
BEGIN
    SELECT CASE event.payload->>'run_class'
        WHEN 'production' THEN 'production'::factory.run_class
        WHEN 'qualification' THEN
            CASE
                WHEN event.payload->>'operator_unit' = 'factory-session14-qualification'
                  AND (
                    event.payload @> '{"qualification_operator_path": true}'::jsonb
                    OR event.payload @> '{"paused_qualification_bypass": true}'::jsonb
                  )
                  AND event.payload->>'qualification_manifest_sha256'
                        = 'cba0ef877fe468043f3a5780a4cbbf0fed8439ca7630cc801b87709268b90383'
                  AND (event.payload->>'request_budget')::integer = 2
                  AND (event.payload->>'run_budget')::integer = 2
                  AND (event.payload->>'wall_time_budget_seconds')::integer = 7200
                  AND event.payload->>'intended_disposition' = 'pr_closed_unmerged'
                    THEN 'qualification'::factory.run_class
                ELSE NULL
            END
        ELSE NULL
    END
    INTO claimed_class
    FROM factory.events AS event
    WHERE event.request_id = NEW.request_id
      AND event.event_type = 'request.claimed'
    ORDER BY event.id DESC
    LIMIT 1;

    IF claimed_class IS NULL THEN
        RAISE EXCEPTION 'run requires a valid durable request.claimed class fact';
    END IF;
    IF NEW.run_class <> claimed_class THEN
        RAISE EXCEPTION 'run class % differs from claimed class %',
            NEW.run_class, claimed_class;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER runs_class_from_claim
BEFORE INSERT ON factory.runs
FOR EACH ROW EXECUTE FUNCTION factory.enforce_run_class_from_claim();

CREATE OR REPLACE FUNCTION factory.prevent_run_class_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'run class is immutable after insertion';
END;
$$;

CREATE TRIGGER runs_class_immutable
BEFORE UPDATE OF run_class ON factory.runs
FOR EACH ROW EXECUTE FUNCTION factory.prevent_run_class_update();

CREATE INDEX runs_class_finished_idx
    ON factory.runs(run_class, finished_at, queued_at, id)
    WHERE finished_at IS NOT NULL;

CREATE OR REPLACE VIEW factory.grafana_request_summary AS
SELECT
    requests.id AS request_id,
    requests.source,
    requests.received_at,
    requests.status::text AS status,
    count(DISTINCT runs.id)::bigint AS run_count,
    count(DISTINCT events.id)::bigint AS event_count,
    max(events.occurred_at) AS latest_event_at
FROM factory.requests
LEFT JOIN factory.runs
    ON runs.request_id = requests.id
   AND runs.run_class = 'production'
LEFT JOIN factory.events ON events.request_id = requests.id
WHERE NOT EXISTS (
    SELECT 1
    FROM factory.events AS qualification_claim
    WHERE qualification_claim.request_id = requests.id
      AND qualification_claim.event_type = 'request.claimed'
      AND (
        qualification_claim.payload->>'run_class' = 'qualification'
        OR qualification_claim.payload @> '{"paused_qualification_bypass": true}'::jsonb
      )
)
GROUP BY requests.id, requests.source, requests.received_at, requests.status;

CREATE OR REPLACE VIEW factory.grafana_run_metrics AS
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
    runs.eval_scores,
    runs.run_class::text AS run_class
FROM factory.runs
WHERE runs.run_class = 'production';

COMMENT ON COLUMN factory.runs.run_class IS
    'A107 production/qualification class, enforced from the durable claim fact';
COMMENT ON VIEW factory.grafana_request_summary IS
    'A94/A107-safe production request aggregates; qualification runs excluded';
COMMENT ON VIEW factory.grafana_run_metrics IS
    'A94/A107-safe production run usage; qualification runs excluded';
