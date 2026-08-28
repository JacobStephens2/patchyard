use std::{
    collections::BTreeMap,
    ffi::OsString,
    fs,
    io::Write as _,
    os::unix::fs::{OpenOptionsExt as _, PermissionsExt as _},
    path::{Path, PathBuf},
    process::Command,
    sync::{Arc, Mutex},
    time::Duration,
};

use factory_core::triage::TriageOutput;
use factory_supervisor::{
    config::Seat,
    contracts::{ResolvedInvocation, TriageInvocation},
    stages::{CredentialCommand, ProcessAgentBackend, StageCommand},
};
use serde_json::json;
use tempfile::TempDir;
use tokio::{
    io::{AsyncReadExt as _, AsyncWriteExt as _},
    net::TcpListener,
};
use tokio_util::sync::CancellationToken;
use uuid::Uuid;

const INPUT_TOKENS: u64 = 11;
const OUTPUT_TOKENS: u64 = 23;

fn project_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .expect("project root")
}

fn tmpfs() -> TempDir {
    let directory = tempfile::Builder::new()
        .prefix("patchyard-triage-seat-")
        .tempdir_in("/dev/shm")
        .expect("tmpfs fixture");
    fs::set_permissions(directory.path(), fs::Permissions::from_mode(0o700))
        .expect("tmpfs permissions");
    let output = Command::new("/usr/bin/stat")
        .args(["-f", "-c", "%T", "/dev/shm"])
        .output()
        .expect("stat tmpfs");
    assert!(output.status.success());
    assert_eq!(
        String::from_utf8(output.stdout).expect("stat utf8").trim(),
        "tmpfs"
    );
    directory
}

fn synthetic_bearer() -> String {
    format!("sk-{}-{}", "ant-oat01", Uuid::new_v4().simple())
}

fn write_private(path: &Path, bytes: &[u8]) {
    let mut file = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(path)
        .expect("private file");
    file.write_all(bytes).expect("private write");
}

fn write_minter(directory: &Path, bearer: &str) -> (PathBuf, PathBuf, PathBuf) {
    let program = directory.join("mint-stub");
    let argv_log = directory.join("mint.argv");
    let environment_log = directory.join("mint.environment");
    fs::write(
        &program,
        format!(
            "#!/usr/bin/bash\nset -euo pipefail\nprintf '%s\\0' \"$0\" \"$@\" > '{}'\nenv -0 > '{}'\nprintf '%s' '{}' > \"$2\"\nchmod 0600 \"$2\"\n",
            argv_log.display(),
            environment_log.display(),
            bearer,
        ),
    )
    .expect("mint stub");
    fs::set_permissions(&program, fs::Permissions::from_mode(0o700)).expect("mint executable");
    (program, argv_log, environment_log)
}

fn write_seat_wrapper(directory: &Path, seat: &Path) -> (PathBuf, PathBuf, PathBuf) {
    let program = directory.join("seat-wrapper");
    let argv_log = directory.join("seat.argv.json");
    let environment_log = directory.join("seat.environment.json");
    fs::write(
        &program,
        format!(
            "#!/usr/bin/python3\nimport json\nimport os\nimport sys\nwith open({argv_log:?}, 'w', encoding='utf-8') as output:\n    json.dump(sys.argv, output)\nwith open('/proc/self/environ', 'rb') as source:\n    raw_environment = source.read()\nwith open({environment_log:?}, 'wb') as output:\n    output.write(raw_environment)\nenvironment = {{}}\nfor entry in raw_environment.split(b'\\0'):\n    if entry:\n        key, value = entry.split(b'=', 1)\n        environment[os.fsdecode(key)] = os.fsdecode(value)\nos.execve({seat:?}, [{seat:?}, *sys.argv[1:]], environment)\n",
            argv_log = argv_log.display().to_string(),
            environment_log = environment_log.display().to_string(),
            seat = seat.display().to_string(),
        ),
    )
    .expect("seat wrapper");
    fs::set_permissions(&program, fs::Permissions::from_mode(0o700))
        .expect("seat wrapper executable");
    (program, argv_log, environment_log)
}

