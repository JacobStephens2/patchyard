use factory_verify::{
    caps::{self, ChangeKind, DiffFile, DiffManifest},
    deny_paths::{self, DenyRule},
    ledger::{self, RunRecord},
    postconditions::{self, ListOrderRole, SortEvidence},
};
use proptest::prelude::*;
use serde_json::Value;
use sqlx::PgPool;
use uuid::Uuid;

const BASE_SHA: &str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const HASH: &str = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
const PROVENANCE_FIELDS: [&str; 8] = [
    "model_id_hash",
    "cli_version_hash",
    "constitution_hash",
    "rubric_hash",
    "skill_hash",
    "prompt_template_hash",
    "verifier_binary_hash",
    "base_tree_hash",
];
const ROUTING_PROVENANCE_FIELDS: [&str; 6] = [
    "model_id",
    "cli_version",
    "harness",
    "provider",
    "effort",
    "routing_config_version",
];

fn file(path: &str, additions: u64, deletions: u64) -> DiffFile {
    DiffFile {
        path: path.to_owned(),
        old_path: None,
        change: ChangeKind::Modified,
        additions,
        deletions,
        binary: false,
        generated: false,
        old_mode: Some("100644".to_owned()),
        new_mode: Some("100644".to_owned()),
    }
}

fn manifest() -> DiffManifest {
    DiffManifest {
        base_sha: BASE_SHA.to_owned(),
        files: vec![
            file("mfieldbook/report.php", 20, 10),
            file("mfieldbook/report.test.php", 10, 10),
        ],
    }
}

#[test]
fn caps_rejects_every_enumerated_mutation() {
    assert!(caps::verify(&manifest(), BASE_SHA, 2, 50).is_ok());

    let mut wrong_base = manifest();
    wrong_base.base_sha = "cccccccccccccccccccccccccccccccccccccccc".to_owned();

    let mut whitespace_padding = manifest();
    // Diff accounting is intentionally content-blind: a whitespace-only line
    // is still an addition, so padding cannot evade the 50-line circuit breaker.
    whitespace_padding.files[0].additions += 1;

    let mut extra_file = manifest();
    extra_file.files.push(file("mfieldbook/third.php", 0, 0));

    let mut rename = manifest();
    rename.files[0].change = ChangeKind::Renamed;
    rename.files[0].old_path = Some("mfieldbook/old-report.php".to_owned());

    let mut mode = manifest();
    mode.files[0].new_mode = Some("100755".to_owned());

    let mut binary = manifest();
    binary.files[0].binary = true;

    let mut generated = manifest();
    generated.files[0].generated = true;

    let mutations = [
        ("recorded-base-sha-change", wrong_base),
        ("whitespace-only-padding", whitespace_padding),
        ("file-membership-change", extra_file),
        ("rename", rename),
        ("mode-change", mode),
        ("binary-change", binary),
        ("generated-change", generated),
    ];
    for (name, mutation) in mutations {
        assert!(
            caps::verify(&mutation, BASE_SHA, 2, 50).is_err(),
            "caps accepted enumerated mutation {name}"
        );
    }
}

