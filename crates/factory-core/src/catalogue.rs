//! Call sites for the trusted Target catalogue.
//!
//! The catalogue in `policy/rubric.md` names a path *because of* a page: the
//! Simple Sales Report is catalogued to `common_functions.php` because
//! `get_salespeople_usernames` supplies its selector options. The page that
//! renders those options is a different file, and it never appears in a lane-A
//! change - so the checking seats, whose projection carries only the changed
//! files, cannot answer a question about what the caller renders. That is not
//! a seat failing to reason; it is a fact absent from its evidence.
//!
//! This module holds the human-ruled answer to "which page renders it": the
//! call sites, in `policy/target-catalogue.json`, keyed to the catalogue rows
//! the rubric already rules.
//!
//! # Why the call sites are not a column in the rubric's own table
//!
//! `policy/rubric.md` is the triage seat's prompt, and the catalogue's whole
//! purpose there is that a path may be copied verbatim from it into `targets`.
//! A column of *other* paths sitting beside those would invite exactly the
//! failure AGENTS.md names dominant - editing the wrong thing - so the call
//! sites live in a second file that the triage prompt never carries. The two
//! cannot drift apart in the direction that matters, because
//! [`TargetCatalogue::verify_against_rubric`] refuses a catalogue whose rows
//! are not the rubric's own rows, verbatim and in order, and the supervisor
//! runs that check before it accepts either file.

use serde::{Deserialize, Serialize};
use sha2::{Digest as _, Sha256};
use thiserror::Error;

use crate::triage::TaskTarget;

/// The sole supported catalogue schema.
pub const CATALOGUE_SCHEMA_VERSION: u16 = 1;

/// Heading the rubric's human-ruled catalogue table sits under.
const CATALOGUE_HEADING: &str = "## Target catalogue (trusted)";

/// Bounds. Every one of these refuses rather than truncates: a catalogue past
/// a limit is a policy edit that needs a human, not input to be trimmed.
const MAX_ENTRIES: usize = 64;
const MAX_CALL_SITES_PER_ENTRY: usize = 4;
const MAX_FIELD_CHARS: usize = 1_000;
const MAX_PATH_CHARS: usize = 512;

/// The most call sites one packet may carry, across every target.
///
/// Each one is a whole extra file body in a seat's projection, and the seat's
/// aggregate byte cap is what ultimately pays for it.
pub const MAX_PACKET_CALL_SITES: usize = 8;

#[derive(Debug, Error, Eq, PartialEq)]
pub enum CatalogueError {
    #[error("target catalogue is not valid JSON: {0}")]
    Malformed(String),
    #[error("target catalogue schema_version {0} is unsupported")]
    SchemaVersion(u16),
    #[error("target catalogue is empty")]
    Empty,
    #[error("target catalogue holds more than {MAX_ENTRIES} entries")]
    TooManyEntries,
    #[error("target catalogue entry {page} holds more than {MAX_CALL_SITES_PER_ENTRY} call sites")]
    TooManyCallSites { page: String },
    #[error("target catalogue field is empty or over its length bound: {field}")]
    FieldBounds { field: String },
    #[error("target catalogue path is outside the workspace contract: {path}")]
    PathContract { path: String },
    #[error("target catalogue entry {page} lists its own catalogued path as a call site")]
    SelfCallSite { page: String },
    #[error("target catalogue names {page} more than once")]
    DuplicateEntry { page: String },
    #[error("target catalogue entry {page} names call site {path} more than once")]
    DuplicateCallSite { page: String, path: String },
    #[error("rubric.md has no `{CATALOGUE_HEADING}` table")]
    RubricTableMissing,
    #[error(
        "target catalogue row {index} is not rubric.md's row {index}: \
         catalogue has {catalogue:?}, rubric has {rubric:?}"
    )]
    RubricRowMismatch {
        index: usize,
        catalogue: Box<CatalogueRow>,
        rubric: Box<CatalogueRow>,
    },
    #[error("rubric.md rules {rubric} catalogue rows, the target catalogue holds {catalogue}")]
    RubricRowCount { rubric: usize, catalogue: usize },
    #[error("a task spec selects more than {MAX_PACKET_CALL_SITES} call sites")]
    TooManyPacketCallSites,
}

/// The three fields a catalogue row and a rubric table row share.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct CatalogueRow {
    pub page: String,
    pub path: String,
    pub behavior: String,
}