async fn stub_provider(
    status: u16,
    body: Vec<u8>,
) -> (String, Arc<Mutex<Vec<u8>>>, tokio::task::JoinHandle<()>) {
    let listener = TcpListener::bind("127.0.0.1:0").await.expect("stub bind");
    let address = listener.local_addr().expect("stub address");
    let captured = Arc::new(Mutex::new(Vec::new()));
    let request_capture = Arc::clone(&captured);
    let task = tokio::spawn(async move {
        let (mut stream, _) = listener.accept().await.expect("stub accept");
        let mut request = Vec::new();
        let mut buffer = [0_u8; 4096];
        let header_end = loop {
            let count = stream.read(&mut buffer).await.expect("stub read");
            assert!(count > 0, "request ended before headers");
            request.extend_from_slice(&buffer[..count]);
            if let Some(position) = request.windows(4).position(|window| window == b"\r\n\r\n") {
                break position + 4;
            }
        };
        let headers = String::from_utf8(request[..header_end].to_vec()).expect("request headers");
        let content_length = headers
            .lines()
            .find_map(|line| {
                line.to_ascii_lowercase()
                    .strip_prefix("content-length:")
                    .map(str::trim)
                    .map(str::parse::<usize>)
            })
            .expect("content length")
            .expect("numeric content length");
        while request.len() < header_end + content_length {
            let count = stream.read(&mut buffer).await.expect("stub body read");
            assert!(count > 0, "request body ended early");
            request.extend_from_slice(&buffer[..count]);
        }
        *request_capture.lock().expect("request capture") = request;
        let reason = if status == 200 { "OK" } else { "Refused" };
        let response = format!(
            "HTTP/1.1 {status} {reason}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
            body.len()
        );
        stream
            .write_all(response.as_bytes())
            .await
            .expect("stub response headers");
        stream.write_all(&body).await.expect("stub response body");
    });
    (format!("http://{address}"), captured, task)
}

fn triage_output_text() -> String {
    fs::read_to_string(project_root().join("fixtures/triage/alphabetize.json"))
        .expect("triage fixture")
}

fn provider_success(content: serde_json::Value) -> Vec<u8> {
    serde_json::to_vec(&json!({
        "type": "message",
        "model": "claude-fable-5",
        "stop_reason": "end_turn",
        "content": content,
        "usage": {
            "input_tokens": INPUT_TOKENS,
            "output_tokens": OUTPUT_TOKENS,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0
        }
    }))
    .expect("provider response")
}

fn invocation(provider: String) -> ResolvedInvocation {
    ResolvedInvocation {
        task_class: "triage".to_owned(),
        routing_version: "provider-free-test".to_owned(),
        seat: Seat {
            model: "Claude Fable 5".to_owned(),
            effort: "max".to_owned(),
            harness: "Claude Code".to_owned(),
            provider,
        },
    }
}

fn triage_input() -> TriageInvocation {
    TriageInvocation {
        schema_version: 1,
        request_id: Uuid::new_v4(),
        untrusted_request: "ALPHABETIZE the two named salesperson selectors".to_owned(),
        authority: "none_untrusted_data_only".to_owned(),
    }
}

