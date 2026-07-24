//! Read-only checkout projections used by `/decisions`, `/bench`, `/model`,
//! and `/codebase`.

use std::{
    collections::BTreeMap,
    path::{Path, PathBuf},
};

use pulldown_cmark::{Event, Options, Parser, Tag, TagEnd, html};
use serde::Deserialize;
use thiserror::Error;

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Bench {
    #[serde(rename = "$schema")]
    pub schema: String,
    pub last_updated: String,
    pub update_note: String,
    pub aa_index_version: String,
    pub aa_snapshot_date: String,
    pub pairs: Vec<BenchPair>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct BenchPair {
    pub model: String,
    pub effort: String,
    pub harness: String,
    pub preferred_harness: bool,
    pub host: String,
    pub floor: BenchDatum,
    pub image_input: BenchDatum,
    pub provenance: String,
    pub standing: String,
    pub visible_tps: String,
    pub long_spec_wall: String,
    pub aa_intelligence: Option<f64>,
    pub aa_cost_per_task_usd: Option<f64>,
    pub aa_coding_index: Option<f64>,
    pub aa_agentic_index: Option<f64>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct BenchDatum {
    pub status: String,
    pub detail: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CodebaseMetrics {
    pub schema_version: u16,
    pub generated_by: String,
    pub tokei_version: String,
    pub roles: Vec<RoleMetrics>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RoleMetrics {
    pub role: String,
    pub description: String,
    pub code: u64,
    pub comments: u64,
    pub blanks: u64,
    pub files: u64,
    pub languages: Vec<LanguageMetrics>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LanguageMetrics {
    pub language: String,
    pub code: u64,
    pub comments: u64,
    pub blanks: u64,
    pub files: u64,
}

#[derive(Clone, Debug, Deserialize)]
pub struct FactoryModel {
    #[serde(rename = "modelVersion")]
    pub model_version: u64,
    pub stages: Vec<ModelStage>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ModelStage {
    pub num: u16,
    pub id: String,
    pub name: String,
    pub summary: String,
    pub actor: String,
    #[serde(default)]
    pub sources: Vec<serde_json::Value>,
    #[serde(default)]
    pub lanes: Vec<String>,
    #[serde(default)]
    pub gate: bool,
}

impl FactoryModel {
    #[must_use]
    pub fn actors(&self) -> BTreeMap<String, String> {
        self.stages
            .iter()
            .map(|stage| (stage.id.clone(), stage.actor.clone()))
            .collect()
    }
}

pub async fn read_bench(root: &Path) -> Result<Bench, ProjectionError> {
    let bytes = tokio::fs::read(root.join("docs/bench.json")).await?;
    Ok(serde_json::from_slice(&bytes)?)
}

pub async fn read_codebase(root: &Path) -> Result<CodebaseMetrics, ProjectionError> {
    let bytes = tokio::fs::read(root.join("docs/codebase-metrics.json")).await?;
    Ok(serde_json::from_slice(&bytes)?)
}

/// Revision of the checkout these projections are read from, for display beside
/// them.
///
/// Provenance only. CI's byte-identical projection check is what guarantees a
/// committed artifact matches its tree, so this never gates a page: an
/// unreadable or unconventional checkout yields `None` and the page renders
/// without a revision rather than failing. Reads git's on-disk refs directly -
/// the dashboard runs no subprocesses (A53) - and resolves the linked-worktree
/// layout so a reviewer worktree reports its own HEAD.
pub async fn read_checkout_revision(root: &Path) -> Option<String> {
    let git = root.join(".git");
    let git_directory = match tokio::fs::symlink_metadata(&git).await {
        Ok(metadata) if metadata.is_dir() => git,
        Ok(metadata) if metadata.is_file() => {
            let pointer = tokio::fs::read_to_string(&git).await.ok()?;
            PathBuf::from(pointer.strip_prefix("gitdir:")?.trim())
        }
        _ => return None,
    };
    // A linked worktree keeps HEAD locally but shares refs with the common directory.
    let common_directory = match tokio::fs::read_to_string(git_directory.join("commondir")).await {
        Ok(value) => git_directory.join(value.trim()),
        Err(_) => git_directory.clone(),
    };
    let head = tokio::fs::read_to_string(git_directory.join("HEAD"))
        .await
        .ok()?;
    let head = head.trim();
    let revision = match head.strip_prefix("ref:") {
        None => head.to_owned(),
        Some(reference) => {
            let reference = reference.trim();
            match tokio::fs::read_to_string(common_directory.join(reference)).await {
                Ok(value) => value.trim().to_owned(),
                Err(_) => packed_revision(&common_directory, reference).await?,
            }
        }
    };
    is_object_id(&revision).then_some(revision)
}

async fn packed_revision(common_directory: &Path, reference: &str) -> Option<String> {
    let packed = tokio::fs::read_to_string(common_directory.join("packed-refs"))
        .await
        .ok()?;
    packed.lines().find_map(|line| {
        let (revision, name) = line.split_once(' ')?;
        (name.trim() == reference && is_object_id(revision)).then(|| revision.to_owned())
    })
}

fn is_object_id(value: &str) -> bool {
    value.len() == 40
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

pub async fn read_model(root: &Path) -> Result<FactoryModel, ProjectionError> {
    let bytes = tokio::fs::read(root.join("model/factory-model.json")).await?;
    Ok(serde_json::from_slice(&bytes)?)
}

/// Render CommonMark with tables while dropping raw HTML and images and
/// allowing only explicitly safe link schemes.
///
/// Governance Markdown is reviewed but still crosses the browser trust
/// boundary. Unsupported links become plain link text and image alt text
/// remains plain text.
#[must_use]
pub fn markdown_without_raw_html(source: &str) -> String {
    let mut options = Options::empty();
    options.insert(Options::ENABLE_TABLES);
    options.insert(Options::ENABLE_STRIKETHROUGH);
    let mut stripped_links = 0_u32;
    let mut stripped_images = 0_u32;
    let events = Parser::new_ext(source, options).filter_map(move |event| match event {
        Event::Html(_) | Event::InlineHtml(_) => None,
        Event::Start(Tag::Link { ref dest_url, .. }) if !safe_link_destination(dest_url) => {
            stripped_links = stripped_links.saturating_add(1);
            None
        }
        Event::End(TagEnd::Link) if stripped_links > 0 => {
            stripped_links -= 1;
            None
        }
        Event::Start(Tag::Image { .. }) => {
            stripped_images = stripped_images.saturating_add(1);
            None
        }
        Event::End(TagEnd::Image) if stripped_images > 0 => {
            stripped_images -= 1;
            None
        }
        other => Some(other),
    });
    let mut output = String::new();
    html::push_html(&mut output, events);
    output
}

fn safe_link_destination(destination: &str) -> bool {
    if destination.trim() != destination || destination.chars().any(char::is_control) {
        return false;
    }
    let Some((scheme, remainder)) = destination.split_once(':') else {
        return false;
    };
    !remainder.is_empty()
        && matches!(
            scheme.to_ascii_lowercase().as_str(),
            "http" | "https" | "mailto"
        )
}

/// Add stable per-ruling anchors after safe Markdown rendering.
#[must_use]
pub fn decision_log_html(source: &str) -> String {
    let mut output = markdown_without_raw_html(source);
    for id in ruling_ids(source) {
        let cell = format!("<td>{id}</td>");
        let anchored = format!("<td id=\"{id}\"><a href=\"#{id}\">{id}</a></td>");
        output = output.replacen(&cell, &anchored, 1);
    }
    output
}

fn ruling_ids(source: &str) -> Vec<String> {
    source
        .lines()
        .filter_map(|line| {
            let candidate = line.split('|').nth(1)?.trim();
            let (prefix, digits) = candidate.as_bytes().split_first()?;
            (matches!(*prefix, b'A' | b'D' | b'R')
                && !digits.is_empty()
                && digits.iter().all(u8::is_ascii_digit))
            .then(|| candidate.to_owned())
        })
        .collect()
}

#[derive(Debug, Error)]
pub enum ProjectionError {
    #[error("checkout projection could not be read: {0}")]
    Io(#[from] std::io::Error),
    #[error("checkout projection JSON is invalid: {0}")]
    Json(#[from] serde_json::Error),
}

#[cfg(test)]
mod tests {
    use super::{decision_log_html, markdown_without_raw_html, read_checkout_revision};

    #[tokio::test]
    async fn checkout_revision_reads_loose_packed_and_worktree_layouts() {
        let root = tempfile::tempdir().expect("tempdir");
        let git = root.path().join(".git");
        let object = "0".repeat(39) + "a";

        // No checkout metadata at all: provenance is absent, never an error.
        assert_eq!(read_checkout_revision(root.path()).await, None);

        // Loose ref.
        std::fs::create_dir_all(git.join("refs/heads")).expect("refs");
        std::fs::write(git.join("HEAD"), "ref: refs/heads/master\n").expect("HEAD");
        std::fs::write(git.join("refs/heads/master"), format!("{object}\n")).expect("ref");
        assert_eq!(
            read_checkout_revision(root.path()).await,
            Some(object.clone())
        );

        // Packed ref: the loose file is gone, the revision still resolves.
        std::fs::remove_file(git.join("refs/heads/master")).expect("unlink");
        std::fs::write(
            git.join("packed-refs"),
            format!("# pack-refs with: peeled\n{object} refs/heads/master\n"),
        )
        .expect("packed-refs");
        assert_eq!(
            read_checkout_revision(root.path()).await,
            Some(object.clone())
        );

        // Detached HEAD.
        std::fs::write(git.join("HEAD"), format!("{object}\n")).expect("detached HEAD");
        assert_eq!(
            read_checkout_revision(root.path()).await,
            Some(object.clone())
        );

        // Linked worktree: `.git` is a file, HEAD is local, refs are shared.
        let linked = tempfile::tempdir().expect("tempdir");
        let worktree_git = git.join("worktrees/review");
        std::fs::create_dir_all(&worktree_git).expect("worktree gitdir");
        std::fs::write(
            linked.path().join(".git"),
            format!("gitdir: {}\n", worktree_git.display()),
        )
        .expect("gitdir pointer");
        std::fs::write(worktree_git.join("commondir"), "../..\n").expect("commondir");
        std::fs::write(worktree_git.join("HEAD"), "ref: refs/heads/master\n").expect("HEAD");
        assert_eq!(read_checkout_revision(linked.path()).await, Some(object));

        // A malformed revision is not reported as provenance.
        std::fs::write(git.join("HEAD"), "not-an-object-id\n").expect("HEAD");
        assert_eq!(read_checkout_revision(root.path()).await, None);
    }

    #[test]
    fn raw_html_is_dropped_and_markdown_tables_still_render() {
        let rendered = markdown_without_raw_html(
            "| name | value |\n| --- | --- |\n| x | <script>alert(1)</script> |\n",
        );
        assert!(rendered.contains("<table>"));
        assert!(rendered.contains("alert(1)"));
        assert!(!rendered.contains("<script>"));
    }

    #[test]
    fn markdown_allows_only_safe_link_schemes_and_strips_images() {
        let rendered = markdown_without_raw_html(
            "[safe](https://example.test) [mail](mailto:factory@example.test) \
             [bad](javascript:alert(1)) ![tracking](data:image/png;base64,AA==)",
        );
        assert!(rendered.contains("href=\"https://example.test\""));
        assert!(rendered.contains("href=\"mailto:factory@example.test\""));
        assert!(rendered.contains("bad"));
        assert!(rendered.contains("tracking"));
        assert!(!rendered.contains("javascript:"));
        assert!(!rendered.contains("data:"));
        assert!(!rendered.contains("<img"));
    }

    #[test]
    fn decision_ids_receive_stable_anchors_only() {
        let rendered =
            decision_log_html("| # | value |\n| -- | -- |\n| A47 | Plan → Implement → Verify |\n");
        assert!(rendered.contains("id=\"A47\""));
        assert!(rendered.contains("href=\"#A47\""));
    }
}
