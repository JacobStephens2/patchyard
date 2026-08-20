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
    "tools/check-infra.sh": "4a0bd59083afbf5e5afd6fda5c5f0f7668187b9602feecfc99f9bbae73405152",
    "tools/check-ansible.sh": "36c00f46f8e70c1302a425741b588d989ce1b8c85d85735fb7d59e0db0f6a52c",
    "tools/run-isolated-unittest.py": "f201a6a57353b485d15a47b803bf274cdf9033ef1e78ed3e07e6f188a728ecc7",
    "tools/check-credential-qualification.py": "7080339d1c05c7cfc0af4f57d57c12151048b21ba7d174e76c106688946ab320",
    "tools/anthropic-spend-evidence.py": "494cba4a628e592004dc975ead283aa32fe1fbfe6236c6d6a4a7c7d7ee733099",
    "tools/openai-spend-evidence.py": "49a8152ec73128717957fffe21faf2321f10ac285371e9187a1fcee1c204078c",
    "tools/check-openai-spend.py": "610e5cb37e82d7a15ff0e23ffab465b13f5b47734986363300786bd92f893574",
    "worker/qualification/patchyard-run-openai-spend": "0218da08c26700d5b04b2ab92c758eb1eddd428ceeb2cb2ff6842dfb141d7cb4",
    "tools/anthropic-wif-admin.py": "89794bd6235d5b37dfa4999a792588396ece9935b17820954b75d8b055822c91",
    "tools/anthropic-wif-lifecycle.py": "10dfc4b3dc0002396f651734ff71f9618c119acde0065d6287193efed492873d",
    "tools/anthropic-wif-revocation.py": "ef4c204880cdc002ccee17f080b6011191a183c07e3ae173b34beb215737b61f",
    "tools/anthropic-wif-crash-cleanup.py": "88bb709eb662734fd85d17ac30b0d30592fadbbd83ce366f17e84ea0143e844c",
    "tools/anthropic-wif-lifecycle-admin.py": "1a1e08060a5ad68f65b3a798e2b992ee2c34fc336e4f7fd8922bfdf2effecc55",
    "tools/openai-wif-issuance.py": "c53617ee45bb08f0b4aab9d4a4fa07788234abe4a6f2077a35d7a6f3357611d5",
    "tools/openai-wif-expiry.py": "44d7007ed7b9fe9468d163caf559b155eb62a40e063a553b087bc9931a6f54c8",
    "tools/openai-wif-crash-cleanup.py": "db94f9c8bda879439c48adc1c8d26ea9af617eac5e1b5ec8a42878eb5ecda192",
    "tools/control-plane-attestation-v1.py": "0d32e80b980c334977e51eb706783896a687d29faef46d50e53f3ee56e8e4d47",
    "tools/openai-wif-federation-revocation.py": "63fc81422a19c19cb53f69cdeb69f1842c187a3b1d793bcf1fd572e186d1cb44",
    "tools/check-openai-wif-federation-revocation.py": "52c14ac1843051ea0dca0ed048bba381b6ba51921d0ef01d83b6bdfb4456c443",
    "tools/openai-wif-signing-key-rotation.py": "7f937d6b4d57a623712bbc3f60a10e99beade6bbed916ae3332647e83c0280b2",
    "tools/check-openai-wif-signing-key-rotation.py": "d9330b4c10e5273561829a37ba5641678a0bbb065f68d14975f1e5c0b3174f3d",
    "tools/check-anthropic-expiry.py": "8d9de38c16bbcc4ad63a73a0f570703581f8264371503385ef513057ff0f8ca8",
    "tools/check-anthropic-spend.py": "f87e2bec8b015222193dc3eaf7853622844e8aa0f0683c3a8fb8723d7dd03a4d",
    "tools/check-anthropic-issuance.py": "c3896ebf62fbf605ec4055bc020aa695026d72a821cbfeaf0d5a3fda0a62fe46",
    "tools/check-anthropic-revocation.py": "748cea22f9ece87dee2b6915f3609c8041cae1b5d6fdfd27b1f165901d9d7297",
    "tools/check-anthropic-crash-cleanup.py": "35dd6d624e4302dd230560b1380736eb43df3aa6b345015a4fce3f429d354e66",
    "tools/check-openai-wif-issuance.py": "5475f594f3316f3622af961cda2246c1313cabfdc9f84e2cf8710a04b26f80a5",
    "tools/check-openai-wif-expiry.py": "4e7507053d0cb7d45e40a76666bdcf6cbc3014c22e9bf0a910ccaff43d96b4e0",
    "tools/check-openai-wif-crash-cleanup.py": "2b7b3fdc34a72c3a96d7e3afb60f18cf04a33cb75012c17e6543d94df3db90a0",
    "tools/check-independence.py": "baaa2e5058862a253c5042e7ccaea4bfea8af05a93825f5ce5cf99bbd1f93782",
    "tools/check-preview-runtime.py": "2f9a6e994c3d50e7e1f729546b3180330c4ccf0d471ee5b75f016cbbc95292be",
    "tools/check-openai-identity-liveness.py": "607926928985f0462111e672d7988f2e1c588bb854434fbf733db8e38e01679a",
    "tools/check-signing-identities.py": "368f4edca351829d21b98621d8dc5dad49262cd48d03268cc0735005b140e165",
    "tools/check-stack.py": "ddce869a4bd4983c35c1b246ba01b5e8b1ea25219c761ebbdb2d5b4a8194deff",
    "tools/check-worker-qualification.py": "e9d5662bed3f7002fb6b0d23b777f12a401e8f9a0be4d340a5cf7580fdb3f15d",
    "tools/check-worker-runtime.py": "2ba1b99160441214acd53e4d8ed3aeb69aedbb540c0960cd47c02b0ecfe1d3c3",
    "infra/ansible/tests/test_a101_readiness_root.py": "6be1b217ec44db6f7858143e5e4696914c97d6978a6fdb9ed4643b065f21dbd8",
    "infra/ansible/tests/test_freeze_graph.py": "fceb032ad52170ac6743e561937bab47b61bbfb4652d1a398de56372a3081927",
    "infra/ansible/tests/test_worker_firewall_readiness.py": "aee76db6075ca6450fdcc38537f5688cb519664ef6270ef163b93672151b1918",
    "infra/ansible/tests/test_anthropic_spend.py": "6182ffe6006e5fd09245300d4035530c6207f4f2ffd9cfc800950263ec8d0b42",
    "infra/ansible/tests/test_anthropic_issuance.py": "bde14af86dcc84cf1a618af2ed91c099b82e718523b2b16245fb7e52c8a4824a",
    "infra/ansible/tests/test_anthropic_lifecycle.py": "55c0296ef879e263172e5c7418b085ca317378b5030b65619017d1bd072ec057",
    "infra/ansible/tests/test_anthropic_wif_admin.py": "1d53f8ffe4ef6ad55b8d7187705344836aed831337c26f310bd11538888a9670",
    "infra/ansible/tests/test_openai_wif_issuance.py": "b4b4713b3fd90c7892fa865382425346477d95a4ad4f657c324dbf9347d29345",
    "infra/ansible/tests/test_openai_control_plane_lifecycle.py": "2af2bed6b29ad323b19bcf04b93dd8940774041d72f77d2928789b21ae8d7810",
    "fixtures/checker-contracts/openai-federation-revocation.json": "e9111b48f59d3c7349d7fcb966ffaa7ae78a109044f8917afc151c20353f22bf",
    "fixtures/checker-contracts/openai-signing-key-rotation.json": "5ad7bb5efb7a3dd25ece00a53012c00df7f1b1154e1e00e12c10b479bf8801bc",
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
    "tools/check-openai-identity-liveness.py",
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
    "check-openai-identity-liveness.py",
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
            'python3 -I "$REPO_ROOT/tools/run-isolated-unittest.py"'
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
