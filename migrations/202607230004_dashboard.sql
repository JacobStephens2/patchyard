CREATE TYPE factory.account_role AS ENUM (
    'factory_submit',
    'factory_admin'
);

CREATE TABLE factory.users (
    id uuid PRIMARY KEY,
    username text NOT NULL UNIQUE,
    display_name text NOT NULL,
    password_hash text NOT NULL,
    role factory.account_role NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    password_reset_required boolean NOT NULL DEFAULT false,
    session_version bigint NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    disabled_at timestamptz,
    password_reset_at timestamptz,
    CONSTRAINT users_username_canonical CHECK (
        username = lower(btrim(username))
        AND username <> ''
        AND octet_length(username) <= 254
    ),
    CONSTRAINT users_display_name_not_blank CHECK (
        btrim(display_name) <> '' AND octet_length(display_name) <= 128
    ),
    CONSTRAINT users_password_hash_argon2id CHECK (
        password_hash LIKE '$argon2id$%'
    ),
    CONSTRAINT users_session_version_positive CHECK (session_version > 0),
    CONSTRAINT users_disable_shape CHECK (
        (enabled AND disabled_at IS NULL)
        OR (NOT enabled AND disabled_at IS NOT NULL)
    )
);

CREATE TABLE factory.sessions (
    token_hash bytea PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES factory.users(id),
    csrf_hash bytea NOT NULL,
    session_version bigint NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    last_seen_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    idle_expires_at timestamptz NOT NULL,
    absolute_expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    CONSTRAINT sessions_token_sha256 CHECK (octet_length(token_hash) = 32),
    CONSTRAINT sessions_csrf_sha256 CHECK (octet_length(csrf_hash) = 32),
    CONSTRAINT sessions_expiry_ordered CHECK (
        last_seen_at >= created_at
        AND idle_expires_at > last_seen_at
        AND absolute_expires_at >= idle_expires_at
    ),
    CONSTRAINT sessions_version_positive CHECK (session_version > 0)
);

CREATE INDEX sessions_user_active_idx
    ON factory.sessions(user_id, absolute_expires_at)
    WHERE revoked_at IS NULL;

CREATE TABLE factory.login_challenges (
    token_hash bytea PRIMARY KEY,
    csrf_hash bytea NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    expires_at timestamptz NOT NULL,
    used_at timestamptz,
    CONSTRAINT login_challenges_token_sha256 CHECK (octet_length(token_hash) = 32),
    CONSTRAINT login_challenges_csrf_sha256 CHECK (octet_length(csrf_hash) = 32),
    CONSTRAINT login_challenges_expiry_ordered CHECK (expires_at > created_at),
    CONSTRAINT login_challenges_used_ordered CHECK (
        used_at IS NULL OR used_at >= created_at
    )
);

CREATE INDEX login_challenges_expiry_idx ON factory.login_challenges(expires_at);

CREATE TABLE factory.login_attempts (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username text NOT NULL,
    client_key text NOT NULL,
    succeeded boolean NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT login_attempts_username_not_blank CHECK (
        btrim(username) <> '' AND octet_length(username) <= 254
    ),
    CONSTRAINT login_attempts_client_not_blank CHECK (
        btrim(client_key) <> '' AND octet_length(client_key) <= 128
    )
);

CREATE INDEX login_attempts_throttle_idx
    ON factory.login_attempts(username, client_key, occurred_at DESC);

CREATE TABLE factory.audit_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id uuid REFERENCES factory.users(id),
    action text NOT NULL,
    subject text NOT NULL,
    client_key text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT audit_events_action_not_blank CHECK (
        btrim(action) <> '' AND octet_length(action) <= 64
    ),
    CONSTRAINT audit_events_subject_bounded CHECK (
        octet_length(subject) <= 256
    ),
    CONSTRAINT audit_events_client_not_blank CHECK (
        btrim(client_key) <> '' AND octet_length(client_key) <= 128
    )
);

CREATE INDEX audit_events_user_time_idx
    ON factory.audit_events(user_id, occurred_at DESC);

CREATE OR REPLACE FUNCTION factory.reject_audit_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'factory audit rows are append-only';
END;
$$;

CREATE TRIGGER audit_events_append_only
BEFORE UPDATE OR DELETE ON factory.audit_events
FOR EACH ROW EXECUTE FUNCTION factory.reject_audit_mutation();