#[test]
fn deny_paths_rejects_self_protection_categories_and_both_rename_sides() {
    let cases = [
        (
            ".github/workflows/application.yml",
            DenyRule::FactorySelfProtection,
        ),
        (
            "infra/digitalocean/main.tf",
            DenyRule::FactorySelfProtection,
        ),
        ("policy/routing.json", DenyRule::FactorySelfProtection),
        (
            "crates/factory-verify/src/deny_paths.rs",
            DenyRule::FactorySelfProtection,
        ),
        ("mysql_files/2026.sql", DenyRule::SchemaOrMigration),
        (
            "mfieldbook/auth/login.php",
            DenyRule::AuthSessionPermissionOrSecret,
        ),
        ("mfieldbook/accounting/totals.php", DenyRule::Financial),
        ("mfieldbook/email/send.php", DenyRule::OutboundOrScheduled),
        ("customerweb/index.php", DenyRule::CustomerFacing),
        ("composer.lock", DenyRule::DependencyOrLockfile),
        (".github/dependabot.yml", DenyRule::Ci),
        ("scripts/deploy-fieldbook.sh", DenyRule::Deploy),
    ];
    for (path, expected) in cases {
        let manifest = DiffManifest {
            base_sha: BASE_SHA.to_owned(),
            files: vec![file(path, 1, 0)],
        };
        let error = deny_paths::verify(&manifest)
            .expect_err("deny-paths must reject every enumerated constitution category");
        assert!(matches!(
            error,
            deny_paths::DenyPathsError::Denied { rule, .. } if rule == expected
        ));
    }

    let mut renamed = file("mfieldbook/report.php", 1, 1);
    renamed.change = ChangeKind::Renamed;
    renamed.old_path = Some("mfieldbook/auth/login.php".to_owned());
    let manifest = DiffManifest {
        base_sha: BASE_SHA.to_owned(),
        files: vec![renamed],
    };
    assert!(deny_paths::verify(&manifest).is_err());

    let mut renamed = file("infra/digitalocean/main.tf", 1, 1);
    renamed.change = ChangeKind::Renamed;
    renamed.old_path = Some("mfieldbook/report.php".to_owned());
    let manifest = DiffManifest {
        base_sha: BASE_SHA.to_owned(),
        files: vec![renamed],
    };
    assert!(
        deny_paths::verify(&manifest).is_err(),
        "deny-paths accepted a rename into a factory gate path"
    );
}

fn sort_evidence() -> SortEvidence {
    serde_json::from_str(include_str!("fixtures/sort-valid.json"))
        .expect("committed canned DOM fixture is valid")
}

#[test]
fn postconditions_accepts_canned_dom_fixture() {
    postconditions::verify(&sort_evidence()).expect("ruled sort fixture must pass");
}

#[test]
fn postconditions_case_folds_unicode_first_names_stably() {
    let mut evidence = sort_evidence();
    evidence.baseline.selects.truncate(1);
    evidence.candidate.selects.truncate(1);
    evidence.baseline.selects[0].options = vec![
        evidence.baseline.selects[0].options[0].clone(),
        factory_verify::postconditions::OptionSnapshot {
            label: "Zoë Adams".to_owned(),
            value: "1".to_owned(),
            selected: false,
            blank_sentinel: false,
        },
        factory_verify::postconditions::OptionSnapshot {
            label: "Éva Baker".to_owned(),
            value: "2".to_owned(),
            selected: false,
            blank_sentinel: false,
        },
        factory_verify::postconditions::OptionSnapshot {
            label: "éva Chen".to_owned(),
            value: "3".to_owned(),
            selected: false,
            blank_sentinel: false,
        },
    ];
    evidence.candidate.selects[0].options = vec![
        evidence.baseline.selects[0].options[0].clone(),
        evidence.baseline.selects[0].options[1].clone(),
        evidence.baseline.selects[0].options[2].clone(),
        evidence.baseline.selects[0].options[3].clone(),
    ];
    postconditions::verify(&evidence).expect("Unicode case folding preserves stable equal keys");
}

