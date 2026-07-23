use std::{error::Error, net::SocketAddr};

use clap::Parser;
use factory_supervisor::{
    bootstrap,
    daemon::SupervisorDaemon,
    observability::{self, TelemetryGuard},
};
use tokio_util::sync::CancellationToken;

#[derive(Debug, Parser)]
#[command(
    name = "factory-supervisor",
    version,
    about = "Patchyard Factory durable pipeline daemon"
)]
struct Cli {
    #[arg(long, env = "DATABASE_URL", hide_env_values = true)]
    database_url: String,
    #[arg(
        long,
        env = "FACTORY_METRICS_ADDRESS",
        default_value = "127.0.0.1:9464"
    )]
    metrics_address: SocketAddr,
    #[arg(long, env = "OTEL_EXPORTER_OTLP_ENDPOINT", hide_env_values = true)]
    otlp_endpoint: Option<String>,
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    let cli = Cli::parse();
    let telemetry = TelemetryGuard::install(cli.otlp_endpoint.as_deref())?;
    observability::install_metrics(cli.metrics_address)?;
    let runtime = bootstrap::from_environment(cli.database_url).await?;
    let shutdown = CancellationToken::new();
    let signal_token = shutdown.clone();
    let signal = tokio::spawn(async move {
        let _ = tokio::signal::ctrl_c().await;
        signal_token.cancel();
    });
    let daemon = SupervisorDaemon::new(
        runtime.store.clone(),
        runtime.pipeline.clone(),
        runtime.daemon.clone(),
    );
    let result = daemon.run(&shutdown).await;
    signal.abort();
    let _signal_result = signal.await;
    runtime.close().await;
    if let Err(error) = telemetry.shutdown().await {
        tracing::warn!(%error, "telemetry shutdown failed open");
    }
    result?;
    Ok(())
}
