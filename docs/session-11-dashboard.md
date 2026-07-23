# Session 11 dashboard evidence

Session 11 replaces the dashboard shell with the server-rendered factory
control-plane UI. `factory-web` serves Askama pages and vendored CSS over a
Unix socket; the Caddy edge owns public HTTP. The browser receives no external
assets and every HTML response carries a strict per-response nonce CSP.

## Trust and scribe boundary

- The request form calls `factory_core::state::NewRequest::from_intake`, the
  same constructor used by `factoryctl request submit`. Core owns the body and
  source constraints, fingerprint, request id, and trace id.
- The dashboard inserts only intake columns. It has no state-transition,
  capability, triage, verification, or publisher dependency. The database
  grants independently deny update/delete/truncate of requests, runs, events,
  and controls, and deny event insertion.
- Request bodies and event payloads remain Askama-escaped text. Live events
  are appended with `textContent`. The decisions and codebase renderers turn
  raw Markdown HTML tokens into text before generating the only trusted HTML
  fragments.
- Refresh appends a durable reconcile request and wakes the supervisor. The
  supervisor claims that request with a fenced token, runs the existing
  bounded fail-closed reconciler, and records completion.
- Admin controls append pause, resume, per-run kill, and full-stop rows. The
  existing supervisor consumes them; its PostgreSQL test proves kill
  convergence through a terminal `run.killed` ledger event.

## Authentication boundary

Factory accounts live only in factory PostgreSQL with `factory_submit` and
`factory_admin` roles. Password hashes use Argon2id. Bootstrap reads an
owner-only controller file and passes passwords to `factoryctl` on standard
input; passwords are not arguments or Ansible logs.

Every state-changing POST requires a session-derived CSRF token. Login uses a
separate one-use challenge, fixed-cost dummy verification for unknown users,
per-client and per-account throttles, and a new session secret on success.
Cookies are `Secure`, `HttpOnly`, and `SameSite=Strict`. Sessions have sliding
idle and fixed absolute expiry. Account disable and password reset revoke all
sessions through a version fence and a `factory_auth` notification. Login,
submission, account, and control actions append audit rows.

## Live and projection views

- `/request/<id>` renders the event ledger at first paint and opens
  `/request/<id>/events?after=<last-rendered-id>`. The SSE handler performs one
  durable catch-up query, then wakes only through PostgreSQL `LISTEN/NOTIFY`;
  browser reconnects resume from `Last-Event-ID`. Non-terminal pages also
  receive `Refresh: 15`.
- The Caddy events matcher disables response buffering and stream timeouts.
  The dashboard closes SSE on terminal events, browser disconnect, session
  expiry, or account revocation and explicitly releases its listener.
- `/decisions`, `/bench`, `/model`, and `/codebase` read canonical checkout
  projections. `/model` overlays active run dots using the same SSE stream.
  `/schema` reads live catalog shape and count-only relation statistics through
  a fixed-search-path security-definer function; the dashboard cannot select
  application rows merely to count them.
- `tools/check-codebase.sh` installs the exact pinned and checksum-verified
  `tokei` source, generates role-grouped metrics, and rejects any byte
  difference in CI.

## Service boundary

`factory-dashboard.service` runs as `factory-web` with no capabilities,
`AF_UNIX` only, an empty privilege set, a strict filesystem, and writable paths
limited to its runtime directory and the designated spool/artifact trees. A
root-only bounded post-start helper changes only the verified dashboard socket
to `caddy:factory-web` mode `0660`. Caddy has only its state/log paths writable,
cannot read artifact or factory credential trees, and keeps only
`CAP_NET_BIND_SERVICE`.

Existing artifacts converge to owner `factory-manager`, group `factory-web`,
setgid directory mode `2750`, and file mode `0640`. New artifact writes use
that same contract. Caddy can reach evidence only through the authenticated
dashboard route.

## Qualification

Committed tests cover:

- the exact anonymous/submitter/admin result for every route, including SSE
  and every state-changing POST;
- hostile request and event strings remaining inert, strict nonce CSP, and
  raw-HTML-disabled Markdown;
- secure session rotation, revocation, idle/absolute expiry, failed-login
  throttling, and audit rows;
- the PostgreSQL dashboard role's direct-SQL denials;
- a seeded event delivered as an SSE frame within one second and the
  non-terminal refresh fallback;
- browser-form submission waking the Session 9 listener, producing a claimed
  run, and a real `factoryctl pause` preventing the next claim;
- the scribe-only dependency and method surface;
- exact systemd/Caddy/socket hardening and the generated schema and codebase
  projections.

## Escalations

1. Session 10's A103 escalation remains open. No authoritative Fieldbook
   deployed SHA exists in a control-plane-local projection that the current
   GitHub App can read. Session 11 installs an explicit fail-closed
   deployed-version program so the supervisor can run and service refresh
   requests without inventing a marker; reconciliation records the source
   failure and never classifies a merged run as passing. Production marker
   publication remains a separate human-ruling and Fieldbook-deployment change.

2. The repository does not name the initial bare `factory_submit` identity.
   A33 names Jacob, Engineer Two, and the Owner as approvers, which implies evidence
   access but does not decide which additional staff member receives submit-
   only access. A69 requires bootstrap identities and roles in Git, while
   credentials stay secret. The implementation therefore accepts an
   owner-only bootstrap file and proves the required two-admin/one-submitter
   shape, but production convergence must not proceed until Jacob rules the
   submit-only identity and the resulting identity/role list is committed;
   that thread is intentionally not resolved by the builder.
