#!/usr/bin/env python3
"""Workflow-rooted source, import, and gate census for A101 readiness."""

from __future__ import annotations

import hashlib
import importlib
from pathlib import Path
import re
import sys
import sysconfig


REPO = Path(__file__).resolve().parent.parent
WORKFLOW = REPO / ".github/workflows/infrastructure.yml"
BOUND_SOURCES = {
    "infra/wait-do-worker-firewall.sh": "5aa2f71ce014671de08104356d77a5ff210efd56525e7c1ddf85f46770336cba",
    "infra/replace-worker.sh": "27f322afc3c3c8d813f18a5003f2e2fdc2c6d75d24b28ed0c19ad215e9ad580e",
    "infra/tofu.sh": "5863f9a885bf1add664592e118fa8b066920be6ef28dc0deb762ac3553e70b7f",
    "infra/ansible/converge.sh": "be3de80250f7a790784a3d100bc095473762a5f49d5ada26f6038c0e1175f18f",
    "infra/ansible/qualify.sh": "2423bb69fe19e355458158b4b49a67917dac0279bfe76110256944974533dd49",
    "infra/ansible/inventory/tofu.sh": "7101838ae5f3eae5031c30888ae6eda754d9519f6af9d2d6884142155f69bb59",
    "infra/ansible/roles/control_plane/templates/patchyard-management-ssh.j2": "fdd1020be15cc56c6c0207c68a876084737ef2fdaa63f74e16e8f8d8e5c41c4b",
    "infra/tool-versions.env": "63fa7fa217d98d914a73394c98b41f97571c5c776b3a9b2d4c51d95e56ab917f",
    "tools/read-infra-tool-version.py": "d94d97d605736d0201d0fc0517e0e780d6c346ab79ddc3bd84de7b472edeccd8",
    "tools/install-shellcheck.sh": "715047c90f6a877c57a5495f1bc24feecd40f365ccd8239a6dc711be22a3f535",
    "tools/check-infra.sh": "f225c5ddfce132dfd67a4bf57aa7cd51b0f92c5a67a9be76bc281d021768b42d",
    "tools/check-ansible.sh": "197184f2c925acb1f4270319625830a36bc2f2cf2f25d660c4f88090e1ea57b3",
    "tools/run-isolated-unittest.py": "f201a6a57353b485d15a47b803bf274cdf9033ef1e78ed3e07e6f188a728ecc7",
    "tools/check-credential-qualification.py": "7080339d1c05c7cfc0af4f57d57c12151048b21ba7d174e76c106688946ab320",
    "tools/anthropic-spend-evidence.py": "494cba4a628e592004dc975ead283aa32fe1fbfe6236c6d6a4a7c7d7ee733099",
    "tools/openai-spend-evidence.py": "9f497e2fe8344a2e314d8f024682760567a65972874abb16f7663ac61cbfc4cf",
    "tools/check-openai-spend.py": "8111df20d4df962ed1e1f4505f220df9ec28a91df0f9f1d87804b6a1d593eeb0",
    "worker/qualification/patchyard-run-openai-spend": "f3c0f02c2b2a82b943cd26d4af96f46b9321d7799dfbff32b235b522776dbf45",
    "tools/anthropic-wif-admin.py": "89794bd6235d5b37dfa4999a792588396ece9935b17820954b75d8b055822c91",
    "tools/anthropic-wif-lifecycle.py": "10dfc4b3dc0002396f651734ff71f9618c119acde0065d6287193efed492873d",
    "tools/anthropic-wif-revocation.py": "ef4c204880cdc002ccee17f080b6011191a183c07e3ae173b34beb215737b61f",
    "tools/anthropic-wif-crash-cleanup.py": "88bb709eb662734fd85d17ac30b0d30592fadbbd83ce366f17e84ea0143e844c",
    "tools/anthropic-wif-lifecycle-admin.py": "1a1e08060a5ad68f65b3a798e2b992ee2c34fc336e4f7fd8922bfdf2effecc55",
    "tools/openai-wif-issuance.py": "63676168101366f50670adf4e06fa5c6841589bfcead4e8813d244f47944469d",
    "tools/openai-wif-expiry.py": "0308a6cf7a9b17e194c8856efd69fe94d2b62e7c0184bc2161af0996015f934f",
    "tools/openai-wif-crash-cleanup.py": "9a770c04b91593a304d97edf07f131cbb0c353c0551648537dc6b7dea9bc4cdf",
    "tools/control-plane-attestation-v1.py": "0d32e80b980c334977e51eb706783896a687d29faef46d50e53f3ee56e8e4d47",
    "tools/openai-wif-federation-revocation.py": "0c3c1c55de148c318570ff9637bb21ddde7a8d04cf48d1c4d2bdda5d088b6a0e",
    "tools/check-openai-wif-federation-revocation.py": "861ffd93fa4f07956e7cf3d2bf3f2956d6019c2388e1a1a7b81de9cad9d1df28",
    "tools/openai-wif-signing-key-rotation.py": "95ea2f6c1cca63c64fc1cd85e0bf5567db3b4c5e47fe4f2c4a83e701db4c8bd3",
    "tools/check-openai-wif-signing-key-rotation.py": "f6380375a0d4652e5bc0717812dbf17e955a9d39294d8e1f16b1379899ce29a0",
    "tools/check-anthropic-expiry.py": "8d9de38c16bbcc4ad63a73a0f570703581f8264371503385ef513057ff0f8ca8",
    "tools/check-anthropic-spend.py": "e3e2efc38a39b3610611807b7fbc680567aa6b46814408da25e22039c6f8c796",
    "tools/check-anthropic-issuance.py": "c3896ebf62fbf605ec4055bc020aa695026d72a821cbfeaf0d5a3fda0a62fe46",
    "tools/check-anthropic-revocation.py": "748cea22f9ece87dee2b6915f3609c8041cae1b5d6fdfd27b1f165901d9d7297",
    "tools/check-anthropic-crash-cleanup.py": "35dd6d624e4302dd230560b1380736eb43df3aa6b345015a4fce3f429d354e66",
    "tools/check-openai-wif-issuance.py": "a5d123114c697fd01b6c7bec89bb302673cef96dd4f66bd1e0c40c8e5bc6f2d2",
    "tools/check-openai-wif-expiry.py": "aa7c34e82227871f98d5d4dacc9ce5397bfd0fce48858caaca6b53323b4d415a",
    "tools/check-openai-wif-crash-cleanup.py": "bfe181b75eadae10471a43a2d877276cc3190767922c930650328b10ee05364e",
    "tools/check-independence.py": "baaa2e5058862a253c5042e7ccaea4bfea8af05a93825f5ce5cf99bbd1f93782",
    "tools/check-preview-runtime.py": "2f9a6e994c3d50e7e1f729546b3180330c4ccf0d471ee5b75f016cbbc95292be",
    "tools/check-signing-identities.py": "368f4edca351829d21b98621d8dc5dad49262cd48d03268cc0735005b140e165",
    "tools/check-stack.py": "ddce869a4bd4983c35c1b246ba01b5e8b1ea25219c761ebbdb2d5b4a8194deff",
    "tools/check-worker-qualification.py": "e9d5662bed3f7002fb6b0d23b777f12a401e8f9a0be4d340a5cf7580fdb3f15d",
    "tools/check-worker-runtime.py": "2ba1b99160441214acd53e4d8ed3aeb69aedbb540c0960cd47c02b0ecfe1d3c3",
    "infra/ansible/tests/test_a101_readiness_root.py": "6be1b217ec44db6f7858143e5e4696914c97d6978a6fdb9ed4643b065f21dbd8",
    "infra/ansible/tests/test_freeze_graph.py": "75e4350aaa4f96cac19100e34d80d4fedc2088249ca86567260dd071039dfffc",
    "infra/ansible/tests/test_worker_firewall_readiness.py": "96aad06159ea85d591c6fad711f71a5442c208278d83945fdd1ac843d8f012c0",
    "infra/ansible/tests/test_anthropic_spend.py": "5edcd638185066a16f6b6cf5d0b54b8654583f5fb217d170a187d05ad6b54aaf",
    "infra/ansible/tests/test_anthropic_issuance.py": "1cd6f3b71df6987c94a3bb02447aebfbb7106a8cfb412f0d751c2ddc76a7f882",
    "infra/ansible/tests/test_anthropic_lifecycle.py": "55c0296ef879e263172e5c7418b085ca317378b5030b65619017d1bd072ec057",
    "infra/ansible/tests/test_anthropic_wif_admin.py": "1d53f8ffe4ef6ad55b8d7187705344836aed831337c26f310bd11538888a9670",
    "infra/ansible/tests/test_openai_wif_issuance.py": "60192725d25f2fdf1ee54d5388314417aada0bf5668c3f90157d665ca3d5c2d4",
    "infra/ansible/tests/test_openai_control_plane_lifecycle.py": "db54b75baf53080a4b1a373f85763e8c6d29d81ae0f5981eb3259fbede072e73",
    "fixtures/checker-contracts/openai-federation-revocation.json": "9ea022b062f61e5d48f5cbef8b1295944743c6b9e3fe96e53a0e9e7af56ce2ee",
    "fixtures/checker-contracts/openai-signing-key-rotation.json": "e2bfd2c0d4f096cd991a44d5401ca689b328ba437548521c5a156a34d5d17d50",
    "fixtures/checker-contracts/credential-qualification-conforming.json": "00301b44a5d7ac1592f6591d3428aeb272f2d2e7cf7793ed5d05cccdd941c36e",
    "fixtures/checker-contracts/credential-qualification-missing-requirements.json": "5caec87918dc89db7e47d1b37f3dde8b7fac912b9fb273f9fa01562bbc4ae527",
    "infra/ansible/tests/test_child_launcher.py": "288f0a9ec44d8bb055606905878702e7d60ba4d3313b4b9c05b2ecca96b38b00",
    "infra/ansible/tests/test_cloud_init_bootstrap.py": "c0c79b21c2f0ed236667fc8176c1c834f1753991fef35ef6a03f4a21fe6bca04",
    "infra/ansible/tests/test_dashboard_checkout.py": "0d7ab333e389409cf16af40d2c4269b82d22dcf3b27bfd911a18dac031c5de1c",
    "infra/ansible/tests/test_log_secret_scan.py": "c03a26dd05028c1e1986a5db544cb23feeacac9758c4cc4e275ffa90a511c880",
    "infra/ansible/tests/test_preview_capability_deployment.py": "f8b44dfa110c4f099711487729e5afd222ae6218beb487d5a31d39a6ee580481",
    "infra/ansible/tests/test_replace_worker.py": "d04bb7e7351f865ba47d9cbd3acf3633eda6c4a3d0f1e9807598282c785635fb",
    "infra/ansible/tests/test_session14_qualification.py": "832f8931dd2a4cb78f677dc991f66a8f7f81599edf74c30483d3cf924d9e0e68",
    "infra/ansible/tests/test_session15_proposer.py": "732b56e62a789f3f442539f5bf88431dd5285558f67274d369784395d6510cb5",
    "infra/ansible/tests/test_session16_cutover.py": "b559f960618e694d218a345efc222249a771f665899bd696a20682125dda9b73",
    "infra/ansible/tests/test_triage_seat_deployment.py": "39c59226c5c472525ef1a95d5ff6c3398617e1303d271cecdf0afbe64b313e49",
    "infra/ansible/roles/control_plane/files/patchyard-log-secret-scan": "356c4a962a262f4128cd22496b068dbf4b02c8a3867214c7c31f80e1ebb11eb8",
    "infra/ansible/roles/control_plane/files/patchyard-mint-seat-bearer": "6b0c88263b4ff4ba2cc22ecc3d892c3b962a62aa64f1375eb31ab25705f6baaf",
    "infra/ansible/roles/control_plane/files/patchyard-request-seat-bearer": "20958c674ecb24e19a8aabb11910189e10a6413187f90cd017e8698978b254a0",
    "infra/ansible/roles/control_plane/files/patchyard-triage-seat": "ae414ec9427f8b0cbace8fc140850fb4a7b3bfd041880ae927677ebc98fc30a3",
}
EXPECTED_TEST_FILES = (
    "infra/ansible/tests/test_a101_readiness_root.py",
    "infra/ansible/tests/test_attended_collector_runner.py",
    "infra/ansible/tests/test_anthropic_issuance.py",
    "infra/ansible/tests/test_anthropic_lifecycle.py",
    "infra/ansible/tests/test_anthropic_spend.py",
    "infra/ansible/tests/test_anthropic_wif_admin.py",
    "infra/ansible/tests/test_child_launcher.py",
    "infra/ansible/tests/test_cloud_init_bootstrap.py",
    "infra/ansible/tests/test_dashboard_checkout.py",
    "infra/ansible/tests/test_freeze_graph.py",
    "infra/ansible/tests/test_live_review_disposition_seats.py",
    "infra/ansible/tests/test_log_secret_scan.py",
    "infra/ansible/tests/test_merge_refix.py",
    "infra/ansible/tests/test_neutral_guest_qualification.py",
    "infra/ansible/tests/test_openai_control_plane_lifecycle.py",
    "infra/ansible/tests/test_openai_wif_issuance.py",
    "infra/ansible/tests/test_preview_capability_deployment.py",
    "infra/ansible/tests/test_replace_worker.py",
    "infra/ansible/tests/test_session14_qualification.py",
    "infra/ansible/tests/test_session15_proposer.py",
    "infra/ansible/tests/test_session16_cutover.py",
    "infra/ansible/tests/test_triage_seat_deployment.py",
    "infra/ansible/tests/test_worker_firewall_readiness.py",
)
EXPECTED_TOOL_PYTHON_FILES = (
    "tools/aa-join.py",
    "tools/aa-sweep.py",
    "tools/anthropic-spend-evidence.py",
    "tools/anthropic-wif-admin.py",
    "tools/anthropic-wif-crash-cleanup.py",
    "tools/anthropic-wif-lifecycle-admin.py",
    "tools/anthropic-wif-lifecycle.py",
    "tools/answer-attended-prompt.py",
    "tools/anthropic-wif-revocation.py",
    "tools/attended-collector-runner.py",
    "tools/benchmark_harmonyagent_cerebras.py",
    "tools/benchmark_harness_speed.py",
    "tools/benchmark_spec_speed.py",
    "tools/check-a101-readiness-root.py",
    "tools/check-anthropic-crash-cleanup.py",
    "tools/check-anthropic-expiry.py",
    "tools/check-anthropic-issuance.py",
    "tools/check-anthropic-revocation.py",
    "tools/check-anthropic-spend.py",
    "tools/check-bench.py",
    "tools/check-credential-qualification.py",
    "tools/check-freeze-graph.py",
    "tools/check-independence.py",
    "tools/check-openai-spend.py",
    "tools/check-openai-wif-crash-cleanup.py",
    "tools/check-openai-wif-expiry.py",
    "tools/check-openai-wif-federation-revocation.py",
    "tools/check-openai-wif-issuance.py",
    "tools/check-openai-wif-signing-key-rotation.py",
    "tools/check-preview-runtime.py",
    "tools/check-seats.py",
    "tools/check-signing-identities.py",
    "tools/check-stack.py",
    "tools/check-worker-qualification.py",
    "tools/check-worker-runtime.py",
    "tools/codebase-metrics.py",
    "tools/control-plane-attestation-v1.py",
    "tools/merge-refix.py",
    "tools/openai-spend-evidence.py",
    "tools/openai-wif-crash-cleanup.py",
    "tools/openai-wif-expiry.py",
    "tools/openai-wif-federation-revocation.py",
    "tools/openai-wif-issuance.py",
    "tools/openai-wif-signing-key-rotation.py",
    "tools/read-infra-tool-version.py",
    "tools/run-isolated-unittest.py",
    "tools/validate-lessons-report.py",
)
INFRA_CHECKERS = (
    "check-freeze-graph.py",
    "check-credential-qualification.py",
    "check-stack.py",
    "check-independence.py",
    "check-worker-runtime.py",
    "check-worker-qualification.py",
    "check-anthropic-spend.py",
    "check-anthropic-issuance.py",
    "check-anthropic-expiry.py",
    "check-anthropic-revocation.py",
    "check-anthropic-crash-cleanup.py",
    "check-openai-wif-issuance.py",
    "check-openai-wif-expiry.py",
    "check-openai-wif-crash-cleanup.py",
    "check-openai-wif-federation-revocation.py",
    "check-openai-wif-signing-key-rotation.py",
    "check-openai-spend.py",
    "check-preview-runtime.py",
    "check-signing-identities.py",
)
PROTECTED_MODULE_FILES = {
    "_hashlib.py",
    "ast.py",
    "copy.py",
    "datetime.py",
    "decimal.py",
    "hashlib.py",
    "importlib.py",
    "json.py",
    "os.py",
    "pathlib.py",
    "re.py",
    "shlex.py",
    "shutil.py",
    "subprocess.py",
    "sys.py",
    "sysconfig.py",
    "tempfile.py",
    "typing.py",
    "unittest.py",
    "yaml.py",
}
STDLIB_MODULES = (hashlib, importlib, re, sysconfig)


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def isolation_errors() -> list[str]:
    errors: list[str] = []
    if not sys.flags.isolated:
        errors.append("A101 readiness trust root requires python3 -I")

    stdlib = Path(sysconfig.get_path("stdlib")).resolve()
    for module in STDLIB_MODULES:
        source = getattr(module, "__file__", None)
        if source is None or not is_within(Path(source).resolve(), stdlib):
            errors.append(
                f"A101 readiness trust root rejected {module.__name__} provenance: "
                f"{source!r}"
            )

    for entry in sys.path:
        try:
            resolved = Path(entry).resolve()
        except OSError:
            continue
        if is_within(resolved, REPO):
            errors.append(f"A101 readiness trust root has repository import path: {entry}")
    return errors


