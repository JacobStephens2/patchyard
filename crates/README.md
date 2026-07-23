# Rust workspace members

`factory-core` owns the PostgreSQL-only domain repository, shared schema
introspection, typed TaskSpec/rubric classifier, and plan-bin transition
automaton. `factoryctl` owns request/status/claim/close/retention/migration/
schema commands plus provider-free `triage-replay` and human `plan` decisions;
`reconcile` fails explicitly until Session 10. `factory-verify` and
`factory-web` remain compileable shells, and `factory-supervisor` arrives with
the daemon in Session 9. The root workspace pins the Rust toolchain and commits
`Cargo.lock`; hosted CI runs format, clippy, test, the triage replay, audit,
deny, disposable-PostgreSQL durability, and generated-ERD drift gates.
