#!/usr/bin/env python3
"""Check the Anthropic requirement-1 issuance and delivery contract."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any
import types


CHECKER_RUNTIME_PATH = Path(__file__).with_name("factory_checker_runtime.py")
CHECKER_RUNTIME_SHA256 = "db4217cdd58d3dc8343f0ba2a9d1842eb07d6356d6aa430a2e3ff9b0be07e9fe"
_checker_runtime_source = CHECKER_RUNTIME_PATH.read_bytes()
if (
    CHECKER_RUNTIME_PATH.is_symlink()
    or hashlib.sha256(_checker_runtime_source).hexdigest()
    != CHECKER_RUNTIME_SHA256
):
    raise RuntimeError("factory checker runtime differs from its exact binding")
RUNTIME = types.ModuleType("factory_checker_runtime_check_anthropic_issuance")
RUNTIME.__file__ = str(CHECKER_RUNTIME_PATH)
RUNTIME.__package__ = None
exec(
    compile(
        _checker_runtime_source,
        str(CHECKER_RUNTIME_PATH),
        "exec",
        dont_inherit=True,
    ),
    RUNTIME.__dict__,
)


REPO = Path(__file__).resolve().parent.parent
POLICY_PATH = REPO / "policy" / "anthropic-wif.json"
RESULT_PATH = (
    REPO / "research" / "isolation" / "results" / "anthropic-issuance-delivery.json"
)
IMAGE_PATH = REPO / "worker" / "image"
PRODUCTION_PARITY_PATH = IMAGE_PATH / "production-parity.json"
HOST_CONTRACT_PATHS = (
    REPO / "worker" / "qualification" / "patchyard-run-anthropic-issuance",
    REPO / "worker" / "runtime" / "patchyard-firecracker-run",
)
ANTHROPIC_REQUEST = b"Anthropic issuance and delivery qualification.\n"
ANTHROPIC_PATCH = (
    b"diff --git a/anthropic-qualified.txt b/anthropic-qualified.txt\n"
    b"new file mode 100644\n"
    b"index 0000000000000000000000000000000000000000.."
    b"2f27dfcaa039397a95cb44d6e0fc4dcdb53e85cf\n"
    b"--- /dev/null\n"
    b"+++ b/anthropic-qualified.txt\n"
    b"@@ -0,0 +1 @@\n"
    b"+anthropic-issuance-delivery-qualified\n"
)
EXPECTED_ISSUANCE_PROVIDER_REQUEST_BLOCK = """  # ANTHROPIC_ISSUANCE_PROVIDER_REQUEST_BEGIN
  PROVIDER_STATUS=$(runuser -u factory-agent -- curl \\
    --config "$AUTH_CONFIG" --silent --show-error \\
    --connect-timeout 10 --max-time 30 \\
    --dump-header "$PROVIDER_HEADERS" \\
    --output "$PROVIDER_RESPONSE" --write-out '%{http_code}' \\
    'https://api.anthropic.com/v1/models?limit=1') || PROVIDER_CURL_EXIT=$?
  # ANTHROPIC_ISSUANCE_PROVIDER_REQUEST_END"""
EXPECTED_LOCAL_WEB_HEALTH_BLOCK = """APP_STATUS=$(curl --silent --output /run/fieldbook-index.html \\
  --write-out '%{http_code}' --max-time 20 http://127.0.0.1/index.php)"""
EXPECTED_LOCAL_PARITY_PROBE_BLOCK = """PROBE_BODY=$(curl --fail --silent --max-time 20 \\
  http://127.0.0.1/mfieldbook/patchyard_session4_probe.php)"""