#[tokio::test]
async fn real_triage_seat_parses_thinking_then_text_without_bearer_residue() {
    let fixture = tmpfs();
    let bearer = synthetic_bearer();
    let (minter, argv_log, environment_log) = write_minter(fixture.path(), &bearer);
    let provider_response = provider_success(json!([
        {
            "type": "thinking",
            "thinking": "Synthetic classification reasoning with no repository claims.",
            "signature": "synthetic-signature"
        },
        {"type": "text", "text": triage_output_text()}
    ]));
    let (provider, captured, server) = stub_provider(200, provider_response).await;
    let root = project_root();
    let (seat, seat_argv_log, seat_environment_log) = write_seat_wrapper(
        fixture.path(),
        &root.join("infra/ansible/roles/control_plane/files/patchyard-triage-seat"),
    );
    let mut commands = BTreeMap::new();
    commands.insert(
        "triage".to_owned(),
        StageCommand {
            program: seat,
            prompt: root.join("policy/triage.md"),
            timeout: Duration::from_secs(10),
            cli_version: "patchyard-triage-seat/1".to_owned(),
            credential: Some(CredentialCommand {
                program: minter,
                arguments: Vec::new(),
                timeout: Duration::from_secs(5),
            }),
        },
    );
    let scratch = fixture.path().join("agents");
    let backend = ProcessAgentBackend::new(commands, scratch.clone());
    let result = backend
        .invoke::<_, TriageOutput>(
            &invocation(provider),
            &triage_input(),
            &CancellationToken::new(),
        )
        .await
        .expect("typed triage result");
    result.value.validate().expect("valid TriageOutput");
    TriageOutput::parse_json(
        &serde_json::to_string(&result.value).expect("serialize TriageOutput"),
    )
    .expect("TriageOutput::parse_json accepts the seat result");
    assert_eq!(result.usage.input_tokens, INPUT_TOKENS);
    assert_eq!(result.usage.output_tokens, OUTPUT_TOKENS);
    assert_eq!(result.usage.cost_microusd, None);
    assert!(!String::from_utf8_lossy(&result.transcript).contains(&bearer));

    server.await.expect("stub server");
    let request = captured.lock().expect("captured request").clone();
    let header_end = request
        .windows(4)
        .position(|window| window == b"\r\n\r\n")
        .expect("header boundary")
        + 4;
    assert!(
        String::from_utf8_lossy(&request[..header_end])
            .to_ascii_lowercase()
            .contains("authorization: bearer ")
    );
    assert!(!String::from_utf8_lossy(&request[header_end..]).contains(&bearer));
    let request_json: serde_json::Value =
        serde_json::from_slice(&request[header_end..]).expect("provider request JSON");
    assert_eq!(request_json["model"], "claude-fable-5");
    assert_eq!(request_json["output_config"]["effort"], "max");
    assert_eq!(request_json["thinking"]["type"], "adaptive");
    assert!(request_json.get("tools").is_none());

    let minter_argv = fs::read(&argv_log).expect("mint argv");
    let minter_environment = fs::read(&environment_log).expect("mint environment");
    let seat_argv: Vec<String> =
        serde_json::from_slice(&fs::read(&seat_argv_log).expect("seat argv"))
            .expect("seat argv JSON");
    let seat_environment: BTreeMap<String, String> = fs::read(&seat_environment_log)
        .expect("seat environment")
        .split(|byte| *byte == 0)
        .filter(|entry| !entry.is_empty())
        .map(|entry| {
            let separator = entry
                .iter()
                .position(|byte| *byte == b'=')
                .expect("seat environment entry");
            let (key, value) = entry.split_at(separator);
            (
                String::from_utf8(key.to_vec()).expect("seat environment key"),
                String::from_utf8(value[1..].to_vec()).expect("seat environment value"),
            )
        })
        .collect();
    assert!(!String::from_utf8_lossy(&minter_argv).contains(&bearer));
    assert!(!String::from_utf8_lossy(&minter_environment).contains(&bearer));
    assert!(seat_argv.iter().all(|argument| !argument.contains(&bearer)));
    assert!(
        seat_environment
            .values()
            .all(|value| !value.contains(&bearer))
    );
    assert_eq!(
        seat_environment
            .keys()
            .map(String::as_str)
            .collect::<Vec<_>>(),
        vec![
            "PATCHYARD_BEARER_FILE",
            "PATCHYARD_EFFORT",
            "PATCHYARD_HARNESS",
            "PATCHYARD_MODEL",
            "PATCHYARD_PROVIDER",
            "PATH",
        ]
    );
    let bearer_path = minter_argv
        .split(|byte| *byte == 0)
        .rfind(|value| !value.is_empty())
        .map(|value| PathBuf::from(String::from_utf8(value.to_vec()).expect("bearer path utf8")))
        .expect("bearer path argument");
    assert!(!bearer_path.exists());
    assert_eq!(fs::read_dir(scratch).expect("agent scratch").count(), 0);
}