/// One read-only file a checking seat is given because the catalogue named a
/// path on account of the page this file renders.
///
/// `page` and `why` ride with the path so a seat can tell what the file is
/// doing in its projection. Both are human-ruled policy text, not model
/// output, but the seat still reads the file's *bytes* as untrusted data.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CallSite {
    pub path: String,
    pub page: String,
    pub why: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
struct RawCallSite {
    path: String,
    why: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
struct CatalogueEntry {
    page: String,
    path: String,
    behavior: String,
    call_sites: Vec<RawCallSite>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct CatalogueDocument {
    schema_version: u16,
    entries: Vec<CatalogueEntry>,
}

/// The parsed, bounded, rubric-agreeing call-site catalogue.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TargetCatalogue {
    entries: Vec<CatalogueEntry>,
    source_sha256: [u8; 32],
}

impl TargetCatalogue {
    /// Parse and bound `policy/target-catalogue.json`.
    ///
    /// This proves the file is well-formed policy. It does *not* prove the
    /// rows are the rubric's rows - call [`Self::verify_against_rubric`] for
    /// that, which is what makes the catalogue trusted rather than merely
    /// present.
    ///
    /// # Errors
    ///
    /// Returns a [`CatalogueError`] naming the first bound the document fails.
    pub fn parse_json(json: &str) -> Result<Self, CatalogueError> {
        let document: CatalogueDocument = serde_json::from_str(json)
            .map_err(|error| CatalogueError::Malformed(error.to_string()))?;
        if document.schema_version != CATALOGUE_SCHEMA_VERSION {
            return Err(CatalogueError::SchemaVersion(document.schema_version));
        }
        if document.entries.is_empty() {
            return Err(CatalogueError::Empty);
        }
        if document.entries.len() > MAX_ENTRIES {
            return Err(CatalogueError::TooManyEntries);
        }
        for (index, entry) in document.entries.iter().enumerate() {
            bounded_field(&entry.page, "page", MAX_FIELD_CHARS)?;
            bounded_field(&entry.behavior, "behavior", MAX_FIELD_CHARS)?;
            workspace_relative(&entry.path)?;
            if entry.call_sites.len() > MAX_CALL_SITES_PER_ENTRY {
                return Err(CatalogueError::TooManyCallSites {
                    page: entry.page.clone(),
                });
            }
            if document.entries[..index]
                .iter()
                .any(|earlier| earlier.page == entry.page)
            {
                return Err(CatalogueError::DuplicateEntry {
                    page: entry.page.clone(),
                });
            }
            for (site_index, site) in entry.call_sites.iter().enumerate() {
                bounded_field(&site.why, "why", MAX_FIELD_CHARS)?;
                workspace_relative(&site.path)?;
                if site.path == entry.path {
                    return Err(CatalogueError::SelfCallSite {
                        page: entry.page.clone(),
                    });
                }
                if entry.call_sites[..site_index]
                    .iter()
                    .any(|earlier| earlier.path == site.path)
                {
                    return Err(CatalogueError::DuplicateCallSite {
                        page: entry.page.clone(),
                        path: site.path.clone(),
                    });
                }
            }
        }
        Ok(Self {
            entries: document.entries,
            source_sha256: Sha256::digest(json.as_bytes()).into(),
        })
    }

    /// Refuse unless every catalogue row is a rubric table row, verbatim and
    /// in the rubric's order.
    ///
    /// The rubric is the human-ruled authority; this file only annotates it.
    /// So the annotation may never introduce a page or a path of its own, and
    /// the supervisor refuses to start rather than run on a catalogue that
    /// has drifted from the ruling it claims to annotate.
    ///
    /// # Errors
    ///
    /// Returns [`CatalogueError::RubricTableMissing`] when the markdown holds
    /// no catalogue table, and a row-level error naming the first
    /// disagreement otherwise.
    pub fn verify_against_rubric(&self, markdown: &str) -> Result<(), CatalogueError> {
        let rubric = rubric_rows(markdown)?;
        if rubric.len() != self.entries.len() {
            return Err(CatalogueError::RubricRowCount {
                rubric: rubric.len(),
                catalogue: self.entries.len(),
            });
        }
        for (index, (entry, row)) in self.entries.iter().zip(rubric.iter()).enumerate() {
            let ours = CatalogueRow {
                page: entry.page.clone(),
                path: entry.path.clone(),
                behavior: entry.behavior.clone(),
            };
            if &ours != row {
                return Err(CatalogueError::RubricRowMismatch {
                    index,
                    catalogue: Box::new(ours),
                    rubric: Box::new(row.clone()),
                });
            }
        }
        Ok(())
    }