PROVIDER_CAPABLE_COMMAND = re.compile(
    r"(?<![-A-Za-z0-9_.])(curl|wget|netcat|nc)(?=\s)|"
    r"/dev/(?:tcp|udp)|openssl\s+s_client"
)
# A142: "the guest image cannot spend" is re-proven against whatever programs the
# image carries, not inherited from the single runner that existed at
# qualification. Every shebang-bearing file in `worker/image/` is swept, so the
# provider-neutral guest dispatcher and spend runner are covered the moment they
# land - and fail closed until this file declares their provider calls as exact
# blocks, the same way the Anthropic runner's are declared above.
SWEPT_ELSEWHERE = {
    # Scanned immediately above, with the stricter exactly-one-call binding.
    "patchyard-guest-run",
}
GUEST_PROGRAM_EXEMPTIONS = {
    # Builds the image on the worker host; never executed inside the guest.
    "build-parity-image",
    # The egress control itself - its network calls are the proof instrument,
    # and it runs only under the hostile-probe qualification.
    "patchyard-hostile-probe",
}


def image_recipe_sha256() -> str:
    records = []
    for path in sorted(path for path in IMAGE_PATH.rglob("*") if path.is_file()):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        records.append(f"{digest}  {path.relative_to(IMAGE_PATH)}\n")
    return hashlib.sha256("".join(records).encode()).hexdigest()


def host_contract_sha256() -> str:
    records = []
    for path in HOST_CONTRACT_PATHS:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        records.append(f"{digest}  {path.relative_to(REPO)}\n")
    return hashlib.sha256("".join(records).encode()).hexdigest()


errors: list[str] = []
policy = json.loads(POLICY_PATH.read_text())
expected_policy = {
    "schema_version": 1,
    "provider": "anthropic",
    "organization": {
        "id": "aaadc747-869a-42d2-af51-58a5be8e3b7f",
        "name": "Example Company",
    },
    "workspace": {
        "id": "wrkspc_000000000000000000000000",
        "name": "Patchyard Factory",
    },
    "spend_enforcement": {
        "currency": "USD",
        "model": "claude-opus-5",
        "operational_cap_cents": 5000,
        "qualification_cap_cents": 100,
        "organization_monthly_limit_cents": 50000,
        "authorization_ruling": "A115",
        "minimum_settlement_window_seconds": 10260,
        "qualification_phases": [
            "operational_acceptance",
            "temporary_refusal",
            "restored_acceptance",
        ],
    },
    "service_account": {
        "id": policy.get("service_account", {}).get("id"),
        "name": "patchyard-worker",
        "description": (
            "Patchyard Factory short-lived inference bearer for isolated worker runs."
        ),
        "organization_role": "developer",
        "workspace_role": "workspace_restricted_developer",
    },
    "issuer": {
        "id": policy.get("issuer", {}).get("id"),
        "name": "patchyard-control-plane",
        "issuer_url": "https://factory.example.com/workload-identity",
        "check_jti": True,
        "max_jwt_lifetime_seconds": 300,
    },
    "rule": {
        "id": policy.get("rule", {}).get("id"),
        "name": "patchyard-inference",
        "description": (
            "Mint five-minute inference-only bearers for the Patchyard Factory worker."
        ),
        "subject": "patchyard-control-plane",
        "audience": "https://api.anthropic.com",
        "claims": {"factory_environment": "production"},
        "oauth_scope": "workspace:inference",
        "token_lifetime_seconds": 300,
    },
}
if policy != expected_policy:
    errors.append("Anthropic WIF policy differs from the reviewed exact binding")

for section, pattern in (
    ("service_account", r"svac_[A-Za-z0-9]+"),
    ("issuer", r"fdis_[A-Za-z0-9]+"),
    ("rule", r"fdrl_[A-Za-z0-9]+"),
):
    value = policy.get(section, {}).get("id")
    if value is not None and not re.fullmatch(pattern, value):
        errors.append(f"Anthropic {section} ID is malformed")

