#!/usr/bin/env python3
"""Check the Anthropic A-5 requirement-2 A115/A120/A121/A122 contract."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import sys
import sysconfig
from typing import Any


REPO = Path(__file__).resolve().parent.parent
POLICY_PATH = REPO / "policy" / "anthropic-wif.json"
RESULT_PATH = REPO / "research/isolation/results/anthropic-spend-enforcement.json"
INITIAL_FAILURE_PATH = (
    REPO / "research/isolation/results/anthropic-spend-enforcement-initial-failure.json"
)
REPAIR_FAILURE_PATH = (
    REPO / "research/isolation/results/anthropic-spend-enforcement-repair-failure.json"
)
IMAGE_PATH = REPO / "worker/image"
PRODUCTION_PARITY_PATH = IMAGE_PATH / "production-parity.json"
RUNNER_PATH = REPO / "worker/qualification/patchyard-run-anthropic-issuance"
LAUNCHER_PATH = REPO / "worker/runtime/patchyard-firecracker-run"
TRANSPORT_PATH = REPO / "worker/runtime/patchyard-anthropic-one-shot"
GUEST_PATH = REPO / "worker/image/patchyard-guest-run"
EVIDENCE_PATH = REPO / "tools/anthropic-spend-evidence.py"
PROCEDURE_PATH = REPO / "docs/anthropic-spend-enforcement.md"
WORKER_TASKS_PATH = REPO / "infra/ansible/roles/worker/tasks/main.yml"
READINESS_HELPER_PATH = REPO / "infra/wait-do-worker-firewall.sh"
REPLACEMENT_OPERATOR_PATH = REPO / "infra/replace-worker.sh"
ANSIBLE_WRAPPER_PATH = REPO / "tools/check-ansible.sh"
READINESS_TEST_PATH = REPO / "infra/ansible/tests/test_worker_firewall_readiness.py"
ANTHROPIC_REQUEST = b"Anthropic provider-side spend enforcement qualification.\n"
ANTHROPIC_PATCH = (
    b"diff --git a/anthropic-spend-qualified.txt b/anthropic-spend-qualified.txt\n"
    b"new file mode 100644\n"
    b"index 0000000000000000000000000000000000000000.."
    b"ce4003a0cb322c6b51e33bc82833fe87d9303b71\n"
    b"--- /dev/null\n"
    b"+++ b/anthropic-spend-qualified.txt\n"
    b"@@ -0,0 +1 @@\n"
    b"+anthropic-provider-spend-enforcement-qualified\n"
)
CALIBRATION_ITEM_COUNT = 16_000
CALIBRATION_COPIES = 2
HISTORICAL_UNCACHED_INPUT_TOKENS_PER_BODY = 192_037
PRECOMPUTED_UNCACHED_INPUT_TOKENS = (
    HISTORICAL_UNCACHED_INPUT_TOKENS_PER_BODY * CALIBRATION_COPIES
)
MINIMUM_UNCACHED_INPUT_TOKENS = 300_000
A119_INPUT_USD_PER_MILLION_TOKENS = Decimal("5")
MINIMUM_UNCACHED_INPUT_COST_USD = (
    Decimal(MINIMUM_UNCACHED_INPUT_TOKENS)
    * A119_INPUT_USD_PER_MILLION_TOKENS
    / Decimal(1_000_000)
)
A121_LEGACY_PRE_ACTIVATION_UTC_DAY = "2026-08-02"
A121_LEGACY_PRE_ACTIVATION_COST_USD = Decimal("3.84074")
CALIBRATION_PROMPT = (
    "Synthetic Patchyard Factory provider spend-enforcement input.\n"
    + "".join(
        f"patchyard-spend-{index:06d} "
        for index in range(CALIBRATION_ITEM_COUNT)
    )
    + "\nReply with one character.\n"
)
ANTHROPIC_PROVIDER_BODY = (
    json.dumps(
        {
            "model": "claude-opus-5",
            "max_tokens": 1,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": CALIBRATION_PROMPT}
                        for _ in range(CALIBRATION_COPIES)
                    ],
                }
            ],
        },
        separators=(",", ":"),
    ).encode()
    + b"\n"
)
EXPECTED_CALIBRATION_PROMPT_SHA256 = (
    "9a7a2d6d96cb17ddb78331fcc2a9ee5475310a65e9dc906c2db1548ac1154c21"
)
EXPECTED_PROVIDER_BODY_SHA256 = (
    "b3751a164cde71cbca2fe5de05d3fc8a836649e46114c616cdaf4a210bdfccf4"
)
EXPECTED_AUTH_CONFIG_BLOCK = '''{
  printf 'header = "Authorization: Bearer %s"\\n' "$(jq -r .secret "$CAPABILITY")"
  printf 'header = "anthropic-version: 2023-06-01"\\n'
  printf 'header = "content-type: application/json"\\n'
} >"$AUTH_CONFIG"'''
EXPECTED_LAUNCHER_SOURCE_SHA256 = (
    "60b71fb24ce3c47b9b62bdece7166dd0c622a1830fb21d673db8830acf133e3f"
)
EXPECTED_RUNNER_SOURCE_SHA256 = (
    "91c3fdc09b34d009a02e4f8d1290976c558b0a654e89171dcaa5b3fd037a7608"
)
EXPECTED_TRANSPORT_SOURCE_SHA256 = (
    "41a5416acb2df277f7268d24f51fc4569b539ffe408df73ad6c6468bdb7bcd36"
)
EXPECTED_GUEST_SOURCE_SHA256 = (
    "229346fb350297b298c1b752188c0f7762ef9d5de77572156843070fecfcc654"
)
EXPECTED_WORKER_TASKS_SOURCE_SHA256 = (
    "110cbffc6db188aafa1364e88901249290653134b7f0adc559152abf3f35df40"
)
EXPECTED_READINESS_HELPER_SOURCE_SHA256 = (
    "5aa2f71ce014671de08104356d77a5ff210efd56525e7c1ddf85f46770336cba"
)
EXPECTED_REPLACEMENT_OPERATOR_SOURCE_SHA256 = (
    "27f322afc3c3c8d813f18a5003f2e2fdc2c6d75d24b28ed0c19ad215e9ad580e"
)
EXPECTED_ANSIBLE_WRAPPER_SOURCE_SHA256 = (
    "309e411f2e81b93c3d74a35a4fd03f475d045d2d25bae1048f7f14480c812eca"
)
EXPECTED_READINESS_TEST_SOURCE_SHA256 = (
    "8c5ac7c98d947c3ecf56f3e1f4b8ef5d6ec429f7d1fbb384e5d13630df24895c"
)
EXPECTED_EVIDENCE_SOURCE_SHA256 = (
    "000f2f5fcfdb5822396d7885e6a4aba82d3ad475e017fd5c032b1dc5a4710b51"
)
EXPECTED_PROVIDER_CALL_SEQUENCE = '''  setup_provider_transport
  assert_provider_transport_preflight
  "$ANTHROPIC_ONE_SHOT" "$PROVIDER_NETNS" "$CAPABILITY" "$PROVIDER_STAGE"'''
EXPECTED_RUN_ROOT_STAGING = '''if $SPEND_MODE; then
  # The one-shot request runs as factory-worker. Grant that identity traversal of
  # this exact run root without directory read or write access; the capability
  # itself remains root:root 0600 and the worker-owned raw directory is 0700.
  install -d -m 0710 -o root -g factory-worker "$RUN_TMPFS"
  [[ "$(stat -c '%U:%G:%a' -- "$RUN_TMPFS")" == root:factory-worker:710 ]]
  /usr/sbin/runuser -u factory-worker -- /usr/bin/test -x "$RUN_TMPFS"
else
  install -d -m 0700 -o root -g root "$RUN_TMPFS"
  [[ "$(stat -c '%U:%G:%a' -- "$RUN_TMPFS")" == root:root:700 ]]
fi'''
EXPECTED_IPV6_PREFLIGHT_COMPARISON = (
    'if [[ "$ipv6_all" != 1 || "$ipv6_default" != 1 || "$ipv6_eth0" != 1 ]]; then'
)
EXPECTED_A120_FLOOR_FUNCTION = '''anthropic_acceptance_meets_a120_floor() {
  jq -e --argjson floor "$MINIMUM_UNCACHED_INPUT_TOKENS" '
    .usage.input_tokens >= $floor
    and .usage.cache_creation_input_tokens == 0
    and .usage.cache_read_input_tokens == 0
  ' "$PROVIDER_RESPONSE" >/dev/null
}'''
EXPECTED_A120_ACCEPTANCE_GUARD = '''  if ! anthropic_acceptance_meets_a120_floor; then
    echo 'anthropic-spend-provider-response-rejected-200-cached-or-below-cost-floor' >&2
    exit 1
  fi'''
EXPECTED_A120_QUALIFIED_NEGATIVE_STOP = '''  if [[ "$QUALIFICATION_PHASE" == temporary_refusal ]]; then
    echo 'anthropic-spend-provider-response-rejected-200-provider-accepted-workspace-scope-qualified-negative' >&2
    exit 1
  fi'''
EXPECTED_PRE_ACTIVATION_SETTLEMENT_GUARD = '''    if pre_activation_settlement_window < minimum_window:
        raise ValueError("pre-activation cost has not completed the settlement window")'''
EXPECTED_POST_REFUSAL_SETTLEMENT_GUARD = '''    if settlement_window < minimum_window:
        raise ValueError("post-refusal cost has not completed the settlement window")'''
EXPECTED_PRE_ACTIVATION_DAY_CLOSE_GUARD = '''    if not utc_day_closed(observed["operational_acceptance"], before_time):
        raise ValueError(
            "pre-activation snapshot was captured before the request UTC day closed"
        )'''
EXPECTED_POST_REFUSAL_DAY_CLOSE_GUARD = '''    if not utc_day_closed(observed["temporary_refusal"], after_time):
        raise ValueError(
            "post-refusal snapshot was captured before the request UTC day closed"
        )'''
EXPECTED_NO_WORKSPACE_ROWS_GUARD = '''    if not matched_workspace:
        raise ValueError("Anthropic Cost Report returned no Factory workspace row")'''
EXPECTED_PRE_ACTIVATION_ROW_GUARD = '''    elif pre_activation_utc_day not in before_workspace_days:
        raise ValueError(
            "pre-activation Cost Report lacks the Factory row for the request UTC day"
        )'''
EXPECTED_POST_REFUSAL_COVERAGE_GUARD = '''    if after_complete_days is None or post_refusal_utc_day not in after_complete_days:
        raise ValueError(
            "post-refusal Cost Report does not completely cover the request UTC day"
        )'''
EXPECTED_COST_REPORT_PAGINATION_GUARD = '''        page = payload.get("next_page")
        if not payload.get("has_more"):
            break
        if not isinstance(page, str) or not page:
            raise ValueError("Anthropic cost report pagination is malformed")'''
EXPECTED_FIRST_ACCEPTANCE_STOP_TEXT = (
    "If the settled amount is $1.00 or less, stop. A second or larger acceptance "
    "is not authorized."
)
EXPECTED_QUALIFIED_NEGATIVE_STOP_TEXT = (
    "This is a qualified negative for workspace-scope enforcement: stop without "
    "the restored provider request or any repair request"
)
EXPECTED_POST_REFUSAL_COVERAGE_TEXT = (
    "A row for that day is optional; a no-row day is zero only when it is closed "
    "and named in `complete_utc_days`."
)
PHASES = (
    "operational_acceptance",
    "temporary_refusal",
    "restored_acceptance",
)


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def isolation_errors() -> list[str]:
    errors: list[str] = []
    if not sys.flags.isolated:
        errors.append("Anthropic spend checker requires python3 -I")

    stdlib = Path(sysconfig.get_path("stdlib")).resolve()
    for module in (hashlib, json, re, sysconfig):
        source = getattr(module, "__file__", None)
        if source is None or not is_within(Path(source).resolve(), stdlib):
            errors.append(
                f"Anthropic spend checker rejected {module.__name__} provenance: "
                f"{source!r}"
            )

    for entry in sys.path:
        try:
            resolved = Path(entry).resolve()
        except OSError:
            continue
        if is_within(resolved, REPO):
            errors.append(f"Anthropic spend checker has repository import path: {entry}")
    return errors


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def image_recipe_sha256() -> str:
    records = []
    for path in sorted(path for path in IMAGE_PATH.rglob("*") if path.is_file()):
        records.append(f"{digest(path)}  {path.relative_to(IMAGE_PATH)}\n")
    return hashlib.sha256("".join(records).encode()).hexdigest()


def host_contract_sha256() -> str:
    records = [
        f"{digest(path)}  {path.relative_to(REPO)}\n"
        for path in (RUNNER_PATH, LAUNCHER_PATH, TRANSPORT_PATH)
    ]
    return hashlib.sha256("".join(records).encode()).hexdigest()


def parse_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp is not a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp has no timezone")
    return parsed


def utc_day(value: datetime) -> str:
    return value.astimezone(timezone.utc).date().isoformat()


def utc_day_closed(request_at: datetime, captured_at: datetime) -> bool:
    return utc_day(captured_at) > utc_day(request_at)


def decimal_value(value: Any) -> Decimal:
    if not isinstance(value, str):
        raise ValueError("decimal figure is not a string")
    number = Decimal(value)
    if not number.is_finite():
        raise ValueError("decimal figure is not finite")
    return number


def secret_named_key(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"secret", "access_token", "assertion", "identity_token"}:
                return key
            found = secret_named_key(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = secret_named_key(child)
            if found:
                return found
    return None


def contains_forbidden_ceiling(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            "ceiling" in key
            or "max_overshoot" in key
            or contains_forbidden_ceiling(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(contains_forbidden_ceiling(child) for child in value)
    return False


errors: list[str] = isolation_errors()
policy = json.loads(POLICY_PATH.read_text())
expected_spend_policy = {
    "currency": "USD",
    "model": "claude-opus-5",
    "operational_cap_cents": 5000,
    "qualification_cap_cents": 100,
    "organization_monthly_limit_cents": 50000,
    "authorization_ruling": "A115",
    "minimum_settlement_window_seconds": 10260,
    "qualification_phases": list(PHASES),
}
if policy.get("spend_enforcement") != expected_spend_policy:
    errors.append("Anthropic spend policy differs from the exact A115 binding")
organization_id = "aaadc747-869a-42d2-af51-58a5be8e3b7f"
workspace_id = "wrkspc_000000000000000000000000"
service_account_id = "svac_01BqCdjSqFsWTvfDyCucThZy"
if policy.get("organization", {}).get("id") != organization_id:
    errors.append("Anthropic organization differs from the reviewed binding")
if policy.get("workspace") != {"id": workspace_id, "name": "Patchyard Factory"}:
    errors.append("Anthropic Factory workspace differs from the reviewed binding")
if policy.get("service_account", {}).get("id") != service_account_id:
    errors.append("Anthropic Factory principal differs from the reviewed binding")

providers = json.loads((REPO / "policy/provider-egress.json").read_text())["providers"]
if len(providers) != 13 or any(
    item.get("credential_qualified") is not False for item in providers.values()
):
    errors.append("all 13 provider credential qualification flags must remain false")

# A117 source bindings. Request cardinality comes from the host namespace's
# admitted conntrack ID and independently read counters. Source checks bind the
# small trusted client and keep the general-purpose guest outside that transport.
runner = RUNNER_PATH.read_text()
launcher = LAUNCHER_PATH.read_text()
transport = TRANSPORT_PATH.read_text()
guest = GUEST_PATH.read_text()
evidence_source = EVIDENCE_PATH.read_text()
procedure = PROCEDURE_PATH.read_text()
normalized_procedure = " ".join(procedure.split())
worker_tasks = WORKER_TASKS_PATH.read_text()
if digest(RUNNER_PATH) != EXPECTED_RUNNER_SOURCE_SHA256:
    errors.append("post-A118 issuance runner differs from its complete source binding")
if digest(TRANSPORT_PATH) != EXPECTED_TRANSPORT_SOURCE_SHA256:
    errors.append("A120 one-shot transport differs from its complete source binding")
if digest(LAUNCHER_PATH) != EXPECTED_LAUNCHER_SOURCE_SHA256:
    errors.append("post-A118 launcher differs from its complete source binding")
if digest(GUEST_PATH) != EXPECTED_GUEST_SOURCE_SHA256:
    errors.append("post-A118 spend guest differs from its complete source binding")
if digest(WORKER_TASKS_PATH) != EXPECTED_WORKER_TASKS_SOURCE_SHA256:
    errors.append("post-A118 worker install tasks differ from their complete source binding")
if digest(READINESS_HELPER_PATH) != EXPECTED_READINESS_HELPER_SOURCE_SHA256:
    errors.append("A101 firewall readiness helper differs from its complete source binding")
if digest(REPLACEMENT_OPERATOR_PATH) != EXPECTED_REPLACEMENT_OPERATOR_SOURCE_SHA256:
    errors.append("A101 worker replacement operator differs from its complete source binding")
if digest(ANSIBLE_WRAPPER_PATH) != EXPECTED_ANSIBLE_WRAPPER_SOURCE_SHA256:
    errors.append("A101 Ansible wrapper differs from its complete source binding")
if digest(READINESS_TEST_PATH) != EXPECTED_READINESS_TEST_SOURCE_SHA256:
    errors.append("A101 readiness test census differs from its complete source binding")
if digest(EVIDENCE_PATH) != EXPECTED_EVIDENCE_SOURCE_SHA256:
    errors.append("A122 evidence finalizer differs from its complete source binding")

if hashlib.sha256(CALIBRATION_PROMPT.encode()).hexdigest() != (
    EXPECTED_CALIBRATION_PROMPT_SHA256
):
    errors.append("A120 calibration prompt differs from its reviewed byte binding")
if hashlib.sha256(ANTHROPIC_PROVIDER_BODY).hexdigest() != EXPECTED_PROVIDER_BODY_SHA256:
    errors.append("A120 provider body differs from its reviewed byte binding")
if PRECOMPUTED_UNCACHED_INPUT_TOKENS != 384_074:
    errors.append("A120 historical tokenization precomputation differs from its binding")
if (
    MINIMUM_UNCACHED_INPUT_TOKENS != 300_000
    or MINIMUM_UNCACHED_INPUT_TOKENS >= PRECOMPUTED_UNCACHED_INPUT_TOKENS
    or MINIMUM_UNCACHED_INPUT_TOKENS <= 200_000
    or MINIMUM_UNCACHED_INPUT_COST_USD != Decimal("1.5")
):
    errors.append("A120 conservative uncached-input cost floor is not above $1.00")
for required in (
    f"readonly PROMPT_CALIBRATION_ITEMS={CALIBRATION_ITEM_COUNT}",
    f"readonly PROMPT_CALIBRATION_COPIES={CALIBRATION_COPIES}",
    f"readonly MINIMUM_UNCACHED_INPUT_TOKENS={MINIMUM_UNCACHED_INPUT_TOKENS}",
    f"readonly EXPECTED_PROMPT_SHA256={EXPECTED_CALIBRATION_PROMPT_SHA256}",
    f"readonly EXPECTED_PROVIDER_REQUEST_SHA256={EXPECTED_PROVIDER_BODY_SHA256}",
):
    if transport.count(required) != 1:
        errors.append("A120 request body falls below or differs from the cost-floor binding")
if transport.count(EXPECTED_A120_FLOOR_FUNCTION) != 1:
    errors.append("A120 uncached-input floor predicate differs from its binding")
if transport.count(EXPECTED_A120_ACCEPTANCE_GUARD) != 1:
    errors.append("A120 uncached-input acceptance guard is missing")
if transport.count(EXPECTED_A120_QUALIFIED_NEGATIVE_STOP) != 1:
    errors.append("A120 provider-acceptance qualified-negative stop is missing")
elif (
    transport.count(EXPECTED_A120_ACCEPTANCE_GUARD) == 1
    and transport.index(EXPECTED_A120_QUALIFIED_NEGATIVE_STOP)
    > transport.index(EXPECTED_A120_ACCEPTANCE_GUARD)
):
    errors.append(
        "A120 provider acceptance can be misclassified before the qualified-negative stop"
    )
if evidence_source.count(EXPECTED_PRE_ACTIVATION_SETTLEMENT_GUARD) != 1:
    errors.append("A120 pre-activation settlement floor guard is missing")
if evidence_source.count(EXPECTED_POST_REFUSAL_SETTLEMENT_GUARD) != 1:
    errors.append("A120 post-refusal settlement floor guard is missing")
if evidence_source.count(EXPECTED_PRE_ACTIVATION_DAY_CLOSE_GUARD) != 1:
    errors.append("A121 pre-activation UTC-day-close guard is missing")
if evidence_source.count(EXPECTED_POST_REFUSAL_DAY_CLOSE_GUARD) != 1:
    errors.append("A121 post-refusal UTC-day-close guard is missing")
if evidence_source.count(EXPECTED_NO_WORKSPACE_ROWS_GUARD) != 1:
    errors.append("A122 snapshot no-rows fail-closed guard is missing")
if evidence_source.count(EXPECTED_PRE_ACTIVATION_ROW_GUARD) != 1:
    errors.append("A122 pre-activation Factory-row guard is missing")
if evidence_source.count(EXPECTED_POST_REFUSAL_COVERAGE_GUARD) != 1:
    errors.append("A122 post-refusal complete-day guard is missing")
if (
    evidence_source.count("COST_REPORT_DAILY_LIMIT = 31") != 1
    or evidence_source.count('"limit": COST_REPORT_DAILY_LIMIT') != 1
    or evidence_source.count(EXPECTED_COST_REPORT_PAGINATION_GUARD) != 1
):
    errors.append("A121 Cost Report query can silently truncate daily buckets")
if EXPECTED_FIRST_ACCEPTANCE_STOP_TEXT not in normalized_procedure:
    errors.append("A120 first-acceptance settled-cost stop is missing from the procedure")
if EXPECTED_QUALIFIED_NEGATIVE_STOP_TEXT not in normalized_procedure:
    errors.append("A120 qualified-negative stop is missing from the procedure")
if EXPECTED_POST_REFUSAL_COVERAGE_TEXT not in normalized_procedure:
    errors.append("A122 post-refusal complete-day procedure is missing")
for installed_path, label in (
    ("dest: /usr/local/sbin/patchyard-firecracker-run", "launcher"),
    ("dest: /usr/local/libexec/patchyard-anthropic-one-shot", "one-shot"),
):
    if worker_tasks.count(installed_path) != 1:
        errors.append(f"post-A118 installed {label} path is not singular")
if launcher.count(EXPECTED_PROVIDER_CALL_SEQUENCE) != 1:
    errors.append("post-A118 setup, preflight, and transfer are not exactly adjacent")
if launcher.count(EXPECTED_RUN_ROOT_STAGING) != 1:
    errors.append("A115 spend run-root traversal differs from its exact binding")
else:
    try:
        runtime_staging_index = launcher.index('FAILURE_STAGE=runtime-staging')
        result_extract_index = launcher.index(
            'install -d -m 0700 -o factory-worker -g factory-worker "$RESULT_EXTRACT"'
        )
        capability_index = launcher.index('CAPABILITY="$RUN_TMPFS/capability.json"')
    except ValueError:
        errors.append("A115 spend run-root traversal is outside runtime staging")
    else:
        staging_index = launcher.index(EXPECTED_RUN_ROOT_STAGING)
        if not (
            runtime_staging_index < staging_index < result_extract_index < capability_index
        ):
            errors.append("A115 spend run-root traversal is outside runtime staging")
if launcher.count(EXPECTED_IPV6_PREFLIGHT_COMPARISON) != 1:
    errors.append("post-A118 exact IPv6 preflight comparison differs from its binding")

transfer_start = "PROVIDER_STATUS=$(\n"
transfer_end = "\n) || PROVIDER_CURL_EXIT=$?"
if transfer_start not in transport or transfer_end not in transport:
    errors.append("A117 one-shot client has no bounded transfer block")
    transfer = ""
else:
    transfer = transport.split(transfer_start, 1)[1].split(transfer_end, 1)[0]
    if transport.count(transfer_start) != 1 or transport.count(transfer_end) != 1:
        errors.append("A117 one-shot client has more than one transfer block")

for required in (
    "/usr/bin/curl -q",
    "/usr/bin/env -i HOME=/var/lib/patchyard-worker PATH=/usr/bin:/bin",
    "--http1.0",
    "--header 'Connection: close'",
    "--ipv4",
    "--proto '=https'",
    "--connect-timeout 10 --max-time 60",
    '--data-binary "@$PROVIDER_REQUEST"',
    "'https://api.anthropic.com/v1/messages'",
):
    if required not in transfer:
        errors.append(f"A117 one-shot transfer is missing: {required}")
for forbidden in (
    "--retry",
    "--retry-all-errors",
    "--location",
    "--next",
    "--parallel",
    "--http0.9",
    "--http1.1",
    "--http2",
    "--http3",
    "http://",
):
    if forbidden in transfer:
        errors.append(f"A117 one-shot transfer permits another transfer: {forbidden}")
if transfer.count("/usr/bin/curl") != 1 or transfer.count(
    "'https://api.anthropic.com/v1/messages'"
) != 1:
    errors.append("A117 one-shot transfer does not contain exactly one fixed client and URL")
if transfer.count('--config "$AUTH_CONFIG"') != 1:
    errors.append("A118 one-shot transfer does not load exactly one bound config")
if transport.count(EXPECTED_AUTH_CONFIG_BLOCK) != 1:
    errors.append("A118 curl configuration is not the exact header-only generator")
if transport.count('"$AUTH_CONFIG"') != 4:
    errors.append("A118 curl configuration has another read or write path")
if transport.count("anthropic-curl.conf") != 1:
    errors.append("A118 curl configuration path is not singular")

transport_without_transfer = transport.replace(
    transfer_start + transfer + transfer_end, "", 1
)
if re.search(
    r"(?<![-A-Za-z0-9_.])(curl|wget|php|python[0-9]*|perl|ruby|nc|netcat|socat)"
    r"(?=\s)|/dev/(tcp|udp)|openssl\s+s_client",
    transport_without_transfer,
):
    errors.append("A117 trusted transport contains another network-capable client")
if transport.count("https://api.anthropic.com/v1/messages") != 1:
    errors.append("A117 trusted transport contains another Messages destination")
for required in (
    '/usr/bin/awk -v items="$PROMPT_CALIBRATION_ITEMS"',
    'for (i = 0; i < items; i++) printf "patchyard-spend-%06d ", i',
    'jq -cn --rawfile prompt "$PROMPT_TEXT"',
    "[range(0; $copies) | {type:\"text\",text:$prompt}]",
    '== "$EXPECTED_PROMPT_SHA256"',
    '== "$EXPECTED_PROVIDER_REQUEST_SHA256"',
    "anthropic_response_is_single_json_object",
    "classify_anthropic_error_shape",
    "anthropic_error_envelope_is_compatible",
    'if [[ ! "$PROVIDER_REQUEST_ID" =~ ^req_[A-Za-z0-9]+$ ]]',
    "anthropic-spend-provider-response-rejected-%s-missing-request-id-%s",
    'rm -f -- "$CAPABILITY"',
):
    if required not in transport:
        errors.append(f"A117 trusted transport is missing: {required}")
if b"cache_control" in ANTHROPIC_PROVIDER_BODY:
    errors.append("A120 request body enables prompt caching")

if "https://api.anthropic.com/v1/messages" in guest:
    errors.append("A117 spend guest still contains the provider destination")
for required in (
    "CREDENTIAL_DELIVERED_TO_GUEST=false",
    '[[ ! -e /dev/disk/by-label/ETA_CREDENTIAL ]]',
    '[[ ! -s /input/provider-hosts ]]',
    'credential_delivered_to_guest:false',
    'guest_provider_allowlist_entries == 0',
    'admitted_new_connections == 1',
    'rejected_new_connections == 0',
    'rejected_connection_packets == 0',
    'namespace_ipv6_disabled == true',
):
    if required not in guest:
        errors.append(f"A117 credential-free guest is missing: {required}")

for required in (
    'ANTHROPIC_ONE_SHOT=/usr/local/libexec/patchyard-anthropic-one-shot',
    '"$ANTHROPIC_ONE_SHOT" "$PROVIDER_NETNS" "$CAPABILITY" "$PROVIDER_STAGE"',
    "ct id @admitted counter accept",
    "ip saddr @used add @rejected { ct id } counter name rejected_new reject",
    "add @admitted '{' ct id '}'",
    "add @used '{' ip saddr '}' counter name admitted_new accept",
    "PROVIDER_ADMITTED_NEW=$(provider_counter_packets admitted_new)",
    "PROVIDER_REJECTED_NEW=$(provider_counter_packets rejected_new)",
    '"$PROVIDER_ADMITTED_NEW" -eq 1',
    '"$PROVIDER_REJECTED_NEW" -eq 0',
    '"$PROVIDER_ADMITTED_IDS" -eq 1',
    '"$PROVIDER_REJECTED_IDS" -eq 0',
    '"$PROVIDER_USED_SOURCES" -eq 1',
    '[[ "$GUEST_REJECTED_EGRESS_PACKETS" -eq 0 ]]',
    'if [[ "$CREDENTIAL_REQUIRED" == true ]] && ! $SPEND_MODE; then',
    'PROVIDER_TRANSPORT_IP=$address',
    'net.ipv6.conf.all.disable_ipv6=1',
    'net.ipv6.conf.default.disable_ipv6=1',
    'net.ipv6.conf.eth0.disable_ipv6)',
    'assert_provider_transport_preflight',
    'anthropic-spend-provider-transport-preflight-rejected-ipv6',
    'anthropic-spend-transport-cardinality-rejected-%s-%s-%s-%s-%s',
    'namespace_ipv6_disabled:true',
):
    if required not in launcher:
        errors.append(f"A117 host cardinality boundary is missing: {required}")
if launcher.count(
    '"$ANTHROPIC_ONE_SHOT" "$PROVIDER_NETNS" "$CAPABILITY" "$PROVIDER_STAGE"'
) != 1:
    errors.append("A117 launcher does not invoke the one-shot client exactly once")
if launcher.count(
    'if [[ "$CREDENTIAL_REQUIRED" == true ]] && ! $SPEND_MODE; then'
) != 2:
    errors.append("A117 launcher can still project a spend credential drive")
try:
    ipv6_all_write = launcher.index("net.ipv6.conf.all.disable_ipv6=1")
    ipv6_default_write = launcher.index("net.ipv6.conf.default.disable_ipv6=1")
    provider_veth_create = launcher.index(
        'ip link add "$PROVIDER_HOST_VETH" type veth peer name "$PROVIDER_NS_VETH"'
    )
    provider_preflight = launcher.index(
        "  assert_provider_transport_preflight\n",
        launcher.index("if $SPEND_MODE; then"),
    )
    provider_call = launcher.index(
        '  "$ANTHROPIC_ONE_SHOT" "$PROVIDER_NETNS" "$CAPABILITY" "$PROVIDER_STAGE"'
    )
    if not (
        ipv6_all_write
        < provider_veth_create
        and ipv6_default_write < provider_veth_create
        and provider_preflight < provider_call
    ):
        errors.append("A118 IPv6 disable/readback does not precede the paid transfer")
except ValueError:
    errors.append("A118 IPv6 disable/readback ordering is incomplete")
if re.search(
    r"(?<![-A-Za-z0-9_.])(curl|wget|php|python[0-9]*|perl|ruby|nc|netcat|socat)"
    r"(?=\s)|/dev/(tcp|udp)|openssl\s+s_client",
    launcher,
):
    errors.append("A117 launcher contains a second provider-capable client")

for required in (
    "worker/runtime/patchyard-anthropic-one-shot",
    "dest: /usr/local/libexec/patchyard-anthropic-one-shot",
):
    if required not in worker_tasks:
        errors.append(f"A117 installed transport binding is missing: {required}")
if "patchyard-anthropic-one-shot" in (
    REPO / "worker/image/build-parity-image"
).read_text():
    errors.append("A117 one-shot client was installed into the general-purpose guest")

for required in (
    "EXPECTED_TRANSPORT_SOURCE",
    "EXPECTED_TRANSPORT_SHA256",
    "TRANSPORT_SOURCE_SHA256",
    "worker/runtime/patchyard-anthropic-one-shot",
    "transport-cardinality-rejected-([0-9]{1,20}-){4}[0-9]{1,20}",
    "efh[0-9a-f]{8}[@:]",
):
    if required not in runner:
        errors.append(f"A117 host-contract binding is missing: {required}")

for source in (runner, launcher, transport, guest):
    if "overshoot_ceiling" in source or "max_overshoot" in source:
        errors.append("source encodes a forbidden preset overshoot ceiling")

# The two failed July attempts are permanent history, not mutually exclusive
# with a future A115 success.
try:
    initial = json.loads(INITIAL_FAILURE_PATH.read_text())
except FileNotFoundError:
    errors.append("initial July failure record is missing")
    initial = {}
if set(initial) != {
    "schema_version",
    "provider",
    "qualification_requirement",
    "outcome",
    "workspace_id",
    "service_account_id",
    "cap_control",
    "fixture",
    "usage_measurement",
    "cost_measurement",
    "containment",
}:
    errors.append("initial July failure record has an unexpected shape")
if (
    initial.get("schema_version") != 1
    or initial.get("provider") != "anthropic"
    or initial.get("qualification_requirement") != "provider-spend-enforcement"
    or initial.get("outcome") != "denial_not_observed"
    or initial.get("workspace_id") != workspace_id
    or initial.get("service_account_id") != service_account_id
):
    errors.append("initial July failure identity differs from the observed attempt")
if initial.get("fixture") != {
    "model": "claude-opus-5",
    "request_attempts": 8,
    "accepted_requests": 8,
    "denial_observed": False,
    "diagnostic": [
        "incomplete guest result: file_count=1 expected_mask=s",
        "guest returned incomplete status=anthropic-spend-denial-not-observed",
        "factory worker run failed: stage=result-filesystem-validation line=470 status=1",
    ],
}:
    errors.append("initial July fixture record differs from the live failure")
initial_usage = initial.get("usage_measurement", {})
if initial_usage != {
    "source": "Anthropic Usage Report API",
    "observed_at": "2026-07-29T22:35:24Z",
    "model": "claude-opus-5",
    "cache_read_input_tokens": 0,
    "cache_creation_input_tokens": 0,
    "buckets": [
        {
            "starting_at": "2026-07-29T22:24:00Z",
            "ending_at": "2026-07-29T22:25:00Z",
            "uncached_input_tokens": 960185,
            "output_tokens": 5,
        },
        {
            "starting_at": "2026-07-29T22:25:00Z",
            "ending_at": "2026-07-29T22:26:00Z",
            "uncached_input_tokens": 576111,
            "output_tokens": 3,
        },
    ],
    "total_uncached_input_tokens": 1536296,
    "total_output_tokens": 8,
}:
    errors.append("A120 historical uncached-token calibration differs from evidence")
elif (
    initial_usage["total_uncached_input_tokens"]
    // initial["fixture"]["accepted_requests"]
    != HISTORICAL_UNCACHED_INPUT_TOKENS_PER_BODY
):
    errors.append("A120 historical per-body tokenization arithmetic is malformed")
initial_cost = initial.get("cost_measurement", {})
if initial_cost != {
    "source": "Anthropic Cost Report API",
    "currency": "USD",
    "observed_at": "2026-07-30T01:17:29Z",
    "billed_cost_usd": "7.68168",
}:
    errors.append("initial July settled cost differs from the live report")
initial_containment = initial.get("containment", {})
if (
    initial_containment.get("boundary_tainted") is not True
    or initial_containment.get("marker")
    != "run=anthropic-s2-20260729-412f8a1777 reason=containment-qualification-failed stage=result-filesystem-validation line=470 detected_at=2026-07-29T22:25:26Z"
    or initial_containment.get("tainted_worker")
    != {"worker_id": 588324505, "disposition": "destroyed"}
    or initial_containment.get("reviewed_replacement", {}).get(
        "copied_state_from_tainted_worker"
    )
    is not False
):
    errors.append("initial failure omits taint or reviewed clean-replacement history")

try:
    repair = json.loads(REPAIR_FAILURE_PATH.read_text())
except FileNotFoundError:
    errors.append("A9 repair failure record is missing")
    repair = {}
if set(repair) != {
    "schema_version",
    "provider",
    "qualification_requirement",
    "outcome",
    "workspace_id",
    "service_account_id",
    "run_id",
    "cap_control",
    "fixture",
    "cost_measurement",
    "containment",
    "repair_loop",
}:
    errors.append("A9 repair failure record has an unexpected shape")
if (
    repair.get("outcome") != "repair_failed_unattributed_http_400"
    or repair.get("run_id") != "anthropic-s2-20260730-4d80267abf"
    or repair.get("workspace_id") != workspace_id
    or repair.get("service_account_id") != service_account_id
):
    errors.append("A9 repair failure identity differs from the observed attempt")
repair_cost = repair.get("cost_measurement", {})
if (
    repair_cost.get("incremental_repair_cost_status")
    != "unproved_due_to_incomplete_settlement_window"
    or repair_cost.get("latest_recheck_seconds_after_repair") != 2543
    or repair_cost.get("initial_spend_above_displayed_cap_usd") != "6.68168"
    or repair_cost.get("denial_overshoot_status") != "not_observed"
    or "incremental_repair_cost_usd" in repair_cost
    or "measured_initial_attempt_overshoot_usd" in repair_cost
):
    errors.append("A9 repair cost record still claims an unproved denial overshoot")
observations = repair_cost.get("observations", [])
if [item.get("billed_cost_usd") for item in observations] != [
    "7.68168",
    "7.68168",
    "7.68168",
] or [item.get("observed_at") for item in observations] != [
    "2026-07-30T01:17:29Z",
    "2026-07-30T02:26:10Z",
    "2026-07-30T03:04:16Z",
]:
    errors.append("A9 repair cost observations differ from the historical reports")
if repair.get("containment", {}).get("tainted_worker") != {
    "worker_id": 588590370,
    "disposition": "quarantined_pending_reviewed_replacement",
}:
    errors.append("A9 repair record does not identify the quarantined worker")
if repair.get("repair_loop") != {
    "consumed": True,
    "further_provider_requests_permitted": False,
    "disposition": "escalated_under_A9",
    "successor_authorization": "A115",
}:
    errors.append(
        "historical A9 stop and A115 successor authorization are not distinct"
    )

for name, record in (("initial", initial), ("repair", repair)):
    serialized = json.dumps(record, sort_keys=True)
    if secret_named_key(record) or re.search(
        r"sk-ant-|eyJ[A-Za-z0-9_-]+\.eyJ", serialized
    ):
        errors.append(f"{name} failure record contains a credential")

if RESULT_PATH.exists():
    result = json.loads(RESULT_PATH.read_text())
    if set(result) != {
        "schema_version",
        "provider",
        "qualification_requirement",
        "authorization_ruling",
        "organization_id",
        "workspace_id",
        "service_account_id",
        "request_binding",
        "phases",
        "cap_control",
        "cost_measurement",
    }:
        errors.append("A115 live result has an unexpected top-level shape")
    if (
        result.get("schema_version") != 3
        or result.get("provider") != "anthropic"
        or result.get("qualification_requirement") != "provider-spend-enforcement"
        or result.get("authorization_ruling") != "A115"
        or result.get("organization_id") != organization_id
        or result.get("workspace_id") != workspace_id
        or result.get("service_account_id") != service_account_id
    ):
        errors.append("A115 live result identity differs from policy")
    phases = result.get("phases", {})
    if set(phases) != set(PHASES):
        errors.append("A115 live result does not contain exactly three phases")
    reproducible = {
        "request_sha256": hashlib.sha256(ANTHROPIC_REQUEST).hexdigest(),
        "patch_sha256": hashlib.sha256(ANTHROPIC_PATCH).hexdigest(),
        "production_parity_sha256": digest(PRODUCTION_PARITY_PATH),
        "image_recipe_sha256": image_recipe_sha256(),
        "host_contract_sha256": host_contract_sha256(),
    }
    provider_body_hashes: set[str] = set()
    provider_times: dict[str, datetime] = {}
    exchange_ids: list[str] = []
    issuance_windows: list[tuple[datetime, datetime]] = []
    for phase in PHASES:
        evidence = phases.get(phase, {}) if isinstance(phases, dict) else {}
        if evidence.get("qualification_phase") != phase:
            errors.append(f"A115 {phase} evidence has the wrong phase")
        for field, expected in reproducible.items():
            if evidence.get(field) != expected:
                errors.append(f"A115 {phase} {field} differs from current source")
        if (
            not re.fullmatch(
                r"[0-9a-f]{64}", str(evidence.get("observed_rootfs_sha256", ""))
            )
            or "rootfs_sha256" in evidence
        ):
            errors.append(f"A115 {phase} rootfs observation is malformed")
        if evidence.get("credential_removed_before_output") is not True:
            errors.append(f"A115 {phase} retained a credential at output")
        if evidence.get("host_teardown") != {
            "processes": 0,
            "taps": 0,
            "nftables_tables": 0,
            "run_directories": 0,
            "credential_files": 0,
            "guest_provider_egress_packets": 0,
        }:
            errors.append(f"A115 {phase} host teardown is incomplete")
        if evidence.get("delivery") != {
            "worker_host_tmpfs": True,
            "credential_delivered_to_guest": False,
            "credential_removed_before_guest_boot": True,
            "assertion_delivered": False,
            "signing_key_delivered": False,
            "admin_credential_delivered": False,
        }:
            errors.append(f"A117 {phase} credential delivery boundary is malformed")
        if evidence.get("provider_transport") != {
            "schema_version": 1,
            "authorization_ruling": "A117",
            "mechanism": "host-one-shot-network-namespace-v1",
            "http_version": "1.0",
            "connection_close": True,
            "client_sha256": digest(TRANSPORT_PATH),
            "admitted_conntrack_ids": 1,
            "admitted_new_connections": 1,
            "rejected_new_connections": 0,
            "rejected_connection_packets": 0,
            "guest_provider_allowlist_entries": 0,
            "namespace_ipv6_disabled": True,
            "credential_removed_before_guest_boot": True,
        }:
            errors.append(f"A117 {phase} one-shot transport receipt is malformed")
        issuance = evidence.get("issuance", {})
        try:
            exchange_id = issuance["exchange_request_id"]
            if not re.fullmatch(r"req_[A-Za-z0-9]+", exchange_id):
                raise ValueError
            exchange_ids.append(exchange_id)
            issuance_windows.append(
                (parse_time(issuance["issued_at"]), parse_time(issuance["expires_at"]))
            )
        except (KeyError, TypeError, ValueError):
            errors.append(f"A115 {phase} issuance window is malformed")
        observation = evidence.get("provider_observation", {})
        provider_body_hashes.add(str(observation.get("request_body_sha256", "")))
        try:
            provider_times[phase] = parse_time(observation.get("observed_at"))
        except ValueError:
            errors.append(f"A115 {phase} provider time is malformed")
        if (
            observation.get("endpoint") != "/v1/messages"
            or observation.get("request_attempts") != 1
            or not re.fullmatch(
                r"req_[A-Za-z0-9]+", str(observation.get("request_id", ""))
            )
        ):
            errors.append(f"A115 {phase} provider observation is malformed")
        if phase == "temporary_refusal":
            provider_error = observation.get("provider_error", {})
            if (
                observation.get("outcome") != "refused"
                or observation.get("http_status") not in {400, 403}
                or observation.get("response_type") != "error"
                or provider_error.get("error_type")
                in {"rate_limit_error", "overloaded_error"}
                or set(provider_error.get("shape", {}))
                != {"top_level_keys", "error_keys"}
            ):
                errors.append("A115 refusal is not a bounded provider denial")
        else:
            usage = observation.get("usage", {})
            if (
                observation.get("outcome") != "accepted"
                or observation.get("http_status") != 200
                or observation.get("response_type") != "message"
                or observation.get("model") != "claude-opus-5"
                or not isinstance(usage, dict)
                or not isinstance(usage.get("input_tokens"), int)
                or usage.get("input_tokens", 0) < MINIMUM_UNCACHED_INPUT_TOKENS
            ):
                errors.append(
                    f"A120 {phase} is not an uncached cost-floor acceptance"
                )
    expected_body_hash = hashlib.sha256(ANTHROPIC_PROVIDER_BODY).hexdigest()
    if provider_body_hashes != {expected_body_hash}:
        errors.append("A120 phase request bodies differ from the exact bound body")
    if len(set(exchange_ids)) != 3 or len(issuance_windows) != 3:
        errors.append("A115 phases do not bind three distinct WIF exchanges")
    elif any(
        first[1] > second[0]
        for first, second in zip(issuance_windows, issuance_windows[1:])
    ):
        errors.append("A115 phase WIF lifetimes overlap")
    binding = result.get("request_binding", {})
    if binding != {
        "model": "claude-opus-5",
        "endpoint": "/v1/messages",
        "request_body_sha256": next(iter(provider_body_hashes), ""),
        "byte_identical_across_phases": True,
    }:
        errors.append("A115 request binding does not match the phase evidence")

    cap_control = result.get("cap_control", {})
    cap_intervals: dict[str, tuple[datetime, datetime]] = {}
    organization_limits: list[Decimal] = []
    for phase, expected in (
        ("operational_acceptance", Decimal(50)),
        ("temporary_refusal", Decimal(1)),
        ("restored_acceptance", Decimal(50)),
    ):
        cap = cap_control.get(phase, {}) if isinstance(cap_control, dict) else {}
        try:
            before = parse_time(cap["captured_before_at"])
            after = parse_time(cap["captured_after_at"])
            workspace_cap = decimal_value(cap["workspace_monthly_limit_usd"])
            organization_cap = decimal_value(cap["organization_monthly_limit_usd"])
            if (
                set(cap)
                != {
                    "captured_before_at",
                    "captured_after_at",
                    "workspace_monthly_limit_usd",
                    "organization_monthly_limit_usd",
                    "capture_method",
                }
                or cap["capture_method"]
                != "operator_console_readback_bounded_by_control_plane_utc"
                or before > after
                or (after - before).total_seconds() > 300
                or workspace_cap != expected
                or organization_cap != Decimal(500)
            ):
                raise ValueError
            cap_intervals[phase] = (before, after)
            organization_limits.append(organization_cap)
        except (KeyError, InvalidOperation, TypeError, ValueError):
            errors.append(f"A115 {phase} cap readback is malformed")
    if organization_limits and len(set(organization_limits)) != 1:
        errors.append("organization cap changed during A115 qualification")

    cost = result.get("cost_measurement", {})
    try:
        before_amount = decimal_value(cost["settled_spend_before_activation_usd"])
        preexisting = decimal_value(cost["preexisting_excess_at_activation_usd"])
        after_amount = decimal_value(cost["settled_spend_after_refusal_usd"])
        incremental = decimal_value(cost["incremental_spend_before_refusal_usd"])
        before_time = parse_time(cost["before_captured_at"])
        after_time = parse_time(cost["after_captured_at"])
        if (
            set(cost)
            != {
                "source",
                "currency",
                "settled_spend_before_activation_usd",
                "preexisting_excess_at_activation_usd",
                "settled_spend_after_refusal_usd",
                "incremental_spend_before_refusal_usd",
                "before_captured_at",
                "after_captured_at",
                "pre_activation_workspace_cost_utc_day",
                "post_refusal_workspace_cost_utc_day",
                "settlement_window_seconds",
                "pre_activation_settlement_window_seconds",
                "attribution",
            }
            or cost["source"] != "Anthropic Cost Report API"
            or cost["currency"] != "USD"
            or before_amount <= Decimal(1)
            or before_amount >= Decimal(50)
            or preexisting != before_amount - Decimal(1)
            or incremental != after_amount - before_amount
            or incremental < 0
            or cost["pre_activation_workspace_cost_utc_day"]
            != utc_day(provider_times["operational_acceptance"])
            or (
                cost["pre_activation_workspace_cost_utc_day"]
                == A121_LEGACY_PRE_ACTIVATION_UTC_DAY
                and before_amount != A121_LEGACY_PRE_ACTIVATION_COST_USD
            )
            or cost["post_refusal_workspace_cost_utc_day"]
            != utc_day(provider_times["temporary_refusal"])
            or not utc_day_closed(
                provider_times["operational_acceptance"], before_time
            )
            or not utc_day_closed(provider_times["temporary_refusal"], after_time)
            or cost["settlement_window_seconds"]
            != int((after_time - provider_times["temporary_refusal"]).total_seconds())
            or cost["settlement_window_seconds"] < 10260
            or cost["pre_activation_settlement_window_seconds"]
            != int(
                (before_time - provider_times["operational_acceptance"]).total_seconds()
            )
            or cost["pre_activation_settlement_window_seconds"] < 10260
            or cost["attribution"]
            != "A115_acceptance_refusal_acceptance_workspace_only_cap_change"
            or not (
                cap_intervals["operational_acceptance"][1]
                <= provider_times["operational_acceptance"]
                <= before_time
                <= cap_intervals["temporary_refusal"][0]
                <= cap_intervals["temporary_refusal"][1]
                <= provider_times["temporary_refusal"]
                <= cap_intervals["restored_acceptance"][0]
                <= cap_intervals["restored_acceptance"][1]
                <= after_time
                <= provider_times["restored_acceptance"]
            )
        ):
            raise ValueError
        event_times = {
            *provider_times.values(),
            before_time,
            after_time,
            *(time for interval in cap_intervals.values() for time in interval),
        }
        if len(
            {
                (
                    value.astimezone(timezone.utc).year,
                    value.astimezone(timezone.utc).month,
                )
                for value in event_times
            }
        ) != 1:
            raise ValueError
    except (KeyError, InvalidOperation, TypeError, ValueError):
        errors.append(
            "A122 cost separation, day-close settlement, or phase ordering is malformed"
        )
    if contains_forbidden_ceiling(result):
        errors.append("A115 result encodes a forbidden preset overshoot ceiling")
    serialized = json.dumps(result, sort_keys=True)
    if secret_named_key(result) or re.search(
        r"sk-ant-|eyJ[A-Za-z0-9_-]+\.eyJ", serialized
    ):
        errors.append("A115 result contains a credential")

if errors:
    print("Anthropic spend check: failed", file=sys.stderr)
    for error in errors:
        print(f"  {error}", file=sys.stderr)
    raise SystemExit(1)

status = (
    "with live A115/A120/A121/A122 result"
    if RESULT_PATH.exists()
    else "A122 source preflight"
)
print(f"Anthropic spend check: pass ({status}; historical failures retained)")
