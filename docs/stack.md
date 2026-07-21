# Technology stack

*Living document - the canonical answer to "what is the factory built with, and why not the obvious alternatives." Each choice cites its ruling; the exclusions are enforced by `tools/check-stack.py` in CI (the doctrine-drift tripwire). This is a document, not a second model: the machine-relevant infrastructure facts live in `model/factory-model.json`'s deployment block; what's here is the full inventory with rationale, which has human readers and no machine consumers beyond the exclusions check.*

## Languages (A42)

| Language | Used for |
| :-- | :-- |
| Rust | Everything the factory *is*: `factory-core`, `factory-supervisor` (A67), `factory-verify`, `factoryctl`, `factory-web`. Toolchain pinned (`rust-toolchain.toml`), `Cargo.lock` committed, `cargo audit` + `cargo deny` in CI |
| Python | Where its ecosystem owns the job: model tooling, Selenium evidence harness, bench/AA tooling (`tools/`) |
| SQL | PostgreSQL schema and migrations |
| HCL | OpenTofu configuration (`infra/<provider>/`) - the tool itself is a pinned Go binary; HCL is what we author and review |
| YAML | Ansible (all host configuration) and GitHub Actions workflows - declaration languages only, never application code |
| Bash | Glue scripts (`model/check-model.sh` and friends) |
| Markdown | Prompts, policy, constitution, rubric, docs - everything humans and models read |

## Web layer (A53, A63, A64, A70-A72, A75)

- **Axum + Askama** on tokio: server-side rendering; SSE endpoints fed by Postgres `LISTEN/NOTIFY`.
- **Vanilla JavaScript, slight**: `EventSource` fragments and the run-dot overlay. All other interactivity is form POSTs.
- **terminal.css (vendored, MIT) + patchyard-theme.css**: matrix-boxy Patchyard look; every asset self-hosted.
- **pulldown-cmark**: server-side markdown rendering for `/decisions`.
- **Factory-native auth** (A68): argon2, server-side sessions, own users table.

## Data and state

- **PostgreSQL** (A56): local socket-only, peer auth, role grant matrix; `LISTEN/NOTIFY` triples as queue wake-up (A65), SSE push (A63), and control-row delivery (A70). Access via **SQLx** behind a domain repository boundary.
- **MySQL 8.4, worker parity only** (A85): a per-run local instance inside the worker isolation boundary, seeded from a dated redacted snapshot artifact - the *subject* codebase's engine, never factory state (which is PostgreSQL).
- **Filesystem artifact store** (A43): `/var/lib/patchyard`, 0700.
- **Git** (A69): every encodable fact, including infrastructure, DNS, branch protection, and this file.

## Infrastructure (A57, A68, A69)

- **DigitalOcean**: control-plane VM + secret-free worker droplet.
- **OpenTofu**: droplets, Route 53 DNS, firewalls, GitHub repo settings/branch protection; state in S3 `example-tofu-state` (A96: versioned, SSE, lockfile locking) + client-side state encryption.
- **Ansible**: Caddy, systemd units + hardening, Postgres roles, headless Chromium, bootstrap accounts.
- **Firecracker microVM** / **rootless Podman** (A44, A91): the worker's OS boundary - a half-session time-boxed probe decides, with ties going to Firecracker's kernel boundary; Podman is the accepted outcome only on material operational cost or absent KVM.
- **Caddy**: TLS/reverse proxy. **1Password**: vault of record; factory-scoped secret injection only.

## AI layer (A41/A78, A61, A67, A73, A74)

- **Claude Code headless** (`claude -p`) and **Codex** (`codex exec`, A73 adversarial reviews) as daemon-exec'd subprocesses - agents live on the far side of an exec boundary, never in-process.
- **Seat routing** (A74): every invocation resolves through the versioned `policy/` routing config against the canonical bench (`docs/bench.json`); one provider per worker boot; A61 allowlist.
- Construction: GPT-5.6 Sol × Codex builds; Fable 5 × Claude Code reviews every build PR (A41, seats amended by A78); humans merge.

## Verification and CI

- **factory-verify** with mutation self-tests (A10); **pass^k** acceptance; targeted **PHPUnit**; **Selenium/Chromium** preview evidence.
- **GitHub Actions**, factory-repo hygiene only (R4): thin YAML wrappers over repo scripts so the CI backend is swappable in an afternoon. Executes on **GitHub-hosted runners** (A76 amended by A88, disposition E-1): `runs-on: ubuntu-latest` + a Rust cache action for warm builds; no runner process on any factory host - kernel co-tenancy with the ledger was the council's unanimous top removal. Escalation path if private-network CI is ever measured to be needed: an ephemeral single-job runner on a disposable droplet, never the ledger VM. **GitHub App** bot identity (A45/A62).

## Observability (A79/A80/A82-A84, A90/A92/A94 ruled; Loki direction)

The **ledger is the primary observability system** - cost, latency, and outcome questions are SQL. Ruled: **Prometheus + Grafana (A80)** - daemon `/metrics`, node/postgres exporters on both hosts, Grafana reading factory PostgreSQL directly for ledger dashboards, pull-based scraping only (expose-never-require, A68); and **server-side usage metrics (A79/R23, phase-1 scope deferred by A92)** - Caddy logs + ledger audit events serve phase 1; the page-view middleware waits for a usage question asked twice; no client-side trackers, ever. Also ruled: **OpenTelemetry in phase 1 (A82, deployment half amended by A90)** - `tracing` instrumentation day one, OTLP exporter fail-open and **dormant** (endpoint empty; Tempo is evidence- or fleet-triggered, never factory-triggered; trace id rides the queued row across the NOTIFY hop); and **full-transcript capture (A83)** - every agent invocation's harness transcript into the artifact store, the content-level record spans can't give. Placement ruled (A84): the existing fleet Grafana (`grafana.example.com`) + Prometheus scrape the factory hosts over the private network, Tempo joins that stack, and one `grafana_ro` VPC-only role is A56's sole TCP exception - an audited exposure (A94), column-pinned to metadata/aggregate views with a canary-content test; cert expiry alerted. Still direction: whether Loki ever earns a place. A fleet-level Grafana/Prometheus host may scrape the factory (expose-never-require keeps A68 intact). No Google Analytics - external beacons don't belong on an internal admin surface.

## Deliberately excluded - enforced by `tools/check-stack.py`

| Exclusion | Ruling / reason | Tripwire artifact |
| :-- | :-- | :-- |
| npm / node toolchain | A53; supply-chain surface for zero benefit | `package.json`, `node_modules/`, `package-lock.json` |
| TypeScript | A53; second type system that drifts from the Rust one | `tsconfig.json`, `*.ts` sources |
| WASM / front-end frameworks | A53; no client-owned state to manage (Leptos is the named escalation if that ever changes) | - (review-caught) |
| Docker Compose / Kubernetes / Helm | Scale mismatch; systemd + Ansible own the hosts | `docker-compose.yml`, `Chart.yaml`, `helmfile` |
| In-process agent SDKs | Agents exec as subprocesses (A44/A67) | - (review-caught) |
| Cloud queues/buses | Postgres LISTEN/NOTIFY does it | - (review-caught) |
| Third-party control planes | R11 - vendors supply workers, never the control plane | - |
| Subscription-gated dependencies | R22 | - |
| Plaintext OpenTofu state in git | A69 | `*.tfstate` |
