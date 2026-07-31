#!/usr/bin/env python3
"""Workflow-rooted source and gate census for the A101 readiness boundary."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import sys


REPO = Path(__file__).resolve().parent.parent
WORKFLOW = REPO / ".github/workflows/infrastructure.yml"
BOUND_SOURCES = {
    "infra/wait-do-worker-firewall.sh": "5aa2f71ce014671de08104356d77a5ff210efd56525e7c1ddf85f46770336cba",
    "infra/replace-worker.sh": "27f322afc3c3c8d813f18a5003f2e2fdc2c6d75d24b28ed0c19ad215e9ad580e",
    "infra/tofu.sh": "5863f9a885bf1add664592e118fa8b066920be6ef28dc0deb762ac3553e70b7f",
    "infra/ansible/converge.sh": "30a8758d6925ffa7635212cc49c67719ba7a6abf6d389481da2e422dec41f63e",
    "infra/ansible/qualify.sh": "2380ef8cdc18ebf1a33f8458a8bbe57fdc415d0d696a56bce712bf1e8466fccd",
    "infra/ansible/inventory/tofu.sh": "7101838ae5f3eae5031c30888ae6eda754d9519f6af9d2d6884142155f69bb59",
    "infra/tool-versions.env": "63fa7fa217d98d914a73394c98b41f97571c5c776b3a9b2d4c51d95e56ab917f",
    "tools/read-infra-tool-version.py": "d94d97d605736d0201d0fc0517e0e780d6c346ab79ddc3bd84de7b472edeccd8",
    "tools/install-shellcheck.sh": "e681fda2ef31cb936cacb0a79aa6bfb8b571bc4922b9d7869899412696772c36",
    "tools/check-infra.sh": "24e28cc6830725f89b889f4b1116eb019acd65208785ee6eb61e9b72f14c7d16",
    "tools/check-ansible.sh": "db391e029f876269f85b0276d20ca7370f8be6179f94285b516c31d32bca128b",
    "tools/check-anthropic-spend.py": "11a87b343c3e88437b4c707acc373321f4891c71b270cd0a8e8c1095a0932b36",
    "infra/ansible/tests/test_a101_readiness_root.py": "5d55c30b8d3b92de9bad435de8348318fad2d4d0b7c029dab88bee87f1350eb7",
    "infra/ansible/tests/test_worker_firewall_readiness.py": "28f14b9bc4f7bcc49f10662b943ad0bef2e1467fbe147d1f780f04f3d3dedd2d",
    "infra/ansible/tests/test_anthropic_spend.py": "0a6b40c524085aa272ed46c7a9e983922f94790d2cb7920f0fe2a7bad3e27eb9",
}
EXPECTED_TEST_MODULES = (
    "infra.ansible.tests.test_a101_readiness_root",
    "infra.ansible.tests.test_worker_firewall_readiness",
    "infra.ansible.tests.test_anthropic_spend",
    "infra.ansible.tests.test_anthropic_issuance",
    "infra.ansible.tests.test_anthropic_wif_admin",
    "infra.ansible.tests.test_child_launcher",
    "infra.ansible.tests.test_cloud_init_bootstrap",
    "infra.ansible.tests.test_dashboard_checkout",
    "infra.ansible.tests.test_log_secret_scan",
    "infra.ansible.tests.test_preview_capability_deployment",
    "infra.ansible.tests.test_replace_worker",
    "infra.ansible.tests.test_session14_qualification",
    "infra.ansible.tests.test_session15_proposer",
    "infra.ansible.tests.test_session16_cutover",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_test_files() -> set[str]:
    return {
        module.replace("infra.ansible.tests.", "infra/ansible/tests/") + ".py"
        for module in EXPECTED_TEST_MODULES
    }


def validate() -> list[str]:
    errors: list[str] = []
    for relative, expected in BOUND_SOURCES.items():
        path = REPO / relative
        if not path.is_file():
            errors.append(f"bound A101 source is missing: {relative}")
            continue
        actual = digest(path)
        if actual != expected:
            errors.append(
                f"bound A101 source differs: {relative} "
                f"(expected {expected}, observed {actual})"
            )

    observed_tests = {
        str(path.relative_to(REPO))
        for path in (REPO / "infra/ansible/tests").glob("test_*.py")
    }
    expected_tests = expected_test_files()
    for missing in sorted(expected_tests - observed_tests):
        errors.append(f"explicit Ansible test census is missing: {missing}")
    for unexpected in sorted(observed_tests - expected_tests):
        errors.append(f"explicit Ansible test census has an extra module: {unexpected}")

    wrapper_path = REPO / "tools/check-ansible.sh"
    if wrapper_path.is_file():
        wrapper = wrapper_path.read_text()
        module_block_match = re.search(
            r"(?ms)^TEST_MODULES=\(\n(?P<body>.*?)^\)\n",
            wrapper,
        )
        if module_block_match is None:
            errors.append("Ansible wrapper has no explicit TEST_MODULES census")
        else:
            observed_modules = tuple(
                line.strip()
                for line in module_block_match.group("body").splitlines()
                if line.strip()
            )
            if observed_modules != EXPECTED_TEST_MODULES:
                errors.append("Ansible wrapper TEST_MODULES census differs")
        if wrapper.count(
            'run_gate python3 "$REPO_ROOT/tools/check-anthropic-spend.py"'
        ) != 1:
            errors.append("Ansible wrapper lacks one independent spend-checker process")
        if wrapper.count(
            'run_gate python3 "$REPO_ROOT/tools/check-a101-readiness-root.py"'
        ) != 1:
            errors.append("Ansible wrapper lacks one post-test trust-root check")
        if "unittest discover" in wrapper:
            errors.append("Ansible wrapper still uses open-ended unittest discovery")

    infra_wrapper_path = REPO / "tools/check-infra.sh"
    if infra_wrapper_path.is_file():
        infra_wrapper = infra_wrapper_path.read_text()
        spend_call = 'python3 "$REPO_ROOT/tools/check-anthropic-spend.py"'
        issuance_call = 'python3 "$REPO_ROOT/tools/check-anthropic-issuance.py"'
        try:
            spend_index = infra_wrapper.index(spend_call)
            issuance_index = infra_wrapper.index(issuance_call)
        except ValueError:
            errors.append("infrastructure wrapper lacks a required Anthropic checker")
        else:
            if spend_index >= issuance_index:
                errors.append("spend checker does not precede the stale issuance boundary")

    for relative in (
        "tools/check-infra.sh",
        "tools/check-ansible.sh",
        "tools/install-shellcheck.sh",
    ):
        path = REPO / relative
        if path.is_file() and "source \"$REPO_ROOT/infra/tool-versions.env\"" in path.read_text():
            errors.append(f"{relative} executes infrastructure tool-version data")

    if WORKFLOW.is_file():
        workflow = WORKFLOW.read_text()
        root_digest = digest(Path(__file__))
        pin = f"{root_digest}  tools/check-a101-readiness-root.py"
        if workflow.count(pin) != 1:
            errors.append("infrastructure workflow does not pin this trust-root checker")
        try:
            trust_index = workflow.index("Verify A101 readiness trust root")
            install_index = workflow.index("Install pinned OpenTofu")
        except ValueError:
            errors.append("infrastructure workflow lacks the A101 trust-root stage")
        else:
            if trust_index >= install_index:
                errors.append("workflow trust-root check occurs after executable setup")
    else:
        errors.append("infrastructure workflow is missing")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("A101 readiness trust root: failed", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1
    print("A101 readiness trust root: pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
