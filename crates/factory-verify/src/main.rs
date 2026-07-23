use std::{fs, path::PathBuf};

use clap::{Parser, Subcommand};
use factory_verify::{
    caps::{self, DiffManifest},
    deny_paths,
    ledger::{self, RunRecord},
    postconditions::{self, SortEvidence},
    runtime::{self, RuntimeManifest},
};
use serde::de::DeserializeOwned;
use sqlx::postgres::PgPoolOptions;
use thiserror::Error;

const MAX_INPUT_BYTES: u64 = 1_048_576;

#[derive(Debug, Parser)]
#[command(name = "factory-verify", version, about)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    /// Enforce the constitution's file and changed-line caps.
    Caps {
        #[arg(long)]
        manifest: PathBuf,
        #[arg(long)]
        expected_base_sha: String,
        #[arg(long, default_value_t = caps::DEFAULT_MAX_FILES)]
        max_files: usize,
        #[arg(long, default_value_t = caps::DEFAULT_MAX_LINES)]
        max_lines: u64,
    },
    /// Reject final-diff paths forbidden by the constitution.
    DenyPaths {
        #[arg(long)]
        manifest: PathBuf,
    },
    /// Enforce the sort skill's DOM and query postconditions.
    Postconditions {
        #[arg(long)]
        evidence: PathBuf,
    },
    /// Validate complete provenance and atomically append a queued run.
    LedgerAppend {
        #[arg(long)]
        record: PathBuf,
        #[arg(long, env = "FACTORY_DATABASE_URL", hide_env_values = true)]
        database_url: String,
    },
    /// Run targeted PHPUnit without permitting the verifier to change the tree.
    Runtime {
        #[arg(long)]
        manifest: PathBuf,
        #[arg(long)]
        worktree: PathBuf,
        #[arg(long)]
        patch: PathBuf,
    },
}

#[derive(Debug, Error)]
enum CliError {
    #[error("cannot inspect input {path}: {source}")]
    Metadata {
        path: PathBuf,
        source: std::io::Error,
    },
    #[error("input exceeds {MAX_INPUT_BYTES} bytes: {0}")]
    InputTooLarge(PathBuf),
    #[error("cannot read input {path}: {source}")]
    Read {
        path: PathBuf,
        source: std::io::Error,
    },
    #[error("invalid JSON in {path}: {source}")]
    Json {
        path: PathBuf,
        source: serde_json::Error,
    },
    #[error(transparent)]
    Caps(#[from] caps::CapsError),
    #[error(transparent)]
    DenyPaths(#[from] deny_paths::DenyPathsError),
    #[error(transparent)]
    Postconditions(#[from] postconditions::PostconditionError),
    #[error(transparent)]
    Ledger(#[from] ledger::LedgerError),
    #[error(transparent)]
    Runtime(#[from] runtime::RuntimeError),
    #[error("database connection failed")]
    Database(#[from] sqlx::Error),
}

#[tokio::main]
async fn main() {
    if let Err(error) = run(Cli::parse()).await {
        eprintln!("factory-verify: {error}");
        std::process::exit(1);
    }
}

async fn run(cli: Cli) -> Result<(), CliError> {
    match cli.command {
        Command::Caps {
            manifest,
            expected_base_sha,
            max_files,
            max_lines,
        } => {
            let manifest: DiffManifest = read_json(&manifest)?;
            let summary = caps::verify(&manifest, &expected_base_sha, max_files, max_lines)?;
            println!(
                "caps: pass ({} files, {} changed lines)",
                summary.files, summary.changed_lines
            );
        }
        Command::DenyPaths { manifest } => {
            let manifest: DiffManifest = read_json(&manifest)?;
            deny_paths::verify(&manifest)?;
            println!("deny-paths: pass");
        }
        Command::Postconditions { evidence } => {
            let evidence: SortEvidence = read_json(&evidence)?;
            postconditions::verify(&evidence)?;
            println!("postconditions: pass");
        }
        Command::LedgerAppend {
            record,
            database_url,
        } => {
            let record: RunRecord = read_json(&record)?;
            let record = ledger::validate(record)?;
            let pool = PgPoolOptions::new()
                .max_connections(1)
                .connect(&database_url)
                .await?;
            ledger::append(&pool, &record).await?;
            println!("ledger-append: pass ({})", record.record().id);
        }
        Command::Runtime {
            manifest,
            worktree,
            patch,
        } => {
            let manifest: RuntimeManifest = read_json(&manifest)?;
            let evidence = runtime::verify(&manifest, &worktree, &patch)?;
            println!(
                "{}",
                serde_json::to_string_pretty(&evidence).expect("runtime evidence serializes")
            );
        }
    }
    Ok(())
}

fn read_json<T: DeserializeOwned>(path: &PathBuf) -> Result<T, CliError> {
    let metadata = fs::metadata(path).map_err(|source| CliError::Metadata {
        path: path.clone(),
        source,
    })?;
    if metadata.len() > MAX_INPUT_BYTES {
        return Err(CliError::InputTooLarge(path.clone()));
    }
    let bytes = fs::read(path).map_err(|source| CliError::Read {
        path: path.clone(),
        source,
    })?;
    serde_json::from_slice(&bytes).map_err(|source| CliError::Json {
        path: path.clone(),
        source,
    })
}
