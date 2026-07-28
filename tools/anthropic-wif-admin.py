#!/usr/bin/env python3
"""Plan or create the exact Anthropic WIF objects for Patchyard Factory."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
import urllib.error
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = ROOT / "policy" / "anthropic-wif.json"
BASE_URL = "https://api.anthropic.com"


class ApiError(RuntimeError):
    pass


class AnthropicAdmin:
    def __init__(self, profile: str) -> None:
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("ANTHROPIC_AUTH_TOKEN", None)
        self.token = subprocess.check_output(
            [
                "ant",
                "auth",
                "print-credentials",
                "--profile",
                profile,
                "--access-token",
            ],
            env=env,
            text=True,
        ).strip()

    def request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        encoded = None
        headers = {
            "anthropic-version": "2023-06-01",
            "authorization": f"Bearer {self.token}",
            "user-agent": "patchyard-anthropic-wif-admin/1",
        }
        if body is not None:
            encoded = json.dumps(body, separators=(",", ":")).encode()
            headers["content-type"] = "application/json"
        request = urllib.request.Request(
            BASE_URL + path, data=encoded, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = response.read(1_000_000)
        except urllib.error.HTTPError as error:
            payload = error.read(1_000_000)
            try:
                parsed = json.loads(payload)
                message = (parsed.get("error") or {}).get("message", "unknown error")
            except (json.JSONDecodeError, AttributeError):
                message = "non-JSON error"
            raise ApiError(f"{method} {path}: HTTP {error.code}: {message}") from error
        return json.loads(payload)

    def list_all(self, path: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page: str | None = None
        while True:
            separator = "&" if "?" in path else "?"
            page_suffix = (
                f"{separator}page={urllib.parse.quote(page)}" if page is not None else ""
            )
            result = self.request("GET", path + page_suffix)
            items.extend(result.get("data", []))
            page = result.get("next_page")
            if not page:
                return items


def unique_named(items: list[dict[str, Any]], name: str, kind: str) -> dict[str, Any] | None:
    matches = [item for item in items if item.get("name") == name]
    if len(matches) > 1:
        raise ApiError(f"multiple {kind} objects named {name}")
    return matches[0] if matches else None


def require_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise ApiError(f"{label} differs: expected {expected!r}, observed {actual!r}")


def load_jwks(path: Path) -> list[dict[str, Any]]:
    document = json.loads(path.read_text())
    require_equal(sorted(document), ["keys"], "JWKS fields")
    keys = document["keys"]
    if not isinstance(keys, list) or len(keys) != 1:
        raise ApiError("JWKS must contain exactly one public key")
    key = keys[0]
    require_equal(sorted(key), ["alg", "e", "kid", "kty", "n", "use"], "JWK fields")
    require_equal(key["alg"], "RS256", "JWK algorithm")
    require_equal(key["kty"], "RSA", "JWK type")
    require_equal(key["use"], "sig", "JWK use")
    for field in ("kid", "n", "e"):
        if not isinstance(key[field], str) or not key[field]:
            raise ApiError(f"JWK {field} must be a non-empty string")
    return keys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="patchyard-admin")
    parser.add_argument("--jwks", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    policy = json.loads(POLICY_PATH.read_text())
    keys = load_jwks(args.jwks)
    api = AnthropicAdmin(args.profile)
    changes: list[str] = []

    organization = api.request("GET", "/v1/organizations/me")
    require_equal(organization.get("id"), policy["organization"]["id"], "organization ID")
    require_equal(organization.get("name"), policy["organization"]["name"], "organization name")

    workspaces = api.list_all("/v1/organizations/workspaces?limit=100&include_archived=false")
    workspace = unique_named(workspaces, policy["workspace"]["name"], "workspace")
    if workspace is None:
        raise ApiError("the reviewed Patchyard Factory workspace does not exist")
    require_equal(workspace.get("id"), policy["workspace"]["id"], "workspace ID")

    account_spec = policy["service_account"]
    accounts = api.list_all(
        "/v1/organizations/service_accounts?limit=100&include_archived=false"
    )
    account = unique_named(accounts, account_spec["name"], "service account")
    if account is None:
        changes.append("create-service-account")
        if args.apply:
            account = api.request(
                "POST",
                "/v1/organizations/service_accounts",
                {
                    "name": account_spec["name"],
                    "description": account_spec["description"],
                    "organization_role": account_spec["organization_role"],
                },
            )
    if account is not None:
        require_equal(
            account.get("description"),
            account_spec["description"],
            "service-account description",
        )
        require_equal(
            account.get("organization_role"),
            account_spec["organization_role"],
            "service-account role",
        )
        if account_spec["id"] is not None:
            require_equal(account.get("id"), account_spec["id"], "service-account ID")

    if account is not None:
        membership_path = f"/v1/organizations/service_accounts/{account['id']}/workspaces"
        memberships = api.list_all(membership_path + "?limit=100")
        matching_memberships = [
            item for item in memberships if item.get("workspace_id") == workspace["id"]
        ]
        if not matching_memberships:
            changes.append("add-service-account-workspace")
            if args.apply:
                api.request(
                    "POST",
                    membership_path,
                    {
                        "workspace_id": workspace["id"],
                        "workspace_role": account_spec["workspace_role"],
                    },
                )
        elif len(matching_memberships) != 1:
            raise ApiError("duplicate service-account workspace membership")
        else:
            require_equal(
                matching_memberships[0].get("workspace_role"),
                account_spec["workspace_role"],
                "service-account workspace role",
            )

    issuer_spec = policy["issuer"]
    issuers = api.list_all(
        "/v1/organizations/federation_issuers?limit=100&include_archived=false"
    )
    issuer = unique_named(issuers, issuer_spec["name"], "federation issuer")
    if issuer is None:
        changes.append("create-federation-issuer")
        if args.apply:
            issuer = api.request(
                "POST",
                "/v1/organizations/federation_issuers",
                {
                    "name": issuer_spec["name"],
                    "issuer_url": issuer_spec["issuer_url"],
                    "jwks": {"type": "inline", "keys": keys},
                    "check_jti": issuer_spec["check_jti"],
                    "max_jwt_lifetime_seconds": issuer_spec["max_jwt_lifetime_seconds"],
                },
            )
    if issuer is not None:
        issuer = api.request("GET", f"/v1/organizations/federation_issuers/{issuer['id']}")
        for field in ("issuer_url", "check_jti", "max_jwt_lifetime_seconds"):
            require_equal(issuer.get(field), issuer_spec[field], f"issuer {field}")
        require_equal(issuer.get("jwks"), {"type": "inline", "keys": keys}, "issuer JWKS")
        if issuer_spec["id"] is not None:
            require_equal(issuer.get("id"), issuer_spec["id"], "issuer ID")

    rule_spec = policy["rule"]
    rules = api.list_all(
        "/v1/organizations/federation_rules?limit=100&include_archived=false"
    )
    rule = unique_named(rules, rule_spec["name"], "federation rule")
    if rule is None:
        changes.append("create-federation-rule")
        if args.apply:
            if account is None or issuer is None:
                raise ApiError("rule dependencies were not created")
            rule = api.request(
                "POST",
                "/v1/organizations/federation_rules",
                {
                    "name": rule_spec["name"],
                    "description": rule_spec["description"],
                    "issuer_id": issuer["id"],
                    "match": {
                        "subject_prefix": rule_spec["subject"],
                        "audience": rule_spec["audience"],
                        "claims": rule_spec["claims"],
                    },
                    "target": {
                        "type": "service_account",
                        "service_account_id": account["id"],
                    },
                    "workspace_id": workspace["id"],
                    "oauth_scope": rule_spec["oauth_scope"],
                    "token_lifetime_seconds": rule_spec["token_lifetime_seconds"],
                },
            )
    if rule is not None:
        rule = api.request("GET", f"/v1/organizations/federation_rules/{rule['id']}")
        require_equal(rule.get("description"), rule_spec["description"], "rule description")
        require_equal(rule.get("issuer_id"), issuer["id"], "rule issuer")
        require_equal(rule.get("target", {}).get("service_account_id"), account["id"], "rule target")
        require_equal(rule.get("oauth_scope"), rule_spec["oauth_scope"], "rule OAuth scope")
        require_equal(rule.get("token_lifetime_seconds"), rule_spec["token_lifetime_seconds"], "rule lifetime")
        require_equal(rule.get("match", {}).get("subject_prefix"), rule_spec["subject"], "rule subject")
        require_equal(rule.get("match", {}).get("audience"), rule_spec["audience"], "rule audience")
        require_equal(rule.get("match", {}).get("claims"), rule_spec["claims"], "rule claims")
        require_equal(rule.get("workspace_ids"), [workspace["id"]], "rule workspaces")
        require_equal(rule.get("applies_to_all_workspaces"), False, "rule all-workspaces flag")
        if rule_spec["id"] is not None:
            require_equal(rule.get("id"), rule_spec["id"], "rule ID")

    ready = account is not None and issuer is not None and rule is not None
    output = {
        "schema_version": 1,
        "mode": "apply" if args.apply else "plan",
        "organization_id": organization["id"],
        "workspace_id": workspace["id"],
        "changes": changes,
        "ready": ready,
        "binding": {
            "service_account_id": account.get("id") if account else None,
            "issuer_id": issuer.get("id") if issuer else None,
            "rule_id": rule.get("id") if rule else None,
        },
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ApiError, OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(f"anthropic WIF admin: {error}", file=sys.stderr)
        raise SystemExit(1)
