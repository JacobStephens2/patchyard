//! Operator CLI for Patchyard Factory's PostgreSQL state layer.

use std::{
    error::Error,
    io::Read as _,
    path::{Path, PathBuf},
    time::Duration,
};

use clap::{Args, Parser, Subcommand};
use factory_core::{
    RequestBody,
    schema::{introspect, render_mermaid},
    state::{
        FactoryRepository, NewRequest, PostgresRepository, Sha256Digest, TraceId, remove_artifact,
    },
};
use sha2::{Digest as _, Sha256};
use time::OffsetDateTime;
use uuid::Uuid;

#[derive(Debug, Parser)]
#[command(name = "factoryctl", version, about = "Patchyard Factory operator CLI")]
struct Cli {
    /// PostgreSQL URL. Defaults to DATABASE_URL; no password is needed on the peer socket.
    #[arg(long, env = "DATABASE_URL", hide_env_values = true)]
    database_url: String,

    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    /// Operations/test intake through factory-core's single parser.
    Request {
        #[command(subcommand)]
        command: RequestCommand,
    },
    /// Show durable request, event, run, and active-lease state.
    Status(RequestIdArgs),
    /// Claim a request with a fencing token and bounded TTL.
    Claim(ClaimArgs),
    /// Close a request and start its artifact retention clock.
    Close(CloseArgs),
    /// Delete expired artifacts safely beneath the 0700 artifact root.
    RetentionSweep(RetentionSweepArgs),
    /// GitHub reconciliation lands in PLAN Session 10.
    Reconcile(RequestIdArgs),
    /// Apply the embedded, append-only SQLx migrations.
    Migrate,
    /// Render the committed Mermaid ERD from live PostgreSQL catalogs.
    SchemaMermaid(SchemaMermaidArgs),
    /// Emit the full shared introspection catalog as JSON.
    SchemaJson,
}

#[derive(Debug, Subcommand)]
enum RequestCommand {
    /// Create one request; `-` reads the body from standard input.
    New(NewRequestArgs),
}

#[derive(Debug, Args)]
struct NewRequestArgs {
    /// UTF-8 request body file or `-` for stdin.
    #[arg(value_name = "FILE")]
    file: PathBuf,
    /// Bounded origin label recorded in state.
    #[arg(long, default_value = "factoryctl")]
    source: String,
    /// Optional pre-selected request UUID for idempotent automation.
    #[arg(long)]
    id: Option<Uuid>,
    /// Optional pre-selected W3C trace ID for propagated traces.
    #[arg(long)]
    trace_id: Option<String>,
}

#[derive(Debug, Args)]
struct RequestIdArgs {
    request_id: Uuid,
}

#[derive(Debug, Args)]
struct ClaimArgs {
    request_id: Uuid,
    #[arg(long)]
    holder: String,
    #[arg(long, default_value_t = 900, value_parser = clap::value_parser!(u64).range(1..=86_400))]
    ttl_seconds: u64,
}

#[derive(Debug, Args)]
struct CloseArgs {
    request_id: Uuid,
    #[arg(long, default_value_t = 90, value_parser = clap::value_parser!(u64).range(1..))]
    retention_days: u64,
}

#[derive(Debug, Args)]
struct RetentionSweepArgs {
    #[arg(long, default_value = "/var/lib/patchyard/artifacts")]
    root: PathBuf,
    #[arg(long, default_value_t = 1000, value_parser = clap::value_parser!(i64).range(1..=10_000))]
    limit: i64,
}

#[derive(Debug, Args)]
struct SchemaMermaidArgs {
    /// Write directly to this file; omit to print to stdout.
    #[arg(long)]
    output: Option<PathBuf>,
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    let cli = Cli::parse();
    let repository = PostgresRepository::connect(&cli.database_url).await?;