providers = json.loads((REPO / "policy" / "provider-egress.json").read_text())[
    "providers"
]
anthropic_egress = providers.get("anthropic")
if (
    not isinstance(anthropic_egress, dict)
    or set(anthropic_egress)
    != {"display_name", "hostnames", "credential_qualified"}
    or anthropic_egress.get("display_name") != "Anthropic"
    or anthropic_egress.get("hostnames") != ["api.anthropic.com"]
):
    errors.append("Anthropic egress policy entry changed")

runner = (
    REPO / "worker" / "qualification" / "patchyard-run-anthropic-issuance"
).read_text()
launcher = (REPO / "worker" / "runtime" / "patchyard-firecracker-run").read_text()
guest = (REPO / "worker" / "image" / "patchyard-guest-run").read_text()
control_tasks = (
    REPO / "infra" / "ansible" / "roles" / "control_plane" / "tasks" / "main.yml"
).read_text()
control_qualifier = (
    REPO
    / "infra"
    / "ansible"
    / "roles"
    / "control_plane"
    / "templates"
    / "qualify-factory-control.j2"
).read_text()
worker_tasks = (
    REPO / "infra" / "ansible" / "roles" / "worker" / "tasks" / "main.yml"
).read_text()
worker_qualifier = (
    REPO / "infra" / "ansible" / "roles" / "worker" / "files" / "qualify-factory-worker"
).read_text()

for required in (
    'openssl dgst -sha256 -sign "$SIGNING_KEY"',
    "https://api.anthropic.com/v1/oauth/token",
    "--connect-timeout 10 --max-time 30",
    "assertion.jwt",
    "capability.json",
    "SPEND_CAP_CENTS=0",
    "remote_ssh sudo /usr/local/sbin/patchyard-firecracker-run",
    "if remote_ssh sudo pgrep",
    "worker_links=$(remote_ssh sudo ip -o link show)",
    "worker_nft_tables=$(remote_ssh sudo nft list tables)",
    'grep -R -F -q -f "$ACCESS_TOKEN_NEEDLE" --',
    'grep -R -F -q -f "$RUN_TEMP/assertion.jwt" --',
    "stat -c '%U:%G:%a' \"$ACCESS_TOKEN_NEEDLE\"",
    "stat -c '%U:%G:%a' \"$RUN_TEMP/assertion.jwt\"",
    'mapfile -t WORKER_IP_LINES <"$WORKER_IP_FILE"',
    '[[ "${#WORKER_IP_LINES[@]}" -eq 1 ]]',
    'cmp --silent -- "$RUNNER_EXECUTABLE" "$EXPECTED_RUNNER_SOURCE"',
    '[[ "$LAUNCHER_SOURCE_SHA256" == "$EXPECTED_LAUNCHER_SHA256" ]]',
):
    if required not in runner:
        errors.append(f"control-plane issuance runner is missing: {required}")
if "{{" in runner or "RUNNER_TEMPLATE_LINE" in runner:
    errors.append(
        "control-plane issuance runner still normalizes executable template data"
    )
for forbidden in (
    'grep -R -F -q -- "$ACCESS_TOKEN"',
    'grep -R -F -q -- "$ASSERTION"',
    "ACCESS_TOKEN=",
):
    if forbidden in runner:
        errors.append(
            f"control-plane issuance runner exposes a credential in argv: {forbidden}"
        )

for required in (
    'dd if=/dev/stdin of="$CAPABILITY" bs=65536 count=1 iflag=fullblock',
    'mount --bind "$RUN_TMPFS/credential.ext4"',
    'drive_id:"credential"',
    "is_read_only:true",
    "remove_runtime() {\n  local -\n  set +e",
    "assert_runtime_removed",
    'grep -R -F -q -f "$CAPABILITY_NEEDLE" --',
    "stat -c '%U:%G:%a' \"$CAPABILITY_NEEDLE\"",
):
    if required not in launcher:
        errors.append(f"worker capability boundary is missing: {required}")
if "CAPABILITY_SECRET" in launcher:
    errors.append("worker capability boundary exposes a credential in argv")