    /// SHA-256 of the catalogue source, for the ledger.
    #[must_use]
    pub fn source_sha256(&self) -> &[u8; 32] {
        &self.source_sha256
    }

    /// The call sites a task spec's targets earn, deduplicated by path,
    /// in catalogue order within each target.
    ///
    /// A target matches an entry only when **both** its page and its path are
    /// the catalogued ones. The page alone is model-authored text, so matching
    /// on it alone would let a mis-named target pull an unrelated file into
    /// the projection; requiring the path too means a match can only ever name
    /// the file the human ruling already tied to that page.
    ///
    /// # Errors
    ///
    /// Returns [`CatalogueError::TooManyPacketCallSites`] when the selection
    /// exceeds [`MAX_PACKET_CALL_SITES`], which refuses rather than silently
    /// projecting a subset.
    pub fn call_sites(&self, targets: &[TaskTarget]) -> Result<Vec<CallSite>, CatalogueError> {
        let mut selected: Vec<CallSite> = Vec::new();
        for target in targets {
            let Some(entry) = self
                .entries
                .iter()
                .find(|entry| entry.page == target.page && entry.path == target.path)
            else {
                continue;
            };
            for site in &entry.call_sites {
                if selected.iter().any(|held| held.path == site.path) {
                    continue;
                }
                if selected.len() == MAX_PACKET_CALL_SITES {
                    return Err(CatalogueError::TooManyPacketCallSites);
                }
                selected.push(CallSite {
                    path: site.path.clone(),
                    page: entry.page.clone(),
                    why: site.why.clone(),
                });
            }
        }
        Ok(selected)
    }
}

fn bounded_field(value: &str, field: &str, maximum: usize) -> Result<(), CatalogueError> {
    if value.is_empty() || value.chars().count() > maximum {
        return Err(CatalogueError::FieldBounds {
            field: field.to_owned(),
        });
    }
    Ok(())
}

/// The same path contract the seat harnesses hold: relative, traversal-free,
/// and in a charset that survives being written into a JSON channel. Both
/// sides check it, because neither can see the other's check.
fn workspace_relative(path: &str) -> Result<(), CatalogueError> {
    let refuse = || CatalogueError::PathContract {
        path: path.to_owned(),
    };
    if path.is_empty()
        || path.chars().count() > MAX_PATH_CHARS
        || path.starts_with('/')
        || path
            .split('/')
            .any(|component| component == ".." || component.is_empty())
        || !path
            .chars()
            .all(|character| character.is_ascii_alphanumeric() || "._/-".contains(character))
    {
        return Err(refuse());
    }
    Ok(())
}

/// Read the rubric's human table back into rows.
///
/// The table is the ruling; this reads it rather than trusting a transcription
/// of it, so the agreement check compares the catalogue against the same bytes
/// the triage seat is prompted with.
fn rubric_rows(markdown: &str) -> Result<Vec<CatalogueRow>, CatalogueError> {
    let heading = markdown
        .find(CATALOGUE_HEADING)
        .ok_or(CatalogueError::RubricTableMissing)?;
    let mut rows = Vec::new();
    let mut seen_table = false;
    for line in markdown[heading..].lines().skip(1) {
        let line = line.trim();
        if !line.starts_with('|') {
            if seen_table {
                break;
            }
            if line.starts_with("## ") {
                return Err(CatalogueError::RubricTableMissing);
            }
            continue;
        }
        seen_table = true;
        let cells: Vec<&str> = line.trim_matches('|').split('|').map(str::trim).collect();
        if cells.len() != 3 || cells.iter().all(|cell| cell.chars().all(|c| c == '-')) {
            continue;
        }
        if cells[0] == "Page" && cells[1] == "Path" {
            continue;
        }
        rows.push(CatalogueRow {
            page: cells[0].to_owned(),
            path: cells[1].trim_matches('`').to_owned(),
            behavior: cells[2].to_owned(),
        });
    }
    if rows.is_empty() {
        return Err(CatalogueError::RubricTableMissing);
    }
    Ok(rows)
}

#[cfg(test)]
mod tests {
    use super::*;

