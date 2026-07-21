# Rust workspace members

Session 1 establishes `factory-core` (types, the parse-don't-validate intake
constructor, shared constants) and empty compileable shells for
`factory-verify`, `factoryctl`, and `factory-web`. `factory-supervisor` arrives
with the daemon in session 9. The root workspace pins the Rust toolchain and
commits `Cargo.lock`; hosted CI runs format, clippy, test, audit, and deny gates.