def expected_workflow(pin: str) -> str:
    return """name: Infrastructure

on:
  pull_request:
  push:
    branches:
      - master

permissions:
  contents: read

jobs:
  infrastructure:
    name: infrastructure
    runs-on: ubuntu-latest
    timeout-minutes: 20

    steps:
      - name: Check out the reviewed revision
        uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0
        with:
          # Session 16 rollback contracts execute against exact merged anchors.
          fetch-depth: 0

      - name: Verify A101 readiness trust root
        run: |
          printf '%s\\n' \\
            '__ROOT_PIN__' \\
            | sha256sum --check
          python3 -I tools/check-a101-readiness-root.py

      - name: Install pinned OpenTofu
        uses: opentofu/setup-opentofu@9d84900f3238fab8cd84ce47d658d25dd008be2f # v1.0.8
        with:
          tofu_version: 1.12.0

      - name: Prepare Python 3.11
        uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5.6.0
        with:
          python-version: "3.11"
          cache: pip
          cache-dependency-path: infra/ansible/requirements.txt

      - name: Warm the Rust cache for Session 1
        uses: Swatinem/rust-cache@c19371144df3bb44fab255c43d04cbc2ab54d1c4 # v2.9.1

      - name: Install pinned Ansible runtime
        run: |
          python -m pip install --requirement infra/ansible/requirements.txt
          ansible-galaxy collection install --requirements-file infra/ansible/requirements.yml

      - name: Install pinned ShellCheck
        run: |
          SHELLCHECK_BIN_DIR="$RUNNER_TEMP/shellcheck-bin" tools/install-shellcheck.sh
          echo "$RUNNER_TEMP/shellcheck-bin" >> "$GITHUB_PATH"

      - name: Validate OpenTofu and stack doctrine
        run: tools/check-infra.sh

      - name: Lint and syntax-check Ansible
        if: ${{ always() }}
        run: tools/check-ansible.sh
""".replace("__ROOT_PIN__", pin)


