-- Terminal requests are durable audit records, not permanent suppression keys.
-- Keep exactly one live intake for a fingerprint while permitting a fresh
-- dashboard submission after a terminal outcome.
ALTER TABLE factory.requests
    DROP CONSTRAINT requests_fingerprint_key;

CREATE UNIQUE INDEX requests_live_fingerprint_unique
    ON factory.requests (fingerprint)
    WHERE status IN ('queued', 'claimed', 'plan_bin');