for required in (
    'blockdev --getro "$CREDENTIAL_DEVICE"',
    "touch /credential/write-probe",
    "umount /credential",
    'header = "Authorization: Bearer %s"',
    "https://api.anthropic.com/v1/models?limit=1",
    'rm -f -- "$AUTH_CONFIG" "$CAPABILITY_FILE"',
    "assertion_delivered:false",
    "signing_key_delivered:false",
    "admin_credential_delivered:false",
):
    if required not in guest:
        errors.append(f"guest issuance fixture is missing: {required}")
provider_free_guest = guest
for label, request_block in (
    ("Anthropic issuance", EXPECTED_ISSUANCE_PROVIDER_REQUEST_BLOCK),
    ("loopback web health", EXPECTED_LOCAL_WEB_HEALTH_BLOCK),
    ("loopback parity probe", EXPECTED_LOCAL_PARITY_PROBE_BLOCK),
):
    if provider_free_guest.count(request_block) != 1:
        errors.append(f"{label} request differs from its exact one-call binding")
    else:
        provider_free_guest = provider_free_guest.replace(request_block, "", 1)
if PROVIDER_CAPABLE_COMMAND.search(provider_free_guest):
    errors.append("issuance guest contains a network-capable call outside exact blocks")
for path in sorted(path for path in IMAGE_PATH.iterdir() if path.is_file()):
    if path.name in SWEPT_ELSEWHERE or path.name in GUEST_PROGRAM_EXEMPTIONS:
        continue
    try:
        program = path.read_text()
    except UnicodeDecodeError:
        continue
    if not program.startswith("#!"):
        continue
    if PROVIDER_CAPABLE_COMMAND.search(program):
        errors.append(
            "guest image program has a network-capable call outside exact blocks: "
            f"{path.name}"
        )
credential_branch = guest.index('if [[ "$CREDENTIAL_DELIVERED_TO_GUEST" == true ]]')
provider_branch = guest.index(
    'if [[ "$MODE" == provider-qualification && "$PROVIDER" == anthropic ]]; then'
)
credential_unmount = guest.index("  umount /credential", credential_branch)
block_read_only = guest.index(
    'blockdev --getro "$CREDENTIAL_DEVICE"', credential_branch
)
credential_mount = guest.index("  mount -o ro,nosuid,nodev,noexec", credential_branch)
provider_call = guest.index(
    "https://api.anthropic.com/v1/models?limit=1", provider_branch
)
provider_output = guest.index("/result/change.patch", provider_branch)
mount_guard = guest.index("if mountpoint -q /credential", provider_branch)
if not (
    credential_branch
    < block_read_only
    < credential_mount
    < credential_unmount
    < provider_branch
    <= mount_guard
    < provider_call
    < provider_output
):
    errors.append("credential drive is not unmounted before the live provider proof")
teardown_branch = launcher.index("FAILURE_STAGE=teardown")
teardown_assertion = launcher.index("assert_runtime_removed", teardown_branch)
teardown_trap_clear = launcher.index("trap - EXIT", teardown_branch)
teardown_publish = launcher.index("FAILURE_STAGE=publish", teardown_branch)
if not teardown_branch < teardown_assertion < teardown_trap_clear < teardown_publish:
    errors.append("worker teardown can publish before residue assertions complete")

for required in (
    "rsa_keygen_bits:3072",
    "owner: root",
    'mode: "0400"',
    "/etc/tmpfiles.d/patchyard-anthropic.conf",
    "/etc/patchyard/anthropic-worker-ip",
    "/usr/local/sbin/patchyard-run-anthropic-issuance",
):
    if required not in control_tasks:
        errors.append(f"control-plane desired state is missing: {required}")
