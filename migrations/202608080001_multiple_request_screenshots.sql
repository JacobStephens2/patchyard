ALTER TABLE factory.artifacts
    ADD COLUMN request_upload_ordinal smallint;

UPDATE factory.artifacts
SET request_upload_ordinal = 1
WHERE run_id IS NULL
  AND kind IN ('request-screenshot-png', 'request-screenshot-jpeg');

ALTER TABLE factory.artifacts
    ADD CONSTRAINT artifacts_request_upload_ordinal_shape CHECK (
        (
            run_id IS NULL
            AND kind IN ('request-screenshot-png', 'request-screenshot-jpeg')
            AND (
                request_upload_ordinal IS NULL
                OR request_upload_ordinal BETWEEN 1 AND 2
            )
        )
        OR (
            (run_id IS NOT NULL
             OR kind NOT IN ('request-screenshot-png', 'request-screenshot-jpeg'))
            AND request_upload_ordinal IS NULL
        )
    );

-- A legacy single-file binary omits the ordinal. Treat its NULL as slot 1 so
-- an application rollback can still write one screenshot per request.
CREATE UNIQUE INDEX artifacts_request_screenshot_ordinal_idx
    ON factory.artifacts(request_id, COALESCE(request_upload_ordinal, 1))
    WHERE run_id IS NULL
      AND kind IN ('request-screenshot-png', 'request-screenshot-jpeg');

DROP INDEX factory.artifacts_one_request_screenshot_idx;
