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
    "infra/ansible/converge.sh": "30a8758d6925ffa7635212cc49c67719ba7a6abf6d389481da2e422dec41f63e",
    "infra/ansible/qualify.sh": "2423bb69fe19e355458158b4b49a67917dac0279bfe76110256944974533dd49",
    "infra/ansible/inventory/tofu.sh": "7101838ae5f3eae5031c30888ae6eda754d9519f6af9d2d6884142155f69bb59",
    "infra/ansible/roles/control_plane/templates/patchyard-management-ssh.j2": "fdd1020be15cc56c6c0207c68a876084737ef2fdaa63f74e16e8f8d8e5c41c4b",
    "infra/tool-versions.env": "63fa7fa217d98d914a73394c98b41f97571c5c776b3a9b2d4c51d95e56ab917f",
    "tools/read-infra-tool-version.py": "d94d97d605736d0201d0fc0517e0e780d6c346ab79ddc3bd84de7b472edeccd8",
    "tools/install-shellcheck.sh": "715047c90f6a877c57a5495f1bc24feecd40f365ccd8239a6dc711be22a3f535",
    "tools/check-infra.sh": "2b3d220f26cb7e1d43e6cde3aacfc214d0943a4ee72aa3175f18c698d26d461e",
    "tools/check-ansible.sh": "5506004cd1658979e907acddcf5aafe6fa46788993b477bb25d6c8150224e88b",
    "tools/run-isolated-unittest.py": "93cac4593b3d3cf928bb4310b856dc7163351b104602c9788092b00c7df1935e",
    "tools/anthropic-spend-evidence.py": "494cba4a628e592004dc975ead283aa32fe1fbfe6236c6d6a4a7c7d7ee733099",
    "tools/anthropic-wif-admin.py": "89794bd6235d5b37dfa4999a792588396ece9935b17820954b75d8b055822c91",
    "tools/anthropic-wif-lifecycle.py": "10dfc4b3dc0002396f651734ff71f9618c119acde0065d6287193efed492873d",
    "tools/anthropic-wif-revocation.py": "ef4c204880cdc002ccee17f080b6011191a183c07e3ae173b34beb215737b61f",
    "tools/anthropic-wif-crash-cleanup.py": "88bb709eb662734fd85d17ac30b0d30592fadbbd83ce366f17e84ea0143e844c",
    "tools/anthropic-wif-lifecycle-admin.py": "1a1e08060a5ad68f65b3a798e2b992ee2c34fc336e4f7fd8922bfdf2effecc55",
    "tools/openai-wif-issuance.py": "7f7515d9279116a9daf59e7c5cfee4b4361b64247c44f1899453b754fbb20132",
    "tools/openai-wif-expiry.py": "bcc5da8d92d1cb12c1dbe450f9acf35684d4388c932b4e41e841ac9e8b20b5dc",
    "tools/openai-wif-crash-cleanup.py": "a160cc713f8ef528244fc4a9aaf81c21d94f99ee6636ccae4558acb93d2c49b5",
    "tools/control-plane-attestation-v1.py": "0d32e80b980c334977e51eb706783896a687d29faef46d50e53f3ee56e8e4d47",
    "tools/openai-wif-federation-revocation.py": "e00892365e8392c1c97a7add258813c0824d3d141cfe33650122acf4074153e7",
    "tools/check-openai-wif-federation-revocation.py": "58a1a2c10fbae5511d51feec774c8bc328a3271899343ef967d482a8e902f623",
    "tools/openai-wif-signing-key-rotation.py": "b06b5b1f424ccb7a1dbb640aa85e3658c746e93385b08beff3c99c580a2e5234",
    "tools/check-openai-wif-signing-key-rotation.py": "88fdd4991f18375be19d39a213e0b753af169432796cde8c771a24457972b0b8",
    "tools/check-anthropic-expiry.py": "41904ee87d54c362c9714c3c06853e5f67047365847edc9431620d62bc5a9c54",
    "tools/check-anthropic-spend.py": "9d225ad42fe5391ddfc41859a5c3432d2416eff5aaa99babdbbf3b16230f0938",
    "tools/check-anthropic-issuance.py": "905dc24ee6ea8ed2aa171c0bc3fc677ff3ff73a4c2f781f6340a76a311229e76",
    "tools/check-anthropic-revocation.py": "deeba4038169d466a31bbcf4d263fe8ac1bdf0aa5bd9365f4449da8e80db085c",
    "tools/check-anthropic-crash-cleanup.py": "770a339f2d6c36c849968b9fed914ebb2fce518e0cc1458c8c0fb98648a6e278",
    "tools/check-openai-wif-issuance.py": "d23b3cac210c9c80982409adf85d130a7a8042b772b500773e837954c41c62b6",
    "tools/check-openai-wif-expiry.py": "2f66e0b540829fad6d8813471c7e106eaeb71aacbd63f6c7f7abab22ce31f917",
    "tools/check-openai-wif-crash-cleanup.py": "4bcf134f51b72e058b6c7720089dec9c60734e7e6c01aeb6997cae205b9e8474",
    "tools/check-independence.py": "baaa2e5058862a253c5042e7ccaea4bfea8af05a93825f5ce5cf99bbd1f93782",
    "tools/check-preview-runtime.py": "2f9a6e994c3d50e7e1f729546b3180330c4ccf0d471ee5b75f016cbbc95292be",
    "tools/check-stack.py": "ddce869a4bd4983c35c1b246ba01b5e8b1ea25219c761ebbdb2d5b4a8194deff",
    "tools/check-worker-qualification.py": "357d756da3c83004db6766956a8c31b9682953a50b470dbb3ff7b9acb879e99a",
    "tools/check-worker-runtime.py": "db1646d9bcf738d1df35679e131b1afdb9e35af73be1859d85c8f4017385ce75",
    "infra/ansible/tests/test_a101_readiness_root.py": "78f21b312f14cdde162ece12c7a80e3fa45f872f6a0df959bcabbd2120e1ef8c",
    "infra/ansible/tests/test_freeze_graph.py": "5d83e2ab9c0902b54650e5588c718eb01edfee71b47c0f9693f55853d0a24938",
    "infra/ansible/tests/test_worker_firewall_readiness.py": "5b95a144237751685b62503c7425bdcc36c1ec9eea1f05afb18d5d904dab25f4",
    "infra/ansible/tests/test_anthropic_spend.py": "24f68c5e32d12868501f2adcb8262b158052227b0e9b5e82bbc30abba0f40e3b",
    "infra/ansible/tests/test_anthropic_issuance.py": "1cd6f3b71df6987c94a3bb02447aebfbb7106a8cfb412f0d751c2ddc76a7f882",
    "infra/ansible/tests/test_anthropic_lifecycle.py": "dba785d7000509be4e9495bfd4d6cf932e8a93f71a92b95877131db4452d14b9",
    "infra/ansible/tests/test_anthropic_wif_admin.py": "1d53f8ffe4ef6ad55b8d7187705344836aed831337c26f310bd11538888a9670",
    "infra/ansible/tests/test_openai_wif_issuance.py": "c74f628a4fa576c613a397f97260e0c2ad9181fd910bebeab64a6a30bd79c590",
    "infra/ansible/tests/test_openai_control_plane_lifecycle.py": "160f0b12c1b0ba362176bc037e9686036ee5d94f15b5594d9dd6238180418c67",
    "fixtures/checker-contracts/openai-federation-revocation.json": "c04b44479b6a670a4bc7466ee0b93958c52922b8c66681d5319b5500198e9a4f",
    "fixtures/checker-contracts/openai-signing-key-rotation.json": "c3e0faada73986b1ee7a4f2f8b8ef4807d1f20dc2edd2e1aa9b919e8a979bb8f",
    "infra/ansible/tests/test_child_launcher.py": "bff549994263407f9b96ec52383b120a159de2c987e2bada49ad13a99c6cd9c0",
    "infra/ansible/tests/test_cloud_init_bootstrap.py": "c0c79b21c2f0ed236667fc8176c1c834f1753991fef35ef6a03f4a21fe6bca04",
    "infra/ansible/tests/test_dashboard_checkout.py": "3f953bb76b11d9d8f8853310fb99938437691024f59a6c55aa5b5fb5cafefcad",
    "infra/ansible/tests/test_log_secret_scan.py": "c03a26dd05028c1e1986a5db544cb23feeacac9758c4cc4e275ffa90a511c880",
    "infra/ansible/tests/test_preview_capability_deployment.py": "f8b44dfa110c4f099711487729e5afd222ae6218beb487d5a31d39a6ee580481",
    "infra/ansible/tests/test_replace_worker.py": "d04bb7e7351f865ba47d9cbd3acf3633eda6c4a3d0f1e9807598282c785635fb",
    "infra/ansible/tests/test_session14_qualification.py": "4a121aeec4dff797e67f2a4d5f151c5a0a3f080cdef3499f0ab8f3fef84f41d3",
    "infra/ansible/tests/test_session15_proposer.py": "f66e21999bb5ede882371069de17256361fb7eea9738bc8fa97fcc5cf4f86a0e",
    "infra/ansible/tests/test_session16_cutover.py": "a93f1c4b4a844222473ce787ce4e5430621c3c496b049621d38e051bbe976ba3",
    "infra/ansible/roles/control_plane/files/patchyard-log-secret-scan": "356c4a962a262f4128cd22496b068dbf4b02c8a3867214c7c31f80e1ebb11eb8",
}
EXPECTED_TEST_FILES = (
    "infra/ansible/tests/test_a101_readiness_root.py",
    "infra/ansible/tests/test_anthropic_issuance.py",
    "infra/ansible/tests/test_anthropic_lifecycle.py",
    "infra/ansible/tests/test_anthropic_spend.py",
    "infra/ansible/tests/test_anthropic_wif_admin.py",
    "infra/ansible/tests/test_child_launcher.py",
    "infra/ansible/tests/test_cloud_init_bootstrap.py",
    "infra/ansible/tests/test_dashboard_checkout.py",
    "infra/ansible/tests/test_freeze_graph.py",
    "infra/ansible/tests/test_log_secret_scan.py",
    "infra/ansible/tests/test_merge_refix.py",
    "infra/ansible/tests/test_openai_control_plane_lifecycle.py",
    "infra/ansible/tests/test_openai_wif_issuance.py",
    "infra/ansible/tests/test_preview_capability_deployment.py",
    "infra/ansible/tests/test_replace_worker.py",
    "infra/ansible/tests/test_session14_qualification.py",
    "infra/ansible/tests/test_session15_proposer.py",
    "infra/ansible/tests/test_session16_cutover.py",
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
    "tools/anthropic-wif-revocation.py",
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
    "tools/check-freeze-graph.py",
    "tools/check-independence.py",
    "tools/check-openai-wif-issuance.py",
    "tools/check-openai-wif-expiry.py",
    "tools/check-openai-wif-crash-cleanup.py",
    "tools/check-openai-wif-federation-revocation.py",
    "tools/check-openai-wif-signing-key-rotation.py",
    "tools/check-preview-runtime.py",
    "tools/check-seats.py",
    "tools/check-stack.py",
    "tools/check-worker-qualification.py",
    "tools/check-worker-runtime.py",
    "tools/codebase-metrics.py",
    "tools/merge-refix.py",
    "tools/control-plane-attestation-v1.py",
    "tools/openai-wif-federation-revocation.py",
    "tools/openai-wif-signing-key-rotation.py",
    "tools/openai-wif-issuance.py",
    "tools/openai-wif-expiry.py",
    "tools/openai-wif-crash-cleanup.py",
    "tools/read-infra-tool-version.py",
    "tools/run-isolated-unittest.py",
    "tools/validate-lessons-report.py",
)
INFRA_CHECKERS = (
    "check-freeze-graph.py",
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
    "check-preview-runtime.py",
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
