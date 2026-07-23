use std::{
    error::Error,
    os::unix::fs::{FileTypeExt as _, PermissionsExt as _},
    path::{Path, PathBuf},
};

use clap::Parser;
use factory_web::{AppState, router, store::DashboardStore};
use tokio::net::UnixListener;

#[derive(Debug, Parser)]
#[command(
    name = "factory-web",
    version,
    about = "Server-rendered Patchyard Factory dashboard"
)]
struct Cli {
    #[arg(long, env = "DATABASE_URL", hide_env_values = true)]
    database_url: String,
    #[arg(
        long,
        env = "FACTORY_DASHBOARD_SOCKET",
        default_value = "/run/patchyard-dashboard/dashboard.sock"
    )]
    socket: PathBuf,
    #[arg(long, env = "FACTORY_INSTALL_ROOT", default_value = "/opt/patchyard")]
    checkout_root: PathBuf,
    #[arg(
        long,
        env = "FACTORY_ARTIFACT_ROOT",
        default_value = "/var/lib/patchyard/artifacts"
    )]
    artifact_root: PathBuf,
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    tracing_subscriber::fmt()
        .json()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "factory_web=info".into()),
        )
        .init();
    let cli = Cli::parse();
    prepare_socket(&cli.socket).await?;
    let listener = UnixListener::bind(&cli.socket)?;
    tokio::fs::set_permissions(&cli.socket, std::fs::Permissions::from_mode(0o660)).await?;
    let store = DashboardStore::connect(&cli.database_url).await?;
    let state = AppState::load(store.clone(), cli.checkout_root, cli.artifact_root).await?;
    tracing::info!(socket = %cli.socket.display(), "factory dashboard listening");
    let server = axum::serve(listener, router(state)).with_graceful_shutdown(shutdown_signal());
    let result = server.await;
    store.close().await;
    result?;
    Ok(())
}

async fn prepare_socket(path: &Path) -> Result<(), Box<dyn Error>> {
    let parent = path
        .parent()
        .ok_or("dashboard socket must have a parent directory")?;
    if !parent.is_dir() {
        return Err("dashboard socket parent does not exist".into());
    }
    match tokio::fs::symlink_metadata(path).await {
        Ok(metadata) if metadata.file_type().is_socket() => {
            tokio::fs::remove_file(path).await?;
        }
        Ok(_) => return Err("refusing to replace a non-socket dashboard path".into()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
        Err(error) => return Err(error.into()),
    }
    Ok(())
}

async fn shutdown_signal() {
    if let Err(error) = tokio::signal::ctrl_c().await {
        tracing::error!(%error, "dashboard shutdown signal failed");
    }
}