CREATE TRIGGER login_attempts_append_only
BEFORE UPDATE OR DELETE ON factory.login_attempts
FOR EACH ROW EXECUTE FUNCTION factory.reject_audit_mutation();

CREATE TABLE factory.reconcile_requests (
    id uuid PRIMARY KEY,
    request_id uuid NOT NULL REFERENCES factory.requests(id),
    requested_by uuid NOT NULL REFERENCES factory.users(id),
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'executing', 'completed', 'failed')),
    requested_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    claim_token uuid,
    claimed_at timestamptz,
    executed_at timestamptz,
    outcome jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT reconcile_requests_claim_shape CHECK (
        (status = 'pending' AND claim_token IS NULL AND claimed_at IS NULL)
        OR (
            status IN ('executing', 'completed', 'failed')
            AND claim_token IS NOT NULL
            AND claimed_at IS NOT NULL
        )
    ),
    CONSTRAINT reconcile_requests_execution_shape CHECK (
        (status IN ('pending', 'executing') AND executed_at IS NULL)
        OR (status IN ('completed', 'failed') AND executed_at IS NOT NULL)
    )
);

CREATE INDEX reconcile_requests_pending_idx
    ON factory.reconcile_requests(status, claimed_at, requested_at, id)
    WHERE status IN ('pending', 'executing');

CREATE OR REPLACE FUNCTION factory.notify_event_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM pg_notify('factory_events', NEW.request_id::text);
    RETURN NEW;
END;
$$;

CREATE TRIGGER events_notify_after_insert
AFTER INSERT ON factory.events
FOR EACH ROW EXECUTE FUNCTION factory.notify_event_insert();

CREATE OR REPLACE FUNCTION factory.notify_auth_revocation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_TABLE_NAME = 'sessions' THEN
        IF OLD.revoked_at IS NULL AND NEW.revoked_at IS NOT NULL THEN
            PERFORM pg_notify('factory_auth', NEW.user_id::text);
        END IF;
    ELSIF
        OLD.enabled IS DISTINCT FROM NEW.enabled
        OR OLD.password_reset_required IS DISTINCT FROM NEW.password_reset_required
        OR OLD.session_version IS DISTINCT FROM NEW.session_version
    THEN
        PERFORM pg_notify('factory_auth', NEW.id::text);
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER sessions_notify_after_revoke
AFTER UPDATE ON factory.sessions
FOR EACH ROW EXECUTE FUNCTION factory.notify_auth_revocation();

CREATE TRIGGER users_notify_after_auth_change
AFTER UPDATE ON factory.users
FOR EACH ROW EXECUTE FUNCTION factory.notify_auth_revocation();

CREATE OR REPLACE FUNCTION factory.notify_reconcile_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM pg_notify('factory_reconcile', NEW.id::text);
    RETURN NEW;
END;
$$;

CREATE TRIGGER reconcile_requests_notify_after_insert
AFTER INSERT ON factory.reconcile_requests
FOR EACH ROW EXECUTE FUNCTION factory.notify_reconcile_insert();

CREATE OR REPLACE FUNCTION factory.schema_relation_counts()
RETURNS TABLE (relation_name text, row_count bigint)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    relation record;
BEGIN
    FOR relation IN
        SELECT class.relname
        FROM pg_catalog.pg_class AS class
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid=class.relnamespace
        WHERE namespace.nspname='factory'
          AND class.relkind IN ('r','v')
        ORDER BY class.relname
    LOOP
        relation_name := relation.relname;
        EXECUTE format(
            'SELECT count(*)::bigint FROM factory.%I',
            relation.relname
        ) INTO row_count;
        RETURN NEXT;
    END LOOP;
END;
$$;

COMMENT ON TABLE factory.users IS
    'A68 factory-native identities and factory_submit/factory_admin authorization';
COMMENT ON TABLE factory.sessions IS
    'Server-side sessions with idle and absolute expiry; cookie holds only the rotating token';
COMMENT ON TABLE factory.login_challenges IS
    'Single-use anonymous CSRF challenges for the state-changing login POST';
COMMENT ON TABLE factory.audit_events IS
    'Append-only A-11 logins, submissions, refreshes, and control-action audit trail';
COMMENT ON TABLE factory.reconcile_requests IS
    'A53 scribe-safe dashboard refresh queue; the supervisor performs bounded reconciliation';
COMMENT ON FUNCTION factory.schema_relation_counts() IS
    'A72 count-only security-definer projection; reveals no relation rows';
