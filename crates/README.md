# Rust workspace members

Session 2 extends `factory-core` with the PostgreSQL-only domain repository and
the one shared schema-introspection module. `factoryctl` owns the initial
request/status/claim/close/retention/migration/schema commands; `reconcile`
fails explicitly until Session 10. `factory-verify` and `factory-web` remain
compileable shells, and `factory-supervisor` arrives with the daemon in Session
9. The root workspace pins the Rust toolchain and commits `Cargo.lock`; hosted
CI runs format, clippy, test, audit, deny, disposable-PostgreSQL durability, and
generated-ERD drift gates.
