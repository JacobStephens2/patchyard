# Rust workspace members (session 1)

The five crates land here: `factory-core` (types, the parse-don't-validate intake constructor, shared constants), `factory-supervisor` (the daemon - A67), `factory-verify` (the gates), `factoryctl`, `factory-web` (dashboard). Root `Cargo.toml` arrives with them; toolchain pinned via `rust-toolchain.toml`, `Cargo.lock` committed, `cargo audit`/`cargo deny` in CI (A42).
