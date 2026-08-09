//! Tell Cargo that the embedded migrations are a build input.
//!
//! `sqlx::migrate!("../../migrations")` reads that directory at compile time,
//! but adding a `.sql` file changes no Rust source, so Cargo considers the
//! crate fresh and reuses the previous binary. A converge then ships a
//! factoryctl whose embedded set predates the new migration, `migrate` applies
//! nothing, and the first task that references a new column fails - which is
//! exactly how the multiple-screenshot migration failed to deploy.
//!
//! Emitting rerun-if-changed for the directory makes the dependency explicit.
fn main() {
    println!("cargo:rerun-if-changed=../../migrations");
}
