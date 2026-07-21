# Rust dependency vetting

`cargo vet --locked` checks every dependency addition and update against the
policy in this directory. The initial exact-version exemptions were generated
by `cargo vet init`; they record the dependency graph accepted at bootstrap and
are not claims that Patchyard audited those crates. New versions fail closed until an
exemption, local audit, or reviewed third-party audit import is committed.

Keep exemptions exact and reduce them as audits or deliberately selected audit
imports become available. Do not add a third-party audit source solely to make
the gate pass.
