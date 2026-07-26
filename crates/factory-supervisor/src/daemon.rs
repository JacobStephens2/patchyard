//! LISTEN-driven supervisor with startup, reconnect, and timer recovery sweeps.

use std::{collections::BTreeMap, sync::Arc, time::Duration};

use sqlx::postgres::PgListener;
use thiserror::Error;
use tokio::task::JoinHandle;
use tokio_util::sync::CancellationToken;
use uuid::Uuid;

use crate::{
    pipeline::{Pipeline, PipelineError, PipelineOutcome},
    proposer::{ImprovementProposer, ProposerError, ProposerOutcome},
    reconcile::Reconciler,
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
    pub reconcile_abandoned_after: Duration,
    pub reconcile_sweep_limit: usize,
    pub proposer_enabled: bool,
    pub proposer_interval: Duration,
}

struct ActiveRun {
    cancellation: CancellationToken,
    handle: JoinHandle<Result<PipelineOutcome, PipelineError>>,
}

struct ActiveReconcile {
    cancellation: CancellationToken,
    handle: JoinHandle<Result<(), DaemonError>>,
}

struct ActiveProposer {
    cancellation: CancellationToken,
    handle: JoinHandle<Result<ProposerOutcome, ProposerError>>,
}

pub struct SupervisorDaemon {
    store: PgPipelineStore,
    pipeline: Pipeline<PgPipelineStore>,
    reconciler: Reconciler<PgPipelineStore>,
    proposer: Arc<ImprovementProposer>,
    config: DaemonConfig,
    active: BTreeMap<Uuid, ActiveRun>,
    active_reconciles: BTreeMap<Uuid, ActiveReconcile>,
    active_proposer: Option<ActiveProposer>,
}

impl SupervisorDaemon {
    #[must_use]
    pub fn new(
        store: PgPipelineStore,
        pipeline: Pipeline<PgPipelineStore>,
        reconciler: Reconciler<PgPipelineStore>,
        proposer: Arc<ImprovementProposer>,
        config: DaemonConfig,
    ) -> Self {
        Self {
            store,
            pipeline,
            reconciler,
            proposer,
            config,
            active: BTreeMap::new(),
            active_reconciles: BTreeMap::new(),
            active_proposer: None,
        }
    }

    /// Notifications are only wakes. Every wake invokes the same durable-row
    /// sweep, including startup, reconnect, and the recovery timer.
    pub async fn run(mut self, shutdown: &CancellationToken) -> Result<(), DaemonError> {
        if self.config.max_active == 0
            || self.config.sweep_interval.is_zero()
            || self.config.reconcile_abandoned_after.is_zero()
            || self.config.reconcile_sweep_limit == 0
            || self.config.reconcile_sweep_limit > 100
            || self.config.proposer_interval.is_zero()
        {
            return Err(DaemonError::InvalidConfig);
        }
        let mut listener = self.connect_listener().await?;
        let mut interval = tokio::time::interval(self.config.sweep_interval);
        interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
        let mut proposer_interval = tokio::time::interval(self.config.proposer_interval);
        proposer_interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
        // Scheduling begins after one full interval; startup already performs
        // the normal durable-work sweep and should not unexpectedly spend a
        // proposer invocation during every service restart.
        proposer_interval.tick().await;
        self.sweep().await?;
        loop {
            // Cancellation audit: CancellationToken::cancelled and Interval::tick
            // are cancellation-safe. PgListener::recv is cancel-safe: cancelling
            // loses neither a durable row nor queue position, because payloads
            // are wakes only and every branch performs a row sweep.
            let wake = tokio::select! {
                () = shutdown.cancelled() => Wake::Shutdown,
                _ = interval.tick() => Wake::Sweep,
                _ = proposer_interval.tick(), if self.config.proposer_enabled => Wake::Proposer,
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
                Wake::Proposer => self.start_or_reap_proposer().await?,
            }
        }
        self.shutdown_active().await?;
        self.shutdown_reconciles().await?;
        self.shutdown_proposer().await?;
        Ok(())
    }

    async fn connect_listener(&self) -> Result<PgListener, DaemonError> {
        let mut listener = PgListener::connect(&self.config.database_url).await?;
        listener.listen("factory_intake").await?;
        listener.listen("factory_control").await?;
        listener.listen("factory_reconcile").await?;
        Ok(listener)
    }

