use std::{
    fs,
    os::unix::fs::PermissionsExt as _,
    path::{Path, PathBuf},
    time::{Duration, SystemTime, UNIX_EPOCH},
};

use factory_supervisor::{
    artifacts::ArtifactStore,
    child::{
        ChildSpawnConfig, ChildTerminalState, EvidenceAction, EvidenceContract,
        IsolatedChildSpawner, PreviewBearer,
    },
    evidence::{EvidenceCapture, EvidenceError},
};
use tempfile::TempDir;
use tokio_util::sync::CancellationToken;
use uuid::Uuid;

struct Fixture {
    _temp: TempDir,
    capture: EvidenceCapture,
    artifact_root: PathBuf,
    staging_root: PathBuf,
}

impl Fixture {
    fn new() -> Self {
        let project = project_root();
        let temp = tempfile::tempdir().expect("fixture tempdir");
        let artifact_root = temp.path().join("artifacts");
        let staging_root = temp.path().join("children");
        fs::create_dir(&artifact_root).expect("artifact root");
        fs::set_permissions(&artifact_root, fs::Permissions::from_mode(0o2750))
            .expect("artifact permissions");
        fs::create_dir(&staging_root).expect("staging root");
        fs::set_permissions(&staging_root, fs::Permissions::from_mode(0o700))
            .expect("staging permissions");
        let spawner = IsolatedChildSpawner::new(ChildSpawnConfig {
            spawn_program: project.join("fixtures/pipeline/bin/child-evidence-fixture"),
            cancel_program: project.join("fixtures/pipeline/bin/child-cancel-stub"),
            staging_root: staging_root.clone(),
            timeout: Duration::from_secs(10),
        });
        let artifacts = ArtifactStore::open(&artifact_root).expect("artifact store");
        Self {
            _temp: temp,
            capture: EvidenceCapture::new(spawner, artifacts),
            artifact_root,
            staging_root,
        }
    }

    async fn run(&self, state: &str) -> Result<Vec<String>, EvidenceError> {
        let artifacts = self
            .capture
            .capture(
                Uuid::new_v4(),
                Uuid::new_v4(),
                contract(state),
                bearer(),
                &CancellationToken::new(),
            )
            .await?;
        Ok(artifacts
            .into_iter()
            .map(|artifact| artifact.kind)
            .collect())
    }

    fn artifact_file_count(&self) -> usize {
        walk_files(&self.artifact_root)
    }

    fn staging_is_empty(&self) -> bool {
        fs::read_dir(&self.staging_root)
            .expect("staging listing")
            .next()
            .is_none()
    }
}

#[tokio::test]
async fn evidence_outputs_import_only_after_shared_child_teardown() {
    let fixture = Fixture::new();
    let kinds = fixture.run("completed").await.expect("positive capture");
    assert_eq!(
        kinds,
        [
            "evidence-dom",
            "evidence-screenshot",
            "evidence-extract",
            "evidence-hashes",
            "evidence-execution",
        ]
    );
    assert_eq!(fixture.artifact_file_count(), 5);
    assert!(
        fixture.staging_is_empty(),
        "child staging was explicitly closed"
    );
}

#[tokio::test]
async fn every_predeclared_negative_state_imports_nothing_and_tears_down() {
    for (fixture_id, state, expected) in [
        (
            "S13-N01",
            "redirect_blocked",
            ChildTerminalState::RedirectBlocked,
        ),
        (
            "S13-N02",
            "dns_binding_changed",
            ChildTerminalState::DnsBindingChanged,
        ),
        (
            "S13-N03",
            "cross_origin_blocked",
            ChildTerminalState::CrossOriginBlocked,
        ),
        ("S13-N04", "popup_blocked", ChildTerminalState::PopupBlocked),
        (
            "S13-N05",
            "download_blocked",
            ChildTerminalState::DownloadBlocked,
        ),
        (
            "S13-N06",
            "output_limit_exceeded",
            ChildTerminalState::OutputLimitExceeded,
        ),
        (
            "S13-N07",
            "bearer_disclosure_blocked",
            ChildTerminalState::BearerDisclosureBlocked,
        ),
        (
            "S13-N08",
            "browser_crashed",
            ChildTerminalState::BrowserCrashed,
        ),
        (
            "S13-N09",
            "authority_probe_failed",
            ChildTerminalState::AuthorityProbeFailed,
        ),
        (
            "S13-N10",
            "egress_probe_failed",
            ChildTerminalState::EgressProbeFailed,
        ),
        (
            "S13-N11",
            "child_timed_out",
            ChildTerminalState::ChildTimedOut,
        ),
        (
            "S13-N12",
            "teardown_failed",
            ChildTerminalState::TeardownFailed,
        ),
    ] {
        let fixture = Fixture::new();
        let error = fixture
            .run(state)
            .await
            .expect_err("negative fixture must fail closed");
        assert!(
            matches!(error, EvidenceError::FailClosed(actual) if actual == expected),
            "{fixture_id} reached {error:?}"
        );
        assert_eq!(
            fixture.artifact_file_count(),
            0,
            "{fixture_id} imported evidence before acceptance"
        );
        assert!(
            fixture.staging_is_empty(),
            "{fixture_id} left child staging behind"
        );
    }
}

fn contract(state: &str) -> EvidenceContract {
    EvidenceContract {
        allowed_url: format!("https://1.preview.example.dev/{state}"),
        expected_sha: "a".repeat(40),
        actions: vec![
            EvidenceAction::WaitFor {
                selector: "#sales_person_id".to_owned(),
            },
            EvidenceAction::ExtractSelect {
                selector: "#sales_person_id".to_owned(),
            },
            EvidenceAction::Screenshot,
        ],
        navigation_timeout_ms: 10_000,
        action_timeout_ms: 5_000,
        total_timeout_ms: 30_000,
        maximum_dom_bytes: 2_000_000,
        maximum_screenshot_bytes: 5_000_000,
        maximum_extract_bytes: 1024 * 1024,
    }
}

fn bearer() -> PreviewBearer {
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("clock")
        .as_secs();
    PreviewBearer {
        capability_id: format!("fixture-{}", Uuid::new_v4().simple()),
        expires_at_unix: i64::try_from(now).expect("clock range") + 60,
        secret: format!("secret-{}", Uuid::new_v4().simple()),
    }
}

fn walk_files(path: &Path) -> usize {
    fs::read_dir(path)
        .expect("directory")
        .map(|entry| entry.expect("entry").path())
        .map(|path| if path.is_dir() { walk_files(&path) } else { 1 })
        .sum()
}

fn project_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .expect("project root")
}