#[test]
fn postconditions_rejects_every_enumerated_mutation() {
    let mut where_clause = sort_evidence();
    where_clause.candidate.source.where_clause.push(' ');

    let mut option_value = sort_evidence();
    option_value.candidate.selects[0].options[1].value = "999".to_owned();

    let mut membership = sort_evidence();
    membership.candidate.selects[0].options.pop();

    let mut sort_key = sort_evidence();
    sort_key.candidate.source.sort_key = "last_name_casefolded".to_owned();

    let mut selection = sort_evidence();
    selection.candidate.selects[1].options[0].selected = false;
    selection.candidate.selects[1].options[1].selected = true;

    let mut shared_caller = sort_evidence();
    shared_caller.candidate.callers.pop();

    let mut priority_order = sort_evidence();
    priority_order.baseline.source.list_order_role = ListOrderRole::Priority;

    let mut sentinel = sort_evidence();
    sentinel.candidate.selects[0].options.swap(0, 1);

    let mut duplicate = sort_evidence();
    duplicate.candidate.selects[0].options[2] = duplicate.candidate.selects[0].options[1].clone();

    let mutations = [
        ("where-clause-change", where_clause),
        ("option-value-change", option_value),
        ("option-membership-change", membership),
        ("sort-key-swap", sort_key),
        ("selected-value-change", selection),
        ("shared-getter-caller-change", shared_caller),
        ("priority-list-order-change", priority_order),
        ("blank-sentinel-move", sentinel),
        ("duplicate-option-count-change", duplicate),
    ];
    for (name, mutation) in mutations {
        assert!(
            postconditions::verify(&mutation).is_err(),
            "postconditions accepted enumerated mutation {name}"
        );
    }
}

fn run_record_json() -> Value {
    serde_json::json!({
        "id": Uuid::nil(),
        "request_id": Uuid::from_u128(1),
        "run_class": "production",
        "base_sha": BASE_SHA,
        "branch": "factory/request-sort",
        "lane": "A",
        "skill": "alphabetize-first-name",
        "provenance": {
            "model_id": "GPT-5.6 Sol|xhigh|Codex|OpenAI",
            "cli_version": "codex 1.2.3",
            "harness": "Codex",
            "provider": "OpenAI",
            "effort": "xhigh",
            "routing_config_version": "2026-07-23.1",
            "model_id_hash": HASH,
            "cli_version_hash": HASH,
            "constitution_hash": HASH,
            "rubric_hash": HASH,
            "skill_hash": HASH,
            "prompt_template_hash": HASH,
            "verifier_binary_hash": HASH,
            "base_tree_hash": HASH
        }
    })
}

#[test]
fn ledger_append_rejects_each_missing_or_malformed_provenance_field() {
    let valid: RunRecord = serde_json::from_value(run_record_json()).expect("valid record JSON");
    assert!(ledger::validate(valid).is_ok());

    for field in PROVENANCE_FIELDS {
        let mut missing = run_record_json();
        missing["provenance"]
            .as_object_mut()
            .expect("provenance is an object")
            .remove(field);
        assert!(
            serde_json::from_value::<RunRecord>(missing).is_err(),
            "ledger-append accepted missing provenance field {field}"
        );

        let mut malformed = run_record_json();
        malformed["provenance"][field] = Value::String("not-a-sha256".to_owned());
        let record: RunRecord =
            serde_json::from_value(malformed).expect("record shape remains valid");
        assert!(
            ledger::validate(record).is_err(),
            "ledger-append accepted malformed provenance field {field}"
        );
    }
    for field in ROUTING_PROVENANCE_FIELDS {
        let mut missing = run_record_json();
        missing["provenance"]
            .as_object_mut()
            .expect("provenance is an object")
            .remove(field);
        assert!(
            serde_json::from_value::<RunRecord>(missing).is_err(),
            "ledger-append accepted missing routing provenance field {field}"
        );

        let mut blank = run_record_json();
        blank["provenance"][field] = Value::String("  ".to_owned());
        let record: RunRecord = serde_json::from_value(blank).expect("record shape remains valid");
        assert!(
            ledger::validate(record).is_err(),
            "ledger-append accepted blank routing provenance field {field}"
        );
    }
}

#[test]
fn ledger_append_rejects_invalid_run_envelope_fields() {
    for field in ["branch", "lane", "skill"] {
        let mut value = run_record_json();
        value[field] = Value::String("  ".to_owned());
        let record: RunRecord = serde_json::from_value(value).expect("record shape remains valid");
        assert!(ledger::validate(record).is_err(), "accepted blank {field}");
    }

    let mut value = run_record_json();
    value["base_sha"] = Value::String("not-a-git-sha".to_owned());
    let record: RunRecord = serde_json::from_value(value).expect("record shape remains valid");
    assert!(ledger::validate(record).is_err());
}

