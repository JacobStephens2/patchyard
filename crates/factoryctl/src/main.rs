//! Operator CLI for Patchyard Factory's PostgreSQL state layer.

use std::{
    error::Error,
    io::Read as _,
    path::{Path, PathBuf},
    time::Duration,
};

use clap::{Args, Parser, Subcommand, ValueEnum};
use factory_core::{
    auth::{AccountRole, PASSWORD_MAX_BYTES, hash_password, normalize_username},
    plan::{PlanAction, PlanDecision},
    schema::{introspect, render_mermaid},
    state::{FactoryRepository, NewRequest, PostgresRepository, TraceId, remove_artifact},
    triage::{Lane, Rubric, TaskSpec, TriageOutput},
};
use factory_supervisor::{
    bootstrap, lessons,
    observability::TelemetryGuard,
    store::{ControlKind, PgPipelineStore, PipelineStore},
};
use serde::Deserialize;
use time::OffsetDateTime;
use uuid::Uuid;

#[derive(Debug, Parser)]
#[command(name = "factoryctl", version, about = "Patchyard Factory operator CLI")]
struct Cli {
    /// PostgreSQL URL. Defaults to DATABASE_URL; no password is needed on the peer socket.
    #[arg(long, env = "DATABASE_URL", hide_env_values = true)]
    database_url: Option<String>,

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
    /// Delete expired artifacts safely beneath the dashboard-readable artifact root.
    RetentionSweep(RetentionSweepArgs),
    /// Reconcile one factory PR against GitHub and the deployed-version source.
    Reconcile(RequestIdArgs),
    /// Apply the embedded, append-only SQLx migrations.
    Migrate,
    /// Render the committed Mermaid ERD from live PostgreSQL catalogs.
    SchemaMermaid(SchemaMermaidArgs),
    /// Emit the full shared introspection catalog as JSON.
    SchemaJson,
    /// Provider-free replay of recorded typed triage outputs.
    TriageReplay(TriageReplayArgs),
    /// Emit deterministic production-only outcome facts as schema-valid JSON.
    LessonsReport,
    /// Run one scheduled improvement-proposer attempt in the foreground.
    ProposerRun,
    /// Run one request in the foreground through the daemon's exact pipeline.
    Run(RunArgs),
    /// Queue a durable pause control row.
    Pause(ControlReasonArgs),
    /// Queue a durable resume control row.
    Resume(ControlReasonArgs),
    /// Queue a durable kill for one run.
    Kill(KillArgs),
    /// Queue a durable full-stop control row.
    FullStop(ControlReasonArgs),
    /// Provision, disable, enable, or reset factory-native dashboard accounts.
    Account {
        #[command(subcommand)]
        command: AccountCommand,
    },
    /// Apply one human plan-bin decision.
    Plan {
        #[command(subcommand)]
        command: PlanCommand,
    },
}

#[derive(Debug, Subcommand)]
enum RequestCommand {
    /// Create one request; `-` reads the body from standard input.
    New(NewRequestArgs),
}

#[derive(Debug, Subcommand)]
enum AccountCommand {
    /// Idempotently provision one account; reads the initial password from stdin.
    Provision(AccountProvisionArgs),
    /// Disable an account and revoke all of its sessions.
    Disable(AccountIdentityArgs),
    /// Re-enable a disabled account without changing its password.
    Enable(AccountIdentityArgs),
    /// Replace an account password and revoke all existing sessions.
    ResetPassword(AccountIdentityArgs),
}

#[derive(Clone, Copy, Debug, ValueEnum)]
enum AccountRoleArgument {
    FactorySubmit,
    FactoryAdmin,
}

impl From<AccountRoleArgument> for AccountRole {
    fn from(value: AccountRoleArgument) -> Self {
        match value {
            AccountRoleArgument::FactorySubmit => Self::Submitter,
            AccountRoleArgument::FactoryAdmin => Self::Admin,
        }
    }
}