for required in (
    "anthropic-wif-signing.pem root root 400",
    "anthropic-worker-ip root root 400",
    "patchyard-run-anthropic-issuance jwks",
    'has("d") | not',
):
    if required not in control_qualifier:
        errors.append(f"control-plane qualifier is missing: {required}")
runner_install = control_tasks.split(
    "- name: Install the Anthropic issuance-and-delivery qualification runner", 1
)[1].split("\n- name:", 1)[0]
if (
    "ansible.builtin.copy" not in runner_install
    or "ansible.builtin.template" in runner_install
):
    errors.append("Anthropic issuance runner is not installed byte-for-byte")
if "anthropic-wif-signing.pem" in worker_tasks:
    errors.append("worker desired state references the control-plane signing key")
for required in (
    "test ! -e /etc/patchyard/anthropic-wif-signing.pem",
    "test ! -e /usr/local/sbin/patchyard-run-anthropic-issuance",
):
    if required not in worker_qualifier:
        errors.append(f"worker credential-absence qualifier is missing: {required}")


CHECKER = RUNTIME.checker_runtime(
    identity="Anthropic issuance checker",
    modules=(hashlib, json, re, types),
    repo=REPO,
    secret_names=frozenset({"secret", "access_token", "assertion", "identity_token", "authorization", "private_key"}),
)
secret_named_key = CHECKER.secret_named_key

allow_missing = "--allow-missing-results" in sys.argv[1:]
if not RESULT_PATH.exists():
    if not allow_missing:
        errors.append("committed live Anthropic issuance result is missing")
