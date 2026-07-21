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
- **Filesystem artifact store** (A43): `/var/lib/patchyard`, 0700.
- **Git** (A69): every encodable fact, including infrastructure, DNS, branch protection, and this file.

## Infrastructure (A57, A68, A69)

- **DigitalOcean**: control-plane VM + secret-free worker droplet.
- **OpenTofu**: droplets, Route 53 DNS, firewalls, GitHub repo settings/branch protection; encrypted state backend (session-0 choice).
- **Ansible**: Caddy, systemd units + hardening, Postgres roles, headless Chromium, bootstrap accounts.
- **Firecracker microVM** (evaluate first) / **rootless Podman** (fallback) (A44): the worker's OS boundary.
- **Caddy**: TLS/reverse proxy. **1Password**: vault of record; factory-scoped secret injection only.

## AI layer (A41/A78, A61, A67, A73, A74)

- **Claude Code headless** (`claude -p`) and **Codex** (`codex exec`, A73 adversarial reviews) as daemon-exec'd subprocesses - agents live on the far side of an exec boundary, never in-process.
- **Seat routing** (A74): every invocation resolves through the versioned `policy/` routing config against the canonical bench (`docs/bench.json`); one provider per worker boot; A61 allowlist.
- Construction: GPT-5.6 Sol × Codex builds; Fable 5 × Claude Code reviews every build PR (A41, seats amended by A78); humans merge.

## Verification and CI

- **factory-verify** with mutation self-tests (A10); **pass^k** acceptance; targeted **PHPUnit**; **Selenium/Chromium** preview evidence.
- **GitHub Actions**, factory-repo hygiene only (R4): thin YAML wrappers over repo scripts so the CI backend is swappable in an afternoon. Executes on a **self-hosted runner on the control-plane VM** (A76): Ansible-provisioned, dedicated `gha-runner` user, ephemeral single-job mode, systemd-hardened and resource-capped, zero access to factory state; GitHub-hosted runners remain the one-line `runs-on` fallback. **GitHub App** bot identity (A45/A62).

## Observability (direction, not yet ruled)

The **ledger is the primary observability system** - cost, latency, and outcome questions are SQL. Planned light additions: `tracing` instrumentation in the daemon, node/postgres exporters, and server-side usage logging - the one ruled slice (A79/R23): page-view rows written by Axum middleware into the ledger, no client-side trackers (Plausible/Umami rejected for the factory). A fleet-level Grafana/Prometheus host may scrape the factory (expose-never-require keeps A68 intact). No Google Analytics - external beacons don't belong on an internal admin surface.

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
