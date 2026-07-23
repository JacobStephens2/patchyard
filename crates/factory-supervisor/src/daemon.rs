//! LISTEN-driven supervisor with startup, reconnect, and timer recovery sweeps.

use std::{collections::BTreeMap, time::Duration};

use sqlx::postgres::PgListener;
use thiserror::Error;
use tokio::task::JoinHandle;
use tokio_util::sync::CancellationToken;
use uuid::Uuid;

use crate::{
    pipeline::{Pipeline, PipelineError, PipelineOutcome},
    store::{ControlKind, DailyLimits, PgPipelineStore, PipelineStore, StoreError},
};

#[derive(Clone, Debug)]
pub struct DaemonConfig {
    pub database_url: String,
    pub holder: String,
    pub sweep_interval: Duration,
    pub lease_ttl: Duration,
    pub limits: DailyLimits,
    pub max_active: usize,
}

struct ActiveRun {
    cancellation: CancellationToken,
    handle: JoinHandle<Result<PipelineOutcome, PipelineError>>,
}

pub struct SupervisorDaemon {
    store: PgPipelineStore,
    pipeline: Pipeline<PgPipelineStore>,
    config: DaemonConfig,
    active: BTreeMap<Uuid, ActiveRun>,
}

impl SupervisorDaemon {
    #[must_use]
    pub fn new(
        store: PgPipelineStore,
        pipeline: Pipeline<PgPipelineStore>,
        config: DaemonConfig,
    ) -> Self {
        Self {
            store,
            pipeline,
            config,
            active: BTreeMap::new(),
        }
    }

    /// Notifications are only wakes. Every wake invokes the same durable-row
    /// sweep, including startup, reconnect, and the recovery timer.
    pub async fn run(mut self, shutdown: &CancellationToken) -> Result<(), DaemonError> {
        if self.config.max_active == 0 || self.config.sweep_interval.is_zero() {
            return Err(DaemonError::InvalidConfig);
        }
        let mut listener = self.connect_listener().await?;
        let mut interval = tokio::time::interval(self.config.sweep_interval);
        interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
        self.sweep().await?;
        loop {
            // Cancellation audit: CancellationToken::cancelled and Interval::tick
            // are cancellation-safe. PgListener::recv is cancel-safe: cancelling
            // loses neither a durable row nor queue position, because payloads
            // are wakes only and every branch performs a row sweep.
            let wake = tokio::select! {
                () = shutdown.cancelled() => Wake::Shutdown,
                _ = interval.tick() => Wake::Sweep,
                notification = listener.recv() => match notification {
                    Ok(_) => Wake::Sweep,
                    Err(error) => Wake::Reconnect(error),
                },
            };
            match wake {
                Wake::Shutdown => break,
                Wake::Sweep => self.sweep().await?,
                Wake::Reconnect(error) => {
                    tracing::warn!(%error, "LISTEN connection lost; reconnecting before durable sweep");
                    listener = self.connect_listener().await?;
                    self.sweep().await?;
                }
            }
        }
        self.shutdown_active().await?;
        Ok(())
    }

    async fn connect_listener(&self) -> Result<PgListener, DaemonError> {
        let mut listener = PgListener::connect(&self.config.database_url).await?;
        listener.listen("factory_intake").await?;
        listener.listen("factory_control").await?;
        Ok(listener)
    }

    async fn sweep(&mut self) -> Result<(), DaemonError> {
        self.execute_controls().await?;
        self.reap_finished().await?;
        while self.active.len() < self.config.max_active {
            let Some(claim) = self
                .store
                .claim_next(
                    &self.config.holder,
                    self.config.lease_ttl,
                    self.config.limits,
                )
                .await?
            else {
                break;
            };
            if self.active.contains_key(&claim.request_id) {
                break;
            }
            let request_id = claim.request_id;
            let cancellation = CancellationToken::new();
            let task_token = cancellation.clone();
            let pipeline = self.pipeline.clone();
            let handle = tokio::spawn(async move { pipeline.run_claim(claim, &task_token).await });
            self.active.insert(
                request_id,
                ActiveRun {
                    cancellation,
                    handle,
                },
            );
        }
        Ok(())
    }