    match cli.command {
        Command::Request {
            command: RequestCommand::New(arguments),
        } => create_request(&repository, arguments).await?,
        Command::Status(arguments) => status(&repository, arguments.request_id).await?,
        Command::Claim(arguments) => claim(&repository, arguments).await?,
        Command::Close(arguments) => close(&repository, arguments).await?,
        Command::RetentionSweep(arguments) => retention_sweep(&repository, arguments).await?,
        Command::Reconcile(arguments) => {
            return Err(format!(
                "reconcile for request {} is intentionally unavailable until PLAN Session 10",
                arguments.request_id
            )
            .into());
        }
        Command::Migrate => {
            sqlx::migrate!("../../migrations")
                .run(repository.pool())
                .await?;
            println!("migrations: current");
        }
        Command::SchemaMermaid(arguments) => {
            let catalog = introspect(repository.pool()).await?;
            let rendered = render_mermaid(&catalog);
            if let Some(output) = arguments.output {
                std::fs::write(output, rendered)?;
            } else {
                print!("{rendered}");
            }
        }
        Command::SchemaJson => {
            let catalog = introspect(repository.pool()).await?;
            println!("{}", serde_json::to_string_pretty(&catalog)?);
        }
    }
    Ok(())
}

async fn create_request(
    repository: &PostgresRepository,
    arguments: NewRequestArgs,
) -> Result<(), Box<dyn Error>> {
    let raw = read_body(&arguments.file)?;
    let body = RequestBody::parse(raw)?;
    let trace_id = match arguments.trace_id {
        Some(value) => TraceId::parse(value)?,
        None => TraceId::random(),
    };

    let mut hasher = Sha256::new();
    hasher.update(arguments.source.as_bytes());
    hasher.update([0]);
    hasher.update(body.as_str().as_bytes());
    let fingerprint = Sha256Digest::new(hasher.finalize().into());
    let request = NewRequest::new(
        arguments.id.unwrap_or_else(Uuid::new_v4),
        fingerprint,
        arguments.source,
        body,
        trace_id,
    )?;
    let created = repository.create_request(&request).await?;
    println!(
        "{} {}",
        created.id,
        if created.inserted {
            "created"
        } else {
            "existing"
        }
    );
    Ok(())
}

async fn status(repository: &PostgresRepository, request_id: Uuid) -> Result<(), Box<dyn Error>> {
    let snapshot = repository.request_status(request_id).await?;
    println!(
        "{}",
        serde_json::to_string_pretty(&serde_json::json!({
            "id": snapshot.id,
            "source": snapshot.source,
            "trace_id": snapshot.trace_id,
            "received_at": snapshot.received_at,
            "status": snapshot.status,
            "closed_at": snapshot.closed_at,
            "run_count": snapshot.run_count,
            "event_count": snapshot.event_count,
            "active_lease_holder": snapshot.active_lease_holder,
            "lease_expires_at": snapshot.lease_expires_at,
        }))?
    );
    Ok(())
}

async fn claim(
    repository: &PostgresRepository,
    arguments: ClaimArgs,
) -> Result<(), Box<dyn Error>> {
    let claim = repository
        .claim_request(
            arguments.request_id,
            &arguments.holder,
            Duration::from_secs(arguments.ttl_seconds),
        )
        .await?;
    println!(
        "request={} holder={} fencing_token={} expires_at={} idempotent_retry={}",
        claim.request_id,
        claim.holder,
        claim.fencing_token,
        claim.expires_at,
        claim.idempotent_retry
    );
    Ok(())
}

async fn close(
    repository: &PostgresRepository,
    arguments: CloseArgs,
) -> Result<(), Box<dyn Error>> {
    let retention_seconds = arguments
        .retention_days
        .checked_mul(86_400)
        .ok_or("retention duration overflow")?;
    let changed = repository
        .close_request(arguments.request_id, Duration::from_secs(retention_seconds))
        .await?;
    println!(
        "request={} {}",
        arguments.request_id,
        if changed { "closed" } else { "already-closed" }
    );
    Ok(())
}

async fn retention_sweep(
    repository: &PostgresRepository,
    arguments: RetentionSweepArgs,
) -> Result<(), Box<dyn Error>> {
    let now = OffsetDateTime::now_utc();
    let artifacts = repository.expired_artifacts(now, arguments.limit).await?;
    let mut removed = 0_u64;
    let mut already_absent = 0_u64;
    for artifact in artifacts {
        if remove_artifact(&arguments.root, &artifact.relative_path)? {
            removed += 1;
        } else {
            already_absent += 1;
        }
        repository.mark_artifact_deleted(artifact.id, now).await?;
    }
    println!("removed={removed} already_absent={already_absent}");
    Ok(())
}

fn read_body(path: &Path) -> Result<String, Box<dyn Error>> {
    if path == Path::new("-") {
        let mut body = String::new();
        std::io::stdin().read_to_string(&mut body)?;
        Ok(body)
    } else {
        Ok(std::fs::read_to_string(path)?)
    }
}