    const RUBRIC: &str = "\
# Triage rubric

## Target catalogue (trusted)

Prose the table sits under.

| Page | Path | Where the behavior lives |
| --- | --- | --- |
| Simple Sales Report | `mfieldbook/common_functions.php` | `helper` supplies the options |
| Create or Assign School | `mfieldbook/leads/assign.php` | the page builds it locally |

## Lane actions

| Lane | Meaning |
| --- | --- |
| A | not a catalogue row |
";

    fn catalogue_json(call_sites: &str) -> String {
        format!(
            r#"{{"schema_version":1,"entries":[
              {{"page":"Simple Sales Report","path":"mfieldbook/common_functions.php",
                "behavior":"`helper` supplies the options","call_sites":[{call_sites}]}},
              {{"page":"Create or Assign School","path":"mfieldbook/leads/assign.php",
                "behavior":"the page builds it locally","call_sites":[]}}]}}"#
        )
    }

    fn site(path: &str) -> String {
        format!(r#"{{"path":"{path}","why":"renders it"}}"#)
    }

    fn target(page: &str, path: &str) -> TaskTarget {
        TaskTarget {
            page: page.to_owned(),
            path: path.to_owned(),
            evidence: "evidence".to_owned(),
        }
    }

    #[test]
    fn the_shipped_catalogue_agrees_with_the_shipped_rubric() {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .and_then(std::path::Path::parent)
            .expect("workspace root");
        let catalogue = TargetCatalogue::parse_json(
            &std::fs::read_to_string(root.join("policy/target-catalogue.json"))
                .expect("catalogue file"),
        )
        .expect("catalogue parses");
        catalogue
            .verify_against_rubric(
                &std::fs::read_to_string(root.join("policy/rubric.md")).expect("rubric file"),
            )
            .expect("catalogue agrees with the rubric");
    }

    #[test]
    fn a_matched_target_earns_its_pages_call_sites() {
        let catalogue = TargetCatalogue::parse_json(&catalogue_json(&site(
            "mfieldbook/reports/simple_sales_report.php",
        )))
        .expect("parses");
        let sites = catalogue
            .call_sites(&[target(
                "Simple Sales Report",
                "mfieldbook/common_functions.php",
            )])
            .expect("selects");
        assert_eq!(sites.len(), 1);
        assert_eq!(sites[0].path, "mfieldbook/reports/simple_sales_report.php");
        assert_eq!(sites[0].page, "Simple Sales Report");
    }

    #[test]
    fn a_target_whose_page_does_not_match_its_catalogued_path_earns_nothing() {
        // The page string is model-authored. On its own it must never be able
        // to pull a file into a seat's projection.
        let catalogue = TargetCatalogue::parse_json(&catalogue_json(&site(
            "mfieldbook/reports/simple_sales_report.php",
        )))
        .expect("parses");
        assert!(
            catalogue
                .call_sites(&[target("Simple Sales Report", "mfieldbook/leads/assign.php")])
                .expect("selects")
                .is_empty()
        );
        assert!(
            catalogue
                .call_sites(&[target(
                    "Create or Assign School",
                    "mfieldbook/common_functions.php"
                )])
                .expect("selects")
                .is_empty()
        );
    }

    #[test]
    fn a_page_catalogued_without_call_sites_earns_nothing() {
        let catalogue = TargetCatalogue::parse_json(&catalogue_json("")).expect("parses");
        assert!(
            catalogue
                .call_sites(&[target(
                    "Create or Assign School",
                    "mfieldbook/leads/assign.php"
                )])
                .expect("selects")
                .is_empty()
        );
    }

    #[test]
    fn two_targets_naming_one_call_site_carry_it_once() {
        let json = format!(
            r#"{{"schema_version":1,"entries":[
              {{"page":"Simple Sales Report","path":"mfieldbook/common_functions.php",
                "behavior":"`helper` supplies the options","call_sites":[{}]}},
              {{"page":"Create or Assign School","path":"mfieldbook/leads/assign.php",
                "behavior":"the page builds it locally","call_sites":[{}]}}]}}"#,
            site("mfieldbook/reports/simple_sales_report.php"),
            site("mfieldbook/reports/simple_sales_report.php"),
        );
        let catalogue = TargetCatalogue::parse_json(&json).expect("parses");
        let sites = catalogue
            .call_sites(&[
                target("Simple Sales Report", "mfieldbook/common_functions.php"),
                target("Create or Assign School", "mfieldbook/leads/assign.php"),
            ])
            .expect("selects");
        assert_eq!(sites.len(), 1);
    }

    #[test]
    fn a_catalogue_row_the_rubric_does_not_rule_is_refused() {
        let json = catalogue_json("").replace("Simple Sales Report", "Invented Page");
        let catalogue = TargetCatalogue::parse_json(&json).expect("parses");
        assert!(matches!(
            catalogue.verify_against_rubric(RUBRIC),
            Err(CatalogueError::RubricRowMismatch { index: 0, .. })
        ));
    }

    #[test]
    fn a_catalogue_that_reworded_the_rubrics_behavior_column_is_refused() {
        let json = catalogue_json("").replace("`helper` supplies the options", "helper does it");
        let catalogue = TargetCatalogue::parse_json(&json).expect("parses");
        assert!(matches!(
            catalogue.verify_against_rubric(RUBRIC),
            Err(CatalogueError::RubricRowMismatch { .. })
        ));
    }

    #[test]
    fn a_rubric_row_the_catalogue_omits_is_refused() {
        let json = r#"{"schema_version":1,"entries":[
          {"page":"Simple Sales Report","path":"mfieldbook/common_functions.php",
           "behavior":"`helper` supplies the options","call_sites":[]}]}"#;
        let catalogue = TargetCatalogue::parse_json(json).expect("parses");
        assert_eq!(
            catalogue.verify_against_rubric(RUBRIC),
            Err(CatalogueError::RubricRowCount {
                rubric: 2,
                catalogue: 1
            })
        );
    }

    #[test]
    fn the_rows_read_back_stop_at_the_catalogue_table() {
        // The rubric holds several tables; only the catalogue's rows may be
        // read, or the lane table would arrive as catalogue rows.
        let rows = rubric_rows(RUBRIC).expect("rows");
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0].path, "mfieldbook/common_functions.php");
        assert_eq!(rows[1].page, "Create or Assign School");
    }

    #[test]
    fn a_rubric_without_the_catalogue_heading_is_refused() {
        assert_eq!(
            rubric_rows("# Triage rubric\n\nno catalogue here\n"),
            Err(CatalogueError::RubricTableMissing)
        );
    }

    #[test]
    fn a_call_site_that_escapes_the_workspace_is_refused() {
        for escape in [
            "/etc/patchyard/xai-seat.key",
            "../../etc/passwd",
            "mfieldbook/../../secret",
        ] {
            assert!(
                matches!(
                    TargetCatalogue::parse_json(&catalogue_json(&site(escape))),
                    Err(CatalogueError::PathContract { .. })
                ),
                "{escape} was not refused"
            );
        }
    }

    #[test]
    fn a_call_site_naming_its_own_catalogued_path_is_refused() {
        assert!(matches!(
            TargetCatalogue::parse_json(&catalogue_json(&site("mfieldbook/common_functions.php"))),
            Err(CatalogueError::SelfCallSite { .. })
        ));
    }

    #[test]
    fn a_repeated_call_site_is_refused() {
        let json = catalogue_json(&format!(
            "{},{}",
            site("mfieldbook/reports/simple_sales_report.php"),
            site("mfieldbook/reports/simple_sales_report.php")
        ));
        assert!(matches!(
            TargetCatalogue::parse_json(&json),
            Err(CatalogueError::DuplicateCallSite { .. })
        ));
    }

    #[test]
    fn an_entry_over_the_call_site_bound_is_refused() {
        let sites: Vec<String> = (0..=MAX_CALL_SITES_PER_ENTRY)
            .map(|index| site(&format!("mfieldbook/page{index}.php")))
            .collect();
        assert!(matches!(
            TargetCatalogue::parse_json(&catalogue_json(&sites.join(","))),
            Err(CatalogueError::TooManyCallSites { .. })
        ));
    }

    #[test]
    fn an_unsupported_schema_version_is_refused() {
        let json = catalogue_json("").replace("\"schema_version\":1", "\"schema_version\":2");
        assert_eq!(
            TargetCatalogue::parse_json(&json),
            Err(CatalogueError::SchemaVersion(2))
        );
    }

    #[test]
    fn an_unknown_catalogue_field_is_refused() {
        let json =
            catalogue_json("").replace("\"call_sites\":[]", "\"call_sites\":[],\"lane\":\"A\"");
        assert!(matches!(
            TargetCatalogue::parse_json(&json),
            Err(CatalogueError::Malformed(_))
        ));
    }
}
