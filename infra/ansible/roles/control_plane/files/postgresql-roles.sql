\set ON_ERROR_STOP on

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'patchyard_owner') THEN
        CREATE ROLE patchyard_owner NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'patchyard_migrator') THEN
        CREATE ROLE patchyard_migrator LOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'patchyard_supervisor') THEN
        CREATE ROLE patchyard_supervisor LOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'patchyard_dashboard') THEN
        CREATE ROLE patchyard_dashboard LOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'grafana_ro') THEN
        CREATE ROLE grafana_ro LOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'patchyard_exporter') THEN
        CREATE ROLE patchyard_exporter LOGIN;
    END IF;
END
$$;

ALTER ROLE patchyard_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
ALTER ROLE patchyard_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
ALTER ROLE patchyard_supervisor LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
ALTER ROLE patchyard_dashboard LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
ALTER ROLE grafana_ro LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
ALTER ROLE patchyard_exporter LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;

ALTER ROLE patchyard_owner PASSWORD NULL;
ALTER ROLE patchyard_migrator PASSWORD NULL;
ALTER ROLE patchyard_supervisor PASSWORD NULL;
ALTER ROLE patchyard_dashboard PASSWORD NULL;
ALTER ROLE grafana_ro PASSWORD NULL;
ALTER ROLE patchyard_exporter PASSWORD NULL;

GRANT patchyard_owner TO patchyard_migrator;
GRANT pg_monitor TO patchyard_exporter;
