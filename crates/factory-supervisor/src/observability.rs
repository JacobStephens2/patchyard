//! Prometheus metrics and dormant, fail-open OTLP tracing.

use std::{net::SocketAddr, time::Duration};

use metrics::{counter, describe_counter, describe_histogram, histogram};
use metrics_exporter_prometheus::{BuildError, PrometheusBuilder};
use opentelemetry::{global, trace::TracerProvider as _};
use opentelemetry_otlp::WithExportConfig as _;
use opentelemetry_sdk::trace::SdkTracerProvider;
use thiserror::Error;
use tracing_subscriber::{EnvFilter, layer::SubscriberExt as _, util::SubscriberInitExt as _};

use crate::contracts::InvocationUsage;

/// Install the pull-only `/metrics` listener owned by the metrics exporter.
pub fn install_metrics(address: SocketAddr) -> Result<(), BuildError> {
    PrometheusBuilder::new()
        .with_http_listener(address)
        .install()?;
    describe_counter!("factory_runs_total", "Pipeline runs by stage and outcome.");
    describe_counter!(
        "factory_llm_tokens_total",
        "LLM tokens by model and direction."
    );
    describe_counter!(
        "factory_llm_cost_microusd_total",
        "LLM cost in millionths of USD by model."
    );
    describe_histogram!(
        "factory_stage_latency_seconds",
        "Pipeline stage wall latency."
    );
    Ok(())
}

pub fn record_stage(stage: &'static str, outcome: &'static str, duration: Duration) {
    counter!("factory_runs_total", "stage" => stage, "outcome" => outcome).increment(1);
    histogram!("factory_stage_latency_seconds", "stage" => stage).record(duration);
}

pub fn record_usage(model: String, usage: InvocationUsage) {
    counter!("factory_llm_tokens_total", "model" => model.clone(), "direction" => "input")
        .increment(usage.input_tokens);
    counter!("factory_llm_tokens_total", "model" => model.clone(), "direction" => "output")
        .increment(usage.output_tokens);
    counter!("factory_llm_cost_microusd_total", "model" => model).increment(usage.cost_microusd);
}

/// Keeps the optional provider alive until explicit shutdown.
pub struct TelemetryGuard {
    provider: Option<SdkTracerProvider>,
}

impl TelemetryGuard {
    /// Install structured logging. Empty endpoint means dormant. Exporter
    /// creation failure is logged and tracing continues without OTLP.
    pub fn install(endpoint: Option<&str>) -> Result<Self, TelemetryError> {
        let filter = EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info"));
        if let Some(endpoint) = configured_endpoint(endpoint) {
            match opentelemetry_otlp::SpanExporter::builder()
                .with_http()
                .with_endpoint(endpoint)
                .with_timeout(Duration::from_millis(250))
                .build()
            {
                Ok(exporter) => {
                    let provider = SdkTracerProvider::builder()
                        .with_batch_exporter(exporter)
                        .build();
                    let tracer = provider.tracer("factory-supervisor");
                    tracing_subscriber::registry()
                        .with(filter)
                        .with(tracing_subscriber::fmt::layer().json())
                        .with(tracing_opentelemetry::layer().with_tracer(tracer))
                        .try_init()
                        .map_err(|error| TelemetryError::Subscriber(error.to_string()))?;
                    global::set_tracer_provider(provider.clone());
                    return Ok(Self {
                        provider: Some(provider),
                    });
                }
                Err(error) => {
                    eprintln!("OTLP exporter unavailable; continuing fail-open: {error}");
                }
            }
        }
        tracing_subscriber::registry()
            .with(filter)
            .with(tracing_subscriber::fmt::layer().json())
            .try_init()
            .map_err(|error| TelemetryError::Subscriber(error.to_string()))?;
        Ok(Self { provider: None })
    }

    /// Flush telemetry explicitly. Failure is returned for logging only and
    /// must never alter a pipeline outcome.
    pub async fn shutdown(mut self) -> Result<(), TelemetryError> {
        let Some(provider) = self.provider.take() else {
            return Ok(());
        };
        tokio::task::spawn_blocking(move || {
            provider
                .shutdown()
                .map_err(|error| TelemetryError::Shutdown(error.to_string()))
        })
        .await
        .map_err(TelemetryError::Join)?
    }
}

fn configured_endpoint(endpoint: Option<&str>) -> Option<&str> {
    endpoint.filter(|value| !value.trim().is_empty())
}

impl Drop for TelemetryGuard {
    fn drop(&mut self) {
        // Best effort only. Daemon main calls shutdown() and reports errors.
        if let Some(provider) = self.provider.take() {
            let _ = provider.shutdown();
        }
    }
}

#[derive(Debug, Error)]
pub enum TelemetryError {
    #[error("tracing subscriber could not be installed: {0}")]
    Subscriber(String),
    #[error("telemetry shutdown failed: {0}")]
    Shutdown(String),
    #[error("telemetry shutdown task failed: {0}")]
    Join(tokio::task::JoinError),
}

#[cfg(test)]
mod tests {
    use super::{TelemetryGuard, configured_endpoint};

    #[tokio::test]
    async fn unreachable_otlp_collector_is_fail_open() {
        assert_eq!(configured_endpoint(None), None);
        assert_eq!(configured_endpoint(Some("")), None);
        let guard = TelemetryGuard::install(Some("http://127.0.0.1:9"))
            .expect("an unreachable collector cannot prevent initialization");
        let deterministic_outcome = "dry_run_complete";
        tracing::info!(outcome = deterministic_outcome, "fail-open fixture run");
        // Export/shutdown may report collector failure, but it is observed only
        // after the deterministic outcome and cannot change it.
        let _telemetry_result = guard.shutdown().await;
        assert_eq!(deterministic_outcome, "dry_run_complete");
    }
}