#[tokio::test]
async fn ledger_append_commits_run_and_event_together() -> Result<(), Box<dyn std::error::Error>> {
    let Ok(database_url) = std::env::var("FACTORY_TEST_DATABASE_URL") else {
        eprintln!("skipped: disposable PostgreSQL URL is not set");
        return Ok(());
    };
    let pool = PgPool::connect(&database_url).await?;
    let request_id = Uuid::new_v4();
    let run_id = Uuid::new_v4();
    let mut value = run_record_json();
    value["id"] = serde_json::to_value(run_id)?;
    value["request_id"] = serde_json::to_value(request_id)?;
    value["branch"] = Value::String(format!("factory/{run_id}"));
    let record = ledger::validate(serde_json::from_value(value.clone())?)?;

    assert!(matches!(
        ledger::append(&pool, &record).await,
        Err(ledger::LedgerError::RequestNotFound(id)) if id == request_id
    ));
    let orphan_count: i64 = sqlx::query_scalar("SELECT count(*) FROM factory.runs WHERE id = $1")
        .bind(run_id)
        .fetch_one(&pool)
        .await?;
    assert_eq!(orphan_count, 0, "failed append left an orphan run");

    let mut fingerprint = [61_u8; 32];
    fingerprint[..16].copy_from_slice(request_id.as_bytes());
    sqlx::query(
        r#"
        INSERT INTO factory.requests (id, fingerprint, source, body, trace_id)
        VALUES ($1, $2, 'verifier-test', 'ledger append fixture', $3)
        "#,
    )
    .bind(request_id)
    .bind(fingerprint.as_slice())
    .bind(format!("{:032x}", request_id.as_u128()))
    .execute(&pool)
    .await?;
    sqlx::query(
        r#"
        INSERT INTO factory.events (request_id,event_type,trace_id,payload)
        VALUES ($1,'request.claimed',$2,'{"run_class":"production"}'::jsonb)
        "#,
    )
    .bind(request_id)
    .bind(format!("{:032x}", request_id.as_u128()))
    .execute(&pool)
    .await?;

    ledger::append(&pool, &record).await?;
    let pair_count: i64 = sqlx::query_scalar(
        r#"
        SELECT count(*)
        FROM factory.runs
        JOIN factory.events ON events.run_id = runs.id
        WHERE runs.id = $1
          AND events.event_type = 'run.queued'
          AND runs.model_id_hash IS NOT NULL
          AND runs.cli_version_hash IS NOT NULL
          AND runs.constitution_hash IS NOT NULL
          AND runs.rubric_hash IS NOT NULL
          AND runs.skill_hash IS NOT NULL
          AND runs.prompt_template_hash IS NOT NULL
          AND runs.verifier_binary_hash IS NOT NULL
          AND runs.base_tree_hash IS NOT NULL
          AND runs.model_id = 'GPT-5.6 Sol|xhigh|Codex|OpenAI'
          AND runs.cli_version = 'codex 1.2.3'
          AND runs.harness = 'Codex'
          AND runs.provider = 'OpenAI'
          AND runs.effort = 'xhigh'
          AND runs.routing_config_version = '2026-07-23.1'
        "#,
    )
    .bind(run_id)
    .fetch_one(&pool)
    .await?;
    assert_eq!(pair_count, 1);
    Ok(())
}

proptest! {
    #![proptest_config(ProptestConfig {
        failure_persistence: None,
        .. ProptestConfig::default()
    })]

    #[test]
    fn caps_counts_all_additions_and_deletions(additions in 0_u64..=50, deletions in 0_u64..=50) {
        let manifest = DiffManifest {
            base_sha: BASE_SHA.to_owned(),
            files: vec![file("mfieldbook/report.php", additions, deletions)],
        };
        let result = caps::verify(&manifest, BASE_SHA, 2, 50);
        prop_assert_eq!(result.is_ok(), additions + deletions <= 50);
    }
}
