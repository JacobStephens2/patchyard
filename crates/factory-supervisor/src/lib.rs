//! Durable, deterministic orchestration for the Patchyard Factory pipeline.
//!
//! Agentic work is confined behind typed subprocess contracts. The supervisor
//! never treats request text, rationale, review prose, or model confidence as
//! authority.

pub mod artifacts;
pub mod automaton;
pub mod bootstrap;
pub mod child;
pub mod config;
pub mod contracts;
pub mod daemon;
pub mod evidence;
pub mod lessons;
pub mod lifecycle;
pub mod observability;
pub mod pipeline;
pub mod preview;
pub mod pricing;
pub mod process;
pub mod proposer;
pub mod publisher;
pub mod reconcile;
pub mod review;
pub mod secret_scan;
pub mod stages;
pub mod store;
pub mod worktree;

pub use config::{RoutingConfig, Seat};
pub use pipeline::{Pipeline, PipelineConfig, PipelineError, RunMode};
