#!/usr/bin/env python3
"""Assert that the mapped OpenAI service account still exists.

The account `user-6tzs2hdFVN7GoYQbWfC0eu7k` ceased to exist between 2026-08-12
and 2026-08-18 with no recorded mutation and stayed dead for six days. Nothing
noticed, because the token exchange kept returning 200 throughout and no
requirement had ever asked the identity to do real work.

Static mode (the default, run in CI) validates policy/openai-identity-history.json
against the A150 contract - one current entry, unique ids, one project, and no
id promoted to current without a primary-source Administration API verification.
No network, no credential.

--live performs the only Administration API call that discriminates a live
service account: GET /v1/organization/projects/{project}/service_accounts. Three
cheaper signals are ruled out by primary-source observation and must never be
substituted:

- the token exchange returns 200 for a deleted account (issue #265);
- GET /v1/organization/users/{id} returns 404 for a *healthy* service account,
  because service accounts are not organization users (issue #267);
- GET /v1/organization/audit_logs returns 200 with zero events even unbounded
  for this organization, so nothing is recoverable after the fact (issue #267).

Because the audit log records nothing, this program's daily reading *is* the
record. It makes no token exchange and no billable call.

--metric additionally publishes the node-exporter textfile gauge, which is how
the control-plane timer surfaces the reading.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any
import urllib.error
import urllib.parse
import urllib.request


REPO = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY = REPO / "policy/openai-identity-history.json"
DEFAULT_ADMIN_KEY_FILE = Path("/etc/patchyard/openai-admin-readonly.key")
BASE_URL = "https://api.openai.com"
MAX_REGISTRY_BYTES = 1_000_000
MAX_ADMIN_KEY_BYTES = 4096
MAX_ERROR_BODY_CHARACTERS = 200
PAGE_LIMIT = 100
MAX_PAGES = 50
REQUEST_TIMEOUT_SECONDS = 30
SERVICE_ACCOUNT_ID_PATTERN = re.compile(r"user-[A-Za-z0-9]{16,64}")
PROJECT_ID_PATTERN = re.compile(r"proj_[A-Za-z0-9]{16,64}")
ADMIN_KEY_PATTERN = re.compile(r"[A-Za-z0-9_.-]{16,256}")
STATUSES = frozenset({"current", "historical"})
METRIC = "patchyard_openai_identity_live"
TIMESTAMP_METRIC = "patchyard_openai_identity_checked_timestamp_seconds"


class IdentityRegistryError(ValueError):
    """The OpenAI identity registry is outside the A150 contract."""


class LivenessError(RuntimeError):
    """The live Administration API assertion could not be completed."""


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    for key, _ in pairs:
        if key in seen:
            raise IdentityRegistryError(f"duplicate JSON key: {key}")
        seen.add(key)
    return dict(pairs)


def load_registry(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if len(raw) > MAX_REGISTRY_BYTES:
        raise IdentityRegistryError("registry file is outside the bounded contract")
    registry = json.loads(raw, object_pairs_hook=reject_duplicate_keys)
    if not isinstance(registry, dict):
        raise IdentityRegistryError("registry root is not an object")
    for field in (
        "schema_version",
        "ruling",
        "provider",
        "project_id",
        "current_service_account_id",
        "service_accounts",
    ):
        if field not in registry:
            raise IdentityRegistryError(f"registry is missing {field}")
    if registry["schema_version"] != 1:
        raise IdentityRegistryError("unsupported schema_version")
    if registry["ruling"] != "A150":
        raise IdentityRegistryError("registry does not carry the A150 ruling")
    if registry["provider"] != "openai":
        raise IdentityRegistryError("registry is not the OpenAI roster")
    return registry


def validate_registry(registry: dict[str, Any]) -> tuple[str, str]:
    """Return the (project_id, current_service_account_id) the roster asserts."""
    project_id = registry["project_id"]
    if not isinstance(project_id, str) or (
        PROJECT_ID_PATTERN.fullmatch(project_id) is None
    ):
        raise IdentityRegistryError("registry project_id is malformed")
    current = registry["current_service_account_id"]
    if not isinstance(current, str) or (
        SERVICE_ACCOUNT_ID_PATTERN.fullmatch(current) is None
    ):
        raise IdentityRegistryError("registry current_service_account_id is malformed")
    roster = registry["service_accounts"]
    if not isinstance(roster, list) or not roster:
        raise IdentityRegistryError("service_accounts is not a non-empty array")

    identifiers: list[str] = []
    marked_current: list[dict[str, Any]] = []
    for entry in roster:
        if not isinstance(entry, dict):
            raise IdentityRegistryError("service_accounts entry is not an object")
        identifier = entry.get("id")
        if not isinstance(identifier, str) or (
            SERVICE_ACCOUNT_ID_PATTERN.fullmatch(identifier) is None
        ):
            raise IdentityRegistryError("service_accounts entry id is malformed")
        status = entry.get("status")
        if status not in STATUSES:
            raise IdentityRegistryError(f"{identifier} carries no recognised status")
        if entry.get("project_id") != project_id:
            raise IdentityRegistryError(f"{identifier} names another project")
        identifiers.append(identifier)
        if status == "current":
            marked_current.append(entry)

    if len(identifiers) != len(set(identifiers)):
        raise IdentityRegistryError("registry repeats a service-account id")
    if [entry["id"] for entry in marked_current] != [current]:
        raise IdentityRegistryError("registry has no single current entry")

    # The whole lesson of the 2026-08-12 disappearance: the console said the
    # account was live and it was not. An id only becomes current after the
    # per-project listing has confirmed it from primary source (issue #267).
    if marked_current[0].get("administration_api_verified") is not True:
        raise IdentityRegistryError(
            f"{current} is current but was never verified from the"
            " Administration API listing"
        )
    return project_id, current


def read_admin_key(path: Path) -> str:
    raw = path.read_bytes()
    if len(raw) > MAX_ADMIN_KEY_BYTES:
        raise LivenessError("admin key file is outside the bounded contract")
    key = raw.decode("ascii", errors="strict").strip()
    if ADMIN_KEY_PATTERN.fullmatch(key) is None:
        raise LivenessError(f"admin key at {path} is malformed")
    return key


def redact(text: str, key: str) -> str:
    """No provider error body may carry the credential back into a log."""
    return text.replace(key, "[redacted]")[:MAX_ERROR_BODY_CHARACTERS]


def fetch_page(url: str, key: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as reply:
            if reply.status != 200:
                raise LivenessError(f"listing returned HTTP {reply.status}")
            body = reply.read(MAX_REGISTRY_BYTES).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        detail = redact(
            error.read(MAX_REGISTRY_BYTES).decode("utf-8", errors="replace"), key
        )
        raise LivenessError(
            f"listing returned HTTP {error.code}: {detail}"
        ) from error
    except urllib.error.URLError as error:
        raise LivenessError(f"listing could not be reached: {error.reason}") from error
    try:
        page = json.loads(body)
    except json.JSONDecodeError as error:
        raise LivenessError("listing returned a body that is not JSON") from error
    if not isinstance(page, dict) or not isinstance(page.get("data"), list):
        raise LivenessError("listing returned no data array")
    return page


def list_service_accounts(project_id: str, key: str) -> list[dict[str, Any]]:
    """Read the whole per-project listing. A truncated read would report a live
    account missing, so pagination is followed to exhaustion rather than
    trusting the first page."""
    endpoint = (
        f"{BASE_URL}/v1/organization/projects/"
        f"{urllib.parse.quote(project_id, safe='')}/service_accounts"
    )
    accounts: list[dict[str, Any]] = []
    after: str | None = None
    for _ in range(MAX_PAGES):
        query = {"limit": str(PAGE_LIMIT)}
        if after is not None:
            query["after"] = after
        page = fetch_page(f"{endpoint}?{urllib.parse.urlencode(query)}", key)
        accounts.extend(
            entry for entry in page["data"] if isinstance(entry, dict)
        )
        if not page.get("has_more"):
            return accounts
        last = page.get("last_id")
        if not isinstance(last, str) or not last:
            raise LivenessError("listing reports more pages but no cursor")
        after = last
    raise LivenessError("listing did not terminate within the bounded page count")


def assert_live(project_id: str, current: str, key: str) -> tuple[bool, str]:
    accounts = list_service_accounts(project_id, key)
    for entry in accounts:
        if entry.get("id") == current:
            role = entry.get("role", "unknown")
            return True, (
                f"{current} is listed by {project_id} at role {role}"
                f" ({len(accounts)} service accounts read)"
            )
    return False, (
        f"{current} is NOT listed by {project_id}"
        f" ({len(accounts)} service accounts read)"
    )


def publish_metric(path: Path, project_id: str, current: str, live: bool) -> None:
    now = datetime.now(timezone.utc).timestamp()
    labels = f'project="{project_id}",service_account="{current}"'
    body = (
        f"# HELP {METRIC} Whether the OpenAI identity registry's current service"
        " account is listed by its project.\n"
        f"# TYPE {METRIC} gauge\n"
        f"{METRIC}{{{labels}}} {1 if live else 0}\n"
        f"# HELP {TIMESTAMP_METRIC} Unix time of the last completed OpenAI"
        " service-account liveness reading.\n"
        f"# TYPE {TIMESTAMP_METRIC} gauge\n"
        f"{TIMESTAMP_METRIC} {now:.0f}\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(body)
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument(
        "--live",
        action="store_true",
        help="also read the project's Administration API service-account listing",
    )
    parser.add_argument(
        "--admin-key-file",
        type=Path,
        default=DEFAULT_ADMIN_KEY_FILE,
        help="read-only Administration key used by --live",
    )
    parser.add_argument(
        "--metric",
        type=Path,
        default=None,
        help="publish the node-exporter textfile gauge here (implies --live)",
    )
    arguments = parser.parse_args()

    try:
        registry = load_registry(arguments.registry)
        project_id, current = validate_registry(registry)
    except (OSError, json.JSONDecodeError, IdentityRegistryError) as error:
        print(f"OpenAI identity registry rejected: {error}", file=sys.stderr)
        return 1
    print(
        f"OpenAI identity registry ok: {len(registry['service_accounts'])} accounts,"
        f" current {current} in {project_id}"
    )
    if not (arguments.live or arguments.metric):
        return 0

    # A malformed registry publishes nothing and fails the unit; a completed
    # reading always publishes, so a dead account is visible as a 0 rather than
    # as a stale file.
    try:
        key = read_admin_key(arguments.admin_key_file)
        live, detail = assert_live(project_id, current, key)
    except (OSError, LivenessError) as error:
        print(f"OpenAI identity liveness unreadable: {error}", file=sys.stderr)
        return 1
    if arguments.metric is not None:
        publish_metric(arguments.metric, project_id, current, live)
    if live:
        print(f"OpenAI identity live: {detail}")
        return 0
    print(f"OpenAI identity MISSING: {detail}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