    async fn execute_controls(&mut self) -> Result<(), DaemonError> {
        for control in self.store.pending_controls(100).await? {
            if !self.store.claim_control(control.id).await? {
                continue;
            }
            let result = match control.command {
                ControlKind::Pause => self
                    .store
                    .set_claiming_state(true, false, &control.requested_by)
                    .await
                    .map(|()| serde_json::json!({"paused": true})),
                ControlKind::Resume => self
                    .store
                    .set_claiming_state(false, false, &control.requested_by)
                    .await
                    .map(|()| serde_json::json!({"paused": false, "full_stop": false})),
                ControlKind::Kill => {
                    let run_id = control
                        .target_run_id
                        .ok_or(StoreError::InvalidControlTarget)?;
                    self.execute_kill(run_id, control.id, &control.reason).await
                }
                ControlKind::FullStop => self.execute_full_stop(control.id, &control).await,
            };
            match result {
                Ok(outcome) => {
                    self.store
                        .complete_control(control.id, true, outcome)
                        .await?
                }
                Err(error) => {
                    self.store
                        .complete_control(
                            control.id,
                            false,
                            serde_json::json!({"error": error.to_string()}),
                        )
                        .await?;
                }
            }
        }
        Ok(())
    }

    async fn execute_kill(
        &mut self,
        run_id: Uuid,
        control_id: Uuid,
        reason: &str,
    ) -> Result<serde_json::Value, StoreError> {
        let request_id = self.store.request_for_run(run_id).await?;
        if let Some(request_id) = request_id
            && let Some(active) = self.active.remove(&request_id)
        {
            active.cancellation.cancel();
            let _pipeline_result = active.handle.await;
        }
        self.pipeline
            .kill_cleanup(run_id)
            .await
            .map_err(|_| StoreError::KillCleanupFailed(run_id))?;
        let request_id = self.store.kill_run(run_id, control_id, reason).await?;
        Ok(serde_json::json!({
            "run_id": run_id,
            "request_id": request_id,
            "worker_teardown": "complete",
            "lease_release": "complete",
            "terminal_event": "run.killed",
        }))
    }

    async fn execute_full_stop(
        &mut self,
        control_id: Uuid,
        control: &crate::store::ControlRow,
    ) -> Result<serde_json::Value, StoreError> {
        self.store
            .set_claiming_state(true, true, &control.requested_by)
            .await?;
        let request_ids: Vec<Uuid> = self.active.keys().copied().collect();
        for request_id in request_ids {
            if let Some(active) = self.active.remove(&request_id) {
                active.cancellation.cancel();
                let _pipeline_result = active.handle.await;
            }
            if let Some(run) = self.store.existing_run(request_id).await? {
                self.pipeline
                    .kill_cleanup(run.id)
                    .await
                    .map_err(|_| StoreError::KillCleanupFailed(run.id))?;
                self.store
                    .kill_run(run.id, control_id, &control.reason)
                    .await?;
            }
        }
        Ok(serde_json::json!({"full_stop": true, "active_workers": 0}))
    }

    async fn reap_finished(&mut self) -> Result<(), DaemonError> {
        let finished: Vec<Uuid> = self
            .active
            .iter()
            .filter_map(|(request_id, active)| active.handle.is_finished().then_some(*request_id))
            .collect();
        for request_id in finished {
            let active = self
                .active
                .remove(&request_id)
                .expect("selected active run exists");
            match active.handle.await? {
                Ok(outcome) => tracing::info!(%request_id, ?outcome, "pipeline completed"),
                Err(error) => {
                    tracing::error!(%request_id, %error, "pipeline attempt stopped; durable sweep will recover")
                }
            }
        }
        Ok(())
    }

    async fn shutdown_active(&mut self) -> Result<(), DaemonError> {
        let active = std::mem::take(&mut self.active);
        for run in active.values() {
            run.cancellation.cancel();
        }
        for (_, run) in active {
            let _pipeline_result = run.handle.await?;
        }
        Ok(())
    }
}

enum Wake {
    Sweep,
    Reconnect(sqlx::Error),
    Shutdown,
}

#[derive(Debug, Error)]
pub enum DaemonError {
    #[error("daemon configuration is invalid")]
    InvalidConfig,
    #[error("PostgreSQL LISTEN failed: {0}")]
    Database(#[from] sqlx::Error),
    #[error("durable supervisor state failed: {0}")]
    Store(#[from] StoreError),
    #[error("pipeline task failed to join: {0}")]
    Join(#[from] tokio::task::JoinError),
}