    async fn sweep(&mut self) -> Result<(), DaemonError> {
        self.execute_controls().await?;
        self.reap_reconciles().await?;
        self.start_reconciles().await?;
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

    async fn start_or_reap_proposer(&mut self) -> Result<(), DaemonError> {
        if let Some(active) = self.active_proposer.take() {
            if active.handle.is_finished() {
                match active.handle.await? {
                    Ok(outcome) => tracing::info!(?outcome, "scheduled proposer completed"),
                    Err(error) => tracing::error!(%error, "scheduled proposer failed closed"),
                }
            } else {
                self.active_proposer = Some(active);
                return Ok(());
            }
        }
        let proposer = self.proposer.clone();
        let pool = self.store.pool().clone();
        let cancellation = CancellationToken::new();
        let task_token = cancellation.clone();
        let handle =
            tokio::spawn(async move { proposer.run_from_ledger(&pool, &task_token).await });
        self.active_proposer = Some(ActiveProposer {
            cancellation,
            handle,
        });
        Ok(())
    }

    async fn start_reconciles(&mut self) -> Result<(), DaemonError> {
        while self.active_reconciles.len() < self.config.reconcile_sweep_limit {
            let Some(request) = self
                .store
                .claim_next_reconcile(self.config.reconcile_abandoned_after)
                .await?
            else {
                break;
            };
            let reconcile_id = request.id;
            let store = self.store.clone();
            let reconciler = self.reconciler.clone();
            let cancellation = CancellationToken::new();
            let task_token = cancellation.clone();
            let handle = tokio::spawn(async move {
                let result = reconciler.reconcile(request.request_id, &task_token).await;
                let (success, outcome) = match result {
                    Ok(outcome) => (true, serde_json::to_value(outcome)?),
                    Err(error) => {
                        tracing::warn!(
                            request_id = %request.request_id,
                            reconcile_id = %request.id,
                            %error,
                            "dashboard reconciliation failed closed"
                        );
                        (false, serde_json::json!({"error": error.to_string()}))
                    }
                };
                store.complete_reconcile(&request, success, outcome).await?;
                Ok(())
            });
            self.active_reconciles.insert(
                reconcile_id,
                ActiveReconcile {
                    cancellation,
                    handle,
                },
            );
        }
        Ok(())
    }

    async fn reap_reconciles(&mut self) -> Result<(), DaemonError> {
        let finished: Vec<Uuid> = self
            .active_reconciles
            .iter()
            .filter_map(|(id, active)| active.handle.is_finished().then_some(*id))
            .collect();
        for reconcile_id in finished {
            let active = self
                .active_reconciles
                .remove(&reconcile_id)
                .expect("selected reconciliation exists");
            match active.handle.await? {
                Ok(()) => tracing::info!(%reconcile_id, "dashboard reconciliation completed"),
                Err(error) => {
                    tracing::error!(%reconcile_id, %error, "dashboard reconciliation task failed")
                }
            }
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
        Ok(kill_outcome(run_id, request_id))
    }

    async fn execute_full_stop(
        &mut self,
        control_id: Uuid,
        control: &crate::store::ControlRow,
    ) -> Result<serde_json::Value, StoreError> {
        self.store
            .set_claiming_state(true, true, &control.requested_by)
            .await?;
        if let Some(active) = self.active_proposer.take() {
            active.cancellation.cancel();
            let _proposer_result = active.handle.await;
        }
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

    async fn shutdown_reconciles(&mut self) -> Result<(), DaemonError> {
        let reconciles = std::mem::take(&mut self.active_reconciles);
        for reconcile in reconciles.values() {
            reconcile.cancellation.cancel();
        }
        for (_, reconcile) in reconciles {
            reconcile.handle.await??;
        }
        Ok(())
    }

    async fn shutdown_proposer(&mut self) -> Result<(), DaemonError> {
        if let Some(active) = self.active_proposer.take() {
            active.cancellation.cancel();
            let _proposer_result = active.handle.await?;
        }
        Ok(())
    }
}

fn kill_outcome(run_id: Uuid, request_id: Option<Uuid>) -> serde_json::Value {
    serde_json::json!({
        "run_id": run_id,
        "request_id": request_id,
        "worker_teardown": "complete",
        "terminal_event": "run.killed",
    })
}

#[cfg(test)]
mod tests {
    use uuid::Uuid;

    use super::kill_outcome;

    #[test]
    fn kill_outcome_claims_only_the_cleanup_it_performed() {
        let outcome = kill_outcome(Uuid::new_v4(), Some(Uuid::new_v4()));

        assert_eq!(outcome["worker_teardown"], "complete");
        assert!(outcome.get("lease_release").is_none());
    }
}

enum Wake {
    Sweep,
    Proposer,
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
    #[error("reconcile outcome serialization failed: {0}")]
    Json(#[from] serde_json::Error),
}