def validate() -> list[str]:
    errors = isolation_errors()
    for relative, expected in BOUND_SOURCES.items():
        path = REPO / relative
        if not path.is_file():
            errors.append(f"bound A101 source is missing: {relative}")
            continue
        if path.is_symlink():
            errors.append(f"bound A101 source is a symlink: {relative}")
            continue
        actual = digest(path)
        if actual != expected:
            errors.append(
                f"bound A101 source differs: {relative} "
                f"(expected {expected}, observed {actual})"
            )

    expected_tests = set(EXPECTED_TEST_FILES)
    observed_infra_python = {
        str(path.relative_to(REPO))
        for path in (REPO / "infra").rglob("*.py")
        if path.is_file()
    }
    for missing in sorted(expected_tests - observed_infra_python):
        errors.append(f"explicit Ansible test census is missing: {missing}")
    for unexpected in sorted(observed_infra_python - expected_tests):
        errors.append(f"unexpected infrastructure Python source: {unexpected}")

    expected_tools = set(EXPECTED_TOOL_PYTHON_FILES)
    observed_tools = {
        str(path.relative_to(REPO))
        for path in (REPO / "tools").iterdir()
        if path.name.endswith(".py")
    }
    for missing in sorted(expected_tools - observed_tools):
        errors.append(f"explicit tools Python census is missing: {missing}")
    for unexpected in sorted(observed_tools - expected_tools):
        errors.append(f"unexpected tools Python source: {unexpected}")

    for path in REPO.rglob("__init__.py"):
        if path.is_file():
            errors.append(
                "repository package initializer is forbidden: "
                f"{path.relative_to(REPO)}"
            )
    for path in REPO.rglob("*.py"):
        if path.is_file() and path.name in PROTECTED_MODULE_FILES:
            errors.append(
                "repository shadows a protected Python module: "
                f"{path.relative_to(REPO)}"
            )

    wrapper_path = REPO / "tools/check-ansible.sh"
    if wrapper_path.is_file():
        wrapper = wrapper_path.read_text()
        file_block_match = re.search(
            r"(?ms)^TEST_FILES=\(\n(?P<body>.*?)^\)\n",
            wrapper,
        )
        if file_block_match is None:
            errors.append("Ansible wrapper has no explicit TEST_FILES census")
        else:
            observed_files = tuple(
                line.strip()
                for line in file_block_match.group("body").splitlines()
                if line.strip()
            )
            if observed_files != EXPECTED_TEST_FILES:
                errors.append("Ansible wrapper TEST_FILES census differs")
        if wrapper.count(
            'run_gate python3 -I "$REPO_ROOT/tools/check-anthropic-spend.py"'
        ) != 1:
            errors.append("Ansible wrapper lacks one isolated spend-checker process")
        if wrapper.count(
            'python3 -I "$REPO_ROOT/tools/check-a101-readiness-root.py"'
        ) != 2:
            errors.append("Ansible wrapper lacks two isolated trust-root checks")
        if wrapper.count(
            'run_gate python3 -I "$REPO_ROOT/tools/run-isolated-unittest.py"'
        ) != 1:
            errors.append("Ansible wrapper lacks its isolated file runner")
        if "unittest discover" in wrapper or "-m unittest" in wrapper:
            errors.append("Ansible wrapper still imports tests as repository packages")

    infra_wrapper_path = REPO / "tools/check-infra.sh"
    if infra_wrapper_path.is_file():
        infra_wrapper = infra_wrapper_path.read_text()
        if infra_wrapper.count(
            'python3 -I "$REPO_ROOT/tools/check-a101-readiness-root.py"'
        ) != 1:
            errors.append("infrastructure wrapper lacks its isolated trust-root check")
        for checker in INFRA_CHECKERS:
            invocation = f'run_gate python3 -I "$REPO_ROOT/tools/{checker}"'
            if infra_wrapper.count(invocation) != 1:
                errors.append(
                    f"infrastructure wrapper lacks one isolated aggregate call: {checker}"
                )
        spend_call = 'run_gate python3 -I "$REPO_ROOT/tools/check-anthropic-spend.py"'
        issuance_call = (
            'run_gate python3 -I "$REPO_ROOT/tools/check-anthropic-issuance.py"'
        )
        expiry_call = (
            'run_gate python3 -I "$REPO_ROOT/tools/check-anthropic-expiry.py"'
        )
        revocation_call = (
            'run_gate python3 -I "$REPO_ROOT/tools/check-anthropic-revocation.py"'
        )
        crash_call = (
            'run_gate python3 -I "$REPO_ROOT/tools/check-anthropic-crash-cleanup.py"'
        )
        openai_call = (
            'run_gate python3 -I "$REPO_ROOT/tools/check-openai-wif-issuance.py"'
        )
        openai_expiry_call = (
            'run_gate python3 -I "$REPO_ROOT/tools/check-openai-wif-expiry.py"'
        )
        openai_crash_call = (
            'run_gate python3 -I "$REPO_ROOT/tools/check-openai-wif-crash-cleanup.py"'
        )
        openai_revocation_call = (
            'run_gate python3 -I "$REPO_ROOT/tools/check-openai-wif-federation-revocation.py"'
        )
        openai_rotation_call = (
            'run_gate python3 -I "$REPO_ROOT/tools/check-openai-wif-signing-key-rotation.py"'
        )
        preview_call = 'run_gate python3 -I "$REPO_ROOT/tools/check-preview-runtime.py"'
        try:
            spend_index = infra_wrapper.index(spend_call)
            issuance_index = infra_wrapper.index(issuance_call)
            expiry_index = infra_wrapper.index(expiry_call)
            revocation_index = infra_wrapper.index(revocation_call)
            crash_index = infra_wrapper.index(crash_call)
            openai_index = infra_wrapper.index(openai_call)
            openai_expiry_index = infra_wrapper.index(openai_expiry_call)
            openai_crash_index = infra_wrapper.index(openai_crash_call)
            openai_revocation_index = infra_wrapper.index(openai_revocation_call)
            openai_rotation_index = infra_wrapper.index(openai_rotation_call)
            preview_index = infra_wrapper.index(preview_call)
        except ValueError:
            errors.append(
                "infrastructure wrapper lacks a required lifecycle/preview checker"
            )
        else:
            if not (
                spend_index
                < issuance_index
                < expiry_index
                < revocation_index
                < crash_index
                < openai_index
                < openai_expiry_index
                < openai_crash_index
                < openai_revocation_index
                < openai_rotation_index
                < preview_index
            ):
                errors.append("infrastructure aggregate checker ordering differs")
        if infra_wrapper.splitlines()[-1:] != ['exit "$gate_status"']:
            errors.append("infrastructure wrapper does not preserve aggregate failure")

    for relative in (
        "tools/check-infra.sh",
        "tools/check-ansible.sh",
        "tools/install-shellcheck.sh",
    ):
        path = REPO / relative
        if path.is_file() and "source \"$REPO_ROOT/infra/tool-versions.env\"" in path.read_text():
            errors.append(f"{relative} executes infrastructure tool-version data")
        if path.is_file() and re.search(
            r'(?m)^\s*python3\s+"\$REPO_ROOT/tools/(?:check-|read-infra)',
            path.read_text(),
        ):
            errors.append(f"{relative} contains a non-isolated Python gate")

    install = REPO / "tools/install-shellcheck.sh"
    if install.is_file() and install.read_text().count(
        'python3 -I "$REPO_ROOT/tools/read-infra-tool-version.py"'
    ) != 3:
        errors.append("ShellCheck installer does not isolate all three pin reads")
    qualify = REPO / "infra/ansible/qualify.sh"
    if qualify.is_file() and qualify.read_text().count(
        'python3 -I "$REPO_ROOT/tools/check-independence.py"'
    ) != 1:
        errors.append("live qualifier does not isolate its independence checker")

    if WORKFLOW.is_file():
        workflow = WORKFLOW.read_text()
        root_digest = digest(Path(__file__))
        pin = f"{root_digest}  tools/check-a101-readiness-root.py"
        if workflow.count(pin) != 1:
            errors.append("infrastructure workflow does not pin this trust-root checker")
        if workflow != expected_workflow(pin):
            errors.append("infrastructure workflow differs from its exact fail-closed binding")
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