else:
    result = json.loads(RESULT_PATH.read_text())
    expected_keys = {
        "base_sha",
        "credential_removed_before_output",
        "delivery",
        "git_remote_count",
        "host_teardown",
        "host_contract_sha256",
        "image_recipe_sha256",
        "issuance",
        "observed_rootfs_sha256",
        "patch_sha256",
        "production_parity_sha256",
        "provider",
        "provider_call",
        "qualification_phase",
        "qualification_requirement",
        "request_sha256",
        "run_id",
        "schema_version",
    }
    if set(result) != expected_keys:
        errors.append("live result has an unexpected top-level evidence shape")
    for field in (
        "base_sha",
        "request_sha256",
        "patch_sha256",
        "observed_rootfs_sha256",
        "image_recipe_sha256",
        "production_parity_sha256",
        "host_contract_sha256",
    ):
        length = 40 if field == "base_sha" else 64
        if not re.fullmatch(rf"[0-9a-f]{{{length}}}", str(result.get(field, ""))):
            errors.append(f"live result {field} is malformed")
    expected_reproducible_bindings = {
        "request_sha256": hashlib.sha256(ANTHROPIC_REQUEST).hexdigest(),
        "patch_sha256": hashlib.sha256(ANTHROPIC_PATCH).hexdigest(),
        "production_parity_sha256": hashlib.sha256(
            PRODUCTION_PARITY_PATH.read_bytes()
        ).hexdigest(),
    }
    for field, expected in expected_reproducible_bindings.items():
        if result.get(field) != expected:
            errors.append(
                f"live result {field} differs from its reproducible fixture binding"
            )
    expected_image_recipe = image_recipe_sha256()
    if result.get("image_recipe_sha256") != expected_image_recipe:
        errors.append(
            "live result is stale for the current worker image recipe; "
            "rerun the Anthropic issuance fixture"
        )
    expected_host_contract = host_contract_sha256()
    if result.get("host_contract_sha256") != expected_host_contract:
        errors.append(
            "live result is stale for the current Anthropic host contract; "
            "rerun the Anthropic issuance fixture"
        )
    if result.get("schema_version") != 1:
        errors.append("live result schema version is not one")
    if result.get("provider") != "anthropic":
        errors.append("live result provider is not Anthropic")
    if result.get("qualification_requirement") != "issuance-delivery":
        errors.append("live result is not requirement 1")
    if result.get("qualification_phase") != "none":
        errors.append("live issuance result has an unexpected qualification phase")
    if result.get("git_remote_count") != 0:
        errors.append("live guest received a Git remote")
    if result.get("credential_removed_before_output") is not True:
        errors.append("live guest did not remove its bearer before output")
    if result.get("host_teardown") != {
        "processes": 0,
        "taps": 0,
        "nftables_tables": 0,
        "run_directories": 0,
        "credential_files": 0,
    }:
        errors.append("live result does not prove exact host teardown")

    issuance = result.get("issuance", {})
    if set(issuance) != {
        "exchange_request_id",
        "expires_at",
        "expires_in",
        "issued_at",
        "rule_id",
        "scope",
        "service_account_id",
        "token_type",
        "workspace_id",
    }:
        errors.append("live issuance evidence has an unexpected shape")
    try:
        issued = datetime.fromisoformat(issuance["issued_at"].replace("Z", "+00:00"))
        expires = datetime.fromisoformat(issuance["expires_at"].replace("Z", "+00:00"))
        expires_in = issuance["expires_in"]
        if not isinstance(expires_in, int) or not 60 <= expires_in <= 300:
            raise ValueError("invalid expiry")
        if int((expires - issued).total_seconds()) != expires_in:
            raise ValueError("expiry times differ from lifetime")
    except (KeyError, TypeError, ValueError):
        errors.append("live issuance times do not prove a one-to-five-minute bearer")
    if issuance.get("token_type") != "Bearer":
        errors.append("live issuance token type is not Bearer")
    if issuance.get("scope") != "workspace:inference":
        errors.append("live issuance scope is not inference-only")
    for field, section in (
        ("service_account_id", "service_account"),
        ("rule_id", "rule"),
        ("workspace_id", "workspace"),
    ):
        if issuance.get(field) != policy.get(section, {}).get("id"):
            errors.append(f"live issuance {field} differs from policy")
    if not re.fullmatch(
        r"req_[A-Za-z0-9]+", str(issuance.get("exchange_request_id", ""))
    ):
        errors.append("live exchange request ID is malformed")

    if result.get("delivery") != {
        "capability_drive_read_only": True,
        "capability_drive_unmounted_before_provider_call": True,
        "credential_removed_before_output": True,
        "assertion_delivered": False,
        "signing_key_delivered": False,
        "admin_credential_delivered": False,
    }:
        errors.append("live result does not prove the exact delivery boundary")
    provider_call = result.get("provider_call", {})
    if set(provider_call) != {"endpoint", "http_status", "model_id", "request_id"}:
        errors.append("live provider-call evidence has an unexpected shape")
    if provider_call.get("endpoint") != "/v1/models?limit=1":
        errors.append("live proof used an unexpected provider endpoint")
    if provider_call.get("http_status") != 200:
        errors.append("live provider proof was not accepted")
    if not re.fullmatch(r"req_[A-Za-z0-9]+", str(provider_call.get("request_id", ""))):
        errors.append("live provider request ID is malformed")
    if (
        not isinstance(provider_call.get("model_id"), str)
        or not provider_call["model_id"]
    ):
        errors.append("live Models response did not identify a model")

    forbidden_key = secret_named_key(result)
    if forbidden_key:
        errors.append(f"committed evidence contains forbidden key: {forbidden_key}")
    serialized = json.dumps(result, sort_keys=True)
    if re.search(r"sk-ant-[A-Za-z0-9_-]+", serialized):
        errors.append("committed evidence contains an Anthropic credential")
    if re.search(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", serialized):
        errors.append("committed evidence contains a JWT assertion")

if errors:
    print("Anthropic issuance check: failed", file=sys.stderr)
    for error in errors:
        print(f"  {error}", file=sys.stderr)
    raise SystemExit(1)

result_status = "with live result" if RESULT_PATH.exists() else "static preflight"
print(f"Anthropic issuance check: pass ({result_status})")