fn direct_stage(fixture: &TempDir, bearer: &str) -> (PathBuf, PathBuf, Vec<OsString>) {
    let stage = fixture.path().join(format!("agent-{}", Uuid::new_v4()));
    fs::create_dir(&stage).expect("stage directory");
    fs::set_permissions(&stage, fs::Permissions::from_mode(0o700)).expect("stage mode");
    let input = stage.join("input.json");
    let output = stage.join("output.json");
    let bearer_path = stage.join("bearer");
    write_private(
        &input,
        &serde_json::to_vec(&triage_input()).expect("triage input JSON"),
    );
    write_private(&bearer_path, bearer.as_bytes());
    let arguments = vec![
        project_root().join("policy/triage.md").into_os_string(),
        input.into_os_string(),
        output.clone().into_os_string(),
    ];
    (output, bearer_path, arguments)
}

async fn run_direct_response(
    status: u16,
    body: Vec<u8>,
) -> (
    TempDir,
    String,
    String,
    PathBuf,
    PathBuf,
    Vec<OsString>,
    std::process::Output,
) {
    let fixture = tmpfs();
    let bearer = synthetic_bearer();
    let (provider, _captured, server) = stub_provider(status, body).await;
    let (output, bearer_path, arguments) = direct_stage(&fixture, &bearer);
    let program =
        project_root().join("infra/ansible/roles/control_plane/files/patchyard-triage-seat");
    let process = tokio::task::spawn_blocking({
        let bearer_path = bearer_path.clone();
        let provider = provider.clone();
        let arguments = arguments.clone();
        move || {
            Command::new(program)
                .args(&arguments)
                .env_clear()
                .env("PATH", "/usr/local/bin:/usr/bin:/bin")
                .env("PATCHYARD_MODEL", "Claude Fable 5")
                .env("PATCHYARD_EFFORT", "max")
                .env("PATCHYARD_HARNESS", "Claude Code")
                .env("PATCHYARD_PROVIDER", provider)
                .env("PATCHYARD_BEARER_FILE", bearer_path)
                .output()
                .expect("seat failure process")
        }
    })
    .await
    .expect("seat failure task");
    server.await.expect("failure stub server");
    (
        fixture,
        bearer,
        provider,
        output,
        bearer_path,
        arguments,
        process,
    )
}

async fn assert_clean_failure(status: u16, body: Vec<u8>, expected_error: &str) {
    let (_fixture, bearer, provider, output, bearer_path, arguments, process) =
        run_direct_response(status, body).await;
    assert!(!process.status.success());
    assert!(!output.exists(), "no partial output may be written");
    assert!(!bearer_path.exists(), "seat removes its bearer on failure");
    assert!(!String::from_utf8_lossy(&process.stdout).contains(&bearer));
    assert!(!String::from_utf8_lossy(&process.stderr).contains(&bearer));
    assert!(String::from_utf8_lossy(&process.stderr).contains(expected_error));
    assert!(
        arguments
            .iter()
            .all(|argument| !argument.to_string_lossy().contains(&bearer))
    );
    let bearer_path_value = bearer_path.to_string_lossy();
    for value in [
        "Claude Fable 5",
        "max",
        "Claude Code",
        provider.as_str(),
        bearer_path_value.as_ref(),
    ] {
        assert!(!value.contains(&bearer));
    }
}

#[tokio::test]
async fn provider_refusal_and_malformed_response_leave_no_output_or_bearer() {
    assert_clean_failure(
        401,
        serde_json::to_vec(&json!({
            "type": "error",
            "error": {"type": "authentication_error", "message": "refused"}
        }))
        .expect("refusal"),
        "provider refused triage request with HTTP 401",
    )
    .await;
    assert_clean_failure(
        200,
        provider_success(json!([{
            "type": "thinking",
            "thinking": "Synthetic reasoning without an answer.",
            "signature": "synthetic-signature"
        }])),
        "provider response must contain one text block",
    )
    .await;
}

#[tokio::test]
async fn text_only_provider_response_still_parses() {
    let response = provider_success(json!([{
        "type": "text",
        "text": triage_output_text()
    }]));
    let (_fixture, _bearer, _provider, output, bearer_path, _arguments, process) =
        run_direct_response(200, response).await;
    assert!(
        process.status.success(),
        "{}",
        String::from_utf8_lossy(&process.stderr)
    );
    assert!(
        !bearer_path.exists(),
        "seat removes its bearer after success"
    );
    let persisted = fs::read_to_string(output).expect("triage output");
    TriageOutput::parse_json(&persisted).expect("valid text-only triage output");
}