#[derive(Debug, Args)]
struct AccountProvisionArgs {
    #[arg(long)]
    username: String,
    #[arg(long)]
    display_name: String,
    #[arg(long, value_enum)]
    role: AccountRoleArgument,
}

#[derive(Debug, Args)]
struct AccountIdentityArgs {
    #[arg(long)]
    username: String,
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
struct RunArgs {
    request_id: Uuid,
    /// Root-owned Session 14 qualification only: claim its queued dashboard
    /// request while normal claiming is paused, with a durable audit marker.
    #[arg(long, hide = true)]
    session14_qualification: bool,
}

#[derive(Debug, Args)]
struct ControlReasonArgs {
    #[arg(long, default_value = "factoryctl")]
    actor: String,
    #[arg(long, default_value = "operator request")]
    reason: String,
}

#[derive(Debug, Args)]
struct KillArgs {
    run_id: Uuid,
    #[command(flatten)]
    control: ControlReasonArgs,
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

#[derive(Debug, Args)]
struct TriageReplayArgs {
    #[arg(long, default_value = "fixtures/triage/replay-manifest.json")]
    manifest: PathBuf,
}

#[derive(Debug, Subcommand)]
enum PlanCommand {
    /// Approve B with a TaskSpec carrying an approved-plan Guide and human budget.
    ApproveB(ApproveBArgs),
    /// Answer D; the answer remains labeled untrusted data on re-triage.
    AnswerD(PlanTextArgs),
    /// Mark a C runbook executed and close the request.
    MarkCExecuted(ExecutedCArgs),
    /// Reject or abandon any B/C/D plan and record the reason.
    Reject(PlanTextArgs),
}

#[derive(Debug, Args)]
struct PlanIdentityArgs {
    request_id: Uuid,
    plan_id: Uuid,
    #[arg(long)]
    decision_id: Option<Uuid>,
}

#[derive(Debug, Args)]
struct ApproveBArgs {
    #[command(flatten)]
    identity: PlanIdentityArgs,
    /// Schema-valid TaskSpec JSON, not a free-text plan.
    #[arg(long)]
    task_spec: PathBuf,
}

#[derive(Debug, Args)]
struct PlanTextArgs {
    #[command(flatten)]
    identity: PlanIdentityArgs,
    /// UTF-8 answer/reason file or `-` for stdin.
    #[arg(value_name = "FILE")]
    file: PathBuf,
}

#[derive(Debug, Args)]
struct ExecutedCArgs {
    #[command(flatten)]
    identity: PlanIdentityArgs,
    #[arg(long)]
    runbook_reference: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ReplayManifest {
    rubric: PathBuf,
    cases: Vec<ReplayCase>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ReplayCase {
    id: String,
    request: PathBuf,
    output: PathBuf,
    expected_lane: Lane,
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    let cli = Cli::parse();
    if let Command::TriageReplay(arguments) = &cli.command {
        triage_replay(arguments)?;
        return Ok(());
    }
    let database_url = cli
        .database_url
        .as_deref()
        .ok_or("DATABASE_URL or --database-url is required for state commands")?;
    match &cli.command {
        Command::LessonsReport => {
            let store = PgPipelineStore::connect(database_url).await?;
            let rendered = async {
                let report = lessons::generate(store.pool()).await?;
                report.to_pretty_json()
            }
            .await;
            store.close().await;
            print!("{}", rendered?);
            return Ok(());
        }
        Command::ProposerRun => {
            proposer_run(database_url.to_owned()).await?;
            return Ok(());
        }
        Command::Run(arguments) => {
            foreground_run(
                database_url.to_owned(),
                arguments.request_id,
                arguments.session14_qualification,
            )
            .await?;
            return Ok(());
        }
        Command::Reconcile(arguments) => {
            reconcile(database_url.to_owned(), arguments.request_id).await?;
            return Ok(());
        }
        Command::Pause(arguments) => {
            enqueue_control(database_url, ControlKind::Pause, None, arguments).await?;
            return Ok(());
        }
        Command::Resume(arguments) => {
            enqueue_control(database_url, ControlKind::Resume, None, arguments).await?;
            return Ok(());
        }
        Command::Kill(arguments) => {
            enqueue_control(
                database_url,
                ControlKind::Kill,
                Some(arguments.run_id),
                &arguments.control,
            )
            .await?;
            return Ok(());
        }
        Command::FullStop(arguments) => {
            enqueue_control(database_url, ControlKind::FullStop, None, arguments).await?;
            return Ok(());
        }
        _ => {}
    }
    let repository = PostgresRepository::connect(database_url).await?;

    match cli.command {
        Command::Request {
            command: RequestCommand::New(arguments),
        } => create_request(&repository, arguments).await?,
        Command::Status(arguments) => status(&repository, arguments.request_id).await?,
        Command::Claim(arguments) => claim(&repository, arguments).await?,
        Command::Close(arguments) => close(&repository, arguments).await?,
        Command::RetentionSweep(arguments) => retention_sweep(&repository, arguments).await?,
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
        Command::TriageReplay(_) => unreachable!("handled before database connection"),
        Command::Account { command } => account(repository.pool(), command).await?,
        Command::Plan { command } => plan(&repository, command).await?,
        Command::Run(_)
        | Command::Reconcile(_)
        | Command::Pause(_)
        | Command::Resume(_)
        | Command::Kill(_)
        | Command::FullStop(_) => unreachable!("handled before core repository connection"),
        Command::LessonsReport => unreachable!("handled before core repository connection"),
        Command::ProposerRun => unreachable!("handled before core repository connection"),
    }
    Ok(())
}

async fn proposer_run(database_url: String) -> Result<(), Box<dyn Error>> {
    let runtime = bootstrap::from_environment(database_url).await?;
    let cancellation = tokio_util::sync::CancellationToken::new();
    let signal_token = cancellation.clone();
    let signal = tokio::spawn(async move {
        let _ = tokio::signal::ctrl_c().await;
        signal_token.cancel();
    });
    let result = runtime
        .proposer
        .run_from_ledger(runtime.store.pool(), &cancellation)
        .await;
    signal.abort();
    let _signal_result = signal.await;
    runtime.close().await;
    match result? {
        factory_supervisor::proposer::ProposerOutcome::FullStopActive => {
            println!("{}", serde_json::json!({"state": "full_stop_active"}));
        }
        factory_supervisor::proposer::ProposerOutcome::IdeaAppended { run_id } => {
            println!(
                "{}",
                serde_json::json!({"state": "idea_appended", "run_id": run_id})
            );
        }
        factory_supervisor::proposer::ProposerOutcome::ReadyForReview {
            run_id,
            pull_request,
        } => {
            println!(
                "{}",
                serde_json::json!({
                    "state": "ready_for_review",
                    "run_id": run_id,
                    "pull_request": {
                        "number": pull_request.number,
                        "url": pull_request.url,
                        "branch": pull_request.branch,
                        "head_sha": pull_request.head_sha,
                        "author_login": pull_request.author_login,
                    }
                })
            );
        }
        factory_supervisor::proposer::ProposerOutcome::OpenPrCapReached { run_id } => {
            println!(
                "{}",
                serde_json::json!({"state": "open_pr_cap_reached", "run_id": run_id})
            );
        }
        factory_supervisor::proposer::ProposerOutcome::Killed { run_id } => {
            println!(
                "{}",
                serde_json::json!({"state": "killed", "run_id": run_id})
            );
        }
    }
    Ok(())
}

async fn reconcile(database_url: String, request_id: Uuid) -> Result<(), Box<dyn Error>> {
    let runtime = bootstrap::reconciler_from_environment(database_url).await?;
    let cancellation = tokio_util::sync::CancellationToken::new();
    let signal_token = cancellation.clone();
    let signal = tokio::spawn(async move {
        let _ = tokio::signal::ctrl_c().await;
        signal_token.cancel();
    });
    let result = runtime
        .reconciler
        .reconcile(request_id, &cancellation)
        .await;
    signal.abort();
    let _signal_result = signal.await;
    runtime.close().await;
    match result {
        Ok(outcome) => println!("{}", serde_json::to_string_pretty(&outcome)?),
        Err(error) => return Err(error.into()),
    }
    Ok(())
}

async fn foreground_run(
    database_url: String,
    request_id: Uuid,
    session14_qualification: bool,
) -> Result<(), Box<dyn Error>> {
    // Foreground qualification uses the daemon's exact lifecycle, including
    // its control-plane log-scan sentinel.  It must therefore install the
    // same structured journal subscriber as the resident supervisor.
    let endpoint = std::env::var("OTEL_EXPORTER_OTLP_ENDPOINT").ok();
    let telemetry = TelemetryGuard::install(endpoint.as_deref())?;
    let runtime = bootstrap::from_environment(database_url).await?;
    let claim = if session14_qualification {
        runtime
            .store
            .claim_session14_qualification(
                request_id,
                &runtime.daemon.holder,
                runtime.daemon.lease_ttl,
                runtime.daemon.limits,
            )
            .await?
    } else {
        runtime
            .store
            .claim_specific(
                request_id,
                &runtime.daemon.holder,
                runtime.daemon.lease_ttl,
                runtime.daemon.limits,
            )
            .await?
    };
    let cancellation = tokio_util::sync::CancellationToken::new();
    let signal_token = cancellation.clone();
    let signal = tokio::spawn(async move {
        let _ = tokio::signal::ctrl_c().await;
        signal_token.cancel();
    });
    let result = runtime.pipeline.run_claim(claim, &cancellation).await;
    signal.abort();
    let _signal_result = signal.await;
    runtime.close().await;
    if let Err(error) = telemetry.shutdown().await {
        eprintln!("foreground telemetry shutdown failed open: {error}");
    }
    match result {
        Ok(outcome) => println!("{}", serde_json::to_string_pretty(&outcome)?),
        Err(error) => return Err(error.into()),
    }
    Ok(())
}

async fn enqueue_control(
    database_url: &str,
    command: ControlKind,
    target: Option<Uuid>,
    arguments: &ControlReasonArgs,
) -> Result<(), Box<dyn Error>> {
    let store = PgPipelineStore::connect(database_url).await?;
    let id = store
        .enqueue_control(command, target, &arguments.actor, &arguments.reason)
        .await?;
    println!("control {id} queued: {}", command.as_str());
    store.close().await;
    Ok(())
}

fn triage_replay(arguments: &TriageReplayArgs) -> Result<(), Box<dyn Error>> {
    let manifest: ReplayManifest =
        serde_json::from_str(&std::fs::read_to_string(&arguments.manifest)?)?;
    let rubric = Rubric::parse_markdown(&std::fs::read_to_string(&manifest.rubric)?)?;
    let mut passed = 0_usize;
    for case in manifest.cases {
        if !case.request.is_file() {
            return Err(format!(
                "fixture {} request is missing: {}",
                case.id,
                case.request.display()
            )
            .into());
        }
        let output = TriageOutput::parse_json(&std::fs::read_to_string(&case.output)?)?;
        let classification = rubric.classify(&output.task_spec)?;
        if classification.lane != case.expected_lane {
            return Err(format!(
                "fixture {} expected lane {}, got {} ({:?})",
                case.id, case.expected_lane, classification.lane, classification.reasons
            )
            .into());
        }
        println!("{} lane={} pass", case.id, classification.lane);
        passed += 1;
    }
    println!("triage replay: {passed} fixtures passed");
    Ok(())
}

async fn plan(repository: &PostgresRepository, command: PlanCommand) -> Result<(), Box<dyn Error>> {
    let (identity, action) = match command {
        PlanCommand::ApproveB(arguments) => {
            let task_spec = TaskSpec::parse_json(&std::fs::read_to_string(&arguments.task_spec)?)?;
            (arguments.identity, PlanAction::ApproveB { task_spec })
        }
        PlanCommand::AnswerD(arguments) => {
            let answer = read_body(&arguments.file)?;
            (arguments.identity, PlanAction::AnswerD { answer })
        }
        PlanCommand::MarkCExecuted(arguments) => (
            arguments.identity,
            PlanAction::MarkCExecuted {
                runbook_reference: arguments.runbook_reference,
            },
        ),
        PlanCommand::Reject(arguments) => {
            let reason = read_body(&arguments.file)?;
            (arguments.identity, PlanAction::Reject { reason })
        }
    };
    let decision = PlanDecision {
        id: identity.decision_id.unwrap_or_else(Uuid::new_v4),
        action,
    };
    let recorded = repository
        .transition_plan(identity.request_id, identity.plan_id, &decision)
        .await?;
    println!(
        "{}",
        serde_json::to_string_pretty(&serde_json::json!({
            "request_id": identity.request_id,
            "plan_id": identity.plan_id,
            "decision_id": decision.id,
            "inserted": recorded.inserted,
            "transition": recorded.transition,
        }))?
    );
    Ok(())
}

async fn create_request(
    repository: &PostgresRepository,
    arguments: NewRequestArgs,
) -> Result<(), Box<dyn Error>> {
    let raw = read_body(&arguments.file)?;
    let trace_id = match arguments.trace_id {
        Some(value) => TraceId::parse(value)?,
        None => TraceId::random(),
    };
    let request = NewRequest::from_intake(
        arguments.id.unwrap_or_else(Uuid::new_v4),
        arguments.source,
        raw,
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

async fn account(pool: &sqlx::PgPool, command: AccountCommand) -> Result<(), Box<dyn Error>> {
    match command {
        AccountCommand::Provision(arguments) => {
            let username = normalize_username(&arguments.username)?;
            validate_display_name(&arguments.display_name)?;
            let password = read_password_stdin()?;
            let password_hash =
                tokio::task::spawn_blocking(move || hash_password(&password)).await??;
            let id = Uuid::new_v4();
            let mut transaction = pool.begin().await?;
            let (account_id, changed): (Uuid, bool) = sqlx::query_as(
                r#"
                WITH changed AS (
                    INSERT INTO factory.users (
                        id, username, display_name, password_hash, role
                    ) VALUES ($1, $2, $3, $4, $5::factory.account_role)
                    ON CONFLICT (username) DO UPDATE SET
                        display_name = EXCLUDED.display_name,
                        role = EXCLUDED.role,
                        updated_at = clock_timestamp()
                    WHERE factory.users.display_name IS DISTINCT FROM EXCLUDED.display_name
                       OR factory.users.role IS DISTINCT FROM EXCLUDED.role
                    RETURNING id
                )
                SELECT id, true AS changed FROM changed
                UNION ALL
                SELECT id, false AS changed FROM factory.users
                WHERE username=$2 AND NOT EXISTS (SELECT 1 FROM changed)
                LIMIT 1
                "#,
            )
            .bind(id)
            .bind(&username)
            .bind(&arguments.display_name)
            .bind(password_hash)
            .bind(AccountRole::from(arguments.role).as_str())
            .fetch_one(&mut *transaction)
            .await?;
            if changed {
                sqlx::query(
                    "INSERT INTO factory.audit_events (user_id,action,subject,client_key) VALUES ($1,'account.provisioned',$2,'factoryctl')",
                )
                .bind(account_id)
                .bind(&username)
                .execute(&mut *transaction)
                .await?;
            }
            transaction.commit().await?;
            println!(
                "account {username} {} as {account_id}",
                if changed { "provisioned" } else { "unchanged" }
            );
        }
        AccountCommand::Disable(arguments) => {
            set_account_enabled(pool, &arguments.username, false).await?;
        }
        AccountCommand::Enable(arguments) => {
            set_account_enabled(pool, &arguments.username, true).await?;
        }
        AccountCommand::ResetPassword(arguments) => {
            let username = normalize_username(&arguments.username)?;
            let password = read_password_stdin()?;
            let password_hash =
                tokio::task::spawn_blocking(move || hash_password(&password)).await??;
            let mut transaction = pool.begin().await?;
            let account_id: Option<Uuid> = sqlx::query_scalar(
                r#"
                UPDATE factory.users SET
                    password_hash=$2,
                    password_reset_required=false,
                    password_reset_at=clock_timestamp(),
                    session_version=session_version+1,
                    updated_at=clock_timestamp()
                WHERE username=$1
                RETURNING id
                "#,
            )
            .bind(&username)
            .bind(password_hash)
            .fetch_optional(&mut *transaction)
            .await?;
            let account_id = account_id.ok_or("dashboard account does not exist")?;
            revoke_account_sessions(&mut transaction, account_id).await?;
            append_account_audit(
                &mut transaction,
                account_id,
                "account.password_reset",
                &username,
            )
            .await?;
            transaction.commit().await?;
            println!("account {username} password reset; sessions revoked");
        }
    }
    Ok(())
}

async fn set_account_enabled(
    pool: &sqlx::PgPool,
    raw_username: &str,
    enabled: bool,
) -> Result<(), Box<dyn Error>> {
    let username = normalize_username(raw_username)?;
    let mut transaction = pool.begin().await?;
    let account_id: Option<Uuid> = sqlx::query_scalar(
        r#"
        UPDATE factory.users SET
            enabled=$2,
            disabled_at=CASE WHEN $2 THEN NULL ELSE clock_timestamp() END,
            session_version=session_version + CASE WHEN $2 THEN 0 ELSE 1 END,
            updated_at=clock_timestamp()
        WHERE username=$1
        RETURNING id
        "#,
    )
    .bind(&username)
    .bind(enabled)
    .fetch_optional(&mut *transaction)
    .await?;
    let account_id = account_id.ok_or("dashboard account does not exist")?;
    if !enabled {
        revoke_account_sessions(&mut transaction, account_id).await?;
    }
    let action = if enabled {
        "account.enabled"
    } else {
        "account.disabled"
    };
    append_account_audit(&mut transaction, account_id, action, &username).await?;
    transaction.commit().await?;
    println!(
        "account {username} {}",
        if enabled { "enabled" } else { "disabled" }
    );
    Ok(())
}

async fn revoke_account_sessions(
    transaction: &mut sqlx::Transaction<'_, sqlx::Postgres>,
    account_id: Uuid,
) -> Result<(), sqlx::Error> {
    sqlx::query(
        "UPDATE factory.sessions SET revoked_at=COALESCE(revoked_at,clock_timestamp()) WHERE user_id=$1",
    )
    .bind(account_id)
    .execute(&mut **transaction)
    .await?;
    Ok(())
}

async fn append_account_audit(
    transaction: &mut sqlx::Transaction<'_, sqlx::Postgres>,
    account_id: Uuid,
    action: &str,
    username: &str,
) -> Result<(), sqlx::Error> {
    sqlx::query(
        "INSERT INTO factory.audit_events (user_id,action,subject,client_key) VALUES ($1,$2,$3,'factoryctl')",
    )
    .bind(account_id)
    .bind(action)
    .bind(username)
    .execute(&mut **transaction)
    .await?;
    Ok(())
}

fn validate_display_name(value: &str) -> Result<(), Box<dyn Error>> {
    if value.trim().is_empty() || value.len() > 128 || value.chars().any(char::is_control) {
        return Err("display name must contain 1 to 128 printable bytes".into());
    }
    Ok(())
}

fn read_password_stdin() -> Result<String, Box<dyn Error>> {
    let mut password = String::new();
    std::io::stdin()
        .take(u64::try_from(PASSWORD_MAX_BYTES)? + 3)
        .read_to_string(&mut password)?;
    if password.ends_with('\n') {
        password.pop();
        if password.ends_with('\r') {
            password.pop();
        }
    }
    if password.len() > PASSWORD_MAX_BYTES {
        return Err(format!("password exceeds {PASSWORD_MAX_BYTES} bytes").into());
    }
    Ok(password)
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
